# 2026-09-27 前端重构 P7：展示板迁移（第 1 轮 v1.26.0 纯函数与测试；第 2 轮 v1.26.1 保存队列、打印协调、常驻预览；第 3 轮 v1.26.2 拖拽排序、版面设置；第 4 轮 v1.26.3 选板浮层原生；第 5 轮 v1.26.4 页面外壳原生、板列表数据所有权；第 6 轮 v1.26.5 整页原生、删除 board.js）

## 背景

- 用户原话：「直接推进P7,不需要等到P6,隔离完成」「继续」；第 2 轮「继续第二轮,最后在合入」（U17：不逐轮合入，P7 做完一次合入）；第 3 轮「继续」；第 4 轮「继续推进P7」「继续」。
- 所属计划：`AI/plans/frontend-rearch/`，P7 第 1 步（`plan.md` §6 P7：先搬纯函数和测试）。轮次安排见 `progress.md` §5c。
- 理解：P7 不等 P6 剩余页面（历史记录、目录、报告、设置、录入题目），单独推进。本轮只动展示板自己的文件；和 P6 共用的文件（`legacy-bridge.js`、`AGENTS.md` 映射表、版本号四处、`changelog.md`、`progress.md`）只加独立的小段，便于 `git apply --3way` 合并。
- 运行模式：受限模式。判定依据：源码来自上传的 `OMRS-source-sanitized-20260927T013727Z.zip`，工作目录没有 `.git`。解压后先把导出包原样提交为基线。
- 基线：导出包 `20260927T013727Z`，版本 v1.25.4。包里没有 `AI/logs/`，本日志是包内唯一的日志；没有生成 `AI/logs/log.md`。
- 环境探测：Python 3.12.3、Node 22.22.2、git 2.43.0、Chromium 141（独立启动，无 CDP）；网络 403；1 核、4GB。

## 行为变化

无用户可见变化。展示板页、选板浮层、常驻预览、打印与纸面记录的行为、文案、请求体都不变。唯一可见的差别是侧栏版本号变为 v1.26.0。

## 盘点（P7 第 1 步）

三个旧脚本共 2252 行：`assets/board.js` 1612 行，`assets/board_picker.js` 414 行，`assets/board_preview.js` 226 行。

**不碰 DOM、不读全局、本轮搬走的：**

- `board.js`：`boardGapCm`、`boardStatusModel`、`boardMoveItems`、`boardItemsPayload`、`boardEffectiveGap`、`boardUniqueUids`、`boardFormatTime`、`boardPaperLayoutChanged`、`boardColumnWidth`、`boardDirtyMerge`、`boardSavePayload`、`boardEstimateText`，以及常量 `CUT_LINES`、`BOARD_LINE_PX`、`BOARD_MM_PX`。
- `board_picker.js`：`boardFolderTree`、`boardPickerRowState`、`boardPickerFilter`、`boardPickerRecent`。

**读全局、本轮只拆出计算的：** `boardContentSignature()`、`boardPreviewGaps()`。计算部分变成纯函数 `boardItemsSignature(items)`、`boardGapMap(items)`，旧函数改成一行包装，继续读 `BOARD_DETAIL`。

**本轮不动的：**

- 带全局回退的 `boardPrintedSummary()` / `boardHasPaper()`，它们在无参调用时读 `BOARD_DETAIL`；
- 预览控制器 `board_preview.js` 整体，包括 `boardPreviewKey`，第 2 轮随打印协调一起进模块；
- 其余所有读写 DOM 或 `BOARD_*` 状态的函数。

**外部调用方：** `grep` 确认，搬走的函数在 `assets/` 其它文件、`omrs_dashboard.html` 和 Python 测试里都没有调用。旧脚本只在函数体里调用它们，文件顶层没有调用，所以过渡桥在模块执行时才挂上也不影响加载。

## 影响文件

**新增：**
- `assets/app/features/board/model.js`：页面纯函数，约 190 行。
- `assets/app/domain/board/model.js`：选板纯函数。选板被题目库、数据复盘、复习调度、展示板多页调用，所以放在 domain。

**改名：** `assets/app/domain/board.js` → `assets/app/domain/board/index.js`。它再导出上面的纯函数，并保留 `boardQuickAdd` / `boardChooseAndAdd` 两个适配器。`features/data/index.js`、`features/questions/index.js` 的 import 各改一行。

**修改：**
- `assets/app/legacy-bridge.js`：新增 `installBoardBridge`，用 `Object.assign` 把两个模块的导出按原名挂回全局。两个模块的导出不重名，由单测检查。
- `assets/board.js`：删掉搬走的定义和 `module.exports`，文件头注明新位置，1612 → 1499 行。
- `assets/board_picker.js`：删掉 4 个纯函数和 `module.exports`。

**测试迁移，旧文件删除：**

| 旧文件 | 新文件 | 用例 |
|---|---|---|
| `tests/test_board_ui.js` | `tests/app/board.test.mjs` | 14 条原样保留，另加 6 条：内容签名、留白表、锁定边界、时间格式、几何常量、两模块导出不重名与适配器 |
| `tests/test_board_regions.js` | `tests/app/board-regions.test.mjs` | 17 条原样。状态机测新模块；INV 静态检查仍读旧 `assets/board.js` 源码 |
| `tests/test_board_preview.js` | `tests/app/board-preview.test.mjs` | 10 条原样。被测的仍是经典脚本，用 `createRequire` 载入 |
| `tests/test_board_locked_incremental.js` | `tests/app/board-locked.test.mjs` | 20 条原样。旧 `board.js` 仍在 vm 里真跑，两个模块的导出注入同一上下文 |

合计 61 → 67 条，没有删减。

**版本：** v1.26.0，同步了 `omrs/version.py`、`omrs_dashboard.html` 侧栏、`README.md`、`AI/README.md`，并在 `AI/changelog.md` 顶部加了一段。

**文档：**
- `AI/frontend/board-ui.md`：速查头的入口与必跑测试；新增「代码位置（P7 迁移中）」一节。
- `AI/board.md`：源文件清单、测试路径、`boardEffectiveGap` 的三处同解。
- `AI/frontend/architecture.md`：`domain/board/`，过渡桥表加 `installBoardBridge`。
- `AI/frontend/components.md`：过渡桥列表。
- `AI/frontend/library.md`、`AI/frontend/records.md`：「加入展示板」经 `domain/board/index.js`。
- `AI/optimization.md`：「board.js 多职责」一条改为「进行中」，测试路径也一并更新。
- `AGENTS.md`：映射表加一行 `features/board/`、`domain/board/`。
- 计划文件：`plan.md` 的速查和 P7 执行者、`progress.md`（状态块、U16、§2、§3、§4、§5c、§8、§9）、`AI/plans/README.md`。

**勘误：** `AI/changelog.md` 的 v1.18.0 段引用了已删除的 `tests/test_board_regions.js`，`check_docs` 因此报错。把它改成不带代码格式的路径，并注明新位置，原文的其余部分没动。

## 验证

**已实际执行**（沙箱，独立 Chromium）：

| 项 | 结果 |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 159 OK（改前同为 159） |
| `node --test tests/*.js tests/app/*.test.mjs` | 226 / 226（改前 220） |
| `python3 tests/check_ui.py` | 0 处问题；存量不变：handlers 127、html_assign 84、inline_style 126、color_literals 103、font_size_literals 227 |
| `python3 tests/check_contrast.py` | 58 组，0 不达标 |
| `python3 tests/check_docs.py --diff <基线>` | 0 处问题，2 条提醒（`AI/api.md` 53KB、`exec-2026-09-26-codex.md` 48KB，都是既有的） |
| `tests/e2e/shell_router.py` / `ui_bridge.py` / `data.py` / `questions.py` | 20/20、15/15、21/21、92/92 |
| `python3 -B tests/smoke_board_lock.py` | 退出码 0（在 Chromium 里驱动展示板页：加题、锁定确认、仅补印新增） |
| `unittest tests.smoke_board_integrity tests.smoke_board_print tests.smoke_board_print_geometry` | 15 项中 1 项失败：`smoke_board_print` 的 `test_full_then_incremental_print`（仅补印新增的第一页不是占位页）。在基线 worktree 上跑同一测试，失败方式与报错完全相同，所以不是本轮引入的。本轮也没有改导出模板和后端。见 progress §8 |
| `tests/visual/run.py --ref <基线>` | 48 张图中 24 张有差异，全是桌面图，每张 ≤0.005%。21 张的差异框是 (48,872)–(69,881)，即侧栏版本号；history / reports / settings 的深色桌面图另有 13–33 个零散像素，是抗锯齿噪声，没有布局变化。手机图侧栏收起，无差异 |

**手工路径**（隔离实例：full fixture，端口 18473，真实浏览器）：

- 打开 `#/board`：状态条显示「还没打印过 / 7 题 / 🖨 打印全部」（状态机）；翻页条显示「预计 2 页 · A4 纵向 · 左右 10 / 上下 12mm」（估算文案）。检查器显示「题栏约 403px」（`boardColumnWidth(42)`）和「2 行 ≈ 1 cm」（`boardGapCm`）。
- 列表视图里 Ctrl+↓ 排序：接口返回的顺序对调（`boardMoveItems` + `boardItemsPayload`）。
- 右侧留白滑块改到 42：接口返回 `note_ratio` 0.42（`boardDirtyMerge` + `boardSavePayload`）。
- 在题目库页调 `boardQuickAdd`：选板浮层打开，输入板名过滤出 1 行（`boardPickerFilter`），单击后题目加入（`boardPickerRowState`）。
- 全程控制台和页面错误为 0。截图只存在 `/tmp`，不入库。

**其余全量门禁（同一沙箱，改完文档与版本号之后）：**

- `tests/app/run_browser.py` 34 / 34；`tests/e2e/dashboard.py` 26 / 26；`schedule.py` 45 / 45；`feedback.py` 31 / 31；`smoke_schedule_workbench` OK。
- `tests/e2e/instant.py` 第一次在「旧入口」段等空态里的「加载」按钮超时（8s），因为这一段没有 `guarded()` 包住，脚本异常退出。立即重跑 23 / 23。本轮没有改即时练习，按偶发处理；progress §4 已记有同一脚本的偶发失败。

**未执行：** Firefox / WebKit；CDP 模式；生产验证（受限模式做不了）。

## 第 2 轮（v1.26.1）：保存队列、打印协调、常驻预览

在第 1 轮的完整包上继续（沙箱里第 1 轮已作为本地提交），没有新导出包。

### 行为变化

无用户可见变化。唯一的外观差别在打印预览窗口弹出后、导出回来前那一两秒的占位页：原来写死 `style=` 与 `#444` / `#888`，改成 `<style>` 里用系统字体与系统色（`CanvasText` / `GrayText`），文案不变。

### 盘点

- 保存队列（`board.js`）：`BOARD_DIRTY`、`BOARD_SAVE_TIMER`、`BOARD_SAVE_IN_FLIGHT`、`boardMarkDirty`、`boardFlushSave`；外部读写者：`boardPersistItems`（整体提交 items 时去掉脏标记）、`boardSyncPreview`（有保存时不导出）、切 Tab 的捕获监听、`beforeunload`；测试 `smoke_board_integrity.py`（读 `BOARD_DIRTY?.print`）、`board-locked.test.mjs`（写 / 读 `BOARD_DIRTY`）。
- 打印协调（`board.js`）：`BOARD_PRINT_JOBS`、`BOARD_WINDOWS`、`boardFetchExport`、`boardExportCurrent`、`boardMarkAwaiting`、`boardMeasureLayout`、`boardRecordPrinted`、`boardMarkPrinted`、`boardResetPrinted`、window 的 message 监听；测试 `smoke_board_integrity.py`（读 `BOARD_WINDOWS`）、`smoke_board_print_geometry.py`（调 `boardMarkAwaiting`）、`board-locked.test.mjs`（写 `BOARD_WINDOWS` / `BOARD_PRINT_JOBS`，调 message 监听）。
- 常驻预览：整份 `assets/board_preview.js`（`BP_*` 状态、`boardPreview*`）；测试 `smoke_board_integrity.py` 读 `BP_FRAME`（5 处），`board-regions.test.mjs` 读源码。
- 这些旧名在 `assets/` 其它文件与 `omrs_dashboard.html` 里没有调用；新模块五个的导出（46 个名字）与所有旧经典脚本的顶层名不重名（脚本逐一比对），过渡桥 `Object.assign` 不会覆盖旧函数。

### 影响文件

- 新增 `assets/app/features/board/save.js`（`createBoardSaveQueue`、`boardAdoptSaved`）、`print.js`（`createBoardPrint`、`fetchBoardExport`、`measureBoardLayout`）、`preview.js`（由 `assets/board_preview.js` 改为 ES 模块，导出请求改走 `fetchBoardExport`，其余逐行不变）。
- 删除 `assets/board_preview.js`；`omrs_dashboard.html` 去掉它的 `<script>`，`board.js` / `board_picker.js` 的 `?v=` 改为 `20260927-p7r2`。
- `assets/board.js`：删掉上述状态与实现，改为 `boardSaveQueue()` / `boardPrint()` 懒创建实例并注入回调（当前板、请求、采纳返回的板、提示、确认、重绘），旧函数名保留为一行包装；1499 → 1346 行。
- `assets/app/legacy-bridge.js`：`installBoardBridge` 另挂 save / print / preview 三个模块。
- 测试：新增 `tests/app/board-save.test.mjs`（8）、`board-print.test.mjs`（7）；`board.test.mjs` 加一条五模块导出不重名（20 → 21）；`board-preview.test.mjs` 改为动态 import 模块（10，原样）；`board-locked.test.mjs` 注入保存与打印模块，`BOARD_DIRTY` / `BOARD_WINDOWS` / `BOARD_PRINT_JOBS` 改为 `boardSaveQueue()` / `boardPrint()` 的访问器（20，原样）；`board-regions.test.mjs` 读预览模块源码（17，原样）；`tests/smoke_board_integrity.py` 的 `BOARD_DIRTY`、`BOARD_WINDOWS`、`BP_FRAME` 改用 `boardSaveQueue().dirty()`、`boardPrint().windows`、`boardPreviewFrame()`，断言不变。
- `tests/ui_baseline.json`：删 `assets/board_preview.js` 一行，`assets/board.js` 的 inline_style 与 color_literals 各 −2（`--update-baseline`）。
- 版本 v1.26.1（四处）与 `AI/changelog.md`；文档 `AI/frontend/board-ui.md`（速查、代码位置表、预览与保存队列两节）、`AI/board.md`、`AI/frontend/shell.md`（加载顺序去掉 board_preview）、`AI/frontend/architecture.md`、`AI/frontend/components.md`、`AI/optimization.md`；计划 `progress.md`（状态块、U17、§2、§3、§4、§5c、§8、§9）。

### 验证

第 2 轮的验证结果（沙箱，独立 Chromium）：

| 项 | 结果 |
|---|---|
| unittest | 159 OK |
| node | 242 / 242（第 1 轮后 226；+8 保存、+7 打印、+1 契约） |
| `check_ui` | 0 处问题；存量 inline_style 124、color_literals 101（各 −2），其余不变 |
| `check_contrast` / `check_docs --diff <第 1 轮提交>` / `git diff --check` | 58 组 0 不达标 / 0 处问题、3 条提醒（`AI/api.md`、执行说明两条既有；`progress.md` 本轮到 40KB，第 3 轮把 §5 / §5b 里「原第 N 轮开工（留作记录）」几段挪进 changelog 或删去） / 无空白问题 |
| `tests/app/run_browser.py` | 34 / 34 |
| E2E | shell_router 20/20、ui_bridge 15/15、dashboard 26/26、data 21/21、schedule 45/45、feedback 31/31、questions 92/92、instant 23/23（第一次 22/23，失败项是 progress §4 已记的偶发「标记筛选」，立即重跑全过） |
| `unittest tests.smoke_board_integrity tests.smoke_board_print_geometry` | OK（9 项）。第一次跑 integrity 8 项全部报错：测试在等待条件里读旧全局 `BP_FRAME`，它随预览迁进模块后不再是全局；改成 `boardPreviewFrame()` 后全过 |
| `smoke_board_print` | 7 项 1 失败，与第 1 轮、与导出包基线相同（`test_full_then_incremental_print`） |
| `smoke_board_lock.py` / `smoke_schedule_workbench` | 退出码 0 / OK |

手工路径（隔离实例 full fixture，端口 18474，真实浏览器）：

- 常驻预览排出 2 页；拖右侧留白滑块后队列 `busy()`、脏字段为 print，去抖后一次 POST，接口返回 0.46；
- 改完立刻刷新页面，`sendBeacon` 把 0.5 送到服务端；
- 点「🖨 打印全部」弹出预览窗口，任务登记在 `boardPrint().windows`，窗口回传的版面写进任务快照（HTML 释放），主按钮翻成「✓ 记录纸面」；点它确认后服务端有纸面（8 题 / 2 页），主按钮回到「🖨 打印全部」；
- 加一道题 → 切「仅新增」→ 主按钮「补印新增 1 题」→ 预览窗口排出 `mode:new` → 记录后新增归零、已印题数 +1；
- 「清空纸面记录」确认后纸面归零；全程控制台与页面错误 0。
- 第一次走查「记录纸面后主按钮复位」一项判为失败：检查写在「纸面记录已写入」之后立刻读按钮文案，而状态条要等随后的重载才重绘。改为等待条件后通过，不是缺陷。

## 第 3 轮（v1.26.2）：拖拽排序、版面设置

在第 2 轮完整包上继续（沙箱里第 2 轮已作为本地提交）。

### 行为变化

- 「按标记同步」对话框打开时焦点落在「同步到展示板」上。原来传的是 P2 之前的选择器 `[data-ui-ok]`，对话框里没有这个元素，焦点落在默认位置（progress §8 登记的遗留）。
- 其余无变化：拖拽与键盘排序、左栏树拖拽、版式字段的钳值与枚举兜底、锁定确认的时机与文案、答案 / 标记开关立即保存都照旧。

### 盘点

- 拖拽：`boardBindDrag`（舞台列表行）、`boardBindTreeDrag`（左栏树三种落点）、快捷键里的 Ctrl/⌘+↑↓ 与 ↑↓ 计算。拖拽中按 Esc：HTML5 拖放由浏览器取消，只触发 dragend、不触发 drop，两处 dragend 都会清空拖拽状态，原实现就不会误移，本轮补了用例。
- 版面设置：`boardApplyPrintField`、`boardSetItemGap`、`boardAllowLayoutChange`、`BOARD_LAYOUT_CONFIRM` / `BOARD_LAYOUT_GRANTED`（`boardReloadData` 与保存成功后收回授权）。外部读者：`board-locked.test.mjs` 读 `BOARD_LAYOUT_GRANTED`；`board-regions.test.mjs` 静态检查 `boardApplyPrintField` 源码里要有 `boardRefreshLiveReadouts`；冒烟测试只调函数名。
- 七个模块的导出（55 个名字）与旧经典脚本的顶层名仍不重名（脚本比对）。

### 影响文件

- 新增 `assets/app/features/board/drag.js`、`settings.js`。
- `assets/board.js`：拖拽两处改为调用绑定函数并注入写入回调；版面设置改为 `boardSettings()` 懒创建、注入界面钩子（比例读数、切割线标签禁用、检查器 / 状态条 / 读数刷新、留白输入框回填），`boardApplyPrintField` / `boardSetItemGap` / `boardAllowLayoutChange` 是一行包装；键盘排序用新纯函数；`[data-ui-ok]` → `[data-dialog-ok]`；1346 → 1260 行。`omrs_dashboard.html` 的 `?v=` 改为 `20260927-p7r3`。
- `assets/app/legacy-bridge.js`：`installBoardBridge` 另挂 settings / drag。
- 测试：新增 `tests/app/board-settings.test.mjs`（6）、`board-drag.test.mjs`（5，含用 DOM 替身跑拖拽绑定与 Esc 取消）；`board.test.mjs` 的模块契约扩到七个模块（条数不变）；`board-locked.test.mjs` 注入 settings / drag，`BOARD_LAYOUT_GRANTED` 改读 `boardSettings().granted()`（20，原样）；`board-regions.test.mjs` 的「改板级字段后刷新读数」改查 `boardSettings` 源码里注入的钩子（17，原样）。
- 版本 v1.26.2（四处）与 `AI/changelog.md`；文档 `AI/frontend/board-ui.md`（速查与代码位置表）、`AI/board.md`、`AI/frontend/architecture.md`、`AI/frontend/components.md`、`AI/optimization.md`；计划 `progress.md`（状态块、§3、§4、§5c；删去 §5b 里 P6 第 1–5 轮已完成的开工条目，文件回到 40KB 以下）。

### 验证

| 项 | 结果 |
|---|---|
| unittest | 159 OK |
| node | 253 / 253（第 2 轮后 242；+6 设置、+5 拖拽） |
| `check_ui` / `check_contrast` / `check_docs --diff <第 2 轮提交>` / `git diff --check` | 0 处问题（存量同第 2 轮）/ 58 组 0 不达标 / 0 处问题 / 无空白问题 |
| `tests/app/run_browser.py` | 34 / 34 |
| E2E | shell_router 20/20、ui_bridge 15/15、dashboard 26/26、data 21/21、schedule 45/45、instant 23/23、feedback 31/31、questions 92/92 |
| `smoke_board_integrity` + `smoke_board_print_geometry` / `smoke_board_lock.py` | OK（9 项）/ 退出码 0 |
| `smoke_board_print` / `smoke_schedule_workbench` | 7 项 1 失败，与前两轮、与导出包基线相同 / OK |

手工路径（隔离实例 full fixture 副本，端口 18475，真实浏览器，用 Playwright 的真实 HTML5 拖放）：

- 列表视图把第 3 行拖到第 1 行，接口返回的顺序对应改变；
- 派发 dragstart → Esc → dragend → drop，顺序不变，也没有残留的 `.dragging` / `.drag-over`；
- Ctrl+↓ 下移选中题并保存；
- 左栏把板拖进新建的文件夹，接口返回的 `folder_id` 变为该文件夹；
- 未锁定时改右侧留白直接保存，读数显示 36%；
- 记录纸面后上锁，上锁本身不弹确认；锁定后改比例弹「版式已锁定，确认修改？」：取消则服务端不变、滑块回到 36；确认则生效，服务端清空纸面记录；
- 「按标记同步」对话框打开后焦点在「同步到展示板」；
- 全程控制台与页面错误为 0。

## 第 4 轮（v1.26.3）：选板浮层原生

在第 3 轮完整包上继续。上传包里没有原始导出包，只有第 3 轮完整包和各轮补丁；把累计补丁 `p7-r1-r3` 从第 3 轮完整包上反向应用，还原出补丁基线 `20260927T013727Z`（v1.25.4），核对「基线 → 第 3 轮」的 diff 与累计补丁逐字节一致（263589 字节）后，以它为基线提交。本轮分两次会话：第一次写完主体代码，第二次开头先把 WIP 补丁存进下载目录，再补测试、文档与收尾。

### 行为变化

- `Ctrl/⌘ + Enter` 连加：加入高亮的板但浮层不关（与底栏提示「⌘ 连加」对上；原来 Enter 带不带修饰键都是普通加入）。
- 浮层开着时背后页面的快捷键不再触发：原来焦点不在搜索框时按 V，搜索框会得到字母，同时题库也切了视图。
- `←` 折叠高亮行所在的文件夹后，高亮移到组后第一行，紧接着 `→` 展开同一个组、高亮回到组里第一行。原来折叠后高亮跳回最前面，`→` 找不到组；高亮在未归档组时 `←` 还会折叠上一个文件夹。
- 搜索框的 `aria-activedescendant` 指向行元素的 id（原来写的是板 id，读屏找不到元素）。
- 「换个板…」加入新板后的提示写「已从《原板》移到《新板》」：原来在排除了原板的候选列表里找原板名，总是空，提示退化成「已加入《新板》」。
- 浮层不在对话框里时，关闭后焦点回到触发元素（原来落到 body）；叠在题目弹窗上时照旧由 `ui/overlay` 还给「加入展示板」按钮。
- 外观：token 化（字号只剩 13 / 12px 两档，桌面浅色实测 1 种带文字字号）；关闭按钮与文件夹组标题是 `ui-btn` 尺寸的按钮，可点目标桌面 ≥28、手机 40；「已全部在板中」的行用前景色退一档，不用透明度；手机隐藏底栏键盘提示；进浏览器顶层（popover），不再靠 `z-index:1200`。
- 其余照旧：单击即加入、⌘ 点击撤回本次加入、全部已在板中的行点了打开该板、过滤与「最近」、新建板（对话框里文件夹默认上次用的板所在的文件夹）、Shift 直接加入与 toast 的撤销 / 换个板、一个板都没有时直接弹「新建」、触屏不自动聚焦。

### 盘点

- 旧 `board_picker.js` 357 行：浮层 DOM 与事件、行 / 元信息 HTML、键盘高亮、定位、提交 / 撤回 / 连加、刷新、新建（两条路径）、Shift 直接加入。外部调用方：`board.js`（`boardAddUids`、`qbChooseBoardForUids`，以及 `boardFolderToggle` 里改 `BOARD_PICKER.collapsed`）、`inbox.js`、`domain/question/mount.js`、`domain/sessions.js`（按名调 `boardQuickAdd`）、`domain/board/index.js`；测试 `smoke_board_integrity.py`（`boardPickerOpen`）、`questions.py`（读 `BOARD_PICKER`）、`data.py`（`[class*="picker"]`）。
- 浮层依赖 `board.js` 的：`BOARD_DATA` / `BOARD_FOLDERS` / `BOARD_DETAIL`（`let`）、`boardLastId`、`boardRemember`、`boardFolderCollapsed`、`boardFolderToggle`、`boardAddToBoard`（含保存队列冲刷与撤销 toast）、`boardReloadData`、`boardLoad`。这些集中在 `domain/board/source.js`，展示板页迁完后换实现。
- 键盘：旧实现挂在 document 捕获阶段、`stopPropagation`。新实现不能也放捕获阶段：`core/keys` 的监听先于 `ui/overlay` 注册，Esc 会先关浮层，overlay 再看时客人已经不在，就把题目弹窗也关了。所以浮层登记为客人时 `escape:true`（在对话框里由 overlay 代关），其余键走 `core/keys` 冒泡阶段的新浮层层；冒泡阶段别的旧 document 监听也会收到，`board.js` 改为查 `boardPickerIsOpen()` 让位（`app.js` / `inbox.js` 的 Esc 影响很小，见 progress §8）。

### 影响文件

- 新增 `assets/app/domain/board/picker.js`（控制器，332 行）、`picker-view.js`（模板）、`picker.css`（`@layer domain`，在 `styles/index.css` 登记）、`source.js`（过渡期数据来源）。
- `assets/app/domain/board/model.js`：行模型 `boardPickerItems`、`boardPickerDefaultActive`、`boardPickerStep`、`boardPickerFoldTarget`、`boardPickerRowAfterGroup`、`boardPickerPlan`、`boardPickerPosition`。`index.js`：`boardQuickAdd` / `boardChooseAndAdd` 直接打开新浮层，另再导出浮层入口。
- `assets/app/core/keys.js`：`pushKeyLayer` / `keyLayerCount`。
- `assets/app/legacy-bridge.js`：`installBoardBridge` 另挂 `boardPickerOpen` / `boardPickerClose` / `boardPickerIsOpen` / `boardQuickAdd` / `boardChooseAndAdd`，逐条注明调用方；`__omrsUi.host` 的注释去掉选板一项。
- 删除 `assets/board_picker.js` 与它的 `<script>`；`board.js` 去掉 `BOARD_PICKER.collapsed` 那行、页面快捷键让位、文件头注明新位置；`omrs_dashboard.html` 的 `board.js?v=` 改为 `20260927-p7r4`。
- `assets/styles.css`：删 `.bd-picker-*`、`.bd-new-folder`、`@keyframes bdPickerIn` 与它们的注释、手机段两条（55 行）；`tests/ui_baseline.json` 删 `board_picker.js`、`styles.css` 下调（颜色 83→82、字号 205→193）。
- `assets/app/features/questions/index.js`：只改一行注释（「点外面关闭」的说明）。
- 测试：新增 `tests/app/board-picker.test.mjs`（11）、`tests/e2e/board_picker.py`（31）；`core.test.mjs` +3（浮层层）；`board.test.mjs` 的两条契约改为含选板浮层（条数不变）；`questions.py` 两处改查 `.bpicker`（条数不变）。
- 版本 v1.26.3（四处）与 `AI/changelog.md`；文档 `AI/frontend/board-ui.md`、`AI/board.md`（§3.2 键盘与挂载）、`AI/frontend/architecture.md`（`core/keys` 表、过渡桥两行）、`AI/frontend/components.md`、`AI/frontend/design-system.md`、`AI/frontend/library.md`、`AI/frontend/shell.md`、`AI/optimization.md`、`AI/environment.md`；计划 `progress.md`（状态块、§3、§4、§5c、§8；§5 P5 的已完成清单压成一段，文件回到 40KB 以下）。
- 勘误：progress §8 第一条「`[data-ui-ok]` 过时，P7 顺手改」在第 3 轮已经修掉，本轮删去。

### 验证

| 项 | 结果 |
|---|---|
| unittest | 159 OK |
| node | 267 / 267（第 3 轮后 253；+11 选板浮层、+3 键盘层） |
| `check_ui` / `check_contrast` / `check_docs --diff <基线>` / `git diff --check` | 0 处问题（存量 handlers 127、html_assign 81、inline_style 124、color_literals 100、font_size_literals 215）/ 58 组 0 不达标 / 0 处问题、2 条既有提醒 / 无空白问题 |
| `tests/app/run_browser.py` | 34 / 34 |
| E2E | board_picker 31/31（新）、questions 92/92、data 21/21、feedback 31/31、shell_router 20/20、ui_bridge 15/15、dashboard 26/26、schedule 45/45、instant 23/23 |
| `smoke_board_lock.py` / `smoke_schedule_workbench` | 退出码 0 / OK |
| `smoke_board_integrity` + `smoke_board_print` + `smoke_board_print_geometry` | 15 项 1 失败：`test_full_then_incremental_print`，报错与前三轮、与导出包基线相同（第一页不是占位页）；`smoke_board_integrity` 里调 `boardPickerOpen(…, {direct:true})` 的一项通过 |
| `tests/visual/run.py --ref <第 3 轮提交>` | 48 张图中 24 张有差异，全是桌面图，每张 0.003%，差异框全部是 (62,872)–(69,881)，即侧栏版本号的末位；两边的审计数据（字号、小目标、行内样式、溢出）逐页相同；页面脚本错误无。选板浮层不在 12 页截图里，它的外观由 `board_picker.py` 的审计覆盖 |

`board_picker.py` 第一次跑 28 / 31：`←` 后 `→` 展不开（上面「行为变化」第 3 条，是旧实现就有的问题，改了实现）；「点组标题」一条是它的连带失败；居中检查在入场动画中途量到 6px 偏移（改为等动画结束再量，属于测试写法）。改后 31 / 31。

手工与 E2E 覆盖的路径（隔离实例 full fixture，另经 HTTP 建 1 个文件夹、7 块板，真实浏览器）：题库「⋯ → 加入展示板」锚定弹出并进顶层、焦点在搜索框；「最近」、文件夹组、未归档组；↑↓；打字过滤；焦点在行上时打字进搜索框且题库不切视图；←/→ 与点组标题折叠（写进 `omrs-board-folders-collapsed`）；Ctrl+Enter 连加 → Ctrl 点击撤回（服务端对应增减）；Enter 加入并关闭；Esc 关闭且焦点回到「⋯」；点外面关闭；「已全部在板中」的行显示 ↗、点了切到 `#/board` 并载入该板；「新建板并加入」对话框带入板名与文件夹；题目弹窗里打开时进对话框、↓ 不翻页、Esc 只关浮层且焦点回到「加入展示板」；无锚点（`boardChooseAndAdd`）居中；桌面 / 手机 × 浅 / 深审计（字号 ≥12、小目标 0、只有定位用的自定义属性写在 style 上、在视口内、无横向溢出、深浅底色不同、全页没有 `.bd-picker-*`）；全程页面脚本错误 0。

**未执行：** Firefox / WebKit；CDP 模式；触屏真机（`pointer: coarse` 不自动聚焦只读了代码）；生产验证。

## 第 5 轮（v1.26.4）：页面外壳原生、板列表数据所有权

在第 4 轮完整包上继续，基线核对同第 4 轮：把累计补丁 `p7-r1-r4` 从第 4 轮完整包上反向应用得到 v1.25.4，再正向应用，树哈希与完整包相同（`383e022`）。本轮分三次会话：第一次只读代码、定方案并写了 `domain/board/` 两个文件（未存 WIP 补丁，没有交付物）；第二次开头先存 WIP 补丁，写完页面、改 `board.js`、跑通新 E2E；第三次跑全量门禁、补文档与交付。

### 行为变化

- 板 / 文件夹的 `⋯`、「＋ 新建 ▾」、「排序 ▾」换成 `ui/menu`：键盘 ↑↓ / Enter / Esc 可用、进浏览器顶层；原来是 `display:none` 切换的旧下拉，靠 document 点击关闭。
- 板行主体是按钮（Tab 可达，`aria-current` 标当前板）；文件夹折叠按钮带 `aria-expanded` 与「折叠 / 展开「名」」的读屏名。
- 状态条标题旁加「重命名」按钮（双击仍可就地改名）；就地改名 Enter 保存、Esc 取消、失焦保存，改完焦点回到按钮。
- 快捷键：`Enter` 焦点在按钮 / 链接上时交给它（原来会同时打开选中的题）；其余键位与让位条件不变（对话框、输入框、选板浮层由 `core/keys` 挡住，标记选择器打开时让位）。
- 离开展示板页的落盘从「侧栏点击的捕获阶段」改到页面卸载函数：浏览器后退 / 改地址离开也会立即保存。
- 板 `⋯` 菜单总有「移到新文件夹…」（原来一个文件夹都没有时整段「移到」都不出现，只能先去「＋ 新建」建文件夹）。
- 预览生成失败的原因存进 `board.js` 的状态、经快照显示在翻页条读数处（原来直接写进 DOM，下一次重绘就丢了），下一次同步成功后清掉。
- 外观：状态条、左栏、舞台头 token 化（`board.css`，类名 `brd-`）；分段按钮用 `aria-pressed`；桌面可点目标 ≥28、手机 40；断点从 1240 / 1180 收到 1500 / 1160 / 760。其余照旧：状态机文案、打印范围、三视图、翻页 / 缩放、拖放、菜单条目、对话框文案。

### 盘点

- `board.js` 里属于本轮的：列表 / 状态条 / 舞台栏 / 翻页条的 HTML 函数、板与文件夹 CRUD 13 个、`BOARD_DATA` / `BOARD_FOLDERS` / `BOARD_CURRENT` / `BOARD_ZOOM`、事件委托里的菜单 / 折叠 / 排序 / 视图 / 翻页 / 缩放 / 选板分支、dblclick 改名、keydown、侧栏捕获落盘、`boardBindTreeDrag`、`boardHintText`。留给第 6 轮的：板详情与打印范围、列表 / 画廊、检查器、加题对话框、按标记同步、保存 / 打印 / 设置的注入、`beforeunload`、打印窗口 message。
- 冒烟测试直接读写旧全局（`BOARD_PRINT_MODE='new'; boardRender()`、`boardReloadData`、`boardLoad`、`BOARD_DETAIL.print`），并点 `[data-board-primary]`、`[data-board-mode]`、`[data-board-seg]`、`[data-board-print]`：所以板详情与打印范围本轮不迁，新模板保留这些属性。
- `boardReloadData` 原来在没有 `#bd-list` 时直接返回；面板改成挂载时渲染后，别的页面上开选板浮层要刷新列表就会落空，守卫改成只看 `document`。
- morph 与常驻 iframe：`morph` 遇到 key 对上但位置不同的节点会 `insertBefore`，iframe 被移动一次就整份重载。骨架每层子节点固定（翻页条、警告包进 `.brd-head`），舞台、列表 / 画廊、检查器 `data-morph="skip"`；舞台显隐与 `boardPreviewMount` 在 `paint()` 末尾做。E2E 用 `contentWindow.__keep` 标记验证折叠、重绘、切视图后 iframe 没重载。
- 旧 keydown 的守卫与 `core/keys` 对照：面板激活 = 作用域；弹层 = `inDialog`；输入框 = `inInput`；选板浮层 = 浮层层；Alt / 修饰键 = 组合键名不同；只有标记选择器要另查 `domain/labels` 的 `pickerOpen()`。

### 影响文件

- 新增 `assets/app/features/board/index.js`（页面契约与控制器）、`state.js`（视图模型）、`view.js`（模板）、`board.css`（`@layer features`，在 `styles/index.css` 登记）；`assets/app/domain/board/boards.js`（板列表数据所有者）、`legacy.js`（过渡适配器）。
- `assets/app/domain/board/source.js`：板列表、文件夹、上次用的板、折叠改读 `boards.js`。
- `assets/app/legacy-bridge.js`：`installBoardBridge` 另挂 `adoptBoards` / `boardCurrentId` / `boardRemember` / `boardPreferredId` / `boardHintText` / `boardPageRepaint`，去掉 `boardPickerIsOpen`（唯一调用方 `board.js` 的 keydown 已删）。`legacy-pages.js` 删 board，`main.js` 登记 `boardPage`。
- `assets/board.js`：1261 → 831 行（见盘点）；新增 `boardPageSnapshot` / `boardSetPrintMode` / `boardMoveItemTo` / `boardRepaintPage`；`boardRender` 只写列表 / 画廊与检查器，其余交给新页面；文件头注明新位置。
- `omrs_dashboard.html`：`#panel-board` 变成空壳，`board.js?v=20260927-p7r5`，版本号。`assets/styles.css` 删 118 条已无人使用的 `.bd-*` 规则与孤立注释（按「类名在 JS / HTML 里已无引用」判定，`.bd-views` 仍被加题对话框用，只留它的一条）；`tests/ui_baseline.json` html_assign 81 → 76。
- 测试：新增 `tests/app/board-page.test.mjs`（12）、`tests/e2e/board.py`（22）；`board-regions.test.mjs` 的 INV-1 / INV-3 / 骨架三条改查 `view.js` / `state.js`（条数不变）；`board-locked.test.mjs` 注入 `boards.js`；`board_picker.py` 改读 `boardCurrentId()`。
- 版本 v1.26.4（四处）与 `AI/changelog.md`；文档 `AI/frontend/board-ui.md`（代码位置、页面各区、快捷键、布局）、`AI/board.md`（§3、§3.1、§3.3、§7）、`AI/frontend/architecture.md`（目录、过渡表）、`AI/frontend/components.md`、`AI/frontend/shell.md`、`AI/frontend/design-system.md`、`AI/optimization.md`（新增一条 `[ ]`：「添加题目」弹层 Esc 关不掉，迁移前就如此，第 6 轮换 `ui/dialog` 时修）；计划 `progress.md`（状态块、§3、§4、§5c、§8；第 1–3 轮清单压成一段）。

### 验证

| 项 | 结果 |
|---|---|
| unittest | 159 OK |
| node | 279 / 279（第 4 轮后 267；+12 `board-page`） |
| `check_ui` / `check_contrast` / `check_docs --diff <基线>` / `git diff --check` | 0 处问题（存量 handlers 127、html_assign 76、inline_style 124、color_literals 100、font_size_literals 215）/ 58 组 0 不达标 / 0 处问题、2 条既有提醒 / 无空白问题 |
| `tests/app/run_browser.py` | 34 / 34 |
| E2E | board 22/22（新）、board_picker 31/31、questions 92/92、shell_router 20/20、ui_bridge 15/15、dashboard 26/26、data 21/21、schedule 45/45、feedback 31/31、instant 23/23 |
| `smoke_board_lock.py` / `smoke_schedule_workbench` | 退出码 0（`ui_primary` 仍是「🖨 补印新增 1 题」，经 `BOARD_PRINT_MODE='new'; boardRender()` 触发新页面重绘）/ OK |
| `smoke_board_integrity` + `smoke_board_print` + `smoke_board_print_geometry` | 15 项 1 失败：`test_full_then_incremental_print`，报错与前四轮、与导出包基线相同（第一页不是占位页）；点 `[data-board-primary]` / `[data-board-mode="new"]` 的几项都通过 |
| `tests/visual/run.py --ref <第 4 轮提交>` | 48 张图中 26 张有差异：展示板 4 张是本轮的改版（桌面浅 9.4% / 深 11.7%，手机浅 21.2% / 深 26.2%，手机页高 1859 → 1931）；其余 22 张全是桌面图、每张 ≤0.003%，是侧栏版本号末位。展示板页整页审计（含仍由旧代码渲染的列表 / 检查器）：带文字字号 8 种 → 5 种、小目标 12 → 5、行内样式 7 → 7（都在检查器与旧徽章里，第 6 轮），最小字号 9.75px 仍来自检查器的旧 `.bd-badge`；溢出 0；其余 11 页审计数据逐页相同；页面脚本错误无 |

`tests/e2e/board.py` 第一次跑 11 / 12（测试写法：`/api/board` 返回 `items` 不是 `uids`），第二次 19 / 20：「添加题目」弹层按 Esc 关不掉，挡住了后面的拖放。迁移前同样关不掉（旧 keydown 在有 `.modal-overlay.open` 时直接返回，Esc 也不在 `installEscapeBridge` 里），本轮不修，记进 `AI/optimization.md`，E2E 改点它的关闭按钮；之后 22 / 22。`board-regions.test.mjs` 改查新模板后第一次 266 / 267：`view.js` 文件头注释里写了 `data-board-primary`，「全页只有一个主行动按钮」按字面数到 2，把注释改成不含该字面。

手工与 E2E 覆盖的路径（隔离实例 full fixture，另经 HTTP 建 1 个文件夹、2 块板，真实浏览器）：进页骨架与三块 skip 区、翻页条读数；点板切换（状态条、`aria-current`、预览换板）；折叠 / 展开（存本地、`aria-expanded`）；折叠、`boardRender()`、切列表再切回纸面后 iframe 仍是同一个、没重载；列表视图 ↓↓ 选行、Ctrl+↓ 换位落盘、Enter 打开题目、Esc 关、Delete 移除与 toast 撤销；双击标题就地改名（Esc 取消、Enter 保存，左栏同步）；「＋ 新建」菜单新建板；板 ⋯ 菜单条目与移到文件夹；文件夹 ⋯ 菜单（只有一个文件夹时上移 / 下移禁用）与重命名；N 弹新建对话框、对话框里按 A 只是输入；A 打开添加题目；左栏拖放把板拖进文件夹；改版面后立即切到仪表盘，服务端已保存；板 ⋯ 菜单删除当前板后落到别的板；桌面 / 手机 × 浅 / 深审计（本页原生部分字号 ≥12、可点目标桌面 ≥28 手机 40、没有 `style=`、无横向溢出、没有旧类名、深浅底色不同）；全程页面脚本错误 0。

**未执行：** Firefox / WebKit；CDP 模式；触屏真机（`@media (hover:none)` 下 `⋯` 常显只读了代码）；生产验证。

## 第 6 轮（v1.26.5）：整页原生、板详情所有权、删除 board.js

在第 5 轮完整包上继续。基线核对：第 5 轮完整包上反向应用累计补丁 `p7-r1-r5` 得到 v1.25.4 导出包，再正向应用，树哈希与完整包相同（`4394fa1`）。本轮分三次会话，每次开头都先把 WIP 补丁存进下载目录（第一次会话没存，结束时补存）：第一次写 `detail.js` / `detail-port.js` / `add.js` 与页面模板；第二次改过渡桥、删 `board.js` 与旧样式、改测试、跑通 E2E 与大部分门禁；第三次跑完剩余门禁、写文档、截图对比与交付。按 §5c 的 6 轮计划收口，没有启用第 7 轮。

### 行为变化

- 「添加题目」是 `ui/dialog`：Esc、点遮罩能关（原 `.modal-overlay` 弹层关不掉），焦点陷阱与归还；勾选跨列表 / 画廊保持；一题没勾时「加入展示板」留在对话框里（Enter 在搜索框里按下去不会空手关掉）。
- 列表行、画廊卡用 `aria-current` 标选中（原来是 `.is-selected` 类）；行上「留白」「详情」悬停 / 选中 / 键盘聚焦时出现，触屏常显。
- 检查器「跳到这道题」在列表 / 画廊视图下先切回纸面再翻页（原来不在纸面时点了没反应）。
- 停用但已打印的题在列表行上只标「停用」（与画廊、检查器同一个 `itemFlags`；原来列表行还标「已印」）。
- 列表行的熟练度从小进度条（旧 `masteryBarHtml`，带行内样式）改为「熟练 N%」文字；到期读数分档不变、改用 `data-tone` 上色。
- 纸面记录改成定义列表；「按标记同步」的单选改用 token 样式。其余照旧：检查器三段与文案、锁定保护、打印范围、三视图、拖放、快捷键、菜单、对话框文案。

### 盘点

- 旧 `board.js` 831 行拆去：状态与操作 → `detail.js`（374 行，I/O 全部注入）；缺省 I/O、单例、端口接线、窗口级监听（`beforeunload`、打印窗口 `message`、`[data-board-hint]` 悬停说明）→ `runtime.js`；列表 / 画廊 / 检查器模板 → `view.js`，视图模型 → `state.js`；加题对话框 → `add.js`；排序与纸面摘要纯函数 → `model.js`（`boardSortItems`、`boardPaperSummary`）。
- 原来为了不丢焦点而写的局部刷新（`boardRefreshLiveReadouts`、`boardSyncGapInputs`、`[data-board-ratio-value]` 手写、`boardRenderInspector`）全部删去：morph 不改聚焦中的输入框与滑杆，整页重绘即可。唯一例外是锁定确认被拒：聚焦中的控件 morph 不会改回旧值，所以 `settings.js` 的 `printRejected` / `gapRejected` 先调 deps 的 `rejected`，页面放掉检查器里的焦点再重绘。
- 依赖方向：`domain/board/boards.js` 与选板浮层要在写操作前后冲刷 / 重读 / 加题，原来经 `legacy.js` 按名调旧全局。现在 domain 声明端口 `detail-port.js`，`runtime.js` 在单例创建时 `connectBoardDetail` 接上（domain 不 import features）；`main.js` 经 `features/board/index.js` 在启动时就创建单例，所以别的页面先开选板浮层也能加题。
- 拖拽：`drag.js` 用 `data-bound` 标记防重复绑定，但 `#bd-content` 由 morph 管，模板里没有这个属性，每次重绘都被抹掉——第 5 轮起旧 `boardRender` 每次重绘都会再绑一次行拖拽（多个 drop 监听，理论上一次拖放会换位多次）。本轮改为挂载时绑一次，`index.js` 用 WeakSet 记。
- 过渡桥：旧 `board.js` 删掉后，`installBoardBridge` 挂的纯函数 / 保存 / 打印 / 设置 / 拖拽全局与 `adoptBoards` / `boardRemember` / `boardPreferredId` / `boardHintText` / `boardPageRepaint` 已无调用方，不再挂；`boardAddUids`、`qbChooseBoardForUids` 同样无人调用，删除。仍挂的逐条登记了调用方（`app.js`、`labels.js`、三份冒烟测试、两份 E2E）。
- `assets/questions.js` 的 `masteryBarHtml` 唯一调用方是旧 `board.js`，现在无人调用；该文件属于 Codex 线（执行说明 P8 删除），本轮不碰，只在 `AI/frontend/shell.md` 注明。
- 冒烟测试原来用 `window.uiConfirm = …` 替换确认框、`BOARD_PRINT_MODE='new'; boardRender()` 改打印范围、读 `BOARD_DETAIL`。前两者改为新入口 `configureBoardDetail({ confirm })` 与 `boardSetPrintMode('new')`；`BOARD_DETAIL` 由过渡桥挂成只读访问器，等待条件不用改。

### 影响文件

- 新增 `assets/app/features/board/detail.js`、`runtime.js`、`add.js`，`assets/app/domain/board/detail-port.js`；删除 `assets/board.js`、`assets/app/domain/board/legacy.js`。
- 修改 `features/board/index.js`（接 `detail.js`，动作 +12：`openItem` / `remove` / `focusGap` / `locate` / `inspectLocate` / `inherit` / `gapLive` / `gapSet` / `printLive` / `printSet` / `seg` / `resetPrinted`；点条目选中、双击打开；拖拽只绑一次）、`state.js`、`view.js`、`model.js`、`board.css`（列表 / 画廊 / 检查器 / 加题 / 同步，281 行）；`domain/board/boards.js`、`source.js`、`picker.js`（改走端口）；`legacy-bridge.js`（`installBoardBridge` 重写；其余几处注释去掉已删的 `board.js`）。
- `omrs_dashboard.html` 删 `board.js` 的 `<script>`、面板注释、版本号；`assets/styles.css` 删 139 行（`.bd-*`、`.board-add-*`、`.bdadd-*`、`.board-sync-options`、`.qb-search`；`.q-label-cell` 保留），`tests/ui_baseline.json` 去掉 `assets/board.js` 一行、`styles.css` 颜色 82 → 80、字号 193 → 184。
- 测试：`board-locked.test.mjs` 从 vm 跑旧脚本改为 `createBoardDetail` 注入替身（20 条原样迁、另加 5 条：确认被拒放焦点、打印范围与等待记录、并发重读只认最后一次、关页 sendBeacon、视图与选中）；`board-regions.test.mjs` 静态检查改查 `view.js` / `state.js` / `detail.js`（17 条不变，「继承读数统一刷新」改为「三处读数同出 `gapReadout`」）；`board-page.test.mjs` +8；`tests/e2e/board.py` 22 → 35；三份冒烟测试见上。
- 版本 v1.26.5（四处）与 `AI/changelog.md`；文档 `AI/frontend/board-ui.md`（代码位置整表、骨架与 morph、舞台、检查器、加题）、`AI/board.md`（速查、§3、§3.3、§7）、`AI/frontend/architecture.md`（目录、过渡表：删 `legacy.js` 一行、重写过渡桥一行）、`components.md`、`shell.md`（文件树与加载顺序）、`design-system.md`、`AI/optimization.md`（删「添加题目 Esc」一条；「board.js 承载多种职责」记为完成）；计划 `progress.md`。

### 验证

| 项 | 结果 |
|---|---|
| unittest | 159 OK |
| node | 292 / 292（第 5 轮后 279；`board-page` +8、`board-locked` +5） |
| `check_ui` / `check_contrast` / `check_docs --diff <基线>` / `git diff --check` | 0 处问题（存量 handlers 127、html_assign 68、inline_style 124、color_literals 98、font_size_literals 206）/ 58 组 0 不达标 / 0 处问题、2 条既有提醒（`AI/api.md` 53KB、`exec-2026-09-26-codex.md` 48KB）/ 无空白问题 |
| `tests/app/run_browser.py` | 34 / 34 |
| E2E | board 35/35、board_picker 31/31、questions 92/92、shell_router 20/20、ui_bridge 15/15、dashboard 26/26、data 21/21、schedule 45/45、feedback 31/31、instant 23/23 |
| `smoke_board_lock.py` / `smoke_schedule_workbench` | 退出码 0（`ui_primary` 是「🖨 补印新增 1 题」，经 `boardSetPrintMode('new')`）/ OK |
| `smoke_board_integrity` + `smoke_board_print` + `smoke_board_print_geometry` | 15 项 1 失败：`test_full_then_incremental_print`，与前五轮、与导出包基线同一项 |
| `tests/visual/run.py --ref <第 5 轮提交>` | 48 张图中 26 张有差异：展示板 4 张是本轮的改版（桌面浅 3.4% / 深 3.4%，手机浅 15.3% / 深 16.5%，手机页高 1931 → 2155，检查器控件按 40px 目标排）；其余 22 张全是桌面图、每张 ≤0.003%，是侧栏版本号末位。展示板整页审计：带文字字号 5 种 → 2 种、最小字号 9.75 → 12px、小目标 5 → 0、横向溢出无；「行内样式 7」前后相同，是脚本把纸面视图里 7 个 `<input>` 截图后带上的空 `style=""` 计了进去（§5b 已定位的脚本问题，执行说明 2.1 修；E2E 审计只计非空 `style`，为 0）。其余 11 页审计数据逐页相同；页面脚本错误无 |

`tests/e2e/board.py` 第一次 27 / 35：主路径与新段全过，8 项审计失败——检查器与列表第一次进审计（原来是 skip 区）：滑杆高 6px 不达可点目标（`.brd-range` 加高到 `--ctl-sm`，手机 `--ctl-lg`），列表视图最小字号 9.6px 来自标记芯片 `.lbl`（外观仍在旧 `styles.css`，progress §8 已列为 P8 随 `styles.css` 搬），审计的字号项改为不计 `.lbl`，复选框的可点区域量它的标签。之后 35 / 35。`check_ui` 第一次 3 处问题：`gap: 1px`（改为无间距）、`box-shadow` 不用 token（改 `outline`）、`detail.js` 464 行超 400（拆出 `runtime.js`，纯函数进 `model.js`，同步对话框正文进 `view.js`）。拆完后自查发现一处由拆分引入的错：预览指纹的纸面时间写成 `paperSummary()`（没传当前板，恒为空），改为 `paperSummary(st.detail)`。

看截图又改了三处（改后 `tests/e2e/board.py` 重跑 35 / 35、截图对比重拍）：检查器三段的标题是 `<header>`，吃到旧 `styles.css` 全局 `header{}` 的内边距、下边框与外边距，标题下多出一条空框——`.brd-sec__head` / `.brd-gcard__head` 显式清零（§6 早有这条坑）；旧全局 `input[type=range]` 把整个滑杆画成底色胶囊，加高到 28px 后成了一大块灰条——`.brd-range` 透明、轨道与滑块走伪元素；行上「留白」「详情」的隐藏规则特异度高于窄屏 / 触屏的常显规则，手机上不出现——隐藏规则改用 `:where()`。

手工与 E2E 覆盖的路径（隔离实例 full fixture，另经 HTTP 建 1 个文件夹、2 块板，真实浏览器）：第 5 轮的全部路径；空板列表空态与检查器提示；A 打开「添加题目」、Esc 关掉；勾 3 题、切画廊再切回勾选不丢、加入后落盘；点行选中、检查器第 N 题；行上「留白」把焦点送进检查器、输入 5 后落盘、行上回显变「留白 5 行」且焦点不丢；排序菜单反转落盘；答案分段写入并重排预览、`aria-pressed`；滑杆输入时读数 40%、焦点留在滑杆、落盘后预览按新比例；画廊 3 张卡题面由 qview 填好、点卡选中、「回到纸面」；主按钮开打印窗口 → 翻成「记录纸面」→ 写入纸面记录；再加 1 题 → 「仅新增（1）」→ 主按钮「补印新增 1 题」→ 预览按仅新增排版；列表行已印 / 新增状态标；桌面 / 手机 × 浅 / 深 × 纸面 / 列表审计；全程页面脚本错误 0。

**未执行：** Firefox / WebKit；CDP 模式；触屏真机（`@media (hover:none)` 下行上次要动作常显只读了代码）；生产验证。

## 合入

执行者：Codex · 完整模式。按 U17，P7 各轮不逐轮合入；**第 6 轮交付后 P7 全部完成，现在一次合入**。

- **补丁基线：** 导出包 `OMRS-source-sanitized-20260927T013727Z.zip`（v1.25.4）。
- **累计补丁（合入用）：** `changes-2026-09-27-p7-r1-r6.patch`，相对导出包，含第 1–6 轮；已在还原出的干净导出包上通过 `git apply --check`，应用后与第 6 轮完整包逐文件一致。
- **增量补丁（审阅、按轮拆提交用）：** `changes-2026-09-27-p7r1.patch`（第 1 轮）、`p7r2`（相对第 1 轮）、`p7r3`、`p7r4`、`p7r5`（各相对上一轮）、`p7r6`（相对第 5 轮完整包）。按顺序应用与累计补丁结果相同。第 1–5 轮的增量补丁在前几轮的交付里；本轮交付 `p7r6` 与累计补丁。

**步骤：**

1. `git status --short` 记录现状；`unset OMRS_SYSTEMD_SERVICE`。
2. `git apply --3way changes-2026-09-27-p7-r1-r6.patch`（或按顺序应用六份增量补丁，便于按轮拆提交）。

**可能冲突的地方**（本机已经做过 P6 某些页面时）：
- 版本号四处和 `AI/changelog.md` 顶部：按 progress §9，工作区版本不低于补丁版本时，在当前最大版本上加 0.0.1，并同步 changelog 标题。
- `AGENTS.md` 映射表、`legacy-bridge.js` 的 import 与 `install*Bridge` 调用列表、`omrs_dashboard.html` 的 `<script>` 列表、`tests/ui_baseline.json`：两边都保留（`ui_baseline.json` 冲突时用 `check_ui.py --update-baseline` 重算，只许下降）。
- `progress.md`：两边都保留，状态块写两条线的实际位置。
- 第 5 轮起另有：`main.js` 的页面列表、`legacy-pages.js`、`styles/index.css` 的 `@import` 列表（两边都保留）；`assets/styles.css`（P6 页面也在删旧规则：逐 hunk 合并，只删本日志列出的展示板规则，合并后跑 `check_ui` 与 `tests/e2e/board.py`）。
- 第 6 轮另有：`legacy-bridge.js` 里其它 `install*Bridge` 的注释（去掉了已删的 `board.js` 调用方）；`assets/questions.js` 本轮未改（`masteryBarHtml` 已无调用方，按执行说明 P8 随文件删除）。

**门禁与预期计数**（在 v1.25.4 上合入时）：
- unittest 159 OK；node 292 / 292；`check_ui` 0；`check_contrast` 0 不达标；`check_docs --diff HEAD` 0 处问题。
- `tests/app/run_browser.py` 34 / 34。
- `smoke_board_lock`、`smoke_board_integrity`、`smoke_board_print_geometry` 通过；`smoke_board_print` 7 项中 `test_full_then_incremental_print` 1 项失败（导出包基线上即失败，见下第 2 条）。
- 已迁页面的 E2E 计数与 progress §4 相同，其中 `tests/e2e/board_picker.py` 31 / 31、`tests/e2e/board.py` 35 / 35。
- 本机已合入 P6 页面时：node 按「本机当前数 − 61 + 133」核对（P7 删掉 4 份旧展示板测试共 61 例，`tests/app/board*.test.mjs` 等新增共 133 例；以实际 `node --test` 输出为准），unittest 不变。

**完整模式补做的步骤与验收：**

1. 运行 `python3 tests/check_docs.py --write-log-index`。验收：`AI/logs/log.md` 收录本日志。
2. 在本机跑 `python3 -m unittest tests.smoke_board_print`。验收：通过就在 progress §8 把这一项记为沙箱环境差异；仍失败就在 `AI/optimization.md` 记一条 `[ ]`（导出模板范围），progress §8 指过去。
3. 跑全量 E2E（含 `tests/e2e/board_picker.py`、`tests/e2e/board.py`）与 `tests/app/run_browser.py`。验收：计数与 progress §4 一致。
4. 按轮拆提交：`frontend-rearch P7 r1: 展示板纯函数进 features/board 与 domain/board（v1.26.0）`、`frontend-rearch P7 r2: 保存队列、打印协调、常驻预览进 features/board（v1.26.1）`、`frontend-rearch P7 r3: 拖拽排序、版面设置进 features/board（v1.26.2）`、`frontend-rearch P7 r4: 选板浮层原生进 domain/board（v1.26.3）`、`frontend-rearch P7 r5: 展示板页外壳原生、板列表归 domain/board/boards.js（v1.26.4）`、`frontend-rearch P7 r6: 展示板整页原生、板详情归 features/board/detail.js，删除 board.js（v1.26.5）`；提交哈希填进 progress 状态块。
5. 真实浏览器手工走一遍展示板主路径（进页 → 列表 / 画廊 / 纸面切换 → 添加题目 → 检查器改留白与版式 → 打印预览 → 记录纸面 → 仅补印新增），另在 Firefox 或 WebKit 至少开一次展示板页。验收：无脚本错误、各步行为与本日志「行为变化」一致。
6. 不部署，不重启生产。
