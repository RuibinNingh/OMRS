# HTTP API：调度、导出与展示板

> **速查**
> - 职责：调度、导出与展示板的请求、响应及错误语义
> - 入口：`omrs/http/registry.py`、`omrs/http/` 领域适配
> - 不变量：统一鉴权、读取期限和生命周期边界见 `AI/api.md`；注册表是路由唯一来源
> - 必跑测试：`tests/test_http_boundaries.py`、`tests/test_security.py`
> - 相关：`AI/api.md`、`AI/routes.md`、`AI/security.md`

### `POST /api/confirm-schedule`
根据用户勾选的题目生成 Session。

**请求体：**
```json
{
  "selected": [
    {"uid": "三角函数1", "source": "due"},
    {"uid": "几何题3", "source": "proficiency"}
  ],
  "subject": "数学"
}
```

可选字段 `persist` 必须为布尔值。`persist:true` 让单题选择也创建正式 `EXP-` Session；省略或传 `false` 时保留兼容语义：单题创建 `TMP-` 临时调度，多题创建正式 Session。正式 Session 创建会去重 UID、校验 `source` 只能为 `due` 或 `proficiency`，并拒绝不存在、停用或已被 active Session 占用的题目。

**响应：**
- ≥2 题：常规 Session（EXP- 前缀），写入 sessions.csv，`session_type: "exp"`
- 1 题：自定义调度（TMP- 前缀），不写入 sessions.csv，`session_type: "tmp"`

多题请求如果包含已在 active Session 中的 UID，后端返回 400 并拒绝创建，避免重复调度。当前单题路径直接生成 `TMP-` 临时 Session，不执行这项 active Session 排除检查。

---

### `POST /api/export`
导出**自包含 HTML**（图片已 base64 内联，单文件可拷给任何带浏览器的设备）。支持两种选题模式：

```json
{ "session_id": "EXP-..." }
```
或
```json
{ "uids": ["题1", "题2"] }
```

可选字段：
- `"format"`：`"a4"`（打印版，默认）或 `"screen"`（屏幕阅读版）。为兼容旧调用，`"docx"`/`"word"`/`"html"`/空 一律按 `a4` 处理。
- `"include_answers": true`：在「一、题目」之后追加「二、反馈区」一节，**每题**的答案下面紧跟该题错因（不分开）。不勾选时反馈区仍会出现，但只有错因，没有答案正文。
- `"question_gap_lines": 0`：A4 题目之间预留的空行数，后端钳制到 `0–20`；默认 `0`，屏幕版忽略该留白。
- `"a4_two_columns": true`：A4 是否使用双栏，默认 `true`；设为 `false` 时整份导出使用单栏。屏幕版忽略该字段。

返回 HTML 文件流（`Content-Type: text/html; charset=utf-8`），文件名 `OMRS-{session}-{a4|screen}.html`（经 `filename*=UTF-8''` 传中文/带后缀名）。临时调度导出的批次号前缀为 `TMP-`，不写入 `sessions.csv`。

**版面与长图切片全部在浏览器端完成**（见 `export.md`）：Python 读题、解析分节，把文字、图片和 Markdown 表格转换为结构化块，图片读成 base64，再将模板 JS/CSS 和本地 KaTeX CSS/JS/字体全部内联。A4 的分页与超长图白缝切片由打开文件的浏览器即时计算；题目与答案走同一条 `_text_to_blocks()` 路径。`$...$` / `$$...$$` 在 A4 与屏幕版均由内联 KaTeX 离线渲染，失败时降级显示原公式。栏模式只由 `a4_two_columns` 决定；前端每次导出 A4 时都会确认，含表格或长公式时可选单栏保留列宽。

题目块显示 UID、科目、分类、难度、状态标签和知识点标签，便于打印后按标签复盘。

#### 展示板模式：`format:"board"`

展示板模式使用持久化展示板，而不是 `session_id` / `uids`：

```json
{
  "format": "board",
  "board_id": "BD-20260904-a1b2c3",
  "mode": "new",
  "include_answers": false,
  "overrides": { "note_ratio": 0.50, "gap_lines": 2, "answers": "none",
                 "show_labels": true, "show_meta": true, "cut_line": "dash", "cut_label": false }
}
```

- `board_id` 必填，也兼容使用 `id`；板内引用按 `question_id` 优先解析。
- `mode` 为 `all`（默认，整板从第 1 页排）或 `new`（只排尚未进入纸面记录的题目，接在
  纸面记录的 `cursor` 之后续排；没有纸面记录或没有新题时返回 400）。`new` 模式下
  `note_ratio / gap_lines` 沿用纸面记录，其余显示项跟随当前设置。`mode:"new"` 的增量预览也固定
  使用该纸面快照，当前板比例不会覆盖已经打印的纸面几何。
- `include_answers` 省略时沿用板设置 `print.answers`，传 `true` 时在新页追加答案附页，每题答案后面跟该题错因。不论是否勾选，题面栏只放「关联」，错因一律留在答案附页（错因会提示解法）。
- `overrides` 只覆盖本次导出的版面设置，不回写 `boards.json`。停用题和缺失题保留在板内
  显示，但导出时跳过。

响应仍是 `text/html; charset=utf-8` 的文件流；文件名 `OMRS-BD-<板名>[-新增]-错题集.html`，
`Content-Disposition` 同时带 ASCII 兜底与 `filename*=UTF-8''…`。HTML 自包含 `board.css` /
`board.js` 与题图数据，分页在浏览器完成，页眉固定「错题集」，页脚为板内绝对页码；排版完成后
模板把版面（`window.OMRS_LAYOUT`，含本次排版实际采用的 `print` 快照）`postMessage` 给主程序，
用于 `POST /api/board/printed`。

展示板页的常驻预览 iframe 用的就是这个端点。它按「板 + 模式 + 题目签名（含答案与标记开关）+ 纸面时间」做指纹缓存，
**纯几何设置不在指纹里**：拖滑块、改题间留白、换切割线走 `omrs-board-relayout` 在 iframe 里就地
重排，一次请求都不发。因此几何调整期间这个端点的 QPS 应当为 0；不为 0 就是回归。

### `POST /api/board/create`
创建展示板，可选地在创建时加入题目或按一个标记初始化。

**请求体：**
```json
{ "name": "三角函数", "uids": ["三角函数1", "三角函数2"], "label": "考前必看", "folder_id": "BF-20260907-a1b2c3" }
```

`uids` 只加入当前可解析的题目并自动去重；当 `uids` 为空且提供 `label` 时，
会把当前统计中的所有匹配题加入板内。`folder_id` 可选，缺省或指向不存在的文件夹时落到未归档。**响应：** `{"status":"ok","board":{...}}`，
其中 `board.items[]` 是已解析的条目详情。

### `POST /api/board/update`
部分更新展示板元数据、版面设置或条目顺序（纸面记录走 `/api/board/printed`）。

**请求体：**
```json
{
  "id": "BD-20260904-a1b2c3",
  "name": "月考前",
  "note": "只在系统内显示",
  "print": { "gap_lines": 8, "cut_line": "dash", "cut_label": false, "locked": true },
  "items": [
    {
      "question_id": "OP-000123",
      "uid": "三角函数1",
      "added_at": "2026-09-04T12:00:00+00:00",
      "gap_lines": 12,
      "pin": false
    }
  ]
}
```

各字段均可省略；`print` 是覆盖式合并，`items` 是**整体覆盖**而不是追加。锁定与未锁定的成员增删、排序、重复追加、未打印题留白均保留全部 `printed`；已印题移出后占位仍在，同一稳定 ID 再加入不会重复补印。整体更新会解析稳定身份并保留原有 `added_at`。

请求前或请求后的 `print.locked=true` 时，真实的题栏比例/题头显示/切割线变化，或保留的已印题有效留白变化会重置纸面；全局留白只在影响已印题有效留白时重置。单独切锁、答案附页、等值留白、关闭切割线时的标签变化不重置。前端在真实影响发生前明确确认，取消不提交；后端不新增确认参数。重置前将旧纸面的**摘要**追加到 `boards_printed_history.jsonl`，不是完整快照，详见 `AI/board.md` §4.6。
`items` 中每项同时保存 `question_id` 与 `uid`。成功响应为 `{"status":"ok","board":{...}}`。

**留白字段：** `items[].gap_lines` 是绝对行数，钳到 `0–48`；`null` = 继承板的全局
`print.gap_lines`（该值本身钳到 `0–24`）。传不上来的值（`"x"`、NaN）按 `null` 处理，
不会折成 0。v2 客户端仍可传 `extra_gap_lines`（钳到 `0–24`），服务端按
`全局 + 额外` 折算成等值的绝对行数后写入 `gap_lines`，响应里 `extra_gap_lines` 恒为 0。

**同一请求提交 `items` + `print`：** `print` 先生效，`items` 的 v2 折算用的是本次请求
**之后**的全局留白。前端的脏字段队列正是靠这条保证把「改了留白又拖了滑块」合并成一次 POST。

**切割线：** `print.cut_line ∈ {none, dash, solid}`（默认 `dash`）、`print.cut_label`（默认
`false`），控制每题留白末尾的裁切提示线，见 `AI/export.md`。`print.locked` 控制版式锁定，锁定板的纸面重置规则见上文。

### `POST /api/board/items/add`
向展示板追加或插入题目引用。已存在的 UID 或稳定 `question_id` 会被跳过。

**请求体：**
```json
{ "id": "BD-20260904-a1b2c3", "uids": ["三角函数3"], "position": 0 }
```

`position` 可省略，省略时追加到板尾；成功响应为完整的 `board` 对象，另附本次实际加入的
数量 `board.added` 与实际新增的 UID 列表 `board.added_uids`。撤销只使用这份新增清单，全部已存在时列表为空；这两个字段只出现在响应，不写入 boards.json。

### `POST /api/board/items/remove`
按 UID 或 `question_id` 移除展示板条目，不影响题目本身。

**请求体：**
```json
{ "id": "BD-20260904-a1b2c3", "uids": ["三角函数3"] }
```

**响应：** `{"status":"ok","board":{...}}`。

### `POST /api/board/duplicate`
复制展示板的版面设置、备注、标记来源和现存题目引用；纸面记录不复制（新板对应新纸）。

**请求体：**
```json
{ "id": "BD-20260904-a1b2c3", "name": "月考前-副本" }
```

**响应：** `{"status":"ok","board":{...}}`。

### `POST /api/board/printed`
记录纸面（「标记为已打印」）。`layout` 是浏览器导出模板实测的版面
（`window.OMRS_LAYOUT`），包含 `pages / cursor / items[].segments / answer_pages` 及本次排版实际
采用的 `print` 快照（至少含 `note_ratio / gap_lines`）。`mode:"all"` 记录时优先采用该快照，
旧导出件缺少它时回退当前板 `print`；`mode:"new"` 追加题目时保留原 `printed.print`，不会用
本次增量布局覆盖原纸比例。每题正文指纹优先使用 `layout.items[].hash`（导出时的内容），缺失时兼容回退记录时正文，用于之后提示「已改动」。

`layout.board_id` 或 `layout.mode` 存在时必须分别与请求的 `id / mode` 相符；不符返回 400，且不修改纸面或历史记录。缺少这些字段的旧导出件仍可记录。
服务端同时校验每个题目引用能解析且 `question_id / uid` 一致，并要求题目属于当前展示板或既有纸面记录；未知题、别板题和越界页码返回 400。`mode:"new"` 必须已有纸面记录，`pages`、`cursor.page`、题目段页码和答案页码彼此一致。导出后移出展示板的旧整板快照仍可记录，用于保留实际纸面占位。

**请求体：**
```json
{
  "id": "BD-20260904-a1b2c3",
  "mode": "new",
  "layout": {
    "pages": 3,
    "cursor": { "page": 3, "y": 493.56 },
    "print": { "note_ratio": 0.50, "gap_lines": 2 },
    "answer_pages": [],
    "items": [{ "question_id": "OP-000123", "uid": "三角函数1",
                "segments": [{ "page": 3, "top": 300.2, "height": 125.7 }] }]
  }
}
```

`mode:"all"` 用这份版面替换整个纸面记录，并保存 `layout.print`（缺失时兼容回退当前板设置）；
`mode:"new"` 把新题追加进原记录并推进 `pages` / `cursor`，保留原 `printed.print` 几何快照。
**响应：** `{"status":"ok","board":{...}}`。

记录与重置都会先把**即将被替换掉**的纸面记录的摘要追加进
`错题/.omrs/boards_printed_history.jsonl`（只增不改，见 `AI/data/storage.md` §4.4）。
该摘要没有逐题占位与指纹，不能用于直接恢复完整纸面。
这份历史**目前没有对外端点**，只能直接读文件或在 Python 里调 `read_printed_history()`。

### `POST /api/board/printed/reset`
清空纸面记录。**请求体：** `{ "id": "BD-20260904-a1b2c3" }`；响应同上。

### `POST /api/board/folder/create`
新建展示板文件夹。**请求体：** `{ "name": "高三上·期中" }`。名称折叠连续空白并截断到 60 字，
为空时返回 400。**响应：** `{"status":"ok","folder":{...}}`，新文件夹排在最后。

### `POST /api/board/folder/update`
重命名文件夹或调整它在列表中的位置。

**请求体：** `{ "id": "BF-20260907-a1b2c3", "name": "期中复习", "order": 0 }`

两个字段都可选。给 `order` 时把该文件夹移到这个位置，其余文件夹顺序连带重排并重新编号；
超出范围的 `order` 收敛到首尾。文件夹不存在时返回 400。

### `POST /api/board/folder/delete`
删除文件夹。**请求体：** `{ "id": "BF-…", "keep_boards": true }`。

`keep_boards` 默认 `true`，组内的板移到未归档，板和纸面记录都保留；显式传 `false` 才连同板一起
删除。**响应：** `{"status":"ok","deleted":true,"boards_kept":N,"boards_deleted":M}`。

### `POST /api/board/move`
把板移到某个文件夹，或调整它在组内的位置。

**请求体：** `{ "id": "BD-…", "folder_id": "BF-…", "index": 0 }`

`folder_id` 为空串表示未归档，指向不存在的文件夹时同样落到未归档（静默，不报错）。`index`
可选，缺省时排到该组末尾，超出范围时收敛到组尾。**响应：** `{"status":"ok","board":{...}}`。

### `POST /api/board/delete`
删除展示板记录，不删除题目、标记或 Ledger 数据。

**请求体：**
```json
{ "id": "BD-20260904-a1b2c3" }
```

成功响应为 `{"status":"ok","deleted":true}`；展示板不存在时返回
`{"status":"error","deleted":false}`。板数据的原子写入与备份规则见 `AI/board.md`
和 `AI/data.md`。

---

### `POST /api/report/create`
托管一份 AI 分析报告（纯 HTML）。

**请求体：**
```json
{ "name": "6月薄弱点分析", "html": "<!doctype html>..." }
```

前端从用户上传的 `.html` 文件用 `FileReader.readAsText` 读出文本后以 JSON 提交（无需 multipart）。后端写入 `错题/report/<id>.html`，并在 `错题/report/index.json` 追加元数据。

**响应：** `{ "status": "ok", "id", "name", "filename", "created_at", "size" }`（`created_at` 由后端记录）。

### `POST /api/report/delete`
删除指定报告（文件 + 索引条目）。

**请求体：** `{ "id": "RPT-..." }`


---


### 稳定题目引用

批量标签与导出可提交 `question_refs:[{question_id}]`；兼容 `uids`。单题选择支持 `{question_id,source}`。已持久化 Session 按绑定身份解析当前位置；未绑定或已归档条目必须先在详情处理再导出，不能因 UID 重用导出另一道题。
