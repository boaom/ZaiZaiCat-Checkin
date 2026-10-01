# 福利吧

入口：`script/fuliba/main.py`

站点：`https://www.wnflb2023.com`（Discuz + `fx_checkin` 签到插件）

## 功能

- 每日自动签到
- 多账号支持
- 自动获取 `formhash`，Cookie 失效时给出明确提示
- 推送通知

## 账号配置

节点：`fuliba.accounts`

必填字段：

- `cookies`：浏览器完整 Cookie 字符串

可选字段：

- `formhash`：留空即可，脚本每次运行会自己去首页抓最新的
- `user_agent`：建议填抓包时的浏览器 UA

## 配置示例

```json
{
  "fuliba": {
    "accounts": [
      {
        "account_name": "主号",
        "cookies": "S5r8_2132_saltkey=xxx; S5r8_2132_auth=xxx; ...",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
      }
    ]
  }
}
```

## 运行方式

```bash
python3 script/fuliba/main.py
```

## 说明

- **Cookie 怎么拿**：登录论坛后，在开发者工具 Network 里任选一个 `wnflb2023.com` 的请求，
  复制 Request Headers 里整条 `Cookie` 的值。关键是必须带上 `S5r8_2132_auth` 和
  `S5r8_2132_saltkey` 这两个，否则视为未登录。
- **formhash 会自动刷新**：Discuz 的 `formhash` 随会话变化，脚本每次先请求首页解析最新的值，
  配置里那一项只是抓不到时的兜底。首页里找不到 `formhash` 通常意味着 Cookie 已过期，
  脚本会直接报「Cookie 已失效」而不是傻等签到接口返回失败。
- **签到接口**：`GET /plugin.php?id=fx_checkin:checkin&formhash=<hash>&<hash>&infloat=yes&handlekey=fx_checkin&inajax=1&ajaxtarget=fwin_content_fx_checkin`。
  链接里 `formhash` 出现两次是站点自身 JS 生成的写法，脚本保持了一致。
- **已签到不算失败**：返回「今天已经签到过了」时按成功处理，通知里用 🔁 前缀区分。
- 依赖：仅 `requests`。
