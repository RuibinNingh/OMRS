# 2026-09-10 错题集移除装订预留

## 变更摘要

展示板导出的错题集不再为装订额外预留左侧空间。页面改为左右各 10mm 普通页边距，移除装订导引虚线、版面浮层中的「装订边」控件及 `binding_mm` 当前配置字段；默认右侧留白 42% 时，题栏宽度由约 376px 增至约 403px。

## 行为与兼容性

现有 `boards.json` 或 API 请求中的 `binding_mm` 作为未知设置忽略，其他打印设置继续生效。仅打印新增仍沿用纸面记录中的 `note_ratio` 与 `gap_lines`；所有新排版均使用固定的左右 10mm 页边距。

## 修改文件

- 版面与数据：`omrs/boards.py`、`omrs/exporting.py`、`omrs/export_templates/board.js`、`omrs/export_templates/board.css`
- 前端：`assets/board.js`、`assets/board_preview.js`
- 测试：`tests/test_boards.py`、`tests/test_board_export.py`、`tests/test_board_ui.js`、`tests/smoke_board_print.py`
- 文档：`README.md`、`AI/README.md`、`AI/api.md`、`AI/board.md`、`AI/data.md`、`AI/export.md`、`AI/frontend.md`

## 验证

- `python3 -m unittest tests.test_boards tests.test_board_export`：30 项通过。
- `node --test tests/test_board_ui.js tests/test_board_preview.js`：22 项通过。
- `python3 -m unittest tests.smoke_board_print`：7 项 Playwright 打印测试通过。
- 启动 `python3 omrs_engine.py --vault /root/workspace/apps/OMRS serve -p 8472`，用 Chromium 打开展示板纸面视图：版面浮层无装订设置；首张 `.page-inner` 左偏移 `37.7953px`、宽 `718.109px`，对应左右各 10mm；`.bind-line` 数量为 0；无页面脚本错误。
- `python3 tests/check_docs.py`：通过。

## 同步过的文档

同步根 README 的用户可见行为，以及展示板的数据、API、前端和导出模块文档。
