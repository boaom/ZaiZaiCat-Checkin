# ZaiZaiCat-Checkin 🐱

自用每日签到脚本,青龙签到脚本

> **⚠️ 免责声明**  
> 本项目中的大量代码由 AI 辅助编写生成，代码规范和格式可能存在不足之处，敬请见谅。  
> 本项目仅供学习交流使用，请勿用于商业用途。使用本项目所造成的一切后果由使用者自行承担。

## 📚 在线文档

项目介绍、部署方法、配置说明、脚本使用指南等内容已迁移至在线文档：
- https://cat-zaizai.github.io/ZaiZaiCat-Checkin-Docs/

## ✅ 脚本可用性状态

以下是各平台脚本的当前可用性状态：

| 平台           | 脚本路径 | 状态 | 说明                  |
|--------------|---------|------|---------------------|
| 🚚 顺丰速运      | `script/sf/main.py` | ✅ 可用 | 支持签到和积分任务           |
| 📱 恩山论坛      | `script/enshan/sign_in.py` | ✅ 可用 | 支持每日签到              |
| 🔐 看雪论坛      | `script/kanxue/sign_in.py` | ✅ 可用 | 支持每日签到              |
| 📺 上海杨浦      | `script/shyp/main.py` | ✅ 可用 | 支持任务列表和积分任务         |
| 🏢 华润通-万象星   | `script/huaruntong/999/main.py` | ✅ 可用 | 支持答题签到              |
| 💳 华润通-微信版   | `script/huaruntong/huaruntong_wx/main.py` | ✅ 可用 | 支持签到送积分             |
| 🛒 华润通-Ole'  | `script/huaruntong/ole/main.py` | ❌ 不可用 | 需要动态获取微信code换取token |
| 🎯 华润通-文体未来荟 | `script/huaruntong/wentiweilaihui/main.py` | ✅ 可用 | 支持签到和积分查询           |
| 👟 鸿星尔克      | `script/erke/main.py` | ✅ 可用 | 支持签到和积分明细查询         |
| 📝 WPS Office  | `script/wps/main.py` | ✅ 可用 | 任务中心签到+积分，天天领福利打卡+会员试用+抽奖（App 抓包 Cookie 可直接用） |
| 💰 什么值得买      | `script/smzdm/sign_daily_task/main.py` | ✅ 可用 | 支持每日签到、互动任务（浏览/关注）与众测申请；众测「任务活动」接口受腾讯验证码限制，已降级为直接申请众测商品 |
| 🤖 WorkBuddy    | `script/workbuddy/main.py` | ✅ 可用 | 支持每日签到、令牌自动续期与多账号管理 |
| 🐅 Trae CN       | `script/trae/main.py` | ✅ 可用 | 支持积分计费模式每日签到与多账号管理 |
| 🚀 Agent Router  | `script/agentrouter/main.py` | ✅ 可用 | 支持 OAuth 登录即签到、余额查询 |
| 🏃 RQ 跑步商      | `script/rq/main.py` | ✅ 可用 | 支持每日签到（仅需 PHPSESSID） |
| 🔓 吾爱破解      | `script/52pojie/main.py` | ✅ 可用 | 支持每日签到，内置网宿 WAF 挑战求解（依赖 curl_cffi） |
| 🎣 大潮 App      | `script/dachao/main.py` | ✅ 可用 | 账号密码登录流程，支持签到与「阅读有礼」抽奖 |
| 🥬 叮咚买菜      | `script/dingdong/main.py` | ✅ 可用 | 签到 + 积分中心任务 + 农场领饲料喂鱼，支持多账号 |
| 🎁 福利吧        | `script/fuliba/main.py` | ✅ 可用 | Discuz 论坛每日签到，自动获取 formhash |
| 📺 追剧更新提醒    | `script/tmdb/main.py` | ✅ 可用 | 读 TMDB 在看列表，集数推进时推 Telegram 卡片 |
| 🐱 NodeSeek     | `script/nodeseek/main.py` | ✅ 可用 | 每日签到领鸡腿，支持多账号与代理 |

### 状态说明

- ✅ **可用**: 脚本完整且功能正常，可以直接使用
- ⚠️ **部分可用**: 脚本基本可用，但可能存在某些功能限制
- 🚧 **开发中**: 脚本正在开发或测试阶段
- ❌ **不可用**: 脚本存在问题或已废弃

### 使用建议

1. **推荐使用**: 所有标记为"✅ 可用"的脚本都已经过测试，可以放心使用
2. **配置要求**: 使用前请确保在 `config/token.json` 中正确配置了相应平台的账号信息
3. **Cookie 有效期**: 建议定期更新 Cookie 等认证信息，以保证脚本正常运行
4. **测试建议**: 使用青龙命令拉取脚本可能会出现混乱的问题,建议直接clone整个项目到青龙的 scripts 目录下

## 📝 WPS 功能说明

WPS 脚本目前包含两个活动页面：

- `script/wps/task_center.py`：任务中心，支持签到、积分查询、抽奖
- `script/wps/daily_benefits.py`：天天领福利，支持打卡免费领会员、会员免费试用、天天抽奖
- `script/wps/main.py`：WPS 统一入口，按账号顺序依次执行上述两个页面任务

## 📝 WorkBuddy 功能说明

WorkBuddy（CodeBuddy）每日签到脚本，接口实现参考 [cockpit-tools](https://github.com/jlcodes99/cockpit-tools) 项目，与官方客户端行为保持一致：

- `script/workbuddy/api.py`：接口封装，签到状态查询（双端点回退）、每日签到、令牌刷新
- `script/workbuddy/import_accounts.py`：账号导入工具，一键导入官方 WorkBuddy 客户端当前登录账号（自动解密凭据库），也支持从 cockpit-tools 批量导入或指定 JSON 文件导入
- `script/workbuddy/main.py`：统一入口，多账号签到编排、令牌自动续期与结果推送

支持每日签到、连签奖励、多账号管理、令牌自动续期（access_token 60 天 / refresh_token 90 天，自动轮换续期）。详见 [script/workbuddy/README.md](script/workbuddy/README.md)。

## 📝 追剧更新提醒 功能说明

剧源来自 TMDB 账号的「在看列表」，由青龙定时触发，某部剧集数往前推进了就把更新卡片推到 Telegram 群：

- `script/tmdb/main.py`：CLI 与编排（青龙入口）
- `script/tmdb/tracker.py`：更新判定，纯逻辑不碰网络和文件
- `script/tmdb/state.py`：进度持久化，代际备份 + checksum 自校验 + 旧格式迁移
- `script/tmdb/notify.py`：推送适配；`message.py`：推送文案；`api.py`：TMDB 接口封装

首次执行（进度文件为空）会给每部剧各推一张「已纳入追踪」卡片，之后只推有更新的剧，一部剧一张。
详见 [script/tmdb/README.md](script/tmdb/README.md)。

## 📝 更新日志

### 2026-10-03
- ✨ **新增 NodeSeek 签到模块**（`script/nodeseek/`）:
  - 🐱 每日签到领鸡腿，接口 `POST /api/attendance?random=true`
  - 👥 多账号管理，账号配置在 `config/token.json` 的 `nodeseek.accounts`
  - 🛡️ 区分 Cookie 失效（401）、Cloudflare 拦截（403 / 非 JSON 响应）、重复签到与签到成功
  - 🔁 已签到按成功处理，通知里用 🔁 前缀区分
  - 🌐 支持按账号配置 `proxy`，应对 `cf_clearance` 与出口 IP 绑定的情况

### 2026-10-01
- 📺 **新增追剧更新提醒模块**（`script/tmdb/`）:
  - 📡 剧源直接读 TMDB 账号的「在看列表」，加剧/删剧不用改脚本
  - 🚀 首次执行给每部剧各推一张「已纳入追踪」卡片，之后只推集数往前推进的剧
  - 🕘 漏跑可补：进度存本地，脚本停几天再跑会把期间新出的集数一次性补报
  - 🛡️ 进度改为代际备份（`config/tmdb/state.json` + `.1` + `.2`）并带 checksum 自校验，主文件被写坏自动退回上一代
  - 🧩 拆成 `main` / `tracker` / `state` / `notify` / `message` / `api` 六个模块，判定逻辑抽成纯函数并补齐单测
  - 🚦 撞上 Telegram 429 时按 `retry_after` 自动等待重试
- ✨ **新增叮咚买菜、福利吧签到模块**
- 📝 状态表补齐此前遗漏的大潮 App、叮咚买菜、福利吧、追剧更新提醒
- 🛠 `notification.py` 的 `send()` / `send_notification()` 支持按次覆盖 Telegram 凭据并返回 `bool`，未配置任何渠道时不再静默失败

### 2026-09-12
- ✨ 新增 Trae CN、Agent Router 自动签到模块，详见各脚本子目录 README
- 🧹 精简账号配置并移除签到前自动同步逻辑，详见 `script/trae/README.md`、`script/workbuddy/README.md`

### 2026-09-06
- ✨ **新增 WorkBuddy(CodeBuddy) 自动签到模块**:
  - 📅 支持每日自动签到与连签奖励
  - 🔄 支持令牌过期自动刷新并回写配置
  - 📥 支持从官方 WorkBuddy 客户端一键导入账号（自动解密凭据库），也支持从 cockpit-tools 批量导入
  - ⏱️ 内置启动随机延迟与账号间随机间隔，自动错峰
  - 📊 签到结果通过统一推送模块通知

### 2026-03-11
- ✨ **WPS脚本升级为多页面任务**:
  - 🧩 新增 `任务中心` 独立页面脚本
  - 🎁 新增 `天天领福利` 页面脚本
  - 📅 支持 `打卡免费领会员`
  - 🪪 支持 `会员免费试用`
  - 🎰 支持 `天天抽奖`
  - 🔄 `script/wps/main.py` 统一执行两个页面任务

### 2025-12-18 
- ✨ **WPS脚本新增抽奖相关任务**:
  - 🎟️ 支持自动参与每日抽奖
  - 🎁 支持自动领取抽奖奖励
  - 📝 更新 WPS 脚本说明文档，加入抽奖功能使用说明

### 2025-12-08 v2.0
- ✨ **新增什么值得买(SMZDM)任务模块**: 完整的自动化任务执行系统
  - 📅 **每日签到**: 自动完成每日签到，获取积分奖励
  - 🎯 **众测任务**: 自动执行众测相关任务
    - 浏览文章任务自动完成
    - 互动任务自动处理
    - 智能任务奖励领取
  - 🎯 **互动任务**: 全面的用户互动任务支持
    - 自动浏览指定文章
    - 智能关注用户任务
    - 自动领取任务奖励
  - 👥 **多账号管理**: 支持配置多个账号并行执行
  - 📊 **详细统计**: 完整的任务执行统计和结果汇总
  - 📝 **完善日志**: 详细的执行日志记录和错误追踪

### 2025-12-08
- ✨ 支持多平台统一推送：在 `notification.py` 中新增 多平台推送 支持，并将各平台推送整合到统一接口 `send_notification`。
- 🛠 新增推送配置文件：`config/notification.json`（支持从文件或环境变量加载配置，优先级：文件 > 环境 > 默认）。
- 📝 更新 `README.md` 的“通知推送”文档，加入 使用说明、配置示例和常用环境变量说明。

### 2025-12-01
- ✨ 新增 WPS Office 自动签到脚本
- 📝 更新项目说明文档

### 2025-11-28
- ✨ 新增鸿星尔克签到脚本
- ✨ 支持鸿星尔克积分明细查询功能
- ❌ Ole'精品超市脚本设为不可用（需要动态获取微信code换取token）
- 📝 更新项目说明文档

### 2025-11-24
- ✨ 新增顺丰速运签到脚本
- ✨ 新增恩山论坛签到脚本
- ✨ 新增看雪论坛签到脚本
- ✨ 新增上海杨浦任务脚本
- ✨ 新增华润通多个子平台支持
- ✨ ✨ 999 签到功能完善
- ✨ ✨ 华润通微信小程序签到功能完善
- ✨ ✨ Ole' 精品超市签到功能（已废弃）
- ✨ ✨ 文体未来荟签到功能完善
- ✨ 创建项目 README 文档
- 📝 完善项目说明和使用指南

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

## ⚠️ 注意事项

1. 本项目仅供学习交流使用，请勿用于商业用途
2. 使用本项目所造成的一切后果由使用者自行承担
3. 请合理使用自动签到功能，避免对平台造成负担
4. Cookie 等敏感信息请妥善保管，不要泄露给他人
5. 定期更新 Cookie，避免失效影响使用
6. 代码由 AI 辅助生成，可能存在不规范之处

## 📄 开源协议

本项目采用 [MIT License](LICENSE) 开源协议。

## 🙏 致谢

- 感谢所有为本项目提供帮助和支持的朋友
- 感谢青龙面板提供的自动化平台

## 📧 联系方式

如有问题或建议，欢迎通过以下方式联系：

- GitHub Issues: [提交问题](https://github.com/Cat-zaizai/ZaiZaiCat-Checkin/issues)
- Email: wusan503@gmail.com

---

**⭐ 如果这个项目对你有帮助，欢迎给个 Star！**
