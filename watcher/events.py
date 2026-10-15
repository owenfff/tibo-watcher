"""Conservative reset classification; never copy untrusted text into QQ messages."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

BEIJING = timezone(timedelta(hours=8))
BANKED = re.compile(r"\bbanked\s+resets?\b|重置券", re.I)
ACTION = r"(?:reset(?:s|ting)?|refresh(?:ed|ing)?|replenish(?:ed|ing)?|restor(?:ed|ing)?|topp?ed\s+up|top\s+up|credit(?:ed|ing)|grant(?:ed|ing)?|added|补发|重置|恢复|补充)"
QUOTA = r"(?:limits?|quotas?|credits?|usage|allowances?|budgets?|额度)"
RESET = re.compile(rf"{QUOTA}.{{0,70}}?{ACTION}|{ACTION}.{{0,70}}?{QUOTA}", re.I)
GRANT = re.compile(r"\b(?:will\s+)?credit\s+(?:every|all)\b.{0,50}\b(?:users?|accounts?)\b", re.I)
FUTURE = re.compile(r"\b(?:will|soon|tomorrow|tonight|plan(?:ning)?|going to|later|expect(?:ed)?|by end of day|lands? (?:by |in |end of|today))\b|预告|即将|稍后|预计|将会|将于", re.I)
UNCERTAIN = re.compile(r"\b(?:maybe|might|may|could|hope|hopefully|if|wish|would|should|not|never|hasn't|haven't|isn't|aren't|won't|can't|don't|didn't)\b|\?|？|可能|尚未|没有|并未|希望", re.I)
DONE = re.compile(rf"\b(?:we(?:'ve| have)?\s+(?:just\s+)?(?:reset|refreshed|credited|granted|added|topped up)|(?:have|has|were|was|are|is)(?:\s+\w+){{0,3}}\s+(?:reset|refreshed|replenished|restored|credited)|(?:reset|refresh)\s+(?:is\s+)?(?:done|complete(?:d)?)|(?:reset|credits?)\s+(?:has |have )?landed)\b|已(?:完成|重置|补发|到账|发放)", re.I)
ISSUED = re.compile(r"\b(?:we(?:'ve| have)?\s+(?:just\s+)?(?:given|issued|granted|added|credited)|(?:is|are|has|have)(?:\s+\w+){0,3}\s+(?:available|landed|issued|granted|added)|(?:reset|resets)\s+(?:has |have )?landed)\b|已(?:发放|到账)|重置券可用", re.I)


@dataclass(frozen=True)
class ResetEvent:
    status: str
    product: str
    banked: bool


def classify_reset(text: str) -> ResetEvent | None:
    text = ' '.join(text.replace('’', "'").split())
    # Ignore URLs: a linked slug must not create a reset signal.
    text = re.sub(r"https?://\S+|www\.\S+", "", text, flags=re.I)
    banked = bool(BANKED.search(text))
    if not (banked or RESET.search(text) or GRANT.search(text)):
        return None
    if re.search(r"\b(?:password|database|router|reset button|git reset)\b", text, re.I):
        return None
    if re.search(r"\b(?:will not|won't|did not|didn't|never)\s+(?:\w+\s+){0,2}(?:reset|refresh|credit|grant)\b", text, re.I):
        return None
    if re.search(r"^\s*(?:how|why|when|can|could|did|do|does|will|are|is|have|has|any)\b", text, re.I) and '?' in text:
        return None
    if not banked and not FUTURE.search(text) and re.search(r"\b(?:wish|wishful|every (?:day|week|month)|automatically resets? (?:daily|weekly))\b", text, re.I):
        return None
    product = ("Codex/ChatGPT Work" if re.search(r"\bcodex\b", text, re.I)
               and re.search(r"\bchatgpt\b", text, re.I) else
               "ChatGPT Work" if re.search(r"\bchatgpt\b", text, re.I) else "Codex")
    # A future promise, even a banked reset, never means the quota has arrived.
    if FUTURE.search(text):
        status = "疑似重置" if UNCERTAIN.search(text) else "预告"
    elif UNCERTAIN.search(text):
        status = "疑似重置"
    elif banked and ISSUED.search(text):
        status = "重置券"
    elif not banked and DONE.search(text):
        status = "已完成"
    else:
        status = "疑似重置"
    return ResetEvent(status, product, banked)


def beijing_time(raw: str) -> str:
    if not isinstance(raw, str):
        return "原帖未提供精确时间"
    try:
        dt = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        # Dayclaw's offset-free ISO timestamps are treated as UTC.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if not re.search(r"[T ]\d{2}:\d{2}", raw):
            return "原帖未提供精确时间"
    except (ValueError, TypeError):
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                return "原帖未提供精确时间"
        except (ValueError, TypeError):
            return "原帖未提供精确时间"
    return dt.astimezone(BEIJING).strftime('%m-%d %H:%M')


def format_qq(post) -> tuple[str, str]:
    event = classify_reset(post.body)
    if event is None:
        raise ValueError("not a reset event")
    when = beijing_time(post.created_at)
    conclusion = {"预告": "重置预告", "重置券": "发放重置券",
                  "已完成": "已完成重置", "疑似重置": "疑似重置"}[event.status]
    title = f"{event.product}{conclusion} 北京时间{when}"
    if event.banked:
        explanation = {"预告": "预告发放重置券，需领取或使用，不代表额度已自动重置。",
                       "重置券": "已发放可使用的重置券，不代表额度已自动重置。",
                       "疑似重置": "涉及重置券，发放或可用状态尚待确认。"}[event.status]
    else:
        explanation = {"预告": "预告自动重置或补发额度，尚未确认到账。",
                       "已完成": "已确认额度自动重置或补发，无需使用重置券。",
                       "疑似重置": "涉及额度重置或补发，方式及到账状态尚待确认。"}[event.status]
    body = (f"状态：{event.status}\n北京时间：{when}（原帖发布时间）\n"
            f"说明：{event.product}{explanation}\n来源：@thsottiaux")
    # All displayed text comes from fixed labels and parsed timestamps.
    assert len(title) <= 40 and not re.search(r"http|www\.", title + body, re.I)
    return title, body
