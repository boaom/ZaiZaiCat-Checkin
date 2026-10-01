#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编排层的单测（只测不碰网络的部分）"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import DEFAULT_OPTIONS, EpisodeTracker  # noqa: E402


def make_tracker(options=None, tracked=None):
    tracker = EpisodeTracker.__new__(EpisodeTracker)
    tracker.options = dict(DEFAULT_OPTIONS)
    tracker.options.update(options or {})
    tracker.state = {'shows': tracked or {}}
    return tracker


def card(show_name, episode_number):
    return ({'name': show_name}, {'season_number': 1, 'episode_number': episode_number,
                                  'air_date': '2026-09-20'})


class BuildMessagesTest(unittest.TestCase):

    def test_first_run_sends_one_card_per_show(self):
        tracker = make_tracker()
        result = {
            'updates': [],
            'initialized_shows': [card('甲剧', 1), card('乙剧', 2), card('丙剧', 3)],
        }
        messages = tracker.build_messages(result, first_run=True)

        self.assertEqual(len(messages), 3)
        self.assertIn('《甲剧》已纳入追踪', messages[0])
        self.assertIn('《乙剧》已纳入追踪', messages[1])
        self.assertIn('《丙剧》已纳入追踪', messages[2])

    def test_first_run_cards_are_not_update_cards(self):
        tracker = make_tracker()
        result = {'updates': [], 'initialized_shows': [card('甲剧', 1)]}
        messages = tracker.build_messages(result, first_run=True)

        self.assertNotIn('更新啦', messages[0])

    def test_first_run_with_empty_watchlist_falls_back_to_summary(self):
        tracker = make_tracker()
        messages = tracker.build_messages({'updates': [], 'initialized_shows': []},
                                          first_run=True)

        self.assertEqual(len(messages), 1)
        self.assertIn('追剧追踪已启动', messages[0])

    def test_first_run_ignores_notify_when_empty(self):
        tracker = make_tracker({'notify_when_empty': True})
        messages = tracker.build_messages(
            {'updates': [], 'initialized_shows': [card('甲剧', 1)]}, first_run=True)

        self.assertEqual(len(messages), 1)
        self.assertIn('已纳入追踪', messages[0])

    def test_later_run_sends_only_updates(self):
        tracker = make_tracker(tracked={'1': {'episode': 3}})
        result = {'updates': [card('甲剧', 4), card('乙剧', 5)], 'initialized_shows': []}
        messages = tracker.build_messages(result, first_run=False)

        self.assertEqual(len(messages), 2)
        self.assertIn('《甲剧》更新啦！', messages[0])
        self.assertIn('《乙剧》更新啦！', messages[1])

    def test_later_run_silent_without_updates(self):
        tracker = make_tracker(tracked={'1': {'episode': 3}})
        messages = tracker.build_messages({'updates': [], 'initialized_shows': []},
                                          first_run=False)

        self.assertEqual(messages, [])

    def test_later_run_notify_when_empty(self):
        tracker = make_tracker({'notify_when_empty': True}, tracked={'1': {'episode': 3}})
        messages = tracker.build_messages({'updates': [], 'initialized_shows': []},
                                          first_run=False)

        self.assertEqual(messages, ['📺 追剧更新提醒\n今天没有剧集更新～'])


class OptionsTest(unittest.TestCase):

    def test_default_intervals(self):
        self.assertEqual(DEFAULT_OPTIONS['notify_interval'], 1.5)
        self.assertGreater(DEFAULT_OPTIONS['init_notify_interval'],
                           DEFAULT_OPTIONS['notify_interval'])


class CheckTest(unittest.TestCase):
    """用假数据喂 check()，确认它把 tracker 的结果原样透传出来"""

    SHOWS = [{'id': 1, 'name': '甲剧'}, {'id': 2, 'name': '乙剧'}, {'id': 3, 'name': '丙剧'}]
    DETAILS = {
        1: {'name': '甲剧', 'last_episode_to_air': {'season_number': 1, 'episode_number': 1,
                                                    'air_date': '2026-09-20', 'name': ''}},
        2: {'name': '乙剧', 'last_episode_to_air': {'season_number': 1, 'episode_number': 5,
                                                    'air_date': '2026-09-20', 'name': ''}},
    }

    def _tracker(self, tracked):
        tracker = make_tracker(tracked=tracked)
        tracker.fetch_shows = lambda: [dict(show) for show in self.SHOWS]
        tracker.fetch_detail = lambda series_id: (
            (series_id, self.DETAILS.get(series_id))
        )
        return tracker

    def test_first_run_reports_every_initialized_show(self):
        tracker = self._tracker({})
        result = tracker.check()

        self.assertEqual(result['shows'], 3)
        self.assertEqual(result['initialized'], 2)
        self.assertEqual(len(result['initialized_shows']), 2)
        self.assertEqual(result['failed'], 1)
        self.assertEqual(sorted(tracker.state['shows']), ['1', '2'])

    def test_initialized_shows_are_passed_through_to_cards(self):
        tracker = self._tracker({})
        messages = tracker.build_messages(tracker.check(), first_run=True)

        self.assertEqual(len(messages), 2)
        self.assertTrue(all('已纳入追踪' in message for message in messages))

    def test_later_run_reports_only_updates(self):
        tracked = {
            '1': {'season': 1, 'episode': 1, 'air_date': '2026-09-13', 'name': '甲剧'},
            '2': {'season': 1, 'episode': 4, 'air_date': '2026-09-13', 'name': '乙剧'},
        }
        tracker = self._tracker(tracked)
        result = tracker.check()

        self.assertEqual(result['initialized'], 0)
        self.assertEqual(result['initialized_shows'], [])
        self.assertEqual(len(result['updates']), 1)
        self.assertEqual(result['updates'][0][0]['name'], '乙剧')


if __name__ == '__main__':
    unittest.main()
