# 叮咚买菜自动签到脚本

叮咚买菜每日签到 + 积分任务 + 农场（鱼塘）自动领饲料喂鱼，支持多账号与推送通知。

## ✨ 功能特性

- 📅 **积分签到**：先查积分首页确认状态，未签到才调签到接口
- 🎯 **积分中心任务**：自动完成「浏览 XX 秒」类任务领积分
- 🌾 **农场任务领饲料**：遍历农场任务，能领的奖励全领一遍
- 🐟 **自动喂鱼**：饲料 ≥ 10g 时自动喂食，推进鱼苗成长
- 🎴 **天天翻牌**：可选，默认关闭（消耗 5g 饲料换随机奖品）
- 🍪 仅依赖 Cookie，**无签名、无加密、无验证码**
- 🔔 推送执行结果通知（本机运行时失败才弹 macOS 通知）

## 📦 依赖

```bash
pip install requests
```

## ⚙️ 配置说明

在项目根目录 `config/token.json` 的 `dingdong` 节点下配置：

```json
{
  "dingdong": {
    "accounts": [
      {
        "account_name": "主号",
        "cookies": "DDXQSESSID=xxxxxxxxxxxxxxxxxxxxxxxx",
        "uid": "69cbf691399ce6002f8ae388",
        "station_id": "5bf2907a716de100468c6ca3",
        "city_name": "上海市",
        "city_number": "0101",
        "latitude": 31.271817,
        "longitude": 121.540474,
        "device_id": "6ae17b9e621d2d61adaa92168e95110e",
        "device_token": "BFAl0aNr...==",
        "os_version": "13",
        "native_version": "13.10.2"
      }
    ],
    "options": {
      "sign_in": true,
      "farm_reward": true,
      "farm_feed": true,
      "farm_achieve": true,
      "mission": true,
      "lucky_draw": false
    }
  }
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `account_name` | 否 | 账号备注名 |
| `cookies` | 是 | 抓包得到的 Cookie，至少包含 `DDXQSESSID` |
| `uid` / `station_id` | 建议 | 农场与积分任务接口的必带元数据 |
| `city_number` / `city_name` | 建议 | 城市编码，上海为 `0101` |
| `latitude` / `longitude` | 建议 | 定位，接口会带上 |
| `device_id` / `device_token` | 建议 | 设备标识，农场接口会带进请求头 |
| `os_version` / `native_version` | 否 | App 版本号 |
| `user_agent` | 否 | 不填使用内置的 App 内嵌 WebView UA |

### 开关说明（`options`）

| 开关 | 默认 | 说明 |
|---|---|---|
| `sign_in` | `true` | 积分签到 |
| `farm_reward` | `true` | 农场任务领饲料 |
| `farm_feed` | `true` | 饲料 ≥ 10g 时自动喂鱼 |
| `farm_achieve` | `true` | 尝试直接标记浏览类农场任务完成（见下方「已知限制」） |
| `mission` | `true` | 积分中心浏览类任务 |
| `lucky_draw` | `false` | 天天翻牌，每次消耗 5g 饲料，净收益不确定 |

### Cookie 获取方法

1. 打开叮咚买菜 App，进「我的 → 积分」或「鱼塘」页面
2. 抓包工具（Charles / ProxyPin 等）找到任意 `ddxq.mobi` 的接口请求
3. 复制请求头里的完整 `Cookie`，只要包含 `DDXQSESSID` 即可

> 该站点只用 `DDXQSESSID` 做鉴权，**会话过期后需要重新抓包更新**。
> 脚本检测到 `code=1111` 会提示「访问已过期，请重新登录」。

## 🚀 使用方法

```bash
python main.py
```

脚本流程：

1. 加载 `config/token.json` 里的所有账号
2. 调 `point/home` 确认今日是否已签到，未签到则调 `user/signin/`
3. 农场：`task/list` 列出任务 → 逐个 `task/reward` 领饲料
4. 农场：饲料 ≥ 10g 则 `props/feed` 喂鱼
5. 积分中心：`searchUnCompleteMissionByUserId` 列未完成任务 →
   `createUserMission` 领取 → `notice` 上报完成
6. 输出统计并推送通知

## 🔌 接口说明

抓包自 App 内嵌 H5 页面，**全部为 GET/POST + Cookie 鉴权，无签名**。

### 积分签到（`maicai` / `sunquan`）

| 用途 | 接口 |
|---|---|
| 签到状态 | `GET https://maicai.api.ddxq.mobi/point/home` |
| 执行签到 | `POST https://sunquan.api.ddxq.mobi/api/v2/user/signin/` |

返回码：`0` 成功 / `1111` 登录态失效 / `500` 操作频繁。

### 积分中心任务（`gw.api.ddxq.mobi/promomission-service`）

| 用途 | 接口 |
|---|---|
| 未完成任务列表 | `POST /mission/search/v1/searchUnCompleteMissionByUserId` |
| 领取任务 | `POST /mission/search/new/createUserMission` |
| 上报完成 | `POST /mission/notice/v1/notice` |

> ⚠️ 坑：`createUserMission` 的 body 字段名叫 `missionId`，但实际要传列表项里的 `id`
> （列表里另有一个真正的 `missionId` 字段，传错会返回 `119000010 参数无效`）。

### 农场 / 鱼塘（`farm.api.ddxq.mobi`）

| 用途 | 接口 |
|---|---|
| 任务列表 | `GET /api/v2/task/list` |
| 标记任务完成 | `GET /api/v2/task/achieve?taskCode=xxx` |
| 领取任务奖励 | `GET /api/v2/task/reward?userTaskLogId=xxx` |
| 饲料存量 | `GET /api/v2/props/list` |
| 鱼苗列表 | `GET /api/v2/seed/list` |
| 喂食 | `GET /api/v2/props/feed?propsId=xxx&seedId=xxx` |
| 好友列表（偷饲料） | `GET /api/v2/friend/list` |
| 天天翻牌状态 | `GET /api/v2/lucky-draw-activity/info` |
| 天天翻牌抽奖 | `GET /api/v2/lucky-draw-activity/draw` |

`task/reward` 返回码：

| 码 | 含义 | 处理 |
|---|---|---|
| `0` | 领取成功 | 计入本次收益 |
| `810` | 已领取过 | 幂等，忽略 |
| `811` | 奖励已过期（当天未领次日作废） | 忽略 |
| `820` | 不可领取 | 忽略 |

> ⚠️ `task/list` 里的 `buttonStatus` 是**服务端缓存值**，不代表当前能否领奖，
> 必须以 `task/reward` 的返回码为准。所以脚本对每个带 `userTaskLogId` 的任务都试一遍。

## 🚫 已知限制

以下任务**无法**自动化，脚本会跳过：

| 任务 | 原因 |
|---|---|
| `ANY_ORDER` / `BUY_GOODS` / `MULTI_ORDER` | 需要真实下单 |
| `INVITE_ASSIST` | 需要好友助力 |
| `STEAL_FEED` | 需要好友列表非空，且对方有饲料 |
| 积分中心的 `share` 类任务 | 需要分享行为 |
| `LOTTERY` 三餐开福袋 | 只在饭点开放 |

`farm_achieve` 开关对应「直接调 `task/achieve` 标记浏览类任务完成」。
实测未完成的下单类任务会返回 `850 此任务不可手动完成`，
而浏览类任务返回 `601 今日已完成`，**服务端是否校验浏览时长尚未验证**，
需要观察次日运行结果。若发现无效可把该开关关掉。

## ⚠️ 部署注意

- **必须在国内网络环境运行**。叮咚有 IP 风控，海外 VPS（如东京）会直接触发风控，
  因此本脚本按「本机执行」设计，青龙订阅里已把 `dingdong` 加进黑名单。
- 接口有限流，脚本内已内置 1~3 秒间隔，**不要缩短**。

## 📊 输出示例

```
📌 正在查询签到状态...
🔁 今日已签到，连续第 1 天，当前 95 积分
✅ 农场领奖 [参与天天翻牌活动] +5g饲料
⏭️ 饲料不足（7g），跳过喂食
📊 签到总结:
   ✅ 成功: 1 个账号
   ❌ 失败: 0 个账号
```

---

**免责声明**：本项目仅供学习交流使用，请勿用于非法用途。使用本脚本产生的一切后果由使用者自行承担。
