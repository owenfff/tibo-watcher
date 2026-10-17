"""Free public monitor discovery; only verified Tibo text becomes an alert."""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from .fetch import get_json, http_get
from .model import Post
from .state import StateStore

TRACKER_URL = 'https://codexy.fyi/data/days.json'
MIRRORS = ('https://twiscan.com/en/x/thsottiaux', 'https://site.twstalker.com/thsottiaux')


def tracker_posts(data):
    if not isinstance(data, dict) or data.get('handle', '').lower() != 'thsottiaux':
        raise ValueError('unexpected tracker author/schema')
    posts = []
    for entry in data.get('entries', []):
        # Follow-ups have their own IDs, never merge their claims into a parent.
        for item in [entry, *entry.get('followups', [])]:
            tid = str(item.get('id', ''))
            text = item.get('text', '')
            if not re.fullmatch(r'\d{10,25}', tid) or not isinstance(text, str) or not text:
                continue
            if item.get('handle', 'thsottiaux').lower() != 'thsottiaux':
                continue
            posts.append(Post(key=f'dayclaw:{tid}', source='x', title=text,
                              body=html.unescape(text), url=f'https://x.com/thsottiaux/status/{tid}',
                              created_at=item.get('posted_at') or item.get('created_at') or '',
                              feed='codexy'))
    return posts


def discover_ids(page):
    # Author-specific paths only: never treat arbitrary quoted authors as Tibo.
    return list(dict.fromkeys(re.findall(
        r'/thsottiaux/(?:status/)?(\d{10,25})(?=[/?#\s\"\'<>])', html.unescape(page), re.I)))


def verified_post(tid):
    data = get_json(f'https://api.fxtwitter.com/thsottiaux/status/{tid}', timeout=12, retries=0)
    tweet = data.get('tweet') or {}
    if (str(tweet.get('id')) != tid
            or tweet.get('author', {}).get('screen_name', '').lower() != 'thsottiaux'):
        raise ValueError('post ID/author verification failed')
    text = tweet.get('text')
    if not isinstance(text, str) or not text:
        raise ValueError('missing verified text')
    return Post(key=f'dayclaw:{tid}', source='x', title=text, body=html.unescape(text),
                url=f'https://x.com/thsottiaux/status/{tid}', created_at=tweet.get('created_at', ''),
                is_reply=bool(tweet.get('replying_to') or tweet.get('replying_to_status')),
                is_repost=bool(tweet.get('retweet') or re.match(r'^RT\s+@', text)),
                is_quote=bool(tweet.get('quote')), feed='public-mirror')


def fetch_public_monitors(cfg):
    if cfg.handle.lower() != 'thsottiaux':
        return []
    posts = []
    store = StateStore(cfg.state_file)
    try:
        posts.extend(tracker_posts(get_json(TRACKER_URL, timeout=12, retries=0)))
        print(f'[source] codexy: {len(posts)} posts', flush=True)
    except Exception:
        print('[warn] codexy unavailable or invalid; retaining other sources', flush=True)
    ids = []
    recovery = Path(__file__).resolve().parent.parent / 'recovery-posts.json'
    if recovery.exists():
        ids.extend(str(i) for i in json.loads(recovery.read_text()))
    recovery_ids = set(ids)
    for url in MIRRORS:
        try:
            found = discover_ids(http_get(url, timeout=12, retries=0))
            print(f'[source] {url.split("/")[2]}: {len(found)} candidate IDs', flush=True)
            ids.extend(found)
        except Exception:
            print(f'[warn] {url.split("/")[2]} unavailable; retaining other sources', flush=True)
    # Bound public API requests. Seen posts never need another lookup.
    pending = [i for i in dict.fromkeys(ids) if re.fullmatch(r'\d{10,25}', i)
               and not store.is_seen(f'dayclaw:{i}')]
    for tid in pending[:12]:
        try:
            post = verified_post(tid)
            if tid in recovery_ids:
                post.feed = 'recovery'
            posts.append(post)
        except Exception:
            print(f'[warn] cannot verify public post {tid}; will check next cycle', flush=True)
    return posts


def old_mirror_post(post):
    """Avoid flooding the group with archived mirror posts at first discovery."""
    if post.feed != 'public-mirror':
        return False
    try:
        dt = parsedate_to_datetime(post.created_at)
        return dt.tzinfo is None or (datetime.now(timezone.utc) - dt).total_seconds() > 86400
    except (ValueError, TypeError):
        return True
