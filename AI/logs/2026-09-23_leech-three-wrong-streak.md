# 2026-09-23 顽固题改为连续答错三次

## 变更摘要

顽固题从累计答错至少四次改为最近连续答错达到阈值，默认三次。答对会清零连错次数并解除顽固题标记；已击杀题仍不标记。累计答错 `fail_count` 保留，用于原有的历史统计。

## 行为与兼容性

`history_log.csv` 按 Ledger 投影顺序读取，不修改存储格式。新增派生字段 `wrong_streak`，用于 `/api/stats`、`/api/recommend`、`/api/analytics` 的题目条目；顽固题数量、熟练度列表加成、数据复盘顽固题排序和导出报告均按连错次数计算。有稳定 `Question_ID` 的历史记录按当前 UID 汇总，题目移动后连续次数仍生效。`leech_fail_threshold` 仍可通过 `tuning` 覆盖，默认值改为 3。

## 修改文件

- `omrs/common.py`、`omrs/scheduling.py`、`omrs/stats.py`、`omrs/analytics.py`：默认阈值、连错计算和各端点派生结果。
- `assets/data.js`、`omrs_dashboard.html`：顽固题表显示连错次数与对应标题。
- `tests/test_leech_streak.py`：第三次连错、答对清零、累计次数保留和移动题目后归属的回归测试。
- `AI/algorithm.md`、`AI/api.md`、`AI/frontend.md`、`README.md`：同步现行行为。
- `AI/logs/log.md`：增加本日志索引。

## 验证

- `python3 -m unittest tests.test_leech_streak tests.test_recommendations tests.test_question_suspend tests.test_labels`：16 项通过。
- `python3 -m pytest -q tests/test_report_export.py`：6 项通过。
- `python3 tests/check_docs.py`：检查 14 个文档，0 处问题。
- 用临时题库启动 `omrs_engine.py`，实际浏览器打开数据复盘页：连错三次后顽固题表显示“连错 3”；提交一次正确反馈后刷新，表格变为“暂无数据”，`/api/stats` 显示 `fail_count=3`、`wrong_streak=0`、`is_leech=false`。

## 同步过的文档

`AI/algorithm.md`、`AI/api.md`、`AI/frontend.md`、`README.md`。
