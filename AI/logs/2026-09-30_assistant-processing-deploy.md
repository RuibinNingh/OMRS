# 2026-09-30 助手处理状态行生产更新

## 授权与范围

用户明确要求“生产目前不是最新的吧,更新”。本次由 Codex 完整模式执行，将提交 `1804d1e` 发布到主服务。只切换 OMRS 主服务代码目录，不修改 Nginx、真实 Vault 内容、AI 模型、框选模型或检测服务配置。

## 发布与备份

- 从 `HEAD=1804d1e` 生成 `/root/workspace/releases/omrs-1804d1e`，共 954 个文件；发布目录执行 `tests.test_migration_compat`，4/4 通过。
- 切换前确认助手 `active=[]`，agent runs 63 条全部 done，tool calls 114 条无未完成项，收件箱 jobs 169 条全部 done。
- 停止主服务期间归档真实 Vault：`/root/workspace/backups/recycle/assistant-processing-1804d1e-20260930T221604+0800/vault-before.tar`，SHA-256 与原 drop-in、服务状态、API 快照和数据库 `quick_check` 结果保存在同目录。6 个 SQLite 文件均返回 `ok`。

## 切换结果

- `/etc/systemd/system/omrs.service.d/10-release.conf` 已切到 `/root/workspace/releases/omrs-1804d1e`，执行 `systemctl daemon-reload` 后启动 `omrs.service`。
- 服务 `active/running`，`MainPID=2289539`、`ExecMainStatus=0`、`NRestarts=0`；`/api/status` 返回 `v2.0.0`、262 道题、workspace scan 变更 0 / 冲突 0。
- `/api/agent/status` 返回助手已启用且 `active=[]`；`/api/ledger/verify` 返回 `valid=true`、717 个提交；错误级 journal 无记录。
- 框选检测服务 `omrs-boxdetect.service` 保持 active，未随本次主服务切换重启或改配置。

## 验证

已实际执行：

- 发布目录迁移兼容测试：4/4 通过。
- 主服务状态、API 状态、助手状态、Ledger 校验、systemd 进程路径和 Nginx HTTPS 入口检查通过。
- 生产直接提供的 `assistant-run.css` SHA-256 与新发布目录一致。
- 真实 Vault 停服归档前 6 个 SQLite 数据库 `pragma quick_check` 全部为 `ok`。

未执行：生产写入型助手 E2E、真实模型调用、Android/iOS 真机验收；本次仅切换已验证的前端样式与同一版本运行时。

## 回退

恢复备份目录中的 `10-release.conf.before`，执行 `systemctl daemon-reload && systemctl restart omrs.service`；旧发布目录 `/root/workspace/releases/omrs-541e7f9` 保留。不得用 Vault 归档覆盖发布后新增数据。
