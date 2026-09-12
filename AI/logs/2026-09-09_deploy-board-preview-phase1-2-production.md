# 2026-09-09 展示板实时预览 Phase 1–2 生产合入

## 任务

将其他 AI 平台生成的 `board-preview-phase1-2.patch` 合入当前 OMRS 生产工作树，并保留第 3–4 期未完成项的详细交接文档。

## 来源包

- `/root/.hermes/attachments/files (25).zip`
- 包内实际包含 3 个文件：patch、WIP 源码 zip、交接文档。
- 生产采用 patch 路线，没有整目录覆盖。

## 部署前状态

- 生产目录：`/root/workspace/apps/OMRS`
- 部署前服务：`omrs.service`
- 部署前版本：`v1.17.0`
- 题目数据未修改；部署前 `错题/.omrs/boards.json` 为 4 个板、version 2。
- 工作树在部署前已有大量未提交修改，本次没有 reset、restore 或覆盖其他文件。
- `git apply --check` 与实际 `git apply --verbose` 均干净通过。

## 实际应用文件

patch 应用了 11 个文件：

- `omrs/boards.py`
- `omrs/exporting.py`
- `omrs/export_templates/board.js`
- `omrs/export_templates/board.css`
- `assets/board.js`
- `assets/board_preview.js`（新增）
- `assets/styles.css`
- `omrs_dashboard.html`
- `tests/test_boards.py`
- `AGENTS.md`
- `AI/logs/2026-09-08_board-preview-redesign.md`（新增）

另外按生产收尾规则新增：

- `AI/logs/2026-09-09_board-preview-remaining.md`
- 本文件
- `AI/logs/log.md` 索引行

没有部署 WIP zip，也没有覆盖 `AI/logs/log.md` 历史内容。

## 回滚点

`/root/workspace/apps/releases/OMRS-board-preview-phase1-2-rollback-20260909-124709/`

已保存：

- 部署前源码快照（排除 `.git`、`错题/`、缓存）；
- 部署前 `错题/.omrs` 数据快照；
- `pre-deploy-git-status.txt`；
- `pre-deploy-uncommitted.patch`；
- 原始 zip、patch、交接文档；
- `MANIFEST.sha256`。

Manifest 已校验 321 个文件，失败 0 个。

## 门禁结果

- `python3 -m unittest discover -s tests -p 'test_*.py'`：**69 tests，全部通过**。
- 9 个 `tests/test_*.js` 逐文件 `node --test`：**55 tests，全部通过**。
- `node --test tests/smoke_feedback_omr_import.js`：通过。
- `python3 tests/check_docs.py`：14 个文档，0 处问题。
- `tests/test_report_export.py`：未执行；系统没有 pytest，`python3 -m pytest` 返回 No module named pytest。
- `tests/smoke_board_print.py`：环境没有 Python Playwright，规范 unittest 命令运行 3 项但全部因依赖缺失而 skip，不能视为真实 Chromium 通过。

## 重启与线上核验

执行：停止 → reset-failed → 确认 8471 端口释放 → 启动。

结果：

- `omrs.service`：active (running)
- 服务启动日志：已索引 156 道题；OMRS 已启动（端口 8471）
- `GET /api/status`：HTTP 200，`status=ok`
- 线上版本：`v1.17.0`（本次 Phase 1–2 不升版本号）
- `question_count=156`
- `workspace_scan.conflict_count=0`
- 首页：HTTP 200
- 浏览器真实页面确认已加载 `assets/board_preview.js?v=20260908-live-preview`
- 展示板页可见纸面、列表、画廊三段；画廊仍为禁用占位，这是已知未完成项。
- 当前生产已有 4 个展示板；API 返回 `cut_line: dash` 的归一化默认值。

## 数据注意事项

生产磁盘上的 `错题/.omrs/boards.json` 当前仍是 version 2；服务读取时按新代码归一化并以 v3 语义返回，但本次没有人为触发写回迁移，也没有直接修改题库数据。后续若要写回迁移，必须再次备份并核对逐题留白、已打印游标和纸面几何。

当前默认切割线为 `dash`。历史板下次打印可能出现淡切割线；第 3 期 UI 完成前可通过 board update API 关闭。产品若要求“旧板保持原样，新板默认开启”，需先修改迁移策略并补测试。

## 未完成任务

详见：

`AI/logs/2026-09-09_board-preview-remaining.md`

该文档逐项写明第 3 期、第 4 期、专项测试、文档同步、真实打印/触屏验收、正文变更失效限制、版本升级条件和防目标漂移规则。

## 回滚方式

只回退本次 patch 涉及的 11 个文件，或从回滚目录的生产快照按文件恢复；不要使用 `git reset --hard`，不要覆盖本任务之外的未提交修改和 `错题/` 数据。恢复后重启 `omrs.service` 并核对 `/api/status`。
