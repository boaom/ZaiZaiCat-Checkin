#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新判定

这里只做纯逻辑：给一批剧集列表和它们的详情，算出哪些剧集有更新、
以及新的进度长什么样。不碰网络、不碰文件，方便单测直接喂 fixture。

判定规则：
    只追踪**加入列表之后**发生的更新。第一次见到某部剧时只记录进度、不通知，
    避免刚把剧加进列表就收到一堆「更新啦」。
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

Show = Dict[str, Any]
Episode = Dict[str, Any]
Tracked = Dict[str, Any]

# 详情里代表「最近已播出的一集」的字段
LATEST_EPISODE_FIELD = 'last_episode_to_air'


def merge_show(show: Show, detail: Show) -> Show:
    """用详情里的中文名覆盖列表接口给的原名"""
    merged = dict(show)
    merged['name'] = detail.get('name') or show.get('name')
    return merged


def extract_progress(episode: Episode) -> Optional[Dict[str, Any]]:
    """
    从 TMDB 的 episode 对象里取出进度标识

    Returns:
        {'season': int, 'episode': int, 'air_date': str}，信息不全时返回 None
    """
    air_date = episode.get('air_date')
    if not air_date or not episode.get('episode_number'):
        return None
    return {
        'season': episode.get('season_number'),
        'episode': episode.get('episode_number'),
        'air_date': air_date,
    }


def evaluate(shows: List[Show], details: Dict[int, Show], tracked: Tracked,
             today: str = None, now: str = None) -> Dict[str, Any]:
    """
    算出本次的更新与最新进度

    Args:
        shows: 剧集列表（列表接口返回的原始结构，至少含 id / name）
        details: {series_id: 详情}，缺失的剧集会被跳过
        tracked: 现有进度 {series_id: {...}}
        today: 当天日期 YYYY-MM-DD，默认取本机日期
        now: 写入 tracked_since / notified_at 的时间戳，默认取当前时间

    Returns:
        {
            'tracked': 新进度（不改动传入的 tracked）,
            'updates': [(show, episode), ...] 本次要通知的更新,
            'initialized': 本次新纳入追踪的剧集数,
            'initialized_shows': [(show, episode), ...] 本次新纳入的剧集，
                                 首次执行时用来给每部剧发一张卡片,
        }
    """
    today = today or date.today().isoformat()
    now = now or datetime.now().isoformat(timespec='seconds')

    new_tracked: Tracked = {key: dict(value) for key, value in tracked.items()}
    updates: List[Tuple[Show, Episode]] = []
    initialized_shows: List[Tuple[Show, Episode]] = []

    for show in shows:
        series_id = str(show.get('id') or '')
        if not series_id or not show.get('id'):
            continue

        detail = details.get(int(show['id']))
        if detail is None:
            continue

        merged = merge_show(show, detail)
        episode = detail.get(LATEST_EPISODE_FIELD) or {}
        current = extract_progress(episode)
        if current is None:
            continue

        known = new_tracked.get(series_id)

        if known is None:
            # 首次见到这部剧：只记录，不通知
            new_tracked[series_id] = {
                **current,
                'name': merged['name'],
                'tracked_since': now,
            }
            initialized_shows.append((merged, episode))
            continue

        if (known.get('season'), known.get('episode')) == (current['season'], current['episode']):
            continue

        # 进度变了，但这一集还没播出（TMDB 提前标了），先不动
        if current['air_date'] > today:
            continue

        updates.append((merged, episode))
        new_tracked[series_id] = {
            **current,
            'name': merged['name'],
            'notified_at': now,
        }

    return {
        'tracked': new_tracked,
        'updates': updates,
        'initialized': len(initialized_shows),
        'initialized_shows': initialized_shows,
    }
