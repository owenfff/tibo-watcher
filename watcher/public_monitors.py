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
from .followups import relevant_context, timing_statement

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
            parent = parent_id(item)
            root_id = str(entry.get('id', ''))
            linked = item is not entry and parent == root_id
            posts.append(Post(key=f'dayclaw:{tid}', source='x', title=text,
                              body=html.unescape(text), url=f'https://x.com/thsottiaux/status/{tid}',
                              created_at=item.get('posted_at') or item.get('created_at') or '',
                              feed='codexy', parent_id=parent, is_reply=bool(parent),
                              is_quote=bool(item.get('quote')),
                              context_id=root_id if linked else '',
                              context_body=entry.get('text','') if linked else ''))
    return posts


def discover_ids(page):
    # Author-specific paths only: never treat arbitrary quoted authors as Tibo.
    return list(dict.fromkeys(re.findall(
        r'/thsottiaux/(?:status/)?(\d{10,25})(?=[/?#\s\"\'<>])', html.unescape(page), re.I)))


def public_tweet(tid):
    if not re.fullmatch(r"\d{10,25}",tid):
        raise ValueError("invalid public post ID")
    data = get_json(f'https://api.fxtwitter.com/thsottiaux/status/{tid}', timeout=12, retries=0)
    tweet = data.get('tweet') or {}
    if str(tweet.get('id')) != tid or not isinstance(tweet.get('text'),str):
        raise ValueError('public post ID/text verification failed')
    return tweet


def verified_post(tid):
    tweet = public_tweet(tid)
    if tweet.get('author',{}).get('screen_name','').lower() != 'thsottiaux':
        raise ValueError('post author verification failed')
    text = tweet.get('text')
    if not isinstance(text, str) or not text:
        raise ValueError('missing verified text')
    return Post(key=f'dayclaw:{tid}', source='x', title=text, body=html.unescape(text),
                url=f'https://x.com/thsottiaux/status/{tid}', created_at=tweet.get('created_at', ''),
                is_reply=bool(tweet.get('replying_to') or parent_id(tweet)),
                parent_id=parent_id(tweet),
                is_repost=bool(tweet.get('retweet') or re.match(r'^RT\s+@', text)),
                is_quote=bool(tweet.get('quote')), feed='public-mirror')


def fetch_public_monitors(cfg, known_posts=None):
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
    known = {p.key.removeprefix('dayclaw:'): p for p in [*(known_posts or []), *posts] if p.source=='x'}
    cache = {}
    budget = [8]
    for post in [*(known_posts or []), *posts]:
        if (post.is_reply and not post.is_repost and not post.context_body
                and not store.is_seen(post.key) and timing_statement(post.body)):
            resolve_reply_context(post, known, cache=cache, budget=budget)
    return posts


def parent_id(data):
    value = (data.get('replying_to_status') or data.get('in_reply_to_status_id_str')
             or data.get('in_reply_to_status_id') or data.get('reply_to_status_id'))
    if isinstance(value, dict):
        value = value.get('id')
    value = str(value or '')
    return value if re.fullmatch(r'\d{10,25}', value) else ''


def resolve_reply_context(post, known, *, cache=None, budget=None, loader=None):
    cache = {} if cache is None else cache
    budget = [8] if budget is None else budget
    loader = public_tweet if loader is None else loader
    current = post.parent_id
    if not current:
        post.context_pending = True
        return
    visited = {post.key.removeprefix('dayclaw:')}
    for _ in range(3):
        if not current or current in visited:
            return
        visited.add(current)
        parent = known.get(current)
        if parent:
            if not parent.is_repost and relevant_context(parent.body):
                post.context_id, post.context_body = current, parent.body
                return
            current = parent.parent_id
            continue
        try:
            if current not in cache:
                if budget[0] <= 0:
                    post.context_pending = True
                    return
                budget[0] -= 1
                cache[current] = loader(current)
            data = cache[current]
            if str(data.get('id')) != current:
                raise ValueError('ancestor ID mismatch')
            author = data.get('author',{}).get('screen_name','').lower()
            if (author == 'thsottiaux' and not data.get('retweet')
                    and not re.match(r'^(?:RT|QT)\s+@',data.get('text',''),re.I)
                    and relevant_context(data.get('text',''))):
                post.context_id, post.context_body = current, data['text']
                return
            quote = data.get('quote') or {}
            if (quote.get('author',{}).get('screen_name','').lower() == 'thsottiaux'
                    and relevant_context(quote.get('text',''))):
                post.context_id, post.context_body = str(quote['id']), quote['text']
                return
            current = parent_id(data)
        except Exception:
            post.context_pending = True
            return


def old_mirror_post(post):
    """Avoid flooding the group with archived mirror posts at first discovery."""
    if post.feed != 'public-mirror':
        return False
    try:
        dt = parsedate_to_datetime(post.created_at)
        return dt.tzinfo is None or (datetime.now(timezone.utc) - dt).total_seconds() > 86400
    except (ValueError, TypeError):
        return True
