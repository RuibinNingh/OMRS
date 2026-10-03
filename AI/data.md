# 数据结构

> **速查**
> - 职责：稳定题目身份、SQL 读模型、按需 CSV、Markdown 与活动配置；独立存储见分册
> - 入口：`omrs/data_repository.py`、`omrs/config_repository.py`、`omrs/common.py`、`omrs/indexing.py`
> - 不变量：题目结构化元数据、复习状态与 Session 以 `ledger.db` 为事实源，CSV 只作按需导出与首次迁移输入；展示板、助手、草稿、收件箱、标注集和运行记录各有独立存储
> - 必跑测试：`tests/test_history_projection.py`、`tests/test_question_records.py`、`tests/test_content_integrity.py`、`tests/test_data_runtime.py`
> - 相关：`AI/ledger.md`、`AI/security.md`、`AI/mcp-storage.md`

> 对应源文件：`omrs/common.py`、`omrs/indexing.py`

> 题目结构化元数据、反馈、熟练度与 Session 的可信来源是 `错题/.omrs/ledger.db`；运行时通过 `data_repository` 查询 SQL，CSV 只在显式导出或备份时流式写出，启动、扫描和普通反馈不生成。无 Ledger 提交的迁移输入可读取旧 CSV；正式运行不依赖镜像。Markdown 是题目正文的工作文件，已入账版本保存在 Ledger 的 `blobs` 表。展示板、助手对话、草稿、收件箱和标注集使用各自的文件或数据库，不由 Ledger 重放；存储路径见 `AI/data/storage.md`，Ledger 边界见 `AI/ledger.md`。

Vault根的`.omrs-maintenance/`保存生命周期锁、世代、恢复预检与journal，独立于可交换的`错题/`；Git与`错题/`一起忽略该维护目录，防止把暂存的个人数据或恢复材料纳入源码提交。备份与恢复边界见`AI/backup.md`。

锁屏入口的 WebGL 场景只读取静态资源，不读取或写入 Vault、Ledger、配置和题目文件；PIN 会话仍由 `auth.json` 与进程内存会话管理，入口本身不产生持久化数据。

---

## 1. UID 规则

科目与分类保存在 `错题/<科目>/<分类>/` 目录中；`<科目>/<科目>.md` 是科目索引，`<分类>/<分类>.md` 是分类锚点。零题分类也使用这套目录与锚点，不创建假题或平行分类数据库。统一词表将有效锚点与已有题目投影合并，按科目隔离同名分类。

- UID = Markdown 文件名（不含 `.md`）。
- 文件名必须以数字结尾，例：`三角函数1.md`、`工业流程题3.md`。
- UID 与文件路径只在活动题目中唯一；归档行保留原身份，允许新活动题复用显示编号。`question_id` 永久关联原题，混传编号和身份不一致时返回 409。
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
| `Kill_Count` | int | 累计击杀次数；答错降级时不重置，复燃休眠时长据此分级变长（algorithm.md §11） |
| `Current_Tag` | string | 状态标签（如 #状态/待攻克） |
| `Entry_Date` | date | 题目录入日期 |
| `Knowledge_Tags` | string | 知识点标签，`|` 分隔 |
| `Labels` | string | 用户标记名称，`|` 分隔；旧 CSV 缺列时按空处理 |
| `Suspended` | 0/1 | 题目停用标记；`1` 时保留题目行供管理/筛选，但不参与调度、统计、分析、反馈或复习导出；没有该列的旧 CSV 按 `0` 处理 |

**注意：** `Last_Review` 历史数据可能包含 `YYYY/M/D` 格式，`parse_date()` 已做兼容。
**注意：** SM-2 字段（`Interval`、`Due_Date`、`Repetition`）为 2026-05 新增，旧数据通过 `resolve_sm2_fields()` 自动填充默认值。
**注意：** 老 CSV 缺 `Kill_Count` 列按 `0` 处理（即「还没击杀过」），重放不会报错，首次击杀即第 1 次。
**写盘安全：** 该文件经 `save_csv(..., backup=True)` 写入——先写 `.tmp` 并 `fsync`，再 `os.replace` 原子覆盖，避免写一半损坏；覆盖前滚动备份为 `mastery_data.csv.bak.1/2/3`（`.1` 最新，保留 3 份）。仅显式导出/备份生成该兼容文件；普通反馈增量更新SQL，不逐次改写CSV。旧库首次 Ledger 迁移只在原题已有 `页码` 时保留其值；无页码题不补空字段。反馈 `Note`、草稿 note、图片说明及附件有各自语义，迁移页码时不清理。

---

## 3. history_log.csv（兼容投影）

路径：`错题/.omrs/history_log.csv`

**写入方式：** 新增反馈先写 `review.batch_submit`，普通追加增量更新 SQL 的 `history_projection`。显式 `export_legacy_csv()` 才写此兼容文件；统计、推荐、Session 和正式记录均读 SQL。

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
**注意：** `UIDs` 是 Session 绑定条目的兼容 JSON；每项含 `entry_id`、`question_id`、`uid_at_creation`、`uid` 和 `source`。`source` 字段标记题目来源（`due`=到期列表，`proficiency`=熟练度列表），用于反馈时区分 SM-2 排期策略。

复习调度工作台提交 `POST /api/confirm-schedule` 时传 `persist:true`，所以单题选择也写入 Ledger 并生成正式 `EXP-` Session；旧客户端省略该字段时仍按单题 TMP 兼容路径处理。正式 Session 的选择在写入前去重，并拒绝无效身份、非法来源、停用题和 active Session 重复占用。

Session 中的 `source` 贯穿反馈处理：`due` 使用常规 SM-2 间隔，`proficiency` 的答对间隔按 0.7 系数折中；分批反馈只更新已提交题目，`pending_uids` 是权威 `entries` 的兼容派生。条目按稳定身份计算 `feedback_submitted`，移动后用当前 UID 展示；归档保留原绑定，停用不列入待反馈，无法证明旧身份的条目标为 `unresolved`。这类条目须经 `/api/session/bind` 人工指定并追加 `session.items_bind`；禁止从当前 UID 静默推断。有效条目全部提交后状态变为 `completed`。

---

## 4.1 ledger.db

路径：`错题/.omrs/ledger.db`

核心表：

- `commits`：不可变提交链。
- `question_projection` / `question_knowledge_points`：题目结构化投影；`question_projection.created_at` 是可空的 Ledger 创建时间。首次 `question.create` / `question.create_external` 写入提交的 UTC 时间；移动、结构化修改、停用与恢复沿用原值；`legacy.bootstrap` 题为空。旧库启动时由 `ledger.init_db()` 自动补列。
- `mastery_projection`：熟练度、EF、SM-2 排期投影，含 `kill_count` 累计击杀次数（老库缺列时 `ledger.py` 用 `ALTER TABLE ... DEFAULT 0` 补列）。
- `session_projection`：Session 稳定绑定条目投影。
- `history_projection`：有效反馈的 SQL 行，按 `question_id`、Session、业务日期建立索引；保留原 `recorded_at` 和业务 `review_date`。
- `active_config`：完整活动配置、revision、mirror_hash、mirror_pending 及上次镜像哈希。
- `projection_meta`：已发布 seq、head hash、policy hash 和 projector version。
- `projection_review_corrections` / `projection_session_corrections`：当前有效分支的 SQL 修正索引，不在进程内累积全量修正载荷。
- `workspace_fingerprint`：Markdown 工作区自检指纹。
- `blobs`：已入账题目 Markdown 全文（`hash` = 正文 sha256，`content`，`created_at`）；当前缺失版本可在启动时经身份和哈希校验增量回填，历史缺失版本可用 `content-recover` 从核验副本显式补入。已有损坏 blob 不会被覆盖，旧哈希不能由当前文件代填。清单、原子性和恢复边界见 `AI/ledger.md` §10。
- `op_results`：创建与 Ledger 事务中的幂等回执；收件箱跨库失败只补回执，不重新创建题目。
- `content_version_refs`：正文版本的题目/哈希/首次提交索引，MCP 版本按 SQL 分页；索引可从不可变 Ledger 重建。
- `snapshots`：当前状态的持久快照，不包含全量历史反馈或修正载荷。保留最近 2 个，使用前验证 policy hash、head hash 和 projector version；缺失或不匹配时流式重建。

旧 CSV 可删除并从 Ledger 重建；Ledger 不应删除。

---

## 5. Markdown 题目格式

```markdown
---
_omrs_id: OP-000001
科目: 数学
分类: [[三角函数]]
难度: 7
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

> **录入说明**：`POST /api/create` 除建骨架外，可直接写入 `# 题目`、`# 答案`、以及 `# 备注` 的 `## 错因`（由 `cause` 字段写入，导出会带上；`## 关联` 子标题保留）；新题不写 `页码`。旧题原文和 Ledger 中的页码证据保留，普通编辑按新格式保存。题目图存为 `错题/附件/<uid>-<omrs_id 短后缀>-q-N.<ext>`（如 `力学1-0135-q-1.png`）并嵌入 `# 题目`，答案图存为 `<uid>-<omrs_id 短后缀>-a-N.<ext>` 并嵌入 `# 答案`（短后缀避免迁移后附件覆盖）。「AI 自动识别」支持三种用途：`classify` 读题目图补全科目/分类/难度/相关知识点（不抄题；知识点可与分类重叠），`question_text` 读题目图把题目正文提取为文本，`answer` 忠实转录答案图内全部可见答案、解析、推导与步骤——最终以文件实际内容为准。

创建题目写出 Markdown 和附件后，若 Ledger 提交失败，文件保留为可能的唯一正文副本，不在失败清理中删除；后续由工作区扫描或原草稿入库恢复路径核对身份和内容。

> **LaTeX 公式（导出 HTML）**：题目/答案/错因中的 `$...$`（行内）与 `$$...$$`（行间）会在 HTML 导出里由内联 KaTeX 渲染；A4 与屏幕版导出都会把 KaTeX CSS/JS/字体嵌入单个 HTML 文件，离线打开仍可显示公式。若 KaTeX 资源缺失或个别公式解析失败，会安全降级为原始公式文本。Obsidian 内仍按其自身 LaTeX 渲染显示。注：旧 docx 导出曾用 `_latex_to_omml` 转 Word 原生公式（OMML），已随 docx 一并移除。

> **Markdown 表格支持子集**：题目或答案可写“表头行 + `---` 分隔行 + 数据行”的管道表格，单元格内的竖线写为 `\|`。主程序预览、A4 和屏幕版会渲染为真实 `<table>`，公式仍走 KaTeX；主程序预览也能渲染备注中的表格，但当前导出只把题目和答案送入结构化表格解析。缺单元格补空，超出表头的单元格忽略，对齐冒号当前不保留语义；A4 导出时可通过 `a4_two_columns=false` 让整份文件使用单栏，前端会在导出前确认栏模式。

### 历史记录格式（兼容）

新 Ledger 反馈的 payload 可含提交时固定的 `subject`、`question_summary`；新正文更新可含 `change_summary`，新移动事件可含 `from_category`。这些字段只为历史卡摘要服务，不影响投影算法；旧 commit 保持原样，缺值时不从当前题目或熟练度补造。
```
YYYY-MM-DD 主观:N, 对/错[, 备注:文字]
```

Markdown `# 历史` 不作为算法输入，也不会由反馈流程追加。`/api/question` 仍把该小节原文放在 `history` 字段里（纯兼容显示），正式练习记录是同一响应的 `records[]`（由 Ledger 的SQL历史投影派生，见 `AI/api.md`）；`common.py::parse_history_lines()` 与前端 `parseQHistory()` 只在老后端没给 `records` 时才用来解析旧手工行。已入账的完整 Markdown 版本可通过 `/api/question/content/history` 列出、`/api/question/content/version` 取回；活动题目可经 `/api/question/content/restore` 还原到属于该题、哈希和 `_omrs_id` 均匹配的版本。结构化 `state.restore` 不会自动重写 Markdown 文件，未入账的旧正文和附件二进制文件不在此版本保证内；细节见 `AI/ledger.md` §10。

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
3. 更新 SQL 题目、熟练度、反馈和 Session 读模型；启动、手工及后台扫描都不生成或轮转 CSV。
4. 读取重建后的 SQL 熟练度投影返回题目行，并写入 `INDEX` 运行日志；HTTP 通过 `return_scan=True` 同时取得本轮扫描回执，避免重复扫描。

需要兼容 CSV 时运行 `python3 omrs_engine.py --vault <Vault路径> export-csv`，通过 `export_legacy_csv()` 流式导出当前 SQL；既有 CSV 仍可作为首次迁移输入，扫描后的读取与更新不依赖它。

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
| `allow_external` | bool | 是否绑定 0.0.0.0（见 `AI/frontend/settings.md`） |
| `lan_pin_exempt_cidrs` | string[] | 直连免 PIN 的私有局域网 CIDR；默认空列表，代理请求不豁免 |
| `entry_background` | object | 入口锁屏背景配置：`mode` 为 `black-hole` / `custom`，`style` 当前为 `gaussian-blur`，`blur_px` 为 0–32，`asset` 为当前媒体的 `{id,kind,mime,bytes}`；缺失或损坏时按黑洞读取 |
| `agent_enabled` | bool | AI 助手总开关，默认关 |
| `agent_base_url` / `agent_api_key` / `agent_model` | string | 助手的模型接口；地址与密钥留空沿用 `ai_*`，模型必填；密钥不回显 |
| `agent_compat` / `agent_compat_overrides` | string / object | 厂商兼容配置名与单项覆写，见 `AI/agent.md` §2 |
| `agent_max_output_tokens` | int | 助手每轮模型请求的最大输出 Token，默认 10240，允许 1–65536 |
| `agent_limits` | object | `rounds` / `calls` / `writes` / `concurrent`，只能比默认值小 |
| `agent_debug_log` / `agent_vision` | bool | 模型请求日志开关；是否把聊天附图直接交给主模型 |
| `draft_mode` | string | AI 录题方式：silent（默认，只建草稿）/ confirm（可申请确认入库） |
| `draft_crop_mode` | string | ask（默认，卡片选择 AI 框/我来框）、auto（建草稿后排检测任务）、manual（去草稿区处理） |
| `draft_train_default` | bool | 新聊天图片的训练开关初值，默认 false；不覆盖已有图 |
| `draft_force_crop` | bool | 新建有来源图的全文字草稿也生成强制训练任务，默认 false；不影响入库 |
| `draft_discard_keep_days` | int | 丢弃草稿保留天数，默认 7；清理仍检查共享引用 |
| `tuning` | object | 算法可调参数覆盖，见 `AI/algorithm.md` §9；拒绝未知键、非有限数字、错误类型及越界值 |
| `ai_base_url` | string | AI 接口基础地址（OpenAI 兼容，如 `https://api.openai.com/v1`） |
| `ai_api_key` | string | AI 接口密钥（Bearer），仅存本机 |
| `ai_model` | string | 默认 AI 模型名；需支持图片输入，如 `gpt-4o` |
| `ai_thinking` | bool | AI 识图是否启用思考，默认 `false`；仅 `deepseek-flash` 显式支持，其它模型沿用服务商默认行为 |
| `ai_model_detect` | string | 收件箱框选模型；为空回退 `ai_model` |
| `ai_model_extract` | string | 收件箱转文本模型；为空回退 `ai_model` |
| `ai_model_classify` | string | 收件箱分类模型；为空回退 `ai_model` |
| `ai_restrict_tags` | bool | 「AI 自动识别」是否把相关知识点限定在「已有分类 ∪ 已有知识点」内。默认 `true`（缺失按 `true`）；`false` 时允许 AI 在无贴切已有项时新建知识点（上限 4 个） |
| `inbox_detect_provider` | string | 框选提供方：`vlm` / `local_http`（旧 `template` 值运行时按 `vlm` 处理），默认 `vlm` |
| `inbox_local_detect_url` | string | `local_http` 的 POST 地址，默认空 |
| `inbox_blind_every` | int | 每 N 张盲标，`0` 关闭，默认 `0` |
| `inbox_auto_ready_conf` | number | 自动提取的最低置信度（键名保留兼容，仍需人工审核），`0` 关闭，默认 `0` |
| `inbox_auto_on_upload` | bool | 上传后自动排队处理，默认 `false` |
| `inbox_discard_keep_days` | int | 丢弃原图保留天数，默认 `7` |

SQLite `active_config` 是完整运行时事实源，`config.json` 是镜像和手改后重启的入口。`save_config()` 按顶层键合并并验证完整候选，返回发布`revision`、`mirror_pending`、完整`tuning_effective`及实际`recalculation`结果。算法参数变化在同一事务内流式重算全部历史、发布投影与 policy hash、脱敏审计、活动配置及`storage_meta`重算摘要；失败保留旧值。重算摘要含状态、题量、有效反馈量、耗时、policy hash和投影版本，不含秘密。读取配置版本与摘要使用同一SQL读事务，跨进程不能读到混合版本。后续修正和 `state.restore` 也采用当前参数。AI、收件箱与算法保存即生效；改变监听地址仍需重启。

镜像在短`BEGIN IMMEDIATE`写事务中复查活动版本，使用0600临时文件、fsync和原子替换，只有最新版本能写回；旧发布者返回`superseded:true`及最新状态。Windows目录刷盘复用生命周期平台适配，不新增依赖。镜像失败时数据库已生效，返回 `mirror_pending:true`；监听前先补镜像，正常手改通过同一发布路径导入。待同步时发现第三方不同编辑会保留原文件和`.active-conflict.json`，接口返回`mirror_conflict:true`，启动前报冲突；镜像缺失直接从活动配置修复。配置审计只存变更键名和算法参数，不存 API 密钥。

入口自定义媒体位于 `错题/.omrs/entry-background/`，文件名由服务端生成并按当前资源 ID 加白名单扩展名保存。每次只保留一个当前自定义媒体；替换成功后删除旧媒体，切回黑洞保留该媒体以便再次切回。它位于 `.omrs` 内，随现有完整备份与恢复流程一起打包，不进入题目图片压缩任务。

`错题/.omrs/auth.json` 保存远端 PIN 的随机盐、PBKDF2-SHA256 哈希和空闲分钟数；写入时使用临时文件替换并设为仅文件所有者可读写。会话令牌只保留在服务进程内，进程重启后失效。`错题/.omrs/mcp_keys.json` 保存 MCP Key 的 SHA-256 摘要、key_id、名称、scope、创建 / 到期 / 吊销 / 最近使用时间等元数据，不保存明文，文件权限为 0600；同目录锁文件串行化 Web/CLI 生命周期更新，明文只由创建接口返回一次。`GET /api/config` 不返回 `ai_api_key` 或 PIN 哈希，仅提供已配置状态；备份包含 `错题/.omrs/`，因此备份下载仅供本机、显式豁免的直连局域网设备及已登录远端使用。

---

## 9. File_Path 分隔符注意

历史数据的 `File_Path` 可能含 **Windows 反斜杠**（如 `错题\数学\xx.md`，数据在 Windows 上录入）。读取题目文件时需归一化：`get_question_content()` 与 `analytics._question_images()` 已做 `replace("\\","/")` 后再 `os.path.join`，保证 Linux/Windows 都能命中。新增读 md 的代码也应照此处理。

## 10. JSON 交换格式（屏幕版 / 外部 AI 反馈回传）

当前只保留**反馈 JSON** 这一种外部导入格式（不落盘、不进 CSV，仅在导入框/剪贴板流转）。题目录入页不再提供外部 AI 题目 JSON 队列导入；录题仍走表单、图片粘贴和内置 AI 识别。

**反馈 JSON** 可由屏幕版「复制作答 JSON」生成，也可由反馈页「复制 AI 反馈提示词」交给外部 AI 按批改结果整理后生成。解析经 `assets/app/features/feedback/importer.js::parseLooseJson`：容忍 ```` ```json ```` 围栏包裹；顶层接受完整对象、`items` / `feedbacks` 数组字段或裸数组。

```json
{"type":"omrs-feedback","version":1,"session_id":"EXP-20260610213000",
 "exported_at":"2026-06-10 21:30","total":16,"graded":12,
 "items":[{"question_id":"OP-000001","uid":"三角函数1","is_correct":true,"sub_score":9}]}
```

仅包含**已判定**的题。导入侧（`assets/app/features/feedback/importer.js::planFeedback`，条目转换在 `state.js::fbImportFeedbackRows`）：`is_correct` / `correct` 经 `looseBool` 宽松解析（true/1/"对"…），`sub_score` / `score` 缺省按对→10 / 错→4、钳 0–10 取整；`session_id` 在 SQL Session 中则自动选中关联，否则仍按该 ID 填入待提交反馈（TMP- 临时卷亦可），为空按手动录入。导入只填充前端表单，**不会直接写 `history_log.csv`**；须人工核对后提交，提交才追加 Ledger 并重建投影。若误贴旧题目 JSON，会提示当前只支持反馈 JSON。


---


## 11. 独立存储分册

报告、收件箱、标记定义、展示板、助手、标注、草稿、训练目录与系统记录的现行结构见 `AI/data/storage.md`；这些存储不由学习 Ledger 重放，完整备份和恢复须覆盖全部独立数据库及文件。


## MCP 调度技术回执

正式复习计划沿用现有 Ledger Session 与 SQL 投影，未增加定时任务存储。ledger.db 的 op_results 复用 mcp:session: 命名空间保存幂等结果，与业务事实及投影同事务；回执不作为学习事实重放或撤销。格式与恢复边界见 AI/mcp-storage.md 的「复习调度回执」。
