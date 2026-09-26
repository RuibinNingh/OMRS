# 2026-09-24 OMRS 重启竞态根治

## 变更摘要
- `omrs/cli.py` 新增 `OMRSTCPServer`（`allow_reuse_address = True`），监听 socket 启用 `SO_REUSEADDR`；未启用 `SO_REUSEPORT`，线程模型和 systemd 重试策略都没有改。
- `omrs/server.py` 新增模块级 `OMRS_INSTANCE_ID`（`secrets.token_hex(16)`），由 `GET /api/auth/session` 返回。
- `assets/app.js` 新增 `waitForRestartReady()`：每 500ms 探测一次，单次超时 1.5s，总计 90s。`doRestart()` 先记录重启前的 ID，只有看到新 ID 才刷新；超时后停在页面并给出提示。

## 行为与兼容性
- `GET /api/auth/session` 新增公开字段 `instance_id`，不是凭据。`POST /api/restart` 的响应契约不变。
- 如果仍有进程在监听同一端口，绑定照常失败，不会出现两个实例同时运行。

## 修改文件
`omrs/cli.py`、`omrs/server.py`、`assets/app.js`，新增 `tests/test_restart_lifecycle.py`、`tests/test_restart_ui.js`。

## 验证
- TDD：每个切片都先确认 RED，再改到 GREEN。
- 隔离实例（临时 Vault、端口 18471）：通过设置页触发了 3 次真实重启，分别在 2.4–2.6s 内看到新的 `instance_id` 后才刷新，日志里没有 `Address already in use`。
- 生产环境重启（计划 Task 9）尚未执行，需要在本机单独授权后验收。

## 同步过的文档
`AI/api.md`、`AI/security.md`、`AI/frontend.md`、`AI/optimization.md`。
