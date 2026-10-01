#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""进度存储的单测"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from state import StateStore, compute_checksum  # noqa: E402


class StateStoreTest(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.state_path = self.root / 'config' / 'tmdb' / 'state.json'
        self.store = StateStore(state_path=self.state_path)

    # ---------------- 辅助 ----------------

    @staticmethod
    def _shows(path):
        return json.loads(path.read_text(encoding='utf-8'))['shows']

    def _write_raw(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str):
            path.write_text(payload, encoding='utf-8')
        else:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')

    # ---------------- 读 ----------------

    def test_load_without_file_returns_empty(self):
        state = self.store.load()
        self.assertEqual(state['shows'], {})
        self.assertFalse(self.state_path.exists())

    def test_load_all_broken_returns_empty(self):
        self.store.save({'1': {'episode': 1}})
        for path in self.store.paths:
            self._write_raw(path, 'not json at all')
        self.assertEqual(self.store.load()['shows'], {})

    def test_truncated_main_falls_back_to_backup(self):
        self.store.save({'1': {'episode': 1}})
        self.store.save({'1': {'episode': 2}})
        self._write_raw(self.state_path, '')
        self.assertEqual(self.store.load()['shows'], {'1': {'episode': 1}})

    def test_checksum_mismatch_falls_back_to_backup(self):
        self.store.save({'1': {'episode': 1}})
        self.store.save({'1': {'episode': 2}})

        payload = json.loads(self.state_path.read_text(encoding='utf-8'))
        payload['shows']['1']['episode'] = 99
        self._write_raw(self.state_path, payload)

        self.assertEqual(self.store.load()['shows'], {'1': {'episode': 1}})

    def test_broken_main_and_backup_fall_back_to_second_backup(self):
        self.store.save({'1': {'episode': 1}})
        self.store.save({'1': {'episode': 2}})
        self.store.save({'1': {'episode': 3}})
        self._write_raw(self.store.paths[0], '{}')
        self._write_raw(self.store.paths[1], '{}')
        self.assertEqual(self.store.load()['shows'], {'1': {'episode': 1}})

    def test_wrong_shape_is_rejected(self):
        self._write_raw(self.state_path, {'shows': []})
        self.assertEqual(self.store.load()['shows'], {})

    # ---------------- 写 ----------------

    def test_save_then_load_round_trip(self):
        shows = {'1': {'season': 1, 'episode': 2, 'air_date': '2026-09-20', 'name': '翠鸟谋杀案'}}
        self.store.save(shows)
        self.assertEqual(self.store.load()['shows'], shows)

    def test_save_writes_version_checksum_updated_at(self):
        self.store.save({'1': {'episode': 1}})
        payload = json.loads(self.state_path.read_text(encoding='utf-8'))
        self.assertEqual(payload['version'], 1)
        self.assertEqual(payload['checksum'], compute_checksum(payload['shows']))
        self.assertIn('updated_at', payload)

    def test_backup_rotates_generations(self):
        self.store.save({'1': {'episode': 1}})
        self.store.save({'1': {'episode': 2}})
        self.store.save({'1': {'episode': 3}})

        self.assertEqual(self._shows(self.store.paths[0]), {'1': {'episode': 3}})
        self.assertEqual(self._shows(self.store.paths[1]), {'1': {'episode': 2}})
        self.assertEqual(self._shows(self.store.paths[2]), {'1': {'episode': 1}})

    def test_save_creates_parent_directory(self):
        self.assertFalse(self.state_path.parent.exists())
        self.store.save({'1': {'episode': 1}})
        self.assertTrue(self.state_path.parent.is_dir())

    def test_save_leaves_no_tmp_file(self):
        self.store.save({'1': {'episode': 1}})
        leftovers = [p.name for p in self.state_path.parent.iterdir() if p.name.endswith('.tmp')]
        self.assertEqual(leftovers, [])

    def test_reset_removes_all_generations(self):
        self.store.save({'1': {'episode': 1}})
        self.store.save({'1': {'episode': 2}})
        self.store.reset()
        for path in self.store.paths:
            self.assertFalse(path.exists())
        self.assertEqual(self.store.load()['shows'], {})

    # ---------------- 迁移 ----------------

    def _make_legacy(self, shows):
        legacy = self.root / 'config' / 'tmdb_state.json'
        self._write_raw(legacy, {'updated_at': '2026-10-01T16:19:29', 'shows': shows})
        return legacy

    def test_legacy_migrated_and_kept(self):
        legacy = self._make_legacy({'7': {'episode': 3, 'name': '某剧'}})
        store = StateStore(state_path=self.state_path, legacy_path=legacy)

        self.assertEqual(store.load()['shows'], {'7': {'episode': 3, 'name': '某剧'}})
        self.assertTrue(self.state_path.exists())
        self.assertTrue(legacy.exists())

    def test_migration_skipped_when_new_state_exists(self):
        legacy = self._make_legacy({'7': {'episode': 3}})
        self.store.save({'9': {'episode': 1}})

        store = StateStore(state_path=self.state_path, legacy_path=legacy)
        self.assertEqual(store.load()['shows'], {'9': {'episode': 1}})

    def test_broken_legacy_is_ignored(self):
        legacy = self.root / 'config' / 'tmdb_state.json'
        self._write_raw(legacy, 'not json')
        store = StateStore(state_path=self.state_path, legacy_path=legacy)

        self.assertEqual(store.load()['shows'], {})
        self.assertFalse(self.state_path.exists())


if __name__ == '__main__':
    unittest.main()
