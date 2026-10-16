import json
import unittest
from unittest.mock import patch

from test_watcher import post
from watcher.config import Config
from watcher.daily import classify_daily
from watcher.detect import score_text, should_alert
from watcher.events import format_qq
from watcher.notify import send_alert


class DailySeries(unittest.TestCase):
    def test_numbered_updates_without_product_or_future_words(self):
        cases = [
            ('Day 11/\nWe have landed changes and more compute to decrease "Selected model is at capacity".', 'Day11满载优化'),
            ("Day 9/\nWe've rolled out optimizations to how we store state on disk.", 'Day9磁盘优化'),
            ('Day 7/\nWe have increased default context length to 500k.', 'Day7上下文更新'),
            ('Day 2.4/\nDecisions API is live.', 'Day2.4决策接口更新'),
            ('Roundup of Day 2/\nApprove for me (auto-review) is now included.', 'Day2自动审批更新'),
        ]
        for text, label in cases:
            with self.subTest(text=text):
                self.assertIsNotNone(classify_daily(text))
                self.assertTrue(should_alert(score_text(text), 3))
                title, body = format_qq(post(text + '\nhttps://t.co/abc'))
                self.assertIn(label, title)
                self.assertLessEqual(len(title), 40)
                self.assertEqual(len(body.splitlines()), 4)
                self.assertNotRegex(title + body, r'http|t\.co|www\.')

    def test_ambiguous_reset_is_not_completed(self):
        for text in ['Day 8/ Reset', 'The reports of my reset button being lost are exaggerated\nDay 10/ Reset']:
            title, body = format_qq(post(text))
            self.assertIn('疑似重置', title)
            self.assertNotIn('已完成', title + body)
        title, body = format_qq(post('Day 6/\nWe have reset all Codex usage limits.'))
        self.assertIn('Day6已完成重置', title)
        title, body = format_qq(post('Day 3/\nWe will give a banked reset tomorrow.'))
        self.assertIn('Day3重置预告', title)
        self.assertIn('重置券', body)

    def test_not_arbitrary_day_or_repost(self):
        for text in ['Great day 11 for Codex', 'RT @other: Day 11/ shipped',
                     'Day 50/ picnic', 'Day 0/ hello', 'https://example.org/Day11/reset',
                     '> Day 11/ quoted text']:
            self.assertIsNone(classify_daily(text), text)

    def test_future_daily_is_not_completed(self):
        title, body = format_qq(post('Day 12/\nWe will ship a new feature tomorrow.'))
        self.assertIn('每日更新预告', title)
        self.assertIn('尚未确认已经交付', body)

    def test_qq_payload(self):
        cfg = Config(pushplus_token='fake', pushplus_qq_option='fake')
        with patch('watcher.notify.http_post', return_value=(200,'{"code":200}')) as send:
            send_alert(cfg, post('Day 11/\nWe have improved capacity.'), 3, 'daily-series')
            send.assert_called_once()
            data = json.loads(send.call_args.args[1])
            self.assertIn('Day11', data['title'])
            self.assertNotIn('http', data['content'])

    def test_own_daily_commentary_with_quote_and_plain_retweet(self):
        cfg = Config(pushplus_token='fake', pushplus_qq_option='fake')
        with patch('watcher.notify.http_post', return_value=(200,'{"code":200}')) as send:
            send_alert(cfg, post('Day 2.4/\nDecisions API is live.', is_quote=True), 3, 'daily-series')
            send.assert_called_once()
        with patch('watcher.notify.http_post') as send:
            send_alert(cfg, post('Day 2.4/\nDecisions API is live.', is_repost=True), 3, 'daily-series')
            send.assert_not_called()
            send_alert(cfg, post('Codex will launch tomorrow.', is_quote=True), 3, 'plan')
            send.assert_not_called()
