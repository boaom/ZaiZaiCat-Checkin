#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
追踪进度的持久化

存储形态（config/tmdb/ 目录）：
    state.json      当前进度
    state.json.1    上一代
    state.json.2    上上代

每份文件都带 version / updated_at / checksum 三个元字段，
checksum 是 shows 规范化 JSON 的 sha256，用来识别「JSON 合法但内容被改坏」的情况。
加载时从新到旧取第一份校验通过的，主文件被清空或截断也能自动退回上一代。

首次运行时如果发现老位置的 config/tmdb_state.json，会自动迁移过来，
旧文件原地保留不删。
"""

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STATE_VERSION = 1
BACKUP_GENERATIONS = 2


def compute_checksum(shows: Dict[str, Any]) -> str:
    """算 shows 的规范化 sha256，键顺序和空白不影响结果"""
    canonical = json.dumps(shows, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


class StateStore:
    """带代际备份与自校验的进度存储"""

    def __init__(self, state_path: Path = None, legacy_path: Path = None,
                 backup_generations: int = BACKUP_GENERATIONS):
        """
        Args:
            state_path: 当前进度文件路径，备份按 .1 / .2 后缀派生
            legacy_path: 老版本进度文件路径，存在且新位置为空时自动迁移
            backup_generations: 保留几代备份
        """
        self.state_path = Path(state_path)
        self.legacy_path = Path(legacy_path) if legacy_path else None
        self.backup_generations = max(1, int(backup_generations))
        self.paths: List[Path] = [self.state_path] + [
            self._generation_path(index) for index in range(1, self.backup_generations + 1)
        ]

    def _generation_path(self, index: int) -> Path:
        return self.state_path.with_name(f"{self.state_path.name}.{index}")

    # ---------------- 读 ----------------

    def load(self) -> Dict[str, Any]:
        """按新→旧顺序加载第一份可用进度，全不可用时返回空进度"""
        self.migrate_legacy()

        if not any(path.exists() for path in self.paths):
            logger.info("进度文件不存在，本次将只初始化不推送")
            return self._empty_state()

        for index, path in enumerate(self.paths):
            if not path.exists():
                continue
            try:
                shows = self._read_state_file(path)
            except (json.JSONDecodeError, OSError, ValueError) as e:
                logger.warning(f"⚠️ 进度文件读取失败（{path.name}）: {e}")
                continue
            if index:
                logger.warning(f"⚠️ 主进度文件不可用，已从备份 {path.name} 恢复")
            logger.info(f"已加载 {len(shows)} 部剧的追踪进度")
            return {'version': STATE_VERSION, 'shows': shows}

        logger.warning("⚠️ 进度文件及其备份均不可用，按空进度处理")
        return self._empty_state()

    @staticmethod
    def _empty_state() -> Dict[str, Any]:
        return {'version': STATE_VERSION, 'shows': {}}

    @staticmethod
    def _read_state_file(path: Path) -> Dict[str, Any]:
        """
        读一份进度文件并校验

        Returns:
            shows 字典

        Raises:
            ValueError: 结构不对或 checksum 对不上
        """
        with open(path, 'r', encoding='utf-8') as f:
            state = json.load(f)

        if not isinstance(state, dict) or not isinstance(state.get('shows'), dict):
            raise ValueError("进度文件结构不正确")

        shows = state['shows']
        checksum = state.get('checksum')
        if checksum:
            actual = compute_checksum(shows)
            if actual != checksum:
                raise ValueError(f"进度文件校验失败（checksum 不匹配）")
        return shows

    # ---------------- 写 ----------------

    def save(self, shows: Dict[str, Any]) -> None:
        """轮转备份后原子写入当前进度"""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._rotate()

        payload = {
            'version': STATE_VERSION,
            'updated_at': datetime.now().isoformat(timespec='seconds'),
            'checksum': compute_checksum(shows),
            'shows': shows,
        }

        # 先写临时文件再原子替换：中途被杀掉也不会把进度文件截断成空文件
        tmp_path = self.state_path.with_name(f"{self.state_path.name}.{os.getpid()}.tmp")
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.write('\n')
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.state_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
        logger.info(f"进度已写入 {self.state_path}")

    def _rotate(self) -> None:
        """state.json → .1 → .2，最老的一代被覆盖"""
        for index in range(len(self.paths) - 1, 0, -1):
            source = self.paths[index - 1]
            target = self.paths[index]
            if not source.exists():
                continue
            try:
                os.replace(source, target)
            except OSError as e:
                logger.warning(f"⚠️ 轮转备份 {source.name} → {target.name} 失败: {e}")

    def reset(self) -> None:
        """清空当前进度与全部备份"""
        for path in self.paths:
            if path.exists():
                path.unlink()
        logger.info("已清空进度文件")

    # ---------------- 迁移 ----------------

    def migrate_legacy(self) -> bool:
        """
        把老位置的进度文件转换到新位置（老文件保留）

        Returns:
            是否真的迁移了
        """
        if self.legacy_path is None or not self.legacy_path.exists():
            return False
        if any(path.exists() for path in self.paths):
            return False

        try:
            with open(self.legacy_path, 'r', encoding='utf-8') as f:
                state = json.load(f)
            if not isinstance(state, dict) or not isinstance(state.get('shows'), dict):
                raise ValueError("进度文件结构不正确")
        except (json.JSONDecodeError, OSError, ValueError) as e:
            logger.warning(f"⚠️ 旧进度文件迁移失败（{self.legacy_path.name}）: {e}")
            return False

        self.save(state['shows'])
        logger.info(f"已把旧进度文件 {self.legacy_path} 迁移到 {self.state_path}（旧文件保留）")
        return True
