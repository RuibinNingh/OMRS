# 2026-08-06 分类标点迁移与知识点清空

## 变更摘要

- 将数学分类目录及分类索引从 `一元二次函数,方程与不等式` 更名为 `一元二次函数、方程与不等式`。
- 更新该分类下 19 道题的 YAML `分类` 字段，并将全部 `相关知识点` 明确设为 `[]`；保留题目文件名、`_omrs_id`、状态标签、题干和答案。
- 修复 `omrs.projections._normalize_question_fields()`：显式空知识点列表不再回退到该题的旧知识点，投影重建后 `Knowledge_Tags` 会保持为空。

## Ledger 与历史兼容

- 迁移追加 38 条结构化审计提交：`CMT-000175` 至 `CMT-000193` 为 19 条 `question.move_external`，`CMT-000194` 至 `CMT-000212` 为 19 条 `question.metadata_update_external`。
- 未新增、删除或改写任何 `review.*` 提交；`history_log.csv` 与迁移前备份逐字一致。
- 投影重建未追加新 Ledger 提交，最终链头为 `CMT-000212`。

## 修改文件

- `错题/数学/一元二次函数、方程与不等式/`：分类目录、分类索引和 19 份题目 Markdown 元数据。
- `错题/.omrs/ledger.db`、`mastery_data.csv`：由工作区扫描与投影重建同步。
- `omrs/projections.py`：保留显式空知识点列表。
- `tests/test_history_projection.py`：覆盖清空知识点标签的回归场景。
- `AI/data.md`、`AI/logs/log.md`：记录数据语义与本次变更。

## 验证

- 创建迁移前完整备份：`Task/OMRS-backup-20260806-171806-before-category-rename.zip`。
- `python -m pytest tests/test_history_projection.py`：5 passed。
- Ledger 校验：`valid=true`，212 条提交，链头 `CMT-000212`。
- `mastery_data.csv`：新分类 19 条、旧分类 0 条、19 条的 `Knowledge_Tags` 均为空。
- 重启服务后工作区自检为 0 项变化、0 冲突；历史 CSV 与备份一致。

## 同步过的文档

- `AI/data.md`
- `AI/logs/log.md`
