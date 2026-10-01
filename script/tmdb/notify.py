#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推送适配

两条路：
    1. 脚本自己配了 bot_token + chat_id（config/token.json 的 tmdb.notify）
       → 直连 Telegram，原样发文本，历史行为不变
    2. 没配
       → 交给项目统一推送层 notification.py，走面板环境变量 / config/notification.json

统一推送层的渠道是否可用由它自己判断，这里只负责把结果收敛成 bool。
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class Notifier:
    """把一条文本消息送到 Telegram（或回退到统一推送层）"""

    def __init__(self, bot_token: str = '', chat_id: str = '',
                 api_host: str = '', proxy: str = '', timeout: int = 20):
        self.bot_token = bot_token or ''
        self.chat_id = str(chat_id) if chat_id else ''
        self.api_host = (api_host or '').strip()
        self.proxy = (proxy or '').strip()
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        """脚本自己带了 Telegram 配置"""
        return bool(self.bot_token and self.chat_id)

    def send(self, text: str) -> bool:
        """发送一条文本消息，返回是否成功"""
        if self.enabled:
            return self._send_telegram(text)
        return self._send_via_unified(text)

    def _send_telegram(self, text: str) -> bool:
        """直连 Telegram Bot API"""
        import requests

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

    def _send_via_unified(self, text: str) -> bool:
        """回退到项目统一推送层"""
        try:
            from notification import send_notification
        except ImportError as e:
            logger.error(f"❌ Telegram 未配置 bot_token / chat_id，统一推送层也不可用: {e}")
            return False

        title, _, content = text.partition('\n')
        if not bool(send_notification(title, content)):
            logger.error("❌ 通知未送达：既没配 Telegram，统一推送层也没有启用任何渠道")
            return False
        return True


def build_notifier(notify_config: Optional[dict] = None) -> Notifier:
    """从 token.json 的 tmdb.notify 节点构造 Notifier"""
    config = notify_config or {}
    return Notifier(
        bot_token=config.get('bot_token') or '',
        chat_id=config.get('chat_id') or '',
        api_host=config.get('api_host') or '',
        proxy=config.get('proxy') or '',
    )
