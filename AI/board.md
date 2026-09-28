# 展示板（错题集打印）

> **速查**
> - 职责：展示板引用集合、版面设置、打印（全部 / 仅新增）与纸面记录
> - 入口：`omrs/boards.py`、`omrs/exporting.py`（展示板段）、`assets/app/features/board/index.js`（页面）、`assets/app/features/board/detail.js`（板详情）
> - 不变量：展示板只保存题目引用，不复制题目内容；纸面记录绑定导出快照
> - 必跑测试：`tests/test_boards.py`、`tests/test_board_export.py`、`tests/test_board_integrity.py`、`tests/smoke_board_print.py`
> - 相关：`AI/frontend/board-ui.md`、`AI/export.md`

> 对应源文件：`omrs/boards.py`、`omrs/exporting.py`（展示板导出段）、
> `omrs/export_templates/board.css`、`omrs/export_templates/board.js`、
> `assets/app/features/board/`（页面 `index.js` / `view.js` / `state.js` / `board.css` / `board-layout.css` / `board-list.css` / `board-popovers.css`、板详情 `detail.js` / `runtime.js`、`add.js`、`model.js`、`save.js`、`print.js`、`preview.js`、`settings.js`、`drag.js`）、
> `assets/app/domain/board/`（`model.js`、`boards.js`、`detail-port.js`、选板浮层 `picker.js`）、`tests/test_boards.py`、
> `tests/test_board_export.py`、`tests/app/board.test.mjs`、`tests/app/board-preview.test.mjs`、
> `tests/app/board-regions.test.mjs`、`tests/smoke_board_print.py`、`tests/test_board_locked_incremental.py`、
> `tests/app/board-locked.test.mjs`、`tests/app/board-page.test.mjs`、`tests/e2e/board.py`。

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

## 3. 展示板页面（`assets/app/features/board/`）

侧栏的「展示板」Tab 打开纸面工作区。桌面从左到右为板列表、常驻纸面和题目面板；板头横跨纸面与题目区域。纸面工具条负责页数、未印 / 已改动提示、翻页、缩放与版式入口。版式和纸面记录在各自浮层里；题目详情从题目面板右侧滑入。移动端（≤760px）板列表改为抽屉，题目面板排在纸面下方。

`view.js` 绘制板头、左栏、纸面与题目面板；`state.js` 派生板头、板树、纸面工具条、题目行、详情与浮层数据；`index.js` 接线动作和快捷键。整页 `morph` 不移动 `#bd-stage[data-morph="skip"]`，因此预览 iframe 保持常驻。`tests/app/board-regions.test.mjs` 与 `tests/e2e/board.py` 覆盖结构和主交互。

板头有可改名的板名、文件夹、题数、备注、保存状态、下载和主打印按钮。有纸面记录且有新增题时显示「只印新增 / 全部重印」。打开打印预览后板头下出现确认条；只有选择「已打印，记录纸面」才写入记录。「没打成」清掉待确认状态。主按钮文案随当前范围和题数变化。

### 3.1 板列表：文件夹 → 板

板列表由 `domain/board/boards.js` 持有数据，`boardFolderTree()` 分组，文件夹按 `order` 排列，未归档恒在最后。左栏可以新建板或文件夹、查找板、折叠文件夹；板行显示题数、已印页数和未印题数。板 / 文件夹的菜单保留重命名、备注、复制、移动、导出和删除等已有操作。折叠状态存在 `localStorage['omrs-board-folders-collapsed']`，不进 `boards.json`。

板与文件夹拖放由 `features/board/drag.js` 计算落点，写操作交给 `domain/board/boards.js`；板拖到文件夹行会移动，拖到板行会排序。手机上左栏由板头按钮打开为抽屉，选择板后收起。其它页面的「加入展示板」入口仍走下述统一选板浮层。

### 3.2 加入展示板：统一选板浮层

八处入口（题库行内 `⋯`、题库批量条、题目 Modal、反馈判定面板、即时练习、数据复盘顽固题表、
收件箱、录入成功提示）统一走 `domain/board/picker.js` 的 `boardPickerOpen(uids, {anchor, exclude, moveFrom, direct, onDone})`。
`boardQuickAdd` / `boardChooseAndAdd`（`domain/board/index.js`）是薄封装；旧脚本经过渡桥挂回的同名全局调用，函数名不变。

浮层结构：标题（带本次题数）+ 搜索框 + 分组列表 + 「＋ 新建板并加入…」。传了 `anchor` 就锚定在
触发元素下方弹出，没有则同一份 DOM 居中显示（toast 按钮、快捷键走这条）。**单击板行即完成**，
没有「确定」按钮；`⌘/Ctrl` + 点击则加入但不关闭，可连加多个板，再点一次撤回本次加进去的题。
点击决策是纯函数 `boardPickerPlan`（打开 / 撤回 / 加入）。「换个板…」加入新板后从原板移除，toast 写「已从《原板》移到《新板》」。

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
toast 写明「已直接加入《X》」；只有实际加入题目时才给「撤销」「换个板…」，两者只处理服务端 `added_uids` 返回的本次新增引用；按钮 `title` 在悬停 / 聚焦时现算，写出当前
默认目标（`加入展示板（上次：X）`）。原则是**默认给选择，加速留给显式修饰键**。

键盘（`core/keys.js` 的浮层键盘层 `pushKeyLayer`，先于页面与全局快捷键）：`↑/↓` 循环移动高亮
（默认高亮第一个不是「全部已在板中」的行，否则 `Enter` 是空动作）、`Enter` 加入、`Ctrl/⌘ + Enter`
连加（浮层不关）、`Esc` 关闭；`←` 折叠高亮行所在的文件夹并把高亮移到组后第一行，紧接着 `→` 展开同一个组、
高亮回到组里第一行（高亮行不在文件夹组里时 `←/→` 照常移动光标）。焦点始终留在搜索框（combobox +
`aria-activedescendant`），焦点不在搜索框时打字直接进搜索框；键盘层独占，浮层开着时背后页面的
快捷键（如题库的 `V`）不触发。触屏（`pointer: coarse`）不自动聚焦，免得软键盘挡住列表。
叠在题目弹窗上时浮层是 `ui/overlay` 的客人（`escape:true`），`Esc` 由 overlay 在捕获阶段关浮层，
底层弹窗不会被顺手关掉，焦点回到弹窗里的「加入展示板」；不在对话框里时关闭后焦点回到触发元素。
点浮层外关闭（document 捕获阶段的 click，打开后下一轮才挂上），叠在浮层上面的弹层不算外面。

### 3.3 添加题目与页面键盘

「添加题目」对话框在 `features/board/add.js`，复用统一筛选与勾选集合：已在板里的题不能重复加入，可全选筛选结果。关联标记按板 ID 存在浏览器本地 `localStorage['omrs-board-linked-labels']`，不改服务端 `source_labels`；点击「同步」才按关联标记追加新题并去重。停用或缺失题在列表里提示，打印时跳过，用户可选择移出。

页面快捷键经 `core/keys.js`：`N` 新建、`A` 加题、`P` 打印预览、`←/→` 翻页、`↑/↓` 选题、`Ctrl/⌘+↑/↓` 排序、`Enter` 打开、`Delete` 移除。输入框、对话框和选板浮层取得键盘优先权。

### 3.4 常驻纸面、题目面板与详情

纸面是一个同源 `srcdoc` iframe，内容直接来自 `/api/export` 的展示板 HTML；翻页、缩放和纸面统计使用它回传的版面。打印与预览使用同一排版。iframe 保持在 `#bd-stage` 中，点纸面上的题通过 `omrs-board-select` 打开右侧详情。内嵌 HTML 的顶栏打印按钮被 `embedded` 收起，以免产生另一套入口。生命周期、指纹和消息校验见 `AI/frontend/board-ui.md`。

题目面板的列表按纸面顺序显示 UID、已印页码 / 未印 / 已改动等状态、分类、难度、标记圆点和行内留白步进；排序菜单、拖放与键盘排序仍可用。点击行打开滑入式详情层，可前后切题、查看题面和练习记录、设置题后留白、打开题目或移出板。行内步进和详情预设均通过 `detail.js` 的 `setItemGap()` 写入。留白范围是 0–48 行，空输入代表继承板级值，保存时保持 `null`；锁定保护边界见 §4.6。

「版式」浮层提供右侧留白、题间留白、答案、题头、切割线与锁定；「纸面记录」浮层显示已印题数、页数、续排位置和已改动计数，并可清空记录。

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

`boardStatusModel(board, mode, awaiting)`（`features/board/model.js`）判定打印范围与当前纸面状态；`state.js::statusView()` 将它与题目数结合，生成板头主按钮的文案。没有纸面时显示「打印 N 题」，有纸面时可「重印全部 N 题」；有新增题并选择仅新增时显示「补印新增 M 题」。只有存在纸面记录且有新增题，板头才显示打印范围分段。`changed_count` 和未印数在纸面工具条显示，纸面统计按钮打开记录浮层。

打开打印预览或下载 HTML 后，主页面出现「打印好了吗？确认后才会记下纸面」确认条。选择「已打印，记录纸面」才记录；选择「没打成」、重置纸面记录或改变打印范围会清掉待确认状态。待记录导出任务与当前预览分开保存，切板和后续编辑不改变它的板 ID、模式和 HTML 快照。

页数直接读常驻预览 iframe 回传的 `layout`（`page_numbers` / `pages`），几何改动通过 iframe 内的 `relayout` 重排。页面不在前台或预览滚出视口时暂停排版，回来再补。下载任务通过隐藏 iframe 测量其保留的同份 HTML；独立打印窗口的 layout 只归属该窗口的导出任务。

### 4.3 记录纸面

版面由浏览器实测，所以记录也来自浏览器：

1. 导出模板排版完成后写 `window.OMRS_LAYOUT`，并向 `opener` / `parent` `postMessage`
   `{type:"omrs-board-layout", boardId, mode, layout}`；顶栏「✓ 已打印，记录纸面」发送
   `omrs-board-printed`。
2. 主程序两条路径都使用导出快照：① 独立窗口点「已打印」→ 宿主确认 → 记录该窗口的 layout；② 主页面「记录纸面」→ 使用该板最近一次待记录导出的 layout，下载 HTML 尚无 layout 时测量保留的同份 HTML。导出等待保存完成，板 ID、模式与窗口映射固定；切板和后续编辑不会让记录改用当前预览。待记录任务存在当前页面内存中，刷新页面不保留。
3. `POST /api/board/printed {id, mode, layout}`（§5）由服务端合并；`mode:"all"` 优先保存
   `layout.print`（模板实测时的 `note_ratio / gap_lines` 等几何快照），以保证记录的设置就是实际
   打出来的设置；旧版客户端未提供该字段时才回退到板当前 `print`。`mode:"new"` 追加题目时继续
   保留原 `printed.print`，不会用本次增量布局里的设置覆盖原纸几何。`hash` 优先取导出时的题目正文指纹，旧导出件缺失时回退记录时正文；
   题目改了会在行内显示「已改动」并在摘要里计数（纸面仍是旧版；要更新只能打印全部）。

服务端校验 `layout.board_id / mode`（存在时必须与请求相符，否则 400 且不写入），并拒绝未知、别板或 `question_id / uid` 不一致的题目引用；`mode:"new"` 没有既有纸面时拒绝。`pages`、`cursor.page`、题目段页码和答案页码必须在同一版面范围内。导出后从板中移除的整板旧快照仍可记录，以保留实际纸面占位；旧导出件缺少归属字段时仍兼容这些校验。`layout.items[].hash` 为导出时的正文指纹。

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

代码默认 `dash`，因此**历史板在下次打印时也会显示淡切割线**。展示板「版式」浮层
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

确认由前端在本地变更和提交之前完成，后端保留真实版式变化的重置兜底；这不是新增鉴权机制，也不新增确认令牌。回归测试包含真实临时题库读写/HTML 数据、JS 动作与取消后零提交；`tests/e2e/board.py` 通过隔离 HTTP + Chromium 核验补印按钮、透明旧区域和 cursor 续排，不代表物理打印机验收。

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

异步状态与纸面快照的保障范围见 `AI/optimization.md`「展示板完整性保障」。

- 展示板不写 Ledger，`boards.json`（含纸面记录）随 `错题/` 目录备份。
- 题目 Markdown、标记和学习状态仍由各自链路维护；展示板只读取它们。
- `board.css` / `board.js` 是独立导出模板；改几何、页码、切片或纸面记录格式时同步 `AI/export.md`、
  `tests/test_boards.py`、`tests/smoke_board_print.py`（需要 playwright + Chromium，缺失自动跳过）。
- 展示板纯函数在 `assets/app/features/board/model.js`（留白、排序、保存载荷、状态机、锁定边界、
  估算文案、几何常量）与 `assets/app/domain/board/model.js`（选板分组、行状态、过滤、最近使用、
  `boardUniqueUids`，以及选板浮层的行模型与点击决策），由 `tests/app/board.test.mjs`、`board-picker.test.mjs` 覆盖；
  板详情控制器 `features/board/detail.js` 由 `tests/app/board-locked.test.mjs` 注入替身覆盖。选板浮层的真实交互由 `tests/e2e/board_picker.py` 覆盖，
  整页（板头、左栏、常驻纸面、题目面板、滑入详情、版式与纸面记录浮层、快捷键，以及「加题 → 排序 → 版式设置 → 打印预览 → 仅补印新增」）由
  `tests/e2e/board.py` 覆盖，视图模型与板列表由 `tests/app/board-page.test.mjs` 覆盖。`boardColumnWidth` 与模板 `board.js` 的 `COL_W`
  是同一算式，改几何要两处一起改。
- 常驻预览 `assets/app/features/board/preview.js` 的消息协议由 `tests/app/board-preview.test.mjs` 锁住：几何 relayout
  不重新导出、内容变化才失效指纹、`omrs-board-select` 回传、回调惰性注册。
  改 `postMessage` 的消息名或载荷形状时，模板 `omrs/export_templates/board.js`、
  `assets/app/features/board/preview.js` 与这份测试必须一起改。
- 每题留白的算式有三处实现，必须同解：`omrs/boards.py::effective_gap_lines`、
  `omrs/exporting.py::_board_gap_lines`、`assets/app/features/board/model.js::boardEffectiveGap`。
