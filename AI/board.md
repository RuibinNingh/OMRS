# 展示板（错题集打印）

> v1.14.0 新增，2026-09-04 重做。对应源文件：`omrs/boards.py`、`omrs/exporting.py`（展示板导出段）、
> `omrs/export_templates/board.css|board.js`、`assets/board.js`、`assets/styles.css`（`.bd-*`）、
> `tests/test_boards.py`、`tests/test_board_export.py`、`tests/smoke_board_print.py`。

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

> 现行实现说明：展示板不绘制 3 孔、26 孔等打孔圆圈，但会在左侧装订区域保留一条极浅的装订导引虚线（`.bind-line`）；`binding_mm` 是装订边距，不是孔位标记开关。

## 2. 数据文件 `boards.json`

路径：`错题/.omrs/boards.json`。写入先把已有文件滚动为 `.bak.1/2/3`，再通过临时文件、
`fsync` 和 `os.replace` 原子替换（`save_boards`）。

```json
{
  "version": 1,
  "boards": [{
    "id": "BD-20260904-a1b2c3",
    "name": "考前速览·三角函数",
    "note": "月考前使用",
    "created_at": "2026-09-04T12:00:00+00:00",
    "updated_at": "2026-09-04T12:30:00+00:00",
    "source_labels": ["考前必看"],
    "print": {
      "note_ratio": 0.42,
      "gap_lines": 2,
      "binding_mm": 22,
      "answers": "none",
      "show_labels": true,
      "show_meta": true
    },
    "printed": {
      "at": "2026-09-04T12:40:00+00:00",
      "pages": 3,
      "cursor": {"page": 3, "y": 493.56},
      "print": {"note_ratio": 0.42, "gap_lines": 2, "binding_mm": 22, "...": "打印时的版面"},
      "items": [{"question_id": "OP-000123", "uid": "三角函数1", "hash": "9f2c…",
                 "segments": [{"page": 1, "top": 0, "height": 125.7}]}],
      "answer_pages": []
    },
    "items": [{
      "question_id": "OP-000123",
      "uid": "三角函数1",
      "added_at": "2026-09-04T12:10:00+00:00",
      "extra_gap_lines": 0,
      "pin": false
    }]
  }]
}
```

字段规则（`normalize_print` / `_normalize_item` / `_normalize_printed`）：

- `print.note_ratio` 钳到 `0.30–0.55`，`gap_lines` `0–24`，`binding_mm` `10–40`，
  `answers ∈ {none,append}`；未知键忽略，缺失键回默认。展示板不生成打孔标记。
- `items[].extra_gap_lines` 0–24：该题之后额外多留几行（每行 18px），供「这题我要写很多」。
- `printed.pages == 0` 表示没有纸面记录；旧文件里的 `last_printed_page` 字段直接忽略。
- 整体覆盖 `items` 时（`update_board(items=…)`）会保留同一题原有的 `added_at`。

### 题目引用解析

`_Resolver` 一次性读取 `question_projection` 与 `mastery_data.csv`，每个 item 解析出
`subject / category / difficulty / mastery / due_date / labels / suspended / missing /
file_path`，以及纸面相关的 `printed`（已在纸上）、`printed_page`、`changed`（题目正文在
打印后改过）。优先按 `question_id` 命中，题目迁移或改名后仍能对上并更新为当前 UID。

`get_board` / `list_boards` 另附 `printed_summary`：`{at, pages, count, new_count,
changed_count, cursor, answer_pages, print}`。

## 3. 展示板页面（`assets/board.js`）

侧栏「题目库」与「目录」之间的「展示板」Tab，三栏：

1. **板列表**（sticky）：板名、题数、已印页数 / 新增数、更新时间；`⋯` 菜单：重命名、备注、复制、
   导出 HTML、删除。空态给「新建第一个展示板」。
2. **板内容**：标题（双击重命名）+ 题数 / 科目分布 / 纸面摘要；工具条「添加题目 / 按标记同步 /
   排序 ▾ / 清空」；每行 = 拖拽手柄 + 序号 + UID + 徽章（已印 p.N / 新增 / 已改动 / 停用 / 缺失）
   + 标记芯片（点击开 LabelPicker）+ 元信息 + 「留白 +N 行」+ 预览 + ✕。缺失 / 停用题有黄红提示条
   与一键清理。排序即持久化（`POST /api/board/update {items}`）。
3. **版面与打印**（sticky）：右侧留白占比（30–55%）、题间留白行数、装订边、答案、
   题头显示项；即改即存（去抖 500ms）。下方「打印」区见 §4；「预计页数」和纸面记录都来自隐藏 iframe 的浏览器实测。

「加入展示板」入口统一走 `boardQuickAdd(uid | uids)`：加入最近使用的板（`localStorage
'omrs-board-last'`），toast 带「撤销」「换个板…」；没有板时先弹新建对话框。题库批量条 /
题目 Modal / 反馈判定面板 / 即时练习 / 数据复盘顽固题表 / 收件箱都复用它。
题库批量条走 `boardChooseAndAdd(uids)` 选板对话框。

「添加题目」对话框复用 `filterItems()`（搜索 / 科目 / 分类 / 知识点 / 状态 / 到期 / 标记 chips），
已在板中的题目灰显跳过，可「全选筛选结果」。「按标记同步」是显式追加并去重，不会因题目后来
打标而自动改变板。

键盘：`N` 新建、`A` 添加题目、`P` 打印预览、`↑/↓` 选行、`Ctrl/⌘+↑/↓` 移动行、`Enter` 打开、
`Delete` 移除；所有对话框用 `uiDialog/uiPrompt/uiConfirm`（core.js），不再用 `prompt()`。

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
- 纸面几何（`note_ratio / gap_lines / binding_mm`）在仅新增模式下**沿用纸面记录**，与原纸对齐；
  `answers / show_labels / show_meta` 跟随当前设置。新题的答案附页排在新题之后的
  新页上（标题「答案（本次新增）」），不会去动已打印的答案页。
- 题号接着纸面继续（`index_start = printed.count + 1`）。

### 4.2 记录纸面（「标记为已打印」）

版面由浏览器实测，所以记录也来自浏览器：

1. 导出模板排版完成后写 `window.OMRS_LAYOUT`，并向 `opener` / `parent` `postMessage`
   `{type:"omrs-board-layout", boardId, mode, layout}`；顶栏「✓ 已打印，记录纸面」发送
   `omrs-board-printed`。
2. 主程序两条路径都能记录：① 打印预览窗口点「已打印」→ 主页面弹确认 → 记录；② 展示板页点
   「标记为已打印」→ `boardMeasureLayout()` 把同一份导出 HTML 放进隐藏 iframe（同一浏览器、
   同一字体，版面一致）→ 拿到 layout → 记录。下载后离线打印的情况走 ②。
3. `POST /api/board/printed {id, mode, layout}`（§5）由服务端合并；`hash` 取题目正文指纹，
   之后题目改了会在行内显示「已改动」并在摘要里计数（纸面仍是旧版；要更新只能打印全部）。

`layout` 结构：

```json
{"pages": 3, "cursor": {"page": 3, "y": 493.56}, "answer_pages": [],
 "items": [{"question_id": "OP-000123", "uid": "三角函数1",
            "segments": [{"page": 1, "top": 0, "height": 125.7}]}]}
```

### 4.3 边界与取舍

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

## 5. HTTP API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/boards` | 板列表：`{id,name,note,count,updated_at,created_at,print,missing,suspended,printed_summary}` |
| GET | `/api/board?id=` | 单板：解析后的 `items`（含 `printed/printed_page/changed`）、`printed`、`printed_summary` |
| POST | `/api/board/create` | `{name, uids?, label?}`；给 `label` 时按当前题目标记选题 |
| POST | `/api/board/update` | `{id, name?, note?, print?, items?, source_labels?}`；`items` 整体覆盖 |
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

- A4 纵向 `793.7 × 1122.52px`；左装订边 `binding_mm`（默认 22mm ≈ 83.1px），右 10mm，上下 12mm，
  页脚安全带 8.5mm（同 `a4.js`）；页眉「错题集」，并在 `show_meta` 开启且有值时显示生成日期，页脚绝对页码。
- 题栏宽 = `(内容宽 − 24) × (1 − note_ratio)`，默认约 376px，与 A4 双栏栏宽相近，字号 / 表格 /
  切片阈值直接复用 `a4.css` 的规则；右侧留白不生成任何 DOM。
- 排版引擎与 `a4.js` 同源：按栏宽测真实高度 → 贪心装页；文字按公式边界拆段；表格整块；长图读
  像素找白缝切片，无缝时最少墨行处切并标红虚线告警；题头不留孤行；题目跨页时新页顶部补
  「第 N 题（续）」。题间留白放不下就贴页底，不为它另起一页。
- 标记芯片打印变体：18% 淡底 + 同色相压暗文字（`_board_label_ink`，WCAG AA）。
- 展示板只保留 `binding_mm` 装订边距，不绘制 3 孔、26 孔或其他打孔圆圈；模板仍绘制极浅的 `.bind-line` 装订导引虚线。

## 7. 维护边界

- 展示板不写 Ledger，`boards.json`（含纸面记录）随 `错题/` 目录备份。
- 题目 Markdown、标记和学习状态仍由各自链路维护；展示板只读取它们。
- `board.css` / `board.js` 是独立导出模板；改几何、页码、切片或纸面记录格式时同步 `AI/export.md`、
  `tests/test_boards.py`、`tests/smoke_board_print.py`（需要 playwright + Chromium，缺失自动跳过）。
