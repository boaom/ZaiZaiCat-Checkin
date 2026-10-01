#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
new Env('RQ跑步商签到');
cron: 0 9 * * *
"""
"""
RQ 跑步商自动签到脚本

功能：
1. 从 config/token.json 读取账号信息
2. 支持多账号管理
3. 先查签到日历确认今日状态，再执行签到
4. 推送执行结果通知

配置节点：rq.accounts
必填字段：cookies（至少包含 PHPSESSID）
可选字段：user_agent

Author: ZaiZaiCat
Date: 2026-10-01
"""

import json
import logging
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
from api import RQAPI

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RQSignInManager:
    """RQ 跑步商签到管理器"""

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
        self.site_name = "RQ跑步商"
        self.accounts = []
        self.load_config()

    def load_config(self) -> None:
        """加载配置文件"""
        try:
            logger.info(f"正在读取配置文件: {self.config_path}")
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            self.accounts = config.get('rq', {}).get('accounts', [])

            if not self.accounts:
                logger.warning("配置文件中没有找到 RQ 跑步商账号信息")
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

        logger.info(f"开始执行账号 [{account_name}] 的签到...")

        if not cookies:
            error_msg = "cookies为空"
            logger.error(f"账号 [{account_name}] {error_msg}")
            return {'account_name': account_name, 'success': False, 'error': error_msg}

        api = RQAPI(cookies, user_agent)
        try:
            # 先查今日状态，已签到就直接跳过；查询失败则仍尝试签到
            # （签到接口会返回真实原因，如“登录已过期”）
            status = api.get_today_status()
            if status and status.get('signed'):
                logger.info(f"今日（{status.get('day_time')}）已签到，跳过")
                result = {
                    'success': True,
                    'already': True,
                    'message': f"今日（{status.get('day_time')}）已签到",
                }
            else:
                result = api.sign_in()
                time.sleep(1)

            result['account_name'] = account_name
            if result.get('success'):
                logger.info(f"账号 [{account_name}] 处理完成")
            else:
                logger.error(f"账号 [{account_name}] 签到失败: {result.get('message') or result.get('error')}")
            return result

        except Exception as e:
            error_msg = f"签到异常: {str(e)}"
            logger.error(f"账号 [{account_name}] {error_msg}", exc_info=True)
            return {'account_name': account_name, 'success': False, 'error': error_msg}
        finally:
            api.close()

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

            # 账号间隔，避免请求过于密集
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

            content_parts.append("")
            content_parts.append(f"⏱️ 执行耗时: {int(duration)}秒")
            content_parts.append(f"🕐 完成时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

            send_notification(title=title, content="\n".join(content_parts), sound=sound)

        except Exception as e:
            logger.error(f"发送通知失败: {e}")


def main() -> int:
    """主函数"""
    start_time = datetime.now()

    logger.info("="*60)
    logger.info(f"RQ跑步商签到任务开始执行 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*60)

    try:
        manager = RQSignInManager()
        results = manager.sign_in_all_accounts()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print(f"\n{'='*60}")
        print(f"## RQ跑步商签到任务完成")
        print(f"## 结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"## 执行耗时: {int(duration)} 秒")
        print(f"{'='*60}\n")

        logger.info("="*60)
        logger.info(f"RQ跑步商签到任务执行完成 - {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
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

        try:
            send_notification(
                title="RQ跑步商签到任务异常 ❌",
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
