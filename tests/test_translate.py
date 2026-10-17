import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from test_watcher import post
from watcher.config import Config
from watcher.events import format_qq
from watcher.notify import send_alert
from watcher.translate import _chunks, add_translation, clean_text, translate_public_post


def response(text):
    return {'responseStatus':200, 'responseData':{'translatedText':text}}


class Translation(unittest.TestCase):
    def test_qq_translation_and_status_protection(self):
        cfg = Config(pushplus_token='fake', pushplus_qq_option='fake')
        item = post('Day 11/\nWe have reduced disk usage by 60%. https://t.co/abc')
        with patch('watcher.translate.get_json', return_value=response('磁盘占用减少了60%。')), patch(
                'watcher.notify.http_post', return_value=(200,'{"code":200}')) as send:
            send_alert(cfg, item, 3, 'daily-series')
            data=json.loads(send.call_args.args[1])
            self.assertIn('Day11', data['title'])
            self.assertIn('原文译文：', data['content'])
            self.assertNotIn('机翻参考', data['content'])
            self.assertNotIn('说明：', data['content'])
            self.assertIn('磁盘占用减少了60%', data['content'])
            self.assertEqual(len(data['content'].splitlines()), 4)
            self.assertNotRegex(data['title']+data['content'], r'http|t\.co')

    def test_source_and_output_link_cleaning(self):
        with patch('watcher.translate.get_json', return_value=response('功能已改进。 https://t.co/a **查看** www.example.com 点击查看详情 View details')) as get:
            out=translate_public_post('Day 11/\nNew improvements. https://x.com/a')
            query=parse_qs(urlparse(get.call_args.args[0]).query)
            self.assertNotRegex(query['q'][0], r'http|x\.com|Day 11')
            self.assertNotRegex(out, r'http|www|t\.co|\*|查看详情|View details')
            self.assertEqual(query['langpair'],['en|zh-CN'])

    def test_failures_fall_back_to_original_chinese(self):
        item=post(); _,body=format_qq(item)
        for value in [{'responseStatus':429}, response('NO QUERY'), [], response(''),
                      {'responseStatus':200,'quotaFinished':True}]:
            with patch('watcher.translate.get_json', return_value=value):
                self.assertEqual(add_translation(body,item.body), body)
        with patch('watcher.translate.get_json', side_effect=RuntimeError('outage')):
            self.assertEqual(add_translation(body,item.body), body)

    def test_utf8_chunks_and_clock(self):
        chunks=_chunks('🌟 A long update about Codex. '*100)
        self.assertTrue(all(len(c.encode('utf-8'))<=450 for c in chunks))
        with patch('watcher.translate.get_json', return_value=response('明天晚上8点上线。')):
            text=translate_public_post('We will launch tomorrow at 8pm PT.')
            self.assertNotIn('明天',text)
            self.assertNotIn('8点',text)

    def test_disabled_or_unconfigured_does_not_translate(self):
        for cfg in [Config(), Config(pushplus_token='fake',pushplus_qq_option='fake',qq_auto_translate=False)]:
            with patch('watcher.translate.get_json') as get, patch('watcher.notify.http_post',return_value=(200,'{"code":200}')):
                send_alert(cfg,post(),5,'reset')
                get.assert_not_called()
