# 前端：展示板页面

> **速查**
> - 职责：展示板页的交互：常驻预览 iframe、保存队列、视图与每题留白（数据模型与打印见 `AI/board.md`）
> - 入口：`assets/board.js`、`assets/board_preview.js`、`assets/board_picker.js`
> - 不变量：保存按字段记脏并合并为一次 POST；预览消息必须带当前 `previewToken`
> - 必跑测试：`tests/test_board_ui.js`、`tests/test_board_preview.js`、`tests/test_board_locked_incremental.js`
> - 相关：`AI/frontend.md`（索引）

## 展示板页（`assets/board.js`）

侧栏「题目库」与「目录」之间的「展示板」Tab。页面是**状态条 + 三栏**：状态条 `#bd-statusbar`、
板列表 `#bd-list`、舞台 `#bd-content`、检查器 `#bd-inspector`。每个区一句话职责——状态条回答
「这叠纸现在什么状态、下一步做什么」，舞台只回答「怎么看」，检查器放所有设置。三条不变量
（舞台里没有设置控件 / 一个设置只有一个入口 / 主行动全页唯一）由 `tests/test_board_regions.js`
守着，完整说明见 `board.md` §3。

**状态条**：板名（双击重命名）、题数与科目分布、纸面状态 chips（`.bd-status-chip`，
paper / new / changed / wait 四种修饰）、一句「为什么」、打印范围分段 `[data-board-modes]`、
唯一主行动 `[data-board-primary]`，以及「下载 HTML」「↻ 重新生成」。文案全部来自纯函数
`boardStatusModel()`，见 `board.md` §4.2。打印范围放在这里而不是浮层里：它决定纸上会多出什么，
改完必须当场在舞台的纸面上看见结果。

**板列表**：`.bd-folder` 是文件夹行，`.bd-folder-body` 用 8px 缩进加一条 `border-left` 发丝竖线
兜住组内的板；空文件夹显示 `.bd-folder-empty` 虚线占位。文件夹名比板名弱一档（`--fs-sm` /
`--fg2`），因为文件夹是结构、板才是内容，视线应该优先落在板上。`⋯` 平时 `opacity:0`，
悬停 / `focus-within` 时出现，`@media(hover:none)` 下常显；它不用 `display:none`，
所以出现时不挤动板数。

**选板浮层 `.bd-picker-pop`**：与 `labels.js` 的 `.label-picker-pop` 同一套浮层语言——同样
body 挂载 + `getBoundingClientRect` 锚定 + 空间不足向上翻、同样的 `keyboard-active` 高亮和
`head / search / options / foot` 结构，只是行里多了「这个板已经有几道」的状态列。传 `anchor`
锚定弹出，不传则加 `.centered` 居中（`fadeUp` 结尾是 `transform:none`，会吃掉居中位移，所以
居中态单独走 `bdPickerIn`）。分组标题 `position:sticky` 贴顶，滚动时始终看得见当前文件夹。
提示符列固定 14px，`↵ / ✓ / ↗` 切换时行内容不位移。行为与键盘见 `board.md` §3.2。

**舞台**：`.bd-stagebar` 一行放视图分段 `[data-board-views]` 与内容操作（添加题目 / 按标记同步 /
排序 ▾ / 清空），纸面视图下 `.bd-pager` 另占一行。每个列表行是一行高的四列网格（手柄 / 序号 /
主内容 / 操作）；「留白」与「详情」平时 `opacity:0`，`:hover`、`.is-selected`、`:focus-within`
或已覆盖过留白（`.bd-gap-view.has`）时才显示，窄屏（≤760px）常显。行里的留白是只读回显
（`[data-board-gap-view]`），点它 = 选中该题并把焦点送进检查器的输入框。

**检查器**：`.bd-ins-sec[data-sec="item|layout|paper"]` 三段，sticky 在右栏。次级设置沿用
`.bd-field` / `.bd-field-row` / `.bd-checks` / `.bd-lock` / `.bd-paper` 这套字段样式。
会随别处改动而变的读数一律挂 `[data-board-live]`（`item-gap` / `gap-lines` / `col-width`），
由 `boardRefreshLiveReadouts()` 统一刷新：拖滑杆时不重建整段 DOM（否则丢焦点），
但继承板级留白的单题读数、列表行与画廊卡的只读回显都要跟着走——同一个数字不能两处不同。
「右侧留白」滑块范围 30%–55%，新建板与缺失配置的默认值为 50%；扣除 24px 间距后，
题栏与手写留白区默认等宽。已有板明确保存的比例继续按原值显示和排版。

**锁定保护纸面，不冻结题目集合：** `boardPaperLayoutChanged()` 与服务端 `update_board` 使用同一边界，增删引用、排序、未印题留白、等值留白不弹重印确认。只有真实版式变化或保留的已印题有效留白变化才调用确认；无纸面不需破坏性确认，取消不改本地设置、不入脏队列、不提交该变更。单独切锁、答案附页以及关闭切割线时的线标签不作废纸面；全局留白仅在影响已印题时触发保护。

统一 picker 的各加题入口由 `boardAddToBoard()` 直接追加，标签同步也直接追加去重；移除、清空、清理缺失/停用、拖拽/键盘/菜单排序保留纸上旧占位。安全操作不授予下一次真实版式修改的确认权限。细节见 `board.md` §4.6；行为覆盖为 `tests/test_board_locked_incremental.js`，隔离 HTTP/Chromium 覆盖为 `tests/smoke_board_lock.py`。

**布局**：`.bd-layout` 是 `200px / minmax(0,1fr) / 268px` 三列网格；≤1180px 检查器
`grid-column:1/-1` 折到底部通栏并取消 sticky，≤760px 整体纵向堆叠。整屏工作台模式
（`.is-workbench`，见 `AI/frontend/shell.md`「整屏工作台布局」）下状态条 `flex-shrink:0`，三栏各自滚动。

### 常驻预览 iframe（`assets/board_preview.js`）

展示板异步状态与打印一致性的保障范围见 `AI/optimization.md`「展示板完整性保障」。

中栏「纸面」视图是一个**常驻**的同源 `srcdoc` iframe，内容就是 `/api/export` 的展示板导出
HTML。常驻而不是每次新建：那份 HTML 内联了将近 1MB 的 KaTeX 字体，重建节点等于重新解码一次
字体。全页只留一个 iframe（`BP_FRAME`），切板换 `srcdoc`。

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
`boardRenderPager()` 只替换 `[data-board-pager]` 这一个节点——整块 `innerHTML` 会把 iframe
卷进去重载。打印与下载在请求前固定板 ID、名称和模式，并按板保留待记录的导出任务；「记录纸面」使用该任务的独立窗口 layout，下载任务则用同份 HTML 在隐藏 iframe 测量。切板与后续编辑不改变其归属和快照；此状态只保存在当前页面内存中。

**正文变更如何失效：** 预览的组合签名覆盖题目集合、顺序、停用 / 缺失状态、答案与标记显示开关和纸面时间，
**不覆盖题目正文**。正常路径没有问题——题目 Modal 保存、反馈提交都会走
`reloadData()` → `boardReloadData()` → `boardPreviewInvalidate()`，下一次同步就重新导出。
留下的缺口是「在应用外改了文件」「第三方链路没触发重载」，人工兜底是检视条上的
「↻ 重新生成」（`boardRegenPreview()`，清缓存后强制重新导出）。

续印预览的几何以本次导出初始化时的纸面快照为准：`mode:"new"` 从 `printed.print` 读取原纸的
`note_ratio / gap_lines`，常驻 iframe 收到 `omrs-board-relayout` 时也继续使用这份快照。宿主当前
设置的比例不会覆盖已打印锁定纸面；只有重新打印全部才会生成新的整板几何。

### 保存队列：按字段记脏、合并成一次 POST

行内留白与版面设置按字段记脏（`boardDirtyMerge` → `{items?:true, print?:true}`），由 `boardSavePayload()` 合并成一次 `POST /api/board/update`。`BOARD_SAVE_IN_FLIGHT` 将保存串行化；响应到达时保留发送后新改的脏字段，再继续保存，直到队列清空。请求同时含 items 与 print 时，后端使用请求后的全局值折算留白。

几何编辑去抖 500ms 保存；答案与标记显示开关立即排空保存队列，再重载预览内容。切板、导出、全量重载和重新生成都会等待待保存与在途保存。失败时保留脏字段并中止依赖动作；下次编辑或重试可继续保存。离开展示板 Tab 前尝试保存，关页时对待保存字段使用 `navigator.sendBeacon`。

### 视图与每题留白

舞台是「纸面 / 列表 / 画廊」三段（`[data-board-views]`），选择存
`localStorage['omrs-board-view']`。画廊按题目缩略展示板内题面，列表行、画廊卡和检查器的
「打开题目」都调用统一 `viewQ()`。收件箱中状态为「已录入」的条目点击后也直接打开题目详情。
换视图只换呈现：三个视图下状态条与检查器都在原处，能做的事完全一样。

检查器里的留白输入框留空 = 继承板的全局设置（`placeholder` 显示继承成几行），填数字 = 覆盖成
**绝对行数**（0–48）。`boardItemsPayload()` 原样把 `null` 传回后端，否则会被当成 0 行，
留白一保存就退化成「不留白」。`boardEffectiveGap()` 与服务端 `effective_gap_lines()` 必须同解。
`boardSetItemGap()` 是唯一写入口，列表行与画廊卡上的数字只读。

打印范围两种：**打印全部**（整板从第 1 页排）与**仅新增**（只有纸面记录存在时可选：
新题接在纸面 `cursor` 所在页的空白处续排，需要新页时用绝对页码 `pages+1`）。范围分段在状态条上，
改完纸面当场重排。「✓ 记录纸面」使用待记录导出的快照；下载任务通过 `boardMeasureLayout` 测量保留的 HTML，再 `POST /api/board/printed`。独立窗口的「已打印，记录纸面」通过 `omrs-board-printed` 回传其自身版面。常驻预览里那份导出的顶栏动作条已由
`embedded` 收起，不构成第三个入口。

打印预览必须**先同步 `window.open('', '_blank')` 拿到窗口、写入占位提示，再
`await` 导出**，最后 `preview.location.replace(blobURL)` 填入内容：浏览器只在用户手势的同步
调用栈里允许开新窗口，先 `await` 会让手势过期而被拦截（板子越大越明显，Safari 尤其严）。
`location.replace` 不换窗口对象，`BOARD_WINDOWS.get(event.source)` 的回传不受影响；导出失败
时关闭占位窗口。纸面记录可重置。快捷键：`N` 新建、`A` 添加、`P` 预览、`↑↓` 选行、`Ctrl/⌘+↑↓` 排序、
Enter 打开、Delete 移除。完整设计见 `board.md` §3 与 §4。
