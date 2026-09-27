# 前端：展示板页面

> **速查**
> - 职责：展示板页的交互：页面外壳、列表 / 画廊、检查器、加题对话框、常驻预览 iframe、保存队列、视图与每题留白（数据模型与打印见 `AI/board.md`）
> - 入口：页面契约 `assets/app/features/board/index.js`；板详情 `assets/app/features/board/detail.js`（单例与真实 I/O 在 `runtime.js`）；板列表数据 `assets/app/domain/board/boards.js`
> - 不变量：保存按字段记脏并合并为一次 POST；预览消息必须带当前 `previewToken`；morph 永不挪动舞台（预览 iframe 不重载）；题后留白只有检查器能写
> - 必跑测试：`tests/app/board*.test.mjs`（含 `board-save.test.mjs`、`board-print.test.mjs`、`board-preview.test.mjs`、`board-locked.test.mjs`、`board-picker.test.mjs`、`board-page.test.mjs`）、`tests/e2e/board.py`、`tests/e2e/board_picker.py`、`tests/smoke_board_lock.py`、`tests/smoke_board_integrity.py`
> - 相关：`AI/frontend.md`（索引）

## 代码位置

展示板页是页面契约 `features/board/index.js`（v1.26.4 起；v1.26.5 起整页原生，旧经典脚本 assets/board.js 已删）：挂载时整页 `morph` 渲染骨架、状态条、左栏板列表、舞台头、列表 / 画廊与检查器，快捷键走 `core/keys.js` 页面作用域。板详情（当前板、打印范围、选中题、视图）归 `detail.js`，板列表归 `domain/board/boards.js`，两者变化都通知页面重绘。各模块：

| 模块 | 内容 |
|---|---|
| `assets/app/features/board/model.js` | 打印状态机 `boardStatusModel`、题后留白 `boardEffectiveGap` / `boardItemsPayload` / `boardGapMap`、换位 `boardMoveItems`、排序菜单 `boardSortItems`、纸面摘要 `boardPaperSummary`、保存载荷 `boardDirtyMerge` / `boardSavePayload`、锁定边界 `boardPaperLayoutChanged`、估算文案 `boardEstimateText`、内容签名 `boardItemsSignature`、时间 `boardFormatTime`、纸面几何 `boardGapCm` / `boardColumnWidth` 与常量 `CUT_LINES` / `BOARD_LINE_PX` / `BOARD_MM_PX` |
| `assets/app/features/board/detail.js` | 板详情控制器 `createBoardDetail(deps)`：状态（详情、打印范围、选中题、视图、预览错误、加载序号）与 `snapshot()` / `onDetail()`；数据（`reloadData` 只采纳最后一次、`load`、`addToBoard`）；条目（移除、换位、排序、清理、清空、按标记同步、打开）；选中、打印范围、版式写入；懒创建保存队列、打印协调、版面设置并注入回调；关页载荷 `beforeUnload`、打印窗口回传 `handleMessage`。只经 deps 碰外界 |
| `assets/app/features/board/runtime.js` | 缺省 I/O（请求沿用旧 `api()` 语义：成功返回数据、失败抛错）、单例 `boardDetail()`（第一次取时经 `connectBoardDetail` 接上 domain 端口）、窗口级监听 `installBoardWindow`（关页落盘、打印窗口回传、「加入展示板」按钮的悬停说明） |
| `assets/app/features/board/save.js` | 保存队列 `createBoardSaveQueue(deps)`：记脏、去抖、合并 POST、在途串行、失败保留、关页取载荷；`boardAdoptSaved` 合并响应与本地新编辑。`detail.js` 懒创建唯一实例 |
| `assets/app/features/board/print.js` | 打印协调 `createBoardPrint(deps)`：导出（预览窗口 / 下载）、待记录任务 `jobs`、预览窗口表 `windows`、记录 / 重置纸面、窗口回传 `handleMessage`；`fetchBoardExport`（预览共用）、`measureBoardLayout`。`detail.js` 懒创建 |
| `assets/app/features/board/preview.js` | 常驻预览 iframe（下文），导出 `boardPreview*`；模块载入时注册 window 的 message 监听 |
| `assets/app/features/board/settings.js` | 版面设置 `createBoardSettings(deps)`：版式字段写入 `applyPrintField`（规范化 `boardNormalizePrint`、答案与标记开关立即保存）、单题留白 `setItemGap`、锁定保护 `allow`（同一轮输入共用一个确认框，确认后本轮不再问，`revoke` 收回）。`detail.js` 懒创建，界面刷新钩子一律是整页重绘 |
| `assets/app/features/board/drag.js` | 拖拽排序：列表行与左栏树的 DOM 绑定 `bindBoardRowDrag` / `bindBoardTreeDrag`，落点纯函数 `boardRowDropPlan` / `boardTreeDropPlan`，键盘目标位置 `boardKeyReorderTarget` / `boardKeySelectTarget`。拖拽中按 Esc 由浏览器取消（只有 dragend、没有 drop），不会误移。页面挂载时每个节点只绑一次（`index.js` 用 WeakSet 记，因为 morph 会抹掉模板里没有的 `data-bound`） |
| `assets/app/features/board/add.js` | 「添加题目」对话框 `openBoardAdd(detail, add)`（`ui/dialog --xl`，内容节点 morph 重绘） |
| `assets/app/features/board/index.js` | 页面契约与控制器：`paint()` 把快照、板列表、预览版面组合成视图再 `morph`，之后管舞台显隐、iframe 挂载与画廊题面水合；动作 `board.*`；快捷键（下文）；点条目选中、双击打开；锁定确认被拒时放掉检查器里的焦点（`releaseFocus`）；卸载时有待保存的改动立即落盘 |
| `assets/app/features/board/state.js` | 页面单例（缩放档、就地改名）与纯函数：`statusView`、`treeView`、`boardMetaBits`、`stageView`、`estimateView`、`firstNewUid`、`contentView`、`inspectorView`、`itemFlags`、`gapReadout`、`dueView`、三个菜单的条目、加题对话框的 `addFilters` / `addRows` / `addSelectAll` |
| `assets/app/features/board/view.js` / `board.css` | 整页 `html` 模板（骨架、状态条、左栏树、舞台头、列表行、画廊卡、检查器三段、「按标记同步」正文 `syncBody`）与样式（`@layer features`，类名前缀 `brd-`，只用 token） |
| `assets/app/domain/board/boards.js` | 板列表的数据所有者：`boardList` / `boardFolders` / `boardCurrentId` / `boardFind`、`adoptBoards`、`boardRemember` / `boardLastId` / `boardPreferredId`、折叠 `boardFolderCollapsed` / `boardFolderToggle`、`boardHintText`、订阅 `onBoards`；写操作 `createBoard`、`saveBoardName` / `renameBoard`、`editBoardNote`、`duplicateBoard`、`deleteBoard`、`createFolder` / `renameFolder` / `reorderFolder` / `deleteFolder`、`moveBoard`、`applyTreeDrop`；写之前冲刷、写之后重读都经 `detail-port.js` |
| `assets/app/domain/board/detail-port.js` | 板详情端口：`boardDetailPort`（flush / reload / detail / add / open / adopt）由 `runtime.js` 经 `connectBoardDetail` 接上实现（domain 不 import features）；没接上时是安全的空实现 |
| `assets/app/domain/board/model.js` | 选板浮层的分组 `boardFolderTree`、行状态 `boardPickerRowState`、过滤 `boardPickerFilter`、最近使用 `boardPickerRecent`、`boardUniqueUids`，以及行模型 `boardPickerItems`、默认高亮 / 移动 / 折叠目标与落点、点击决策 `boardPickerPlan`、锚定位置 `boardPickerPosition`（选板被多个页面调用，所以在 domain） |
| `assets/app/domain/board/picker.js` | 选板浮层（下文）：`boardPickerOpen` / `boardPickerClose` / `boardPickerIsOpen`；模板 `picker-view.js`、样式 `picker.css`（`@layer domain`）、数据来源 `source.js`（板列表、文件夹、折叠读 `boards.js`；加题、重读、打开板、新板设为当前详情经 `detail-port.js`） |
| `assets/app/domain/board/index.js` | 上面全部，加上「加入展示板」的 `boardQuickAdd` / `boardChooseAndAdd`（直接打开 `picker.js`；旧代码经过渡桥挂回的同名全局调用） |

旧调用方（`app.js` 的 `init` 与数据刷新链、`labels.js` 标记保存后）与冒烟测试经过渡桥 `installBoardBridge` 挂回的同名全局碰板详情（`boardReloadData`、`boardLoad`、`boardApplyPrintField` 等，逐条登记在 `legacy-bridge.js`；`BOARD_DETAIL` 是只读访问器）。进度与后续见 `AI/plans/frontend-rearch/progress.md`。

## 展示板页

侧栏「题目库」与「目录」之间的「展示板」Tab。`#panel-board` 在 HTML 里是空壳，页面挂载时渲染 `.brd` 骨架：
状态条 `#bd-statusbar`（`.brd-bar`）+ 三栏 `.brd-layout`——板列表 `#bd-list`、中栏 `#bd-content`（舞台头 `.brd-head`、
舞台 `#bd-stage`、列表 / 画廊 `#bd-content-body`）、检查器 `#bd-inspector`。每个区一句话职责——状态条回答
「这叠纸现在什么状态、下一步做什么」，舞台只回答「怎么看」，检查器放所有设置。三条不变量
（舞台里没有设置控件 / 一个设置只有一个入口 / 主行动全页唯一）由 `tests/app/board-regions.test.mjs`
守着，完整说明见 `board.md` §3。

**骨架与 morph**：整页一次 `morph`，只有两类节点是 `data-morph="skip"`：舞台 `#bd-stage`（装常驻 iframe）与画廊卡的
题面挂载点（key 编码 uid，换题才换新挂载点，`qvRender` 填）。每层子节点的个数与顺序固定、都带 `data-key`，可有可无的块
（翻页条、警告）都包在 `.brd-head` 里，所以 morph 永远不会 `insertBefore` 舞台——iframe 被挪动一次就整份重载。舞台的显隐与
`boardPreviewMount` 在 `paint()` 末尾做（skip 节点的属性 morph 不管）。聚焦中的输入框与滑杆 morph 不改值，所以拖滑杆、
敲留白数字时整页重绘不丢焦点；锁定确认被拒时页面先放掉检查器里的焦点，随后的重绘把控件改回旧值。

**状态条**：板名 `<h2>`（双击或旁边的「重命名」按钮就地改名，Enter 保存、Esc 取消、失焦保存）、题数与科目分布、
纸面状态 chips（`.brd-chip[data-tone]`，paper / new / changed / wait）、一句「为什么」、打印范围分段
`[data-board-modes]`（按钮 `aria-pressed`，没有纸面或没有新增时「仅新增」禁用）、唯一主行动 `[data-board-primary]`，
以及「下载 HTML」「↻ 重新生成」。文案全部来自纯函数 `boardStatusModel()`（`state.js` 的 `statusView` 直接读它），
见 `board.md` §4.2。打印范围放在这里而不是浮层里：它决定纸上会多出什么，改完必须当场在舞台的纸面上看见结果。

**板列表**：`.brd-folder` 是文件夹行（折叠按钮 `.brd-fold` 带 `aria-expanded`，折叠状态存
`localStorage['omrs-board-folders-collapsed']`），`.brd-folder__body` 缩进加一条 `border-left` 发丝竖线兜住组内的板；
空文件夹显示虚线占位，「未归档」恒在最后、不能折叠。板行 `.brd-item` 的主体是按钮（`aria-current` 标当前板），
第二行是题数 · 已印页数（+未印）· 缺失 · 停用 · 更新时间。文件夹名比板名弱一档。板 / 文件夹的 `⋯` 与「＋ 新建 ▾」
都是 `ui/menu`（键盘可用、进顶层）；`⋯` 平时 `opacity:0`，悬停 / `focus-within` / 菜单展开时出现，`@media(hover:none)`
下常显。拖放：板拖到文件夹行 = 移进去，拖到板行 = 落在那个位置，文件夹行之间拖 = 排序；不会拖或触屏时用 `⋯` 菜单
里的「移到…」「上移 / 下移」。

**选板浮层 `.bpicker`**（`domain/board/picker.js`，v1.26.3 起原生）：根节点建一次，内容用 `morph`
渲染 `picker-view.js`；`head / search / list / foot` 四段，行是 `<button role="option">`，键盘高亮
是 `.is-active` 加搜索框的 `aria-activedescendant`（指向行的 id）。挂载走 `ui/overlay` 的
`hostGuest`（叠在题目弹窗上时进对话框，否则进 body），再 `popover="manual"` 进浏览器顶层；
传 `anchor` 时写 `--bpicker-x / --bpicker-y` 锚定（下方放不下向上翻），不传加 `.is-centered`
居中。分组标题 sticky 贴顶，文件夹组标题是按钮（点击折叠）；提示符列固定 14px，`↵ / ✓ / ↗`
切换时行内容不位移。「已全部在板中」的行用前景色退一档，不用透明度。可点目标桌面 ≥28、手机 40
（`--ctl-sm`），字号只用 `--text-sm` / `--text-xs`；手机隐藏底栏键盘提示。行为与键盘见 `board.md` §3.2。

**舞台**：舞台栏 `.brd-stagebar` 一行放视图分段（`[data-board-view]`）与内容操作（添加题目 / 按标记同步 /
排序 `ui/menu` / 清空），纸面视图下翻页条 `[data-board-pager]` 另占一行（上一页 / 页码框 / 下一页 / 跳到新增 /
预计页数读数 / 适应宽度与 100%），缺失 / 停用各一条警告带清理按钮。列表视图的行 `.brd-row` 是四列网格（手柄 / 序号 / 主内容 / 操作），选中用
`aria-current`；「留白」与「详情」平时 `opacity:0`，悬停、选中、`:focus-within` 或已覆盖过留白（`.brd-gapchip.is-own`）
时才显示，窄屏（≤760px）与触屏常显。行里的留白是只读回显（`[data-board-gap-view]`），点它 = 选中该题并把焦点送进
检查器的 `#bd-ins-gap`。画廊卡 `.brd-gcard` 与题库画廊同一套 qview 缩略，「回到纸面」（`board.locate`）切回纸面视图再翻到这道题。
纸面状态标 `.brd-flag`（缺失 / 停用 / 已印 p.N / 新增 / 已改动）在列表行、画廊卡、检查器三处由 `itemFlags` 一处算。

**快捷键**（`core/keys.js`，作用域 `board`；对话框、输入框、选板浮层打开时由 core/keys 挡住，标记选择器打开时让位）：
`N` 新建、`A` 添加题目、`P` 打印预览；纸面视图 `← / →` 翻页；`↑ / ↓` 选行（纸面视图同时翻到那道题）、
`Ctrl/⌘ + ↑ / ↓` 换位落盘；`Enter` 打开选中的题（焦点在按钮上时交给按钮）；`Delete` / `Backspace` 移除。

**添加题目**（`add.js`，`A` 或舞台栏按钮）：`ui/dialog --xl`，Esc / 点遮罩关闭、焦点陷阱与归还由 `ui/overlay` 负责。
筛选（搜索、科目、分类、知识点、状态、到期、排序、标记芯片）与题库共用 `filterItems()`；已在板里的题标灰、不可勾；勾选集合是
唯一真相，列表 / 画廊（存 `localStorage['omrs-board-add-view']`）来回切不丢；一题没勾时「加入展示板」留在对话框里。
「按标记同步」是 `ui/dialog` 单选（`id="bd-sync-N"`），正文由 `view.js` 的 `syncBody` 画。

**检查器**：`.brd-sec[data-sec="item|layout|paper"]` 三段，sticky 在右栏；字段是 `.brd-field` / `.brd-checks` /
`.brd-lock` / `.brd-paper`（定义列表）。控件保留测试钩子：`[data-board-inspect-gap]`（题后留白，全页唯一）、
`[data-board-print="note_ratio|gap_lines|show_labels|show_meta|cut_label|locked"]`、分段 `[data-board-seg="answers|cut_line"]`
（按钮 `data-value`，`aria-pressed` 标当前档）。滑杆与数字框 `input` 时即写（锁定时只在 `change` 写，一轮输入一个确认框），
复选框 `change` 时写。会随别处改动而变的读数挂 `[data-board-live]`（`item-gap` / `gap-lines` / `col-width`）；
留白读数、列表行与画廊卡的只读回显都出自 `state.js` 的 `gapReadout`，改了板级留白整页重绘一起变——同一个数字不能两处不同。
「跳到这道题」在列表 / 画廊视图下先切回纸面再翻页。
「右侧留白」滑块范围 30%–55%，新建板与缺失配置的默认值为 50%；扣除 24px 间距后，
题栏与手写留白区默认等宽。已有板明确保存的比例继续按原值显示和排版。

**锁定保护纸面，不冻结题目集合：** `boardPaperLayoutChanged()` 与服务端 `update_board` 使用同一边界，增删引用、排序、未印题留白、等值留白不弹重印确认。只有真实版式变化或保留的已印题有效留白变化才调用确认；无纸面不需破坏性确认，取消不改本地设置、不入脏队列、不提交该变更。单独切锁、答案附页以及关闭切割线时的线标签不作废纸面；全局留白仅在影响已印题时触发保护。

统一 picker 的各加题入口由 `detail.js` 的 `addToBoard()` 直接追加，标签同步也直接追加去重；移除、清空、清理缺失/停用、拖拽/键盘/菜单排序保留纸上旧占位。安全操作不授予下一次真实版式修改的确认权限。细节见 `board.md` §4.6；行为覆盖为 `tests/app/board-locked.test.mjs`，隔离 HTTP/Chromium 覆盖为 `tests/smoke_board_lock.py`。

**布局**：`.brd-layout` 是 `200px / minmax(0,1fr) / 268px` 三列网格（≤1500px 收成 188 / 248）；≤1160px 检查器
折到底部通栏并取消 sticky，≤760px 整体纵向堆叠、可点目标 40px。整屏工作台模式（`.is-workbench`，≥1161px，见
`AI/frontend/shell.md`「整屏工作台布局」）下状态条不动、三栏各自滚动，舞台吃满中栏剩余高度。

### 常驻预览 iframe（`assets/app/features/board/preview.js`）

展示板异步状态与打印一致性的保障范围见 `AI/optimization.md`「展示板完整性保障」。

中栏「纸面」视图是一个**常驻**的同源 `srcdoc` iframe，内容就是 `/api/export` 的展示板导出
HTML。常驻而不是每次新建：那份 HTML 内联了将近 1MB 的 KaTeX 字体，重建节点等于重新解码一次
字体。全页只留一个 iframe（模块内的 `BP_FRAME`，外部经 `boardPreviewFrame()` 读），切板换 `srcdoc`。

刷新分三档，内容变化和切板需要重新导出，几何调整不请求导出接口：

| 档 | 触发 | 动作 | 去抖 |
|---|---|---|---|
| 几何 | 留白比例 / 题间留白 / 切割线 | `postMessage` `omrs-board-relayout` | 120ms |
| 内容 | 增删题 / 排序 / 换模式 / 答案与标记开关 | 保存完成后重新拉 `/api/export` | 等待保存 |
| 切板 | 选了别的板 | 立即拉导出 | — |

导出指纹是 `板 + 模式 + 题目签名（含答案与标记开关）+ 纸面时间`（`boardPreviewKey`），**刻意不含
`board.updated_at`**：拖一次版面滑块就会 bump 它，而版面改动本该走 relayout，把它算进指纹
等于每拖一下都重新请求近 1MB 的导出。HTML 缓存只留最近一份（`BP_HTML_CACHE`），
不把几份 1MB 的字符串攒在内存里。

不在前台就不排版：切到别的 Tab、或预览滚出视口（`IntersectionObserver`）时几何改动只记不发，
回来再 `boardPreviewFlushPending()` 补一次。切板时进行中的导出请求会被 `AbortController`
取消，晚到的结果按文档代次 `previewToken` 丢弃。宿主为每份 srcdoc 注入独立 token，消息同时校验来源窗口、token、板 ID 和模式；模板也拒绝旧 token 的宿主消息。内嵌 HTML 从加载开始就带 `embedded`，就绪后重放单页和缩放状态。

页数不再单独跑一遍排版估算：翻页条直接读预览已经排好的 `layout`（`page_numbers` / `pages`），
预览回传版面时 `detail.js` 通知页面整页 morph（舞台是 skip 节点，不会被卷进去）；
生成失败的原因存在 `detail.js` 的状态里，经快照显示在读数处，下一次同步成功后清掉。打印与下载在请求前固定板 ID、名称和模式，并按板保留待记录的导出任务；「记录纸面」使用该任务的独立窗口 layout，下载任务则用同份 HTML 在隐藏 iframe 测量。切板与后续编辑不改变其归属和快照；此状态只保存在当前页面内存中。

**正文变更如何失效：** 预览的组合签名覆盖题目集合、顺序、停用 / 缺失状态、答案与标记显示开关和纸面时间，
**不覆盖题目正文**。正常路径没有问题——题目 Modal 保存、反馈提交都会走
`reloadData()` → `boardReloadData()`（过渡桥 → `detail.js` 的 `reloadData`）→ `boardPreviewInvalidate()`，下一次同步就重新导出。
留下的缺口是「在应用外改了文件」「第三方链路没触发重载」，人工兜底是状态条上的
「↻ 重新生成」（`detail.js` 的 `regen()`，清缓存后强制重新导出）。

续印预览的几何以本次导出初始化时的纸面快照为准：`mode:"new"` 从 `printed.print` 读取原纸的
`note_ratio / gap_lines`，常驻 iframe 收到 `omrs-board-relayout` 时也继续使用这份快照。宿主当前
设置的比例不会覆盖已打印锁定纸面；只有重新打印全部才会生成新的整板几何。

### 保存队列：按字段记脏、合并成一次 POST

行内留白与版面设置按字段记脏（`boardDirtyMerge` → `{items?:true, print?:true}`），由 `boardSavePayload()` 合并成一次 `POST /api/board/update`。队列（`save.js`）把在途保存串行化；响应到达时保留发送后新改的脏字段，再继续保存，直到队列清空。请求同时含 items 与 print 时，后端使用请求后的全局值折算留白。

几何编辑去抖 500ms 保存；答案与标记显示开关立即排空保存队列，再重载预览内容。切板、导出、全量重载和重新生成都会等待待保存与在途保存。失败时保留脏字段并中止依赖动作；下次编辑或重试可继续保存。离开展示板页时（页面卸载函数，侧栏点击与浏览器后退都算）有待保存的字段就立即保存，关页时对待保存字段使用 `navigator.sendBeacon`。

### 视图与每题留白

舞台是「纸面 / 列表 / 画廊」三段（`[data-board-view]`），选择存
`localStorage['omrs-board-view']`。画廊按题目缩略展示板内题面，列表行、画廊卡和检查器的
「打开题目」都调用统一 `viewQ()`。收件箱中状态为「已录入」的条目点击后也直接打开题目详情。
换视图只换呈现：三个视图下状态条与检查器都在原处，能做的事完全一样。

检查器里的留白输入框留空 = 继承板的全局设置（`placeholder` 显示继承成几行），填数字 = 覆盖成
**绝对行数**（0–48）。`boardItemsPayload()` 原样把 `null` 传回后端，否则会被当成 0 行，
留白一保存就退化成「不留白」。`boardEffectiveGap()` 与服务端 `effective_gap_lines()` 必须同解。
`detail.js` 的 `setItemGap()`（转调 `settings.js` 的 `setItemGap`）是唯一写入口，列表行与画廊卡上的数字只读。

打印范围两种：**打印全部**（整板从第 1 页排）与**仅新增**（只有纸面记录存在时可选：
新题接在纸面 `cursor` 所在页的空白处续排，需要新页时用绝对页码 `pages+1`）。范围分段在状态条上，
改完纸面当场重排。「✓ 记录纸面」使用待记录导出的快照；下载任务通过 `measureBoardLayout` 测量保留的 HTML，再 `POST /api/board/printed`。独立窗口的「已打印，记录纸面」通过 `omrs-board-printed` 回传其自身版面。常驻预览里那份导出的顶栏动作条已由
`embedded` 收起，不构成第三个入口。

打印预览必须**先同步 `window.open('', '_blank')` 拿到窗口、写入占位提示，再
`await` 导出**，最后 `preview.location.replace(blobURL)` 填入内容：浏览器只在用户手势的同步
调用栈里允许开新窗口，先 `await` 会让手势过期而被拦截（板子越大越明显，Safari 尤其严）。
`location.replace` 不换窗口对象，`boardPrint().windows.get(event.source)` 的回传不受影响；导出失败
时关闭占位窗口。纸面记录可重置。快捷键：`N` 新建、`A` 添加、`P` 预览、`↑↓` 选行、`Ctrl/⌘+↑↓` 排序、
Enter 打开、Delete 移除。完整设计见 `board.md` §3 与 §4。
