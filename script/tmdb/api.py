#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TMDB API 封装

鉴权：
    支持两种方式，任选其一（access_token 优先）
    - access_token  v4 读访问令牌，走 Authorization: Bearer
    - api_key       v3 API 密钥，走 query 参数

账号数据：
    /account/{account_id}/watchlist/tv 实测**不需要 session_id**，
    只要令牌本身属于该账号即可读取。所以「在看列表」不用走 OAuth 授权流程。
"""

import logging
import threading
import time
from typing import Any, Dict, Iterator, List, Optional

import requests

logger = logging.getLogger(__name__)

CODE_SUCCESS = 0


class TMDBError(Exception):
    """TMDB 接口异常"""


class TMDBClient:
    """TMDB API 客户端（线程安全）"""

    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

    def __init__(self, api_key: str = None, access_token: str = None,
                 language: str = "zh-CN", timeout: int = 30, max_retries: int = 3):
        """
        Args:
            api_key: v3 API 密钥
            access_token: v4 读访问令牌（优先）
            language: 返回语言，中文用 zh-CN
            timeout: 单次请求超时秒数
            max_retries: 429 / 5xx 时的重试次数
        """
        if not access_token and not api_key:
            raise ValueError("必须提供 access_token 或 api_key 之一")

        self.api_key = api_key
        self.access_token = access_token
        self.language = language
        self.timeout = timeout
        self.max_retries = max_retries

        # 每个线程一个 Session，避免并发时互相干扰
        self._local = threading.local()

    @property
    def session(self) -> requests.Session:
        """获取当前线程的 Session"""
        session = getattr(self._local, 'session', None)
        if session is None:
            session = requests.Session()
            headers = {'accept': 'application/json'}
            if self.access_token:
                headers['Authorization'] = f'Bearer {self.access_token}'
            session.headers.update(headers)
            adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=8)
            session.mount('https://', adapter)
            self._local.session = session
        return session

    def _request(self, path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        发一次 GET 请求，带 429 / 5xx 重试

        Raises:
            TMDBError: 重试耗尽或返回非 JSON
        """
        params = dict(params or {})
        params.setdefault('language', self.language)
        if not self.access_token and self.api_key:
            params['api_key'] = self.api_key

        url = f"{self.BASE_URL}{path}"
        last_error = ''
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.exceptions.RequestException as e:
                last_error = f'请求异常: {e}'
                time.sleep(1 + attempt)
                continue

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as e:
                    raise TMDBError(f'响应不是 JSON: {e}')

            if response.status_code == 429 or response.status_code >= 500:
                # TMDB 限流时会给 Retry-After
                delay = float(response.headers.get('Retry-After') or 0) or (1 + attempt)
                last_error = f'HTTP {response.status_code}'
                logger.warning(f"⚠️ {path} {last_error}，{delay:.0f}s 后重试")
                time.sleep(delay)
                continue

            raise TMDBError(f'HTTP {response.status_code}: {response.text[:200]}')

        raise TMDBError(f'{path} 重试 {self.max_retries} 次仍失败：{last_error}')

    # ---------------- 账号 ----------------

    def get_account(self) -> Dict[str, Any]:
        """获取当前令牌所属账号信息（含 id）"""
        return self._request('/account')

    def get_watchlist_tv(self, account_id: str, page: int = 1,
                         sort_by: str = 'created_at.desc') -> Dict[str, Any]:
        """获取「在看」电视剧列表的单页数据"""
        return self._request(f'/account/{account_id}/watchlist/tv',
                             {'page': page, 'sort_by': sort_by})

    def iter_watchlist_tv(self, account_id: str, max_pages: int = 50) -> Iterator[Dict[str, Any]]:
        """翻页迭代「在看」列表里的每一部剧"""
        page = 1
        while page <= max_pages:
            data = self.get_watchlist_tv(account_id, page=page)
            for item in data.get('results') or []:
                yield item
            total_pages = int(data.get('total_pages') or 0)
            if page >= total_pages:
                break
            page += 1

    def get_list(self, list_id: str) -> Dict[str, Any]:
        """获取自定义列表（list_type=list 时用）"""
        return self._request(f'/list/{list_id}')

    # ---------------- 剧集 ----------------

    def get_tv_detail(self, series_id: int) -> Dict[str, Any]:
        """
        获取剧集详情，附带最近一集与下一集信息

        Returns:
            含 last_episode_to_air / next_episode_to_air / status / name 等字段
        """
        return self._request(
            f'/tv/{series_id}',
            {'append_to_response': 'next_episode_to_air,last_episode_to_air'},
        )
