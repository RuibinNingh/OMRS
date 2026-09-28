# 2026-09-28 展示板 UI 改版

## 背景

按 `AI/plans/board-redesign/plan.md` 与同目录 `target.html` 重做展示板工作区。执行者为 Codex，完整模式；基线为当前仓库 `HEAD`（v1.28.1）。开工前工作区有无关未跟踪目录 `.playwright-mcp/`，本任务未改动、未纳入提交。

## 行为变化

- 桌面工作区改为板列表、板头、常驻纸面、题目面板；页面进入展示板时应用侧栏收成图标栏。窄屏板列表作为抽屉打开，题目面板移到纸面下方。
- 去掉纸面 / 列表 / 画廊的切换；原版式与纸面记录检查器改为浮层，题目详情从题目面板右侧滑入。行内可步进调整题后留白，详情层可用预设和继承值。
- 按板把关联标记保存在浏览器本地，点击「同步」时仍通过现有追加接口同步，不写入新的服务端字段。打印预览后显示独立确认条，用户确认才记录纸面。
- 保留现有保存队列、打印协调、纸面续排与常驻 iframe。`detail.js` 只扩展保存状态通知、纸面点题回调和按本地关联标记同步入口，不改变数据格式或服务端 API。

## 影响文件

- `assets/app/features/board/`：重排 `view.js`、`state.js`、`index.js` 与小范围修改 `detail.js`；新增 `board-layout.css`、`board-list.css`、`board-popovers.css`；原 `board.css` 保留通用样式。
- `assets/app/styles/index.css`、`tokens.css`：引入新样式，增加深浅色桌面 token；纸张阴影沿用导出模板。
- `tests/app/board-page.test.mjs`、`board-regions.test.mjs`，`tests/e2e/board.py`、`board_picker.py`、`p8_test_modules.js`：覆盖新结构、行内留白、详情、浮层、保存、锁定、补印与手机抽屉；关联标记断言等待菜单动作完成。
- `AI/board.md`、`AI/frontend/board-ui.md`、`AI/frontend/design-system.md`、`AI/frontend/shell.md`、`AI/frontend/qview.md`、`AI/frontend.md`、`README.md`：同步当前页面、样式、题面调用点和用户可见入口；`AI/plans/board-redesign/progress.md` 记录执行结果。

## 验证

已实际执行：

- `node --test tests/app/board*.test.mjs`：120/120；`node --test tests/app/*.test.mjs`：326/326。
- `python3 -m unittest discover -s tests -p 'test_*.py' -q`：182/182。
- `python3 tests/e2e/board.py`：23/23；`python3 tests/e2e/board_picker.py`：31/31；`python3 tests/app/run_browser.py`：32/32。
- `python3 tests/check_ui.py`：全仓 0 处问题；`python3 tests/check_contrast.py`：58 组全通过。
- `python3 tests/visual/run.py --ref HEAD --out /tmp/omrs-board-redesign-visual-final`：48 张截图，4 张展示板截图有预期差异，其余 44 张为 0；页面脚本错误为 0。展示板四档运行时审计均无小于 28px 的可点区域、行内样式或页面横向溢出，最小字号 11px。
- `python3 tests/check_docs.py --write-log-index`：已生成日志索引；`python3 tests/check_docs.py --diff HEAD`：42 个文档，0 处问题、2 条已有文件体积提醒。

未执行：物理打印机实物验收；隔离浏览器已验证预览、确认记录与仅新增续排位置。

## 视觉差异

与 `HEAD` 比较，只有展示板页变化：桌面浅色 14.719%、深色 23.199%，手机浅色 43.739%、深色 72.532%。差异来自原状态条、三视图和常驻检查器改为板头、常驻纸面、题目面板与浮层；手机还改为板列表抽屉和纸面下方题目列表。深色页面受大面积桌面与面板配色影响，像素差异更高。其余 11 页 × 4 档截图没有变化。手机工具条内部允许横向滚动，整页没有横向溢出。
