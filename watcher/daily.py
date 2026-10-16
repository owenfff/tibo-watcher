"""Recognize Tibo's numbered 28-day shipping series, including sub-updates."""
from __future__ import annotations

import re
from dataclasses import dataclass

DAY_PATTERN = (r"(?m)^\s*(?:roundup\s+of\s+)?day\s+"
               r"((?:[1-9]|1[0-9]|2[0-8])(?:\.[1-9][0-9]?)?)\s*"
               r"(?:/|of\s+28\b|[:：])")
DAY_MARKER = re.compile(DAY_PATTERN, re.I)
TOPICS = [
    (r"\bat capacity\b|\bcapacity\b", "满载优化", "模型满载及任务续跑相关改进"),
    (r"\bdisk\b|磁盘", "磁盘优化", "桌面应用磁盘占用相关优化"),
    (r"\bcontext\b|上下文", "上下文更新", "上下文容量及使用体验相关更新"),
    (r"\bauto-review\b|\bapprove for me\b", "自动审批更新", "自动审批及用量计算相关更新"),
    (r"\bmeeting notes\b", "会议纪要更新", "会议纪要相关更新"),
    (r"\bdecisions api\b", "决策接口更新", "决策接口相关更新"),
    (r"\bmemory\b|记忆", "记忆功能更新", "记忆功能相关更新"),
    (r"\bvoice\b|语音", "语音功能更新", "语音功能相关更新"),
    (r"\bapi\b|接口", "接口更新", "开发者接口相关更新"),
    (r"\bskills?\b|技能", "技能更新", "技能功能相关更新"),
]


@dataclass(frozen=True)
class DailyEvent:
    day: str
    conclusion: str
    status: str
    detail: str


def classify_daily(text: str) -> DailyEvent | None:
    # Keep newlines: a Day marker must start its own line, not occur inside
    # another person's quoted prose or an arbitrary sentence about a day.
    text = re.sub(r"https?://\S+|www\.\S+", "", text, flags=re.I)
    if re.match(r"\s*(?:RT|QT)\s+@", text, re.I):
        return None
    marker = DAY_MARKER.search(text)
    if not marker:
        return None
    return DailyEvent(marker[1], "每日进展", "每日更新", "产品进展，具体功能尚未自动归类")


def format_daily_qq(post, when: str, reset_event=None) -> tuple[str, str]:
    event = classify_daily(post.body)
    if event is None:
        raise ValueError("not a numbered daily update")
    text = re.sub(r"https?://\S+|www\.\S+", "", post.body, flags=re.I)
    reset = bool(re.search(r"\bresets?\b|重置", text, re.I)) and not re.search(
        r"\b(?:no reset|not reset|won't reset|will not reset)\b|不会重置", text, re.I)
    if reset_event is not None or reset:
        status = reset_event.status if reset_event else "疑似重置"
        banked = bool(re.search(r"\bbanked\s+resets?\b|重置券", text, re.I))
        conclusion = {"预告":"重置预告", "重置券":"发放重置券",
                      "已完成":"已完成重置", "疑似重置":"疑似重置"}[status]
        method = "可使用的重置券" if banked else "额度重置"
        certainty = {"预告":"尚未确认到账", "重置券":"不代表额度已自动重置",
                     "已完成":"原帖明确表示已完成", "疑似重置":"方式及到账状态尚待确认"}[status]
        detail = f"第{event.day}天更新涉及{method}，{certainty}"
    else:
        topic, detail = next(((label, detail) for pattern, label, detail in TOPICS
                             if re.search(pattern, text, re.I)),
                            (event.conclusion, event.detail))
        status, conclusion = event.status, topic
        # Keep completion and future promises distinct even within the series.
        if re.search(r"\b(?:might|maybe|could|tentative)\b|可能|暂定", text, re.I):
            status, conclusion = "疑似更新", "疑似每日更新"
        elif (re.search(r"\b(?:(?:we will|we'll)\s+(?:ship|release|launch|roll out|add|enable)|plan to|tomorrow|coming soon)\b|即将|将于|预告", text, re.I)
              and not re.search(r"\b(?:landed|shipped|released|increased|rolled out|improved|is live|is now available)\b|已上线|已发布", text, re.I)):
            status, conclusion = "更新预告", "每日更新预告"
        detail = f"第{event.day}天公布{detail}"
        if status != "每日更新":
            detail += "，尚未确认已经交付"
    title = f"Codex Day{event.day}{conclusion} 北京时间{when}"
    body = (f"状态：{status}\n北京时间：{when}（原帖发布时间）\n"
            f"说明：{detail}。\n来源：@thsottiaux")
    assert len(title) <= 40 and not re.search(r"http|www\.", title + body, re.I)
    return title, body
