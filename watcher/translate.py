"""Best-effort English-to-Chinese translation of public posts, without API keys."""
from __future__ import annotations

import html
import re
from urllib.parse import urlencode

from .daily import DAY_MARKER
from .fetch import get_json

MAX_SOURCE_CHARS = 1000
MAX_TRANSLATION_CHARS = 1100
MAX_CHUNK_BYTES = 450


def clean_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r'<[^>]*>', ' ', text)
    text = re.sub(r'(?i)(?:https?://|www\.)\S+', ' ', text)
    text = re.sub(r'(?i)\b(?:[a-z0-9-]+\.)+[a-z]{2,63}(?:/\S*)?', ' ', text)
    text = re.sub(r'(?i)http\S*', ' ', text)
    text = re.sub(r'[*_`#>\[\]]', '', text)
    text = re.sub(r'(?:点击|点此|请点击)?查看详情|(?i:view details|read more)', '', text)
    return ' '.join(text.split())


def _chunks(text: str) -> list[str]:
    result, chunk, size = [], '', 0
    for char in text:
        length = len(char.encode('utf-8'))
        if size + length > MAX_CHUNK_BYTES:
            # Prefer a word boundary so an English word is not split in two.
            split = chunk.rfind(' ')
            if split > len(chunk) // 2:
                result.append(chunk[:split])
                chunk = chunk[split + 1:]
                size = len(chunk.encode('utf-8'))
            else:
                result.append(chunk)
                chunk, size = '', 0
        chunk += char
        size += length
    if chunk:
        result.append(chunk)
    return result


def _neutralize_clock(text: str) -> str:
    # Keep the authoritative Beijing timestamp in the existing second line.
    # Do not reproduce a machine-converted or timezone-ambiguous event clock.
    text = re.sub(r'(?i)\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\s*(?:PT|PST|PDT|ET|EST|EDT|UTC|GMT)?\b',
                  '（执行时刻以北京时间说明为准）', text)
    text = re.sub(r'(?i)\b\d{1,2}:\d{2}\s*(?:PT|PST|PDT|ET|EST|EDT|UTC|GMT)?\b',
                  '（执行时刻以北京时间说明为准）', text)
    text = re.sub(r'(?:上午|下午|晚上|早上|凌晨)?\d{1,2}[点时](?:\d{1,2}分)?',
                  '（执行时刻以北京时间说明为准）', text)
    text = re.sub(r'(?i)\b(?:today|tomorrow|tonight|yesterday)\b|今天|明天|今晚|昨天|昨晚',
                  '原帖所指日期', text)
    return text


def translate_public_post(text: str, *, time_context: bool = False) -> str | None:
    text = clean_text(DAY_MARKER.sub('', text))
    text = re.sub(r'\blanding\b', 'rolling out', text, flags=re.I)
    text = re.sub(r'\blanded\b', 'rolled out', text, flags=re.I)
    original_han = len(re.findall(r'[\u3400-\u9fff]', text))
    original_latin = len(re.findall(r'[a-zA-Z]', text))
    already_chinese = original_han > original_latin
    if time_context:
        # Keep converted times authoritative in the fixed second line. Translate
        # only the author's own reply, never merge the parent's claims into it.
        text = re.sub(r'(?i)\b(?:by\s+)?(?:EOD|end of (?:the )?day)\s*(?:PST|PDT|PT|UTC|GMT)?\b',
                      '上述北京时间截止前', text)
        text = re.sub(r'(?i)\b(?:in|within)\s+(?:(?:the\s+)?next\s+)?(?:about\s+)?(?:\d+(?:\.\d+)?|one|two|three|four|five|six|a|an)\s+(?:hours?|minutes?|days?)\b',
                      '上方换算的北京时间窗口', text)
    else:
        text = re.sub(r'(?i)\b(?:EOD|end of (?:the )?day)\s*(?:PST|PDT|PT)?\b',
                      '原帖所述日终（具体北京时间未确认）', text)
    text = _neutralize_clock(clean_text(text))[:MAX_SOURCE_CHARS]
    if not text:
        return None
    # Already-Chinese posts do not need an external request.
    han = len(re.findall(r'[\u3400-\u9fff]', text))
    latin = len(re.findall(r'[a-zA-Z]', text))
    if already_chinese:
        return text[:MAX_TRANSLATION_CHARS]
    try:
        translated = []
        chunks = _chunks(text)
        if len(chunks) > 4:
            return None
        for chunk in chunks:
            query = urlencode({'q': chunk, 'langpair': 'en|zh-CN'})
            data = get_json('https://api.mymemory.translated.net/get?' + query,
                            timeout=12, retries=0)
            if not isinstance(data, dict) or str(data.get('responseStatus')) != '200' or data.get('quotaFinished'):
                return None
            result = data.get('responseData')
            part = result.get('translatedText') if isinstance(result, dict) else None
            if not isinstance(part, str) or not part.strip():
                return None
            translated.append(part)
        output = _neutralize_clock(clean_text(' '.join(translated)))
        if not re.search(r'[\u3400-\u9fff]', output):
            return None
        return output[:MAX_TRANSLATION_CHARS] + ('…' if len(output) > MAX_TRANSLATION_CHARS else '')
    except (OSError, RuntimeError, ValueError, TypeError):
        # Never log provider URLs/responses. A service outage must not stop QQ.
        return None


def add_translation(body: str, text: str) -> str:
    timed = bool(re.search(r'北京时间：(最晚|预计)\d{2}-\d{2} \d{2}:\d{2}',body))
    translated = translate_public_post(text, time_context=timed)
    if not translated:
        return body
    lines = body.splitlines()
    if len(lines) != 4:
        return body
    lines[2] = '原文译文：' + translated
    result = '\n'.join(lines)
    assert len(result) < 1900 and not re.search(r'http|www\.', result, re.I)
    return result
