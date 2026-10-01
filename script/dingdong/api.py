#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
叮咚买菜（ddxq.mobi）签到接口封装

抓包自 App 内嵌 H5 活动页 https://activity.m.ddxq.mobi/

鉴权说明：
    接口只用 Cookie 里的 DDXQSESSID 做会话鉴权，**没有签名、没有加密参数**。
    body 里的 uid / station_id / 经纬度等只是客户端元数据，实测全部省略也能签到成功
    （空 body 同样返回 code=0），这里按配置可选携带，尽量贴近真实客户端。

接口：
    签到状态  GET  https://maicai.api.ddxq.mobi/point/home
    执行签到  POST https://sunquan.api.ddxq.mobi/api/v2/user/signin/

返回码：
    0     成功
    1111  登录态失效（访问已过期，请重新登录）
    500   操作频繁（触发限流）
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

CODE_SUCCESS = 0
CODE_NOT_LOGIN = 1111
CODE_TOO_FREQUENT = 500

# 签到 body 里的固定部分
BASE_BODY = {
    'api_version': '9.7.3',
    'app_client_id': '2',
    'app_version': '2.105.1',
    'app_client_name': 'activity',
}

# 可从配置透传到 body / query 的元数据字段
META_FIELDS = (
    'station_id', 'native_version', 'city_name', 'city_number', 'uid',
    'latitude', 'longitude', 'device_token', 'device_id', 'os_version',
)


class DingdongAPI:
    """叮咚买菜 API 客户端"""

    BASE_URL = "https://sunquan.api.ddxq.mobi"
    SIGN_IN_URL = f"{BASE_URL}/api/v2/user/signin/"
    POINT_HOME_URL = "https://maicai.api.ddxq.mobi/point/home"
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Linux; Android 13; 23013RK75C Build/TKQ1.220905.001; wv) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/153.0.8010.39 "
        "Mobile Safari/537.36 xzone/13.10.2"
    )

    def __init__(self, cookies: str, meta: Optional[Dict[str, Any]] = None,
                 user_agent: Optional[str] = None):
        """
        初始化客户端

        Args:
            cookies: Cookie 字符串，至少包含 DDXQSESSID
            meta: 可选元数据（uid / station_id / 经纬度 等），会带进请求
            user_agent: 可选自定义 UA
        """
        self.cookies = cookies
        self.meta = {k: v for k, v in (meta or {}).items() if k in META_FIELDS and v not in (None, '')}
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.user_agent,
            'Cookie': cookies,
            'Accept': '*/*',
            'Content-Type': 'application/json',
            'Origin': 'https://activity.m.ddxq.mobi',
            'Referer': 'https://activity.m.ddxq.mobi/',
            'X-Requested-With': 'com.yaya.zone',
        })

    def close(self) -> None:
        """关闭会话"""
        self.session.close()

    def _body(self) -> Dict[str, Any]:
        """组装签到请求体：固定字段 + 配置里的元数据"""
        body = dict(BASE_BODY)
        body.update(self.meta)
        return body

    def _query(self) -> Dict[str, Any]:
        """组装状态查询的 query 参数"""
        query = {
            'api_version': BASE_BODY['api_version'],
            'app_client_id': '2',
            'app_version': BASE_BODY['app_version'],
            'app_client_name': 'activity',
        }
        query.update(self.meta)
        return query

    @staticmethod
    def _parse(response) -> Optional[Dict[str, Any]]:
        """解析响应，非 JSON 返回 None"""
        try:
            return response.json()
        except ValueError:
            logger.error(f"❌ 响应不是 JSON: {response.text[:200]}")
            return None

    def get_point_home(self) -> Optional[Dict[str, Any]]:
        """
        查询积分首页（含今日签到状态）

        Returns:
            data 字典，失败返回 None
        """
        logger.info("📌 正在查询签到状态...")
        try:
            response = self.session.get(self.POINT_HOME_URL, params=self._query(), timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 查询签到状态失败: {e}")
            return None

        data = self._parse(response)
        if data is None:
            return None
        if data.get('code') != CODE_SUCCESS:
            logger.error(f"❌ 查询签到状态失败: {data.get('msg')} (code={data.get('code')})")
            return None
        return data.get('data') or {}

    def get_today_status(self) -> Optional[Dict[str, Any]]:
        """
        获取今日签到状态

        Returns:
            {'signed': bool, 'sign_series': int, 'point_num': int, 'total_money': str}
            查询失败返回 None
        """
        data = self.get_point_home()
        if data is None:
            return None
        user_sign = data.get('user_sign') or {}
        return {
            'signed': bool(user_sign.get('is_today_sign')),
            'sign_series': user_sign.get('sign_series', 0),
            'point_num': data.get('point_num', 0),
            'point_money': data.get('point_money', ''),
            'total_money': user_sign.get('total_money', ''),
        }

    def sign_in(self) -> Dict[str, Any]:
        """
        执行签到

        Returns:
            {'success': bool, 'message': str, 'data': dict}
        """
        logger.info("📌 正在执行签到...")
        try:
            response = self.session.post(self.SIGN_IN_URL, json=self._body(), timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            return {'success': False, 'message': f'请求失败: {e}', 'data': {}}

        data = self._parse(response)
        if data is None:
            return {'success': False, 'message': '响应解析失败', 'data': {}}

        code = data.get('code')
        if code == CODE_SUCCESS:
            payload = data.get('data') or {}
            point = payload.get('point', 0)
            reward = payload.get('rewardPoint', 0)
            series = payload.get('sign_series', 0)
            message = f"签到成功，本期第 {series} 天"
            if point:
                message += f"，获得 {point} 积分"
            if reward:
                message += f"，额外奖励 {reward}"
            logger.info(f"✅ {message}")
            return {'success': True, 'message': message, 'data': payload}

        if code == CODE_NOT_LOGIN:
            message = data.get('msg') or '登录态失效，请重新登录'
            logger.error(f"❌ {message}")
            return {'success': False, 'message': message, 'data': data}

        if code == CODE_TOO_FREQUENT:
            message = data.get('msg') or '操作频繁'
            logger.warning(f"⚠️ {message}")
            return {'success': False, 'message': message, 'data': data}

        message = data.get('msg') or f"未知返回码 {code}"
        logger.error(f"❌ 签到失败: {message}")
        return {'success': False, 'message': message, 'data': data}


# ============================================================================
# 农场（鱼塘）接口 —— farm.api.ddxq.mobi
#
# 抓包自 App 内嵌 H5 https://game.m.ddxq.mobi/
# 鉴权同样只用 Cookie 里的 DDXQSESSID，无签名；请求头里的 ddmc-* 只是客户端元数据。
#
# 关键语义（实测）：
#   task/list 的 buttonStatus 是**缓存值**，不代表当前能否领奖，必须以 task/reward 的返回码为准：
#       0    领取成功
#       810  已领取过（幂等，可忽略）
#       811  奖励已过期（当天未领，次日作废）
#       820  不可领取
#   FINISHED / TO_RECEIVE / WAITING_REWARD 都值得试一把；TO_ACHIEVE 需要真实下单/浏览，脚本做不了。
# ============================================================================

FARM_BASE_URL = "https://farm.api.ddxq.mobi"
GW_BASE_URL = "https://gw.api.ddxq.mobi"

# 农场接口固定 query 参数
FARM_BASE_QUERY = {
    'api_version': '9.1.0',
    'app_client_id': '2',
    'app_version': '13.10.2',
    'OSVersion': '13',
    'CrossPlatform': 'GameM',
    'ClientType': 'Android',
    'game_version': '2',
    'gameId': '1',
}

CODE_ALREADY_REWARDED = 810
CODE_REWARD_EXPIRED = 811
CODE_NOT_REWARDABLE = 820
CODE_INVALID_PARAM = 119000010


class FarmAPI:
    """叮咚农场（鱼塘）客户端：任务领饲料 / 喂鱼 / 天天翻牌"""

    TASK_LIST_URL = f"{FARM_BASE_URL}/api/v2/task/list"
    TASK_ACHIEVE_URL = f"{FARM_BASE_URL}/api/v2/task/achieve"
    TASK_REWARD_URL = f"{FARM_BASE_URL}/api/v2/task/reward"
    PROPS_LIST_URL = f"{FARM_BASE_URL}/api/v2/props/list"
    PROPS_FEED_URL = f"{FARM_BASE_URL}/api/v2/props/feed"
    SEED_LIST_URL = f"{FARM_BASE_URL}/api/v2/seed/list"
    FRIEND_LIST_URL = f"{FARM_BASE_URL}/api/v2/friend/list"
    LUCKY_DRAW_INFO_URL = f"{FARM_BASE_URL}/api/v2/lucky-draw-activity/info"
    LUCKY_DRAW_DRAW_URL = f"{FARM_BASE_URL}/api/v2/lucky-draw-activity/draw"

    def __init__(self, cookies: str, meta: Optional[Dict[str, Any]] = None,
                 user_agent: Optional[str] = None):
        self.cookies = cookies
        self.meta = {k: v for k, v in (meta or {}).items() if v not in (None, '')}
        self.user_agent = user_agent or DingdongAPI.DEFAULT_USER_AGENT
        self.session = requests.Session()
        self.session.headers.update(self._headers())

    def _headers(self) -> Dict[str, str]:
        m = self.meta
        headers = {
            'User-Agent': self.user_agent,
            'Cookie': self.cookies,
            'Accept': '*/*',
            'Content-Type': 'application/json',
            'Origin': 'https://game.m.ddxq.mobi',
            'Referer': 'https://game.m.ddxq.mobi/',
            'X-Requested-With': 'com.yaya.zone',
        }
        passthrough = {
            'ddmc-longitude': 'longitude',
            'ddmc-latitude': 'latitude',
            'ddmc-os-version': 'os_version',
            'ddmc-device-id': 'device_id',
            'ddmc-station-id': 'station_id',
            'ddmc-city-number': 'city_number',
            'ddmc-device-token': 'device_token',
            'ddmc-app-client-id': lambda: '2',
            'ddmc-api-version': lambda: '9.1.0',
        }
        for header, source in passthrough.items():
            value = source() if callable(source) else m.get(source)
            if value not in (None, ''):
                headers[header] = str(value)
        return headers

    def close(self) -> None:
        self.session.close()

    def _query(self, **extra) -> Dict[str, Any]:
        """组装 query：固定参数 + 元数据 + 接口特有参数"""
        query = dict(FARM_BASE_QUERY)
        query['station_id'] = self.meta.get('station_id', '')
        query['stationId'] = self.meta.get('station_id', '')
        query['CityId'] = self.meta.get('city_number', '')
        query['city_number'] = self.meta.get('city_number', '')
        query['cityCode'] = self.meta.get('city_number', '')
        query['uid'] = self.meta.get('uid', '')
        query['DeviceId'] = self.meta.get('device_id', '')
        query['latitude'] = self.meta.get('latitude', '')
        query['longitude'] = self.meta.get('longitude', '')
        query['lat'] = self.meta.get('latitude', '')
        query['lng'] = self.meta.get('longitude', '')
        query['device_token'] = self.meta.get('device_token', '')
        query.update({k: v for k, v in extra.items() if v is not None})
        return {k: v for k, v in query.items() if v != ''}

    def _get(self, url: str, **extra) -> Optional[Dict[str, Any]]:
        """发 GET 请求，返回完整响应体；网络异常返回 None"""
        try:
            response = self.session.get(url, params=self._query(**extra), timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 请求失败 {url}: {e}")
            return None
        try:
            return response.json()
        except ValueError:
            logger.error(f"❌ 响应不是 JSON: {response.text[:200]}")
            return None

    # ---------------- 任务 ----------------

    def get_task_list(self) -> List[Dict[str, Any]]:
        """获取农场任务列表"""
        data = self._get(self.TASK_LIST_URL, inviteActivityType='INVITE_ASSIST')
        if not data or data.get('code') != CODE_SUCCESS:
            logger.warning(f"⚠️ 获取农场任务列表失败: {(data or {}).get('msg')}")
            return []
        return (data.get('data') or {}).get('userTasks') or []

    def achieve_task(self, task_code: str) -> Dict[str, Any]:
        """
        标记农场任务已完成（app 端在用户浏览/下单后调这个）

        实测只有浏览类任务可手动完成：
            601  今日已完成
            850  此任务不可手动完成（下单/邀请类）
            1127 任务不允许完成
        服务端是否校验浏览时长未知，需要观察次日运行结果。
        """
        data = self._get(self.TASK_ACHIEVE_URL, taskCode=task_code,
                         env='PE', api_version='11.30.1', app_client_id='3')
        if data is None:
            return {'success': False, 'message': '请求失败'}
        return {
            'success': data.get('code') == CODE_SUCCESS,
            'code': data.get('code'),
            'message': data.get('msg') or '',
            'data': data.get('data') or {},
        }

    def claim_reward(self, user_task_log_id: str) -> Dict[str, Any]:
        """
        领取任务奖励

        Returns:
            {'success': bool, 'code': int, 'message': str, 'amount': int}
        """
        data = self._get(self.TASK_REWARD_URL, userTaskLogId=user_task_log_id)
        if data is None:
            return {'success': False, 'code': None, 'message': '请求失败', 'amount': 0}

        code = data.get('code')
        if code == CODE_SUCCESS:
            payload = data.get('data') or {}
            amount = sum(int(r.get('amount') or 0) for r in (payload.get('rewards') or []))
            return {'success': True, 'code': code, 'message': '领取成功', 'amount': amount,
                    'feed': (payload.get('feed') or {}).get('amount')}

        if code == CODE_ALREADY_REWARDED:
            return {'success': False, 'code': code, 'message': '已领取过', 'amount': 0}
        if code == CODE_REWARD_EXPIRED:
            return {'success': False, 'code': code, 'message': '奖励已过期', 'amount': 0}
        return {'success': False, 'code': code, 'message': data.get('msg') or f'返回码 {code}', 'amount': 0}

    def claim_all_rewards(self, sleep_seconds: float = 2.5) -> Dict[str, Any]:
        """
        遍历任务列表，把带 userTaskLogId 的任务奖励全部领一遍

        Returns:
            {'claimed': int, 'feed': int, 'details': List[str]}
        """
        tasks = self.get_task_list()
        claimed = 0
        total_feed = 0
        details: List[str] = []

        for task in tasks:
            log_id = task.get('userTaskLogId')
            if not log_id:
                continue
            name = task.get('taskName') or task.get('taskCode')
            result = self.claim_reward(log_id)
            if result['success']:
                claimed += 1
                total_feed += result['amount']
                details.append(f"✅ {name} +{result['amount']}g饲料")
                logger.info(f"✅ 农场领奖 [{name}] +{result['amount']}g饲料")
            elif result['code'] not in (CODE_ALREADY_REWARDED, CODE_REWARD_EXPIRED, CODE_NOT_REWARDABLE):
                details.append(f"⚠️ {name} {result['message']}")
                logger.warning(f"⚠️ 农场领奖 [{name}] {result['message']}")
            time.sleep(sleep_seconds)

        return {'claimed': claimed, 'feed': total_feed, 'details': details}

    # ---------------- 喂鱼 ----------------

    def get_feed_amount(self) -> int:
        """查询当前饲料存量（g）"""
        data = self._get(self.PROPS_LIST_URL)
        if not data or data.get('code') != CODE_SUCCESS:
            return 0
        for prop in ((data.get('data') or {}).get('props') or []):
            if prop.get('propsCode') == 'FEED':
                return int(prop.get('amount') or 0)
        return 0

    def get_seeds(self) -> List[Dict[str, Any]]:
        """获取鱼塘里的鱼苗列表"""
        data = self._get(self.SEED_LIST_URL)
        if not data or data.get('code') != CODE_SUCCESS:
            return []
        return (data.get('data') or {}).get('seeds') or []

    def feed(self, props_id: str = None, seed_id: str = None) -> Dict[str, Any]:
        """
        喂食（每次消耗 10g 饲料，需存量 ≥ 10g）

        不传 propsId/seedId 时自动从 props/list 与 seed/list 取第一个。
        """
        if not props_id:
            data = self._get(self.PROPS_LIST_URL)
            for prop in ((data or {}).get('data') or {}).get('props') or []:
                if prop.get('propsCode') == 'FEED':
                    props_id = prop.get('propsId')
                    break
        if not seed_id:
            seeds = self.get_seeds()
            if seeds:
                seed_id = seeds[0].get('seedId')
        if not props_id or not seed_id:
            return {'success': False, 'message': '缺少 propsId/seedId，无法喂食'}

        data = self._get(self.PROPS_FEED_URL, propsId=props_id, seedId=seed_id,
                         feedPro=0, triggerMultiFeed=1)
        if data is None:
            return {'success': False, 'message': '请求失败'}
        if data.get('code') == CODE_SUCCESS:
            payload = data.get('data') or {}
            seed = payload.get('seed') or {}
            return {
                'success': True,
                'message': payload.get('msg') or seed.get('msg') or '喂食成功',
                'feed': (payload.get('props') or {}).get('amount'),
                'level_exp': seed.get('levelExp'),
                'box_reward': payload.get('hardBoxRewardAmountAfterFeed'),
            }
        return {'success': False, 'message': data.get('msg') or f"返回码 {data.get('code')}"}

    # ---------------- 天天翻牌 ----------------

    def get_lucky_draw_info(self) -> Dict[str, Any]:
        """查询天天翻牌状态（canDraw / 饲料存量 / 奖品池）"""
        data = self._get(self.LUCKY_DRAW_INFO_URL, ldaId='45')
        if not data or data.get('code') != CODE_SUCCESS:
            return {}
        return data.get('data') or {}

    def draw(self) -> Dict[str, Any]:
        """
        天天翻牌抽一次（消耗 5g 饲料）

        注意：这是净消耗行为，期望收益为负，默认不自动执行，仅在配置开启时调用。
        """
        data = self._get(self.LUCKY_DRAW_DRAW_URL, ldaId='45')
        if data is None:
            return {'success': False, 'message': '请求失败'}
        if data.get('code') == CODE_SUCCESS:
            payload = data.get('data') or {}
            chosen = payload.get('chosen') or {}
            return {'success': True, 'name': chosen.get('name'),
                    'amount': chosen.get('amount'), 'reward_type': chosen.get('rewardType')}
        return {'success': False, 'message': data.get('msg') or f"返回码 {data.get('code')}"}


# ============================================================================
# 积分任务接口 —— gw.api.ddxq.mobi/promomission-service
#
# 抓包自 App 内嵌 H5 https://activity.m.ddxq.mobi/#/points
# 流程：searchUnCompleteMissionByUserId 列未完成任务
#      -> createUserMission 领取任务
#      -> notice 上报完成（seconds 需 ≥ 任务要求秒数）-> 发积分
#
# 注意 createUserMission 的 body 字段名叫 missionId，但实际要传列表里的 `id`
# （列表里另有真正的 missionId 字段，传错会报参数无效）。
# ============================================================================

class MissionAPI:
    """叮咚积分任务客户端（浏览类任务可全自动完成）"""

    LIST_URL = f"{GW_BASE_URL}/promomission-service/mission/search/v1/searchUnCompleteMissionByUserId"
    CREATE_URL = f"{GW_BASE_URL}/promomission-service/mission/search/new/createUserMission"
    NOTICE_URL = f"{GW_BASE_URL}/promomission-service/mission/notice/v1/notice"

    # 积分页 H5 的 pageUuid，用于列任务；列表里任务自带 pageId 时优先用任务的
    DEFAULT_PAGE_UUID = 'ec0bef9c537a4574'

    def __init__(self, cookies: str, meta: Optional[Dict[str, Any]] = None,
                 user_agent: Optional[str] = None):
        self.cookies = cookies
        self.meta = {k: v for k, v in (meta or {}).items() if v not in (None, '')}
        self.user_agent = user_agent or DingdongAPI.DEFAULT_USER_AGENT
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.user_agent,
            'Cookie': cookies,
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'Origin': 'https://activity.m.ddxq.mobi',
            'Referer': 'https://activity.m.ddxq.mobi/',
            'X-Requested-With': 'com.yaya.zone',
        })

    def close(self) -> None:
        self.session.close()

    def _post(self, url: str, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            response = self.session.post(url, json=body, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 请求失败 {url}: {e}")
            return None
        try:
            return response.json()
        except ValueError:
            logger.error(f"❌ 响应不是 JSON: {response.text[:200]}")
            return None

    def _base_body(self) -> Dict[str, Any]:
        """11.30.1 / app_client_id=3 版请求体（列表与上报用）"""
        return {
            'latitude': self.meta.get('latitude', ''),
            'longitude': self.meta.get('longitude', ''),
            'env': 'PE',
            'station_id': self.meta.get('station_id', ''),
            'city_number': self.meta.get('city_number', ''),
            'api_version': '11.30.1',
            'app_client_id': 3,
            'native_version': self.meta.get('native_version', ''),
            'h5_source': '',
        }

    def _activity_body(self) -> Dict[str, Any]:
        """9.7.3 / app_client_name=activity 版请求体（领任务用）"""
        return {
            'api_version': '9.7.3',
            'app_client_id': '2',
            'app_version': '2.105.1',
            'app_client_name': 'activity',
            'station_id': self.meta.get('station_id', ''),
            'native_version': self.meta.get('native_version', ''),
            'city_name': self.meta.get('city_name', ''),
            'city_number': self.meta.get('city_number', ''),
            'uid': self.meta.get('uid', ''),
            'latitude': self.meta.get('latitude', ''),
            'longitude': self.meta.get('longitude', ''),
            'device_token': self.meta.get('device_token', ''),
            'device_id': self.meta.get('device_id', ''),
            'os_version': self.meta.get('os_version', ''),
        }

    def list_uncompleted(self, page_uuid: str = None) -> List[Dict[str, Any]]:
        """列出未完成的积分任务"""
        body = self._base_body()
        body.update({'page_type': 2, 'pageUuid': page_uuid or self.DEFAULT_PAGE_UUID})
        data = self._post(self.LIST_URL, body)
        if not data or data.get('code') != CODE_SUCCESS:
            logger.warning(f"⚠️ 获取积分任务列表失败: {(data or {}).get('msg')}")
            return []
        return data.get('data') or []

    def create_mission(self, mission_id: Any) -> Dict[str, Any]:
        """领取任务（传列表项的 id 字段）"""
        body = self._activity_body()
        body['missionId'] = mission_id
        data = self._post(self.CREATE_URL, body)
        if data is None:
            return {'success': False, 'message': '请求失败'}
        return {'success': data.get('code') == CODE_SUCCESS,
                'message': data.get('data') or data.get('msg') or ''}

    def notice(self, mission: Dict[str, Any]) -> Dict[str, Any]:
        """上报任务完成（浏览类任务靠这个发奖）"""
        body = self._base_body()
        body.update({
            'page_type': 2,
            'pageUuid': mission.get('pageId') or self.DEFAULT_PAGE_UUID,
            'pageId': mission.get('pageId'),
            'seconds': mission.get('seconds'),
            'missionType': mission.get('missionType'),
            'missionId': mission.get('id'),
            'cityCode': self.meta.get('city_number', ''),
            'serialNo': str(int(time.time() * 1000)),
        })
        data = self._post(self.NOTICE_URL, body)
        if data is None:
            return {'success': False, 'message': '请求失败'}
        return {'success': data.get('code') == CODE_SUCCESS,
                'message': data.get('msg') or ''}

    def run_browse_missions(self, sleep_seconds: float = 3.0) -> Dict[str, Any]:
        """
        自动完成所有浏览类（missionType=scan）任务

        Returns:
            {'done': int, 'details': List[str]}
        """
        missions = self.list_uncompleted()
        done = 0
        details: List[str] = []

        for mission in missions:
            if mission.get('missionType') != 'scan':
                continue
            title = mission.get('title') or mission.get('id')

            created = self.create_mission(mission.get('id'))
            if not created['success']:
                details.append(f"⚠️ {title} 领取失败: {created['message']}")
                logger.warning(f"⚠️ 积分任务 [{title}] 领取失败: {created['message']}")
                continue
            time.sleep(sleep_seconds)

            reported = self.notice(mission)
            if reported['success']:
                done += 1
                details.append(f"✅ {title}")
                logger.info(f"✅ 积分任务 [{title}] 已完成")
            else:
                details.append(f"⚠️ {title} 上报失败: {reported['message']}")
                logger.warning(f"⚠️ 积分任务 [{title}] 上报失败: {reported['message']}")
            time.sleep(sleep_seconds)

        return {'done': done, 'details': details}
