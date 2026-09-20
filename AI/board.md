# 展示板（错题集打印）

> 对应源文件：`omrs/boards.py`、`omrs/exporting.py`（展示板导出段）、
> `omrs/export_templates/board.css`、`omrs/export_templates/board.js`、`assets/board.js`、
> `assets/board_preview.js`、`assets/styles.css`（`.bd-*`）、`tests/test_boards.py`、
> `tests/test_board_export.py`、`tests/test_board_ui.js`、`tests/test_board_preview.js`、
> `tests/smoke_board_print.py`、`tests/test_board_locked_incremental.py`、
> `tests/test_board_locked_incremental.js`、`tests/smoke_board_lock.py`。

## 1. 定位与边界

展示板是可持久化的题目引用集合，服务于「左题右空」的纸面复习：

- 多个展示板可并存；板名、备注只在系统内使用，纸面标题固定为「错题集」；
- 板里保存题目的 `question_id` 与当前 `uid`，不是题目副本，重印即读取最新 Markdown；
- 可以添加、移除、清空、拖拽/菜单排序、复制和删除；
- 板不进入 Ledger，不参与熟练度、SM-2、统计或推荐；
- 停用题保留在板中并提示，但导出跳过；删除或无法解析的题显示为「缺失」，需用户清理；
- **纸面记录**（§4）让「加了一道题只补印这一道」成为可能：新题接在原纸空白处，
  已打印区域留白，把原纸放回打印机即可。

展示板与收件箱一样是呈现 / 暂存层数据，不是题目与复习事实链。

错题集页面左右均使用 10mm 普通页边距，不额外预留装订区，也不绘制装订导引线或打孔圆圈。

## 2. 数据文件 `boards.json`

路径：`错题/.omrs/boards.json`，当前 `version: 3`。写入先把已有文件滚动为 `.bak.1/2/3`，再通过临时文件、
`fsync` 和 `os.replace` 原子替换（`save_boards`）。字段全表见 `AI/data.md` §14，这里只记与纸面相关的要点。

```json
{
  "version": 3,
  "folders": [{"id": "BF-20260907-a1b2c3", "name": "高三上·期中", "order": 0,
               "created_at": "2026-09-07T10:00:00+00:00", "updated_at": "2026-09-07T10:00:00+00:00"}],
  "boards": [{
    "id": "BD-20260904-a1b2c3",
    "name": "考前速览·三角函数",
    "note": "月考前使用",
    "folder_id": "BF-20260907-a1b2c3",
    "order": 0,
    "created_at": "2026-09-04T12:00:00+00:00",
    "updated_at": "2026-09-04T12:30:00+00:00",
    "source_labels": ["考前必看"],
    "print": {
      "note_ratio": 0.50,
      "gap_lines": 2,
      "answers": "none",
      "show_labels": true,
      "show_meta": true,
      "cut_line": "dash",
      "cut_label": false,
      "locked": false
    },
    "printed": {
      "at": "2026-09-04T12:40:00+00:00",
      "pages": 3,
      "cursor": {"page": 3, "y": 493.56},
      "print": {"note_ratio": 0.50, "gap_lines": 2, "...": "打印时的版面"},
      "items": [{"question_id": "OP-000123", "uid": "三角函数1", "hash": "9f2c…",
                 "segments": [{"page": 1, "top": 0, "height": 125.7}]}],
      "answer_pages": []
    },
    "items": [{
      "question_id": "OP-000123",
      "uid": "三角函数1",
      "added_at": "2026-09-04T12:10:00+00:00",
      "gap_lines": null,
      "pin": false
    }]
  }]
}
```

字段规则（`normalize_print` / `_normalize_item` / `_normalize_printed`）：

- `print.note_ratio` 钳到 `0.30–0.55`，全局 `gap_lines` `0–24`，
  `answers ∈ {none,append}`，`cut_line ∈ {none,dash,solid}`（默认 `dash`）、`cut_label` 与 `locked` 均为布尔；
  未知键忽略，缺失键回默认。展示板不生成打孔标记。
- `items[].gap_lines` 是**这道题之后留白的绝对行数**（0–48，每行 18px）；`null` = 继承板的
  全局 `print.gap_lines`。v2 的 `extra_gap_lines`（「在全局之上再加几行」）读取时按
  `全局 + 额外` 折算成等值的绝对行数，**迁移前后纸面像素完全一致**，折算后该字段恒为 0，
  因此重复归一化是空操作。详见 `AI/data.md` §14.2。
- `printed.pages == 0` 表示没有纸面记录；旧文件里的 `last_printed_page` 字段直接忽略。
- 整体覆盖 `items` 时（`update_board(items=…)`）会保留同一题原有的 `added_at`。
- 同一请求同时给 `items` 与 `print` 时，`print` 先生效，v2 折算用的是**本次请求之后**的全局留白。

覆盖旧纸面记录（`record_printed` / `reset_printed`）之前，会把被替换记录的摘要追加进
`错题/.omrs/boards_printed_history.jsonl`（只增不改，见 `AI/data.md` §14.4）。
摘要没有逐题 `items/segments/hash`，不能直接恢复完整纸面；完整记录需从 `boards.json` 或其备份核验。
**这份历史目前没有 UI，也没有 HTTP 端点。**

### 题目引用解析

`_Resolver` 一次性读取 `question_projection` 与 `mastery_data.csv`，每个 item 解析出
`subject / category / difficulty / mastery / due_date / labels / suspended / missing /
file_path`，以及纸面相关的 `printed`（已在纸上）、`printed_page`、`changed`（题目正文在
打印后改过）。优先按 `question_id` 命中，题目迁移或改名后仍能对上并更新为当前 UID。

`get_board` / `list_boards` 另附 `printed_summary`：`{at, pages, count, new_count,
changed_count, cursor, answer_pages, print}`。

## 3. 展示板页面（`assets/board.js`）

侧栏「题目库」与「目录」之间的「展示板」Tab。页面分成**状态条 + 三栏**，每个区一句话职责，互不重叠：

```text
┌─ 状态条 #bd-statusbar ─────────────────────────────────────┐
│ 板名 · 题数   [状态 chips]      为什么  [打印范围] [主行动]  │
├────────┬────────────────────────────┬─────────────────────┤
│ 板列表 │ 舞台 #bd-content            │ 检查器 #bd-inspector │
│        │ [纸面|列表|画廊] 内容操作    │ 选中的题             │
│        │ 翻页条（纸面视图）           │ 版式                 │
│        │      只换呈现，不换能力       │ 纸面记录             │
└────────┴────────────────────────────┴─────────────────────┘
```

1. **状态条**（`boardStatusbarHtml()`）：板名（双击重命名）、题数 / 科目分布 / 备注、纸面状态
   chips、一句「为什么」、打印范围分段（`[data-board-modes]`）、**全页唯一的主行动按钮**
   （`[data-board-primary]`，文案由 §4.2 的状态机决定），以及「下载 HTML」「↻ 重新生成」两个次要动作。
2. **板列表**（sticky）：文件夹 → 板的两级树，见 §3.1。板行显示板名、题数、已印页数 / 新增数、
   更新时间；`⋯` 菜单：重命名、备注、复制、导出 HTML、移到某个文件夹、删除。空态给
   「新建第一个展示板」。
3. **舞台**：舞台栏是视图分段 + 内容操作（添加题目 / 按标记同步 / 排序 ▾ / 清空），纸面视图下
   翻页条另占一行；缺失 / 停用题的黄红提示条排在下方。排序即持久化
   （`POST /api/board/update {items}`）。三个视图见 §3.4。
4. **检查器**（`boardInspectorHtml()`，sticky）：三段固定在这里，与当前是哪个视图无关——
   「选中的题」（题号 / UID / 徽章 / 元信息 / **题后留白** / 跳到这道题 / 打开题目 / 从板中移除）、
   「版式」（右侧留白 30–55%、题间留白、答案、题头显示、切割线、锁定版式，即改即存，去抖 500ms）、
   「纸面记录」（已印题数 / 页数 / 时间、续排位置、已改动计数、清空纸面记录）。
   `locked` 保护纸面，不冻结引用集合。增删、重复追加、清空引用、排序与未打印题留白不要求重印确认，均保留纸面记录；真正影响已印区域的版式/留白变更才确认，取消时不提交该变更。具体边界见 §4.6。

三条不变量由 `tests/test_board_regions.js` 守着，破坏了「能做什么随视图变」的老毛病就会回来：

- **舞台只呈现**：舞台渲染出的 HTML 里不出现任何设置控件（滑杆、设置类数字框、`[data-board-print]`、
  打印范围分段）。翻页条里的页码框是导航，靠 `data-board-page-input` 与设置区分。
- **一个设置只有一个入口**：题后留白只有检查器能写（`[data-board-inspect-gap]` 全页仅一个），
  列表行与画廊卡上的留白是只读回显（`[data-board-gap-view]`，点一下 = 选中并把焦点送进检查器）；
  板级 `gap_lines` 同样只渲染一次。板级留白一改，继承它的单题读数与两处只读回显由
  `boardRefreshLiveReadouts()` 一起刷新。
- **状态与行动同处**：`[data-board-primary]` 全页唯一，文案直接来自 `boardStatusModel()`。

行内「留白」与「详情」默认透明，行悬停 / 选中 / 键盘聚焦时才显示；已覆盖过留白的行常显。
`.bd-*` 样式的间距、圆角、字号全部走密度变量（`--pad/--row/--ctl/--fs*`），紧凑档单行约 28px，
舒适档约 49px；1180px 以下检查器折到底部通栏，760px 以下三栏纵向堆叠且行内控件常显。

### 3.1 板列表：文件夹 → 板

左栏是两级树，由 `boardListHtml()` 渲染，`boardFolderTree(boards, folders)` 负责分组：文件夹按
`order` 排列，未归档恒在最后，空文件夹保留并显示虚线占位「把板拖进来」。文件夹行给折叠箭头、
板数，以及组内「还没印上纸」的题数汇总 `+N`（各板 `printed_summary.new_count` 相加），
`⋯` 菜单提供重命名 / 在此新建板 / 上移 / 下移 / 删除文件夹。删除文件夹默认把板移到未归档，
对话框里可以改成连板一起删。

折叠状态存 `localStorage['omrs-board-folders-collapsed']`，不进 `boards.json`——它是 UI 状态，
不是数据。拖拽（`boardBindTreeDrag()`）：板拖到文件夹行 = 移动，板拖到板行 = 落在那个位置，
文件夹行之间拖 = 文件夹排序；不便拖拽时用板 `⋯` 菜单的「移到」。

### 3.2 加入展示板：统一选板浮层

八处入口（题库行内 `⋯`、题库批量条、题目 Modal、反馈判定面板、即时练习、数据复盘顽固题表、
收件箱、录入成功提示）统一走 `boardPickerOpen(uids, {anchor, exclude, moveFrom, direct, onDone})`。
`boardQuickAdd` / `boardChooseAndAdd` 保留为薄封装，调用点函数名不变。

浮层结构：标题（带本次题数）+ 搜索框 + 分组列表 + 「＋ 新建板并加入…」。传了 `anchor` 就锚定在
触发元素下方弹出，没有则同一份 DOM 居中显示（toast 按钮、快捷键走这条）。**单击板行即完成**，
没有「确定」按钮；`⌘/Ctrl` + 点击则加入但不关闭，可连加多个板，再点一次撤回本次加进去的题。

行状态由 `boardPickerRowState(board, uids)` 算出，靠 `/api/boards` 返回的每板 `uids` 本地判断：

| 状态 | 显示 | 点击行为 |
|---|---|---|
| 全新 | `12 题 · 已印 3 页` | 加入全部 |
| 部分已在 | 追加 `已有 1/3` | 只加尚未在板里的那些 |
| 全部已在 | 灰显 + `↗` + `已全部在板中` | 不重复加入，改为打开该板 |

搜索匹配板名与文件夹名，过滤态展平分组、每行副标题显示所属文件夹（`boardPickerFilter`）；
搜不到时底部按钮变成「＋ 新建《输入的名字》并加入」。板多于 6 个时列表顶部给「最近」
（`boardPickerRecent`：上次用的板 + 最近更新，最多 2 条）；板少时不显示，避免同一个板出现两次。

速度不倒退：键盘「打开浮层 → `Enter`」两键进上次的板；`Shift` + 点「加入展示板」跳过浮层直接加入，
toast 写明「已直接加入《X》」并给「撤销」「换个板…」；按钮 `title` 在悬停 / 聚焦时现算，写出当前
默认目标（`加入展示板（上次：X）`）。原则是**默认给选择，加速留给显式修饰键**。

键盘：`↑/↓` 移动高亮（默认跳过「全部已在板中」的行，否则 `Enter` 是空动作）、`Enter` 加入、
`←/→` 折叠 / 展开所在文件夹、`Esc` 关闭。焦点始终留在搜索框（combobox + `aria-activedescendant`），
触屏（`pointer: coarse`）不自动聚焦，免得软键盘挡住列表。`Esc` 在 capture 阶段处理并
`stopPropagation`，因此浮层开着时按 `Esc` 关的是浮层，底层 Modal 不会被顺手关掉。

### 3.3 添加题目与页面键盘

「添加题目」对话框复用 `filterItems()`（搜索 / 科目 / 分类 / 知识点 / 状态 / 到期 / 标记 chips），
已在板中的题目灰显跳过，可「全选筛选结果」。「按标记同步」是显式追加并去重，不会因题目后来
打标而自动改变板。

键盘：`N` 新建、`A` 添加题目、`P` 打印预览、`↑/↓` 选行、`Ctrl/⌘+↑/↓` 移动行、`Enter` 打开、
`Delete` 移除；所有对话框用 `uiDialog/uiPrompt/uiConfirm`（core.js），不再用 `prompt()`。

### 3.4 中栏三视图：纸面 / 列表 / 画廊

分段按钮 `[data-board-views]`，选择存 `localStorage['omrs-board-view']`（UI 状态，不进
`boards.json`）。

**纸面（默认）** 是一个常驻的同源 `srcdoc` iframe，内容就是 `/api/export` 的导出 HTML——
所见即所打印，没有第二套估算。上方是翻页条：`←/→` 翻页、页码直填、「⚑ 跳到新增」定位到第一道
还没印上纸的题、「适应宽度 / 100%」缩放，以及从真实版面读出的页数与告警摘要。默认**一次一面**。
点纸面上的题会回传 `omrs-board-select`，宿主据此同步选中态并在检查器里显示它的设置。
宿主在 `omrs-board-view` 里带 `embedded: true`，导出模板据此收起自带的顶栏动作条
（「打印 / 导出 PDF」「✓ 已打印，记录纸面」）——那一条是给独立下载的 HTML 用的，
嵌在舞台里就成了第二套打印与记录入口。
iframe 的生命周期、三档刷新与指纹缓存见 `AI/frontend.md` §3.4。

**列表** 每行一行高：拖拽手柄 + 序号 + UID + 徽章（已印 p.N / 新增 / 已改动 / 停用 / 缺失）+
标记芯片（点击开 LabelPicker）+ 元信息 + 留白只读回显 + 详情 + ✕。留白显示的是生效值
（继承时标「（继承）」），改它点一下跳到检查器。

**画廊**显示板内题目缩略详情，点击「详情」或双击题目均打开统一题目详情视图；纸面视图和列表视图也提供同一详情入口。

## 4. 打印系统：全部 / 仅新增 / 纸面记录

### 4.1 心智模型

纸是逐次累积的：第一次「打印全部」得到 N 张纸；之后加题，只想补印新题——而且新题要
**印在最后那张纸剩下的空白处**，用不着重新打印整叠。系统因此需要知道「纸上现在有什么」：

```text
printed（纸面记录）= 已打印题目集合 + 每题所在页 / 位置 + 续排 cursor{page,y} + 当时的版面几何
```

- **打印全部**（`mode:"all"`）：整板从第 1 页重新排版；确认已打印后用这次版面**替换**纸面记录。
- **仅打印新增**（`mode:"new"`）：只排「不在纸面记录里」的题目。浏览器模板先在 `cursor.page`
  这一页顶部放一个高度 = `cursor.y` 的占位块（屏幕上显示斜纹「已打印区域」，打印时完全透明，
  页眉页脚也隐藏），新题从占位块下方继续排；这一页放不下时**跳到 `pages + 1`** 新页（绝对页码，
  跳过中间的答案页）。占位页若没放进任何新题则不输出。确认后把新题**追加**进纸面记录并推进 cursor。
- 纸面几何（`note_ratio / gap_lines`）在仅新增模式下**沿用纸面记录中的打印快照**，与原纸对齐；
  当前板的 `print.note_ratio` 只影响下一次「打印全部」，不能覆盖已经打印的锁定纸面比例。
  `answers / show_labels / show_meta` 跟随当前设置。新题的答案附页排在新题之后的
  新页上（标题「答案（本次新增）」），不会去动已打印的答案页。
- 题号接着纸面继续（`index_start = printed.count + 1`）。

### 4.2 打印状态机与页数估算

纸面状态与「下一步做什么」只在状态条上出现一次，由纯函数
`boardStatusModel(board, mode, awaiting)` 算出（`assets/board.js`，已导出，见
`tests/test_board_regions.js`）。它返回 `{chips, scope, action, why}`：

| 纸面记录 | 新增题 | 打印范围 | 状态 chips | 主行动 | 一句「为什么」 |
|---|---|---|---|---|---|
| 无 | — | 全部 | `还没打印过` `N 题` | 🖨 打印全部 | 第一次打印会用掉新的一叠纸 |
| 有 | 0 | 全部 | `已印 N 题 / P 页` | 🖨 打印全部 | 没有新增题需补印；想按当前顺序重排可主动打印全部 |
| 有 | M>0 | 全部 | + `新增 M 题未印` | 🖨 打印全部 | 会重排整叠纸，写过的作废 |
| 有 | M>0 | 仅新增 | 同上 | 🖨 补印新增 M 题 | 接在第 X 页的空白处 |
| 任意 | 任意 | 任意 | + `等待记录纸面` | ✓ 记录纸面 | 打完了点这里 |

`changed_count > 0` 时在任何状态下追加一枚 `K 题已改动` chip。打印范围为 `new` 但没有纸面记录
或没有新增题时自动落回 `all`，分段按钮同时禁用。

**等待记录纸面**是打印链路的落脚点：触发过打印预览或下载 HTML 之后
（`boardMarkAwaiting(mode)`）主按钮翻成「✓ 记录纸面」，直到记录成功、重置纸面记录或改了打印范围
才复位。它取代了原先埋在浮层里的「标记为已打印」——那时没有任何地方提示「你刚打完，该记录了」。

页数不再单独跑一遍排版：**常驻预览 iframe 就是那一遍**。翻页条的页数、页码范围与告警数
直接读它回传的 `layout`（`boardEstimateText()` 只负责拼文案），几何改动走 `relayout`
在 iframe 内重排、全程零请求。展示板 Tab 不在前台或预览滚出视口时不排版，回来再补一次。

隐藏 iframe 测量（`boardMeasureLayout()`）只剩一条回退路径：预览不可用（列表视图、导出报错）
时「标记为已打印」仍要拿到版面。打印预览窗口的 `omrs-board-layout` 回传不再当估算用，
只保留「已打印，记录纸面」这条链路。

### 4.3 记录纸面（「标记为已打印」）

版面由浏览器实测，所以记录也来自浏览器：

1. 导出模板排版完成后写 `window.OMRS_LAYOUT`，并向 `opener` / `parent` `postMessage`
   `{type:"omrs-board-layout", boardId, mode, layout}`；顶栏「✓ 已打印，记录纸面」发送
   `omrs-board-printed`。
2. 主程序两条路径都能记录：① 打印预览窗口点「已打印」→ 主页面弹确认 → 记录；② 状态条的
   「✓ 记录纸面」→ 优先复用常驻预览已经测好的 layout（板 id 与模式都对得上才采纳），
   预览不可用时才用 `boardMeasureLayout()` 把同一份导出 HTML 放进隐藏 iframe（同一浏览器、
   同一字体，版面一致）→ 拿到 layout → 记录。下载后离线打印的情况走 ②。
   常驻预览里那份导出的顶栏动作条已被 `embedded` 收起，不构成第三条路径。
3. `POST /api/board/printed {id, mode, layout}`（§5）由服务端合并；`mode:"all"` 优先保存
   `layout.print`（模板实测时的 `note_ratio / gap_lines` 等几何快照），以保证记录的设置就是实际
   打出来的设置；旧版客户端未提供该字段时才回退到板当前 `print`。`mode:"new"` 追加题目时继续
   保留原 `printed.print`，不会用本次增量布局里的设置覆盖原纸几何。`hash` 取题目正文指纹，
   之后题目改了会在行内显示「已改动」并在摘要里计数（纸面仍是旧版；要更新只能打印全部）。

`layout` 结构（`print` 是本次浏览器排版实际采用的设置快照）：

```json
{"pages": 3, "cursor": {"page": 3, "y": 493.56}, "print": {"note_ratio": 0.50, "gap_lines": 2}, "answer_pages": [],
 "items": [{"question_id": "OP-000123", "uid": "三角函数1",
            "segments": [{"page": 1, "top": 0, "height": 125.7}]}]}
```

### 4.4 每题留白与切割线

题间留白是「留给你写的地方」，因此逐题可调：`items[].gap_lines` 是这道题之后的**绝对行数**
（0–48，每行 18px），`null` 表示继承板的全局 `print.gap_lines`（0–24）。
服务端 `effective_gap_lines()` 与前端 `boardEffectiveGap()` 是同一算式；导出时继承关系
已在服务端解开，浏览器模板只看到算好的绝对值。

**切割线**（`.cut-line`）画在每题留白的末尾，回答「这道题写到这里为止」：

| `cut_line` | 纸面 |
|---|---|
| `none` | 不画 |
| `dash` | 淡虚线（默认） |
| `solid` | 淡实线 |

`cut_label` 开启时线右端加一枚「第 N 题止」小标。线宽等于内容全宽（题栏 + 24px 间距 +
右侧留白区），打印色比屏幕深一档，否则喷墨印不出来。四种情况**不画**：贴页底、被顶到新页
顶部、答案页、仅新增模式的已打印占位区内——详见 `AI/export.md`。

### 4.5 切割线的默认值与入口

代码默认 `dash`，因此**历史板在下次打印时也会显示淡切割线**。展示板检查器的「版式」区
提供「不画 / 虚线 / 实线」切换和「线右端标『第 N 题止』」选项；也可以通过 API 修改：

```http
POST /api/board/update
{"id":"<BOARD_ID>","print":{"cut_line":"none"}}
```

「老板保持原样、新板默认开」如果是最终产品决定，应在 v2→v3 的迁移逻辑里把旧板写成
`none` 并补测试；当前实现**没有**这样区分。

**未实机验证：** 淡线在真实打印机 A4 上是否可见、会不会被判为过浅而完全吃掉，
尚未用真实打印机确认（本环境无打印机）。切割线的位置、条数、线宽与不画条件由
`tests/smoke_board_print.py::BoardCutLineSmokeTest` 在真实 Chromium 下验收。

### 4.6 边界与取舍

| 情况 | 处理 |
|---|---|
| 已打印题从板里移除 | 纸上仍有它：纸面记录保留其占位，仅新增时不会重排别的题去填空 |
| 重排 / 插入到中间 | 只影响下次「打印全部」；仅新增始终按纸面顺序在末尾续排 |
| 已打印题正文改动 | 行内「已改动」徽章 + 摘要计数；不自动重印 |
| 改版面几何后仅新增 | 沿用纸面几何（面板标注「仅新增时沿用纸面几何」） |
| 最后一页几乎排满 | 占位页被丢弃，新题直接从新页开始，页码仍是绝对页码 |
| 复制板 | 不复制纸面记录（新板对应新纸） |
| 重置纸面记录 | `POST /api/board/printed/reset`，之后只能打印全部 |
| 浏览器换了 / 字体变了 | 排版可能有像素级差异；纸面几何只依赖 cursor.y，误差落在题间留白里 |

**锁定边界：** 不论是否锁定，`items/add`、重复追加、`items/remove` 与整体覆盖 `items` 的成员/顺序变化均完整保留 `printed`（包括题目指纹、占位、页数、cursor、打印设置与答案页）。移出已印题不擦掉其占位；同一稳定 `question_id` 重新加入不重复打印。标签同步、统一 picker、撤销、拖拽/键盘/菜单排序与清理引用沿用此规则；新题按当前引用顺序选出，但始终接在旧纸面的末尾，题号按纸面记录题数续接。

有纸面且请求前或请求后的 `print.locked` 为真时，改变题栏比例、题头显示、切割线或生效的切割线标签，或改变仍在板内的已印题的**有效**留白，会走明确确认重印流程，服务端更新时重置纸面记录。单独开/关锁定、答案附页选择、未打印题留白、等值的继承/显式留白切换不重置；全局留白仅在确实改变保留的已印题有效留白时重置。切割线关闭时的标签设置不生效，无需确认。无纸面时不弹破坏性确认；未锁定时版式编辑保留旧纸面，`new` 仍按纸面几何续排。

确认由前端在本地变更和提交之前完成，后端保留真实版式变化的重置兜底；这不是新增鉴权机制，也不新增确认令牌。回归测试包含真实临时题库读写/HTML 数据、JS 动作与取消后零提交；`tests/smoke_board_lock.py` 通过隔离 HTTP + Chromium 核验补印按钮、透明旧区域和 cursor 续排，不代表物理打印机验收。

## 5. HTTP API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/boards` | `{boards:[…], folders:[…]}`；板含 `{id,name,note,folder_id,order,count,uids,updated_at,created_at,print,missing,suspended,printed_summary}`，`uids` 供选板浮层本地算行状态 |
| GET | `/api/board?id=` | 单板：解析后的 `items`（含 `printed/printed_page/changed`）、`printed`、`printed_summary` |
| POST | `/api/board/create` | `{name, uids?, label?, folder_id?}`；给 `label` 时按当前题目标记选题 |
| POST | `/api/board/update` | `{id, name?, note?, print?, items?, source_labels?, folder_id?}`；`items` 整体覆盖。`print` 含 `cut_line`/`cut_label`；`items[].gap_lines` 为绝对行数（`null`=继承），同帧提交 `items+print` 时折算用请求后的全局值 |
| POST | `/api/board/folder/create` | `{name}` → `{folder}` |
| POST | `/api/board/folder/update` | `{id, name?, order?}`；改 `order` 会重排整组文件夹 |
| POST | `/api/board/folder/delete` | `{id, keep_boards=true}`；默认把板移到未归档，`false` 时连板一起删 |
| POST | `/api/board/move` | `{id, folder_id, index?}`；板改文件夹 / 改组内顺序 |
| POST | `/api/board/items/add` | `{id, uids:[], position?}`；按 `question_id`/`uid` 去重，返回 `board.added` |
| POST | `/api/board/items/remove` | `{id, uids:[]}` |
| POST | `/api/board/duplicate` | `{id, name}`；复制引用与版面，不复制纸面记录 |
| POST | `/api/board/delete` | `{id}` |
| POST | `/api/board/printed` | `{id, mode:"all"|"new", layout}`；记录 / 追加纸面记录，返回 `board` |
| POST | `/api/board/printed/reset` | `{id}`；清空纸面记录 |
| POST | `/api/export` | `{format:"board", board_id, mode?:"all"|"new", include_answers?, overrides?}` → 自包含 HTML |

导出文件名 `OMRS-BD-<板名>[-新增]-错题集.html`；`Content-Disposition` 同时给 ASCII 兜底与
`filename*=UTF-8''…`，中文板名不再触发 latin-1 编码错误。

## 6. 纸面模型（浏览器模板 `board.js`）

- A4 纵向 `793.7 × 1122.52px`；左右 10mm、上下 12mm，
  页脚安全带 8.5mm（同 `a4.js`）；页眉「错题集」，并在 `show_meta` 开启且有值时显示生成日期，页脚绝对页码。
- 题栏宽 = `(内容宽 − 24) × (1 − note_ratio)`；`note_ratio` 默认 `0.50`，扣除 24px
  间距后题栏与右侧留白各约 347px。字号 / 表格 / 切片阈值直接复用 `a4.css` 的规则；
  右侧留白不生成任何 DOM。
- 切割线画在 `.page-inner` 上（不在 `.col` 里，那是 `overflow:hidden`），
  `top = 页眉高 39px + 留白末尾相对题栏顶的偏移`，宽度 = 内容全宽。
- 排版引擎与 `a4.js` 同源：按栏宽测真实高度 → 贪心装页；文字按公式边界拆段；表格整块；长图读
  像素找白缝切片，无缝时最少墨行处切并标红虚线告警；题头不留孤行；题目跨页时新页顶部补
  「第 N 题（续）」。题间留白放不下就贴页底，不为它另起一页。
- 标记芯片打印变体：18% 淡底 + 同色相压暗文字（`_board_label_ink`，WCAG AA）。
- 左侧只保留 10mm 普通页边距，不额外预留装订区，也不绘制装订导引线或打孔圆圈。

## 7. 维护边界

- 展示板不写 Ledger，`boards.json`（含纸面记录）随 `错题/` 目录备份。
- 题目 Markdown、标记和学习状态仍由各自链路维护；展示板只读取它们。
- `board.css` / `board.js` 是独立导出模板；改几何、页码、切片或纸面记录格式时同步 `AI/export.md`、
  `tests/test_boards.py`、`tests/smoke_board_print.py`（需要 playwright + Chromium，缺失自动跳过）。
- `assets/board.js` 的纯函数（`boardMoveItems / boardItemsPayload / boardUniqueUids /
  boardEstimateText / boardColumnWidth / boardEffectiveGap / boardDirtyMerge / boardSavePayload /
  boardFolderTree / boardPicker*`）通过 `module.exports` 暴露给 `tests/test_board_ui.js`；
  `boardColumnWidth` 与模板 `board.js` 的 `COL_W` 是同一算式，改几何要两处一起改。
- `assets/board_preview.js` 的消息协议由 `tests/test_board_preview.js` 锁住：几何 relayout
  不重新导出、内容变化才失效指纹、`omrs-board-select` 回传、回调惰性注册。
  改 `postMessage` 的消息名或载荷形状时，模板 `omrs/export_templates/board.js`、
  `assets/board_preview.js` 与这份测试必须一起改。
- 每题留白的算式有三处实现，必须同解：`omrs/boards.py::effective_gap_lines`、
  `omrs/exporting.py::_board_gap_lines`、`assets/board.js::boardEffectiveGap`。
