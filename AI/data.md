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

**注意：** `Last_Review` 历史数据可能包含 `YYYY/M/D` 格式，`parse_date()` 已做兼容。
**注意：** SM-2 字段（`Interval`、`Due_Date`、`Repetition`）为 2026-05 新增，旧数据通过 `resolve_sm2_fields()` 自动填充默认值。
**写盘安全：** 该文件经 `save_csv(..., backup=True)` 写入——先写 `.tmp` 并 `fsync`，再 `os.replace` 原子覆盖，避免写一半损坏；覆盖前滚动备份为 `mastery_data.csv.bak.1/2/3`（`.1` 最新，保留 3 份）。反馈与重建索引均走此路径。

---

## 3. history_log.csv（兼容投影）

路径：`错题/.omrs/history_log.csv`

**写入方式：** v1.1.0 后由 `rebuild_projection()` 从 Ledger 导出。新增反馈先写 `review.batch_submit` commit，再重建该兼容表。该文件仍供旧表格、导出和调试查看使用。

| 字段 | 类型 | 说明 |
|---|---|---|
| `Log_ID` | string | `LOG-YYYYMMDD-NNN` |
| `UID` | string | 题目 UID |
| `Date` | string | `YYYY-MM-DD HH:MM` |
| `Action` | string | 目前固定为 `Feedback` |
| `Sub_Score` | int | 主观分 0–10 |
| `Is_Correct` | 0/1 | 是否答对 |
| `Session_ID` | string | 所属 Session ID |
| `Note` | string | 备注（可为空） |

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
- `snapshots`：重放缓存。

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
  - 二倍角公式
  - 辅助角公式
tags:
  - 状态/待攻克
  - 知识点/三角函数
---

# 题目

题目内容……

# 历史

<!-- 该区域不再作为算法事实源；网页时间线读取 Ledger。 -->
```

> **录入说明**：`POST /api/create` 除建骨架外，可直接写入 `# 题目`、`# 答案`、以及 `# 备注` 的 `## 错因`（由 `cause` 字段写入，导出会带上；`## 关联` 子标题保留）；YAML 可含可选 `页码` 字段。题目图存为 `错题/附件/<uid>-q-N.<ext>` 并嵌入 `# 题目`，答案图存为 `<uid>-a-N.<ext>` 并嵌入 `# 答案`。「AI 自动识别」分两步：`classify` 读题目图回填科目/分类/难度/相关知识点（不抄题；知识点可与分类重叠），`answer` 读答案图把答案提取为文本——最终以文件实际内容为准。

> **LaTeX 公式（导出 HTML）**：题目/答案/错因中的 `$...$`（行内）与 `$$...$$`（行间）会在 HTML 导出里由内联 KaTeX 渲染；A4 与屏幕版导出都会把 KaTeX CSS/JS/字体嵌入单个 HTML 文件，离线打开仍可显示公式。若 KaTeX 资源缺失或个别公式解析失败，会安全降级为原始公式文本。Obsidian 内仍按其自身 LaTeX 渲染显示。注：旧 docx 导出曾用 `_latex_to_omml` 转 Word 原生公式（OMML），已随 docx 一并移除。

### 历史记录格式（兼容）
```
YYYY-MM-DD 主观:N, 对/错[, 备注:文字]
```

v1.1.0 后 Markdown `# 历史` 不再作为算法输入。系统只承诺恢复结构化状态、算法状态、Session 和统计，不承诺恢复 Markdown 正文旧版本。

### 标签约定

| 标签 | 含义 |
|---|---|
| `状态/待攻克` | 尚未掌握，正在复习 |
| `状态/已击杀` | 高分答对，视为掌握 |
| `标签/易错坑` | 曾高分但答错（粗心/陷阱） |

---

## 6. 重建索引行为（`build_index()`）

- 扫描所有以数字结尾的 `.md` 文件。
- 已有记录：同步 `Subject`、`Category`、`Difficulty`、`Current_Tag`、`Knowledge_Tags`，保留 `Mastery`、`EF`、`Attempts` 等学习数据。
- 新增记录：初始化 `Mastery=0.0`、`EF=2.5`、`Attempts=0`、`High_Correct_Streak=0`。

---

## 7. 日志文件

路径：`错题/logs/omrs_YYYY-MM-DD.log`（位于 vault 本级目录内）

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
| `tuning` | object | 算法可调参数覆盖，键与默认值见 algorithm.md §10；仅接受已知键且为数字 |
| `ai_base_url` | string | AI 接口基础地址（OpenAI 兼容，如 `https://api.openai.com/v1`） |
| `ai_api_key` | string | AI 接口密钥（Bearer），仅存本机 |
| `ai_model` | string | AI 模型名（需支持图片输入，如 `gpt-4o`） |
| `ai_restrict_tags` | bool | 「AI 自动识别」是否把相关知识点限定在「已有分类 ∪ 已有知识点」内。默认 `true`（缺失按 `true`）；`false` 时允许 AI 在无贴切已有项时新建知识点（上限 4 个） |

`load_tuning()` 带进程内缓存，`save_config()` 写入后自动失效缓存；UI 改配置后会重启，亦保证生效。  
`ai_*`/`ai_restrict_tags` 供「AI 自动识别」（见 api.md `/api/ai-recognize`）使用：由 `load_config()` 每次读盘，**保存即生效、无需重启**；`save_config()` 按键合并，可单独提交。`load_config()` 的缺省键集中在 `common.CONFIG_DEFAULTS`（`allow_external=false`、`ai_restrict_tags=true`）。

---

## 9. report/（AI 分析报告托管）

> 对应源文件：`omrs/reports.py`

| 路径 | 说明 |
|---|---|
| `错题/report/<id>.html` | 单份报告的纯 HTML 文件 |
| `错题/report/index.json` | 报告索引数组：`[{id, name, filename, created_at, size}]` |

- `id` 形如 `RPT-YYYYMMDDHHMMSS`（同秒冲突加 `-N`）。`created_at` 由后端在创建时记录。
- 报告由 `GET /api/report/view?id=` 同源提供（`text/html`），因此报告内可直接用 `<img src="/api/image?name=<URL编码文件名>">` 引用题目图片——这是「报告引用题目图片」的对接方式。
- 题目图片文件名可从 `/api/question?uid=` 的 `images`、`/api/stats` 与 `/api/analytics` 的 items `images` 字段，或导出复盘报告 JSON 中获得（均由 `extract_images()` 从题面 `![[名]]`/`![](路径)` 解析，取 basename）。

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

仅包含**已判定**的题。导入侧（`schedule.js::importFeedbackJson`）：`is_correct` / `correct` 经 `looseBool` 宽松解析（true/1/"对"…），`sub_score` / `score` 缺省按对→10 / 错→4、钳 0–10 取整；`session_id` 在 sessions.csv 中则自动选中关联，否则仍按该 ID 写入 history_log（TMP- 临时卷亦可），为空按手动录入。填充后不自动提交，须人工核对。若误贴旧题目 JSON，会提示当前只支持反馈 JSON。
