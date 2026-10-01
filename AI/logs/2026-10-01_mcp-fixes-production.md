# 2026-10-01 MCP 修复生产部署

## 背景

用户原话：「部署生产」。Codex 完整模式；工作区干净，生产原运行 `bbf3757`，待发布源码为本地 `main` 的 `3ae272957d1c789a885f840c268b617507c2df0f`。F0–F4 修复及隔离验收见 `AI/logs/2026-10-01_mcp-fixes.md`。本次没有推送 GitHub，也没有启动 Tunnel。

## 行为变化

生产 MCP 已包含四项审查修复：`get_overview(subject=...)` 的汇总限定科目；首次草稿库迁移串行化；创建及幂等复用返回前重新鉴权；工具发现按当前 Key scope 过滤。生物科目线上概况现为 19 题、逾期 3、今日到期 16，范围内统计不再显示全库的 108/128。

## 部署与回滚

- 从提交 `3ae2729` 生成独立源码目录 `/root/workspace/apps/releases/omrs-3ae2729`，源码关键文件哈希与 Git 工作区一致。该提交没有依赖变化；release 的 `.venv` 链接到保留的 `/root/workspace/apps/releases/omrs-bbf3757/.venv`，MCP SDK 为 1.28.1。
- 只将 `/etc/systemd/system/omrs.service.d/10-release.conf` 的 release 路径改到新目录，并执行 `systemctl daemon-reload`、启动 `omrs.service`。没有改 Nginx、端口、Vault 路径、PIN、检测服务或 MCP 认证配置。
- 发布前停服快照位于 `/root/workspace/apps/releases/OMRS-mcp-fixes-rollback-20261001T064345Z/`，包含原 unit/drop-in、Nginx 配置、`bbf3757` 源码归档、完整 `错题/` 归档、6 个 SQLite 表计数及 282 个 Markdown 文件哈希。`sha256sum -c MANIFEST.sha256` 和 `tar -df` 均通过；Vault 归档 SHA-256：`01317ecc9625c7120b2d39b73991210581951ab6e9e8316c6c9e5fdf0a37e473`。
- 代码回滚时从该快照恢复 `10-release.conf.before`，执行 `systemctl daemon-reload` 并重启服务，确认 `/api/status` 正常。不要恢复旧 Vault 归档覆盖部署后的数据。

## 影响文件

- `AI/environment.md`：更新当前生产 release 与回滚快照。
- `AI/mcp.md`：更新线上 scope 与科目统计验收事实。
- `AI/plans/README.md`、`AI/plans/mcp-integration/progress.md`：登记生产更新状态与后续事项。
- 本任务日志与生成的 `AI/logs/log.md`：记录部署和验证。

## 验证

本轮在 release 副本执行 MCP/助手专项 unittest：68/68 通过。运行时输出一条 Pydantic `IncompleteFieldDefinitionWarning`，测试退出码为 0。F0–F4 的 Python 487/487、Node 399/399 及浏览器回归数字见修复日志；本部署轮未重复全仓与浏览器套件。

生产更新后：

- `omrs.service` 为 `active/running`，PID 1185297，`NRestarts=0`；`/api/status` 返回 v2.0.0、262 题、0 冲突。错误级 journal 为空，8471、回环 18472 与 HTTPS 8472 监听正常。
- 公网官方 SDK 完成 initialize，`tools/list` 返回 9 个只读工具。`get_overview(subject="生物")` 返回 `total=19`、`overdue=3`、`due_today=16`、`leech=0`、`killed=0`；直接调用隐藏的 `create_draft` 被拒绝。有效只读 Key 访问普通 Web API 返回 403，吊销后访问 MCP 返回 401。临时 Key `mcp_4ee86978be284813` 已撤销。
- 6 个 SQLite 库前后 `quick_check` 均为 `ok`，282 个 Markdown 文件哈希无变化；对比完整 SQLite 表内容没有草稿或业务表变化，仅 Ledger `workspace_fingerprint.last_seen_at` 与 `workspace_scan_status.last_scan_at` 随启动扫描更新。未创建测试草稿。
- `nginx -t` 通过，包含宿主机原有的监听协议重复配置 warning；本次没有改 Nginx 配置。

未执行：生产草稿创建、需要 PIN 会话的主应用页面走查、ChatGPT 账户/Tunnel 联调。生产未创建草稿是有意保持只读验收；账户与 Tunnel 尚未接入。本次未推送 GitHub。
