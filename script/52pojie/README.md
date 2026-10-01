# 吾爱破解论坛每日签到

52pojie.cn 每日签到（Discuz 任务 `id=2`），支持多账号。

## ✨ 功能特性

- 📅 **每日签到**：走论坛任务系统「申请 → 领取」，等价于网页上点一次签到
- 🛡️ **内置网宿 WAF 挑战求解**：任务接口被 WAF 拦截时自动算题、校验、重放，无需人工过盾
- 🔐 请求走 `curl_cffi` 模拟 Chrome TLS 指纹（普通 `requests` 会被拦，见下文）
- 👤 签到前先确认登录态，顺手回显用户名与积分
- 🔁 已签到识别为成功，不会误报失败
- 🔔 推送执行结果通知

## 📦 依赖

```bash
pip install curl_cffi
```

`curl_cffi` 不是可选项：站点 WAF 会校验 TLS 指纹，用普通 `requests`
即使挑战校验返回 `ok`，重放原请求依然会被拦截。

## ⚙️ 配置说明

在项目根目录 `config/token.json` 的 `52pojie` 节点下配置：

```json
{
  "52pojie": {
    "accounts": [
      {
        "account_name": "大号",
        "cookie": "htVC_2132_...; htVC_2132_auth=...",
        "user_agent": ""
      }
    ]
  }
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `account_name` | 否 | 账号备注名 |
| `cookie` | 是 | 登录后的完整 Cookie（见下方获取方法） |
| `user_agent` | 否 | 建议与抓包时保持一致，不填用内置 UA |
| `task_id` | 否 | 签到任务 ID，默认 `2` |

### cookie 获取方法

1. 浏览器登录 <https://www.52pojie.cn/>
2. F12 → Network，刷新首页，随便点一个 `www.52pojie.cn` 的请求
3. 复制请求头里的整条 `Cookie`（或从 Application → Cookies 里拼）

关键字段是 `htVC_2132_auth` 和 `htVC_2132_saltkey`，其余 `htVC_2132_*` 一起带上更稳。

> `wzws_cid` / `wzws_sid` 是 WAF 下发的短时 Cookie，**可以不带**，
> 脚本会自动剔除并在需要时重新过一遍挑战。
> Cookie 有效期较长（约半年），失效后脚本会提示「Cookie 已失效」。

## 🚀 使用方法

```bash
python script/52pojie/main.py
```

脚本流程：

1. 读 `config/token.json` 里的所有账号
2. 请求首页确认登录态，取出用户名和积分
3. 请求任务接口 `home.php?mod=task&do=apply&id=2`
4. 命中 WAF 挑战页 → 自动算题 + 校验 + 重放
5. 申请成功会 302 到 `do=draw`，跟随领取奖励并解析结果
6. 汇总结果推送通知

## 🔌 接口说明

| 用途 | 路径 |
|---|---|
| 登录态判断 | `/index.php` |
| 申请签到任务 | `/home.php?mod=task&do=apply&id=2&referer=%2Findex.php` |
| 领取任务奖励 | `/home.php?mod=task&do=draw&id=2&referer=%2Findex.php` |
| WAF 校验接口 | `/waf_zw_verify` |

### 网宿 WAF 挑战流程

只有 `home.php?mod=task*` 这类任务接口会被拦，其余页面正常。

1. 请求任务接口 → 拿到挑战页，页内以 JS 变量给出
   `wzwsquestion`（题干）、`wzwsfactor`（乘数）、`base64_chars`（乱序码表）、
   `dynamicapi`（校验接口）
2. 计算确认串：`answer = Σ(2*(a+字符)) * factor + Σ(2*(序号+1))`，
   前缀固定为 `WZWS_CONFIRM_PREFIX_LABEL`
3. 把 `{fp_infos, answer, hostname, scheme}` 用**乱序码表**做 base64 编码，
   `POST` 到校验接口，返回 `ok`
4. 重放原请求即通过

`fp_infos` 是浏览器指纹（屏幕分辨率、WebGL、字体、Canvas 等），
已从抓包还原并固化在 `fp_infos.json`，运行时只刷新时间戳。

## 📊 输出示例

```
[大号] 登录态正常：丶江流儿（积分: 23）
[大号] 开始申请每日签到任务...
命中网宿 WAF 挑战（第 1 次）: .../home.php?mod=task&do=apply&id=2...
[大号] 任务页提示[alert_info]: 恭喜，签到成功，获得 5 吾爱币
[大号] 签到结果: 恭喜，签到成功，获得 5 吾爱币
```

## 🚫 已知限制

- 站点风控策略可能随时调整，若提示「响应含 WAF 特征但缺少挑战变量」，
  说明挑战页结构变了，需要重新抓包更新 `fp_infos.json` 与解析逻辑
- 一天只需跑一次，重复执行会返回「本期您已申请过此任务」，按已签到处理

---

**免责声明**：本脚本仅供学习交流使用，使用产生的一切后果由使用者自行承担。
