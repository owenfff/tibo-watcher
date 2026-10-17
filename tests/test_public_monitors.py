import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from watcher.config import Config
from watcher.public_monitors import discover_ids, tracker_posts, verified_post
from watcher.run import check_once
from watcher.state import StateStore


class PublicMonitors(unittest.TestCase):
    def test_only_target_author_links(self):
        page = '<a href="/thsottiaux/2111492673890824348">x</a><a href="/other/status/2111492673890824348">q</a>'
        self.assertEqual(discover_ids(page), ['2111492673890824348'])
        self.assertEqual(discover_ids('<a href="/thsottiaux/status/2111492673890824348">x</a>'), ['2111492673890824348'])

    def test_verify_author_and_id(self):
        with patch('watcher.public_monitors.get_json', return_value={'tweet': {
            'id': '2111492673890824348', 'author': {'screen_name': 'other'}, 'text': 'Day 13/ Reset'}}):
            with self.assertRaises(ValueError):
                verified_post('2111492673890824348')

    def test_tracker_does_not_merge_quote_or_followup(self):
        data = {'handle': 'thsottiaux', 'entries': [{'id': '2111492673890824348',
            'text': 'Day 13/ Le limit reset', 'quote': {'text': 'Reset is complete'},
            'followups': [{'id': '2111492673890824349', 'text': 'We will reset usage tonight.'}]}]}
        a, b = tracker_posts(data)
        self.assertNotIn('complete', a.body)
        self.assertNotEqual(a.key, b.key)

    def test_initial_archive_then_new_update_and_shared_dedupe(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(state_file=Path(d) / 'state.json', qq_auto_translate=False)
            store = StateStore(cfg.state_file)
            store.mark_seen('existing')
            store.save()
            archive = tracker_posts({'handle': 'thsottiaux', 'entries': [
                {'id': '2111244596131111253', 'text': 'Day 12/ context update'}]})[0]
            new = replace(archive, key='dayclaw:2111492673890824348', body='Day 13/ Le limit reset',
                          created_at='Sat Oct 17 16:20:57 +0000 2026', feed='recovery')
            with patch('watcher.run.sources.collect', return_value=[archive, new]), patch(
                    'watcher.run.notify.send_alert', return_value=[(True, 'mock accepted')]) as send:
                self.assertEqual(check_once(cfg), 1)
                self.assertEqual(send.call_args.args[1].key, new.key)
                self.assertEqual(check_once(cfg), 0)
                self.assertEqual(send.call_count, 1)
            # Another source reporting the same original ID cannot replay it.
            with patch('watcher.run.sources.collect', return_value=[replace(new, feed='')]), patch(
                    'watcher.run.notify.send_alert') as send:
                check_once(cfg)
                send.assert_not_called()

    def test_rejection_logs_only_numeric_code(self):
        from watcher.notify import _send_qq
        cfg = Config(pushplus_token='private-token', pushplus_qq_option='private-option')
        with patch('watcher.notify.http_post', return_value=(200, '{"code":600,"msg":"private-token private-option"}')):
            ok, note = _send_qq(cfg, 'title', 'body')
            self.assertFalse(ok)
            self.assertIn('code 600', note)
            self.assertNotIn('private', note)

    def test_existing_tracker_can_notify_without_false_baseline_log(self):
        from contextlib import redirect_stdout
        from io import StringIO
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(state_file=Path(d) / 'state.json')
            store = StateStore(cfg.state_file)
            store.mark_seen('source:codexy:v1')
            store.save()
            item = tracker_posts({'handle':'thsottiaux','entries':[{'id':'2111492673890824348','text':'Day 13/ Le limit reset'}]})[0]
            output = StringIO()
            with patch('watcher.run.sources.collect', return_value=[item]), patch('watcher.run.notify.send_alert', return_value=[(True,'mock')]), redirect_stdout(output):
                self.assertEqual(check_once(cfg), 1)
            self.assertNotIn('baseline recorded', output.getvalue())
