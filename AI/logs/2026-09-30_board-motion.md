# 2026-09-30 展示板页面切换动效

## 背景

用户要求展示板来回切换时加入平滑过渡，并在 `.brd-head` 增加动效菜单和时长滑杆。执行模式为 Codex 完整模式，基线提交为 `3c0df69`。工作区已有其他任务的未提交改动，本任务只修改展示板动效相关路径。

## 行为变化

纸面工具条新增“动效”入口。用户可以选择渐隐渐显、左右滑页、抽纸或关闭动效，并用 100–800ms、步进 50ms 的滑杆调整时长；默认值为渐隐渐显 / 280ms。偏好写入浏览器本地 `omrs-board-motion`，非法值回默认。单页嵌入式预览的翻页、页码跳转和跳题使用当前设置；再次操作会取消当前过渡并从当前逻辑页重新播放。切换展示板固定使用渐隐渐显，快速连续切板不会遗留旧 token 的透明 iframe。系统启用 `prefers-reduced-motion: reduce` 时立即切换并保留设置。独立下载 HTML、打印预览和纸面数据仍保持静态。

## 影响文件

核心代码：`assets/app/features/board/state.js`、`view.js`、`index.js`、`preview.js`、`board-popovers.css`；模板：`omrs/export_templates/board.js`、`board.css`。测试：`tests/app/board-page.test.mjs`、`board-preview.test.mjs`、`board-regions.test.mjs`、`tests/e2e/board.py`。文档与计划：`AI/frontend/board-ui.md`、`AI/board.md`、`AI/export.md`、`README.md`、`AI/plans/board-motion/`。

## 验证

已实际执行：

- `node --test tests/app/board*.test.mjs`：123/123 通过。
- `python3 tests/app/run_browser.py`：33/33 通过。
- `python3 tests/e2e/board.py`：28/28 通过，覆盖菜单、四种模式、时长、本地恢复、连续翻页和页面脚本错误。
- `python3 -m unittest tests.test_board_export tests.smoke_board_print`：15/15 通过。
- `python3 tests/check_ui.py`：0 问题；`python3 tests/check_contrast.py`：58/58 通过；`git diff --check` 通过。
- 视觉前后对比：标准脚本根路径受本地访问门禁影响，使用临时入口副本完成四组展示板截图对比；桌面浅色差异 0.301%、桌面深色 0.107%、手机两组 0%，无脚本错误和横向溢出。报告位于 `/tmp/omrs-visual-board-auth/report.html`。

未通过或未执行：

- `python3 tests/e2e/board_picker.py` 两次均因题库表格未就绪失败，页面脚本错误为 0；与展示板动效无关，未修改题库代码。
- `python3 tests/check_docs.py --write-log-index` 已更新索引；`python3 tests/check_docs.py --diff 3c0df69` 通过（0 个问题，3 条既有超长文档提醒）。最终改动范围复核随后完成。

提交只包含本任务的 18 个文件；提交哈希在最终汇报中给出。工作区其他未提交改动属于并行任务，已保留。

## 追补修复

用户录屏确认左右滑页 / 抽纸在动画结束后纸面仍向左偏移。实测原因是 `fill: "forwards"` 的 Web Animation 在 `finished` 回调中只恢复了内联布局，没有调用 `Animation.cancel()`，最后一帧的 `translateX(-50%)` 继续覆盖静态样式。`settlePageMotion()` 现在在正常结束和取消路径统一先取消动画，再恢复页面布局；E2E 额外检查目标页没有残留动画且计算后的 transform 为 `none`。

追补验证：`node --test tests/app/board*.test.mjs` 123/123；`python3 tests/e2e/board.py` 28/28；`git diff --check` 通过。
