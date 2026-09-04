# 展示板

> v1.14.0 新增。对应源文件：`omrs/boards.py`、`omrs/exporting.py`、`assets/board.js`、
> `omrs/export_templates/board.css`、`omrs/export_templates/board.js`。

## 1. 定位与边界

展示板是可持久化的题目引用集合，服务于「左题右空」的纸面复习：

- 多个展示板可并存，板名和备注只在系统内使用，纸面标题固定为「错题集」；
- 板里保存题目的 `question_id` 与当前 `uid`，不是题目副本，重印即读取最新 Markdown；
- 可以添加、移除、清空、拖拽/菜单排序、复制和删除；
- 板不进入 Ledger，不参与熟练度、SM-2、统计或推荐状态；
- 停用题保留在板中并提示，但导出跳过；删除或无法解析的题显示为缺失，需用户清理。

展示板与收件箱一样是呈现/暂存层数据，不是题目与复习事实链。

## 2. 数据文件 `boards.json`

路径：`错题/.omrs/boards.json`。写入会先滚动已有文件为 `.bak.1/2/3`，然后
通过临时文件、`fsync` 和 `os.replace` 原子替换。

```json
{
  "version": 1,
  "boards": [{
    "id": "BD-20260904-a1b2c3",
    "name": "三角函数",
    "note": "月考前使用",
    "created_at": "2026-09-04T12:00:00+00:00",
    "updated_at": "2026-09-04T12:30:00+00:00",
    "source_labels": ["考前必看"],
    "print": {
      "note_ratio": 0.42,
      "gap_lines": 6,
      "binding_mm": 22,
      "binding_marks": "none",
      "answers": "none",
      "show_labels": true,
      "show_meta": true
    },
    "last_printed_page": 2,
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

### 题目引用解析

读取时优先按 `question_id` 查 `question_projection`，再按 `uid` 降级。这样题目
迁移或改名后展示板仍能命中稳定身份，并更新为当前 UID。解析后的 item 附带：
`subject`、`category`、`difficulty`、`mastery`、`due_date`、`labels`、
`suspended`、`missing` 和 `file_path`。

`print` 只有当前支持的版面字段。旧的 `note_align`、`note_min_lines`、
`note_pattern` 会被忽略，不会进入规范化结果。`gap_lines` 默认 6，单题
`extra_gap_lines` 可在 0–24 行内追加。

## 3. 展示板页面

入口是侧栏「题目库」与「目录」之间的「展示板」Tab。页面由三部分组成：

1. 左侧板列表：板名、题数、更新时间、缺失/停用数，以及重命名/复制/导出/删除菜单；
2. 中间板内容：可拖拽排序的题目行、标记芯片、元信息、单题额外留白、预览和移除；
3. 右侧版面面板：留白占比、题间距、装订边、孔位标记、答案和打印范围。

板内工具包括「添加题目」「按标记同步」「排序」「清空」。添加题目复用题库筛选
骨架，支持全文、科目、分类、状态、知识点、标记 any/all、难度、熟练度、到期和
停用状态筛选。`按标记同步` 是显式追加并去重，不会因题目后来打标而自动改变板。

常用入口统一调用 `boardQuickAdd(uid)`：题目库、题目 Modal、反馈、即时练习、
数据复盘等页面可将当前题加入最近使用的板；最近板 id 存在
`localStorage('omrs-board-last')`。

键盘快捷键：`N` 新建、`A` 添加题目、`P` 打印预览、方向键选择题目、
Ctrl/Cmd+方向键排序、Enter 打开、Delete 移除。

## 4. HTTP API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/boards` | 返回板列表，包含 `count`、`print`、`last_printed_page`、`missing`、`suspended` |
| GET | `/api/board?id=` | 返回单板及解析后的完整 `items` |
| POST | `/api/board/create` | `{name, uids?, label?}`；可按一个标记从当前题目创建 |
| POST | `/api/board/update` | `{id, name?, note?, print?, items?, source_labels?, last_printed_page?}`；`items` 是整体覆盖 |
| POST | `/api/board/items/add` | `{id, uids:[], position?}`；按稳定身份去重 |
| POST | `/api/board/items/remove` | `{id, uids:[]}` |
| POST | `/api/board/duplicate` | `{id, name}`；复制有效题目引用并清零打印高水位 |
| POST | `/api/board/delete` | `{id}`；只删除展示板，不删除题目 |
| POST | `/api/export` | `{format:"board", board_id, page_start?, page_end?, include_answers?, overrides?}` |

导出接口返回内嵌 `OMRS_DATA` 的自包含 HTML。停用或缺失题不会进入导出数据，
但不会静默从 `boards.json` 删除。

## 5. 板面打印模型

固定 A4 纵向页面为 `793.7 × 1122.52px`（96dpi 近似），默认几何：

- 左装订边 22mm（约 83.1px），右边距 10mm，上下边距 12mm；
- `note_ratio` 在 0.30–0.55 之间，默认 0.42；左栏为题面；
- 题间距以行计，默认 6 行，每行 18px；单题可额外增加 0–24 行；
- 右侧整栏保持原生空白，不生成边框、底纹、线条或笔记 DOM；
- 页眉每页只有「错题集」，页脚只有当前板内绝对页码，不显示总页数；
- 题头保持单行，序号和 UID 不截断，标记区域溢出时隐藏并以 CSS 省略；
- 正文、表格和图片不截断，放不下时移动到下一页；长图采用切片。

答案默认不含。`answers:"append"` 或导出时 `include_answers:true` 会把所有答案
按题号排在末页附页，仍不占用题目右侧空白。

### 打印范围与高水位

板记录 `last_printed_page`。页面默认选择「第 `last_printed_page + 1` 页起」，
也可以选择全部或自定义范围。浏览器先对整板分页，再裁出请求页，因此只导出
第 3–4 页时，纸面页码仍然是 3、4。确认打印后由预览窗口向主页面发送消息，
主页面用 `POST /api/board/update` 推进高水位。

新增题最好追加在板尾。插入中间或整体重排可能改变后续页码，前端会提示建议
重打受影响的后续页面；系统不会静默修正已打印纸张。

### 装订辅助

`binding_marks` 支持：

- `none`：默认关闭；
- `3hole`：左装订边内绘制 3 个浅灰孔位圆圈；
- `26hole`：左装订边内绘制 26 个浅灰孔位圆圈。

孔位只用于对齐打孔机，不影响题面列宽。

## 6. 维护边界

- 展示板不写 Ledger，结构化恢复不能从 Ledger 还原板；`boards.json` 会随 `错题/`
  目录备份。
- 题目 Markdown、标签和学习状态仍由各自原有链路维护；展示板只读取它们。
- `board.css` / `board.js` 是独立导出模板，修改几何、页码、切片或答案附页时必须
  同步 `AI/export.md` 和 `tests/test_board_export.py`。
