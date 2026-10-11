# 追剧更新提醒

入口：`script/tmdb/main.py`

剧源来自 TMDB 账号的「在看列表」，由青龙定时触发，
每次跑发现某部剧的集数往前推进了就把更新卡片推到 Telegram 群。

## ✨ 功能特性

- 📺 **剧源自动同步**：直接读 TMDB 在看列表，加剧/删剧不用改脚本
- 🔀 **兜底剧单**：没配令牌时回退到脚本内 `TRACKED_SHOWS`，可按名称搜索或直接写 TMDB ID
- 🔔 **首次执行逐部确认**：进度文件为空时给每部剧各推一张「新关注提醒」卡片（当前最新一集），之后转入只推更新的模式
- 🔕 **不误报**：之后新加进列表的剧只记录进度不推送，避免刚加剧就收到「更新啦」
- 🕘 **漏跑可补**：进度存在本地文件，脚本停几天再跑会把期间新出的集数一次性补报
- 🚦 **自带限流兜底**：每两条推送间隔 3 秒，撞上 Telegram 429 会按 `retry_after` 自动重试
- 🧪 **可预演**：`--dry-run` 只打印不推送、不写进度，方便验证判定逻辑
- 🔁 **可用 `--list` / `--reset`**：只看剧源、或清空进度重新初始化

## 🗂 目录结构

单文件实现，全部逻辑集中在 `script/tmdb/main.py`：

- `Notifier`：推送适配，优先脚本自带 Telegram 凭据，否则回退到项目统一推送层 `notification.py`
- `EpisodeTracker`：读配置 → 拉列表 → 取详情 → 判定 → 写进度 → 推送

## 📦 依赖

```bash
pip install requests
```

## ⚙️ 配置说明

在项目根目录 `config/token.json` 的 `tmdb` 节点下配置：

```json
{
  "tmdb": {
    "access_token": "TMDB v4 读访问令牌",
    "api_key": "TMDB v3 API 密钥",
    "account_id": "14895713",
    "options": {
      "language": "zh-CN",
      "list_type": "watchlist",
      "notify_when_empty": false
    },
    "notify": {
      "bot_token": "911654878:AAE...",
      "chat_id": "-1001387319088",
      "api_host": "",
      "proxy": ""
    }
  }
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `access_token` | 二选一 | TMDB v4 读访问令牌，走 `Authorization: Bearer`，**优先使用**；配了它才启用在看列表模式 |
| `api_key` | 二选一 | TMDB v3 API 密钥，走 query 参数 |
| `account_id` | 否 | TMDB 账号数字 ID，不填脚本自动调 `/account` 查一次 |
| `notify.bot_token` | 否 | 推送用的 Telegram Bot Token |
| `notify.chat_id` | 否 | 推送目标，群组用负数 ID（如 `-1001387319088`） |
| `notify.api_host` | 否 | 自建 Bot API 反代域名，留空走 `api.telegram.org` |
| `notify.proxy` | 否 | 如 `socks5h://127.0.0.1:1080` |

> `notify` 配了就直连 Telegram，消息原样发送。
> 没配则回退到项目统一推送层 `notification.py`，走青龙环境变量或
> `config/notification.json` 里已启用的渠道；两边都没有可用渠道时脚本会记错误日志。

### options 说明

| 开关 | 默认 | 说明 |
|---|---|---|
| `language` | `zh-CN` | 剧名 / 集名返回语言 |
| `notify_when_empty` | `false` | 无更新时是否也推一条「今天没有更新」（预留） |

### 凭证获取

1. **读访问令牌 / API 密钥**：登录 <https://www.themoviedb.org/settings/api> 申请（免费）
2. **account_id**：可留空让脚本自动查；也可访问 <https://www.themoviedb.org/account> 看
3. **Bot Token**：找 [@BotFather](https://t.me/BotFather) 创建机器人
4. **chat_id**：把机器人拉进群，在群里发一条消息，然后访问
   `https://api.telegram.org/bot<TOKEN>/getUpdates` 取 `chat.id`（群组是负数）

## 🚀 使用方法

```bash
python script/tmdb/main.py            # 正常跑
python script/tmdb/main.py --dry-run  # 只打印不推送（不写进度）
python script/tmdb/main.py --list     # 只列当前剧集来源
python script/tmdb/main.py --reset    # 清空进度，下次跑重新初始化
```

青龙 cron：`30 21,9,13 * * *`

## 🔍 判定逻辑

```
首次执行（进度文件为空）：
    给每部剧静默建立基线（历史已播集标记为已读），
    并推送一次「新关注提醒」（当前最新一集）

之后的每一次：
对每部剧：
    回看最近 MAX_RECENT_SEASONS 季的每一集
    air_date > 今天        →  跳过（还没播）
    (季, 集) 已在进度里    →  跳过
    首次见到这部剧          →  只记录，不推送
    其余（已播且未通知）    →  推送更新卡片，写入进度
```

进度文件：`config/tmdb/watch_state.json`

```json
{
  "version": 1,
  "updated_at": "2026-10-11T19:27:23",
  "shows": {
    "108978": {
      "name": "侠探杰克",
      "notified": ["S1E1", "S1E2", "S4E8"]
    }
  }
}
```

> 想重新开始追踪，删掉这个文件或跑 `--reset` 即可。
> 注意 `--reset` 之后的下一次跑会当成首次执行，把每部剧各推一张卡片。

进度写入用「先写临时文件 + `fsync` + `os.replace`」，中途被杀掉不会留下半截文件。

## 📨 推送文案

有更新时（示例，实际内容按剧集信息生成）：

```
📺 追剧更新提醒
《侠客行》更新啦！
第 1 季 第 4 集：双面棋盘
播出日期：2026-09-27
#追剧更新
```

首次把一部剧加入跟踪时发的是「新关注提醒」，抬头不同，避免误以为是新集：

```
🎬 新关注提醒
《侠客行》已加入追剧跟踪
当前最新：第 1 季 第 4 集：双面棋盘
播出日期：2026-09-27
#追剧更新
```

## 🔌 接口说明

| 用途 | 接口 |
|---|---|
| 账号信息 | `GET /account` |
| 在看列表 | `GET /account/{account_id}/watchlist/tv?page=N&sort_by=created_at.asc` |
| 搜索剧集 | `GET /search/tv?query=...` |
| 剧集详情 | `GET /tv/{id}` |
| 季详情 | `GET /tv/{id}/season/{n}` |

## ⚠️ 已知限制

- **天数判定**：用 `air_date <= 今天` 而不是 `== 今天`。TMDB 的 `air_date` 按剧集出品国日期算，
  美剧标 `10-01`、而我们这边跑的时候美东还没播，严格等于当天会让美剧永远推不出来，
  所以实际体感是「当天或次日」推一次。
- **回看窗口**：每部剧只回看最近 `MAX_RECENT_SEASONS` 季，超长的老剧早期季不会补报。
- **只有播出日期**：TMDB 不提供精确到分钟的播出时间，也无法区分「已上线流媒体」和「已电视播出」。

---

**免责声明**：本脚本仅供学习交流使用，使用产生的一切后果由使用者自行承担。
