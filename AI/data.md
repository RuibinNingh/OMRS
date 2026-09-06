# 数据结构

> 对应源文件：`omrs/common.py`、`omrs/indexing.py`

> v1.1.0 起，结构化状态的唯一可信来源是 `错题/.omrs/ledger.db`。本文件中的 CSV 仍会由投影器导出，用于兼容既有前端、调试查看和旧数据迁移；不要再把 CSV 当成核心运行时事实源。详见 `ledger.md`。

---

## 1. UID 规则

- UID = Markdown 文件名（不含 `.md`）。
- 文件名必须以数字结尾，例：`三角函数1.md`、`工业流程题3.md`。
- UID 在整个题库中必须唯一，`scan_vault()` 检测冲突并抛出错误。
- 可以通过网页迁移或文件管理器改名；系统依靠 Markdown YAML 的 `_omrs_id` 识别同一道题，历史反馈引用隐藏 `question_id`，不会只靠 UID 关联。

---

## 2. mastery_data.csv（兼容投影）

路径：`错题/.omrs/mastery_data.csv`

| 字段 | 类型 | 说明 |
|---|---|---|
| `UID` | string | 题目唯一标识 |
| `File_Path` | string | 相对于 vault 根目录的路径 |
| `Subject` | string | 科目（如 数学、化学） |
| `Category` | string | 分类（如 三角函数） |
| `Difficulty` | int(1–10) | 难度，重建索引时从 Markdown 同步 |
| `Mastery` | float(0–1) | 当前熟练度 |
| `EF` | float(1.3–3.0) | 易错因子（SM-2 变体） |
| `Attempts` | int | 累计练习次数 |
| `High_Correct_Streak` | int | 连续高分答对次数，达到 2 次才自动击杀 |
| `Last_Review` | date | 最后复习日期（ISO 格式 YYYY-MM-DD） |
| `Interval` | int | SM-2 当前间隔（天数），旧数据默认为 0 |
| `Due_Date` | date | SM-2 下次到期日，旧数据默认为 Last_Review（即立即到期） |
| `Repetition` | int | SM-2 连续答对次数（n），答错重置为 0 |
| `Current_Tag` | string | 状态标签（如 #状态/待攻克） |
| `Entry_Date` | date | 题目录入日期 |
| `Knowledge_Tags` | string | 知识点标签，`|` 分隔 |
| `Labels` | string | 用户标记名称，`|` 分隔；旧 CSV 缺列时按空处理 |
| `Suspended` | 0/1 | 题目停用标记；`1` 时保留题目行供管理/筛选，但不参与调度、统计、分析、反馈或复习导出；没有该列的旧 CSV 按 `0` 处理 |

**注意：** `Last_Review` 历史数据可能包含 `YYYY/M/D` 格式，`parse_date()` 已做兼容。
**注意：** SM-2 字段（`Interval`、`Due_Date`、`Repetition`）为 2026-05 新增，旧数据通过 `resolve_sm2_fields()` 自动填充默认值。
**写盘安全：** 该文件经 `save_csv(..., backup=True)` 写入——先写 `.tmp` 并 `fsync`，再 `os.replace` 原子覆盖，避免写一半损坏；覆盖前滚动备份为 `mastery_data.csv.bak.1/2/3`（`.1` 最新，保留 3 份）。反馈与重建索引均走此路径。

---

## 3. history_log.csv（兼容投影）

路径：`错题/.omrs/history_log.csv`

**写入方式：** v1.1.0 后由 `rebuild_projection()` 从 Ledger 导出。新增反馈先写 `review.batch_submit` commit，再重建该兼容表。该文件仍供旧表格、导出和调试查看使用。

| 字段 | 类型 | 说明 |
|---|---|---|
| `Log_ID` | string | Ledger 新反馈为 `{commit_id}-{index:03d}`，如 `CMT-000002-001`；`legacy.bootstrap` 导入的旧历史行可能保留原有值 |
| `UID` | string | 题目 UID |
| `Date` | string | `YYYY-MM-DD HH:MM` |
| `Action` | string | 目前固定为 `Feedback` |
| `Sub_Score` | int | 主观分 0–10 |
| `Is_Correct` | 0/1 | 是否答对 |
| `Session_ID` | string | 所属 Session ID |
| `Note` | string | 备注（可为空） |
| `Question_ID` | string | 稳定题目身份；新反馈与重建后的 legacy 历史均写入，用于题目改名/迁移后的分析归属 |

---

## 4. sessions.csv（兼容投影）

路径：`错题/.omrs/sessions.csv`

| 字段 | 类型 | 说明 |
|---|---|---|
| `Session_ID` | string | `EXP-YYYYMMDDHHmmss`（含冲突后缀 A-Z） |
| `Created_At` | string | 创建时间 |
| `Subject_Filter` | string | 科目筛选条件（空=全科） |
| `Count` | int | 题目数量 |
| `UIDs` | JSON | 题目列表，新格式为 `[{"uid":"...","source":"due|proficiency"}]`，兼容旧格式 `["uid1","uid2"]` |
| `Status` | string | `active` 或 `completed` |
| `Completed_At` | string | 完成时间（可为空） |

临时调度（`TMP-` 前缀）**不写入**此文件。
**注意：** `UIDs` 新格式中 `source` 字段标记题目来源（`due`=到期列表，`proficiency`=熟练度列表），用于反馈时区分 SM-2 排期策略。

---

## 4.1 ledger.db

路径：`错题/.omrs/ledger.db`

核心表：

- `commits`：不可变提交链。
- `question_projection` / `question_knowledge_points`：题目结构化投影。
- `mastery_projection`：熟练度、EF、SM-2 排期投影。
- `session_projection`：Session 投影。
- `workspace_fingerprint`：Markdown 工作区自检指纹。
- `snapshots`：预留的持久化快照表；当前投影器尚未读写此表。`_project_state()` 只在单次重放过程中维护内存快照，`rebuild_projection()` 仍从完整提交链重放。

旧 CSV 可删除并从 Ledger 重建；Ledger 不应删除。

---

## 5. Markdown 题目格式

```markdown
---
_omrs_id: OP-000001
科目: 数学
分类: [[三角函数]]
难度: 7
页码:
相关知识点:
  - "[[二倍角公式]]"
  - "[[辅助角公式]]"
标记:
  - 考前必看
  - 计算失误
tags:
  - 状态/待攻克
录入日期: 2026-06-12
---

# 题目

题目内容……

# 备注

## 错因

## 关联

# 答案

答案/解析……

# 历史

<!-- 该区域不再作为算法事实源；网页时间线读取 Ledger。 -->
```

> **录入说明**：`POST /api/create` 除建骨架外，可直接写入 `# 题目`、`# 答案`、以及 `# 备注` 的 `## 错因`（由 `cause` 字段写入，导出会带上；`## 关联` 子标题保留）；YAML 可含可选 `页码` 字段。题目图存为 `错题/附件/<uid>-<omrs_id 短后缀>-q-N.<ext>`（如 `力学1-0135-q-1.png`）并嵌入 `# 题目`，答案图存为 `<uid>-<omrs_id 短后缀>-a-N.<ext>` 并嵌入 `# 答案`（短后缀避免迁移后附件覆盖）。「AI 自动识别」支持三种用途：`classify` 读题目图只回填科目/分类/难度/相关知识点（不抄题；知识点可与分类重叠），`question_text` 读题目图把题目正文提取为文本，`answer` 忠实转录答案图内全部可见答案、解析、推导与步骤——最终以文件实际内容为准。

> **LaTeX 公式（导出 HTML）**：题目/答案/错因中的 `$...$`（行内）与 `$$...$$`（行间）会在 HTML 导出里由内联 KaTeX 渲染；A4 与屏幕版导出都会把 KaTeX CSS/JS/字体嵌入单个 HTML 文件，离线打开仍可显示公式。若 KaTeX 资源缺失或个别公式解析失败，会安全降级为原始公式文本。Obsidian 内仍按其自身 LaTeX 渲染显示。注：旧 docx 导出曾用 `_latex_to_omml` 转 Word 原生公式（OMML），已随 docx 一并移除。

> **Markdown 表格支持子集**：题目或答案可写“表头行 + `---` 分隔行 + 数据行”的管道表格，单元格内的竖线写为 `\|`。主程序预览、A4 和屏幕版会渲染为真实 `<table>`，公式仍走 KaTeX；主程序预览也能渲染备注中的表格，但当前导出只把题目和答案送入结构化表格解析。缺单元格补空，超出表头的单元格忽略，对齐冒号当前不保留语义；A4 导出时可通过 `a4_two_columns=false` 让整份文件使用单栏，前端会在导出前确认栏模式。

### 历史记录格式（兼容）
```
YYYY-MM-DD 主观:N, 对/错[, 备注:文字]
```

v1.1.0 后 Markdown `# 历史` 不再作为算法输入，也不会由反馈流程追加。`/api/question` 仍返回该小节原文，`common.py::parse_history_lines()` 和 v1.16.0 题目详情/画廊代码仍会兼容解析旧手工行；这与 Ledger 导出的正式复习记录是两套数据。系统只承诺恢复结构化状态、算法状态、Session 和统计，不承诺恢复 Markdown 正文旧版本。

`相关知识点: []` 是显式清空知识点标签的结构化更新。工作区扫描将该空列表写入 Ledger 的题目元数据投影，并在重建 `mastery_data.csv` 时保持 `Knowledge_Tags` 为空；它不会回退到该题此前的知识点标签。

### 标签约定

| 标签 | 含义 |
|---|---|
| `状态/待攻克` | 尚未掌握，正在复习 |
| `状态/已击杀` | 高分答对，视为掌握 |
| `标签/易错坑` | 曾高分但答错（粗心/陷阱） |

`tags` 中的状态和知识点兼容旧题格式；v1.14.0 的用户自定义横切标记单独使用
顶层 YAML 列表 `标记:`，不要把它写回 `tags`。`标记: []` 是显式清空，
标记名称按出现顺序去重，名称本身不保存 `labels.json` 的内部 id。

---

## 6. 重建索引行为（`build_index()`）

`build_index()` 当前不是直接把 CSV 当作事实源保留字段，而是按以下顺序执行：

1. 确保 Ledger 已完成迁移引导（`ensure_ledger_bootstrap()`）。
2. 扫描工作区并记录新增、移动、元数据变化或消失（`scan_workspace()`）；发现冲突时中止。
3. 从完整 Ledger 重放并重建题目、熟练度、Session 和兼容 CSV 投影（`rebuild_projection()`）。
4. 读取重建后的 `mastery_data.csv` 返回题目行，并写入 `INDEX` 运行日志。

扫描对象仍是所有以数字结尾的 `.md` 文件；Markdown 元数据同步到 Ledger/题目投影，Mastery、EF、Attempts 等学习状态由 Ledger 重放，不由旧 CSV 覆盖。

---

## 7. 日志文件

路径：`<vault>/logs/omrs_YYYY-MM-DD.log`（位于 vault 根目录下的 `logs/`；标准启动 `python omrs_engine.py serve` 时 vault=仓库根目录，即 `logs/omrs_YYYY-MM-DD.log`）

每日一个文件，记录以下事件：

| 事件类型 | 触发时机 |
|---|---|
| `FEEDBACK` | 每条反馈处理后 |
| `SCHEDULE` | 每次调度执行后 |
| `INDEX` | 每次重建索引后 |

### optimization_log.jsonl

路径：`错题/.omrs/optimization_log.jsonl`

设置页“优化”块的审计日志，一行一个 JSON：`quick_scan`、`compress`、`backup.export`、`backup.import.prepare`、`backup.restore`。记录时间、文件数、字节数、任务 ID、跳过原因和错误摘要。该文件属于活跃 `.omrs` 数据，会计入设置页“数据链”大小；用户导出的备份 zip 不保存在数据目录中。

---

## 8. config.json

路径：`错题/.omrs/config.json`

| 键 | 类型 | 说明 |
|---|---|---|
| `allow_external` | bool | 是否绑定 0.0.0.0（见 frontend.md 设置页） |
| `tuning` | object | 算法可调参数覆盖，键与默认值见 algorithm.md §9；仅接受已知键且为数字 |
| `ai_base_url` | string | AI 接口基础地址（OpenAI 兼容，如 `https://api.openai.com/v1`） |
| `ai_api_key` | string | AI 接口密钥（Bearer），仅存本机 |
| `ai_model` | string | 默认 AI 模型名；需支持图片输入，如 `gpt-4o` |
| `ai_model_detect` | string | 收件箱框选模型；为空回退 `ai_model` |
| `ai_model_extract` | string | 收件箱转文本模型；为空回退 `ai_model` |
| `ai_model_classify` | string | 收件箱分类模型；为空回退 `ai_model` |
| `ai_restrict_tags` | bool | 「AI 自动识别」是否把相关知识点限定在「已有分类 ∪ 已有知识点」内。默认 `true`（缺失按 `true`）；`false` 时允许 AI 在无贴切已有项时新建知识点（上限 4 个） |
| `inbox_detect_provider` | string | 框选提供方：`vlm` / `template` / `local_http`，默认 `vlm` |
| `inbox_local_detect_url` | string | `local_http` 的 POST 地址，默认空 |
| `inbox_blind_every` | int | 每 N 张盲标，`0` 关闭，默认 `0` |
| `inbox_auto_ready_conf` | number | 自动转文本并置就绪的最低置信度，`0` 关闭，默认 `0` |
| `inbox_auto_on_upload` | bool | 上传后自动排队处理，默认 `false` |
| `inbox_discard_keep_days` | int | 丢弃原图保留天数，默认 `7` |

`load_tuning()` 带进程内缓存，`save_config()` 写入后自动失效缓存；算法调参、AI 和收件箱策略保存即生效，无需重启。只有 `allow_external` 改变监听地址时需要重启。`save_config()` 按键合并，可单独提交；`load_config()` 的缺省键集中在 `common.CONFIG_DEFAULTS`。

---

## 9. report/（AI 分析报告托管）

> 对应源文件：`omrs/reports.py`

| 路径 | 说明 |
|---|---|
| `错题/report/<id>.html` | 单份报告的纯 HTML 文件 |
| `错题/report/index.json` | 报告索引数组：`[{id, name, filename, created_at, size}]` |

- `id` 形如 `RPT-YYYYMMDDHHMMSS`（同秒冲突加 `-N`）。`created_at` 由后端在创建时记录。
- 报告由 `GET /api/report/view?id=` 同源提供（`text/html`），因此报告内可直接用 `<img src="/api/image?name=<URL编码文件名>">` 引用题目图片——这是「报告引用题目图片」的对接方式。
- 题目图片文件名可从 `/api/question?uid=` 的 `images`、`/api/analytics` 的 `items[].images`，或导出复盘报告 JSON 中获得（均由 `extract_images()` 从题面 `![[名]]`/`![](路径)` 解析，取 basename）；`/api/stats` 的 `items` 不含 `images`。
- 报告页下载 AI 分析材料时，可选择不带图片的单个 Markdown，或包含 Markdown + `images/` 的 ZIP。ZIP 只收录 `items[].images` 引用且仍存在的题面图片，不包含未引用附件；其中图片只供 AI 阅读，生成的托管 HTML 仍按上一条 `/api/image?name=` 规则引用。

---

## 10. File_Path 分隔符注意

历史数据的 `File_Path` 可能含 **Windows 反斜杠**（如 `错题\数学\xx.md`，数据在 Windows 上录入）。读取题目文件时需归一化：`get_question_content()` 与 `analytics._question_images()` 已做 `replace("\\","/")` 后再 `os.path.join`，保证 Linux/Windows 都能命中。新增读 md 的代码也应照此处理。

## 11. JSON 交换格式（屏幕版 / 外部 AI 反馈回传）

当前只保留**反馈 JSON** 这一种外部导入格式（不落盘、不进 CSV，仅在导入框/剪贴板流转）。题目录入页不再提供外部 AI 题目 JSON 队列导入；录题仍走表单、图片粘贴和内置 AI 识别。

**反馈 JSON** 可由屏幕版「复制作答 JSON」生成，也可由反馈页「复制 AI 反馈提示词」交给外部 AI 按批改结果整理后生成。解析经 `core.js::parseLooseJson`：容忍 ```` ```json ```` 围栏包裹；顶层接受完整对象、`items` / `feedbacks` 数组字段或裸数组。

```json
{"type":"omrs-feedback","version":1,"session_id":"EXP-20260610213000",
 "exported_at":"2026-06-10 21:30","total":16,"graded":12,
 "items":[{"uid":"三角函数1","is_correct":true,"sub_score":9}]}
```

仅包含**已判定**的题。导入侧（`assets/feedback.js::importFeedbackJson`）：`is_correct` / `correct` 经 `looseBool` 宽松解析（true/1/"对"…），`sub_score` / `score` 缺省按对→10 / 错→4、钳 0–10 取整；`session_id` 在 `sessions.csv` 中则自动选中关联，否则仍按该 ID 填入待提交反馈（TMP- 临时卷亦可），为空按手动录入。导入只填充前端表单，**不会直接写 `history_log.csv`**；须人工核对后提交，提交才追加 Ledger 并重建投影。若误贴旧题目 JSON，会提示当前只支持反馈 JSON。


---

## 12. 收件箱 `错题/.omrs/inbox/`（v1.12.0）

`inbox.db`（SQLite：items / regions / cards / jobs / meta；v1.13.0 items 多 `blind`、`blind_boxes` 两列，`connect()` 对旧库 ALTER 补齐）、`raw/<sha256>.<ext>`（上传原件）、`crops/`（裁剪缓存，可重建）、`annotations.jsonl`（append-only 标注事件）。区域坐标归一化 0–1。字段与状态机见 `AI/inbox.md` §2；`items.layout` 的新上传默认值为 `zuoyebang`（作业帮截图），已有记录可在处理页改选。不参与备份导出以外的任何投影；`item.commit` 事件里记录了创建出的 `uid` / `question_id` 便于回溯。

`config.json` 新增键：`ai_model_detect`、`ai_model_extract`、`ai_model_classify`（string，留空回退 `ai_model`；`CONFIG_DEFAULTS` 均为空串）。v1.13.0 再加 `inbox_detect_provider`（`vlm`）、`inbox_local_detect_url`（`""`）、`inbox_blind_every`（0）、`inbox_auto_ready_conf`（0.0）、`inbox_auto_on_upload`（false）、`inbox_discard_keep_days`（7），含义见 `AI/inbox.md` §8。丢弃项超期清理后 `items.file` 为 NULL、原图文件删除，行与 `annotations.jsonl` 事件保留。

---

## 13. 用户标记 `labels.json`（v1.14.0）

路径：`错题/.omrs/labels.json`。这是标记定义表，不是题目归属的第二份事实源：
题目真正保存的是 Markdown YAML 中可读的 `标记:` 名称。文件格式如下：

```json
{
  "version": 1,
  "labels": [{
    "id": "LB-20260904-a1b2c3",
    "name": "考前必看",
    "color": "#dc2626",
    "order": 1,
    "priority_bonus": 0.0,
    "archived": false,
    "created_at": "2026-09-04T12:00:00+00:00"
  }]
}
```

- `id` 只用于标记定义管理；题目 YAML 不引用它，方便在 Obsidian 中直接读写。
- `name` 必须唯一，不能包含换行或 `|`；`color` 规范化为 `#rrggbb`。
- `order` 控制选择器顺序；`priority_bonus` 是可选的调度加成，默认 `0.0`。
- 当前定义文件使用临时文件 + `fsync` + `os.replace` 原子写，尚未滚动 `.bak`。
- 题目标记进入 Ledger 的方式是 `question.metadata_update_external`，投影器同时
 维护 `question_labels(question_id, label)` 和 CSV 的 `Labels` 列。

---

## 14. 展示板 `boards.json`（v1.14.0）

路径：`错题/.omrs/boards.json`。展示板是呈现层引用集合，不进入 Ledger，也不
复制题目正文。文件写入会滚动 `.bak.1/2/3`，再使用临时文件、`fsync` 和
`os.replace` 原子替换。

板记录包含板元数据、打印设置和 `items[]`。每个条目同时保存
`question_id` 与 `uid`；读取优先稳定的 `question_id`，UID 只做显示和降级兜底。
`print` 当前字段为 `note_ratio`、`gap_lines`、`binding_mm`、
`answers`、`show_labels`、`show_meta`；旧的 `note_align`、`note_min_lines`、
`note_pattern` 会被忽略。`gap_lines` 默认 2，单题可以用
`extra_gap_lines` 追加 0–24 行。

停用题继续保留在板内但导出跳过；题目删除或无法按稳定身份解析时显示
`missing`，不会自动从板文件中删除。

`printed` 是**纸面记录**——纸上现在有什么：`pages`（已打印总页数）、`cursor{page,y}`
（下一道新题的续排位置）、打印时的 `print` 几何、`items[]`（每题 `question_id / uid /
hash`（正文指纹）/ `segments[{page,top,height}]`）和 `answer_pages`。`pages == 0` 表示没有
记录；由 `POST /api/board/printed` 在用户「标记为已打印」时写入，`mode:"new"` 追加、
`mode:"all"` 替换；旧字段 `last_printed_page` 读取时忽略。设计见 `board.md` §4。
备份整个 `错题/` 目录时，`labels.json`、`boards.json` 都随 `.omrs/` 一起进入备份。
