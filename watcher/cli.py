from __future__ import annotations

import argparse
import json
from pathlib import Path

from .model import Post

from . import __version__, notify
from .config import load_config
from .run import check_once, run_loop


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tibo-watcher",
        description="Push alerts when Tibo (@thsottiaux, Codex lead) or the "
                    "Codex changelog hints at usage-limit resets, plus public product plans on X.",
    )
    parser.add_argument("--version", action="version",
                        version=f"tibo-watcher {__version__}")
    parser.add_argument("--loop", action="store_true",
                        help="keep running forever, checking every "
                             "WATCH_INTERVAL_MIN minutes (default 10)")
    parser.add_argument("--prime", action="store_true",
                        help="(re)record the current posts as baseline, "
                             "pushing nothing; useful after a long pause")
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch and score but never deliver, never save state")
    parser.add_argument("--sample-post", metavar="FILE",
                        help="offline JSON fake post; requires --dry-run, never sends or saves")
    parser.add_argument("--test-notify", action="store_true",
                        help="send a test message to every configured channel "
                             "and exit")
    parser.add_argument("--alert-all", action="store_true",
                        help="bypass score threshold for monitored events only")
    parser.add_argument("--verbose", action="store_true",
                        help="print every new item and its score")
    parser.add_argument("--handle",
                        help="override the watched X handle (default thsottiaux)")
    parser.add_argument("--interval", type=int, metavar="MINUTES",
                        help="override the loop interval in minutes")
    parser.add_argument("--state", type=Path, metavar="FILE",
                        help="override the state file path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.dry_run and (args.test_notify or args.loop or args.prime):
        parser.error("--dry-run cannot be combined with --test-notify, --loop or --prime")
    if args.sample_post and not args.dry_run:
        parser.error("--sample-post requires --dry-run")
    cfg = load_config(
        handle=args.handle,
        interval_min=args.interval,
        alert_all=args.alert_all or None,
        state_file=args.state,
        verbose=args.verbose or None,
    )

    if args.test_notify:
        results = notify.send_test(cfg)
        if not results:
            print("no channels configured; set NTFY_TOPIC (easiest), "
                  "TELEGRAM_*, or SMTP_* in .env first")
            return 1
        ok = True
        for delivered, note in results:
            print(("OK   " if delivered else "FAIL ") + note)
            ok = ok and delivered
        return 0 if ok else 2

    if args.loop:
        run_loop(cfg)
        return 0

    if args.sample_post:
        try:
            data = json.loads(Path(args.sample_post).read_text(encoding="utf-8"))
            text = data["body"]
            if not isinstance(text, str) or not text:
                raise ValueError("body must be a nonempty string")
            post = Post(key="sample:offline", source="x", title=text, body=text,
                        url="", created_at=data.get("created_at", ""),
                        is_repost=bool(data.get("is_repost", False)))
        except (OSError, ValueError, KeyError, TypeError) as error:
            parser.error(f"invalid sample: {error}")
        check_once(cfg, dry_run=True, sample_posts=[post])
        return 0

    check_once(cfg, prime=args.prime, dry_run=args.dry_run)
    return 0
