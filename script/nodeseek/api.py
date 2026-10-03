#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NodeSeek API 模块

封装 NodeSeek 的每日签到接口（`POST /api/attendance?random=true`）：

1. 带上浏览器完整 Cookie 请求签到接口
2. 解析 JSON 响应，取出提示文案与本次获得的鸡腿数
3. 区分 Cookie 失效（401）、Cloudflare 拦截（403 / 非 JSON 响应）、
   重复签到与签到成功

接口成功响应示例：

    {"success": true, "message": "今天的签到收益是2个鸡腿", "gain": 2}
"""

import json
import logging
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = 'https://www.nodeseek.com'
SIGN_URL = f'{BASE_URL}/api/attendance?random=true'

# 已经签到过，视同成功
_ALREADY_HINTS = ('已经签到', '已签到', '今天已经', '重复签到', '已领取')

# Cookie 失效时站点给出的提示
_AUTH_HINTS = ('未登录', '请先登录', '请登录', '登录已失效', '登录失效')

DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)


class NodeSeekAPI:
    """NodeSeek 签到 API"""

    def __init__(
        self,
        cookies: str,
        user_agent: Optional[str] = None,
        timeout: int = 15,
        proxy: Optional[str] = None,
    ):
        """
        Args:
            cookies: 浏览器完整 Cookie 字符串
            user_agent: 可选，建议与抓包时的浏览器保持一致
            timeout: 请求超时秒数
            proxy: 可选，HTTP(S) 代理，如 http://127.0.0.1:7890
        """
        self.cookies = (cookies or '').strip()
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.timeout = timeout
        self.proxy = (proxy or '').strip() or None

    @staticmethod
    def mask(cookies: str) -> str:
        """只保留尾部片段，避免日志泄漏完整凭据"""
        return f'***{cookies[-8:]}' if len(cookies) > 8 else '***'

    def _headers(self) -> Dict[str, str]:
        return {
            'Cookie': self.cookies,
            'Origin': BASE_URL,
            'Referer': f'{BASE_URL}/board',
            'User-Agent': self.user_agent,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }

    def sign_in(self) -> Dict:
        """
        执行签到

        Returns:
            {
                'success': bool,
                'result': dict,   # 成功时包含 message / gain / already
                'error': str      # 失败时的错误信息
            }
        """
        if not self.cookies:
            error_msg = 'cookies 为空，请检查配置'
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}

        # HTTP 头只能承载 latin-1，中文/全角字符会让 requests 直接抛异常
        try:
            self.cookies.encode('latin-1')
        except UnicodeEncodeError:
            error_msg = 'cookies 含非 ASCII 字符（疑似占位符或复制错误）'
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}

        logger.info(f"开始执行 NodeSeek 签到 {self.mask(self.cookies)}...")

        proxies = None
        if self.proxy:
            proxies = {'http': self.proxy, 'https': self.proxy}

        try:
            response = requests.post(
                SIGN_URL,
                headers=self._headers(),
                timeout=self.timeout,
                proxies=proxies,
            )
        except requests.RequestException as e:
            error_msg = f"签到请求失败: {e}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}

        if response.status_code == 401:
            error_msg = 'Cookie 已失效或未登录，请重新登录后更新 cookies'
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
        if response.status_code == 403:
            error_msg = '签到被拦截（403）：触发了 Cloudflare 盾或人机验证'
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
        if response.status_code != 200:
            error_msg = f"未知状态码 {response.status_code}: {response.text[:200]}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}

        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError):
            error_msg = '响应不是 JSON，疑似触发 Cloudflare 人机验证'
            logger.error(f"{error_msg}: {response.text[:200]}")
            return {'success': False, 'error': error_msg}

        message = data.get('message') or data.get('msg') or ''
        gain = data.get('gain')

        if data.get('success') is True or data.get('status') == 'success':
            detail = message or '签到成功'
            logger.info(f"NodeSeek 签到结果: {detail}")
            return {
                'success': True,
                'result': {'message': detail, 'gain': gain, 'already': False},
            }

        if any(hint in message for hint in _ALREADY_HINTS):
            logger.info(f"NodeSeek 签到结果: {message}")
            return {
                'success': True,
                'result': {'message': message, 'gain': gain, 'already': True},
            }

        if any(hint in message for hint in _AUTH_HINTS):
            logger.error(f"NodeSeek 签到失败: {message}")
            return {'success': False, 'error': message}

        error_msg = message or f"签到失败，响应: {data}"
        logger.error(f"NodeSeek 签到失败: {error_msg}")
        return {'success': False, 'error': error_msg}

