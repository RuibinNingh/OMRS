# 2026-09-24 OMRS 文档架构升级生产记录

## 任务
部署附件 `files (7).zip` 中的「文档架构优化与维护环境记录」。升级说明指出这是文档与 `tests/check_docs.py` 更新，不包含新的运行时功能。

## 部署前状态
- 工作区已有大量未提交生产改动（含此前 restart/PIN/settings 升级）；未清理、未覆盖、未提交。
- 服务 `omrs.service` active/running，MainPID `656109`，NRestarts `0`；`/api/status` 为 HTTP 200，版本 `v1.19.0`、题目 208、扫描冲突 0。
- 附件外层 ZIP 完整，含源码导出 ZIP、文档升级说明、`changes-2026-09-24-docs.patch` 和 `changes-2026-09-24-all.patch`。
- 说明要求在维护模式补丁未应用时选择 all patch；但 all patch 含此前已部署的运行时代码，不能整体重放；docs patch 直接检查时因 `AGENTS.md` 前置维护模式段落缺失而失败。根据附件源码导出树生成仅包含该前置 `AGENTS.md` 变更的补丁，先在临时副本分层应用两补丁，再与导出包逐目标文件比对：30 个 docs patch 目标均一致，随后才在生产应用。并单独部署包内 `2026-09-24_maintainer-modes.md` 任务记录。

## 备份
- 回滚目录：`/root/workspace/apps/releases/OMRS-docs-architecture-rollback-20260924-233628/`
- 保存源码/文档/测试快照、升级 ZIP 与补丁、部署前 Git 状态及 staged/unstaged diff。
- `MANIFEST.sha256` 核验 482 个文件，0 失败；备份约 24 MB。

## 已部署内容
应用维护模式段落及 `changes-2026-09-24-docs.patch`；新增维护模式任务记录；运行 `python3 tests/check_docs.py --write-log-index` 更新日志索引。前端文档拆成 10 个分册，新增 `AI/routes.md`、`AI/environment.md`，并更新速查头、文档索引与检查器。

仅修改文档、任务记录、日志索引和文档检查脚本；未改题库、运行时代码、服务配置或 systemd 单元，未重启服务，未提交 Git。

## 验证
- 包树预检：Python 单测 137 项通过；Node 测试 140 项通过；文档检查 27 份、0 问题、1 条提示（`AI/api.md` 约 52KB，建议后续拆分）。
- 部署后：Python 单测 137 项通过；Node 测试 140 项通过；`python3 tests/check_docs.py --diff HEAD` 检查 27 份文档、0 问题、1 条相同提示。
- 测试期间 Python 输出 3 条 `tests/test_inbox.py` 未关闭文件的 `ResourceWarning`；不影响本次测试通过。
- 部署后核对 docs patch 的 30 个目标文件均与附件源码导出字节一致；维护模式日志也与包内版本一致。
- 服务仍 active/running，NRestarts `0`；`/api/status` 仍为 `v1.19.0`、题目 208、扫描冲突 0，符合未改运行时代码且不需重启的预期。
- 未做浏览器验收：本次没有前端运行时代码改动。

## 回滚
从上述回滚目录恢复本次修改涉及的文档、任务日志、`tests/check_docs.py` 与 `AI/logs/log.md`；不触碰 `错题/`。不需要重启服务。此前已有未提交改动也保存在 `uncommitted-worktree.patch` 和完整快照中。