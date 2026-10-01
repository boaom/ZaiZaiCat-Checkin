#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新判定的单测"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracker import evaluate, extract_progress, merge_show  # noqa: E402

TODAY = '2026-10-01'
NOW = '2026-10-01T20:00:00'


def make_show(series_id=1, name='原名'):
    return {'id': series_id, 'name': name, 'first_air_date': '2024-01-01'}


def make_episode(season=1, episode=3, air_date='2026-09-20', name='花园里的低语'):
    return {
        'season_number': season,
        'episode_number': episode,
        'air_date': air_date,
        'name': name,
    }


def make_detail(name='翠鸟谋杀案', episode=None):
    return {
        'name': name,
        'last_episode_to_air': episode if episode is not None else make_episode(),
    }


def run(shows, details, tracked=None):
    return evaluate(shows, details, tracked or {}, today=TODAY, now=NOW)


class ExtractProgressTest(unittest.TestCase):

    def test_full_episode(self):
        self.assertEqual(
            extract_progress(make_episode()),
            {'season': 1, 'episode': 3, 'air_date': '2026-09-20'},
        )

    def test_missing_air_date(self):
        self.assertIsNone(extract_progress(make_episode(air_date=None)))

    def test_missing_episode_number(self):
        self.assertIsNone(extract_progress(make_episode(episode=None)))

    def test_empty_episode(self):
        self.assertIsNone(extract_progress({}))


class MergeShowTest(unittest.TestCase):

    def test_detail_name_wins(self):
        self.assertEqual(merge_show(make_show(), make_detail(name='中文名'))['name'], '中文名')

    def test_falls_back_to_show_name(self):
        self.assertEqual(merge_show(make_show(name='原名'), make_detail(name=''))['name'], '原名')

    def test_original_show_not_mutated(self):
        show = make_show()
        merge_show(show, make_detail(name='中文名'))
        self.assertEqual(show['name'], '原名')


class EvaluateTest(unittest.TestCase):

    def test_first_sight_only_records(self):
        result = run([make_show()], {1: make_detail()})

        self.assertEqual(result['initialized'], 1)
        self.assertEqual(result['updates'], [])
        self.assertEqual(len(result['initialized_shows']), 1)
        self.assertEqual(result['tracked']['1'], {
            'season': 1,
            'episode': 3,
            'air_date': '2026-09-20',
            'name': '翠鸟谋杀案',
            'tracked_since': NOW,
        })

    def test_initialized_shows_carry_show_and_episode(self):
        result = run([make_show(7)], {7: make_detail(name='某剧')})

        show, episode = result['initialized_shows'][0]
        self.assertEqual(show['name'], '某剧')
        self.assertEqual(episode['episode_number'], 3)

    def test_initialized_shows_empty_when_nothing_new(self):
        tracked = {'1': {'season': 1, 'episode': 3, 'air_date': '2026-09-20',
                         'name': '翠鸟谋杀案', 'tracked_since': '2026-09-01T00:00:00'}}
        result = run([make_show()], {1: make_detail()}, tracked)

        self.assertEqual(result['initialized'], 0)
        self.assertEqual(result['initialized_shows'], [])

    def test_same_episode_is_not_an_update(self):
        tracked = {'1': {'season': 1, 'episode': 3, 'air_date': '2026-09-20',
                         'name': '翠鸟谋杀案', 'tracked_since': '2026-09-01T00:00:00'}}
        result = run([make_show()], {1: make_detail()}, tracked)

        self.assertEqual(result['updates'], [])
        self.assertEqual(result['initialized'], 0)
        self.assertEqual(result['tracked'], tracked)

    def test_advanced_and_aired_is_an_update(self):
        tracked = {'1': {'season': 1, 'episode': 2, 'air_date': '2026-09-13',
                         'name': '翠鸟谋杀案', 'tracked_since': '2026-09-01T00:00:00'}}
        result = run([make_show()], {1: make_detail()}, tracked)

        self.assertEqual(len(result['updates']), 1)
        show, episode = result['updates'][0]
        self.assertEqual(show['name'], '翠鸟谋杀案')
        self.assertEqual(episode['episode_number'], 3)
        self.assertEqual(result['tracked']['1']['episode'], 3)
        self.assertEqual(result['tracked']['1']['notified_at'], NOW)

    def test_advanced_but_not_aired_yet_is_skipped(self):
        tracked = {'1': {'season': 1, 'episode': 2, 'air_date': '2026-09-13',
                         'name': '翠鸟谋杀案', 'tracked_since': '2026-09-01T00:00:00'}}
        detail = make_detail(episode=make_episode(episode=4, air_date='2026-10-11'))
        result = run([make_show()], {1: detail}, tracked)

        self.assertEqual(result['updates'], [])
        self.assertEqual(result['tracked'], tracked)

    def test_airing_today_counts_as_aired(self):
        tracked = {'1': {'season': 1, 'episode': 2, 'air_date': '2026-09-13',
                         'name': '翠鸟谋杀案', 'tracked_since': '2026-09-01T00:00:00'}}
        detail = make_detail(episode=make_episode(episode=4, air_date=TODAY))
        result = run([make_show()], {1: detail}, tracked)

        self.assertEqual(len(result['updates']), 1)

    def test_episode_without_air_date_is_skipped(self):
        detail = make_detail(episode=make_episode(air_date=None))
        result = run([make_show()], {1: detail})

        self.assertEqual(result['initialized'], 0)
        self.assertEqual(result['tracked'], {})

    def test_missing_detail_is_skipped(self):
        result = run([make_show()], {})

        self.assertEqual(result['initialized'], 0)
        self.assertEqual(result['updates'], [])
        self.assertEqual(result['tracked'], {})

    def test_show_without_id_is_skipped(self):
        result = run([{'name': '没有 id'}], {1: make_detail()})

        self.assertEqual(result['tracked'], {})

    def test_input_tracked_is_not_mutated(self):
        tracked = {'1': {'season': 1, 'episode': 2, 'air_date': '2026-09-13',
                         'name': '翠鸟谋杀案', 'tracked_since': '2026-09-01T00:00:00'}}
        snapshot = {key: dict(value) for key, value in tracked.items()}
        run([make_show()], {1: make_detail()}, tracked)

        self.assertEqual(tracked, snapshot)

    def test_mixed_batch(self):
        shows = [make_show(1), make_show(2), make_show(3)]
        details = {
            1: make_detail(name='A'),                                        # 首次见到
            2: make_detail(name='B', episode=make_episode(episode=5)),       # 有更新
            3: make_detail(name='C', episode=make_episode(episode=1)),       # 进度未变
        }
        tracked = {
            '2': {'season': 1, 'episode': 4, 'air_date': '2026-09-20',
                  'name': 'B', 'tracked_since': '2026-09-01T00:00:00'},
            '3': {'season': 1, 'episode': 1, 'air_date': '2026-09-20',
                  'name': 'C', 'tracked_since': '2026-09-01T00:00:00'},
        }
        result = run(shows, details, tracked)

        self.assertEqual(result['initialized'], 1)
        self.assertEqual(len(result['initialized_shows']), 1)
        self.assertEqual(len(result['updates']), 1)
        self.assertEqual(result['updates'][0][0]['name'], 'B')
        self.assertEqual(sorted(result['tracked']), ['1', '2', '3'])

    def test_missing_tracked_keys_are_not_lost(self):
        tracked = {'99': {'season': 2, 'episode': 1, 'air_date': '2020-01-01', 'name': '已下架'}}
        result = run([], {}, tracked)

        self.assertEqual(result['tracked'], tracked)


if __name__ == '__main__':
    unittest.main()
