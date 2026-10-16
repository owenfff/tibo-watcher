"""Public product plans only: explicit intent plus a Codex/ChatGPT Work action."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

PRODUCT = re.compile(r"\bcodex\b|\bchatgpt\s+work\b", re.I)
INTENT = re.compile(
    r"\b(?:will|planning|plan\s+to|going\s+to|aim(?:ing)?\s+to|targeting|"
    r"intend(?:ing)?\s+to|expect(?:ing)?\s+to|might|may|could)\b|"
    r"\b(?:coming|shipping|launching|releasing|rolling\s+out)\s+"
    r"(?:soon|today|tomorrow|this|next|in|by|at)\b|"
    r"\b(?:we(?:'re|\s+are)|the\s+team\s+is)\s+working\s+on\b|"
    r"\bcoming\s+to\b|计划|即将|预告|预计|将于|将会|正在开发", re.I)
ACTION = re.compile(
    r"\b(?:launch(?:ing)?|ship(?:ping)?|releas(?:e|ing)|roll(?:ing)?\s+out|"
    r"rollout|introduc(?:e|ing)|enabl(?:e|ing)|expand(?:ing)?|support(?:ing)?|"
    r"add(?:ing)?|bring(?:ing)?|available|coming\s+to|mak(?:e|ing)\s+.{0,40}\s+available|working\s+on)\b|"
    r"上线|发布|推出|开放|支持|增加|开发", re.I)
TIMING = re.compile(
    r"\b(?:today|tomorrow|tonight|next\s+(?:week|month)|this\s+week|"
    r"in\s+\d+\s+(?:hours?|minutes?|days?)|by\s+\d|at\s+\d)\b|"
    r"今天|明天|下周|本周|时间安排", re.I)
DELAY = re.compile(r"\b(?:delay(?:ed)?|postpon(?:e|ed)|reschedul(?:e|ed))\b|延期|推迟|改期", re.I)
NEGATIVE = re.compile(r"\b(?:will\s+not|won't|not\s+going\s+to|no\s+plans?\s+to)\b|没有计划|不会推出", re.I)
SPECULATIVE = re.compile(r"\b(?:might|may|could|hopefully|tentative(?:ly)?|subject\s+to|if)\b|可能|暂定|疑似", re.I)
TOPICS = [
    (r"\bwindows\b", "Windows支持"), (r"\blinux\b", "Linux支持"),
    (r"\bmacos\b", "macOS支持"), (r"\bios\b", "iOS支持"),
    (r"\bandroid\b", "Android支持"), (r"\bvoice\b|语音", "语音功能"),
    (r"\bimage\s+generation\b|图像生成", "图像生成功能"),
    (r"\bskills?\b|技能", "技能功能"), (r"\bmemory\b|记忆", "记忆功能"),
    (r"\bconnectors?\b|连接器", "连接器功能"),
    (r"\bmodels?\b|新模型", "新模型"),
]


@dataclass(frozen=True)
class PlanEvent:
    status: str
    product: str
    conclusion: str
    detail: str


def classify_plan(text: str) -> PlanEvent | None:
    text = ' '.join(text.replace('’', "'").split())
    text = re.sub(r"https?://\S+|www\.\S+", "", text, flags=re.I)
    if not PRODUCT.search(text) or not ACTION.search(text):
        return None
    if re.match(r"^(?:RT|QT)\s+@", text, re.I) or '?' in text or '？' in text:
        return None
    if re.search(r"\b(?:I\s+(?:wish|hope|plan|want)|would\s+love|rumou?rs?)\b|希望能|听说", text, re.I):
        return None
    delayed = bool(DELAY.search(text))
    if NEGATIVE.search(text) and not delayed:
        return None
    if not delayed and not INTENT.search(text):
        # A schedule statement must contain both an actual launch action and time.
        if not (TIMING.search(text) and re.search(
                r"\b(?:scheduled|launch(?:es)?|ships|release\s+(?:date|time))\b|定于", text, re.I)):
            return None
    codex = bool(re.search(r"\bcodex\b", text, re.I))
    work = bool(re.search(r"\bchatgpt\s+work\b", text, re.I))
    product = "Codex/ChatGPT Work" if codex and work else "Codex" if codex else "ChatGPT Work"
    topic = next((label for pattern, label in TOPICS if re.search(pattern, text, re.I)), "产品更新")
    if delayed:
        status, conclusion, detail = "时间安排", "上线时间调整", f"公开调整{topic}的上线安排"
    elif SPECULATIVE.search(text):
        status, conclusion, detail = "疑似计划", f"{topic}疑似计划", f"提及{topic}的可能安排，尚未确定"
    elif re.search(r"\b(?:rollout|roll(?:ing)?\s+out|expand(?:ing)?|available)\b|扩大开放", text, re.I):
        status, conclusion, detail = "上线预告", "开放范围预告", "预告扩大产品开放范围，尚不代表所有用户已获得访问权限"
    elif re.search(r"\bworking\s+on\b|正在开发", text, re.I):
        status, conclusion, detail = "计划", f"{topic}开发计划", f"公开表示正在开发{topic}，尚不代表已经上线"
    else:
        status = "时间安排" if TIMING.search(text) else "上线预告"
        conclusion = f"{topic}上线预告"
        detail = f"预告推出{topic}，尚不代表已经上线"
    return PlanEvent(status, product, conclusion, detail)


def _relative_target(post) -> str | None:
    # Only unambiguous durations are converted. Do not invent a timezone for
    # 'tomorrow', 'end of day', or a bare wall-clock time.
    clean = re.sub(r"https?://\S+|www\.\S+", "", post.body, flags=re.I)
    match = re.search(r"\bin\s+(?:about\s+|~\s*)?(\d+)\s+(minutes?|hours?|days?)\b", clean, re.I)
    if not match:
        return None
    try:
        dt = datetime.fromisoformat(post.created_at.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if not re.search(r"[T ]\d{2}:\d{2}", post.created_at):
            return None
        value = int(match[1])
        delta = timedelta(**{('minutes' if match[2].lower().startswith('minute') else
                              'hours' if match[2].lower().startswith('hour') else 'days'): value})
        return (dt + delta).astimezone(timezone(timedelta(hours=8))).strftime('%m-%d %H:%M')
    except (ValueError, AttributeError, OverflowError):
        return None


def format_plan_qq(post, when: str) -> tuple[str, str]:
    event = classify_plan(post.body)
    if event is None:
        raise ValueError("not a product plan")
    title_product = event.product
    title = f"{title_product}{event.conclusion} 北京时间{when}"
    if len(title) > 40 and title_product == "Codex/ChatGPT Work":
        title = f"Codex/Work{event.conclusion} 北京时间{when}"
    target = _relative_target(post)
    timing = f"；原帖相对时间折算预计北京时间{target}" if target else "；未确认精确执行时刻"
    body = (f"状态：{event.status}\n北京时间：{when}（原帖发布时间）\n"
            f"说明：{event.product}{event.detail}{timing}。\n来源：@thsottiaux")
    assert len(title) <= 40 and not re.search(r"http|www\.", title + body, re.I)
    return title, body
