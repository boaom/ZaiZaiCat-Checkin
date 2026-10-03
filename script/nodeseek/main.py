#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
new Env('NodeSeek 签到');
cron: 30 8 * * *
"""
"""
NodeSeek 自动签到脚本

功能：
1. 从 config/token.json 读取账号信息
2. 支持多账号管理
3. 调用 /api/attendance 完成每日签到
4. 推送执行结果通知

配置节点：nodeseek.accounts
必填字段：cookies
可选字段：user_agent、proxy

Author: ZaiZaiCat
Date: 2026-10-03
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from notification import send_notification, NotificationSound

# 导入API模块（当前目录）
from api import NodeSeekAPI

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NodeSeekSignInManager:
    """NodeSeek 签到管理器"""

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
        self.site_name = "NodeSeek"
        self.accounts = []
        self.load_config()

    def load_config(self) -> None:
        """加载配置文件"""
        try:
            logger.info(f"正在读取配置文件: {self.config_path}")
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            self.accounts = config.get('nodeseek', {}).get('accounts', [])

            if not self.accounts:
                logger.warning("配置文件中没有找到 NodeSeek 账号信息")
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
        account_name = account.get('account_name', '未命名账号')
        cookies = account.get('cookies', '')
        user_agent = account.get('user_agent')
        proxy = account.get('proxy')

        logger.info(f"开始执行账号 [{account_name}] 的签到...")

        if not cookies:
            error_msg = "cookies为必填项，请检查配置"
            logger.error(f"[{account_name}] {error_msg}")
            return {
                'account_name': account_name,
                'success': False,
                'error': error_msg,
            }

        api = NodeSeekAPI(cookies, user_agent=user_agent, proxy=proxy)
        result = api.sign_in()

        return {
            'account_name': account_name,
            'success': result.get('success', False),
            'result': result.get('result'),
            'error': result.get('error'),
        }

    def sign_in_all_accounts(self) -> List[Dict[str, Any]]:
        """
        所有账号签到

        Returns:
            List[Dict]: 所有账号的签到结果
        """
        results = []

        if not self.accounts:
            logger.warning("没有可用的账号配置")
            return results

        logger.info(f"开始执行 {len(self.accounts)} 个账号的签到任务")

        for index, account in enumerate(self.accounts, start=1):
            logger.info(f"处理第 {index}/{len(self.accounts)} 个账号")
            try:
                result = self.sign_in_single_account(account)
                results.append(result)

                if result.get('success'):
                    logger.info(f"[{result['account_name']}] 签到成功")
                else:
                    logger.error(f"[{result['account_name']}] 签到失败: {result.get('error')}")

            except Exception as e:
                account_name = account.get('account_name', '未命名账号')
                logger.error(f"[{account_name}] 签到异常: {e}", exc_info=True)
                results.append({
                    'account_name': account_name,
                    'success': False,
                    'error': f"签到异常: {e}",
                })

        return results

    def send_notification(self, results: List[Dict[str, Any]],
                          start_time: datetime, end_time: datetime) -> None:
        """
        发送签到结果通知

        Args:
            results: 签到结果列表
            start_time: 任务开始时间
            end_time: 任务结束时间
        """
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
                api_result = result.get('result') or {}

                if result.get('success'):
                    message = api_result.get('message', '签到成功')
                    gain = api_result.get('gain')
                    if gain:
                        message = f"{message}（+{gain} 鸡腿）"
                    if len(message) > 60:
                        message = message[:60] + "..."
                    prefix = "🔁" if api_result.get('already') else "✅"
                    content_parts.append(f"  {prefix} [{account_name}] {message}")
                else:
                    error = result.get('error', '未知错误')
                    if len(error) > 60:
                        error = error[:60] + "..."
                    content_parts.append(f"  ❌ [{account_name}] {error}")

            content_parts.append("")
            content_parts.append(f"⏱️ 执行耗时: {int(duration)}秒")
            content_parts.append(f"🕐 完成时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

            send_notification(
                title=title,
                content="\n".join(content_parts),
                sound=sound
            )

        except Exception as e:
            logger.error(f"发送通知失败: {e}")


def main() -> int:
    """主函数"""
    start_time = datetime.now()

    logger.info("="*60)
    logger.info(f"NodeSeek签到任务开始执行 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*60)

    try:
        manager = NodeSeekSignInManager()
        results = manager.sign_in_all_accounts()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print(f"\n{'='*60}")
        print(f"## NodeSeek签到任务完成")
        print(f"## 结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"## 执行耗时: {int(duration)} 秒")
        print(f"{'='*60}\n")

        logger.info("="*60)
        logger.info(f"NodeSeek签到任务执行完成 - {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
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
                title="NodeSeek签到任务异常 ❌",
                content=(
                    f"❌ 任务执行异常\n"
                    f"💬 错误信息: {str(e)}\n"
                    f"⏱️ 执行耗时: {int(duration)}秒\n"
                    f"🕐 完成时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}"
                ),
                sound=NotificationSound.ALARM
            )
        except:
            pass

        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)

