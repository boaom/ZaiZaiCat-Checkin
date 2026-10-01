#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
new Env('追剧更新提醒');
cron: 0 20 * * *
"""
"""
剧集更新追踪脚本

剧源来自 TMDB 账号的「在看列表」（watchlist），由青龙定时触发，
每次跑发现某部剧集数往前推进了就把更新卡片推到 Telegram 群。

判定规则：
    首次执行（进度文件为空）时给每部剧各推一张「已纳入追踪」卡片，并把当前进度落盘。
    之后每次跑只推**进度往前推进了**的剧，一部剧一张卡片；
    新加进列表的剧只记录不通知，避免刚加剧就收到「更新啦」。

    进度用 (季, 集) 作为标识存在 config/tmdb/state.json，
    所以脚本漏跑几天也没关系，下次跑会把期间新出的集数一次性补报。

推送文案（示例，实际内容按剧集信息生成）：
    📺 追剧更新提醒
    《翠鸟谋杀案》更新啦！
    第 1 季 第 3 集：花园里的低语
    播出日期：2026-09-20
    #追剧更新

模块划分：
    main.py     CLI 与编排（本文件）
    tracker.py  更新判定（纯逻辑）
    state.py    进度持久化（代际备份 + 自校验）
    notify.py   推送适配
    message.py  文案
    api.py      TMDB 接口封装

用法：
    python script/tmdb/main.py              # 正常跑
    python script/tmdb/main.py --dry-run    # 只打印不推送
    python script/tmdb/main.py --list       # 只列当前在看列表
    python script/tmdb/main.py --reset      # 清空进度（下次跑会重新初始化）

Author: ZaiZaiCat
Date: 2026-10-01
"""

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).parent))

from api import TMDBClient, TMDBError
from message import (format_empty_message, format_init_message, format_startup_message,
                     format_update_message)
from notify import build_notifier
from state import StateStore
from tracker import evaluate

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = project_root / 'config' / 'token.json'
DEFAULT_STATE_PATH = project_root / 'config' / 'tmdb' / 'state.json'
DEFAULT_LEGACY_STATE_PATH = project_root / 'config' / 'tmdb_state.json'

DEFAULT_OPTIONS = {
    'language': 'zh-CN',
    'list_type': 'watchlist',   # watchlist（在看列表）| list（自定义列表）
    'max_workers': 5,           # 并发拉取剧集详情的线程数
    'notify_when_empty': False,  # 无更新时是否也推一条
    'upcoming_days': 0,         # >0 时在卡片末尾附带 N 天内的待播预告
    'notify_interval': 1.5,      # 日常推送之间的间隔（秒）
    'init_notify_interval': 3.5,  # 首次执行批量推送时的间隔（秒），避开群限流
}


class EpisodeTracker:
    """编排：读配置 → 拉列表 → 并发取详情 → 判定 → 写进度 → 推送"""

    def __init__(self, config_path: Path = None, state_path: Path = None):
        self.config_path = Path(config_path or DEFAULT_CONFIG_PATH)
        self.store = StateStore(
            state_path=Path(state_path) if state_path else DEFAULT_STATE_PATH,
            legacy_path=None if state_path else DEFAULT_LEGACY_STATE_PATH,
        )
        self.config: Dict[str, Any] = {}
        self.options: Dict[str, Any] = dict(DEFAULT_OPTIONS)
        self.state: Dict[str, Any] = {'shows': {}}
        self.client: Optional[TMDBClient] = None
        self.notifier = None
        self.load_config()
        self.load_state()

    # ---------------- 配置 ----------------

    def load_config(self) -> None:
        logger.info(f"正在读取配置文件: {self.config_path}")
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        self.config = config.get('tmdb') or {}
        if not self.config:
            raise ValueError("配置文件中没有 tmdb 节点")

        self.options.update(self.config.get('options') or {})

        access_token = self.config.get('access_token')
        api_key = self.config.get('api_key')
        if not access_token and not api_key:
            raise ValueError("tmdb 节点缺少 access_token / api_key")

        self.client = TMDBClient(
            api_key=api_key,
            access_token=access_token,
            language=self.options['language'],
        )

        self.notifier = build_notifier(self.config.get('notify'))

        self.account_id = str(self.config.get('account_id') or '')
        if not self.account_id and self.options['list_type'] == 'watchlist':
            # 没配就自己查一次
            self.account_id = str(self.client.get_account().get('id') or '')
            logger.info(f"自动获取 account_id = {self.account_id}")

    # ---------------- 进度 ----------------

    def load_state(self) -> None:
        self.state = self.store.load()

    def save_state(self) -> None:
        self.store.save(self.state['shows'])

    # ---------------- 剧源 ----------------

    def fetch_shows(self) -> List[Dict[str, Any]]:
        """按配置从 TMDB 拉取待追踪的剧集列表"""
        list_type = self.options['list_type']

        if list_type == 'list':
            list_id = str(self.config.get('list_id') or '')
            if not list_id:
                raise ValueError("list_type=list 时必须配置 list_id")
            data = self.client.get_list(list_id)
            shows = [i for i in (data.get('items') or []) if i.get('media_type') in (None, 'tv')]
            logger.info(f"从自定义列表《{data.get('name')}》读取到 {len(shows)} 部剧")
            return shows

        if not self.account_id:
            raise ValueError("list_type=watchlist 时必须配置 account_id")
        shows = list(self.client.iter_watchlist_tv(self.account_id))
        logger.info(f"从在看列表读取到 {len(shows)} 部剧")
        return shows

    def fetch_detail(self, series_id: int) -> Tuple[int, Optional[Dict[str, Any]]]:
        """拉取单部剧的详情，失败返回 None（不中断整体）"""
        try:
            return series_id, self.client.get_tv_detail(series_id)
        except TMDBError as e:
            logger.warning(f"⚠️ 剧集 {series_id} 详情拉取失败: {e}")
            return series_id, None

    def collect_details(self, shows: List[Dict[str, Any]]) -> Tuple[Dict[int, Dict[str, Any]], int]:
        """
        并发拉取所有剧集的详情

        Returns:
            (details, 失败数)
        """
        details: Dict[int, Dict[str, Any]] = {}
        failed = 0
        with ThreadPoolExecutor(max_workers=int(self.options['max_workers'])) as pool:
            futures = [pool.submit(self.fetch_detail, int(s['id'])) for s in shows if s.get('id')]
            for future in as_completed(futures):
                series_id, detail = future.result()
                if detail is None:
                    failed += 1
                else:
                    details[series_id] = detail
        return details, failed

    # ---------------- 核心检查 ----------------

    def check(self) -> Dict[str, Any]:
        """
        检查所有剧集，返回本次发现的更新

        Returns:
            {'shows': 总数, 'updates': [(show, episode)], 'initialized': int,
             'initialized_shows': [(show, episode)], 'failed': int}
        """
        shows = self.fetch_shows()
        details, failed = self.collect_details(shows)

        result = evaluate(shows, details, self.state['shows'])
        self.state['shows'] = result['tracked']

        return {
            'shows': len(shows),
            'updates': result['updates'],
            'initialized': result['initialized'],
            'initialized_shows': result['initialized_shows'],
            'failed': failed,
        }

    # ---------------- 待播预告 ----------------

    def collect_upcoming(self, shows: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        """收集 N 天内待播出的剧集（upcoming_days > 0 时启用）"""
        days = int(self.options.get('upcoming_days') or 0)
        if days <= 0:
            return []

        limit = (date.today() + timedelta(days=days)).isoformat()
        today = date.today().isoformat()

        upcoming = []
        for show in shows:
            try:
                detail = self.client.get_tv_detail(int(show['id']))
            except (TMDBError, KeyError, TypeError):
                continue
            episode = detail.get('next_episode_to_air') or {}
            air_date = episode.get('air_date')
            if air_date and today <= air_date <= limit:
                merged = dict(show, name=detail.get('name') or show.get('name'))
                upcoming.append((merged, episode))
        upcoming.sort(key=lambda x: x[1].get('air_date') or '')
        return upcoming

    # ---------------- 主流程 ----------------

    def build_messages(self, result: Dict[str, Any], first_run: bool) -> List[str]:
        """
        按本次判定结果拼出要推送的文案

        首次执行（进度文件为空）时给每部剧各发一张「已纳入追踪」卡片，
        之后只发本次有更新的剧。
        """
        if first_run:
            cards = [format_init_message(show, episode)
                     for show, episode in result['initialized_shows']]
            if cards:
                return cards
            # 在看列表为空这种退化情况，保留一条汇总
            return [format_startup_message(len(self.state['shows']))]

        messages = [format_update_message(show, episode) for show, episode in result['updates']]
        if not messages and self.options.get('notify_when_empty'):
            messages.append(format_empty_message())
        return messages

    def run(self, dry_run: bool = False, reset: bool = False) -> int:
        if reset:
            self.store.reset()
            self.state = {'shows': {}}

        first_run = not self.state['shows']
        result = self.check()

        logger.info(
            f"共 {result['shows']} 部剧，"
            f"新纳入追踪 {result['initialized']} 部，"
            f"本次更新 {len(result['updates'])} 部，"
            f"详情失败 {result['failed']} 部"
        )

        messages = self.build_messages(result, first_run)

        for message in messages:
            print(f"\n{'-' * 40}\n{message}")

        if dry_run:
            # dry-run 不写进度、不推送，方便反复验证判定逻辑
            logger.info("dry-run 模式：不写进度、不推送")
            return 0

        self.save_state()

        if not messages:
            logger.info("本次没有需要推送的内容")
            return 0

        sent = 0
        interval = float(self.options['init_notify_interval'] if first_run
                         else self.options['notify_interval'])
        for index, message in enumerate(messages):
            if self.notifier.send(message):
                sent += 1
            if index < len(messages) - 1:
                # 避免群消息刷屏触发 Telegram 限流；首次执行会连发几十条，间隔更宽
                time.sleep(interval)

        logger.info(f"推送完成 {sent}/{len(messages)}")
        return 0 if sent == len(messages) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description='TMDB 剧集更新追踪')
    parser.add_argument('--dry-run', action='store_true', help='只打印不推送')
    parser.add_argument('--reset', action='store_true', help='清空追踪进度后重新初始化')
    parser.add_argument('--list', action='store_true', help='只列出当前在看列表')
    parser.add_argument('--config', help='配置文件路径')
    parser.add_argument('--state', help='进度文件路径')
    args = parser.parse_args()

    start = datetime.now()
    logger.info("=" * 60)
    logger.info(f"剧集更新追踪开始 - {start.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    try:
        tracker = EpisodeTracker(config_path=args.config, state_path=args.state)

        if args.list:
            shows = tracker.fetch_shows()
            for show in shows:
                print(f"{show.get('id'):>8} | {(show.get('name') or '')[:30]:32} | "
                      f"{show.get('first_air_date') or '':10} | {show.get('vote_average')}")
            print(f"\n共 {len(shows)} 部")
            return 0

        code = tracker.run(dry_run=args.dry_run, reset=args.reset)
        logger.info(f"执行耗时 {int((datetime.now() - start).total_seconds())} 秒")
        return code

    except Exception as e:
        logger.error(f"执行异常: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
