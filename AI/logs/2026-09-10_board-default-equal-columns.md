# 2026-09-10 错题集默认对半分栏

## 变更摘要

展示板新建板与缺失配置的 `note_ratio` 默认值由 0.42 调整为 0.50。扣除题栏和手写区之间的 24px 间距后，两侧默认各约 347px。

## 行为与兼容性

已有展示板明确保存的 `note_ratio` 保持不变；已有纸面记录在「仅打印新增」时仍沿用记录中的比例，避免与原纸错位。前端和导出模板读取到缺失或非法比例时统一回退 50%。

## 修改文件

- 默认值与模板：`omrs/boards.py`、`omrs/export_templates/board.js`
- 前端：`assets/board.js`
- 测试：`tests/test_boards.py`、`tests/test_board_export.py`、`tests/test_board_ui.js`
- 文档：`README.md`、`AI/api.md`、`AI/board.md`、`AI/data.md`、`AI/export.md`、`AI/frontend.md`

## 验证

- `python3 -m unittest tests.test_boards tests.test_board_export`：31 项通过。
- `node --test tests/test_board_ui.js tests/test_board_preview.js`：22 项通过。
- `python3 -m unittest tests.smoke_board_print`：7 项 Playwright 打印测试通过。
- 用 Playwright Chromium 打开临时题库中新建板的实际导出 HTML：`note_ratio = 0.5`，内容区宽 718.11px，题栏 347.05px，右侧留白 347.06px，无页面脚本错误。
- `python3 tests/check_docs.py`：通过。

## 同步过的文档

同步根 README 的用户可见默认行为，以及展示板的数据、API、前端和导出模块文档。
