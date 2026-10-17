"""Time-only replies require a verified link to Tibo's product/day post."""
from __future__ import annotations

import re
from dataclasses import dataclass
from .daily import classify_daily
from .plans import classify_plan
from .timing import BJ, EVIDENCE, UpdateTime, parse_update_time, post_datetime


def relevant_context(text):
    from .events import classify_reset
    return bool(classify_daily(text) or classify_plan(text) or classify_reset(text))


def timing_statement(text):
    clean = re.sub(r'https?://\S+|www\.\S+', '',text,flags=re.I).strip()
    if '?' in clean or '？' in clean or re.match(r'^(?:when|what|how|why|can you|will you)\b',clean,re.I):
        return False
    if re.search(r'\b(?:dinner|lunch|breakfast|birthday|vacation|tax|sleep|bedtime)\b',clean,re.I):
        return False
    action = re.search(r'\b(?:landing|lands?|shipping|ship|release|rollout|launch|ETA|EOD|delay(?:ed)?|postponed|sometime)\b',clean,re.I)
    bare = len(clean)<120 and re.match(r'^(?:(?:maybe|hopefully|about|around)\s+)?(?:in\b|within\b|today\b|tomorrow\b|tonight\b|soon\b|by\b|at\b|\d)',clean,re.I)
    return bool(EVIDENCE.search(clean) and (action or bare))


@dataclass(frozen=True)
class TimeReply:
    day: str
    reset: bool
    timing: UpdateTime


def classify_time_reply(post):
    if (post.source != "x" or not post.is_reply or post.is_repost or not post.context_id or not post.context_body
            or not relevant_context(post.context_body) or not timing_statement(post.body)):
        return None
    from .events import classify_reset
    # An explicit new product/reset statement takes precedence over inherited context.
    if classify_daily(post.body) or classify_plan(post.body) or classify_reset(post.body):
        return None
    if re.search(r"\b(?:already|was|were|have|has)\b.{0,30}\b(?:done|completed|landed)\b",post.body,re.I):
        return None
    timing = parse_update_time(post.body,post.created_at)
    if timing is None:
        return None
    day = classify_daily(post.context_body)
    reset = bool(re.search(r'\bresets?\b|重置',post.context_body,re.I)) and not re.search(r'\bno reset\b|不会重置',post.context_body,re.I)
    return TimeReply(day.day if day else '',reset,timing)


def _published(raw):
    dt=post_datetime(raw)
    return dt.astimezone(BJ).strftime('%m-%d %H:%M') if dt else '精确发布时间缺失'


def format_time_reply(post,event):
    timing=event.timing
    product='Codex' + (' Day'+event.day if event.day else '')
    status='疑似预告' if timing.uncertain else '预告'
    if timing.target is None and ('否定' in timing.note or '确定时间' in timing.note):
        status='时间待定'
    conclusion=('重置' if event.reset else '更新') + ('时间待定' if status=='时间待定' else '疑似预告' if timing.uncertain else '预告')
    suffix=timing.target.astimezone(BJ).strftime('%m-%d %H:%M')+('前' if timing.deadline else '') if timing.target else _published(post.created_at)
    title=f'{product}{conclusion} 北京时间{suffix}'
    line2=f'北京时间：{timing.chinese}'
    if timing.target:
        line2+=f'；{timing.note}'
    line2+=f'；回复发布于{_published(post.created_at)}'
    detail=('第'+event.day+'天的' if event.day else '')+('额度重置' if event.reset else '产品更新')+'时间补充，尚未确认完成。'
    source='来源：@thsottiaux'+('（Day'+event.day+' 后续回复）' if event.day else '（后续回复）')
    body=f'状态：{status}\n{line2}\n说明：{detail}\n{source}'
    assert len(title)<=40 and not re.search(r'http|www\.',title+body,re.I)
    return title,body


def enrich_timing(post,title,body):
    timing=parse_update_time(post.body,post.created_at)
    if timing is None or timing.target is None:
        return title,body
    # Avoid turning a past elapsed duration into a future release promise.
    if re.search(r'\b(?:took|spent|ago)\b',post.body,re.I):
        return title,body
    prefix=title.split(' 北京时间')[0]
    target=timing.target.astimezone(BJ).strftime('%m-%d %H:%M')+('前' if timing.deadline else '')
    title=prefix+' 北京时间'+target
    lines=body.splitlines()
    lines[1]=f'北京时间：{timing.chinese}；{timing.note}；原帖发布于{_published(post.created_at)}'
    lines[2]=lines[2].replace('未确认精确执行时刻','时间按原文折算，尚未确认已完成')
    assert len(title)<=40
    return title,'\n'.join(lines)
