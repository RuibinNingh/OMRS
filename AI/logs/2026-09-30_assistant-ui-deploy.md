# 2026-09-30 助手界面生产部署

## 授权与范围

用户明确要求“部署生产”。本轮部署提交 `1b0558c` 的助手界面重设计，只切换主服务固定发布目录；不修改 Nginx、检测服务、模型、生产配置和真实 Vault 内容。用户未跟踪的 `.playwright-mcp/` 原样保留。

## 发布与备份

新发布目录：`/root/workspace/releases/omrs-1b0558c`，由 `git archive` 生成；发布目录执行 `/usr/bin/python3 -m unittest tests.test_migration_compat -q`，4/4 通过。切换前确认 `/api/agent/status` 的 `active=[]`，inbox jobs 全部 done（145 条），agent runs 全部 done（57 条）。

停服期间完整归档真实 Vault：`/root/workspace/backups/recycle/assistant-ui-1b0558c-20260930T004155Z/vault-before.tar`，并保存原 `10-release.conf`、服务状态、SHA-256 与生产浏览器验收记录。旧发布目录 `/root/workspace/releases/omrs-dccbe6b` 保留用于回退。

## 切换结果

仅将 `/etc/systemd/system/omrs.service.d/10-release.conf` 的代码路径切换为 `/root/workspace/releases/omrs-1b0558c`，执行 `systemctl daemon-reload` 后启动服务。服务返回 active/running，`MainPID=4189481`、`ExecMainStatus=0`、`NRestarts=0`。本地 `/api/status` 返回 v2.0.0、239 道题、工作区扫描 0 变更 / 0 冲突；`/api/agent/status` 显示助手已启用且无活动运行。错误级 journal 无记录。

生产提供的 `assets/app/features/assistant/view.js` SHA-256 与发布目录一致。

## 验证

已实际执行：

- 发布目录迁移兼容测试：4/4 通过。
- 服务健康检查：`/api/status` 返回 ok，v2.0.0，239 题，扫描无冲突。
- systemd：active/running，`ExecMainStatus=0`，`NRestarts=0`，错误级 journal 为空。
- 生产只读 Chromium：1440×900 与 390×844 均确认输入框存在、展开按钮为 0、上下文与缓存同时显示、无横向溢出、脚本错误 0。证据：备份目录 `production-browser.json`。
- 生产数据库只读复核：inbox jobs 145 条全部 done；agent runs 57 条全部 done。

未执行：生产写入型 E2E、真实模型调用、Android/iOS 真机验收；本次界面切换不需要这些动作。

## 回退

如需回退，恢复备份中的 `10-release.conf.before`，执行 `systemctl daemon-reload` 并重启 `omrs.service`；旧发布目录保留。不得用旧 Vault 归档覆盖上线后的新增数据。
