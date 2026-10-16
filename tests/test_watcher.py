import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from watcher.cli import main
from watcher.config import Config, load_config
from watcher.detect import score_text
from watcher.events import classify_reset, format_qq
from watcher.model import Post
from watcher.notify import send_alert
from watcher.run import check_once
from watcher.sources import fetch_x_posts
from watcher.state import StateStore


def post(body="We have reset all Codex usage limits.", **kw):
    return Post(key=kw.pop("key", "dayclaw:123"), source="x", title=body,
                body=body, url="https://t.co/secret", created_at="2026-10-13T05:06:00Z", **kw)


class Events(unittest.TestCase):
    def test_states(self):
        cases = [
            ("We have reset all Codex usage limits.", "已完成"),
            ("We've just reset Codex limits.", "已完成"),
            ("Codex usage limits have been reset.", "已完成"),
            ("We will reset all Codex usage limits tonight.", "预告"),
            ("We will credit every Codex and ChatGPT user today.", "预告"),
            ("We added credits to all Codex users.", "已完成"),
            ("Your banked reset is now available.", "重置券"),
            ("We have issued a banked reset.", "重置券"),
            ("We have granted a banked reset.", "重置券"),
            ("We will give a banked reset today. Lands end of day.", "预告"),
            ("Codex limits might have reset.", "疑似重置"),
            ("Codex limits have not reset.", "疑似重置"),
            ("Codex limits should have reset.", "疑似重置"),
            ("Banked reset", "疑似重置"),
            ("We will give one banked reset for every day you don't have access to Astra on your paid ChatGPT plan, starting today.", "疑似重置"),
        ]
        for text, status in cases:
            with self.subTest(text=text):
                self.assertEqual(classify_reset(text).status, status)

    def test_chatter(self):
        for text in ["Codex weekly limits are annoying.", "We granted a wish.",
                     "Codex has 20 million users", "Codex credit usage is high",
                     "Codex credits are expensive and usage is high", "We will not reset Codex limits.",
                     "How do I reset my Codex limits?", "Reset your database credits",
                     "Codex https://example.org/limits-reset", "RT @other: hello"]:
            with self.subTest(text=text):
                self.assertIsNone(classify_reset(text))

    def test_qq_format_and_time(self):
        title, body = format_qq(post())
        self.assertEqual(title, "Codex已完成重置 北京时间10-13 13:06")
        self.assertEqual(len(body.splitlines()), 4)
        self.assertTrue(body.endswith("来源：@thsottiaux"))
        self.assertNotIn("http", title + body)
        for text in ["We have reset Codex and ChatGPT usage limits. https://t.co/abc",
                     "We will give ChatGPT Work a banked reset tomorrow.",
                     "Your Codex banked reset is now available."]:
            title, body = format_qq(post(text))
            self.assertLessEqual(len(title), 40)
            self.assertNotRegex(title + body, r"https?|t\.co|www\.")
        item = post(); item.created_at = "2026-10-13T05:06:00"
        self.assertIn("10-13 13:06", format_qq(item)[0])
        item.created_at = "2026-10-12T22:06:00-07:00"
        self.assertIn("10-13 13:06", format_qq(item)[0])
        item.created_at = "2026-10-13"
        self.assertIn("未提供精确时间", format_qq(item)[0])


class Delivery(unittest.TestCase):
    def test_config_env(self):
        with patch.dict(os.environ, {"PUSHPLUS_TOKEN":" test-token ", "PUSHPLUS_QQ_OPTION":" group-config "}):
            cfg = load_config()
            self.assertEqual(cfg.pushplus_token, "test-token")
            self.assertEqual(cfg.pushplus_qq_option, "group-config")
            self.assertIn("qq", cfg.active_channels())

    def test_payload_and_business_failure(self):
        cfg = Config(qq_auto_translate=False, pushplus_token="fake", pushplus_qq_option="group-code")
        with patch("watcher.notify.http_post", return_value=(200, '{"code":200}')) as send:
            self.assertTrue(send_alert(cfg, post(), 5, "reset")[0][0])
            args, kwargs = send.call_args
            self.assertEqual(args[0], "https://www.pushplus.plus/send")
            data = json.loads(args[1])
            self.assertEqual(set(data), {"token", "title", "content", "channel", "option", "template"})
            self.assertEqual(data["channel"], "qq")
            self.assertEqual(data["template"], "txt")
            self.assertEqual(data["option"], "group-code")
        for response in ['{"code":500,"msg":"fake secret"}', 'broken', '[]']:
            with patch("watcher.notify.http_post", return_value=(200, response)):
                result = send_alert(cfg, post(), 5, "reset")
                self.assertFalse(result[0][0]); self.assertNotIn("fake", str(result))

    def test_absent_credentials_and_failure_isolation(self):
        for cfg in [Config(qq_auto_translate=False, ), Config(qq_auto_translate=False, pushplus_token="fake"), Config(qq_auto_translate=False, pushplus_qq_option="code")]:
            with patch("watcher.notify.http_post") as send:
                self.assertEqual(send_alert(cfg, post(), 5, "reset"), [])
                send.assert_not_called()
        cfg = Config(qq_auto_translate=False, ntfy_topic="fake", pushplus_token="fake", pushplus_qq_option="code")
        with patch("watcher.notify._send_ntfy", side_effect=OSError()), patch(
                "watcher.notify._send_qq", return_value=(True, "accepted")) as send:
            self.assertEqual(len(send_alert(cfg, post(), 5, "reset")), 2)
            send.assert_called_once()


class Pipeline(unittest.TestCase):
    def test_dedupe_forever_and_baseline(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.json'
            cfg = Config(qq_auto_translate=False, state_file=path)
            with patch("watcher.run.sources.collect", return_value=[post()]), patch("watcher.run.notify.send_alert") as send:
                check_once(cfg)  # baseline
                check_once(cfg)
                send.assert_not_called()
            store = StateStore(path)
            for i in range(1600): store.mark_seen(str(i))
            store.save()
            self.assertTrue(StateStore(path).is_seen(post().key))
            self.assertEqual(StateStore(path).tracked_count(), 1601)

    def test_one_send_and_reposts_chatter(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.json'; StateStore(path).save()
            cfg = Config(qq_auto_translate=False, state_file=path, alert_all=True)
            items = [post(), post(), post(key="rt", is_repost=True), post("Codex quota is low", key="chat")]
            with patch("watcher.run.sources.collect", return_value=items), patch(
                    "watcher.run.notify.send_alert", return_value=[(True,"ok")]) as send:
                check_once(cfg); check_once(cfg)
                send.assert_called_once()

    def test_failed_delivery_is_not_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.json'; StateStore(path).save()
            cfg = Config(qq_auto_translate=False, state_file=path)
            def fail_after_claim(*args):
                self.assertTrue(StateStore(path).is_seen(post().key))
                return [(False, "qq rejected")]
            with patch("watcher.run.sources.collect", return_value=[post()]), patch(
                    "watcher.run.notify.send_alert", side_effect=fail_after_claim) as send:
                check_once(cfg); check_once(cfg)
                send.assert_called_once()

    def test_offline_dry_run_no_io(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg = Config(qq_auto_translate=False, state_file=Path(folder)/'state.json', pushplus_token="fake", pushplus_qq_option="fake")
            with patch("watcher.run.sources.collect") as fetch, patch("watcher.notify.http_post") as send:
                check_once(cfg, dry_run=True, sample_posts=[post()])
                send.assert_not_called(); fetch.assert_not_called()
                self.assertFalse(cfg.state_file.exists())
                with patch("watcher.cli.load_config", return_value=cfg):
                    main(["--dry-run", "--sample-post", "examples/reset-post.json"])
                send.assert_not_called(); fetch.assert_not_called()
                self.assertFalse(cfg.state_file.exists())
        with self.assertRaises(SystemExit): main(["--dry-run", "--test-notify"])
        with self.assertRaises(SystemExit): main(["--sample-post", "examples/reset-post.json"])

    def test_repost_metadata(self):
        for metadata in [{"is_retweet":True}, {"author_user_name":"other"}]:
            with patch("watcher.sources.get_json", return_value={"items":[{
                    "external_id":"123", "content":post().body, "metadata":metadata}]}):
                self.assertTrue(fetch_x_posts(Config(qq_auto_translate=False, ))[0].is_repost)


if __name__ == '__main__': unittest.main()
