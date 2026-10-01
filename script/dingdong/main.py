#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
new Env('叮咚买菜签到');
cron: 30 9 * * *
"""
"""
叮咚买菜自动签到脚本

功能：
1. 从 config/token.json 读取账号信息，支持多账号
2. 积分签到：先查积分首页确认今日状态，未签到才调签到接口
3. 农场任务：遍历 task/list 把能领的饲料奖励全领一遍
4. 农场喂鱼：饲料 ≥ 10g 时自动喂食
5. 积分中心：自动完成「浏览 XX 秒」类任务
6. 推送执行结果通知（本机运行时失败才弹 macOS 通知）

配置节点：dingdong.accounts / dingdong.options
必填字段：cookies（至少包含 DDXQSESSID）
可选字段：uid、station_id、city_number、latitude、longitude、
         device_id、device_token、user_agent 等

注意：本脚本按「本地执行」设计（见 README），不建议放到海外 VPS 上跑。

Author: ZaiZaiCat
Date: 2026-10-01
"""

import json
import logging
import platform
import warnings

# 本机 Python 用 LibreSSL 时 urllib3 会刷 NotOpenSSLWarning，屏蔽掉以免污染日志
warnings.filterwarnings('ignore', message=r'.*OpenSSL.*')

import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from notification import send_notification, NotificationSound

# 导入API模块（当前目录）
from api import DingdongAPI, FarmAPI, MissionAPI, META_FIELDS

# 日常任务开关（可被 config/token.json 里 dingdong.options 覆盖）
DEFAULT_OPTIONS = {
    'sign_in': True,        # 积分签到
    'farm_reward': True,    # 农场任务领饲料
    'farm_feed': True,      # 喂鱼（饲料 ≥ 10g 才喂）
    'farm_achieve': True,   # 尝试直接完成浏览类农场任务
    'mission': True,        # 积分中心浏览类任务
    'lucky_draw': False,    # 天天翻牌（消耗 5g 饲料，净收益不确定，默认关）
}

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def notify_local(title: str, message: str) -> None:
    """macOS 本机通知（非 macOS 或失败时静默跳过）"""
    if platform.system() != 'Darwin' or not shutil.which('osascript'):
        return
    try:
        script = f'display notification {json.dumps(message)} with title {json.dumps(title)}'
        subprocess.run(['osascript', '-e', script], timeout=10,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        logger.debug(f"本机通知发送失败: {e}")


class DingdongSignInManager:
    """叮咚买菜签到管理器"""

    def __init__(self, config_path: str = None):
        """
        初始化签到管理器

        Args:
            config_path: 配置文件路径，默认为项目根目录下的config/token.json
        """
        if config_path is None:
            config_path = project_root / "config" / "token.json"
        else:
            config_path = Path(config_path)

        self.config_path = config_path
        self.site_name = "叮咚买菜"
        self.accounts = []
        self.options = dict(DEFAULT_OPTIONS)
        self.load_config()

    def load_config(self) -> None:
        """加载配置文件"""
        try:
            logger.info(f"正在读取配置文件: {self.config_path}")
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            self.accounts = config.get('dingdong', {}).get('accounts', [])
            self.options.update(config.get('dingdong', {}).get('options') or {})

            if not self.accounts:
                logger.warning("配置文件中没有找到叮咚买菜账号信息")
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

    def sign_in_single_account(self, account: Dict[str, Any]) -> Dict[str, Any]:
        """
        单个账号签到

        Args:
            account: 账号配置信息

        Returns:
            Dict: 签到结果
        """
        account_name = account.get('account_name') or account.get('name') or '未命名账号'
        cookies = account.get('cookies') or account.get('cookie') or ''
        user_agent = account.get('user_agent')
        meta = {k: account[k] for k in META_FIELDS if account.get(k) not in (None, '')}

        logger.info(f"开始执行账号 [{account_name}] 的签到...")

        if not cookies:
            error_msg = "cookies为空"
            logger.error(f"账号 [{account_name}] {error_msg}")
            return {'account_name': account_name, 'success': False, 'error': error_msg}

        api = DingdongAPI(cookies, meta, user_agent)
        try:
            if self.options.get('sign_in', True):
                # 先查今日状态，已签到直接跳过；查询失败仍尝试签到
                status = api.get_today_status()
                if status and status.get('signed'):
                    message = (f"今日已签到，连续第 {status.get('sign_series', 0)} 天，"
                               f"当前 {status.get('point_num', 0)} 积分")
                    logger.info(f"🔁 {message}")
                    result = {'success': True, 'already': True, 'message': message, 'status': status}
                else:
                    result = api.sign_in()
                    result['already'] = False
                    # 签到后补一次状态，拿最新积分
                    if result.get('success'):
                        time.sleep(1)
                        latest = api.get_today_status()
                        if latest:
                            result['status'] = latest
                            result['message'] += f"，当前 {latest.get('point_num', 0)} 积分"
            else:
                logger.info("⏭️ 已跳过签到（options.sign_in = false）")
                result = {'success': True, 'already': True, 'message': '已跳过签到', 'status': {}}

            # 签到之外：农场领饲料 / 喂鱼 / 积分中心浏览任务
            result['extras'] = self.run_daily_tasks(cookies, meta, user_agent)

            result['account_name'] = account_name
            if result.get('success'):
                logger.info(f"账号 [{account_name}] 处理完成")
            else:
                logger.error(f"账号 [{account_name}] 签到失败: {result.get('message')}")
            return result

        except Exception as e:
            error_msg = f"签到异常: {str(e)}"
            logger.error(f"账号 [{account_name}] {error_msg}", exc_info=True)
            return {'account_name': account_name, 'success': False, 'error': error_msg}
        finally:
            api.close()

    def run_daily_tasks(self, cookies: str, meta: Dict[str, Any],
                        user_agent: str = None) -> Dict[str, Any]:
        """
        签到之外的日常任务：农场领饲料 / 喂鱼 / 积分中心浏览任务

        任何一步失败都不影响签到结果，只记进 extras 里。
        """
        extras: Dict[str, Any] = {
            'farm_claimed': 0, 'farm_feed': 0, 'farm_details': [],
            'feed_left': None, 'fed': False, 'feed_message': '',
            'missions_done': 0, 'mission_details': [],
            'draw': '', 'errors': [],
        }

        # ---------- 农场：领任务奖励 ----------
        if self.options.get('farm_reward', True):
            farm = FarmAPI(cookies, meta, user_agent)
            try:
                result = farm.claim_all_rewards()
                extras['farm_claimed'] = result['claimed']
                extras['farm_feed'] = result['feed']
                extras['farm_details'] = result['details']

                # ---------- 农场：尝试直接完成浏览类任务 ----------
                if self.options.get('farm_achieve', True):
                    for task in farm.get_task_list():
                        if task.get('buttonStatus') != 'TO_ACHIEVE':
                            continue
                        code = task.get('taskCode') or ''
                        if not code.startswith('BROWSE_'):
                            continue
                        achieved = farm.achieve_task(code)
                        if achieved.get('success'):
                            extras['farm_details'].append(f"✅ {task.get('taskName')} 已标记完成")
                            logger.info(f"✅ 农场任务 [{task.get('taskName')}] 已标记完成")
                        time.sleep(2)
                    # 标记完成后再领一轮
                    if extras['farm_details']:
                        second = farm.claim_all_rewards()
                        extras['farm_claimed'] += second['claimed']
                        extras['farm_feed'] += second['feed']
                        extras['farm_details'] += second['details']

                # ---------- 农场：喂鱼 ----------
                if self.options.get('farm_feed', True):
                    time.sleep(1)
                    extras['feed_left'] = farm.get_feed_amount()
                    if extras['feed_left'] >= 10:
                        fed = farm.feed()
                        extras['fed'] = fed.get('success', False)
                        extras['feed_message'] = fed.get('message', '')
                        if fed.get('success'):
                            logger.info(f"🐟 喂食成功：{fed.get('message')}")
                        else:
                            logger.warning(f"⚠️ 喂食失败：{fed.get('message')}")
                    else:
                        extras['feed_message'] = f"饲料不足（{extras['feed_left']}g），跳过喂食"
                        logger.info(f"⏭️ {extras['feed_message']}")

                # ---------- 农场：天天翻牌（默认关） ----------
                if self.options.get('lucky_draw', False):
                    time.sleep(1)
                    info = farm.get_lucky_draw_info()
                    if info.get('canDraw'):
                        drawn = farm.draw()
                        if drawn.get('success'):
                            extras['draw'] = f"{drawn.get('name')} x{drawn.get('amount')}"
                            logger.info(f"🎴 翻牌：{extras['draw']}")
                        else:
                            extras['draw'] = drawn.get('message', '')
                    else:
                        extras['draw'] = info.get('reason') or '今日不可翻牌'
            except Exception as e:
                extras['errors'].append(f"农场任务异常: {e}")
                logger.error(f"农场任务异常: {e}", exc_info=True)
            finally:
                farm.close()

        # ---------- 积分中心：浏览类任务 ----------
        if self.options.get('mission', True):
            mission = MissionAPI(cookies, meta, user_agent)
            try:
                result = mission.run_browse_missions()
                extras['missions_done'] = result['done']
                extras['mission_details'] = result['details']
            except Exception as e:
                extras['errors'].append(f"积分任务异常: {e}")
                logger.error(f"积分任务异常: {e}", exc_info=True)
            finally:
                mission.close()

        return extras

    def sign_in_all_accounts(self) -> List[Dict[str, Any]]:
        """
        所有账号签到

        Returns:
            List[Dict]: 所有账号的签到结果列表
        """
        if not self.accounts:
            logger.warning("没有可签到的账号")
            return []

        results = []
        for i, account in enumerate(self.accounts, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"正在处理第 {i}/{len(self.accounts)} 个账号")
            logger.info(f"{'='*60}")

            results.append(self.sign_in_single_account(account))

            # 账号间隔，避免触发限流
            if i < len(self.accounts):
                time.sleep(5)

        return results

    def send_notification(self, results: List[Dict[str, Any]], start_time: datetime, end_time: datetime) -> None:
        """发送签到结果通知"""
        try:
            duration = (end_time - start_time).total_seconds()

            total_count = len(results)
            success_count = sum(1 for r in results if r.get('success'))
            failed_count = total_count - success_count

            if failed_count == 0:
                title = f"{self.site_name}签到成功 ✅"
                sound = NotificationSound.BIRDSONG
            elif success_count == 0:
                title = f"{self.site_name}签到失败 ❌"
                sound = NotificationSound.ALARM
            else:
                title = f"{self.site_name}签到部分成功 ⚠️"
                sound = NotificationSound.BELL

            content_parts = ["📊 执行统计:"]
            if success_count > 0:
                content_parts.append(f"✅ 成功: {success_count} 个账号")
            if failed_count > 0:
                content_parts.append(f"❌ 失败: {failed_count} 个账号")
            content_parts.append(f"📈 总计: {total_count} 个账号")
            content_parts.append("")

            content_parts.append("📝 详情:")
            for result in results:
                account_name = result.get('account_name', '未知账号')
                if result.get('success'):
                    message = result.get('message', '签到成功')
                    if len(message) > 60:
                        message = message[:60] + "..."
                    prefix = "🔁" if result.get('already') else "✅"
                    content_parts.append(f"  {prefix} [{account_name}] {message}")
                else:
                    error = result.get('error') or result.get('message') or '未知错误'
                    if len(error) > 60:
                        error = error[:60] + "..."
                    content_parts.append(f"  ❌ [{account_name}] {error}")

                extras = result.get('extras') or {}
                if extras.get('farm_claimed'):
                    content_parts.append(
                        f"  🌾 农场领奖 {extras['farm_claimed']} 项，"
                        f"共 +{extras['farm_feed']}g 饲料")
                if extras.get('fed'):
                    content_parts.append(
                        f"  🐟 喂鱼成功（余 {extras.get('feed_left')}g）："
                        f"{extras.get('feed_message')}")
                elif extras.get('feed_left') is not None:
                    content_parts.append(f"  🐟 {extras.get('feed_message')}")
                if extras.get('missions_done'):
                    content_parts.append(f"  🎯 积分任务完成 {extras['missions_done']} 个")
                if extras.get('draw'):
                    content_parts.append(f"  🎴 翻牌：{extras['draw']}")
                for err in extras.get('errors') or []:
                    content_parts.append(f"  ⚠️ {err}")

            content_parts.append("")
            content_parts.append(f"⏱️ 执行耗时: {int(duration)}秒")
            content_parts.append(f"🕐 完成时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

            content = "\n".join(content_parts)

            # 青龙渠道（本地运行且未配置 config/notification.json 时自动跳过）
            send_notification(title=title, content=content, sound=sound)

            # 本机桌面通知：只推送失败/部分成功，避免每天打扰
            if failed_count > 0:
                brief = "；".join(
                    f"{r.get('account_name')}: {(r.get('error') or r.get('message') or '失败')[:40]}"
                    for r in results if not r.get('success')
                )
                notify_local(title, brief)

        except Exception as e:
            logger.error(f"发送通知失败: {e}")


def main() -> int:
    """主函数"""
    start_time = datetime.now()

    logger.info("="*60)
    logger.info(f"叮咚买菜签到任务开始执行 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*60)

    try:
        manager = DingdongSignInManager()
        results = manager.sign_in_all_accounts()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print(f"\n{'='*60}")
        print(f"## 叮咚买菜签到任务完成")
        print(f"## 结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"## 执行耗时: {int(duration)} 秒")
        print(f"{'='*60}\n")

        logger.info("="*60)
        logger.info(f"叮咚买菜签到任务执行完成 - {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"执行耗时: {int(duration)} 秒")
        logger.info("="*60)

        if results:
            manager.send_notification(results, start_time, end_time)

        total_count = len(results)
        success_count = sum(1 for r in results if r.get('success'))
        failed_count = total_count - success_count

        print(f"📊 签到总结:")
        print(f"   ✅ 成功: {success_count} 个账号")
        print(f"   ❌ 失败: {failed_count} 个账号")
        print(f"   📈 总计: {total_count} 个账号\n")

        if failed_count > 0:
            return 1 if success_count == 0 else 2
        return 0

    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.error(f"签到任务执行异常: {str(e)}", exc_info=True)

        print(f"\n{'='*60}")
        print(f"## ❌ 签到任务执行异常")
        print(f"## 错误信息: {str(e)}")
        print(f"## 结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"## 执行耗时: {int(duration)} 秒")
        print(f"{'='*60}\n")

        notify_local("叮咚买菜签到异常 ❌", str(e)[:100])
        try:
            send_notification(
                title="叮咚买菜签到任务异常 ❌",
                content=(
                    f"❌ 任务执行异常\n"
                    f"💬 错误信息: {str(e)}\n"
                    f"⏱️ 执行耗时: {int(duration)}秒\n"
                    f"🕐 完成时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}"
                ),
                sound=NotificationSound.ALARM
            )
        except Exception:
            pass

        return 1


if __name__ == '__main__':
    sys.exit(main())
