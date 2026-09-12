# 2026-09-12 展示板重构：状态条 / 舞台 / 检查器三区

## 变更摘要

用户原话是「展示板的 UI 操作有点太怪了，有点难形容，我觉得是时候进行重构了」。
读 `board.js` 与 `board.md` 后拆出四条职责放错位置的问题，重构按这四条来：

| # | 问题 | 后果 |
|---|---|---|
| 1 | 能做什么随视图变：纸面有检视条、列表是行内控件、画廊两样都没有 | 视图本该只决定「怎么看」，现在连「能做什么」一起换 |
| 2 | 打印范围（全部 / 仅新增）藏在会遮住纸面的浮层里 | 它决定纸上多出什么，改完却要先关掉浮层才看得见结果 |
| 3 | 题后留白三个入口（列表数字框、检视条、拖切割线）彼此不可见 | 同一个数字三处可改、改了不同步 |
| 4 | 打印状态机没有落脚点 | 状态散在副标题、警告条、行内徽章、浮层里，没有一处说下一步做什么，所以最容易漏掉「标记为已打印」 |

页面改成**状态条 + 三栏**（`#bd-statusbar` / `#bd-list` / `#bd-content` / `#bd-inspector`），
三条不变量：舞台里不出现设置控件；一个设置只有一个入口；主行动全页唯一。

## 行为与兼容性

- **状态条**（新）：板名、纸面状态 chips、一句「为什么」、打印范围分段、唯一主行动
  `[data-board-primary]`，外加「下载 HTML」「↻ 重新生成」。文案来自新的纯函数
  `boardStatusModel(board, mode, awaiting)`。
- **等待记录纸面**（新状态）：触发打印预览或下载 HTML 后主按钮翻成「✓ 记录纸面」
  （`BOARD_AWAITING_RECORD` / `boardMarkAwaiting()`），记录成功、重置纸面记录或改打印范围才复位。
  这是问题 4 的落脚点。
- **检查器**（新）：右栏常驻三段——选中的题 / 版式 / 纸面记录，与当前视图无关。
  「版式与打印」浮层整套移除（`boardSettingsPopHtml`、`boardPopOpen/Close/Place/Refresh`、
  `BOARD_POP`、`.bd-pop*`、`[data-board-pop]`），旧检视条 `#bd-inspect` 一并移除。
- **题后留白**：写入口只剩检查器的 `[data-board-inspect-gap]`；列表行与画廊卡改成
  `[data-board-gap-view]` 只读回显（显示生效值，继承时标「（继承）」），点它 = 选中该题并把焦点
  送进检查器。新增 `boardRefreshLiveReadouts()`：板级 `gap_lines` 一改，继承它的单题读数与两处
  回显一起刷新（原型阶段这里错过一次，见「验证」）。
- **舞台栏**：只留视图分段与内容操作（添加 / 按标记同步 / 排序 / 清空），翻页条另占一行。
  缩放档状态化为 `BOARD_ZOOM`，修掉「初始状态两个缩放按钮都不高亮」。
- **嵌入式预览**：`omrs-board-view` 新增 `embedded` 字段，导出模板据此给 `<body>` 加 `.embedded`
  并收起顶栏 `#bar`。那一条带着「打印 / 导出 PDF」和「✓ 已打印，记录纸面」，嵌在舞台里就是
  第二套打印入口和第二套记录入口。独立下载 / 打印预览窗口不受影响。
- **顺手修掉一个既有缺陷**：`boardEffectiveMode()` 原来只判断 `BOARD_PRINT_MODE === 'new' &&
  boardHasPaper()`，而 `boardRecordPrinted()` 记录完会把 `BOARD_PRINT_MODE` 置成 `'new'`。
  于是「补印新增 → 记录纸面」之后新增数已归零、模式却还是 `new`，下一次导出拿 `mode:'new'` 去跑，
  纸面预览直接报「无法生成预览：没有新增题目需要打印」。现在 `boardEffectiveMode()` 直接返回
  `boardStatusModel(...).scope`，与状态条同源，状态条写「打印全部」时导出就一定按 `all` 跑。
- **布局**：`.bd-layout` 由两列改 `200px / minmax(0,1fr) / 268px`；≤1180px 检查器
  `grid-column:1/-1` 折到底部通栏并取消 sticky，≤760px 整体纵向堆叠。
- 无数据、API 或持久化格式变化。`boards.json`、`/api/board/*`、`printed` 结构、脏字段保存队列
  （`{items?, print?}` 合并成一次 POST）、预览指纹 `boardPreviewKey`（仍不含 `updated_at`）、
  `null = 继承` 的留白语义、打印预览必须先同步 `window.open` 再 `await` 导出，全部保持原样。

## 修改文件

- `assets/board.js`：新增 `boardStatusModel` / `boardAwaiting` / `boardClearAwaiting` /
  `boardMarkAwaiting` / `boardStatusbarHtml` / `boardStageBarHtml` / `boardInspectorHtml`
  （及 item / layout / paper 三段）/ `boardRenderStatus` / `boardRenderInspector` /
  `boardRefreshLiveReadouts` / `BOARD_ZOOM`；删除整套浮层；`boardRowHtml` 与
  `boardGalleryCardHtml` 的留白改只读；`boardSetItemGap`、`boardApplyPrintField`、
  `boardRender`、`boardEffectiveMode` 与事件委托同步改写；`boardStatusModel` 进 `module.exports`。
- `assets/board_preview.js`：`boardPreviewSetView()` 的 `omrs-board-view` 带 `embedded: true`。
- `assets/styles.css`：新增 `.bd-statusbar` / `.bd-status-chip` / `.bd-inspector` / `.bd-ins-*` /
  `.bd-gap-view` / `.bd-stagebar`；`.bd-layout` 改三列并加 1180px 断点；删除 `.bd-pop*`、
  `.bd-inspect*`、`.bd-head*`、`.bd-toolbar`、旧 `.bd-gap`。
- `omrs_dashboard.html`：面板骨架改为状态条 + 三栏，移除 `#bd-inspect` 与 `bd-head` 里重复的
  「＋ 新建板」「🖨 打印预览」；`board.js` 的 `?v=` 刷成 `20260912-board-regions`；侧栏版本号。
- `omrs/export_templates/board.js` / `board.css`：认 `embedded` 标志并收起 `#bar`。
- `tests/test_board_regions.js`（新增，17 项）：状态机五态 + `boardEffectiveMode` 同源 +
  三条不变量 + 浮层已移除 + 嵌入式动作条已收起。
- `tests/test_board_preview.js`：`omrs-board-view` 断言补上 `embedded: true`。
- 版本 v1.17.0 → v1.18.0：`omrs/version.py`、`omrs_dashboard.html` 侧栏、`README.md`（含版本表）、
  `AI/README.md`、`AI/changelog.md` 顶部新增一段。

## 验证

- `node tests/test_board_regions.js`：17 项通过。
- 其余 13 个前端测试 + 2 个冒烟脚本全绿；`python3 -m unittest discover -s tests -p "test_*.py"`
  87 项通过；`python3 tests/check_docs.py` 退出码 0。
- **真起服务、真开浏览器走了一遍主路径**（Chrome 131 headless，1500×950；演示库 11 题 3 板，
  B1 的纸面记录是真跑过一遍导出排版记下来的：已印 5 题 / 2 页、续排第 2 页 295px、新增 4 题未印）：

  | 步骤 | 结果 |
  |---|---|
  | 纸面 / 打印全部 | 主按钮「🖨 打印全部」，范围 = 打印全部 |
  | 切「仅新增」 | 主按钮变「🖨 补印新增 4 题」，纸面当场重排成「本次补印 2 页（第 2–3 页），第 2 页印在原纸上」 |
  | 点纸面上的题 | 检查器出现「第 6 题 先秦到秦汉6 新增 … 题后留白 10 行 ≈ 4.8 cm（继承）」 |
  | 板级留白 10 → 4 → 9 | 选中题读数跟着 10→4，列表行同步「留白 4 行（继承）」→「留白 9 行（继承）」 |
  | 检查器里填 20 | 读数「20 行 ≈ 9.5 cm」，列表行「留白 20 行」（去掉继承标），模型 `gap_lines = 20` |
  | 下载 HTML | 主按钮翻成「✓ 记录纸面」，多出 `等待记录纸面` chip |
  | 补印新增 → 记录纸面 | 纸面记录由「已印 5 题 / 2 页」推进到「已印 9 题 / 3 页、续排第 3 页 273px」，主按钮回到「🖨 打印全部」，「仅新增」自动禁用，预览按 `all` 正常重排（修复前这里会报「没有新增题目需要打印」） |
  | 1100px 断点 | 检查器折到列表下方通栏（`inspectorTop 935` vs `listTop 132`，宽度 > 800px） |
  | 三视图各测一遍不变量 | 舞台设置控件 0；题后留白写入口 0（未选中）/ 1（选中）；板级留白入口 1；主按钮 1；浮层 0 |

  全程无 `pageerror`、无 console error。
- 已知、**与本次改动无关**：`tests/smoke_board_print.py::test_full_then_incremental_print`
  在本容器失败（`first["partial"] and first["ghost"]` 为假）。该用例自己的 docstring 说明这条分支
  取决于字体，本容器缺中文衬线字体导致块高偏小、末页排满、占位页按设计被丢弃。
  在改动前的基线上跑同样失败，改动前后输出逐字一致。

## 同步过的文档

`AI/board.md`（§3 重写成区域模型 + 三条不变量、§3.4 列表行与 embedded、§4.2 状态机表 +
等待记录纸面、§4.3 记录路径）、`AI/frontend.md`（§3.4 重写）、`AI/export.md`（`omrs-board-view`
新增 `embedded`）、`AI/changelog.md`、`README.md`、`AI/README.md`。版本 v1.17.0 → v1.18.0 已在页面侧栏确认生效。
本条需在 `AI/logs/log.md` 补一行索引（`AI/logs/` 不在脱敏源码包内）。
