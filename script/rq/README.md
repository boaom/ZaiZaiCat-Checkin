# RQ 跑步商自动签到脚本

RQ 跑步商（[runningquotient.cn](https://rq.runningquotient.cn)）每日签到，支持多账号与推送通知。

## ✨ 功能特性

- 🔐 多账号支持，依次处理
- 📅 签到前先查签到日历，已签到直接跳过
- 🍪 仅依赖 Cookie，无需签名、无需验证码
- 🔔 推送执行结果通知（成功 / 已签到 / 失败分别标识）
- 🛡️ 登录态失效时给出明确提示，不会静默失败

## 📦 依赖

```bash
pip install requests
```

## ⚙️ 配置说明

在项目根目录 `config/token.json` 的 `rq` 节点下配置：

```json
{
  "rq": {
    "accounts": [
      {
        "account_name": "主号",
        "cookies": "PHPSESSID=xxxxxxxxxxxxxxxxxxxxxxxx",
        "user_agent": ""
      }
    ]
  }
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `account_name` | 否 | 账号备注名 |
| `cookies` | 是 | 抓包得到的 Cookie，至少包含 `PHPSESSID` |
| `user_agent` | 否 | 不填使用内置的 App 内嵌 WebView UA |

### Cookie 获取方法

1. 打开 App 里的「签到」页面（H5 页面 `/Minisite/SignIn/index.html`）
2. 抓包工具（Charles / ProxyPin 等）找到任意 `rq.runningquotient.cn` 的接口请求
3. 复制请求头里的完整 `Cookie`，只要包含 `PHPSESSID` 即可

> 该站点只用 `PHPSESSID` 做鉴权，是 PHP 会话。**会话过期后需要重新抓包更新**，
> 脚本检测到过期会提示「登录已过期，请重新登录」。

## 🚀 使用方法

```bash
python main.py
```

脚本流程：

1. 加载 `config/token.json` 里的所有账号
2. 调 `get_sign_day_list` 确认今日是否已签到
3. 未签到则调 `sign_in` 执行签到
4. 输出统计并推送通知

## 🔌 接口说明

抓包自 App 内嵌 H5 页面，均为 `POST`，路径尾部带随机数防缓存：

| 用途 | 接口 |
|---|---|
| 签到日历 | `/MiniApi/SignIn/get_sign_day_list/rand/<随机数>` |
| 执行签到 | `/MiniApi/SignIn/sign_in/rand/<随机数>` |

签到返回：

```jsonc
// 签到成功
{"status": 1, "total_days": 197, "now_periods": 1, "now_continuity_periods": 1,
 "running_days": 59, "next_days": 2, "gain_amount": 0, "total_amount": "53"}

// 今日已签到
{"status": 10009, "error": "今日已签到(2026-10-01 14:04:35)"}

// 登录态失效
{"status": 10001, "error": "登录已过期，请重新登录"}
```

## 📊 输出示例

```
📌 正在获取签到日历...
✅ 签到成功，累计 197 天，本期连续 1 天
📊 签到总结:
   ✅ 成功: 1 个账号
   ❌ 失败: 0 个账号
```

---

**免责声明**：本项目仅供学习交流使用，请勿用于非法用途。使用本脚本产生的一切后果由使用者自行承担。
