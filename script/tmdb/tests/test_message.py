#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""推送文案的单测"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from message import format_empty_message, format_startup_message, format_update_message  # noqa: E402


class FormatUpdateMessageTest(unittest.TestCase):

    def test_full_card(self):
        show = {'name': '翠鸟谋杀案'}
        episode = {'season_number': 1, 'episode_number': 3,
                   'name': '花园里的低语', 'air_date': '2026-09-20'}
        self.assertEqual(
            format_update_message(show, episode),
            '📺 追剧更新提醒\n'
            '《翠鸟谋杀案》更新啦！\n'
            '第 1 季 第 3 集：花园里的低语\n'
            '播出日期：2026-09-20\n'
            '#追剧更新',
        )

    def test_without_episode_name(self):
        message = format_update_message({'name': '某剧'}, {'season_number': 2, 'episode_number': 1})
        self.assertIn('第 2 季 第 1 集\n', message)

    def test_blank_episode_name_is_trimmed(self):
        message = format_update_message({'name': '某剧'}, {'season_number': 2, 'episode_number': 1,
                                                           'name': '   '})
        self.assertIn('第 2 季 第 1 集\n', message)

    def test_missing_fields_use_placeholders(self):
        message = format_update_message({}, {})
        self.assertIn('《未知剧集》更新啦！', message)
        self.assertIn('播出日期：未知', message)


class OtherMessagesTest(unittest.TestCase):

    def test_startup_message(self):
        self.assertEqual(
            format_startup_message(58),
            '✅ 追剧追踪已启动\n正在追踪 58 部剧集\n有新集才推送',
        )

    def test_empty_message(self):
        self.assertEqual(format_empty_message(), '📺 追剧更新提醒\n今天没有剧集更新～')


if __name__ == '__main__':
    unittest.main()
