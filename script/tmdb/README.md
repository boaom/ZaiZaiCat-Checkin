# 追剧更新提醒

从 TMDB 账号的「在看列表」拉剧源，由青龙定时触发，
每次跑发现某部剧的集数往前推进了就把更新卡片推到 Telegram 群。

## ✨ 功能特性

- 📺 **剧源自动同步**：直接读 TMDB 在看列表，加剧/删剧不用改脚本
- 🔕 **不误报**：第一次见到某部剧只记录进度不推送，避免刚加进列表就收到「更新啦」
- 🕘 **漏跑可补**：进度存在本地文件，脚本停几天再跑会把期间新出的集数一次性补报
- ⚡ **并发拉取**：64 部剧约 7 秒跑完
- 🧪 **可预演**：`--dry-run` 只打印不推送、不写进度，方便验证判定逻辑
- 🛡️ **进度不丢**：代际备份 + checksum 自校验，主文件被写坏自动退回上一代
- 🔁 接口带 429 / 5xx 重试，单部剧拉取失败不影响其他剧

## 🗂 模块划分

| 文件 | 职责 |
|---|---|
| `main.py` | CLI 与编排（青龙入口，路径不要改） |
| `tracker.py` | 更新判定，纯逻辑不碰网络和文件 |
| `state.py` | 进度持久化（代际备份 + 自校验 + 旧格式迁移） |
| `notify.py` | 推送适配 |
| `message.py` | 推送文案 |
| `api.py` | TMDB 接口封装 |
| `tests/` | 单测 |

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
      "max_workers": 5,
      "notify_when_empty": false,
      "upcoming_days": 0
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
| `access_token` | 二选一 | TMDB v4 读访问令牌，走 `Authorization: Bearer`，**优先使用** |
| `api_key` | 二选一 | TMDB v3 API 密钥，走 query 参数 |
| `account_id` | 否 | TMDB 账号数字 ID，不填脚本自动调 `/account` 查一次 |
| `list_type` | 否 | `watchlist`（在看列表，默认）或 `list`（自定义列表） |
| `list_id` | 否 | `list_type=list` 时必填，取自列表页 URL `themoviedb.org/list/<id>` |
| `notify.bot_token` | 是 | 推送用的 Telegram Bot Token |
| `notify.chat_id` | 是 | 推送目标，群组用负数 ID（如 `-1001387319088`） |
| `notify.api_host` | 否 | 自建 Bot API 反代域名，留空走 `api.telegram.org` |
| `notify.proxy` | 否 | 如 `socks5h://127.0.0.1:1080` |

> `notify` 配了就直连 Telegram，消息原样发送。
> 没配则回退到项目统一推送层 `notification.py`，走青龙环境变量或
> `config/notification.json` 里已启用的渠道；两边都没有可用渠道时脚本会报错并返回非 0。

### options 说明

| 开关 | 默认 | 说明 |
|---|---|---|
| `language` | `zh-CN` | 剧名 / 集名返回语言 |
| `max_workers` | `5` | 并发拉剧集详情的线程数 |
| `notify_when_empty` | `false` | 无更新时是否也推一条「今天没有更新」 |
| `upcoming_days` | `0` | >0 时在卡片末尾附带 N 天内的待播预告 |

### 凭证获取

1. **读访问令牌 / API 密钥**：登录 <https://www.themoviedb.org/settings/api> 申请（免费）
2. **account_id**：可留空让脚本自动查；也可访问 <https://www.themoviedb.org/account> 看
3. **Bot Token**：找 [@BotFather](https://t.me/BotFather) 创建机器人
4. **chat_id**：把机器人拉进群，在群里发一条消息，然后访问
   `https://api.telegram.org/bot<TOKEN>/getUpdates` 取 `chat.id`（群组是负数）

> **不需要 OAuth 授权流程**。实测 `/account/{id}/watchlist/tv` 只要令牌本身属于该账号就能读，
> 不需要 `session_id`。

## 🚀 使用方法

```bash
python script/tmdb/main.py              # 正常跑
python script/tmdb/main.py --dry-run    # 只打印不推送（不写进度）
python script/tmdb/main.py --list       # 只列当前在看列表
python script/tmdb/main.py --reset      # 清空进度，下次跑重新初始化
```

青龙 cron：`0 20 * * *`（每天 20:00）

## 🔍 判定逻辑

```
对在看列表里的每一部剧：
    取 last_episode_to_air（TMDB 最近播出的一集）

    第一次见到这部剧  →  只记录 (季, 集) 到进度文件，不推送
    (季, 集) 和记录相同  →  跳过
    进度变了但 air_date 还没到  →  跳过（TMDB 会提前标好）
    进度变了且已播出  →  推送卡片，更新进度
```

进度文件：`config/tmdb/state.json`

```json
{
  "version": 1,
  "updated_at": "2026-10-01T20:00:00",
  "checksum": "shows 规范化 JSON 的 sha256",
  "shows": {
    "283319": {
      "season": 1,
      "episode": 4,
      "air_date": "2026-09-27",
      "name": "大理石厅谋杀案",
      "notified_at": "2026-10-01T15:17:09"
    }
  }
}
```

> 想重新开始追踪（比如清空后让所有剧重新初始化），删掉这个文件或跑 `--reset` 即可。

### 进度文件怎么保证不丢

- **原子写入**：先写临时文件、`fsync` 后再 `os.replace` 顶上，中途被杀掉不会留下半截文件。
- **代际备份**：每次保存前把 `state.json` → `state.json.1` → `state.json.2` 轮转，
  始终保留最近三代。
- **自校验**：每份文件都带 `checksum`（`shows` 规范化 JSON 的 sha256）。
  加载时从新到旧取第一份校验通过的，所以主文件被清空、截断、或内容被改坏都能自动恢复。
- **旧格式迁移**：首次运行发现老位置的 `config/tmdb_state.json` 会自动转换到新位置，
  旧文件原地保留不删。

三代全坏时会退化成空进度重新初始化（只会重新记录、不会误推）。

## 📨 推送文案

每部剧一条消息，格式如下（示例，实际内容按剧集信息生成）：

```
📺 追剧更新提醒
《大理石厅谋杀案》更新啦！
第 1 季 第 4 集：双面棋盘
播出日期：2026-09-27
#追剧更新
```

集名为空时省略 `：集名` 部分。多条消息之间间隔 1.5 秒，避免触发 Telegram 群限流。

## 🔌 接口说明

| 用途 | 接口 |
|---|---|
| 账号信息 | `GET /account` |
| 在看列表 | `GET /account/{account_id}/watchlist/tv?page=N&sort_by=created_at.desc` |
| 自定义列表 | `GET /list/{list_id}` |
| 剧集详情 | `GET /tv/{id}?append_to_response=next_episode_to_air,last_episode_to_air` |

## 🧪 测试

零额外依赖，用标准库 `unittest`：

```bash
python -m unittest discover -s script/tmdb/tests -t script/tmdb/tests -v
```

## ⚠️ 已知限制

- **时区差**：TMDB 的 `air_date` 按剧集出品国日期算。美剧标注的「今天」在美东才刚播，
  所以脚本用「`air_date` 已过 + 进度变化」判定，美剧通常会**晚一天**才推送——
  这时候确实已经能看了，不影响使用。
- **只有播出日期**：TMDB 不提供精确到分钟的播出时间，也无法区分「已上线流媒体」和「已电视播出」。
- **未开播的剧**：`last_episode_to_air` 为空，脚本会跳过，等首播后自动纳入。

---

**免责声明**：本脚本仅供学习交流使用，使用产生的一切后果由使用者自行承担。
