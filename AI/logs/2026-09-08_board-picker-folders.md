# 2026-09-08 展示板文件夹与统一选板浮层

## 变更摘要

按 `board-picker-folders-设计方案.md` 落地 P0 + P1。

**P0 统一选板浮层。** 此前「加入展示板」有两条并行实现：`boardQuickAdd()` 直接加入最近用过的板、
事后靠 toast 的「换个板…」纠错；`boardChooseAndAdd()` 弹 `uiDialog` 单选框。前者动作发生前看不见
目标，后者要点两次还不显示板的状态。现在八处入口统一走
`boardPickerOpen(uids, {anchor, exclude, moveFrom, direct, onDone})`：锚定在触发元素下方弹浮层，
单击板行即完成，没有「确定」按钮。`boardQuickAdd` / `boardChooseAndAdd` 保留为薄封装，
调用点函数名不变。

**P1 文件夹。** `boards.json` 升到 v2，新增单层（不嵌套）文件夹；左栏板列表从扁平列表改成
「文件夹 → 板」两级树，支持折叠、拖拽归类、文件夹排序，空文件夹显示占位。

## 行为与兼容性

- **数据格式**：`boards.json` `version: 1 → 2`，顶层新增 `folders`，板新增 `folder_id` 与 `order`。
  v1 文件（没有 `folders` 键）读取时自动迁移：文件夹列表为空、所有板归入未归档，下次写入落盘为新
  格式。`folder_id` 指向不存在的文件夹时静默归入未归档，不报错也不丢板。文件夹是分类，坏掉的分类
  不该连累数据。
- **`/api/boards` 响应变了**：从 `{boards}` 变成 `{boards, folders}`，且每个板多返回一个 `uids`
  字段。加这个字段是因为浮层要在点击之前就显示「已有 1/3」，而原来的 `count` 算不出来，逐板再请求
  又是 N 次往返；`_Resolver` 本来就把每个 item 解析过一遍，附带返回几乎零成本。
- **toast 变了**：加入后的 toast 去掉「换个板…」（选择已经前置到浮层里，不再需要这条事后纠错
  通道），改为「撤销」+「打开展示板」。只有 `Shift` 直加那条路径仍保留「换个板…」，因为那条路径
  确实跳过了选择。
- **速度不倒退**：键盘「打开浮层 → `Enter`」两键进上次的板（默认高亮会跳过「全部已在板中」的行，
  否则 `Enter` 是空动作）；`Shift` + 点「加入展示板」跳过浮层直接加入，toast 写明「已直接加入
  《X》」。按钮 `title` 在悬停 / 聚焦时现算，写出当前默认目标。原则是默认给选择，加速留给显式
  修饰键。
- 折叠状态存 `localStorage['omrs-board-folders-collapsed']`，不进 `boards.json`。
- 删除文件夹默认把板移到未归档（`keep_boards=true`），对话框里可改成连板一起删。

## 实现中的几个判断

设计方案没写死、由本次实现决定的地方：

1. **焦点始终留在搜索框**（combobox + `aria-activedescendant`），而不是按板数多少在搜索框和列表项
   之间切换。一套键盘处理、打字随时能过滤。触屏（`pointer: coarse`）不自动聚焦，免得软键盘弹起来
   挡住列表。
2. **「最近」只在板多于 6 个时显示。** 方案要求「与下方全量列表去重显示」，但保留分组里的位置对
   空间记忆更有价值，所以同一个板在两处都渲染、状态按 id 联动。板少时列表本来一屏看得完，这样只会
   让同一个板出现两次，看起来像 bug——加了阈值。
3. **`⌘` 点已加过的行 = 撤回本次加进去的那些题**（只撤这次会话加的，不动板里原有的）。
4. **搜不到时底部按钮变成「＋ 新建《输入的名字》并加入」**，不留死胡同。
5. **文件夹名比板名弱一档**（`--fs-sm` / `--fg2`）。文件夹是结构、板才是内容，视线应该优先落在
   板上。文件夹行只显示板数和「还没印上纸」的 `+N`，题数总和放进 `title`——220px 一行放不下三个
   数字，`+N` 才是「这组要不要补印」的关键信号。

## 修改文件

| 文件 | 变化 |
|---|---|
| `omrs/boards.py` | `BOARDS_VERSION=2`；`_normalize_folder` / `_arrange`（load 与 save 共用、幂等）；`create_folder` / `update_folder` / `delete_folder` / `move_board` / `list_folders`；`create_board` 接受 `folder_id`；`duplicate_board` 继承文件夹并显式排在源板之后；`list_boards` 返回 `folder_id` / `order` / `uids` |
| `omrs/server.py` | 4 条新路由（`/api/board/folder/{create,update,delete}`、`/api/board/move`）；`/api/boards` 返回 `folders`；`create` / `update` 接受 `folder_id` |
| `assets/board.js` | `boardPickerOpen` 及纯函数 `boardFolderTree` / `boardPickerRowState` / `boardPickerFilter` / `boardPickerRecent`；`boardListHtml()` 重写为两级树；`boardBindTreeDrag()`；文件夹 CRUD；toast 调整；`boardHintText()` 惰性标注默认板 |
| `assets/styles.css` | `.bd-picker-*`、`.bd-folder-*`、`.bd-tree`；颜色全部走既有变量，无裸十六进制 |
| `assets/questions.js` `qview.js` `feedback.js` `qtable.js` `data.js` `schedule.js` `omrs_dashboard.html` | 各入口传 `anchor` 与 `direct`（`Shift`）；题库行内菜单的锚点取仍在 DOM 里的 `⋯` 按钮，不取会被一起关掉的菜单项 |
| `tests/test_boards.py` | 新增 `BoardFolderTests`：v1 迁移、悬空 `folder_id`、文件夹 CRUD 与排序、删除文件夹两种语义、跨组 / 组内移动、复制归属、`list_boards` 的 `uids` |
| `tests/test_board_ui.js` | 新增 5 组纯函数用例 |

## 验证

- `python3 -m unittest discover -s tests -p "test_*.py"` → 67 passed（新增 7 个)。
- 全部 `tests/test_*.js` 逐个 `node --test` → 通过；`test_board_ui.js` 9 passed。
- 起真实 `OMRSHandler` 打了一轮 HTTP：4 条新路由、`/api/boards` 带 `folders` 与 `uids`、
  删除文件夹后板落到未归档、文件夹不存在时返回 400。
- 浏览器实测（Playwright 驱动本地 Chrome，桩掉 `fetch`、`core.js` 与 `board.js` 都是真的）
  24 项断言全过、无 pageerror：锚定位置、三种行状态、默认高亮跳过 `is-full`、`↑↓` / 输入过滤 /
  `Enter` 加入并关闭、`⌘` 连加与撤回、`Esc` 与点击外部关闭、`Shift` 直加、按钮 `title`、
  「全部已在板中」改为打开该板。
- 单独验证方案 §3.5 的 `Esc` 顺序陷阱：`app.js` 的 Modal 关闭器在冒泡阶段，浮层在 capture 阶段
  `stopPropagation`，因此浮层开着时 `Esc` 关的是浮层，底层 Modal 不受影响，浮层关掉后再按才轮到
  Modal。三项断言通过。
- 浅色 / 深色两套主题渲染截图人工复核过一轮，据此修掉三处：短列表里「最近」重复渲染同一个板、
  底部提示换行、未归档分组显示了一个点了没反应的折叠箭头。

## 同步过的文档

`AI/board.md`（§2 数据文件、§3 页面、新增 §3.1 板列表树 / §3.2 选板浮层 / §3.3、§5 API 表）、
`AI/api.md`（`/api/boards` 响应、`create` 的 `folder_id`、4 个新端点）、
`AI/data.md`（§14 boards.json v2 与迁移）、`AI/frontend.md`（§3.4 与浮层 / 左栏树的样式约定）、
根 `README.md`（版本表）、版本号四处（`omrs/version.py`、`omrs_dashboard.html`、根 `README.md`、
`AI/README.md`）。

## 遗留

- 本次在 sanitized 源码导出包上作业，包内没有 `.git`、`AI/logs/`、`AI/changelog.md` 和
  `tests/check_docs.py`（`SOURCE_EXPORT_MANIFEST.txt` 已注明排除）。因此 `git status --short`、
  `git diff --name-status` 和 `python3 tests/check_docs.py` 本次**没有执行**，需要在完整仓库里补跑；
  `AI/logs/log.md` 的索引行和 `AI/changelog.md` 的 v1.17.0 段落也需要在完整仓库里补上，本次没有
  凭空新建这两个文件。
- 方案 §7 的「板名字号档」未做。§8 的四个待定项按方案倾向取默认：文件夹单层不嵌套、未归档恒在
  最后、文件夹不参与题目筛选、删除文件夹默认保留板。
