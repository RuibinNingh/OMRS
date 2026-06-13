# Ledger UI 与迁移审计工具补完

## 摘要

- 题目库「编辑」按钮改为在按钮下方展开操作列表，包含「迁移到其他分类」与「编辑 Markdown」。
- 历史记录页从表格改成 Ledger 竖线时间线。
- 历史节点新增操作面板：反馈修改/撤销/恢复、Session 撤销/恢复、state.restore。
- 迁移脚本升级为迁移审计工具，并附带 AI 检查提示词。

## 前端

- `assets/questions.js`：新增 `renderQuestionEditMenu()` 和菜单开合逻辑；List/Gallery 共用。
- `assets/schedule.js`：`loadHist()` 改为渲染 Ledger 时间线；新增历史操作 API 调用函数。
- `assets/styles.css`：新增题目编辑菜单、历史时间线、节点详情和操作表单样式。
- `omrs_dashboard.html`：历史页容器从旧表格换为时间线容器。

## 后端

- `omrs/projections.py`：修正 Session 撤销重放时伪 commit 的 `session_id` 识别，确保撤销 Session 会跳过对应反馈。

## 工具

- `tool/migrate_ledger.py`：支持 `--check-only`、`--scan`、`--report`、`--json`、`--write-ai-prompt`。
- `tool/ledger_migration_ai_check_prompt.md`：用于外部 AI 审查迁移报告和关键代码。

## 验证

- Python 编译通过。
- 前端 JS 语法检查通过。
- 迁移审计脚本在当前 vault 上运行，Ledger 校验有效。
