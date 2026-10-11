#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
new Env('追剧更新提醒');
cron: 30 21,9,13 * * *
"""
"""
追剧更新提醒（TMDB + 推送）

功能：
  - 通过 TMDB 跟踪指定剧集的最新播出情况
  - 一旦有新剧集已播出（air_date <= 今天），推送更新卡片
  - 不记录/不跟踪“看到第几集”，只负责“有新更新就提醒”

剧源两种模式（按 config/token.json 的 tmdb 节点决定）：
  - 配了 access_token：自动同步 TMDB 账号的「在看列表」（加剧即跟踪，删剧即停）
  - 未配：回退到下方的 TRACKED_SHOWS 列表（按名称搜索，或直接写 TMDB ID）

判定规则：
  - 首次把一部剧加入跟踪时静默建立基线（历史已播集标记为已读，避免刷屏），
    并推送一次“新关注提醒”（当前最新一集）；之后只有真正新播出的集数才会再次推送。
  - 想重新建立基线，删掉状态文件或跑 --reset 即可。

用法：
  python script/tmdb/main.py            # 正常跑
  python script/tmdb/main.py --dry-run  # 只检查不发送
  python script/tmdb/main.py --list     # 只列当前在看列表
  python script/tmdb/main.py --reset    # 清空进度（下次跑会重新初始化）

配置节点：tmdb
必填字段：access_token 或 api_key（二选一）
可选字段：account_id、options、notify

Author: boaom
Date: 2026-10-11
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 添加项目根目录到 Python 路径（统一推送层、配置都在根目录）
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = project_root / 'config' / 'token.json'
DEFAULT_STATE_PATH = project_root / 'config' / 'tmdb' / 'watch_state.json'

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_LANG = "zh-CN"          # 用中文返回剧名/集名

# 仅在未配置 access_token 时使用的备用剧集列表：
#   - 字符串 => 按名称在 TMDB 搜索（取最匹配结果）
#   - 整数   => 直接当作 TMDB 剧集 ID（更精确，推荐）
TRACKED_SHOWS: List[Any] = [
    "剑来",
    # "繁花",
    # 12345,        # 直接写 TMDB ID 示例
]

MAX_RECENT_SEASONS = 3        # 每部剧每次最多回看最近几季（长剧省请求）
TOPIC_TAG = "#追剧更新"        # 推送消息末尾附带的话题标签
SEND_INTERVAL = 3.0           # 每两条推送之间的间隔（秒），避开 Telegram 限流
MAX_SEND_RETRY = 5            # 撞上 429 时最多重试次数


class Notifier:
    """推送适配：优先脚本自带 Telegram 凭据，否则回退到项目统一推送层。"""

    def __init__(self, notify_config: Optional[dict] = None):
        config = notify_config or {}
        self.bot_token = (config.get('bot_token') or '').strip()
        self.chat_id = str(config.get('chat_id') or '').strip()
        self.api_host = (config.get('api_host') or '').strip()
        self.proxy = (config.get('proxy') or '').strip()
        self.timeout = 20

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, text: str) -> bool:
        if self.enabled:
            return self._send_telegram(text)
        return self._send_via_unified(text)

    def _send_telegram(self, text: str) -> bool:
        host = self.api_host or 'api.telegram.org'
        url = f"https://{host}/bot{self.bot_token}/sendMessage"
        payload = {
            'chat_id': self.chat_id,
            'text': text,
            'disable_web_page_preview': True,
        }
        proxies = {'https': self.proxy, 'http': self.proxy} if self.proxy else None

        for attempt in range(MAX_SEND_RETRY + 1):
            try:
                response = requests.post(url, json=payload, timeout=self.timeout,
                                         proxies=proxies)
                data = response.json()
            except Exception as e:
                logger.error(f"❌ Telegram 推送异常: {e}")
                return False

            if data.get('ok'):
                return True

            retry_after = (data.get('parameters') or {}).get('retry_after')
            if data.get('error_code') == 429 and retry_after and attempt < MAX_SEND_RETRY:
                wait = float(retry_after) + 1
                logger.warning(f"⚠️ Telegram 限流，{wait:.0f}s 后重试（第 {attempt + 1} 次）")
                time.sleep(wait)
                continue

            logger.error(f"❌ Telegram 推送失败: {data.get('description')}")
            return False
        return False

    def _send_via_unified(self, text: str) -> bool:
        try:
            from notification import send_notification
        except ImportError as e:
            logger.error(f"❌ 未配置 Telegram bot_token / chat_id，统一推送层也不可用: {e}")
            return False

        title, _, content = text.partition('\n')
        if not bool(send_notification(title, content)):
            logger.error("❌ 通知未送达：既没配 Telegram，统一推送层也没有启用任何渠道")
            return False
        return True


class EpisodeTracker:
    """编排：读配置 → 拉列表 → 取详情 → 判定 → 写进度 → 推送"""

    def __init__(self, config_path: Path = None, state_path: Path = None):
        self.config_path = Path(config_path or DEFAULT_CONFIG_PATH)
        self.state_path = Path(state_path or DEFAULT_STATE_PATH)
        self.config: Dict[str, Any] = {}
        self.options: Dict[str, Any] = {
            'language': TMDB_LANG,
            'list_type': 'watchlist',
            'notify_when_empty': False,
        }
        self.state: Dict[str, Any] = {}
        self.tracked: Dict[str, Any] = {}
        self.access_token = ''
        self.api_key = ''
        self.account_id = ''
        self.notifier = Notifier()
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

        self.access_token = (self.config.get('access_token') or '').strip()
        self.api_key = (self.config.get('api_key') or '').strip()
        if not self.access_token and not self.api_key:
            raise ValueError("tmdb 节点缺少 access_token / api_key")

        self.account_id = str(self.config.get('account_id') or '')
        self.notifier = Notifier(self.config.get('notify'))

    # ---------------- 进度 ----------------

    def load_state(self) -> None:
        if not self.state_path.exists():
            self.state = {}
            self.tracked = {}
            return
        try:
            with open(self.state_path, 'r', encoding='utf-8') as f:
                self.state = json.load(f) or {}
        except Exception:
            logger.warning(f"⚠️ 进度文件读取失败，按空进度处理: {self.state_path}")
            self.state = {}
        self.tracked = self.state.get('shows', self.state) or {}

    def save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {'version': 1, 'updated_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
                   'shows': self.tracked}
        tmp = self.state_path.with_suffix('.json.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.state_path)

    def reset(self) -> None:
        self.tracked = {}
        if self.state_path.exists():
            self.state_path.unlink()
        logger.info("进度已清空，下次跑会重新初始化")

    # ---------------- TMDB ----------------

    def _tmdb_get(self, path: str, params: Optional[dict] = None) -> dict:
        params = dict(params or {})
        params['language'] = self.options['language']
        headers = {"Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        else:
            params['api_key'] = self.api_key
        resp = requests.get(TMDB_BASE + path, params=params, headers=headers, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def search_show(self, query: str) -> Optional[Tuple[int, str]]:
        data = self._tmdb_get("/search/tv", {"query": query, "include_adult": "false"})
        results = data.get("results", [])
        if not results:
            return None
        top = results[0]
        return top["id"], top.get("name") or top.get("original_name")

    def get_account_id(self) -> str:
        if self.account_id:
            return self.account_id
        if not self.access_token:
            return ''
        account = self._tmdb_get("/account")
        self.account_id = str(account.get("id") or '')
        logger.info(f"自动获取 account_id = {self.account_id}")
        return self.account_id

    def get_watchlist_tv(self) -> List[Tuple[int, str]]:
        account_id = self.get_account_id()
        if not account_id:
            raise ValueError("watchlist 模式需要 access_token 或 account_id")
        shows, page, total = [], 1, 1
        while page <= total:
            data = self._tmdb_get(f"/account/{account_id}/watchlist/tv", {
                "page": page,
                "sort_by": "created_at.asc",
            })
            for s in data.get("results", []):
                shows.append((s["id"], s.get("name") or s.get("original_name")))
            total = data.get("total_pages", 1)
            page += 1
        return shows

    def get_show(self, show_id: int) -> dict:
        return self._tmdb_get(f"/tv/{show_id}")

    def get_season(self, show_id: int, season_num: int) -> dict:
        return self._tmdb_get(f"/tv/{show_id}/season/{season_num}")

    def resolve_tracked_shows(self) -> Tuple[List[Tuple[int, str]], bool]:
        """
        返回 ([(tmdb_id, name), ...], used_watchlist)。
        优先用 TMDB 在看列表；未配置令牌或拉取失败时回退到 TRACKED_SHOWS。
        """
        if self.access_token:
            try:
                logger.info("[*] 来源：TMDB 在看列表")
                wl = self.get_watchlist_tv()
                if not wl:
                    logger.info("    （在看列表为空，无剧集可跟踪）")
                return wl, True
            except Exception as e:
                logger.warning(f"  [!] 拉取 TMDB 在看列表失败：{e}")
                logger.warning("    回退到 TRACKED_SHOWS 配置")

        result: List[Tuple[int, str]] = []
        for entry in TRACKED_SHOWS:
            if isinstance(entry, int):
                result.append((entry, ''))
                continue
            try:
                res = self.search_show(entry)
            except Exception as e:
                logger.warning(f"[!] 搜索失败：{entry}（{e}）")
                continue
            if res:
                result.append(res)
            else:
                logger.warning(f"[!] 未找到剧集：{entry}")
        return result, False

    # ---------------- 判定 ----------------

    def find_new_episodes(self, show_id: int, notified: set,
                          is_first_run: bool) -> Tuple[list, Optional[tuple]]:
        """
        找出该剧尚未通知、且已播出的新集。
        返回 (new_eps, latest_aired)：
          - new_eps:      [(season, episode, name, air_date), ...]
          - latest_aired: 首次运行时记录的“最新一集”，用于首次添加推送
        函数会就地更新 notified 集合（首次运行把历史已播集全部标记为已读）。
        """
        show = self.get_show(show_id)
        seasons = [s for s in show.get("seasons", []) if s.get("season_number", 0) > 0]
        seasons.sort(key=lambda s: s["season_number"])
        recent = seasons[-MAX_RECENT_SEASONS:]

        today = date.today()
        new_eps = []
        latest_aired = None

        for s in recent:
            sn = s["season_number"]
            try:
                season = self.get_season(show_id, sn)
            except Exception as e:
                logger.warning(f"    · 跳过第 {sn} 季（拉取失败）：{e}")
                continue
            for ep in season.get("episodes", []):
                en = ep.get("episode_number")
                air = ep.get("air_date")
                if not en or not air:
                    continue
                try:
                    air_date = date.fromisoformat(air)
                except ValueError:
                    continue
                if air_date > today:
                    continue
                key = f"S{sn}E{en}"
                if key in notified:
                    continue
                notified.add(key)
                if is_first_run:
                    cand = (sn, en, ep.get("name", ""), air)
                    if latest_aired is None or (sn, en) > (latest_aired[0], latest_aired[1]):
                        latest_aired = cand
                    continue
                new_eps.append((sn, en, ep.get("name", ""), air))

        new_eps.sort(key=lambda x: (x[0], x[1]))
        return new_eps, latest_aired

    # ---------------- 文案 ----------------

    @staticmethod
    def format_message(show_name: str, eps: list) -> str:
        lines = ["📺 追剧更新提醒", f"《{show_name}》更新啦！"]
        for sn, en, name, air in eps:
            lines.append(f"第 {sn} 季 第 {en} 集：{name}")
            lines.append(f"播出日期：{air}")
        lines.append(TOPIC_TAG)
        return "\n".join(lines)

    @staticmethod
    def format_first_add(show_name: str, ep: tuple) -> str:
        sn, en, name, air = ep
        return "\n".join([
            "🎬 新关注提醒",
            f"《{show_name}》已加入追剧跟踪",
            f"当前最新：第 {sn} 季 第 {en} 集：{name}",
            f"播出日期：{air}",
            TOPIC_TAG,
        ])

    # ---------------- 主流程 ----------------

    def run(self, dry_run: bool = False) -> int:
        logger.info(f"== 追剧更新检查 {date.today()} {'[DRY-RUN]' if dry_run else ''} ==")
        changed = False

        tracked, used_watchlist = self.resolve_tracked_shows()
        current_ids = {str(sid) for sid, _ in tracked}

        # 在看列表模式下，清理已从列表移除的剧集的本地基线
        if used_watchlist and not dry_run:
            for old in list(self.tracked.keys()):
                if old not in current_ids:
                    logger.info(f"[*] 已从在看列表移除：{self.tracked[old].get('name', old)}，清理本地基线")
                    del self.tracked[old]
                    changed = True

        for show_id, show_name in tracked:
            if not show_name:
                try:
                    show = self.get_show(show_id)
                    show_name = show.get("name") or str(show_id)
                except Exception as e:
                    logger.warning(f"[!] 无法获取剧集信息：TMDB {show_id}（{e}）")
                    continue

            key = str(show_id)
            rec = self.tracked.get(key, {})
            notified = set(rec.get("notified", []))
            is_first_run = key not in self.tracked
            if is_first_run:
                logger.info(f"[*] 首次跟踪：{show_name} (TMDB {show_id})，建立基线中…")
            else:
                logger.info(f"[*] 检查：{show_name} (TMDB {show_id})")

            try:
                eps, first_add = self.find_new_episodes(show_id, notified, is_first_run)
            except Exception as e:
                logger.warning(f"  [!] 检查失败：{e}")
                continue

            if is_first_run:
                logger.info(f"    基线已建立，已记录 {len(notified)} 个已播出集。")
                if first_add:
                    text = self.format_first_add(show_name, first_add)
                else:
                    text = "\n".join([
                        "🎬 新关注提醒",
                        f"《{show_name}》已加入追剧跟踪",
                        "（暂未播出，后续更新会自动提醒）",
                    ])
                print(f"----- 首次添加待推送 -----\n{text}\n------------------------")
                if dry_run:
                    print("    [DRY-RUN] 未实际发送")
                else:
                    if self.notifier.send(text):
                        print("    ✓ 已推送首次添加提醒")
                    else:
                        print("    ❌ 推送失败")
                    time.sleep(SEND_INTERVAL)
                self.tracked[key] = {"name": show_name, "notified": sorted(notified)}
                changed = True
                continue

            if eps:
                text = self.format_message(show_name, eps)
                print(f"----- 待推送 -----\n{text}\n-----------------")
                if dry_run:
                    print("    [DRY-RUN] 未实际发送")
                else:
                    if self.notifier.send(text):
                        print("    ✓ 已推送到群组")
                    else:
                        print("    ❌ 推送失败")
                    time.sleep(SEND_INTERVAL)
                self.tracked[key] = {"name": show_name, "notified": sorted(notified)}
                changed = True
            else:
                logger.info("    暂无新更新")

        if not dry_run and changed:
            self.save_state()
            logger.info("== 状态已保存 ==")
        elif dry_run:
            logger.info("== DRY-RUN 结束，未修改状态 ==")
        else:
            logger.info("== 无变更 ==")
        return 0

    def list_shows(self) -> int:
        tracked, used_watchlist = self.resolve_tracked_shows()
        for show_id, show_name in tracked:
            print(f"{show_id:>8} | {show_name}")
        print(f"\n共 {len(tracked)} 部（来源：{'TMDB 在看列表' if used_watchlist else 'TRACKED_SHOWS'}）")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='TMDB 剧集更新追踪')
    parser.add_argument('--dry-run', action='store_true', help='只打印不推送')
    parser.add_argument('--reset', action='store_true', help='清空追踪进度后重新初始化')
    parser.add_argument('--list', action='store_true', help='只列出当前剧集来源')
    parser.add_argument('--config', help='配置文件路径')
    parser.add_argument('--state', help='进度文件路径')
    args = parser.parse_args()

    try:
        tracker = EpisodeTracker(config_path=args.config, state_path=args.state)
        if args.reset:
            tracker.reset()
        if args.list:
            return tracker.list_shows()
        return tracker.run(dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"执行异常: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
