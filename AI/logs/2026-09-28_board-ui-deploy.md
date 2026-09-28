# 2026-09-28 展示板 UI 打磨生产部署

## 背景

用户原话：「部署生产」。承接 `2026-09-28_board-ui-polish.md` 的展示板改动。部署目标为已完成本地验收的提交 `d7b48ef9677c64ed0cb280d0c1dd69bfef695d84`（v1.28.1）。同一工作区的 `ai-draft` 分支已有后续 AI 功能提交和未提交改动，因此生产服务改为从固定发布目录读取代码，真实 Vault 仍指向原路径。

## 行为变化

- 将 `d7b48ef` 归档到 `/root/workspace/releases/omrs-d7b48ef`；在 `/etc/systemd/system/omrs.service.d/10-release.conf` 固定 `WorkingDirectory` 和 `ExecStart` 到该目录，`--vault /root/workspace/apps/OMRS` 与 TCP 8471 不变。执行 `systemctl daemon-reload` 和 `systemctl restart omrs.service` 后，服务 PID 为 2443976，状态为 active。
- 部署前将 `boards.json`、`config.json`、`mastery_data.csv` 复制到 `/root/workspace/backups/recycle/board-ui-deploy-20260928T211103`；另留上一版 `ae471fc` 的代码归档 `/root/workspace/releases/omrs-ae471fc`。部署后这三份数据文件与备份逐字节一致。
- 未推送远端或改动 Nginx。后续开发继续在工作区进行，不会改变当前发布目录的代码。

## 影响文件

- 仓库：`AI/environment.md`（生产代码路径）、`AI/plans/board-redesign/progress.md`（部署状态）、本日志和自动生成的 `AI/logs/log.md`。
- 仓库外：上述两个发布目录、三份数据备份、systemd drop-in；真实 Vault 路径未变。

## 验证

已实际执行：发布目录用临时 fixture Vault 和随机高端口启动，`/api/status`、展示板脚本和 `/api/export` 均通过（导出 695998 字节）；生产重启后 `/api/status` 返回 `ok`、v1.28.1，展示板脚本哈希与发布目录一致，四块板中的首块可导出新版 HTML。真实浏览器走了展示板纸面、详情层、「打开题目」弹窗和 390px 手机布局：无页面脚本错误、无横向溢出。`systemctl is-active omrs.service` 为 active，重启后的错误级 journal 无记录。三份关键数据文件未变。

文档索引已由 `python3 tests/check_docs.py --write-log-index` 生成。原工作区运行 `python3 tests/check_docs.py --diff HEAD` 时，因为另一智能体尚未提交的 `omrs/agent/` 与 `omrs/drafts.py` 改动缺少对应 AI 文档而报 2 处问题；在只包含当前已提交代码和本次部署文档的临时 Git 副本中执行同一检查，46 个文档、0 处问题、2 条已有文件体积提醒。临时副本同时复制了仓库忽略但本机存在的历史日志 `2026-08-16_mini-host-deploy.md`，使生成的日志索引与生产工作区一致。未改动另一智能体的代码或文档。

未执行：物理打印机出纸；远端设备的登录与反向代理路径（本次未改访问配置）。

## 回退

若需回退到部署前的代码，将 drop-in 的发布路径从 `omrs-d7b48ef` 改为 `omrs-ae471fc`，执行 `systemctl daemon-reload && systemctl restart omrs.service`，再核对 `/api/status` 和展示板页面。真实 Vault 路径保持原值；数据备份只在确认数据损坏时使用，不随代码回退覆盖现有数据。
