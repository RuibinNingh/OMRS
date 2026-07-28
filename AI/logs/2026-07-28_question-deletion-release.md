# 2026-07-28 v1.6.0 单题删除与 v1.5.0 后变更汇总

## 变更摘要

- 题目库的编辑菜单新增「删除题目」，删除前须二次确认。
- 新增 `POST /api/question/delete`：删除目标 Markdown 后追加 `question.archive` commit，重建投影并清理工作区指纹。
- 版本号从 `v1.5.0` 升至 `v1.6.0`。

## 行为与兼容性

- 被删除题目不会再出现在题库、统计、调度或兼容 CSV；历史反馈与 Ledger 记录仍保留。
- Ledger 不保存 Markdown 正文，删除后的正文不能通过 Ledger 恢复；附件图片不自动删除，避免影响其他题目的引用。
- `update_fingerprints()` 改为用完整活动题目集重建 `workspace_fingerprint`，因此主动删除不会在后续扫描中重复写入 `question.archive_external`。

## v1.5.0 后审查

- `81a2922`：后续 UI 优化。
- `a39ad41`：根 README。
- `7e7e6d7`：到期提示。
- `d8d7874`、`262a256`：AI 提示词与分类约束。
- `6a4417e`：难度分布修复。
- `b481181`：报告页面优化。
- 当前未提交发布批次：导出分页/题间留白、AI 报告材料、Ledger 文档校准、可配置时间线时区，以及本次单题删除与 v1.6.0 升级。

## 修改文件

- `omrs/question_ops.py`
- `omrs/workspace_sync.py`
- `omrs/server.py`
- `omrs/projections.py`
- `omrs/version.py`
- `assets/questions.js`
- `assets/history.js`
- `assets/styles.css`
- `omrs_dashboard.html`
- `README.md`
- `AI/README.md`
- `AI/api.md`
- `AI/frontend.md`
- `AI/ledger.md`
- `AI/logs/log.md`

## 验证

- `python -m unittest discover -s tests -p "test_*.py" -v`：10 项通过；删除测试覆盖投影归档、Markdown 删除、附件保留与后续扫描不重复归档。
- `node --check assets/questions.js`、`assets/history.js`、`assets/core.js`、`assets/dashboard.js`、`assets/app.js`：通过。
- `git diff --check`：通过。

## 同步过的文档

- `README.md`
- `AI/README.md`
- `AI/api.md`
- `AI/frontend.md`
- `AI/ledger.md`
- `AI/logs/log.md`
