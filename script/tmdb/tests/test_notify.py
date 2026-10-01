#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""推送适配的单测"""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from notify import Notifier, build_notifier  # noqa: E402

TEXT = '📺 追剧更新提醒\n《翠鸟谋杀案》更新啦！\n#追剧更新'


def fake_notification_module(result=True, calls=None):
    """造一个假的 notification 模块，避免真的去读面板配置"""
    module = types.ModuleType('notification')

    def send_notification(title, content, **kwargs):
        if calls is not None:
            calls.append((title, content, kwargs))
        return result

    module.send_notification = send_notification
    return module


class DirectTelegramTest(unittest.TestCase):

    def setUp(self):
        self.notifier = Notifier(bot_token='123:ABC', chat_id='-1001387319088')

    def test_enabled_requires_both_fields(self):
        self.assertTrue(self.notifier.enabled)
        self.assertFalse(Notifier(bot_token='123:ABC').enabled)
        self.assertFalse(Notifier(chat_id='-100').enabled)

    def test_payload_is_sent_verbatim(self):
        response = mock.Mock()
        response.json.return_value = {'ok': True}

        with mock.patch('requests.post', return_value=response) as post:
            self.assertTrue(self.notifier.send(TEXT))

        _, kwargs = post.call_args
        self.assertEqual(kwargs['json']['text'], TEXT)
        self.assertEqual(kwargs['json']['chat_id'], '-1001387319088')
        self.assertTrue(kwargs['json']['disable_web_page_preview'])
        self.assertNotIn('parse_mode', kwargs['json'])

    def test_custom_api_host(self):
        notifier = Notifier(bot_token='123:ABC', chat_id='-100', api_host='tg.example.com')
        response = mock.Mock()
        response.json.return_value = {'ok': True}

        with mock.patch('requests.post', return_value=response) as post:
            notifier.send(TEXT)

        self.assertTrue(post.call_args[0][0].startswith('https://tg.example.com/bot123:ABC/'))

    def test_telegram_error_returns_false(self):
        response = mock.Mock()
        response.json.return_value = {'ok': False, 'description': 'chat not found'}

        with mock.patch('requests.post', return_value=response):
            self.assertFalse(self.notifier.send(TEXT))

    def test_request_exception_returns_false(self):
        with mock.patch('requests.post', side_effect=OSError('boom')):
            self.assertFalse(self.notifier.send(TEXT))


class UnifiedFallbackTest(unittest.TestCase):

    def _install(self, module):
        sys.modules['notification'] = module
        self.addCleanup(sys.modules.pop, 'notification', None)

    def test_falls_back_when_not_configured(self):
        calls = []
        self._install(fake_notification_module(result=True, calls=calls))

        self.assertTrue(Notifier().send(TEXT))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], '📺 追剧更新提醒')
        self.assertEqual(calls[0][1], '《翠鸟谋杀案》更新啦！\n#追剧更新')

    def test_returns_false_when_unified_layer_fails(self):
        self._install(fake_notification_module(result=False))
        self.assertFalse(Notifier().send(TEXT))

    def test_returns_false_when_unified_layer_missing(self):
        sys.modules['notification'] = None  # 让 import 直接失败
        self.addCleanup(sys.modules.pop, 'notification', None)
        self.assertFalse(Notifier().send(TEXT))


class BuildNotifierTest(unittest.TestCase):

    def test_builds_from_config(self):
        notifier = build_notifier({
            'bot_token': '911654878:AAEfFg9uIzPov7rVa4pcfDK2SzvQmjgMCRU',
            'chat_id': '-1001387319088',
            'api_host': '',
            'proxy': '',
        })
        self.assertTrue(notifier.enabled)
        self.assertEqual(notifier.chat_id, '-1001387319088')

    def test_empty_config_is_not_enabled(self):
        self.assertFalse(build_notifier(None).enabled)
        self.assertFalse(build_notifier({}).enabled)


if __name__ == '__main__':
    unittest.main()
