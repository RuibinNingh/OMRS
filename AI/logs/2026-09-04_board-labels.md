# 2026-09-04 展示板、用户标记与题库交互重设计（v1.14.0）

## 变更摘要

按 `Task/2026-09-04_展示板-标记-题库重设计.md` 落地 v1.14.0：

- 新增用户标记定义与题目标记链路：`labels.json`、Markdown YAML `标记:`
  、`question_labels` 投影、CSV `Labels`、单题/批量 CRUD、改名/删除/合并、
  筛选及可选调度加成。
- 新增持久化展示板：`boards.json`、题目稳定身份引用、增删改查、排序、停用/
  缺失处理、按标记同步、打印范围、高水位、孔位标记、答案附页和左题右空 A4
  导出。
- 重设计题库交互：筛选抽屉、标记 any/all、激活筛选 chips、列设置、密度、
  批量操作、视图预设和键盘操作。
- 将标记接入录入、题库、Modal、反馈、推荐、即时练习、导出、展示板、数据复盘
  和仪表盘。

## 行为与兼容性

- 展示板不进入 Ledger；板内保存 `question_id + uid`，读取优先稳定
  `question_id`。
- 停用题保留在展示板中但导出跳过；已删除题保留为 `missing`，由用户清理。
- 展示板默认题间距为 6 行，单题可增加 `extra_gap_lines`；纸面右栏不生成边框、
  底纹或笔记元素。
- 打印页眉固定为「错题集」，页脚只显示板内绝对页码；`last_printed_page` 用于
  默认打印下一页并在确认后推进。
- 标记始终使用 18% 淡底和彩色文字；调度默认不受标记影响，只有设置
  `priority_bonus` 后才加入优先级，并受 `label_bonus_cap=1.0` 限制。
- 旧 CSV 缺少 `Labels` 列时按空标记兼容；展示板旧的
  `note_align` / `note_min_lines` / `note_pattern` 字段会被忽略。

## 影响文件

- 后端：`omrs/labels.py`、`omrs/boards.py`、`omrs/server.py`、
  `omrs/question_ops.py`、`omrs/projections.py`、`omrs/workspace_sync.py`、
  `omrs/scheduling.py`、`omrs/analytics.py`、`omrs/stats.py`、
  `omrs/exporting.py`、`omrs/creation.py`、`omrs/common.py`、`omrs/version.py`
- 前端与模板：`omrs_dashboard.html`、`assets/*.js` 相关模块、
  `assets/styles.css`、`omrs/export_templates/board.css`、
  `omrs/export_templates/board.js`
- 测试：`tests/test_labels.py`、`tests/test_boards.py`、
  `tests/test_board_export.py`、`tests/test_labels_ui.js`、
  `tests/test_board_ui.js`
- 文档：`AI/*.md` 受影响模块、根 `README.md`、
  `Task/2026-09-04_展示板-标记-题库重设计.md`

## 验证

- `python3 -m unittest discover -s tests -v`：52 项通过。
- `node --test tests/test_labels_ui.js tests/test_board_ui.js`：5 项通过。
- `for f in assets/*.js omrs/export_templates/*.js; do node --check "$f"; done`：通过。
- `python3 -m compileall -q omrs omrs_engine.py`：通过。
- 已完成静态展示板导出检查；真实 Playwright/Puppeteer 打印回归尚未执行。
- `tests/smoke_frontend_actions_catalog.js` 的既有日期相关失败仍未处理。

## 同步过的文档

`AI/README.md`、`AI/algorithm.md`、`AI/api.md`、`AI/data.md`、
`AI/frontend.md`、`AI/export.md`、`AI/ledger.md`、`AI/optimization.md`、
`AI/labels.md`、`AI/board.md` 及根 `README.md` 已同步当前行为。
