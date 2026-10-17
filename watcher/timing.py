"""Conservative update-time parsing, anchored to the original post timestamp."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

BJ = timezone(timedelta(hours=8))
NUM = r'(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|twelve|twenty-four|a|an)'
WORDS = dict(one=1,two=2,three=3,four=4,five=5,six=6,seven=7,eight=8,nine=9,ten=10,twelve=12,a=1,an=1)
WORDS['twenty-four'] = 24
ZONE = r'(?:PST|PDT|PT|UTC(?:[+-]\d{1,2}(?::?\d{2})?)?|GMT(?:[+-]\d{1,2}(?::?\d{2})?)?)'
EVIDENCE = re.compile(r'\b(?:ETA|EOD|end of (?:the )?day|today|tomorrow|tonight|soon|no ETA|in\s+'+NUM+r'\s+(?:hours?|minutes?|days?)|within\b|\d{1,2}(?::\d{2})?\s*(?:am|pm)|\d{1,2}:\d{2})\b', re.I)


@dataclass(frozen=True)
class UpdateTime:
    target: datetime | None
    deadline: bool = False
    uncertain: bool = False
    note: str = ''

    @property
    def chinese(self):
        if self.target is None:
            return self.note or '原帖未明确时区或具体时刻'
        label = self.target.astimezone(BJ).strftime('%m-%d %H:%M')
        return ('最晚' + label + '前' if self.deadline else '预计' + label) + ('（暂定）' if self.uncertain else '')


def post_datetime(raw):
    if not isinstance(raw, str):
        return None
    try:
        if re.search(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}', raw):
            dt = datetime.fromisoformat(raw.replace('Z','+00:00'))
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        dt = parsedate_to_datetime(raw)
        return dt if dt.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def _zone(label):
    label = label.upper()
    if label == 'PT':
        return ZoneInfo('America/Los_Angeles')
    if label == 'PST':
        return timezone(timedelta(hours=-8))
    if label == 'PDT':
        return timezone(timedelta(hours=-7))
    match = re.fullmatch(r'(?:UTC|GMT)(?:([+-])(\d{1,2})(?::?(\d{2}))?)?', label)
    if not match:
        return None
    if not match[1]:
        return timezone.utc
    h,m = int(match[2]),int(match[3] or 0)
    if h > 23 or m > 59:
        return None
    return timezone((1 if match[1]=='+' else -1)*timedelta(hours=h, minutes=m))


def parse_update_time(text, created_at):
    text = re.sub(r'https?://\S+|www\.\S+', '', text, flags=re.I).replace('’',"'")
    if not EVIDENCE.search(text):
        return None
    uncertain = bool(re.search(r'\b(?:maybe|might|could|hopefully|tentative|hope|if)\b',text,re.I))
    if re.search(r'\b(?:no ETA|no date|not sure|don.t know|can.t say|not today|not tomorrow|won.t|will not|not in)\b',text,re.I):
        return UpdateTime(None,uncertain=True,note='原帖未给出确定时间，或否定了该时间')
    dt = post_datetime(created_at)
    if dt is None:
        return UpdateTime(None,uncertain=uncertain,note='缺少回复精确发布时间，无法可靠换算')
    rel = re.search(r'\b(in|within)\s+(?:(?:the\s+)?next\s+)?(?:(?:about|around)\s+|~\s*)?('+NUM+r')\s+(minutes?|hours?|days?)\b',text,re.I)
    if rel:
        if re.search(r'\b(?:took|spent|ago|used to)\b',text,re.I):
            return None
        number = WORDS.get(rel[2].lower())
        number = float(rel[2]) if number is None else number
        if number > 366 or number < 0:
            return UpdateTime(None,note='原帖相对时间超出可靠换算范围')
        delta = timedelta(**{('minutes' if rel[3].lower().startswith('minute') else 'hours' if rel[3].lower().startswith('hour') else 'days'):number})
        return UpdateTime(dt+delta,deadline=rel[1].lower()=='within',uncertain=uncertain,note='以回复发布时间加上原文时长换算')
    zmatch = re.search(r'\b('+ZONE+r')\b',text,re.I)
    eod = bool(re.search(r'\b(?:EOD|end of (?:the )?day)\b',text,re.I))
    clock_text = text[:zmatch.start()]+' '+text[zmatch.end():] if zmatch else text
    clock = re.search(r'\b(?:(?:at|by|before|around)\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b',clock_text,re.I)
    if not clock:
        clock = re.search(r'\b(?:(?:at|by|before|around)\s+)?(\d{1,2}):(\d{2})(?!\d)()',clock_text,re.I)
    if re.search(r'\b(?:not by|not before|after)\b',text,re.I):
        return UpdateTime(None,uncertain=uncertain,note='原帖给出否定或较晚范围，未明确具体执行时刻')
    if re.search(r'\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b',text,re.I) and not re.search(r'20\d{2}-\d{2}-\d{2}',text):
        return UpdateTime(None,uncertain=uncertain,note='原帖给出星期但具体日期未明确')
    if len(re.findall(r'\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b|\b\d{1,2}:\d{2}\b',clock_text,re.I)) > 1:
        return UpdateTime(None,uncertain=uncertain,note='原帖给出多个时刻或范围，需核对具体安排')
    if not (eod or clock):
        return UpdateTime(None,uncertain=uncertain,note='原帖只给出模糊时间，未公布精确时刻')
    if not zmatch:
        return UpdateTime(None,uncertain=uncertain,note='原帖没有明确时区，不猜测北京时间')
    tz = _zone(zmatch[1])
    if tz is None:
        return UpdateTime(None,note='原帖时区无法可靠解析')
    local = dt.astimezone(tz)
    day = local.date() + timedelta(days=1 if re.search(r'\btomorrow\b',text,re.I) else 0)
    iso = re.search(r'\b(20\d\d)-(\d{2})-(\d{2})\b',text)
    month = re.search(r'\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})(?:,?\s+(20\d\d))?\b',text,re.I)
    try:
        if iso:
            day = datetime(int(iso[1]),int(iso[2]),int(iso[3])).date()
        elif month:
            mn = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'].index(month[1][:3].lower())+1
            day = datetime(int(month[3] or local.year),mn,int(month[2])).date()
        if eod:
            # Day-end is an exclusive next-midnight boundary, not a claimed exact execution time.
            target = datetime.combine(day+timedelta(days=1),datetime.min.time(),tzinfo=tz)
        else:
            h,m = int(clock[1]),int(clock[2] or 0)
            ap = clock[3].lower()
            if (ap and not 1 <= h <= 12) or (not ap and h>23) or m>59:
                return UpdateTime(None,note='原帖时刻无效，无法可靠换算')
            if ap:
                h=h%12+(12 if ap=='pm' else 0)
            target=datetime.combine(day,datetime.min.time(),tzinfo=tz).replace(hour=h,minute=m)
            # Do not guess a second date when no explicit future date is given.
            if target < dt and not (iso or month or re.search(r'\btomorrow\b',text,re.I)):
                return UpdateTime(None,note='原帖时刻已早于发布时间，日期未明确')
            # A nonexistent DST clock must not silently become a real deadline.
            if target.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) != target.replace(tzinfo=None):
                return UpdateTime(None,note='原帖时刻落在夏令时切换空档，需确认')
            if target.replace(fold=0).utcoffset()!=target.replace(fold=1).utcoffset():
                return UpdateTime(None,note='原帖时刻在夏令时切换时重复，需确认')
        note = '按原文PST固定偏移换算' if zmatch[1].upper()=='PST' else '按原文时区换算'
        return UpdateTime(target,deadline=eod or bool(re.search(r'\b(?:by|before|until)\b',text,re.I)),uncertain=uncertain,note=note)
    except (ValueError,OverflowError):
        return UpdateTime(None,note='原帖日期或时刻无法可靠解析')
