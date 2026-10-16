import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from watcher.config import Config
from watcher.detect import score_text, should_alert
from watcher.events import classify_reset, format_qq
from watcher.notify import send_alert
from watcher.plans import classify_plan
from watcher.run import check_once
from watcher.state import StateStore
from test_watcher import post


class PublicPlans(unittest.TestCase):
    def test_public_plans(self):
        cases = [
            ("We will launch a new model for Codex tomorrow.", "时间安排"),
            ("Codex will be available for all Plus users tomorrow.", "上线预告"),
            ("Codex is coming to Windows tomorrow.", "时间安排"),
            ("We will launch Windows support for Codex and ChatGPT Work tomorrow.", "时间安排"),
            ("ChatGPT Work is launching next week.", "时间安排"),
            ("We plan to add voice support to Codex.", "上线预告"),
            ("We are working on memory for ChatGPT Work.", "计划"),
            ("Codex will roll out to all Plus users tomorrow.", "上线预告"),
            ("Codex launch is delayed until next week.", "时间安排"),
            ("We might ship a new model for Codex tomorrow.", "疑似计划"),
            ("Codex release date is scheduled for tomorrow.", "时间安排"),
            ("We will launch new features for Codex and ChatGPT Work in 3 hours.", "时间安排"),
        ]
        for text, status in cases:
            with self.subTest(text=text):
                self.assertEqual(classify_plan(text).status, status)
                score = score_text(text)
                self.assertTrue(should_alert(score, 3), score)
                title, body = format_qq(post(text))
                self.assertLessEqual(len(title), 40)
                self.assertEqual(len(body.splitlines()), 4)
                self.assertNotRegex(title + body, r"http|www\.|t\.co")
                self.assertNotIn("已完成", title + body)

    def test_chatter_and_unrelated(self):
        for text in ["Codex is great", "We launched Codex yesterday.",
                     "ChatGPT Work is available now.", "I plan to use Codex tomorrow.",
                     "We will launch a new website tomorrow.",
                     "We will introduce a new ChatGPT subscription plan.",
                     "When will you launch voice for Codex?", "I hope Codex will support Linux.",
                     "We won't ship the Codex update.", "RT @other: Codex will ship tomorrow.",
                     "Codex https://example.com/will-launch-tomorrow",
                     "Codex model benchmarks are impressive."]:
            with self.subTest(text=text):
                self.assertIsNone(classify_plan(text))

    def test_time_conversion_and_link_safety(self):
        title, body = format_qq(post("We will launch Codex in 3 hours. https://t.co/example"))
        self.assertIn("北京时间10-13 16:06", body)
        self.assertNotIn("http", title + body)
        _, body = format_qq(post("We will launch Codex tomorrow at 8pm PT."))
        self.assertIn("未确认精确执行时刻", body)
        self.assertNotIn("8pm", body)

    def test_reset_precedence(self):
        item = post("We will reset Codex limits and launch a new model tomorrow.")
        self.assertEqual(classify_reset(item.body).status, "预告")
        self.assertIn("重置预告", format_qq(item)[0])

    def test_qq_delivery_and_dedupe(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.json'; StateStore(path).save()
            cfg = Config(qq_auto_translate=False, state_file=path, pushplus_token='test', pushplus_qq_option='test')
            item = post("We will launch voice for Codex tomorrow.")
            with patch('watcher.run.sources.collect', return_value=[item]), patch(
                    'watcher.notify.http_post', return_value=(200, '{"code":200}')) as send:
                check_once(cfg); check_once(cfg)
                send.assert_called_once()
                data = json.loads(send.call_args.args[1])
                self.assertIn("上线预告", data['title'])
                self.assertNotIn("http", data['title'] + data['content'])
            # An already seen plan is never replayed after broadening rules.
            with patch('watcher.run.sources.collect', return_value=[item]), patch(
                    'watcher.notify.http_post') as send:
                check_once(cfg); send.assert_not_called()
