# 顺丰速运积分任务自动化

顺丰会员中心每日签到 + 积分任务自动完成，支持多账号。

## ✨ 功能特性

- 📅 **每日签到**：`integralSignV2Service~sign`，先查今日状态再签
- 🎯 **积分任务**：拉取任务列表，自动完成「页面浏览 / 页面点击」类任务并领积分
- 🍪 靠分享链接里的 `sign` 换会话 Cookie，**不需要手工复制 Cookie**
- 🔐 请求头 `signature` 为 MD5 计算，`sw8` 由本地 JS（`code.js`）生成，无需外部服务
- 🔔 推送执行结果通知（含积分余额）

## 📦 依赖

```bash
pip install requests PyExecJS
```

还需要本机有 **Node.js**（`PyExecJS` 会调用它执行 `code.js`）。

## ⚙️ 配置说明

在项目根目录 `config/token.json` 的 `sf` 节点下配置：

```json
{
  "sf": {
    "accounts": [
      {
        "account_name": "大号",
        "sign": "分享链接里的 sign 值",
        "user_id": "",
        "user_agent": "",
        "channel": "appqiandao",
        "device_id": ""
      }
    ]
  }
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `account_name` | 否 | 账号备注名 |
| `sign` | 是 | 分享链接里的 `sign` 参数值（见下方获取方法） |
| `channel` | 是 | 请求头 `channel`，签到场景固定填 `appqiandao` |
| `device_id` | 是 | 请求体里的 `deviceId`，抓包时用的那个值即可 |
| `user_id` | 否 | 仅用于通知里区分账号，不参与请求 |
| `user_agent` | 否 | 不填使用内置 App 内嵌 WebView UA |

### sign 获取方法

1. 打开顺丰 App → 我的 → 积分，进入会员中心页面
2. 抓包工具（Charles / ProxyPin 等）找到 `mcs-mimp-web.sf-express.com` 的
   **`/mcs-mimp/share/app/shareRedirect?sign=...`** 请求（进页面时第一个请求）
3. 复制 URL 里 `sign=` 后面的值（很长，约 344 字符，**注意不要漏掉末尾的 `%3D%3D`**）
4. 同一个请求的请求头里取 `channel`（`appqiandao`），
   紧接着的 `queryPointTaskAndSignFromES` 请求体里取 `deviceId`

> `sign` 有效期通常为几天到两周，失效后脚本会提示「分享登录失败」，重新抓一次即可。
> 换 `sign` 时 `device_id` 不用跟着换。

## 🚀 使用方法

```bash
python script/sf/main.py
```

脚本流程：

1. 读 `config/token.json` 里的所有账号
2. `share/app/shareLogin` 用 `sign` 换取 `_login_user_id_` / `sessionId` 等 Cookie
3. `integralSignV2Service~getTodaySign` 查状态 → 未签则 `sign`
4. `integralTaskStrategyService~queryPointTaskAndSignFromES` 拉任务列表
5. 逐个完成任务：`finishTask` → `fetchTasksReward` 领积分
6. 查询积分余额，输出统计并推送通知

> 单账号跑完约 2~3 分钟，任务之间内置 10~15 秒随机延时，**不要缩短**，否则容易触发风控。

## 🔌 接口说明

均走 `https://mcs-mimp-web.sf-express.com`，`POST` + JSON：

| 用途 | 路径 |
|---|---|
| 分享登录 | `/mcs-mimp/share/app/shareLogin` |
| 分享跳转登录 | `/mcs-mimp/share/app/shareRedirect` |
| 查任务与签到 | `/mcs-mimp/commonPost/~memberNonactivity~integralTaskStrategyService~queryPointTaskAndSignFromES` |
| 今日签到状态 | `/mcs-mimp/commonPost/~memberNonactivity~integralSignV2Service~getTodaySign` |
| 执行签到 | `/mcs-mimp/commonPost/~memberNonactivity~integralSignV2Service~sign` |
| 完成任务 | `/mcs-mimp/commonPost/~memberNonactivity~integralTaskStrategyService~finishTask` |
| 领取任务积分 | `/mcs-mimp/commonPost/~memberNonactivity~integralTaskStrategyService~fetchTasksReward` |
| 用户积分信息 | `/mcs-mimp/commonPost/~memberIntegral~userInfoService~queryUserInfo` |

请求头里的三个动态字段：

| 头 | 生成方式 |
|---|---|
| `timestamp` | 当前毫秒时间戳 |
| `signature` | `md5("wwesldfs29aniversaryvdld29&timestamp=<ts>&sysCode=MCS-MIMP-CORE")` |
| `sw8` | 本地执行 `code.js` 里的 `get_sw8(path)` |

## 🚫 已知限制

任务列表里 `taskType` 非日常的任务（如「用行业模板寄件下单」「每月累计寄件」「参与积分活动」）
需要真实业务行为，脚本会打印「非日常任务，跳过」，不计入失败。

## 📊 输出示例

```
[主号] 分享登录成功，已获取用户信息
[主号] 签到完成，延时 4.14 秒后继续任务...
获取到 18 个任务
[主号] 任务 去看看生活服务 完成成功
[主号] 任务奖励获取结果: {'success': True, 'obj': [{'pageType': '页面浏览/浏览生活服务', 'pageStatus': 3, 'point': 2}]}
...
[主号] 当前积分: 26
```

---

**免责声明**：本脚本仅供学习交流使用，使用产生的一切后果由使用者自行承担。
