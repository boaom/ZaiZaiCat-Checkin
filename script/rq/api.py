#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RQ 跑步商（runningquotient.cn）签到接口封装

接口说明（抓包自 App 内嵌 H5 页面 /Minisite/SignIn/index.html）：

- 鉴权：仅需 Cookie 中的 PHPSESSID，无需签名、无需验证码
- 签到日历：POST /MiniApi/SignIn/get_sign_day_list/rand/<随机数>
- 执行签到：POST /MiniApi/SignIn/sign_in/rand/<随机数>

签到返回：
    成功     {"status": 1, "total_days": 197, "now_continuity_periods": 1, ...}
    已签到   {"status": 10009, "error": "今日已签到(2026-10-01 14:04:35)"}
"""

import json
import logging
import random
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

# 签到状态码
STATUS_SUCCESS = 1
STATUS_ALREADY_SIGNED = 10009


class RQAPI:
    """RQ 跑步商 API 客户端"""

    BASE_URL = "https://rq.runningquotient.cn"
    SIGN_IN_URL = f"{BASE_URL}/MiniApi/SignIn/sign_in"
    SIGN_DAY_LIST_URL = f"{BASE_URL}/MiniApi/SignIn/get_sign_day_list"
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Linux; Android 13; 23013RK75C Build/TKQ1.220905.001; wv) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/153.0.8010.39 "
        "Mobile Safari/537.36"
    )

    def __init__(self, cookies: str, user_agent: Optional[str] = None):
        """
        初始化客户端

        Args:
            cookies: Cookie 字符串，至少包含 PHPSESSID
            user_agent: 可选，自定义 UA
        """
        self.cookies = cookies
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.user_agent,
            'Cookie': cookies,
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': self.BASE_URL,
            'Referer': f'{self.BASE_URL}/Minisite/SignIn/index.html',
        })

    def close(self) -> None:
        """关闭会话"""
        self.session.close()

    def _post(self, url: str) -> Optional[Dict[str, Any]]:
        """
        发送 POST 请求（RQ 的接口在路径尾部带随机数防缓存）

        Args:
            url: 不含随机数的接口地址

        Returns:
            解析后的 JSON，失败返回 None
        """
        full_url = f"{url}/rand/{random.random()}"
        try:
            response = self.session.post(full_url, timeout=30)
            response.raise_for_status()
            # 注意：sign_in 返回的 Content-Type 是 text/html，但 body 是 JSON
            try:
                return response.json()
            except ValueError:
                return json.loads(response.text)
        except requests.exceptions.Timeout:
            logger.error(f"❌ 请求超时: {url}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 请求失败: {url} | 错误: {e}")
            return None
        except ValueError as e:
            logger.error(f"❌ JSON解析失败: {e}")
            return None

    def get_sign_day_list(self) -> Optional[Dict[str, Any]]:
        """
        获取签到日历（含今日签到状态）

        Returns:
            data 字典（含 list、total_number），失败返回 None
        """
        logger.info("📌 正在获取签到日历...")
        data = self._post(self.SIGN_DAY_LIST_URL)
        if not data or data.get('syscode') != 200:
            logger.error(f"❌ 获取签到日历失败: {data.get('sysmsg') if data else '无响应'}")
            return None
        return data.get('data') or {}

    def get_today_status(self) -> Optional[Dict[str, Any]]:
        """
        获取今日签到状态

        Returns:
            {'signed': bool, 'day_time': str, 'total_number': int}，失败返回 None
        """
        data = self.get_sign_day_list()
        if data is None:
            return None

        for item in data.get('list') or []:
            if item.get('is_today') == 1:
                return {
                    'signed': item.get('sign_status') == 1,
                    'day_time': item.get('day_time', ''),
                    'total_number': data.get('total_number', 0),
                }
        return {'signed': False, 'day_time': '', 'total_number': data.get('total_number', 0)}

    def sign_in(self) -> Dict[str, Any]:
        """
        执行签到

        Returns:
            {
                'success': bool,   # 是否签到成功（已签到也算成功）
                'already': bool,   # 是否本次之前就已签到
                'message': str,
                'data': dict       # 原始返回
            }
        """
        logger.info("📌 正在执行签到...")
        data = self._post(self.SIGN_IN_URL)

        if not data:
            return {'success': False, 'already': False, 'message': '请求失败，无响应', 'data': {}}

        status = data.get('status')

        if status == STATUS_SUCCESS:
            days = data.get('total_days', 0)
            continuity = data.get('now_continuity_periods', 0)
            gain = data.get('gain_amount', 0)
            message = f"签到成功，累计 {days} 天"
            if continuity:
                message += f"，本期连续 {continuity} 天"
            if gain:
                message += f"，获得 {gain}"
            logger.info(f"✅ {message}")
            return {'success': True, 'already': False, 'message': message, 'data': data}

        if status == STATUS_ALREADY_SIGNED:
            message = data.get('error') or '今日已签到'
            logger.info(f"🔁 {message}")
            return {'success': True, 'already': True, 'message': message, 'data': data}

        message = data.get('error') or data.get('sysmsg') or f"未知状态码 {status}"
        logger.error(f"❌ 签到失败: {message}")
        return {'success': False, 'already': False, 'message': message, 'data': data}
