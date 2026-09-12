# 展示板版式锁定、详情入口与调度反馈表清理

## 行为变化

- 展示板把版式、打印范围、切割线、答案显示、锁定和纸面记录集中到「版式与打印」浮层。
- 打开启用版式锁定后，版式字段、题后留白、排序以及板内题目增删会先确认；确认后服务端清空纸面记录，状态回到未打印，并把被替换的纸面快照追加到 `boards_printed_history.jsonl`。
- 展示板列表、画廊和纸面检视条提供题目详情入口；收件箱中点击「已录入」条目直接打开题目详情。
- 复习调度页移除 Session 历史和反馈表卡片及其刷新入口；独立「反馈录入」工作台与 `/api/feedback` 保留。

## 影响文件

- `omrs/boards.py`
- `assets/board.js`
- `assets/styles.css`
- `assets/inbox.js`
- `assets/schedule.js`
- `assets/recommend.js`
- `assets/recommend_v2.js`
- `omrs_dashboard.html`
- `tests/test_boards.py`
- `AI/board.md`
- `AI/api.md`
- `AI/data.md`
- `AI/frontend.md`
- `README.md`

## 验证

- `python3 -m unittest tests.test_boards tests.test_board_export`：通过。
- `node --test tests/test_board_ui.js tests/test_board_preview.js tests/test_feedback_ui.js`：通过。
- `node --check` 相关 JavaScript、`python3 -m py_compile omrs/boards.py omrs/server.py`：通过。
- `git diff --check`：通过。
- `python3 omrs_engine.py serve --port 8472` 启动成功；Playwright 访问真实页面，确认统一浮层、锁定控件、题目详情入口存在，调度页 Session 反馈卡片已移除。
