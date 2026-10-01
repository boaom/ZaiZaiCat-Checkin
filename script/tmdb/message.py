#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推送文案

文案格式属于对外行为，改动前先确认是有意为之。
"""

from typing import Any, Dict


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


def format_init_message(show: Dict[str, Any], episode: Dict[str, Any]) -> str:
    """
    首次执行时给每部剧发的「已纳入追踪」卡片

    和更新卡片刻意用不同的抬头和标签，避免误以为是新集。
    """
    season = episode.get('season_number')
    number = episode.get('episode_number')
    title = f"第 {season} 季 第 {number} 集"
    episode_name = (episode.get('name') or '').strip()
    if episode_name:
        title += f"：{episode_name}"

    return '\n'.join([
        '📺 追剧追踪',
        f"《{show.get('name') or '未知剧集'}》已纳入追踪",
        title,
        f"播出日期：{episode.get('air_date') or '未知'}",
        '#追剧追踪',
    ])


def format_startup_message(tracked_count: int) -> str:
    """首次运行时告诉用户追踪已启动"""
    return (
        f"✅ 追剧追踪已启动\n"
        f"正在追踪 {tracked_count} 部剧集\n"
        f"有新集才推送"
    )


def format_empty_message() -> str:
    """notify_when_empty 打开且当天无更新时的兜底文案"""
    return "📺 追剧更新提醒\n今天没有剧集更新～"
