# 题目停用机制

## 变更

- 新增题目 `question.suspend` / `question.resume` Ledger commit；停用不删除 Markdown，恢复沿用原 Mastery、EF、SM-2 和历史。
- `question_projection` 增加 `suspended` 列，并对既有 ledger.db 做幂等 `ALTER TABLE` 迁移。
- 兼容 `mastery_data.csv` 增加 `Suspended` 列；旧 CSV 缺列时按未停用处理。
- 停用题目保留在题库管理条目中，但从调度、推荐、行动推荐、统计、数据复盘、反馈提交和复习导出中排除；按 UID 手动确认调度也会被拒绝。
- `/api/stats` 增加活跃题总数口径下的 `suspended` 计数；`items` 仍包含停用题并携带 `suspended` 标记。
- 新增 `POST /api/question/suspend` 与 `POST /api/question/resume`。
- 网页题库新增活动/仅停用/含停用全部筛选，编辑菜单提供停用/恢复，停用行使用灰色弱化样式；仪表盘增加停用题 KPI。
- 数据复盘分析和 AI Markdown 导出过滤停用题及其历史聚合，但 Ledger 与历史明细仍保留，可审计。

## 影响文件

- 后端：`omrs/common.py`、`ledger.py`、`projections.py`、`question_ops.py`、`server.py`、`scheduling.py`、`stats.py`、`analytics.py`、`feedback.py`、`exporting.py`
- 前端：`omrs_dashboard.html`、`assets/core.js`、`questions.js`、`actions.js`、`dashboard.js`、`styles.css`
- 测试：`tests/test_question_suspend.py`、`tests/test_question_suspend_frontend.js`
- 文档：`README.md`、`AI/api.md`、`AI/algorithm.md`、`AI/data.md`、`AI/export.md`、`AI/frontend.md`、`AI/ledger.md`
- 版本：`v1.9.0`

## 验证

- `python3 -m unittest discover -s tests -v`：21 个测试全部通过。
- `node --check assets/core.js assets/questions.js assets/actions.js assets/dashboard.js`：通过。
- `node tests/test_question_suspend_frontend.js`：前端停用筛选与行动计划验证通过。
- `TZ=UTC node tests/smoke_frontend_actions_catalog.js`：全部通过。默认 CST 环境运行该既有 smoke 测试时，测试自身用 `toISOString()` 生成的“今天”会变为 UTC 前一天，出现 3 个既有日期断言失败；代码未因本任务产生该问题，使用与测试日期生成一致的 `TZ=UTC` 后通过。
- 临时 vault + `18471` 实例 API 验收：停用后 `/api/stats` 从 `total=2,suspended=0` 变为 `total=1,suspended=1`，推荐仅返回另一题，历史出现 `question.suspend` / `停用题目：代数1`；恢复后回到 `total=2,suspended=0`。临时实例已停止并清理。
- 临时实例浏览器验收：题库存在 `q-filter-suspended`；仅停用筛选只显示停用题，行含 `q-row-suspended`、`停用` 和 `resumeQuestion` 恢复入口；仪表盘显示 `v1.9.0` 与停用 KPI。
- 旧 ledger.db 副本迁移验证：`question_projection.suspended` 自动补列，既有 144 条投影保留。
- `git diff --check`：通过。

## 上线状态

仅完成源码、测试和文档；未重启生产 `omrs.service`，因此生产网页尚未宣称已上线。备份位于 `/root/workspace/backups/OMRS-question-suspend-20260831-063621/`，包含任务前状态、受影响文件和 Ledger 副本。
