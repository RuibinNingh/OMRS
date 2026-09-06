# 2026-09-06 · 文档事实审计

## 变更摘要

扫描当前工作区的根 README、`AI/*.md`、`Task/*.md` 和任务日志索引，按当前代码、测试和配置校正过时或误导性的现行行为描述。未修改顽固题算法；未恢复 Markdown `# 历史` 为正式复习记录源。

## 关键校正

- 明确正式反馈的事实链为 Ledger → 兼容投影 `history_log.csv`，Markdown `# 历史` 仅保留旧手工记录兼容解析。
- 记录 v1.16.0 题库界面的已知数据源错配：`attempts` 来自 Ledger 投影，而画廊 / 详情仍解析 Markdown 历史，因此可能显示“还没练过”，下一次反馈也不会自行修复。
- 更正前后端历史行正则并非字面完全一致。
- 更正展示板当前不绘制打孔圆圈，仅保留极浅 `.bind-line` 装订导引线；`binding_mm` 是装订边距。
- 更正展示板预计页数和纸面记录都通过隐藏 iframe 的浏览器布局测量获得，并同步页眉日期条件。
- 更正首次主题现状：启动脚本默认深色，但设置页帮助文案仍写“默认浅色”，技术债保持未完成。
- 保留 2026-09-04 展示板设计文档的历史性质，并在其中补充现行实现勘误，不把提案字段当作当前契约。

## 修改文件

- `AI/frontend.md`
- `AI/optimization.md`
- `AI/board.md`
- `AI/export.md`
- `README.md`
- `Task/2026-09-04_展示板-标记-题库重设计.md`
- `AI/logs/2026-09-06_practice-record.md`（追加事实勘误）
- `AI/logs/log.md`

## 验证

- `git diff --check` 通过。
- `python3 -m unittest discover -s tests -q`：59 tests OK。
- `node --test tests/test_question_record_ui.js`：10 tests passed。
- 文档关键词复扫完成；仍保留的 `last_printed_page`、`binding_marks`、默认 6 行等内容均位于历史设计/历史日志，并已加现行实现勘误。
- `pytest` 未安装，因此未运行 pytest 风格的 `tests/test_report_export.py`。

## 同步过的文档

- `AI/README.md` 的文档索引和维护规则已作为审计依据复核；无需改变其事实内容。
