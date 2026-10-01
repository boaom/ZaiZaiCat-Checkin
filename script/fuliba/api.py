#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
福利吧API模块

封装福利吧 Discuz 签到插件(fx_checkin)的签到流程：

1. 用 Cookie 请求论坛首页，从登出链接中提取 formhash
   （formhash 只在登录态下才会渲染，因此它同时也是 Cookie 是否有效的判据）
2. 带 formhash 请求 plugin.php?id=fx_checkin:checkin
3. 解析 inajax 返回的 XML/CDATA，取出提示文案与弹窗类型
"""

import logging
import re
from typing import Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# Discuz 的 inajax 响应把真正的 HTML 包在 CDATA 里
_CDATA_RE = re.compile(r'<!\[CDATA\[(.*?)\]\]>', re.S)

# formhash 藏在登出链接里，只有登录态下才会渲染出来
_FORMHASH_RE = re.compile(
    r'member\.php\?mod=logging(?:&amp;|&)action=logout(?:&amp;|&)formhash=([0-9a-fA-F]+)'
)

# 提示信息的两种渲染方式
_DIALOG_RE = re.compile(r"showDialog\('([^']*)'\s*,\s*'([^']*)'")
_HANDLE_RE = re.compile(r"errorhandle_\w+\('([^']*)'")

# 已经签到过，视同成功
_ALREADY_HINTS = ('已经签到', '已签到', '今天已经', '您今天已')

# Cookie 失效时站点给出的提示
_AUTH_HINTS = ('请先登录', '需要登录', '请登录', '没有权限', '游客')


class FulibaAPI:
    """福利吧签到 API"""

    BASE_URL = 'https://www.wnflb2023.com'

    def __init__(
        self,
        cookies: str,
        formhash: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """
        Args:
            cookies: 浏览器 Cookie 字符串
            formhash: 可选，留空则每次运行时自动获取
            user_agent: 可选，建议与抓包时的浏览器保持一致
        """
        self.cookies = cookies
        self.formhash = (formhash or '').strip()
        self.user_agent = user_agent or (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/141.0.0.0 Safari/537.36'
        )

    def _headers(self, ajax: bool = False) -> Dict[str, str]:
        """构造请求头，ajax 请求与普通页面请求的 Accept 不同"""
        headers = {
            'User-Agent': self.user_agent,
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': f'{self.BASE_URL}/',
            'Cookie': self.cookies,
        }
        if ajax:
            headers['Accept'] = '*/*'
            headers['X-Requested-With'] = 'XMLHttpRequest'
        else:
            headers['Accept'] = (
                'text/html,application/xhtml+xml,application/xml;q=0.9,'
                'image/avif,image/webp,image/apng,*/*;q=0.8'
            )
        return headers

    def fetch_formhash(self) -> Optional[str]:
        """
        请求论坛首页并提取 formhash

        Returns:
            formhash 字符串；提取不到返回 None（通常意味着 Cookie 已失效）
        """
        try:
            response = requests.get(
                f'{self.BASE_URL}/',
                headers=self._headers(),
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"获取 formhash 失败: {e}")
            return None

        match = _FORMHASH_RE.search(response.text)
        return match.group(1) if match else None

    def _build_sign_url(self) -> str:
        # 站点自身生成的签到链接里 formhash 出现了两次，这里保持一致
        query = (
            f'formhash={self.formhash}&{self.formhash}'
            '&infloat=yes&handlekey=fx_checkin&inajax=1'
            '&ajaxtarget=fwin_content_fx_checkin'
        )
        return f'{self.BASE_URL}/plugin.php?id=fx_checkin:checkin&{query}'

    @staticmethod
    def _extract_message(text: str) -> Tuple[str, str]:
        """
        从 inajax 响应中取出提示文案与弹窗类型

        Returns:
            (提示文案, 弹窗类型)，解析不出时返回 ('', '')
        """
        cdata = _CDATA_RE.search(text)
        body = cdata.group(1) if cdata else text

        dialog = _DIALOG_RE.search(body)
        if dialog:
            return dialog.group(1), dialog.group(2)

        handle = _HANDLE_RE.search(body)
        if handle:
            return handle.group(1), ''

        return '', ''

    def sign_in(self) -> Dict:
        """
        执行签到

        Returns:
            {
                'success': bool,
                'result': dict,   # 成功时包含 message / already
                'error': str      # 失败时的错误信息
            }
        """
        logger.info("开始执行福利吧签到...")

        formhash = self.fetch_formhash()
        if formhash:
            self.formhash = formhash
        elif not self.formhash:
            error_msg = "Cookie 已失效：首页里找不到 formhash，请重新登录后更新 cookies"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
        else:
            logger.warning("未能刷新 formhash，回退使用配置中的值")

        try:
            response = requests.get(
                self._build_sign_url(),
                headers=self._headers(ajax=True),
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            error_msg = f"签到请求失败: {e}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}

        message, dialog_type = self._extract_message(response.text)
        if not message:
            logger.error(f"无法从响应中解析签到结果: {response.text[:200]}")
            return {'success': False, 'error': '响应解析失败，签到结果未知'}

        if any(hint in message for hint in _AUTH_HINTS):
            logger.error(f"福利吧签到失败: {message}")
            return {'success': False, 'error': message}

        already = any(hint in message for hint in _ALREADY_HINTS)
        success = already or dialog_type == 'right' or '签到成功' in message

        logger.info(f"福利吧签到结果: {message}")
        result = {
            'message': message,
            'already': already,
            'formhash': self.formhash,
        }
        if success:
            return {'success': True, 'result': result}
        return {'success': False, 'error': message, 'result': result}

    def get_user_info(self) -> Dict:
        """预留：获取用户信息"""
        return {}
