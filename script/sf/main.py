#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
new Env('顺丰快递积分任务');
cron: 45 9 * * *
"""
"""
顺丰快递积分任务自动化脚本

功能：
1. 从token.json配置文件读取账号信息
2. 支持多账号管理
3. 自动执行签到和积分任务
4. 推送执行结果通知

Author: ZaiZaiCat
Date: 2025-01-20
"""

import json
import logging
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from notification import send_notification, NotificationSound

# 导入API模块（当前目录）
from api import SFExpressAPI, ShareLoginInfo

# 延迟时间常量配置 (秒)
DELAY_BETWEEN_ACCOUNTS = (3, 8)      # 账号间切换延迟
DELAY_AFTER_SIGN = (2, 5)           # 签到后延迟
DELAY_BETWEEN_TASKS = (10, 15)      # 任务间延迟

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SFAccountConfig:
    """顺丰账号配置"""

    account_name: str
    sign: str
    user_agent: str
    channel: str
    device_id: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SFAccountConfig":
        """从配置字典构建账号配置"""
        account_name = data.get("account_name") or "未命名账号"
        sign = data.get("sign") or ""
        user_agent = data.get("user_agent") or ""
        channel = data.get("channel") or ""
        device_id = data.get("device_id") or ""

        missing_fields = []
        if not sign:
            missing_fields.append("sign")
        if not channel:
            missing_fields.append("channel")
        if not device_id:
            missing_fields.append("device_id")

        if missing_fields:
            missing_text = "、".join(missing_fields)
            raise ValueError(f"账号【{account_name}】缺少必填字段: {missing_text}")

        return cls(
            account_name=account_name,
            sign=sign,
            user_agent=user_agent,
            channel=channel,
            device_id=device_id
        )


class SFTasksManager:
    """顺丰积分任务管理器"""

    def __init__(self, config_path: str = None):
        """
        初始化任务管理器

        Args:
            config_path: 配置文件路径，默认为项目根目录下的config/token.json
        """
        if config_path is None:
            config_path = project_root / "config" / "token.json"
        else:
            config_path = Path(config_path)

        self.config_path = config_path
        self.site_name = "顺丰速运"
        self.accounts: List[SFAccountConfig] = []
        self.task_summary = []
        self.load_config()

    def load_config(self) -> None:
        """加载配置文件"""
        try:
            logger.info(f"正在读取配置文件: {self.config_path}")
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 获取顺丰的配置
            sf_config = config.get("sf", {})
            raw_accounts = sf_config.get("accounts", [])

            self.accounts = []
            for raw_account in raw_accounts:
                try:
                    self.accounts.append(SFAccountConfig.from_dict(raw_account))
                except ValueError as e:
                    logger.error(f"账号配置异常: {e}")

            if not self.accounts:
                logger.warning("配置文件中没有找到顺丰账号信息")
            else:
                logger.info(f"成功加载 {len(self.accounts)} 个账号配置")

        except FileNotFoundError:
            logger.error(f"配置文件不存在: {self.config_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"配置文件JSON格式错误: {e}")
            raise
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise

    def get_task_list(self, sf_api: SFExpressAPI) -> List[Dict[str, Any]]:
        """
        获取顺丰积分任务列表

        Args:
            sf_api: SF API实例

        Returns:
            List[Dict[str, Any]]: 任务列表
        """
        try:
            result = sf_api.query_point_task_and_sign()
            task_list = result.get("obj", {}).get("taskTitleLevels", [])
            logger.info(f"获取到 {len(task_list)} 个任务")
            return task_list
        except Exception as e:
            logger.error(f"获取任务列表失败: {e}")
            return []

    @staticmethod
    def extract_task_code(task: Dict[str, Any]) -> str:
        """从任务信息中提取task_code"""
        task_code = task.get("taskCode")
        if task_code:
            return task_code

        button_redirect = task.get("buttonRedirect", "")
        if not button_redirect:
            return ""

        decoded_redirect = unquote(button_redirect)
        ug_param = ""

        if "_ug_view_param=" in decoded_redirect:
            ug_param = decoded_redirect.split("_ug_view_param=", 1)[1]
        else:
            for candidate in (button_redirect, decoded_redirect):
                try:
                    query = urlparse(candidate).query
                    if not query:
                        continue
                    params = parse_qs(query)
                    if params.get("_ug_view_param"):
                        ug_param = params["_ug_view_param"][0]
                        break
                except Exception:
                    continue

        if not ug_param:
            return ""

        ug_param = unquote(ug_param).strip()

        try:
            ug_data = json.loads(ug_param)
            if isinstance(ug_data, dict):
                return ug_data.get("taskId", "")
        except json.JSONDecodeError:
            match = re.search(r'"taskId"\s*:\s*"([^"]+)"', ug_param)
            if match:
                return match.group(1)

        return ""

    def fetch_login_info(self, account: SFAccountConfig) -> Optional[ShareLoginInfo]:
        """
        获取账号登录信息（user_id + cookies）

        Args:
            account: 账号配置

        Returns:
            ShareLoginInfo | None: 登录信息
        """
        logger.info(f"[{account.account_name}] 开始请求分享登录接口")
        login_info = SFExpressAPI.share_login(
            sign=account.sign,
            user_agent=account.user_agent or None
        )

        if not login_info.success:
            logger.warning(f"[{account.account_name}] 分享登录失败: {login_info.error}")
            return None

        if not login_info.user_id or not login_info.cookies:
            logger.warning(f"[{account.account_name}] 分享登录返回数据不完整")
            return None

        logger.info(f"[{account.account_name}] 分享登录成功，已获取用户信息")
        return login_info

    def auto_sign_and_fetch_package(self, sf_api: SFExpressAPI, account_name: str) -> Dict[str, Any]:
        """
        自动签到并获取礼包

        Args:
            sf_api: SF API实例
            account_name: 账号名称

        Returns:
            Dict[str, Any]: 签到结果，包含成功状态和连续签到天数
        """
        try:
            logger.info(f"[{account_name}] 开始执行自动签到获取礼包...")
            result = sf_api.automatic_sign_fetch_package()

            if result.get("success"):
                obj = result.get("obj", {})
                has_finish_sign = obj.get("hasFinishSign", 0)
                count_day = obj.get("countDay", 0)
                package_list = obj.get("integralTaskSignPackageVOList", [])

                if has_finish_sign == 1:
                    logger.info(f"[{account_name}] 今日已完成签到，连续签到 {count_day} 天")
                else:
                    logger.info(f"[{account_name}] 签到成功！连续签到 {count_day} 天")

                # 记录获得的礼包
                if package_list:
                    logger.info(f"[{account_name}] 获得签到礼包:")
                    for package in package_list:
                        package_name = package.get("commodityName", "未知礼包")
                        invalid_date = package.get("invalidDate", "")
                        logger.info(f"[{account_name}] - {package_name} (有效期至: {invalid_date})")
                else:
                    logger.info(f"[{account_name}] 未获得签到礼包")

                return {'success': True, 'days': count_day, 'already_signed': has_finish_sign == 1}
            else:
                error_msg = result.get("errorMessage", "未知错误")
                logger.warning(f"[{account_name}] 签到失败: {error_msg}")
                return {'success': False, 'days': 0, 'error': error_msg}

        except Exception as e:
            logger.error(f"[{account_name}] 自动签到时发生错误: {e}")
            return {'success': False, 'days': 0, 'error': str(e)}

    def process_single_task(self, task: Dict[str, Any], sf_api: SFExpressAPI, account_name: str) -> Dict[str, Any]:
        """
        处理单个任务

        Args:
            task: 任务信息
            sf_api: SF API实例
            account_name: 账号名称

        Returns:
            Dict[str, Any]: 任务执行结果
        """
        task_title = task.get('title', '未知任务')
        task_code = self.extract_task_code(task)

        if not task_code:
            logger.warning(f"[{account_name}] 任务 {task_title} 缺少任务代码，跳过")
            return {'title': task_title, 'success': False, 'points': 0}

        try:
            finish_result = sf_api.finish_task(task_code)
            if finish_result and finish_result.get('success'):
                logger.info(f"[{account_name}] 任务 {task_title} 完成成功")

                # 获取任务奖励
                reward_result = sf_api.fetch_tasks_reward()
                logger.info(f"[{account_name}] 任务奖励获取结果: {reward_result}")

                # 提取获得的积分
                points = 0
                if reward_result and reward_result.get('success'):
                    obj_list = reward_result.get('obj', [])
                    if isinstance(obj_list, list):
                        for item in obj_list:
                            points += item.get('point', 0)

                return {'title': task_title, 'success': True, 'points': points}
            else:
                logger.warning(f"[{account_name}] 任务 {task_title} 完成失败或无返回结果")
                return {'title': task_title, 'success': False, 'points': 0}
        except Exception as e:
            logger.error(f"[{account_name}] 执行任务 {task_title} 时发生错误: {e}")
            return {'title': task_title, 'success': False, 'points': 0}

    def process_account_tasks(self, account: SFAccountConfig) -> Dict[str, Any]:
        """
        处理单个账号的所有任务

        Args:
            account: 账号信息

        Returns:
            Dict[str, Any]: 账号任务执行统计
        """
        account_name = account.account_name

        # 初始化账号统计
        account_stat = {
            'account_name': account_name,
            'sign_success': False,
            'sign_days': 0,
            'total_tasks': 0,
            'completed_tasks': 0,
            'total_points': 0,
            'available_points': None,
            'tasks': []
        }

        if not account.sign:
            logger.error(f"账号 {account_name} 配置信息不完整，缺少sign，跳过处理")
            account_stat['error'] = '配置信息不完整'
            return account_stat

        logger.info(f"开始处理账号: {account_name}")

        try:
            login_info = self.fetch_login_info(account)
            if login_info is None:
                account_stat['error'] = '分享登录失败'
                return account_stat

            # 创建API实例
            sf_api = SFExpressAPI(
                cookies=login_info.cookies,
                device_id=account.device_id,
                user_id=login_info.user_id,
                user_agent=account.user_agent,
                channel=account.channel
            )

            # 首先执行自动签到获取礼包
            sign_result = self.auto_sign_and_fetch_package(sf_api, account_name)
            account_stat['sign_success'] = sign_result.get('success', False)
            account_stat['sign_days'] = sign_result.get('days', 0)

            # 签到后稍作延时
            sign_delay = random.uniform(*DELAY_AFTER_SIGN)
            logger.info(f"[{account_name}] 签到完成，延时 {sign_delay:.2f} 秒后继续任务...")
            time.sleep(sign_delay)

            # 获取任务列表
            task_list = self.get_task_list(sf_api)

            if not task_list:
                logger.warning(f"[{account_name}] 未获取到任务列表")
            else:
                logger.info(f"[{account_name}] 获取到 {len(task_list)} 个任务")

                # 处理每个任务
                for i, task in enumerate(task_list, 1):
                    logger.info(f"[{account_name}] 开始处理第 {i}/{len(task_list)} 个任务")

                    if task.get("taskPeriod") != "D":
                        logger.info(f"[{account_name}] 任务 {task.get('title', '未知任务')} 非日常任务，跳过")
                        continue

                    account_stat['total_tasks'] += 1

                    # 如果任务已完成，跳过
                    if task.get("status") == 3:
                        logger.info(f"[{account_name}] 任务 {task.get('title', '未知任务')} 已完成，跳过")
                        continue

                    delay_time = random.uniform(*DELAY_BETWEEN_TASKS)
                    logger.info(f"[{account_name}] 准备执行任务 {task.get('title', '未知任务')}，延时 {delay_time:.2f} 秒...")
                    time.sleep(delay_time)

                    task_result = self.process_single_task(task, sf_api, account_name)
                    account_stat['tasks'].append(task_result)

                    if task_result.get('success'):
                        account_stat['completed_tasks'] += 1
                        account_stat['total_points'] += task_result.get('points', 0)

            # 查询账号积分信息（当前积分）
            user_info_result = sf_api.query_user_info()
            if user_info_result.get("success"):
                user_info_obj = user_info_result.get("obj", {})
                available_points = user_info_obj.get("availablePoints")
                account_stat['available_points'] = available_points
                logger.info(f"[{account_name}] 当前积分: {available_points}")
            else:
                error_msg = user_info_result.get("errorMessage") or user_info_result.get("error") or "未知错误"
                logger.warning(f"[{account_name}] 查询当前积分失败: {error_msg}")

        except Exception as e:
            logger.error(f"处理账号 {account_name} 时发生错误: {e}")
            account_stat['error'] = str(e)

        return account_stat

    def run_all_accounts(self) -> None:
        """执行所有账号的任务处理"""
        if not self.accounts:
            logger.warning("没有配置的账号，程序退出")
            return

        logger.info(f"开始执行任务，共 {len(self.accounts)} 个账号")

        for i, account in enumerate(self.accounts, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"处理第 {i}/{len(self.accounts)} 个账号")
            logger.info(f"{'='*60}")

            account_stat = self.process_account_tasks(account)
            self.task_summary.append(account_stat)
            logger.info(f"账号 {i} 处理完成")

            # 账号间添加延时，避免频繁切换
            if i < len(self.accounts):
                account_delay = random.uniform(*DELAY_BETWEEN_ACCOUNTS)
                logger.info(f"账号切换延时 {account_delay:.2f} 秒...")
                time.sleep(account_delay)

        logger.info("所有账号任务处理完成")

    def send_notification(self, start_time: datetime, end_time: datetime) -> None:
        """
        发送任务执行汇总推送通知

        Args:
            start_time: 任务开始时间
            end_time: 任务结束时间
        """
        try:
            duration = (end_time - start_time).total_seconds()

            # 计算总体统计
            total_accounts = len(self.task_summary)
            total_sign_success = sum(1 for stat in self.task_summary if stat.get('sign_success'))
            total_completed = sum(stat.get('completed_tasks', 0) for stat in self.task_summary)
            total_points = sum(stat.get('total_points', 0) for stat in self.task_summary)

            # 构建推送标题
            title = f"{self.site_name}积分任务完成 ✅"

            # 构建推送内容
            content_parts = [
                f"📊 总体统计",
                f"━━━━━━━━━━━━━━━━",
                f"👥 账号数量: {total_accounts}个",
                f"✅ 签到成功: {total_sign_success}/{total_accounts}",
                f"📝 完成任务: {total_completed}个",
                f"🎁 获得积分: {total_points}分",
                f"⏱️ 执行耗时: {int(duration)}秒",
                "",
                f"📋 账号详情",
                f"━━━━━━━━━━━━━━━━"
            ]

            # 添加每个账号的详细信息
            for i, stat in enumerate(self.task_summary, 1):
                account_name = stat.get('account_name', f'账号{i}')
                sign_days = stat.get('sign_days', 0)
                completed = stat.get('completed_tasks', 0)
                points = stat.get('total_points', 0)
                available_points = stat.get('available_points')

                # 账号摘要
                if stat.get('error'):
                    content_parts.append(f"❌ [{account_name}] 执行失败")
                    content_parts.append(f"   错误: {stat['error']}")
                else:
                    sign_status = "✅" if stat.get('sign_success') else "❌"
                    content_parts.append(f"{sign_status} [{account_name}]")
                    content_parts.append(f"   📅 连续签到: {sign_days}天")
                    content_parts.append(f"   📝 完成任务: {completed}个")
                    content_parts.append(f"   🎁 获得积分: {points}分")
                    if available_points is not None:
                        content_parts.append(f"   💰 当前积分: {available_points}分")

                # 账号之间添加空行
                if i < len(self.task_summary):
                    content_parts.append("")

            # 添加完成时间
            content_parts.append("━━━━━━━━━━━━━━━━")
            content_parts.append(f"🕐 {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

            content = "\n".join(content_parts)

            # 发送推送
            send_notification(
                title=title,
                content=content,
                sound=NotificationSound.BIRDSONG
            )
            logger.info(f"✅ {self.site_name}任务汇总推送发送成功")

        except Exception as e:
            logger.error(f"❌ 发送任务汇总推送失败: {str(e)}", exc_info=True)


def log_task_header(title: str, timestamp: datetime) -> None:
    """打印任务执行标题"""
    logger.info("=" * 60)
    logger.info(f"{title} - {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)


def main():
    """主函数"""
    # 记录开始时间
    start_time = datetime.now()
    log_task_header("顺丰快递积分任务开始执行", start_time)

    try:
        # 创建任务管理器
        manager = SFTasksManager()

        # 执行所有账号的任务
        manager.run_all_accounts()

        # 记录结束时间
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info("=" * 60)
        logger.info(f"顺丰快递积分任务执行完成 - {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"执行耗时: {int(duration)} 秒")
        logger.info("=" * 60)

        # 发送推送通知
        if manager.task_summary:
            manager.send_notification(start_time, end_time)

        return 0

    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.error(f"任务执行异常: {str(e)}", exc_info=True)

        # 发送错误通知
        try:
            send_notification(
                title=f"顺丰快递积分任务异常 ❌",
                content=(
                    f"❌ 任务执行异常\n"
                    f"💬 错误信息: {str(e)}\n"
                    f"⏱️ 执行耗时: {int(duration)}秒\n"
                    f"🕐 完成时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}"
                ),
                sound=NotificationSound.ALARM
            )
        except Exception:
            logger.error("发送异常通知失败", exc_info=True)

        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
