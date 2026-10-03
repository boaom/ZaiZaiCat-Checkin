# NodeSeek

入口：`script/nodeseek/main.py`

站点：`https://www.nodeseek.com`（每日签到领鸡腿）

## 功能

- 每日自动签到
- 多账号支持
- 区分 Cookie 失效、Cloudflare 拦截、重复签到与签到成功
- 推送通知

## 账号配置

节点：`nodeseek.accounts`

必填字段：

- `cookies`：浏览器完整 Cookie 字符串

可选字段：

- `user_agent`：建议填抓包时的浏览器 UA
- `proxy`：HTTP(S) 代理，如 `http://127.0.0.1:7890`

## 配置示例

```json
{
  "nodeseek": {
    "accounts": [
      {
        "account_name": "主号",
        "cookies": "colorscheme=light; session=xxx; pjwt=xxx; cf_clearance=xxx; ...",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
      }
    ]
  }
}
```

## 运行方式

```bash
python3 script/nodeseek/main.py
```

## 说明

- **Cookie 怎么拿**：登录 NodeSeek 后，在开发者工具 Network 里任选一个 `nodeseek.com` 的请求，
  复制 Request Headers 里整条 `Cookie` 的值。关键是 `session` 与 `pjwt` 两个，缺一即视为未登录。
- **签到接口**：`POST /api/attendance?random=true`，成功时返回
  `{"success": true, "message": "今天的签到收益是2个鸡腿", "gain": 2}`。
- **已签到不算失败**：返回「今天已经签到过了」时按成功处理，通知里用 🔁 前缀区分。
- **403 不一定是脚本问题**：`cf_clearance` 与抓包时的 IP、UA 绑定且有有效期，
  服务器出口 IP 与抓包环境不一致、或该值过期时，站点会返回 403 或直接返回验证页。
  此时重新抓一次 Cookie 更新配置即可；若仍 403，可给该账号配 `proxy` 走同一出口。
- **Cookie 含非 ASCII 字符会报错**：HTTP 头只能承载 latin-1，脚本会在请求前拦截并提示，
  避免抛 `UnicodeEncodeError`。
- 依赖：仅 `requests`。

