from __future__ import annotations

import time
from datetime import datetime

from . import notify, sources
from .config import Config
from .events import BEIJING, classify_reset, format_qq
from .daily import classify_daily
from .plans import classify_plan
from .detect import score_text, should_alert
from .state import StateStore

MAX_ALERTS_PER_CYCLE = 5


def _stamp() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M 北京时间")


def log(message: str) -> None:
    print(f"[{_stamp()}] {message}", flush=True)


def check_once(cfg: Config, *, prime: bool = False, dry_run: bool = False, sample_posts: list | None = None) -> int:
    if sample_posts is not None and not dry_run:
        raise ValueError("sample posts require dry-run")
    posts = sample_posts if sample_posts is not None else sources.collect(cfg)
    if not posts:
        log("no posts fetched from any source; keeping previous state")
        return 0

    store = StateStore(cfg.state_file)
    baseline = (store.fresh_file or prime) and sample_posts is None
    findings = []

    for post in posts:
        if store.is_seen(post.key):
            continue
        score = score_text(post.body)
        if cfg.verbose:
            log(f"new {post.source} item, score {score.total} ({score.hits}): "
                f"{post.title[:70]}")
        store.mark_seen(post.key)
        if not cfg.include_replies and post.is_reply:
            continue
        event = classify_reset(post.body) or ((classify_daily(post.body) or classify_plan(post.body)) if post.source == "x" else None)
        if (post.is_repost or event is None
                or (post.is_quote and not (post.source == "x" and classify_daily(post.body)))):
            continue
        if cfg.alert_all or should_alert(score, cfg.score_threshold):
            findings.append((post, score))

    if baseline:
        findings = []
        log(f"baseline recorded: {store.tracked_count()} items tracked, "
            "no alerts sent (first run / prime)")

    pushed = 0
    if len(findings) > MAX_ALERTS_PER_CYCLE:
        log(f"{len(findings)} findings, capping at {MAX_ALERTS_PER_CYCLE} "
            "pushes this cycle")
    for post, score in findings[:MAX_ALERTS_PER_CYCLE]:
        if dry_run:
            if post.source == "x":
                title, body = format_qq(post)
                print(f"DRY-RUN QQ 预览（不发送）\n{title}\n{body}")
            else:
                log(f"DRY-RUN changelog match: score {score.total}")
            continue
        # Persist locally before network delivery; never retry a seen post.
        store.save()
        results = notify.send_alert(cfg, post, score.total, score.hits)
        for ok, note in results:
            if not ok:
                log(f"DELIVERY FAILED {note}")
        if not results:
            log(f"finding scored {score.total} but no notification channel "
                "is configured (set NTFY_TOPIC etc.)")
        pushed += 1

    if not dry_run:
        store.save()
    log(f"cycle done: {len(posts)} fetched, {len(findings)} matched, "
        f"{pushed} pushed{' (dry-run)' if dry_run else ''}")
    return pushed


def run_loop(cfg: Config) -> None:
    interval = cfg.interval_min * 60
    channels = ", ".join(cfg.active_channels()) or "NONE (console only!)"
    log(f"loop started: every {cfg.interval_min} min, watching "
        f"@{cfg.handle}, channels: {channels}")
    while True:
        try:
            check_once(cfg)
        except KeyboardInterrupt:
            log("interrupted; bye")
            return
        except Exception as error:
            log(f"cycle crashed but loop continues: {error}")
        time.sleep(interval)
