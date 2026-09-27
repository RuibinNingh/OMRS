# 2026-09-24 PIN 功能修复与设置页重构

## 变更摘要
- 登录页 `next` 改用 `new URL()` 解析并只接受同源地址，修复 `/\evil.example` 形式的开放重定向。
- `core.js` 和 `/m` 页的活动监听改为捕获阶段，并增加 `wheel`，工作台内部容器里的滚动也能续期会话。
- `/m` 遇到 401 时跳转 `/login?next=/m`，并停止处理剩余上传；状态行不再误显示“已连接”。
- `/api/auth/pin`：尚未设置 PIN 时，免 PIN 网段设备可以直接设置首个 PIN。已设置 PIN 时，远端校验当前 PIN 与登录共用每 IP 15 分钟 5 次的失败上限（新增 `security.verify_pin_limited()`）。
- `security.set_idle_minutes()` 不再清空全部会话，新的空闲上限立即生效，与 `AI/security.md` 的描述一致。
- `GET /api/status` 新增 `listen_external`，表示当前进程实际的监听范围。
- 设置页重构为五个分区：外观与显示 / 访问与安全 / AI 识别 / 数据与存储 / 服务与运行。
  - “访问与安全”顶部新增访问概览，并提示哪些配置要重启后才生效。
  - PIN 控件按连接身份显示。
  - 只改免 PIN 网段时不重启，只有切换局域网开关才重启。
  - 停用 PIN 前有二次确认；读取配置失败时显示错误，不再静默。
  - 所有旧元素 ID 保留。

## 修改文件
`omrs/security.py`、`omrs/server.py`、`omrs/cli.py`、`assets/app/main.js`、`assets/app/domain/items.js`、`assets/inbox_mobile.html`、`assets/app/styles/index.css`、`omrs_dashboard.html`、`tests/test_security.py`（在原文件末尾追加 4 项测试）；新增 `tests/test_auth_activity_ui.js`、`tests/test_settings_ui.js`。

## 验证
- Python 单测 137 项 OK；Node 140 项全部通过；`check_docs` 0 处问题；`git diff --check` 干净。
- Playwright 端到端 12 步全部通过，覆盖本机（1440 宽）和远端手机视口（192.0.2.2 直连）。控制台只有预期内的 1 次 400（未设 PIN 就开局域网）和重启期间的连接拒绝，没有 pageerror。

## 同步过的文档
`AI/api.md`、`AI/security.md`、`AI/frontend.md`（第 7 节重写）、`AI/inbox.md`、`AI/optimization.md`、`README.md`。
