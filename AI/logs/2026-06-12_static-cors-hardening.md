# static-cors-hardening

## 背景

Bug 排查时复核到一个安全问题：未知路径会落到 `SimpleHTTPRequestHandler` 默认静态文件服务，导致仓库内文件可被 HTTP 直接读取；同时 JSON/API/导出响应带 `Access-Control-Allow-Origin: *`，第三方网页可跨域读取本地服务响应。当前配置中存在 AI Key，因此该问题会扩大为配置泄露风险。

## 修改

- `omrs/server.py`
  - 未命中的 GET 路径不再调用 `super().do_GET()`，改为直接 404。
  - 移除 `_json()`、导出、报告、图片、OPTIONS 响应中的 `Access-Control-Allow-Origin: *`。
- `AI/api.md`
  - 记录静态路由白名单和 API 不主动设置跨域读取头的边界。

## 验证

- 修复前：`/AI/README.md`、`/错题/.omrs/config.json`、`/.gitignore` 均返回 200；`/api/config` 返回 CORS `*` 且包含配置密钥字段。
- 修复后预期：上述仓库文件路径返回 404；`/api/config` 仍同源可用，但不再带 CORS `*`。
