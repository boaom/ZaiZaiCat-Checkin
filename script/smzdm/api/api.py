"""
什么值得买API接口模块
功能：提供所有与什么值得买服务交互的API接口
版本：2.0
更新：优化日志输出、改进错误处理、统一代码规范
"""

import base64
import re
import requests
from typing import Dict, Optional, Any, List
import logging
import time
from io import BytesIO
from PIL import Image
from urllib.parse import unquote
from typing import Optional, Dict, Any
from .sign_calculator import calculate_sign_from_params,calculate_sign

# 获取logger实例（由main.py统一配置）
logger = logging.getLogger(__name__)


class SmzdmAPI:
    """什么值得买API类 - 封装所有API交互逻辑"""

    # ==================== 常量定义 ====================
    BASE_URL = "https://zhiyou.m.smzdm.com"
    TEST_URL = "https://test.m.smzdm.com"
    USER_API_URL = "https://user-api.smzdm.com"
    DEFAULT_USER_AGENT = "smzdm_android_V11.1.95 rv:1195 (Android13;zh)smzdmapp"
    CHECKIN_WEB_URL = "https://zhiyou.smzdm.com"
    WEB_USER_AGENT = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                      "Mobile/15E148 Safari/604.1")
    TEST_API_URL = "https://test-api.smzdm.com"
    ARTICLE_CDN_URL = "https://article-cdn.smzdm.com"
    DINGYUE_API_URL = "https://dingyue-api.smzdm.com"
    BAOLIAO_TASK_URL = "https://user-api.smzdm.com"

    def __init__(self, cookie: str, user_agent: str, setting: str):
        """
        初始化API客户端

        Args:
            cookie: 账号Cookie
            user_agent: 用户代理字符串
        """
        self.cookie = cookie
        self.user_agent = user_agent
        self.session = requests.Session()
        self._setup_headers()
        self.setting = setting
        logger.debug("API客户端初始化完成")

    def _setup_headers(self):
        """设置默认请求头"""
        self.session.headers.update({
            'User-Agent': f'Mozilla/5.0 (iPhone; CPU iPhone OS 15_8_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148/{self.user_agent}/wkwebview/jsbv_1.0.0',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh-Hans;q=0.9',
            'Origin': self.TEST_URL,
            'Referer': f'{self.TEST_URL}/',
            'Cookie': self.cookie
        })

    def _get_token_from_cookie(self) -> str:
        """
        从Cookie中提取token(sess字段)

        Returns:
            token字符串，提取失败返回空字符串
        """
        for item in self.cookie.split(';'):
            if 'sess=' in item:
                return unquote(item.split('sess=')[1].strip())
        logger.warning("未能从Cookie中提取token")
        return ""

    def _make_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        发送HTTP请求的通用方法

        Args:
            method: HTTP方法 (GET, POST等)
            url: 请求URL
            **kwargs: 其他请求参数

        Returns:
            响应的JSON数据，失败返回None
        """
        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
            response.raise_for_status()
            data = response.json()

            # 检查业务错误码
            error_code = data.get('error_code')
            if error_code not in [0, '0', None]:
                error_msg = data.get('error_msg', '未知错误')
                logger.error(f"❌ API返回错误: {error_msg} (错误码: {error_code})")
                return None

            return data
        except requests.exceptions.Timeout:
            logger.error(f"❌ 请求超时: {url}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 请求失败: {url} | 错误: {str(e)}")
            return None
        except ValueError as e:
            logger.error(f"❌ JSON解析失败: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"❌ 未知错误: {str(e)}")
            return None

    # ==================== 众测任务相关API ====================

    def get_activity_id(self, from_source: str = "zhongce") -> Optional[str]:
        """
        获取活动ID

        Args:
            from_source: 来源标识，默认为"zhongce"

        Returns:
            活动ID，失败返回None
        """
        url = f"{self.BASE_URL}/task/task/ajax_get_activity_id"
        params = {'from': from_source}

        logger.info("📌 正在获取活动ID...")
        data = self._make_request('GET', url, params=params)

        if data and 'data' in data and 'activity_id' in data['data']:
            activity_id = str(data['data']['activity_id'])
            logger.info(f"✅ 成功获取活动ID: {activity_id}")
            return activity_id

        logger.error("❌ 获取活动ID失败")
        return None

    def get_activity_info(self, activity_id: str) -> Optional[Dict[str, Any]]:
        """
        获取活动信息和任务列表

        Args:
            activity_id: 活动ID

        Returns:
            活动信息字典，失败返回None
        """
        url = f"{self.BASE_URL}/task/task/ajax_get_activity_info"
        params = {'activity_id': activity_id}

        logger.info(f"📌 正在获取活动信息 (activity_id={activity_id})...")
        data = self._make_request('GET', url, params=params)

        if data and 'data' in data:
            logger.info("✅ 成功获取活动信息")
            return data['data']

        logger.error("❌ 获取活动信息失败")
        return None




    def get_baoliao_task_list(self) -> Optional[Dict[str, Any]]:
        """
        获取爆料任务列表

        Args:

        Returns:
            爆料任务信息字典，失败返回None
        """
        url = f"{self.BAOLIAO_TASK_URL}/task/list_v2"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            "basic_v": "0",
            "f": "iphone",
            "get_total": "1",
            "limit": "100",
            "offset": "0",
            "point_type": "0",
            "source_from": "任务活动",
            "time": str(current_time),
            "v": "11.1.35",
            "weixin": "1",
            "zhuanzai_ab": "b"
        }

        # 计算签名
        sign = calculate_sign(params)
        params['sign'] = sign

        # 设置特殊的请求头，匹配curl命令中的User-Agent
        headers = {
            'User-Agent': 'smzdm 11.1.35 rv:167 (iPhone 6s; iOS 15.8.3; zh_CN)/iphone_smzdmapp/11.1.35',
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(current_time)[:15],  # 使用时间戳的前15位作为request_key
            'content-encoding': 'gzip',
            'accept-language': 'zh-Hans-CN;q=1',
            'Cookie': self.cookie
        }

        logger.info(f"📌 正在获取爆料任务列表")

        try:
            response = self.session.post(url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            # 检查业务错误码
            error_code = data.get('error_code')
            if error_code not in [0, '0', None]:
                error_msg = data.get('error_msg', '未知错误')
                logger.error(f"❌ 获取爆料任务列表失败: {error_msg} (错误码: {error_code})")
                return None

            if data and 'data' in data:
                logger.info("✅ 成功获取爆料任务列表")
                return data['data']
            else:
                logger.error("❌ 响应数据格式异常")
                return None

        except requests.exceptions.Timeout:
            logger.error("❌ 请求超时")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 请求失败: {str(e)}")
            return None
        except ValueError as e:
            logger.error(f"❌ JSON解析失败: {str(e)}")
            return None
    def get_task_list(self, activity_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        获取任务列表

        Args:
            activity_id: 活动ID

        Returns:
            任务列表，失败返回None
        """
        activity_info = self.get_activity_info(activity_id)
        # print(activity_info)
        if not activity_info:
            return None

        # 提取所有类型的任务列表
        task_lists = []
        activity_task = activity_info.get('activity_task', {})

        # 合并所有任务列表
        for task_type in ['default_list', 'accumulate_list', 'clock_list']:
            task_list = activity_task.get(task_type, [])
            if task_list:
                task_lists.extend(task_list)

        logger.info(f"✅ 获取到 {len(task_lists)} 个任务")
        return task_lists

    def get_user_energy_info(self) -> Optional[Dict[str, Any]]:
        """
        获取用户众测能量值信息

        Returns:
            用户能量值信息字典，失败返回None
        """
        url = f"{self.TEST_URL}/win_coupon/user_data"

        logger.info("📌 正在获取用户能量值信息...")

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == 0:
                logger.info("✅ 成功获取用户能量值信息")
                return data.get('data', {})
            else:
                logger.error(f"❌ 获取用户能量值信息失败: {data.get('error_msg', '未知错误')}")
                return None
        except Exception as e:
            logger.error(f"❌ 获取用户能量值信息请求失败: {str(e)}")
            return None

    # ==================== 任务执行相关API ====================

    def view_article_task(
        self,
        task_id: str,
        article_id: str,
        channel_id: int,
        task_event_type: str = "interactive.view.article"
    ) -> bool:
        """
        完成浏览文章任务

        Args:
            task_id: 任务ID
            article_id: 文章ID (字符串类型,如'a3re2odk')
            channel_id: 文章频道ID
            task_event_type: 任务事件类型

        Returns:
            是否成功
        """

        url = f"{self.USER_API_URL}/task/event_view_article_sync"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'article_id': str(article_id),
            'basic_v': '0',
            'channel_id': str(channel_id),
            'f': 'iphone',
            'task_event_type': task_event_type,
            'task_id': task_id,
            'time': str(current_time),
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }

        # 计算签名
        sign = calculate_sign_from_params(params)
        params['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip'
        })

        logger.info(f"正在完成浏览文章任务 (task_id={task_id}, article_id={article_id}, channel_id={channel_id})...")
        try:
            response = self.session.post(url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info(f"✅ 浏览文章任务完成成功")
                return True
            else:
                logger.error(f"❌ 浏览文章任务失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 浏览文章任务请求失败: {str(e)}")
            return False

    def get_article_channel_id(self, article_id: str) -> Optional[int]:
        """
        通过article_id获取文章的channel_id

        Args:
            article_id: 文章ID (字符串类型,如'a3re2odk')

        Returns:
            channel_id,失败返回None
        """
        # 构建URL
        url = f"{self.ARTICLE_CDN_URL}/preload/{article_id}/fiphone/v11_1_35/wx1/im0/hcae67e467x7q/h5cc7e8ebddb8f0f73.json"

        logger.info(f"📌 正在获取文章channel_id (article_id={article_id})...")

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                channel_id = data.get('data', {}).get('channel_id')
                if channel_id:
                    channel_id = int(channel_id)
                    logger.info(f"✅ 成功获取channel_id: {channel_id}")
                    return channel_id
                else:
                    logger.error(f"响应中没有找到channel_id")
                    return None
            else:
                logger.error(f"❌ 获取文章信息失败: {data.get('error_msg', '未知错误')}")
                return None
        except Exception as e:
            logger.error(f"❌ 获取文章channel_id请求失败: {str(e)}")
            return None

    def favorite_article_task(
        self,
        task_id: str,
        article_id: str
    ) -> bool:
        """
        完成收藏文章任务

        Args:
            task_id: 任务ID
            article_id: 文章ID (字符串类型,如'a3re2odk')

        Returns:
            是否成功
        """
        # 通过article_id获取channel_id
        channel_id = self.get_article_channel_id(article_id)
        if channel_id is None:
            logger.error(f"无法获取文章的channel_id，任务失败")
            return False

        url = f"{self.USER_API_URL}/favorites/create"

        # 获取token
        token = self._get_token_from_cookie()

        # 构建请求参数
        current_time = int(time.time() * 1000)


        params = {
            'basic_v': '0',
            'channel_id': str(channel_id),
            'f': 'iphone',
            'id': article_id,
            'time': str(current_time),
            'token': token,
            # 'touchstone_event': str(touchstone_event).replace("'", '"'),
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }

        # 计算签名
        sign = calculate_sign_from_params(params)
        params['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })

        logger.info(f"正在完成收藏文章任务 (task_id={task_id}, article_id={article_id}, channel_id={channel_id})...")

        try:
            response = self.session.post(url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info(f"✅ 收藏文章任务完成成功")
                return True
            else:
                logger.error(f"❌ 收藏文章任务失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 收藏文章任务请求失败: {str(e)}")
            return False

    def rating_article_task(
        self,
        task_id: str,
        article_id: str
    ) -> bool:
        """
        完成点赞文章任务

        Args:
            task_id: 任务ID
            article_id: 文章ID (字符串类型,如'a3re2odk')

        Returns:
            是否成功
        """
        # 通过article_id获取channel_id
        channel_id = self.get_article_channel_id(article_id)
        if channel_id is None:
            logger.error(f"无法获取文章的channel_id，任务失败")
            return False

        url = f"{self.USER_API_URL}/rating/like_create"

        # 获取token
        token = self._get_token_from_cookie()

        # 构建请求参数
        current_time = int(time.time() * 1000)

        # 构建touchstone_event (简化版本,只包含必要信息)
        # touchstone_event = {
        #     "event_value": {
        #         "cid": str(channel_id),
        #         "aid": article_id,
        #         "otype": "点赞"
        #     },
        #     "event_key": "点赞",
        #     "user_id":"1619566011"
        # }

        params = {
            'basic_v': '0',
            'channel_id': str(channel_id),
            'f': 'iphone',
            'id': article_id,
            'time': str(current_time),
            'token': token,
            # 'touchstone_event': str(touchstone_event).replace("'", '"'),
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }
        # params = {
        #     'basic_v': '0',
        #     'channel_id': '80',
        #     'f': 'iphone',
        #     'id': 'a8w3kkel',
        #     'sign': '',
        #     'time': '1760959472000',
        #     'token': 'BC-1UTFKA5S+nJM9aijvc+yVpLcJ7cOnZ38OMcDmaZ6OySZwECUqT91hrA7UE/SSDLFDV1OGBToh+xPIbmJ3HZuiuEbljtyEKDkSLCCkO0IjGQTnh7L9L1AVcFEaw==',
        #     'v': '11.1.35',
        #     'weixin': '1',
        #     'zhuanzai_ab': 'b',
        # }


        # 计算签名
        sign = calculate_sign_from_params(params)
        params['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })

        logger.info(f"正在完成点赞文章任务 (task_id={task_id}, article_id={article_id}, channel_id={channel_id})...")

        try:
            response = self.session.post(url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info(f"✅ 点赞文章任务完成成功")
                return True
            else:
                logger.error(f"❌ 点赞文章任务失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 点赞文章任务请求失败: {str(e)}")
            return False

    def share_probation_task(
        self,
        article_id: str,
        channel_id: str
    ) -> bool:
        """
        完成分享众测招募任务

        Args:
            article_id: 文章ID (众测商品ID)
            channel_id: 频道ID

        Returns:
            是否成功
        """
        url = f"{self.USER_API_URL}/share/callback"

        # 获取token
        token = self._get_token_from_cookie()

        # 构建请求参数
        current_time = int(time.time() * 1000)

        params = {
            'article_id': article_id,
            'basic_v': '0',
            'channel_id': channel_id,
            'f': 'iphone',
            'time': str(current_time),
            'token': token,
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }

        # 计算签名
        sign = calculate_sign_from_params(params)
        params['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })

        logger.info(f"正在完成分享众测招募任务 (article_id={article_id}, channel_id={channel_id})...")

        try:
            response = self.session.post(url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info(f"✅ 分享众测招募任务完成成功")
                return True
            else:
                logger.error(f"❌ 分享众测招募任务失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 分享众测招募任务请求失败: {str(e)}")
            return False

    def execute_share_task(self, task: Dict[str, Any]) -> bool:
        """
        执行分享众测招募任务

        Args:
            task: 任务信息字典

        Returns:
            是否成功
        """
        task_name = task.get('task_name', '未知任务')
        task_finished_num = task.get('task_finished_num', 0)
        task_even_num = task.get('task_even_num', 0)

        # 计算还需要分享的次数
        remaining_count = task_even_num - task_finished_num

        if remaining_count <= 0:
            logger.info(f"任务 [{task_name}] 已完成所有分享 ({task_finished_num}/{task_even_num})")
            return True

        logger.info(f"任务 [{task_name}] 需要分享 {remaining_count} 次 (已完成 {task_finished_num}/{task_even_num})")

        # 获取众测列表
        probation_list = self.get_probation_list()
        if not probation_list:
            logger.error("获取众测列表失败，无法完成分享任务")
            return False

        # 提取可分享的众测商品信息
        available_shares = []
        for item in probation_list:
            article_id = item.get('article_id', '')
            article_channel_id = item.get('article_channel_id', '')
            article_title = item.get('article_title', '未知商品')

            if article_id and article_channel_id:
                available_shares.append({
                    'article_id': article_id,
                    'channel_id': article_channel_id,
                    'title': article_title
                })

        if not available_shares:
            logger.warning("当前没有可分享的众测商品")
            return False

        logger.info(f"找到 {len(available_shares)} 个可分享的众测商品")

        # 开始分享
        success_count = 0
        for i, share_item in enumerate(available_shares):
            if success_count >= remaining_count:
                break

            logger.info(f"  [{i+1}] 分享众测商品: {share_item['title']}")

            # 执行分享
            if self.share_probation_task(share_item['article_id'], share_item['channel_id']):
                success_count += 1
                logger.info(f"    ✅ 分享成功 (进度: {success_count}/{remaining_count})")
            else:
                logger.info(f"    ❌ 分享失败")

            # 分享间隔
            if success_count < remaining_count:
                time.sleep(2)

        logger.info(f"分享任务完成，成功分享 {success_count} 次")
        return success_count > 0

    def receive_reward(self, task_id: str) -> bool:
        """
        领取任务奖励

        Args:
            task_id: 任务ID

        Returns:
            是否成功
        """
        url = f"{self.BASE_URL}/task/task/ajax_activity_task_receive"

        # 构建请求参数
        params = {
            'task_id': task_id
        }

        logger.info(f"正在领取任务奖励 (task_id={task_id})...")

        try:
            # 使用POST请求,表单编码
            headers = self.session.headers.copy()
            headers.update({
                'Content-Type': 'application/x-www-form-urlencoded'
            })

            response = self.session.post(url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == 0 or data.get('error_code') == '0':
                reward_info = data.get('data', {})
                logger.info(f"✅ 任务奖励领取成功! 奖励: {reward_info}")
                return True
            else:
                logger.error(f"❌ 领取任务奖励失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 领取任务奖励请求失败: {str(e)}")
            return False

    def receive_activity_reward(self, activity_id: str) -> bool:
        """
        领取活动阶段性奖励

        Args:
            activity_id: 活动ID

        Returns:
            是否成功
        """
        url = f"{self.USER_API_URL}/task/activity_receive"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'activity_id': activity_id,
            'basic_v': '0',
            'f': 'iphone',
            'time': str(current_time),
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }

        # 计算签名
        sign = calculate_sign_from_params(params)
        params['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })

        logger.info(f"正在领取活动阶段性奖励 (activity_id={activity_id})...")

        try:
            response = self.session.post(url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                reward_info = data.get('data', {})
                logger.info(f"✅ 活动阶段性奖励领取成功! 奖励: {reward_info}")
                return True
            else:
                logger.error(f"❌ 领取活动阶段性奖励失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 领取活动阶段性奖励请求失败: {str(e)}")
            return False

    # ==================== 每日签到相关API ====================

    def daily_checkin(self) -> Optional[Dict[str, Any]]:
        """
        每日签到

        说明：App 端 /checkin 接口要求客户端每次现算的 sk 参数（一次性，
        无法离线复现，复用旧值会返回 check Sign Fail），因此这里改用
        Web 端签到接口，仅依赖 Cookie。

        Returns:
            签到结果数据（字段已归一化为 App 端命名），失败返回 None
        """
        url = f"{self.CHECKIN_WEB_URL}/user/checkin/jsonp_checkin"

        headers = {
            'User-Agent': self.WEB_USER_AGENT,
            'Referer': f'{self.CHECKIN_WEB_URL}/user/',
            'Origin': self.CHECKIN_WEB_URL,
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        logger.info(f"📌 正在执行每日签到...")

        try:
            response = self.session.post(url, data={}, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') not in (0, '0'):
                logger.error(f"❌ 每日签到失败: {data.get('error_msg', '未知错误')}")
                return None

            raw = data.get('data') or {}
            add_point = self._to_int(raw.get('add_point'))
            checkin_data = {
                # 归一化为 App 端字段，保持上层展示逻辑不变
                'cpadd': add_point,
                'daily_num': self._to_int(raw.get('checkin_num')),
                'cpoints': self._to_int(raw.get('point')),
                'cexperience': self._to_int(raw.get('exp')),
                'cgold': self._to_int(raw.get('gold')),
                'cprestige': self._to_int(raw.get('prestige')),
                'rank': self._to_int(raw.get('rank')),
                'slogan': self._strip_html(raw.get('slogan', '')),
                # Web 端特有字段
                'cards': self._to_int(raw.get('cards')),
                'continue_checkin_days': self._to_int(raw.get('continue_checkin_days')),
            }

            if add_point > 0:
                logger.info(f"✅ 每日签到成功! +{add_point} 积分")
            else:
                logger.info(f"✅ 今日已签到（本次 +0 积分）")
            return checkin_data
        except Exception as e:
            logger.error(f"❌ 每日签到请求失败: {str(e)}")
            return None

    @staticmethod
    def _to_int(value) -> int:
        """把接口返回的字符串数字安全转为 int"""
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _strip_html(text: str) -> str:
        """去掉接口返回文案里的 HTML 标签"""
        return re.sub(r'<[^>]+>', '', str(text or '')).strip()

    def close(self):
        """关闭会话"""
        self.session.close()

    def get_probation_list(self, status: str = "progress", offset: int = 0) -> Optional[list]:
        """
        获取众测列表

        Args:
            status: 众测状态，默认为"progress"（进行中）
            offset: 偏移量，默认为0

        Returns:
            众测列表，失败返回None
        """
        url = f"{self.TEST_API_URL}/probation/list"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'basic_v': '0',
            'f': 'iphone',
            'offset': str(offset),
            'status': status,
            'time': str(current_time),
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }

        # 计算签名
        sign = calculate_sign_from_params(params)
        params['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })

        logger.info(f"📌 正在获取众测列表 (状态: {status}, 偏移量: {offset})...")

        try:
            response = self.session.post(url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                rows = data.get('data', {}).get('rows', [])
                logger.info(f"✅ 成功获取众测列表，共 {len(rows)} 个众测商品")
                return rows
            else:
                logger.error(f"❌ 获取众测列表失败: {data.get('error_msg', '未知错误')}")
                return None
        except Exception as e:
            logger.error(f"❌ 获取众测列表请求失败: {str(e)}")
            return None

    def submit_probation_apply(self, probation_id: str) -> bool:
        """
        提交众测申请

        Args:
            probation_id: 众测商品ID（对应众测列表中的article_id）

        Returns:
            是否成功
        """
        url = f"{self.TEST_API_URL}/probation/submit"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'attention_merchant': '0',
            'basic_v': '0',
            'f': 'iphone',
            'probation_id': probation_id,
            'remark_list': '["",""]',
            'time': str(current_time),
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }

        # 计算签名
        sign = calculate_sign_from_params(params)
        params['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })

        logger.info(f"正在提交众测申请 (probation_id={probation_id})...")

        try:
            response = self.session.post(url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info(f"✅ 众测申请提交成功")
                return True
            elif data.get('error_code') == '1':
                error_msg = data.get('error_msg', '')
                if '已经申请过' in error_msg:
                    logger.info(f"该众测商品已经申请过，跳过")
                    return False
                else:
                    logger.error(f"众测申请失败: {error_msg}")
                    return False
            else:
                logger.error(f"众测申请失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 众测申请请求失败: {str(e)}")
            return False

    def apply_zhongce_task(self, task: Dict[str, Any]) -> bool:
        """
        执行申请众测任务

        Args:
            task: 任务信息字典

        Returns:
            是否成功
        """
        task_name = task.get('task_name', '未知任务')
        task_finished_num = task.get('task_finished_num', 0)
        task_even_num = task.get('task_even_num', 0)

        # 计算还需要申请的次数
        remaining_count = task_even_num - task_finished_num

        if remaining_count <= 0:
            logger.info(f"任务 [{task_name}] 已完成所有申请 ({task_finished_num}/{task_even_num})")
            return True

        logger.info(f"任务 [{task_name}] 需要申请 {remaining_count} 次 (已完成 {task_finished_num}/{task_even_num})")

        # 获取众测列表
        probation_list = self.get_probation_list()
        if not probation_list:
            logger.error("获取众测列表失败，无法完成申请任务")
            return False

        # 过滤出可申请的众测商品
        available_probations = []
        for item in probation_list:
            article_probation = item.get('article_probation', {})
            product_status = article_probation.get('product_status', '')

            # product_status == "1" 表示可申请
            if product_status == '1':
                article_id = item.get('article_id', '')
                article_title = item.get('article_title', '未知商品')
                apply_num = article_probation.get('apply_num', '')
                product_num = article_probation.get('product_num', '')
                product_status_name = article_probation.get('product_status_name', '')

                available_probations.append({
                    'id': article_id,
                    'title': article_title,
                    'apply_num': apply_num,
                    'product_num': product_num,
                    'status_name': product_status_name
                })

        if not available_probations:
            logger.warning("当前没有可申请的众测商品")
            return False

        logger.info(f"找到 {len(available_probations)} 个可申请的众测商品")

        # 开始申请
        success_count = 0
        for i, probation in enumerate(available_probations):
            if success_count >= remaining_count:
                break

            logger.info(f"  [{i+1}] {probation['title']} - {probation['apply_num']} - {probation['status_name']}")

            # 提交申请
            if self.submit_probation_apply(probation['id']):
                success_count += 1
                logger.info(f"    ✅ 申请成功 (进度: {success_count}/{remaining_count})")
            else:
                logger.info(f"    ⏭️  跳过该商品")

            # 申请间隔
            if success_count < remaining_count:
                time.sleep(1)

        logger.info(f"众测申请任务完成，成功申请 {success_count} 次")
        return success_count > 0

    def get_interactive_task_list(
        self,
        point_type: int = 0,
        limit: int = 100,
        offset: int = 0,
        source_from: str = "任务活动"
    ) -> Optional[Dict[str, Any]]:
        """
        获取互动任务列表

        Args:
            point_type: 积分类型，默认为0
            limit: 每页数量，默认100
            offset: 偏移量，默认0
            source_from: 来源标识，默认"任务活动"

        Returns:
            任务列表数据，失败返回None
        """
        url = f"{self.USER_API_URL}/task/list_v2"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'basic_v': '0',
            'f': 'iphone',
            'get_total': '1',
            'limit': str(limit),
            'offset': str(offset),
            'point_type': str(point_type),
            'source_from': source_from,
            'time': str(current_time),
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }

        # 计算签名
        sign = calculate_sign_from_params(params)
        params['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })

        logger.info(f"📌 正在获取互动任务列表...")

        try:
            response = self.session.post(url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info(f"✅ 成功获取互动任务列表")
                return data.get('data', {})
            else:
                logger.error(f"❌ 获取互动任务列表失败: {data.get('error_msg', '未知错误')}")
                return None
        except Exception as e:
            logger.error(f"❌ 获取互动任务列表请求失败: {str(e)}")
            return None


    # ==================== 关注用户相关功能 ====================

    def get_follow_user_list(self, page: int = 1) -> Optional[Dict[str, Any]]:
        """
        获取被关注用户列表信息

        Args:
            page: 页码，默认为1

        Returns:
            用户列表数据，失败返回None
        """
        url = "https://dingyue-api.smzdm.com/tuijian/search_result"

        # 获取token
        token = self._get_token_from_cookie()

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'basic_v': '0',
            'f': 'iphone',
            'nav_id': '83',
            'page': str(page),
            'time': str(current_time),
            'type': 'user',
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }

        # 计算签名
        sign = calculate_sign_from_params(params)
        params['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })

        logger.info(f"📌 正在获取关注用户列表 (页码: {page})...")

        try:
            response = self.session.post(url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info("✅ 成功获取关注用户列表")
                return data.get('data', {})
            else:
                logger.error(f"❌ 获取关注用户列表失败: {data.get('error_msg', '未知错误')}")
                return None
        except Exception as e:
            logger.error(f"❌ 获取关注用户列表请求失败: {str(e)}")
            return None

    def follow_user(self, keyword: str, keyword_id: str) -> bool:
        """
        关注用户

        Args:
            keyword: 用户名称 (从用户列表中获取的article_title)
            keyword_id: 用户ID (从用户列表中获取的用户ID)

        Returns:
            是否成功
        """
        url = "https://dingyue-api.smzdm.com/dingyue/create"

        # 获取token
        token = self._get_token_from_cookie()

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'basic_v': '0',
            'f': 'iphone',
            'is_follow_activity_page': '1',
            'is_from_task': '1',
            'keyword': keyword,
            'keyword_id': keyword_id,
            'refer': 'iPhone/关注/达人/推荐/',
            'time': str(current_time),
            'token': token,
            'type': 'user',
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }

        # 计算签名
        sign = calculate_sign_from_params(params)
        params['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })

        logger.info(f"正在关注用户: {keyword} (ID: {keyword_id})...")

        try:
            response = self.session.post(url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info(f"✅ 关注用户成功: {keyword}")
                return True
            else:
                logger.error(f"❌ 关注用户失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 关注用户请求失败: {str(e)}")
            return False

    def unfollow_user(self, keyword: str, keyword_id: str) -> bool:
        """
        取消关注用户

        Args:
            keyword: 用户名称
            keyword_id: 用户ID

        Returns:
            是否成功
        """
        url = "https://dingyue-api.smzdm.com/dingyue/destroy"

        # 获取token
        token = self._get_token_from_cookie()

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'basic_v': '0',
            'f': 'iphone',
            'keyword': keyword,
            'keyword_id': keyword_id,
            'refer': 'iPhone/公共/我的兴趣管理/感兴趣/全部',
            'time': str(current_time),
            'token': token,
            'type': 'user',
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }

        # 计算签名
        sign = calculate_sign_from_params(params)
        params['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })

        logger.info(f"正在取消关注用户: {keyword} (ID: {keyword_id})...")

        try:
            response = self.session.post(url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info(f"✅ 取消关注用户成功: {keyword}")
                return True
            else:
                logger.error(f"❌ 取消关注用户失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 取消关注用户请求失败: {str(e)}")
            return False

    def execute_follow_task(self, max_follow_count: int = 5) -> Dict[str, int]:
        """
        执行关注任务（关注用户后立即取消关注）

        Args:
            max_follow_count: 最大关注用户数量，默认为5

        Returns:
            执行统计字典 {success: 成功数, fail: 失败数}
        """
        logger.info(f"开始执行关注任务，最大关注用户数: {max_follow_count}")

        success_count = 0
        fail_count = 0

        try:
            # 获取用户列表
            user_data = self.get_follow_user_list()
            if not user_data:
                logger.error("获取用户列表失败")
                return {'success': 0, 'fail': 1}

            # 解析用户列表
            rows = user_data.get('rows', [])
            if not rows:
                logger.warning("用户列表为空")
                return {'success': 0, 'fail': 1}

            logger.info(f"获取到 {len(rows)} 个用户")

            processed_count = 0
            for user_row in rows:
                if processed_count >= max_follow_count:
                    break

                # 提取用户信息
                article_title = user_row.get('article_title', '')
                # 从用户数据中提取用户ID，这里需要根据实际返回的数据结构调整
                user_id = user_row.get('keyword_id', '')

                if not article_title or not user_id:
                    logger.warning(f"用户信息不完整，跳过: {user_row}")
                    continue

                logger.info(f"  [{processed_count + 1}] 处理用户: {article_title}")

                # 执行关注
                if self.follow_user(article_title, user_id):
                    logger.info(f"    ✅ 关注成功")

                    # 等待一下再取消关注
                    time.sleep(2)

                    # 取消关注
                    if self.unfollow_user(article_title, user_id):
                        logger.info(f"    ✅ 取消关注成功")
                        success_count += 1
                    else:
                        logger.info(f"    ❌ 取消关注失败")
                        fail_count += 1
                else:
                    logger.info(f"    ❌ 关注失败")
                    fail_count += 1

                processed_count += 1

                # 处理间隔
                if processed_count < max_follow_count:
                    time.sleep(3)

            logger.info(f"关注任务执行完成: 成功 {success_count} 个, 失败 {fail_count} 个")
            return {'success': success_count, 'fail': fail_count}

        except Exception as e:
            logger.error(f"执行关注任务时发生错误: {str(e)}")
            return {'success': success_count, 'fail': fail_count + 1}





    # ==================== 爆料相关API ====================

    def check_repeat_baoliao(self, url: str) -> Optional[Dict[str, Any]]:
        """
        检查爆料链接是否重复

        Args:
            url: 要检查的商品链接URL

        Returns:
            检查结果字典，失败返回None
        """
        api_url = "https://app-api.smzdm.com/v2/baoliao/check_repeat"

        # 获取当前时间戳
        current_time = int(time.time() * 1000)

        # 构建请求参数
        params = {
            'basic_v': '0',
            'f': 'iphone',
            'pdd_token': '1086704855cd376d73bd5507c1926cf2',  # 从curl命令中提取的固定token
            'setting': self.setting,
            'time': str(current_time),
            'url': url,  # 用户传入的URL参数
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }

        # 计算签名
        sign = calculate_sign_from_params(params)
        params['sign'] = sign

        # 设置请求头，完全匹配curl命令
        headers = {
            'User-Agent': 'smzdm 11.1.35 rv:167 (iPhone 6s; iOS 15.8.3; zh_CN)/iphone_smzdmapp/11.1.35',
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'content-encoding': 'gzip',
            'accept-language': 'zh-Hans-CN;q=1',
            'Cookie': self.cookie
        }

        logger.info(f"📌 正在检查爆料链接是否重复: {url}")

        try:
            response = requests.post(
                api_url,
                data=params,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            # 检查业务错误码
            error_code = data.get('error_code')
            if error_code not in [0, '0', None]:
                error_msg = data.get('error_msg', '未知错误')
                logger.error(f"❌ 检查爆料重复失败: {error_msg} (错误码: {error_code})")
                return None

            logger.info("✅ 成功检查爆料链接重复状态")
            return data

        except requests.exceptions.Timeout:
            logger.error("❌ 检查爆料重复请求超时")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 检查爆料重复请求失败: {str(e)}")
            return None
        except ValueError as e:
            logger.error(f"❌ 检查爆料重复响应JSON解析失败: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"❌ 检查爆料重复未知错误: {str(e)}")
            return None

    def submit_pre_check_baoliao(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        提交爆料前置检查

        Args:

        Returns:
            检查结果字典，失败返回None
        """
        import json  # 在函数内部导入，避免循环导入

        api_url = "https://app-api.smzdm.com/baoliao_v2/submit_pre_check"

        params["setting"] = self.setting
        # 获取当前时间戳
        current_time = int(time.time() * 1000)
        # 构建请求参数
        params['time'] = str(current_time)
        # 计算签名
        sign = calculate_sign(params)
        params['sign'] = sign

        # print(json.dumps(params, ensure_ascii=False))


        # 设置请求头，完全匹配curl命令
        headers = {
            'User-Agent': 'smzdm 11.1.35 rv:167 (iPhone 6s; iOS 15.8.3; zh_CN)/iphone_smzdmapp/11.1.35',
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'content-encoding': 'gzip',
            'accept-language': 'zh-Hans-CN;q=1',
            'Cookie': self.cookie
        }

        try:
            response = requests.post(
                api_url,
                data=params,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            # 检查业务错误码
            error_code = data.get('error_code')
            if error_code not in [0, '0', None]:

                error_msg = data.get('error_msg', '未知错误')
                logger.error(f"❌ 爆料前置检查失败: {error_msg} (错误码: {error_code})")
                return None

            logger.info("✅ 爆料前置检查成功")
            return data

        except requests.exceptions.Timeout:
            logger.error("❌ 爆料前置检查请求超时")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 爆料前置检查请求失败: {str(e)}")
            return None
        except ValueError as e:
            logger.error(f"❌ 爆料前置检查响应JSON解析失败: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"❌ 爆料前置检查未知错误: {str(e)}")
            return None


    def submit_baoliao_article(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        提交爆料

        Args:

        Returns:
            检查结果字典，失败返回None
        """
        import json  # 在函数内部导入，避免循环导入

        api_url = "https://app-api.smzdm.com/v2/baoliao/submit"

        # 获取当前时间戳
        current_time = int(time.time() * 1000)

        params["setting"] = self.setting
        # 构建请求参数
        params['time'] = str(current_time)
        # 计算签名
        sign = calculate_sign(params)
        params['sign'] = sign

        # 设置请求头，完全匹配curl命令
        headers = {
            'User-Agent': 'smzdm 11.1.35 rv:167 (iPhone 6s; iOS 15.8.3; zh_CN)/iphone_smzdmapp/11.1.35',
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'content-encoding': 'gzip',
            'accept-language': 'zh-Hans-CN;q=1',
            'Cookie': self.cookie
        }

        try:
            response = requests.post(
                api_url,
                data=params,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            # 检查业务错误码
            error_code = data.get('error_code')
            if error_code not in [0, '0', None]:
                error_msg = data.get('error_msg', '未知错误')
                logger.error(f"❌ 爆料前置检查失败: {error_msg} (错误码: {error_code})")
                return None

            logger.info("✅ 爆料前置检查成功")
            return data

        except requests.exceptions.Timeout:
            logger.error("❌ 爆料前置检查请求超时")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 爆料前置检查请求失败: {str(e)}")
            return None
        except ValueError as e:
            logger.error(f"❌ 爆料前置检查响应JSON解析失败: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"❌ 爆料前置检查未知错误: {str(e)}")
            return None



    def upload_baoliao_image(self, image_url: str, pic_index: int = 0) -> Optional[Dict[str, Any]]:
        """
        上传图片到什么值得买服务器

        Args:
            image_url: 图片的URL地址
            pic_index: 图片索引，默认为0

        Returns:
            上传结果字典，失败返回None
        """
        logger.info(f"📌 正在下载图片: {image_url}")

        # 下载并处理图片
        img_data, img_format = self._download_and_process_image(image_url)
        if not img_data:
            return None

        # 上传图片
        return self._upload_to_smzdm(img_data, img_format, pic_index)

    def _download_and_process_image(self, image_url: str) -> tuple[Optional[bytes], str]:
        """
        下载并处理图片，统一转换为 JPEG 格式

        Returns:
            (图片数据, 格式) 或 (None, '')
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/123.0.0.0 Safari/537.36",
            "Referer": "https://detail.tmall.com/",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }

        try:
            response = requests.get(image_url, headers=headers, timeout=30)
            response.raise_for_status()

            # 使用 PIL 打开图片，自动识别格式
            img = Image.open(BytesIO(response.content))

            # 统一转换为 JPEG（SMZDM 更兼容）
            if img.mode in ('RGBA', 'LA', 'P'):
                # 处理透明通道
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # 保存为 JPEG
            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=90, optimize=True)
            img_data = buffer.getvalue()

            logger.info(f"✅ 图片处理成功，格式: JPEG, 大小: {len(img_data)} 字节")
            return img_data, 'jpeg'

        except requests.RequestException as e:
            logger.error(f"❌ 下载图片失败: {e}")
            return None, ''
        except Exception as e:
            logger.error(f"❌ 处理图片失败: {e}")
            return None, ''

    def _upload_to_smzdm(self, img_data: bytes, img_format: str, pic_index: int) -> Optional[Dict[str, Any]]:
        """
        上传图片数据到什么值得买服务器
        """
        api_url = "https://app-api.smzdm.com/util/image/upload"

        # 尝试三种 base64 格式
        img_base64 = base64.b64encode(img_data).decode('utf-8')

        # 格式1: 带 data URI scheme (最常见)
        pic_data_formats = [
            f"data:image/{img_format};base64,{img_base64}",  # 标准格式
            img_base64,  # 纯 base64
            f"data:image/jpeg;base64,{img_base64}",  # 强制 jpeg
        ]

        for idx, pic_data in enumerate(pic_data_formats):
            logger.info(f"📌 尝试格式 {idx + 1}: {'带前缀' if pic_data.startswith('data:') else '纯base64'}")

            params = {
                'basic_v': '0',
                'f': 'iphone',
                'pic_data': pic_data,
                'pic_index': str(pic_index),
                'time': str(int(time.time() * 1000)),
                'v': '11.1.35',
                'weixin': '1',
                'zhuanzai_ab': 'b'
            }

            params['sign'] = calculate_sign_from_params(params)

            headers = {
                'Cookie': self.cookie,
                'content-type': 'application/x-www-form-urlencoded',
                'request_key': '944831971761922056',
                'accept': '*/*',
                'accept-language': 'zh-Hans-CN;q=1',
                'user-agent': 'smzdm 11.1.35 rv:167 (iPhone 6s; iOS 15.8.3; zh_CN)/iphone_smzdmapp/11.1.35',
            }

            try:
                response = requests.post(api_url, data=params, headers=headers, timeout=60)
                response.raise_for_status()
                data = response.json()

                error_code = data.get('error_code')

                # 成功
                if error_code in [0, '0', None]:
                    logger.info("✅ 图片上传成功")
                    if upload_data := data.get('data', {}):
                        logger.info(f"    图片URL: {upload_data.get('url', '')}")
                        logger.info(f"   图片HASH: {upload_data.get('hash', '')}")
                    return data

                # 格式错误，尝试下一种格式
                if error_code == '10004':
                    logger.warning(f"⚠️ 格式 {idx + 1} 失败: {data.get('error_msg')}")
                    continue

                # 其他错误，直接返回
                logger.error(f"❌ 上传失败: {data.get('error_msg')} (错误码: {error_code})")
                return None

            except requests.Timeout:
                logger.error("❌ 请求超时")
                return None
            except Exception as e:
                logger.error(f"❌ 请求异常: {e}")
                return None

        logger.error("❌ 所有格式尝试失败")
        return None


    def activity_task_receive(self, activity_id: str, token: str) -> bool:
        """
        领取活动阶段性奖励

        Args:
            activity_id: 活动ID

        Returns:
            是否成功
            :param token:
        """
        url = f"{self.USER_API_URL}/task/activity_task_receive"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        data = {
          "basic_v": "0",
          "f": "iphone",
          "robot_token": token,
          "sign": "",
          "task_id": activity_id,
          "time": str(current_time),
          "v": "11.1.35",
          "weixin": "1",
          "zhuanzai_ab": "b"
        }

        # 计算签名
        sign = calculate_sign_from_params(data)
        data['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })

        logger.info(f"正在领取爆料阶段性奖励 (activity_id={activity_id})...")

        try:
            response = self.session.post(url, data=data, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                reward_info = data.get('data', {})
                logger.info(f"✅ 爆料阶段性奖励领取成功! 奖励: {reward_info}")
                return True
            else:
                logger.error(f"❌ 领取爆料阶段性奖励失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 领取爆料阶段性奖励请求失败: {str(e)}")
            return False

    def get_user_article(self):
        """
        获取用户的爆料文章列表

        Returns:
            文章列表数据，失败返回None
        """
        url = f"{self.USER_API_URL}/articles/publish/baoliao"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'basic_v': '0',
            'f': 'iphone',
            'limit': '30',
            'offset': '0',
            'time': str(current_time),
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }

        # 计算签名
        sign = calculate_sign_from_params(params)
        params['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })

        logger.info(f"📌 正在获取用户爆料文章列表...")

        try:
            response = self.session.post(url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info(f"✅ 成功获取用户爆料文章列表")
                return data.get('data', {})
            else:
                logger.error(f"❌ 获取用户爆料文章列表失败: {data.get('error_msg', '未知错误')}")
                return None
        except Exception as e:
            logger.error(f"❌ 获取用户爆料文章列表请求失败: {str(e)}")
            return None

    def get_robot_token(self):
        """
        获取用户的爆料文章列表

        Returns:
            文章列表数据，失败返回None
        """
        url = f"{self.USER_API_URL}/robot/token"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        params = {
            'basic_v': '0',
            'f': 'iphone',
            'sign': '',
            'time': str(current_time),
            'v': '11.1.35',
            'weixin': '1',
            'zhuanzai_ab': 'b'
        }

        # 计算签名
        sign = calculate_sign_from_params(params)
        params['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })

        logger.info(f"📌 正在获取用户robot生成token...")

        try:
            response = self.session.post(url, data=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            print(data)
            if data.get('error_code') == '0' or data.get('error_code') == 0:
                logger.info(f"✅ 成功获取用户robot生成token")
                return data.get('data', {})
            else:
                logger.error(f"❌ 获取用户robot生成token失败: {data.get('error_msg', '未知错误')}")
                return None
        except Exception as e:
            logger.error(f"❌ 获取用户robot生成token请求失败: {str(e)}")
            return None





    def getcaptcha_switch(self) -> bool:
        """
        领取活动阶段性奖励

        Args:
            activity_id: 活动ID

        Returns:
            是否成功
            :param token:
        """
        url = f"{self.USER_API_URL}/getcaptcha/switch"

        # 构建请求参数
        current_time = int(time.time() * 1000)
        data = {
          "basic_v": "0",
          "f": "iphone",
          "sign": "",
          "time": str(current_time),
          "v": "11.1.35",
          "weixin": "1",
          "zhuanzai_ab": "b"
        }

        # 计算签名
        sign = calculate_sign_from_params(data)
        data['sign'] = sign

        # 设置特殊请求头
        headers = self.session.headers.copy()
        headers.update({
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'request_key': str(int(time.time() * 1000000000))[:18],
            'Content-Encoding': 'gzip',
            'Accept-Language': 'zh-Hans-CN;q=1'
        })


        try:
            response = self.session.post(url, data=data, headers=headers)
            response.raise_for_status()
            data = response.json()
            print(data)
            if data.get('error_code') == '0' or data.get('error_code') == 0:
                reward_info = data.get('data', {})
                logger.info(f"✅ 爆料阶段性奖励领取成功! 奖励: {reward_info}")
                return True
            else:
                logger.error(f"❌ 领取爆料阶段性奖励失败: {data.get('error_msg', '未知错误')}")
                return False
        except Exception as e:
            logger.error(f"❌ 领取爆料阶段性奖励请求失败: {str(e)}")
            return False




if __name__ == '__main__':
    api = SmzdmAPI("z_df=dz7a0RhUmbvWKo4vzEq%2BnqPhE2bgPIZs6idZXnQ7fLSKp52DTEJ%2FtQ%3D%3D;z_df_md5=0;basic_v=0;device_s=7xbgt04V1fJNr5Xq6afo99CNcHiFU%2FeMoSYLiCs%2FR9jr0MrWbxyzEJ4daig9ftTSvD55KLkgUlg%3D;session_id=7xbgt04V1fJNr5Xq6afo99CNcHiFU%2FeMoSYLiCs%2FR9gFPqaGnl8E3Q%3D%3D.1760957718;partner_id=31241;partner_name=iweibo241;device_recfeed_setting=%7B%22homepage_sort_switch%22%3A%221%22%2C%22haojia_recfeed_switch%22%3A%221%22%2C%22other_recfeed_switch%22%3A%221%22%2C%22shequ_recfeed_switch%22%3A%221%22%7D;f=iphone;device_id=7xbgt04V1fJNr5Xq6afo99CNcHiFU%2FeMoSYLiCs%2FR9gFPqaGnl8E3Q%3D%3D;device_name=iPhone%2014%20Plus;apk_partner_name=appstore;active_time=1699085598;v=11.1.35;last_article_info=%7B%22article_id%22%3A%22160010675%22%2C%22article_channel_id%22%3A%222%22%7D;is_dark_mode=0;device_smzdm_version_code=167;device_system_version=26.0.1;sess=BC-1RkVC19l4AT3O%20P9xPOFcO3xhAwxdGKoVf0Ig1mDTp750xrJgvpa653OQMWAUCzj%2FIkvEqu1qZGNk9qf5Wx9u6gBRAQOLSGvabtjABeLegCnOi3PWhoUQpP2uw%3D%3D;device_push=notifications_are_disabled;client_id=d12bae4972f9934d727f0367d9b4df20.1728221391721;device_screen_type=iphone;onmac=0;network=1;smzdm_id=7126551750;font_size=normal;device_type=iPhone14%2C8;device_smzdm=iphone;",
                   "smzdm 11.1.35 rv:167 (iPhone 14 Plus; iOS 26.0.1; zh_CN)/iphone_smzdmapp/11.1.35")

    api.upload_baoliao_image("https://img.alicdn.com/i4/2014491970/O1CN01iOBG9z1QQJEt06kJm_!!2014491970.jpg")