import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from test_watcher import post
from watcher.config import Config
from watcher.events import format_qq
from watcher.followups import classify_time_reply
from watcher.public_monitors import tracker_posts, resolve_reply_context
from watcher.run import check_once
from watcher.state import StateStore
from watcher.timing import parse_update_time
from watcher.translate import add_translation

CREATED='Sat Oct 17 16:21:13 +0000 2026'
ROOT='2111492673890824348'
REPLY='2111492738025959922'


def reply(text='Landing sometime today by EOD PST', **kw):
    item=post(text,key='dayclaw:'+REPLY,is_reply=True,parent_id=ROOT,
              context_id=ROOT,context_body='Day 13/ Le limit reset', **kw)
    item.created_at=CREATED
    return item


class Timing(unittest.TestCase):
    def test_actual_day13_reply_pst_deadline_and_not_completed(self):
        timing=parse_update_time(reply().body,CREATED)
        self.assertEqual(timing.chinese,'最晚10-18 16:00前')
        self.assertIn('原文PST',timing.note)
        title,body=format_qq(reply())
        self.assertIn('Day13重置预告',title)
        self.assertIn('10-18 16:00前',title)
        self.assertIn('回复发布于10-18 00:21',body)
        self.assertNotIn('已完成',title+body)
        self.assertEqual(len(body.splitlines()),4)
        self.assertLessEqual(len(title),40)
        self.assertNotRegex(title+body,r'http|www\.')

    def test_pt_tracks_dst_but_literal_pst_does_not(self):
        self.assertEqual(parse_update_time('Landing by EOD PT',CREATED).chinese,'最晚10-18 15:00前')
        self.assertEqual(parse_update_time('Landing by EOD PDT',CREATED).chinese,'最晚10-18 15:00前')
        self.assertEqual(parse_update_time('Landing by EOD PST',CREATED).chinese,'最晚10-18 16:00前')
        self.assertEqual(parse_update_time('Landing by EOD PT','2026-12-17T16:21:13Z').chinese,'最晚12-18 16:00前')

    def test_relative_is_anchored_to_reply_not_collection_or_parent(self):
        stamp='Thu Oct 15 04:56:07 +0000 2026'
        self.assertEqual(parse_update_time('Landing within the next 2 hours',stamp).chinese,'最晚10-15 14:56前')
        self.assertEqual(parse_update_time('In two hours',stamp).chinese,'预计10-15 14:56')
        self.assertEqual(parse_update_time('In 30 minutes',stamp).chinese,'预计10-15 13:26')

    def test_explicit_date_clock_and_utc_offset(self):
        self.assertEqual(parse_update_time('Landing tomorrow at 8pm PT',CREATED).chinese,'预计10-19 11:00')
        self.assertEqual(parse_update_time('Landing Oct 18 at 8pm PST',CREATED).chinese,'预计10-19 12:00')
        self.assertEqual(parse_update_time('Landing 2026-10-18 at 20:00 UTC+02:00',CREATED).chinese,'预计10-19 02:00')

    def test_missing_ambiguous_and_negated_times_are_not_guessed(self):
        for text,stamp in [('By EOD',CREATED),('Tomorrow at 8pm',CREATED),('No ETA yet',CREATED),
                           ('Not in 2 hours',CREATED),('In 2 hours','2026-10-17'),
                           ('Landing UTC+08:00',CREATED)]:
            value=parse_update_time(text,stamp)
            self.assertTrue(value is None or value.target is None,(text,value))
        self.assertIsNone(parse_update_time('It took 2 hours',CREATED))
        self.assertIsNone(parse_update_time('Landing at 1:30am PT','2026-11-01T07:00:00Z').target)
        self.assertIsNone(parse_update_time('Landing at 2:30am PT','2026-03-08T08:00:00Z').target)

    def test_questions_and_unlinked_chatter_never_make_schedule(self):
        for text in ['When is the update?', 'Will it land in two hours?', 'Dinner tomorrow at 8pm PT']:
            self.assertIsNone(classify_time_reply(reply(text)))
        item=reply('In two hours');item.context_body='Thanks for the birthday wishes'
        self.assertIsNone(classify_time_reply(item))
        item=reply('In two hours');item.context_id=''
        self.assertIsNone(classify_time_reply(item))

    def test_speculation_keeps_uncertainty(self):
        title,body=format_qq(reply('Maybe in 2 hours'))
        self.assertIn('疑似',title)
        self.assertIn('暂定',body)
        self.assertNotIn('已完成',body)

    def test_tracker_parent_context_is_preserved(self):
        entries={'handle':'thsottiaux','entries':[{'id':ROOT,'text':'Day 13/ Le limit reset','followups':[
            {'id':REPLY,'text':'Landing sometime today by EOD PST','posted_at':CREATED,'replying_to_status':ROOT}]}]}
        root,child=tracker_posts(entries)
        self.assertEqual(child.context_id,ROOT)
        self.assertEqual(child.context_body,root.body)
        self.assertIsNotNone(classify_time_reply(child))

    def test_reply_to_another_users_question_walks_to_tibo_root(self):
        item=reply('In 2 hours');item.context_id='';item.context_body='';item.parent_id='2111492000000000000'
        data={'2111492000000000000': {'id':'2111492000000000000','author':{'screen_name':'someone'},'text':'When?', 'replying_to_status':ROOT},
              ROOT:{'id':ROOT,'author':{'screen_name':'thsottiaux'},'text':'Day 13/ Le limit reset'}}
        resolve_reply_context(item,{},loader=lambda key:data[key])
        self.assertEqual(item.context_id,ROOT)
        self.assertIsNotNone(classify_time_reply(item))

    def test_failed_parent_lookup_retries_without_marking_seen(self):
        item=reply('In 2 hours');item.context_id='';item.context_body=''
        with tempfile.TemporaryDirectory() as d:
            cfg=Config(state_file=Path(d)/'state.json');StateStore(cfg.state_file).save()
            with patch('watcher.public_monitors.public_tweet',side_effect=RuntimeError('unavailable')):
                resolve_reply_context(item,{})
            self.assertTrue(item.context_pending)
            with patch('watcher.run.sources.collect',return_value=[item]),patch('watcher.run.notify.send_alert') as send:
                check_once(cfg)
                send.assert_not_called()
            self.assertFalse(StateStore(cfg.state_file).is_seen(item.key))

    def test_parent_is_not_resent_and_reply_is_delivered_once(self):
        with tempfile.TemporaryDirectory() as d:
            cfg=Config(state_file=Path(d)/'state.json',qq_auto_translate=False,pushplus_token='fake',pushplus_qq_option='fake')
            store=StateStore(cfg.state_file);store.mark_seen('dayclaw:'+ROOT);store.save()
            with patch('watcher.run.sources.collect',return_value=[reply()]),patch('watcher.notify.http_post',return_value=(200,'{"code":200}')) as send:
                self.assertEqual(check_once(cfg),1)
                self.assertEqual(check_once(cfg),0)
                send.assert_called_once()
                payload=json.loads(send.call_args.args[1])
                self.assertIn('10-18 16:00前',payload['title'])
                self.assertNotIn('http',payload['content'])

    def test_translation_preserves_converted_deadline(self):
        _,body=format_qq(reply())
        response={'responseStatus':200,'responseData':{'translatedText':'将在上述北京时间截止前落地。'}}
        with patch('watcher.translate.get_json',return_value=response) as get:
            out=add_translation(body,reply().body)
            self.assertIn('10-18 16:00前',out)
            self.assertIn('原文译文：',out)
            self.assertIn('预计在上述北京时间截止前上线，具体时刻未定。',out)
            self.assertNotIn('已完成',out)
            get.assert_not_called()
            self.assertEqual(len(out.splitlines()),4)

    def test_explicit_product_plan_does_not_inherit_reset_topic(self):
        item = reply('We will launch voice for Codex tomorrow at 8pm PT.')
        self.assertIsNone(classify_time_reply(item))
        title, body = format_qq(item)
        self.assertNotIn('重置', title)
        self.assertIn('语音', title)

    def test_unsupported_ranges_and_negative_deadlines_are_not_invented(self):
        for text in ['Landing after 8pm PT', 'Landing not by EOD PST', 'Landing Friday at 8pm PT', 'Landing between 8pm and 10pm PT']:
            self.assertIsNone(parse_update_time(text, CREATED).target, text)
