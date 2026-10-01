#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
吾爱破解论坛（52pojie.cn）API 模块

站点前置了网宿（WangSu）WAF：命中 `home.php?mod=task` 这类任务接口时，
返回的不是真实内容，而是一段 JS 挑战页。这里把挑战求解内置在请求层，
调用方（main.py）只需要关心「签到成功 / 今天已签 / 登录失效」。

挑战流程（逆向自抓包）：

1. 请求任务接口 → 拿到挑战页，页内以 JS 变量给出
   `wzwsquestion`（题干）、`wzwsfactor`（乘数）、`base64_chars`（乱序码表）、
   `dynamicapi`（校验接口，固定 `/waf_zw_verify`）
2. 按 `answer = 累加(2*(a+字符)) * factor + 累加(2*(序号+1))` 算出确认串
3. 把 `{fp_infos, answer, hostname, scheme}` 用**乱序码表**做 base64 编码，
   `POST` 到校验接口，服务端返回 `ok`
4. 重放原请求即通过

注意：校验请求必须带接近真实浏览器的 TLS 指纹，所以这里用 curl_cffi 而不是
requests —— 实测普通 requests 即使校验返回 `ok`，重放仍然会被拦截。
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover - 依赖缺失时给出明确提示
    curl_requests = None

logger = logging.getLogger(__name__)

BASE_URL = "https://www.52pojie.cn"
HOSTNAME = "www.52pojie.cn"

# 任务 ID：2 = 每日签到
DEFAULT_TASK_ID = 2

# 挑战页特征串（bytes，用于在响应体里做包含判断）
WAF_MARKER = b"wzws-waf-cgi"
WZWS_CONFIRM_PREFIX = "WZWS_CONFIRM_PREFIX_LABEL"
WZWS_VERIFY_API = "/waf_zw_verify"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/134.0.0.0 Safari/537.36"
)

# 已经签过 / 已领过，视同成功
_ALREADY_HINTS = (
    "已申请过",
    "已完成",
    "已领取",
    "下期再来",
    "已经领取",
    "已经申请",
    "不是进行中的任务",
)
# 领取成功
_SUCCESS_HINTS = ("恭喜", "领取成功", "获得")
# 登录态失效
_AUTH_HINTS = ("请先登录", "尚未登录", "您需要登录", "游客", "登录后才能")
# 明确失败
_FAIL_HINTS = ("尚未完成", "无法领取", "任务未完成", "不存在", "抱歉")

_FP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fp_infos.json")


def _extract_js_var(html: str, name: str) -> Optional[str]:
    """从挑战页里取出形如 `name = 'xxx'` 的 JS 变量"""
    match = re.search(r"%s\s*=\s*'([^']*)'" % re.escape(name), html)
    return match.group(1) if match else None


def wzws_answer(question: str, factor: str) -> str:
    """按网宿挑战算法计算 answer 确认串"""
    accumulated, index_sum = 0, 1
    for index, char in enumerate(question):
        accumulated = 2 * (accumulated + ord(char))
        index_sum = 2 * (index_sum + index + 1)
    return WZWS_CONFIRM_PREFIX + str(accumulated * int(factor) + index_sum)


def custom_b64_encode(data: str, chars: str) -> str:
    """用挑战页给出的乱序码表做 base64 编码"""
    output: List[str] = []
    index, length = 0, len(data)
    while index < length:
        byte0 = ord(data[index]) & 0xFF
        index += 1
        if index == length:
            output += [chars[byte0 >> 2], chars[(byte0 & 0x03) << 4], "=="]
            break
        byte1 = ord(data[index]) & 0xFF
        index += 1
        if index == length:
            output += [
                chars[byte0 >> 2],
                chars[((byte0 & 0x03) << 4) | ((byte1 & 0xF0) >> 4)],
                chars[(byte1 & 0x0F) << 2],
                "=",
            ]
            break
        byte2 = ord(data[index]) & 0xFF
        index += 1
        output += [
            chars[byte0 >> 2],
            chars[((byte0 & 0x03) << 4) | ((byte1 & 0xF0) >> 4)],
            chars[((byte1 & 0x0F) << 2) | ((byte2 & 0xC0) >> 6)],
            chars[byte2 & 0x3F],
        ]
    return "".join(output)


def custom_b64_decode(data: str, chars: str) -> str:
    """用挑战页给出的乱序码表做 base64 解码（抓包还原时用得上）"""
    table = {char: index for index, char in enumerate(chars)}
    bits, bit_count, output = 0, 0, bytearray()
    for char in data:
        if char == "=":
            break
        if char not in table:
            continue
        bits = (bits << 6) | table[char]
        bit_count += 6
        if bit_count >= 8:
            bit_count -= 8
            output.append((bits >> bit_count) & 0xFF)
    return output.decode("utf-8", "replace")


def _extract_alert(html: str) -> Tuple[str, str]:
    """
    从 Discuz 提示页里取出提示文案与提示类型

    Returns:
        (提示文案, 提示类型)，提示类型形如 alert_error / alert_info / alert_right
    """
    match = re.search(
        r'<div[^>]*class="(alert_\w+)"[^>]*>(.*?)</div>\s*</div>', html, re.S
    )
    if not match:
        match = re.search(r'<div[^>]*class="(alert_\w+)"[^>]*>(.*?)</div>', html, re.S)
    if not match:
        return "", ""

    alert_type, body = match.group(1), match.group(2)
    body = re.sub(r"<script.*?</script>", "", body, flags=re.S)
    body = re.sub(r"<[^>]+>", "", body)
    body = re.sub(r"\s+", " ", body).strip()
    # 去掉自动跳转的固定话术，只留业务提示
    for noise in ("如果您的浏览器没有自动跳转，请点击此链接", "如果您的浏览器没有自动跳转"):
        body = body.replace(noise, "")
    return body.strip(), alert_type


class PoJieAPI:
    """吾爱破解论坛 API"""

    BASE_URL = BASE_URL

    def __init__(
        self,
        cookie: str,
        user_agent: Optional[str] = None,
        task_id: int = DEFAULT_TASK_ID,
        timeout: int = 30,
    ):
        """
        Args:
            cookie: 登录后的 Cookie 字符串（wzws_* 会被自动剔除，交给挑战流程重新获取）
            user_agent: 建议与抓包时保持一致
            task_id: 每日签到任务 ID，默认 2
            timeout: 单次请求超时（秒）
        """
        if curl_requests is None:
            raise RuntimeError(
                "缺少依赖 curl_cffi，请先执行: pip install curl_cffi"
            )

        self.cookie = self._normalize_cookie(cookie)
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.task_id = task_id
        self.timeout = timeout

        # impersonate 负责 TLS 指纹，是绕过网宿校验的关键
        self.session = curl_requests.Session(impersonate="chrome")
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,image/apng,*/*;q=0.8"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Upgrade-Insecure-Requests": "1",
                "Cookie": self.cookie,
            }
        )

        self._fp_template: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------ 工具

    @staticmethod
    def _normalize_cookie(cookie: str) -> str:
        """剔除 wzws_* 这类由 WAF 下发的短时 Cookie，避免脏值干扰挑战流程"""
        items = []
        for raw in (cookie or "").replace("\n", " ").split(";"):
            item = raw.strip()
            if not item or "=" not in item:
                continue
            name = item.split("=", 1)[0].strip()
            if name.startswith("wzws_"):
                continue
            items.append(item)
        return "; ".join(items)

    @staticmethod
    def _decode(response) -> str:
        """按响应头声明的 charset 解码，Discuz 默认 GBK"""
        charset = "gbk"
        content_type = response.headers.get("content-type", "") or ""
        match = re.search(r"charset=([\w-]+)", content_type, re.I)
        if match:
            charset = match.group(1)
        try:
            return response.content.decode(charset, "replace")
        except LookupError:
            return response.content.decode("gbk", "replace")

    def _load_fingerprint(self) -> Dict[str, Any]:
        """读取浏览器指纹模板（抓包还原出来的），只刷新时间戳"""
        if self._fp_template is None:
            with open(_FP_FILE, "r", encoding="utf-8") as fp:
                self._fp_template = json.load(fp)

        fingerprint = json.loads(json.dumps(self._fp_template))
        date_time = fingerprint.setdefault("dateTime", {})
        date_time["timestamp"] = int(time.time() * 1000)
        return fingerprint

    # ------------------------------------------------------------------ WAF

    def _solve_waf(self, challenge: bytes, target_url: str) -> bool:
        """
        求解网宿 WAF 挑战

        Args:
            challenge: 挑战页原始字节
            target_url: 触发挑战的原始请求 URL（用作 Referer）

        Returns:
            bool: 是否校验通过
        """
        try:
            html = challenge.decode("utf-8", "replace")
            question = _extract_js_var(html, "wzwsquestion")
            factor = _extract_js_var(html, "wzwsfactor")
            chars = _extract_js_var(html, "base64_chars")
            verify_api = _extract_js_var(html, "dynamicapi") or WZWS_VERIFY_API

            if not (question and factor and chars):
                logger.warning("响应含 WAF 特征但缺少挑战变量（多半是被拦截的错误页）")
                return False

            payload = {
                "fp_infos": self._load_fingerprint(),
                "answer": wzws_answer(question, factor),
                "hostname": HOSTNAME,
                "scheme": "https",
            }
            body = custom_b64_encode(
                json.dumps(payload, separators=(",", ":"), ensure_ascii=False), chars
            )
            response = self.session.post(
                self.BASE_URL + verify_api,
                data=body,
                timeout=self.timeout,
                headers={
                    "Content-Type": "text/plain;charset=UTF-8",
                    "Referer": target_url,
                    "Origin": self.BASE_URL,
                },
            )
            passed = response.status_code == 200 and "ok" in response.text.lower()
            if not passed:
                logger.warning(
                    f"WAF 校验未通过: HTTP {response.status_code} {response.text[:60]!r}"
                )
            return passed

        except Exception as e:
            logger.error(f"WAF 挑战求解异常: {e}", exc_info=True)
            return False

    def _request(self, method: str, path: str, *, max_waf_retry: int = 2, **kwargs):
        """
        统一请求入口：命中挑战页则自动求解并重放

        Args:
            method: HTTP 方法
            path: 站内路径或完整 URL
            max_waf_retry: 挑战求解最大重试次数
        """
        url = path if path.startswith("http") else self.BASE_URL + path
        kwargs.setdefault("timeout", self.timeout)

        response = None
        for attempt in range(max_waf_retry + 1):
            response = self.session.request(method, url, **kwargs)
            if WAF_MARKER not in response.content:
                return response

            logger.info(f"命中网宿 WAF 挑战（第 {attempt + 1} 次）: {url}")
            if attempt >= max_waf_retry or not self._solve_waf(response.content, url):
                break
            time.sleep(1.2)

        return response

    # ------------------------------------------------------------------ 业务

    def _task_path(self, action: str) -> str:
        return f"/home.php?mod=task&do={action}&id={self.task_id}&referer=%2Findex.php"

    def check_login(self) -> Dict[str, Any]:
        """
        通过首页判断 Cookie 是否有效

        Returns:
            {'success': bool, 'username': str, 'credit': str, 'error': str}
        """
        response = self._request("GET", "/index.php")
        html = self._decode(response)

        match = re.search(
            r'<strong class="vwmy[^"]*">\s*<a[^>]*>([^<]+)</a>', html
        )
        if not match:
            return {
                "success": False,
                "error": "Cookie 已失效：首页未识别到登录状态，请重新登录后更新 cookie",
            }

        username = match.group(1).strip()
        credit_match = re.search(
            r'id="extcreditmenu"[^>]*>([^<]+)</a>', html
        )
        credit = credit_match.group(1).strip() if credit_match else ""

        logger.info(f"登录态正常：{username}{f'（{credit}）' if credit else ''}")
        return {"success": True, "username": username, "credit": credit}

    def _parse_task_page(self, html: str) -> Dict[str, Any]:
        """解析 Discuz 任务页提示，映射成统一状态"""
        message, alert_type = _extract_alert(html)
        logger.info(f"任务页提示[{alert_type or '未知'}]: {message or '(未解析到提示)'}")

        if any(hint in message for hint in _AUTH_HINTS):
            return {"success": False, "status": "login_invalid", "error": message or "登录态失效"}

        if any(hint in message for hint in _ALREADY_HINTS):
            text = f"今日已签到（{message}）" if message else "今日已签到"
            return {"success": True, "status": "already", "message": text}

        if alert_type == "alert_error" or any(hint in message for hint in _FAIL_HINTS):
            return {"success": False, "status": "failed", "error": message or "任务执行失败"}

        if any(hint in message for hint in _SUCCESS_HINTS) or alert_type in (
            "alert_right",
            "alert_info",
        ):
            return {"success": True, "status": "signed", "message": message or "签到成功"}

        return {"success": False, "status": "unknown", "error": message or "无法识别任务结果"}

    def sign_in(self) -> Dict[str, Any]:
        """
        执行每日签到（Discuz 任务：申请 → 自动跳转领取）

        Returns:
            {
                'success': bool,
                'result': {'status': str, 'message': str, 'username': str, 'credit': str},
                'error': str
            }
        """
        login = self.check_login()
        if not login.get("success"):
            return {"success": False, "error": login.get("error", "登录态失效")}

        username = login.get("username", "")
        credit = login.get("credit", "")

        logger.info("开始申请每日签到任务...")
        response = self._request("GET", self._task_path("apply"))
        html = self._decode(response)
        final_url = str(response.url)

        # 申请成功时 Discuz 会 302 到 do=draw，跟随后拿到的就是领取结果页
        if "do=draw" in final_url:
            outcome = self._parse_task_page(html)
        elif response.status_code != 200:
            outcome = {
                "success": False,
                "status": "failed",
                "error": f"申请任务返回 HTTP {response.status_code}",
            }
        else:
            outcome = self._parse_task_page(html)
            # 提示「已申请过」时，再补一次领取，避免出现「申请了但没领」的挂空状态
            if outcome.get("status") == "already":
                logger.info("任务本期已申请，尝试直接领取奖励...")
                draw_response = self._request("GET", self._task_path("draw"))
                draw_outcome = self._parse_task_page(self._decode(draw_response))
                # 只有真的领到奖励才覆盖申请页的提示，否则保留信息量更大的原文
                if draw_outcome.get("status") == "signed":
                    outcome = draw_outcome

        result = {
            "status": outcome.get("status", ""),
            "message": outcome.get("message") or outcome.get("error", ""),
            "username": username,
            "credit": credit,
        }
        outcome["result"] = result

        if outcome.get("success"):
            logger.info(f"签到结果: {result['message']}")
        else:
            logger.error(f"签到失败: {result['message']}")

        return outcome

    def get_user_info(self) -> Dict[str, Any]:
        """预留：获取用户信息"""
        return {}
