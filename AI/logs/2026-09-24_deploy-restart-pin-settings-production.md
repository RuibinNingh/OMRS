# 2026-09-24 OMRS 重启竞态与 PIN 设置修复生产部署

## 任务与包形态

部署附件 `OMRS-20260924-restart-pin-settings.zip`。包内包含完整源码树和 `changes-2026-09-24.patch`；按交接文档推荐，仅应用补丁，避免整树覆盖生产工作区中的其他未提交改动。此次为 v1.19.0 同版本修复，不改版本号。

## 部署前状态与基线核验

- 生产版本 v1.19.0，题目 208 道，`workspace_scan.conflict_count=0`；服务监听 `0.0.0.0:8471`。
- `GET /api/auth/session` 显示 PIN 尚未设置；配置允许 `192.168.0.0/24` 免 PIN 直连。该访问设置是既有状态，本次未更改。
- 工作树已有大量未提交改动及未跟踪文件。部署前完整记录 `git status` 并保留；未使用整树覆盖、`reset` 或清理命令。
- `git apply --check` 通过。隔离目录中应用补丁后，21 个补丁路径均与包内对应副本逐字节一致；其余包内源码文件均与生产树一致（忽略测试生成的 `__pycache__`）。

## 备份

回滚快照：`/root/workspace/apps/releases/OMRS-v1.19.0-rollback-20260924-225336/`

包含源码快照（不含 `错题/` 与 `.git/`）、部署前状态、未提交/暂存 diff、原始上传 ZIP、交接文档及补丁。`MANIFEST.sha256` 共 403 项，`sha256sum -c` 全部通过。

## 部署与验收

- 使用 `git apply --verbose` 应用补丁，涉及 21 个路径；没有部署完整源码树，没有覆盖 `错题/`、配置文件或 systemd 单元。
- 部署前生产基线测试：Python 128 项、Node 122 项通过。包树测试通过：Python 137 项、Node 140 项，`check_docs.py` 0 处问题。
- 部署后生产门禁：Python 137 项通过；Node 140 项通过；`python3 tests/check_docs.py` 检查 15 个文档、0 处问题；`git diff --check` 与 `git apply --reverse --check` 通过。
- 首次从旧进程切换时，systemd 日志记录 12 次 `Address already in use` 后才于 22:57:09 启动成功；当时的 30 秒就绪轮询先超时退出。服务随后由 systemd 自动恢复。之后从真实设置页触发第二次重启，`POST /api/restart` 返回 200，22:58:34 新实例启动，`instance_id` 变化，重启后未再出现该 bind 错误。首次切换的失败记录保留在 journal 中，不将其记作零错误。
- 最终 `/api/status`：`status=ok`、版本 v1.19.0、题目 208 道、扫描冲突 0、`listen_external=true`；systemd 为 `active/running`，端口仅一个 listener。
- Chromium 实测设置页五个分区均存在；访问与安全页显示现有免 PIN 网段和 PIN 未设置状态。真实设置页重启后页面以 reload 方式重新加载；注入的 `console.error` 计数为 0。

## 未执行项与注意事项

- 未设置或修改 PIN，也未从远端设备验证登录流程；访问仍按既有配置运行：`192.168.0.0/24` 可免 PIN 访问；其他远端设备当前无法登录，因为 PIN 尚未设置。
- 首次旧实例到新实例的启动仍出现上述 12 次 bind 重试；新实例随后进行的真实设置页重启无 bind 错误。若再次遇到启动延迟，先看 `systemctl`、journal 和监听状态，不要连续点击重启。
- 题库及 `.omrs` 数据未由本次部署写入；未提交 Git。

## 回滚

补丁型回滚保留其他工作树内容：在项目目录执行 `systemctl stop omrs.service`、`systemctl reset-failed omrs.service`，再执行 `git apply --reverse /root/workspace/apps/releases/OMRS-v1.19.0-rollback-20260924-225336/changes-2026-09-24.patch`，最后 `systemctl start omrs.service` 并核验 `/api/status`。如需完整恢复部署前工作区，按快照目录和 `pre-deploy-git-status.txt` 逐项恢复；不得覆盖 `错题/`。
