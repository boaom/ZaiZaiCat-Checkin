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
    只追踪**加入列表之后**发生的更新。第一次见到某部剧时只记录进度、不通知，
    避免刚把剧加进列表就收到一堆「更新啦」。

    进度用 (季, 集) 作为标识存在 config/tmdb_state.json，
    所以脚本漏跑几天也没关系，下次跑会把期间新出的集数一次性补报。

推送文案（示例，实际内容按剧集信息生成）：
    📺 追剧更新提醒
    《翠鸟谋杀案》更新啦！
    第 1 季 第 3 集：花园里的低语
    播出日期：2026-09-20
    #追剧更新

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
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).parent))

from api import TMDBClient, TMDBError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DEFAULT_OPTIONS = {
    'language': 'zh-CN',
    'list_type': 'watchlist',   # watchlist（在看列表）| list（自定义列表）
    'max_workers': 5,           # 并发拉取剧集详情的线程数
    'notify_when_empty': False,  # 无更新时是否也推一条
    'upcoming_days': 0,         # >0 时在卡片末尾附带 N 天内的待播预告
}


def format_update_message(show: Dict[str, Any], episode: Dict[str, Any]) -> str:
    """
    按固定文案格式生成更新卡片

    Args:
        show: 剧集信息，至少含 name
        episode: TMDB 的 episode 对象，含 season_number / episode_number / name / air_date
    """
    season = episode.get('season_number')
    number = episode.get('episode_number')
    title = f"第 {season} 季 第 {number} 集"
    episode_name = (episode.get('name') or '').strip()
    if episode_name:
        title += f"：{episode_name}"

    return '\n'.join([
        '📺 追剧更新提醒',
        f"《{show.get('name') or '未知剧集'}》更新啦！",
        title,
        f"播出日期：{episode.get('air_date') or '未知'}",
        '#追剧更新',
    ])


class TelegramNotifier:
    """直连 Telegram Bot API 推送（独立于项目统一推送配置）"""

    def __init__(self, bot_token: str, chat_id: str,
                 api_host: str = '', proxy: str = '', timeout: int = 20):
        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self.api_host = (api_host or '').strip()
        self.proxy = (proxy or '').strip()
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, text: str) -> bool:
        """发送一条文本消息"""
        import requests

        if not self.enabled:
            logger.error("❌ Telegram 未配置 bot_token / chat_id")
            return False

        host = self.api_host or 'api.telegram.org'
        url = f"https://{host}/bot{self.bot_token}/sendMessage"
        payload = {
            'chat_id': self.chat_id,
            'text': text,
            'disable_web_page_preview': True,
        }
        proxies = {'https': self.proxy, 'http': self.proxy} if self.proxy else None

        try:
            response = requests.post(url, json=payload, timeout=self.timeout, proxies=proxies)
            data = response.json()
        except Exception as e:
            logger.error(f"❌ Telegram 推送异常: {e}")
            return False

        if not data.get('ok'):
            logger.error(f"❌ Telegram 推送失败: {data.get('description')}")
            return False
        return True


class EpisodeTracker:
    """剧集更新追踪器"""

    def __init__(self, config_path: Path = None, state_path: Path = None):
        self.config_path = Path(config_path or (project_root / 'config' / 'token.json'))
        self.state_path = Path(state_path or (project_root / 'config' / 'tmdb_state.json'))
        self.config: Dict[str, Any] = {}
        self.options: Dict[str, Any] = dict(DEFAULT_OPTIONS)
        self.state: Dict[str, Any] = {'shows': {}}
        self.client: Optional[TMDBClient] = None
        self.notifier: Optional[TelegramNotifier] = None
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

        notify = self.config.get('notify') or {}
        self.notifier = TelegramNotifier(
            bot_token=notify.get('bot_token') or '',
            chat_id=notify.get('chat_id') or '',
            api_host=notify.get('api_host') or '',
            proxy=notify.get('proxy') or '',
        )

        self.account_id = str(self.config.get('account_id') or '')
        if not self.account_id and self.options['list_type'] == 'watchlist':
            # 没配就自己查一次
            self.account_id = str(self.client.get_account().get('id') or '')
            logger.info(f"自动获取 account_id = {self.account_id}")

    # ---------------- 进度 ----------------

    def load_state(self) -> None:
        if not self.state_path.exists() and not self.state_backup_path.exists():
            logger.info("进度文件不存在，本次将只初始化不推送")
            self.state = {'shows': {}}
            return

        for path in (self.state_path, self.state_backup_path):
            if not path.exists():
                continue
            try:
                state = self._read_state_file(path)
            except (json.JSONDecodeError, OSError, ValueError) as e:
                logger.warning(f"⚠️ 进度文件读取失败（{path.name}）: {e}")
                continue
            self.state = state
            if path != self.state_path:
                logger.warning(f"⚠️ 主进度文件不可用，已从备份 {path.name} 恢复")
            logger.info(f"已加载 {len(self.state['shows'])} 部剧的追踪进度")
            return

        logger.warning("⚠️ 进度文件及其备份均不可用，按空进度处理")
        self.state = {'shows': {}}

    @property
    def state_backup_path(self) -> Path:
        return self.state_path.with_name(self.state_path.name + '.bak')

    @staticmethod
    def _read_state_file(path: Path) -> Dict[str, Any]:
        with open(path, 'r', encoding='utf-8') as f:
            state = json.load(f)
        if not isinstance(state, dict) or not isinstance(state.get('shows'), dict):
            raise ValueError("进度文件结构不正确")
        state.setdefault('shows', {})
        return state

    def save_state(self) -> None:
        self.state['updated_at'] = datetime.now().isoformat(timespec='seconds')
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        # 先写临时文件再原子替换：中途被杀掉也不会把进度文件截断成空文件
        tmp_path = self.state_path.with_name(f"{self.state_path.name}.{os.getpid()}.tmp")
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
                f.write('\n')
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.state_path)
            try:
                # 主文件落盘后再镜像一份，备份始终和主文件同版本
                shutil.copyfile(self.state_path, self.state_backup_path)
            except OSError as e:
                logger.warning(f"⚠️ 备份进度文件失败: {e}")
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
        logger.info(f"进度已写入 {self.state_path}")

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

    # ---------------- 核心检查 ----------------

    def check(self) -> Dict[str, Any]:
        """
        检查所有剧集，返回本次发现的更新

        Returns:
            {'shows': 总数, 'updates': [(show, episode)], 'initialized': int, 'failed': int}
        """
        shows = self.fetch_shows()
        today = date.today().isoformat()
        tracked = self.state['shows']

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

        updates: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
        initialized = 0

        for show in shows:
            series_id = str(show.get('id') or '')
            detail = details.get(int(show['id'])) if show.get('id') else None
            if not series_id or detail is None:
                continue

            # 用详情里的中文名，列表接口有时给的是原名
            merged = dict(show)
            merged['name'] = detail.get('name') or show.get('name')

            episode = detail.get('last_episode_to_air') or {}
            air_date = episode.get('air_date')
            if not air_date or not episode.get('episode_number'):
                continue

            current = {
                'season': episode.get('season_number'),
                'episode': episode.get('episode_number'),
                'air_date': air_date,
            }
            known = tracked.get(series_id)

            if known is None:
                # 首次见到这部剧：只记录，不通知
                tracked[series_id] = {
                    **current,
                    'name': merged['name'],
                    'tracked_since': datetime.now().isoformat(timespec='seconds'),
                }
                initialized += 1
                continue

            if (known.get('season'), known.get('episode')) == (current['season'], current['episode']):
                continue

            # 进度变了，但这一集还没播出（TMDB 提前标了），先不动
            if air_date > today:
                continue

            updates.append((merged, episode))
            tracked[series_id] = {
                **current,
                'name': merged['name'],
                'notified_at': datetime.now().isoformat(timespec='seconds'),
            }

        return {
            'shows': len(shows),
            'updates': updates,
            'initialized': initialized,
            'failed': failed,
        }

    # ---------------- 待播预告 ----------------

    def collect_upcoming(self, shows: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        """收集 N 天内待播出的剧集（upcoming_days > 0 时启用）"""
        days = int(self.options.get('upcoming_days') or 0)
        if days <= 0:
            return []

        from datetime import timedelta
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

    def run(self, dry_run: bool = False, reset: bool = False) -> int:
        if reset:
            for path in (self.state_path, self.state_backup_path):
                if path.exists():
                    path.unlink()
            logger.info("已清空进度文件")
            self.state = {'shows': {}}

        first_run = not self.state['shows']
        result = self.check()

        logger.info(
            f"共 {result['shows']} 部剧，"
            f"新纳入追踪 {result['initialized']} 部，"
            f"本次更新 {len(result['updates'])} 部，"
            f"详情失败 {result['failed']} 部"
        )

        messages = [format_update_message(show, episode) for show, episode in result['updates']]

        if first_run:
            messages.append(
                f"✅ 追剧追踪已启动\n"
                f"正在追踪 {len(self.state['shows'])} 部剧集\n"
                f"有新集才推送"
            )
        elif not messages and self.options.get('notify_when_empty'):
            messages.append(f"📺 追剧更新提醒\n今天没有剧集更新～")

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
        for message in messages:
            if self.notifier.send(message):
                sent += 1
            import time as _time
            _time.sleep(1.5)  # 避免群消息刷屏触发 Telegram 限流

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
