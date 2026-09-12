# 2026-09-06 练习记录改读 Ledger + 文档审计整理（v1.16.1）

## 变更摘要

1. **修 bug**：题目详情记录模块 / 画廊战绩带只解析题目 Markdown 的 `# 历史`，而反馈流程早就只写 Ledger，导致有正式反馈的题显示「还没练过（熟练度表记了 N 次，但题目文件里没有可解析的历史行）」。现在 `GET /api/question` 返回 `records[]`（`stats.get_question_records()`，从 `history_log.csv` 投影派生，`Question_ID` 优先、`UID` 兜底），前端 `core.js::qRecordsFromDetail()` 统一取记录；空记录只显示「还没练过。」。反馈提交 / 历史修正后 `qvInvalidateMany()` 清详情缓存并重绘。
2. **全站去原生弹窗**：35 处 `alert / prompt / confirm` → `uiToast / uiPrompt / uiConfirm`；`history.js` 三个函数改 async。
3. **文案**：设置页「外观」帮助改为「首次打开默认深色」，与首帧脚本一致。
4. **文档整理**：`frontend.md` 顶部 16 段版本叙述搬进新建 `AI/changelog.md`（倒序）；正文 3 段改写为当前状态；章节重新编号（§7–§12）；§5.1.1 拆出 `AI/omr-import.md`；`api.md` / `data.md` / `optimization.md` 改成修后事实；`optimization.md` 两条技术债 `[x]`，测试清单改按主题分组；根 `README.md` 合并两处重复的技术债章节、修正项目结构（`tool/`、`Task/` 已 gitignore）、版本表加 v1.16.1。
5. **规则持久化**：根 `AGENTS.md` 新增「文档写法」三条硬规则 + 收尾第 7 步跑 `tests/check_docs.py`；`AI/README.md` 同步索引、版本号与规则摘要。

## 行为与兼容性

- `/api/question` 只增字段（`records`），`history` 仍在；老前端不受影响。老后端（没有 `records`）配新前端时自动退回解析 Markdown。
- `uiConfirm` 是异步的，所有调用点已在 async 函数内；行内 `onclick` 调 async 函数返回 promise 无副作用。
- 版本 v1.16.0 → v1.16.1；13 个 JS 的 `?v=` 刷成 `20260906-v1161`。

## 修改文件

代码：`omrs/stats.py`、`omrs/version.py`、`omrs_dashboard.html`、`assets/{core,qview,questions,feedback,instant,history,app,export,inbox,recommend,recommend_v2,reports,schedule}.js`
测试：`tests/test_question_records.py`（新）、`tests/test_question_record_ui.js`（+3 例）、`tests/check_docs.py`（新）
文档：`AGENTS.md`、`README.md`、`AI/README.md`、`AI/changelog.md`（新）、`AI/omr-import.md`（新）、`AI/frontend.md`、`AI/api.md`、`AI/data.md`、`AI/optimization.md`

## 验证

- `python3 -m unittest discover -s tests -p "test_*.py"` → 61 OK（`test_report_export.py` 为 pytest 风格，本环境无 pytest 未跑）
- `for f in tests/test_*.js; do node --test "$f"; done` → 9 个文件全部 pass（含新增 3 例）
- `for f in assets/*.js; do node --check "$f"; done` → 全部通过
- `python3 tests/check_docs.py` → 14 个文档 0 处问题
- `node tests/smoke_feedback_omr_import.js`、`node tests/smoke_frontend_actions_catalog.js` → 全部通过
- `PYTHONPATH=. python3 tests/smoke_board_print.py` → **失败**（`test_full_then_incremental_print`），在改动前的原始源码包上同样失败，属既有问题，已记入 `optimization.md`
- 未做浏览器手动回归：录反馈后详情记录刷新、`uiConfirm` 各处按钮文案，建议本机跑一遍

## 同步过的文档

见「修改文件 → 文档」。`AI/logs/log.md` 需追加索引行（本包不含该文件）：
`| 2026-09-06 | [ledger-records-docs-audit](2026-09-06_ledger-records-docs-audit.md) | v1.16.1：练习记录改读 Ledger、全站去原生弹窗、文档整理与写法规则 |`
