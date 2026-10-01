# 数据结构

> **速查**
> - 职责：CSV 字段、Markdown 题目格式、UID、配置、标记与报告存储
> - 入口：`omrs/common.py`、`omrs/indexing.py`
> - 不变量：题目结构化元数据、复习状态与 Session 以 `ledger.db` 为事实源，CSV 只是兼容投影；展示板、助手、草稿、收件箱和标注集各有独立存储
> - 必跑测试：`tests/test_history_projection.py`、`tests/test_question_records.py`、`tests/test_content_integrity.py`
> - 相关：`AI/ledger.md`、`AI/security.md`

> 对应源文件：`omrs/common.py`、`omrs/indexing.py`

> 题目结构化元数据、反馈、熟练度与 Session 的可信来源是 `错题/.omrs/ledger.db`；本文件中的 CSV 由投影器导出，用于兼容既有前端、调试查看和旧数据迁移。Markdown 是题目正文的工作文件，已入账版本保存在 Ledger 的 `blobs` 表。展示板、助手对话、草稿、收件箱和标注集使用各自的文件或数据库，不由 Ledger 重放；存储路径见下文对应章节，Ledger 边界见 `AI/ledger.md`。

锁屏入口的 WebGL 场景只读取静态资源，不读取或写入 Vault、Ledger、配置和题目文件；PIN 会话仍由 `auth.json` 与进程内存会话管理，入口本身不产生持久化数据。

---

## 1. UID 规则

科目与分类保存在 `错题/<科目>/<分类>/` 目录中；`<科目>/<科目>.md` 是科目索引，`<分类>/<分类>.md` 是分类锚点。零题分类也使用这套目录与锚点，不创建假题或平行分类数据库。统一词表将有效锚点与已有题目投影合并，按科目隔离同名分类。

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
| `Kill_Count` | int | 累计击杀次数；答错降级时不重置，复燃休眠时长据此分级变长（algorithm.md §11） |
| `Current_Tag` | string | 状态标签（如 #状态/待攻克） |
| `Entry_Date` | date | 题目录入日期 |
| `Knowledge_Tags` | string | 知识点标签，`|` 分隔 |
| `Labels` | string | 用户标记名称，`|` 分隔；旧 CSV 缺列时按空处理 |
| `Suspended` | 0/1 | 题目停用标记；`1` 时保留题目行供管理/筛选，但不参与调度、统计、分析、反馈或复习导出；没有该列的旧 CSV 按 `0` 处理 |

**注意：** `Last_Review` 历史数据可能包含 `YYYY/M/D` 格式，`parse_date()` 已做兼容。
**注意：** SM-2 字段（`Interval`、`Due_Date`、`Repetition`）为 2026-05 新增，旧数据通过 `resolve_sm2_fields()` 自动填充默认值。
**注意：** `Kill_Count` 为 2026-09 新增，老 CSV 缺列按 `0` 处理（即「还没击杀过」），重放不会报错，首次击杀即第 1 次。
**写盘安全：** 该文件经 `save_csv(..., backup=True)` 写入——先写 `.tmp` 并 `fsync`，再 `os.replace` 原子覆盖，避免写一半损坏；覆盖前滚动备份为 `mastery_data.csv.bak.1/2/3`（`.1` 最新，保留 3 份）。反馈与重建索引均走此路径。旧库首次 Ledger 迁移只在原题已有 `页码` 时保留其值；无页码题不补空字段。反馈 `Note`、草稿 note、图片说明及附件有各自语义，迁移页码时不清理。

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

复习调度工作台提交 `POST /api/confirm-schedule` 时传 `persist:true`，所以单题选择也写入 `sessions.csv` 并生成正式 `EXP-` Session；旧客户端省略该字段时仍按单题 TMP 兼容路径处理。正式 Session 的选择在写入前去重，并拒绝无效 UID、非法来源、停用题和 active Session 重复占用。

Session 中的 `source` 贯穿反馈处理：`due` 使用常规 SM-2 间隔，`proficiency` 的答对间隔按 0.7 系数折中；分批反馈只更新已提交题目，`pending_uids` 保留未反馈题，全部提交后状态变为 `completed`。

---

## 4.1 ledger.db

路径：`错题/.omrs/ledger.db`

核心表：

- `commits`：不可变提交链。
- `question_projection` / `question_knowledge_points`：题目结构化投影；`question_projection.created_at` 是可空的 Ledger 创建时间。首次 `question.create` / `question.create_external` 写入提交的 UTC 时间；移动、结构化修改、停用与恢复沿用原值；`legacy.bootstrap` 题为空。旧库启动时由 `ledger.init_db()` 自动补列。
- `mastery_projection`：熟练度、EF、SM-2 排期投影，含 `kill_count` 累计击杀次数（老库缺列时 `ledger.py` 用 `ALTER TABLE ... DEFAULT 0` 补列）。
- `session_projection`：Session 投影。
- `workspace_fingerprint`：Markdown 工作区自检指纹。
- `blobs`：已入账题目 Markdown 全文（`hash` = 正文 sha256，`content`，`created_at`）；当前缺失版本可在启动时经身份和哈希校验增量回填，内容损坏的已有 blob 不会被静默覆盖，旧哈希不能由当前文件代填。见 `AI/ledger.md` §10。
- `op_results`：预留的操作结果表（按 `op_id` 存结果 JSON，供幂等重放）；当前没有写入方。
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

Markdown `# 历史` 不作为算法输入，也不会由反馈流程追加。`/api/question` 仍把该小节原文放在 `history` 字段里（纯兼容显示），正式练习记录是同一响应的 `records[]`（由 Ledger 投影 `history_log.csv` 派生，见 `AI/api.md`）；`common.py::parse_history_lines()` 与前端 `parseQHistory()` 只在老后端没给 `records` 时才用来解析旧手工行。已入账的完整 Markdown 版本可通过 `/api/question/content/history` 列出、`/api/question/content/version` 取回；活动题目可经 `/api/question/content/restore` 还原到属于该题、哈希和 `_omrs_id` 均匹配的版本。结构化 `state.restore` 不会自动重写 Markdown 文件，未入账的旧正文和附件二进制文件不在此版本保证内；细节见 `AI/ledger.md` §10。

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
| `tuning` | object | 算法可调参数覆盖，键与默认值见 algorithm.md §9；仅接受已知键且为数字 |
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

`load_tuning()` 带进程内缓存，`save_config()` 写入后自动失效缓存；算法调参、AI 和收件箱策略保存即生效，无需重启。只有 `allow_external` 改变监听地址时需要重启。`save_config()` 按键合并，可单独提交；`load_config()` 的缺省键集中在 `common.CONFIG_DEFAULTS`。

入口自定义媒体位于 `错题/.omrs/entry-background/`，文件名由服务端生成并按当前资源 ID 加白名单扩展名保存。每次只保留一个当前自定义媒体；替换成功后删除旧媒体，切回黑洞保留该媒体以便再次切回。它位于 `.omrs` 内，随现有完整备份与恢复流程一起打包，不进入题目图片压缩任务。

`错题/.omrs/auth.json` 保存远端 PIN 的随机盐、PBKDF2-SHA256 哈希和空闲分钟数；写入时使用临时文件替换并设为仅文件所有者可读写。会话令牌只保留在服务进程内，进程重启后失效。`错题/.omrs/mcp_keys.json` 保存 MCP Key 的 SHA-256 摘要、key_id、名称、scope、创建 / 到期 / 吊销 / 最近使用时间等元数据，不保存明文，文件权限为 0600；同目录锁文件串行化 Web/CLI 生命周期更新，明文只由创建接口返回一次。`GET /api/config` 不返回 `ai_api_key` 或 PIN 哈希，仅提供已配置状态；备份包含 `错题/.omrs/`，因此备份下载仅供本机、显式豁免的直连局域网设备及已登录远端使用。

---

## 9. report/（AI 分析报告托管）

> 对应源文件：`omrs/reports.py`

| 路径 | 说明 |
|---|---|
| `错题/report/<id>.html` | 单份报告的纯 HTML 文件 |
| `错题/report/index.json` | 报告索引数组：`[{id, name, filename, created_at, size}]` |

- `id` 形如 `RPT-YYYYMMDDHHMMSS`（同秒冲突加 `-N`）。`created_at` 由后端在创建时记录。
- 报告由 `GET /api/report/view?id=` 以 `text/html` 提供，响应使用独立来源的 CSP 沙箱。报告内仍用 `<img src="/api/image?name=<URL编码文件名>">` 引用题目图片；浏览时服务端只为附件目录中的静态图片 URL 加当前会话的单图签名。磁盘上的报告 HTML 保持原样。
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

仅包含**已判定**的题。导入侧（`assets/app/features/feedback/importer.js::planFeedback`，条目转换在 `state.js::fbImportFeedbackRows`）：`is_correct` / `correct` 经 `looseBool` 宽松解析（true/1/"对"…），`sub_score` / `score` 缺省按对→10 / 错→4、钳 0–10 取整；`session_id` 在 `sessions.csv` 中则自动选中关联，否则仍按该 ID 填入待提交反馈（TMP- 临时卷亦可），为空按手动录入。导入只填充前端表单，**不会直接写 `history_log.csv`**；须人工核对后提交，提交才追加 Ledger 并重建投影。若误贴旧题目 JSON，会提示当前只支持反馈 JSON。


---

## 12. 收件箱 `错题/.omrs/inbox/`（v1.12.0）

`inbox.db`（SQLite：items / regions / cards / jobs / meta / chat_training_boxes；items 扩展列含 `blind`、`blind_boxes`、`reset_epoch`、`revision`，`connect()` 对旧库 ALTER 补齐）、`raw/<sha256>.<ext>`（上传原件）、`crops/`（裁剪缓存，可重建）、`annotations.jsonl`（append-only 标注事件）。区域坐标归一化 0–1。items.training_only 隔离聊天训练图，chat_training_boxes 独立保存训练标注并按图合并导出。`reset_epoch` 是当前图处理代次，重置递增以阻止旧保存和后台任务写回；`revision` 是当前图写入版本，更新、重置、丢弃和录入成功后递增，HTTP 写入必须附预期版本。重置删除当前区域、题卡和对应裁图缓存，保留原图及历史事件。字段与状态机见 `AI/inbox.md` §2、§9；`items.layout` 的新上传默认值为 `zuoyebang`（作业帮截图），已有记录可在处理页改选。不参与备份导出以外的任何投影；`item.commit` 事件里记录了创建出的 `uid` / `question_id` 便于回溯。

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

## 14. 展示板 `boards.json`

路径：`错题/.omrs/boards.json`，当前 `version: 3`。展示板是呈现层引用集合，不进入 Ledger，也不
复制题目正文。文件写入会滚动 `.bak.1/2/3`，再使用临时文件、`fsync` 和
`os.replace` 原子替换。

文件顶层是 `{version, folders, boards}`。`folders[]` 是单层（不嵌套）的展示板文件夹，每项为
`{id, name, order, created_at, updated_at}`，id 形如 `BF-20260907-a1b2c3`。板用 `folder_id`
指向所属文件夹，空串表示未归档；`order` 是它在组内的位置。读写时都会重新编号：文件夹按 `order`
排 0..n-1，板在组内排 0..n-1，因此顺序字段始终连续且无重复。

`folder_id` 指向不存在的文件夹时静默归入未归档，不报错也不丢板——文件夹是分类，坏掉的分类不该
连累数据。折叠状态属于 UI 状态，存在 `localStorage['omrs-board-folders-collapsed']`，不写进本文件。

板记录包含板元数据、打印设置和 `items[]`。每个条目同时保存
`question_id` 与 `uid`；读取优先稳定的 `question_id`，UID 只做显示和降级兜底。
停用题继续保留在板内但导出跳过；题目删除或无法按稳定身份解析时显示
`missing`，不会自动从板文件中删除。

### 14.1 版面设置 `print`

`normalize_print()` 的当前字段与取值范围：

| 字段 | 范围 | 说明 |
|---|---|---|
| `note_ratio` | 0.30–0.55 | 右侧留白占可分配宽度的比例，默认 0.50 |
| `gap_lines` | 0–24 | 板的**全局**题间留白行数（每行 18px） |
| `answers` | `none` \| `append` | 是否在末页附答案 |
| `show_labels` / `show_meta` | bool | 题头是否显示标记 / 科目·难度 |
| `cut_line` | `none` \| `dash` \| `solid` | 每题留白末尾的裁切提示线，默认 `dash` |
| `cut_label` | bool | 切割线右端是否标「第 N 题止」，默认关 |
| `locked` | bool | 保护纸面版式；真实影响已印区域的版式/有效留白变更才重置，引用增删排序不重置，见 `board.md` §4.6 |

未知键忽略，缺失键回默认；旧的 `note_align`、`note_min_lines`、`note_pattern`、
`last_printed_page` 读取时直接丢弃。

### 14.2 每题留白：v2 `extra_gap_lines` → v3 `gap_lines`

v2 的语义是「全局 + 每题额外」，v3 改成**每题绝对行数**：

- `items[].gap_lines = null` → 继承板的全局 `print.gap_lines`；
- `items[].gap_lines = 数字` → 这道题之后固定留这么多行，上限 `MAX_GAP_LINES = 48`。

迁移在 `_normalize_item()` 里就地完成，不需要单独的迁移脚本：读到 v2 的
`extra_gap_lines`（先夹到 0–24）时折算成 `全局 + 额外`，因此**迁移前后每题的有效留白逐题等值，
纸面像素不变**。折算后 `extra_gap_lines` 恒为 0，只读不写，所以重复归一化是空操作——
`load → save → load` 的结果与一次 `load` 完全相同（`tests/test_boards.py`
的 `BoardGapMigrationTests` 逐条锁住这两点）。

`extra_gap_lines == 0` 的条目不折算，保持 `gap_lines = null`（继承），避免把「没设过」
写死成一个具体数字。读不懂的 `gap_lines`（`"x"`、NaN）同样按「没设」处理而不是折成 0：
0 是「这题后面不留白」的真实选择，把坏数据折成 0 会静默改掉纸面。

`update_board(items=…, print=…)` 同一请求里同时提交两者时，`print` 先生效，
`items` 的 v2 折算用的是**本次请求之后**的全局留白，不会用旧值折算出错值。

`effective_gap_lines(item, print)` 是「这道题实际留几行」的唯一算式，服务端与前端
（`boardEffectiveGap`）必须同解；导出时由 `_board_gap_lines()` 落成绝对值交给浏览器模板，
导出数据里**不再出现** `extra_gap_lines`。

### 14.3 纸面记录 `printed`

`printed` 描述**纸上现在有什么**：`pages`（已打印总页数）、`cursor{page,y}`
（下一道新题的续排位置）、打印时的 `print` 几何、`items[]`（每题 `question_id / uid /
hash`（正文指纹）/ `segments[{page,top,height}]`）和 `answer_pages`。`print` 是实际排版时的
几何快照，其中 `note_ratio / gap_lines` 是仅新增续排的权威比例与留白；它不因板当前设置变化而
被覆盖。`pages == 0` 表示没有记录；由 `POST /api/board/printed` 在用户「标记为已打印」时写入，
`mode:"all"` 优先采用导出模板回传的 `layout.print`，缺失时兼容回退当前板 `print`；`mode:"new"`
追加题目但保留原 `printed.print` 快照。`hash` 优先沿用导出时回传的 `layout.items[].hash`，旧导出件缺失时才读取记录时的正文指纹。设计见 `board.md` §4。

纸面记录独立于板的引用集合：追加、去重、移出、清空引用、排序和未打印题留白更新都保留完整记录。已印题从板移除仍保留旧占位；重新加入同一稳定 `question_id` 不重复打印，后续新增题号仍按纸面记录中的题数续接，不按当前板内题数计算。

记录入口会拒绝无法解析或与板内 / 既有纸面不一致的题目身份，且所有段页码、答案页码和续排页码都必须不超过 `pages`；`mode:"new"` 不能在空纸面上建立伪基线。

### 14.4 纸面历史 `boards_printed_history.jsonl`

路径：`错题/.omrs/boards_printed_history.jsonl`，一行一条 JSON，**只增不改**。
记录纸面（`record_printed`）与重置纸面（`reset_printed`，包括锁定版式真实变更触发的重置）会在覆盖之前，追加旧纸面的**摘要**：页数、题数、cursor 和设置。没有逐题 `items/segments/hash`，不能据此直接恢复完整纸面；完整占位必须从 `boards.json` 或其备份核验，恢复时还需保留后续新增引用。

```json
{"at":"2026-09-09T04:00:00+00:00","board_id":"BD-…","board_name":"考前速览",
 "event":"record","mode":"all","pages":3,"count":12,
 "cursor":{"page":3,"y":493.56},"print":{"note_ratio":0.50,"…":"当时的版面"}}
```

- `event ∈ {record, reset}`；`mode` 只在 `record` 时有值（`all` / `new`）。
- 旧纸面为空（`pages <= 0`）时没有可留存的历史，跳过——所以**第一次**「标记为已打印」
  不会产生任何一行。
- 展示板不进 Ledger，这份 jsonl 是审计辅助而不是事实链；写失败只记运行日志
  （`board_printed_history_failed`），绝不打断打印记录本身。
- `read_printed_history(vault, board_id="", limit=20)` 按时间**倒序**读回，可按板过滤；
  文件不存在返回空列表，坏行跳过不报错。**目前没有 UI 也没有 HTTP 端点**读它，
  只能直接读文件或在 Python 里调用。

备份整个 `错题/` 目录时，`labels.json`、`boards.json` 和 `boards_printed_history.jsonl`
都随 `.omrs/` 一起进入备份。

## 15. 对话库 `agent.db`

路径：`错题/.omrs/agent.db`（SQLite，随备份导出，不进 Ledger）。表：`conversations`（对话，软删除）、`messages`（按 OpenAI 格式存的会话消息，用于重放模型上下文）、`runs`（每次运行的状态、结束原因、统计、合并后的事件、撤销信息）、`tool_calls`（参数、用户决定、结果、产生的 commit）、`practice_cards`（按工具调用保存结构化卡片和稳定题序）、`practice_attempts`（签发的 attempt、唯一重练请求标识及界面进度）。后两表不保存正式 Session 或反馈事实，反馈仍在 Ledger；字段与读写规则见 `AI/agent.md` §8。模型请求日志（开关打开时）在 `错题/.omrs/logs/agent-llm.jsonl`，含题目内容，不含密钥。

`runs.events_json` 原样保存主请求 `round.end` 和辅助请求 `usage.aux` 的归属及归一化用量，旧事件无需迁移或回写；新增用量字段保留 `null` 表示供应商未返回，不能按零解释。`stats_json` 仍有旧聚合字段，页面以事件按请求重放为准。

## 16. 框选标注集 `错题/.omrs/annotate/`

独立于收件箱的训练数据，由 `omrs/annotate.py` 读写，不进 Ledger、不参与任何投影。`annotate.db` 只有一张 `images` 表：`id (AN-YYYYMMDD-xxxxxx)、sha256（唯一）、file（上传时的文件名）、mime、width、height、bytes、status (todo|done)、boxes（JSON 数组 [{role, x, y, w, h}]，role 为 question / answer，坐标归一化 0–1）、revision、uploaded_at、updated_at`。旧库缺 `revision` 时幂等补列，保存与删除按预期版本检查，保存成功递增。原图在 `images/<sha256>.<ext>`，删除记录时一并删除。整个目录随设置页「备份导出」打包（备份遍历整个 `错题/`），图片压缩优化只处理附件目录，不碰这里。

## 17. AI 草稿存储

`draft_manual_edits` 表按 `(draft_id,target)` 记录人工编辑过的字段或块，供 AI 修订工具在同一版本内保护人工内容；`events.jsonl` 的 `draft.ai_update` 记录 AI 修改的运行来源、旧新 revision 和实际变化。草稿存储不进入题目 Ledger。

`错题/.omrs/drafts/` 的 drafts.db 独立于 Ledger，包含 images、conv_images、drafts、blocks、draft_images、commit_operations、training_tasks、training_boxes、draft_jobs 与 cleanup_candidates；图片按 hash 保存，事件追加到 events.jsonl。JPEG 在计算 hash 前清除主图结束标记后的相册数据，缺尾时补标记，保留编码像素；旧文件只在读取为 data URL 时临时整理，不改写。revision、来源完整性、清理状态与训练任务 manual_override / force_crop 通过增量迁移添加。字段、来源恢复和入库恢复以 `AI/drafts.md` 为准；只有通过产生带 `_draft` 追溯信息的题目创建提交。


## 18. 外部训练目录与面板配置

`config.json` 的 `train_dir` 默认空串（读取 `~/omrs-train`）；`train_try_collect` 默认 false（实时测试成功后是否积累到标注集）。训练数据、权重和运行日志放在 Vault 外，不随题库备份，不进 Git。主程序仅以标准库读文件，不导入训练框架。

- datasets/版本/manifest.json：classes、counts（train/val/test/quarantine）、strip_counts、samples、excluded、groups、splits；图片 ID 带 annotate/inbox 前缀，samples 保存 SHA-256、原始框与条带信息。测试图清单冻结到 test_ids.txt，重建沿用。
- runs/实验/status.json：state（running/done/failed）、epoch、epochs、started_at、updated_at、epoch_seconds、pid、dataset、可选 error；训练每轮临时文件加 os.replace 原子写入。进程消失或更新超时由面板派生 interrupted。
- runs/实验/metrics.jsonl：每轮一行，epoch、epoch_seconds、train/box_loss、train/cls_loss、val/box_loss、val/cls_loss、metrics/mAP50(B)、metrics/mAP50-95(B)；忽略最后未写完的一行，按轮次去重排序。
- runs/实验/eval.json：dataset、split、manifest_sha256、template/model 汇总、逐图 rows/template_rows、overlays（name/id）；overlays/ 下 JPEG 叠加图必须在清单中登记才可经接口读取。
- models/current/model.onnx 与 model.json：固定模型与 name、run、created_at、sha256、bytes、classes、imgsz、conf、dataset 元数据；训练不会隐式修改已发布模型。

面板只读目录为空时返回空状态，各文件解析错误各自报告。配置保存继续使用 `/api/config`；不提供网页训练控制。续训命令从原实验 identity.json 取参数，恢复前训练脚本检查数据清单和参数指纹。

实时测试默认只在内存中运行。积累开启后调用现有 annotate 模块写原图与模型框，status 保持 todo；重复 SHA 只提示已有，不更新框。完成标注前不进入默认导出和训练数据集，不增加任何数据表或来源字段。单图 15 MB／4000 万像素与每进程单并发限制用于约束内存。

面板生成的构建与开始训练命令采用未占用的新版本／实验目录；续训沿用旧目录和 identity 参数。评估命令只评估，导出与发布各自显式执行，网页只展示训练命令；受管服务切换使用下述独立映射。

### 内容评测产物与复核存储

外部训练根目录的 audits/评测/audit.json 保存数据集和manifest哈希、样本/分组/用途、检测模型与权重哈希、阈值、提示词版本/哈希、参数、原图/裁图资源ID及坐标。images/仅保存登记图片；案例JSON与attempts/每次响应只允许首次写入，不覆盖原判；progress.json为可恢复的进度快照。缺框也有案例，不从指标分母排除。历史校准导入保留原响应和各轮参数，不作为独立验收。

reviews.sqlite3 的 reviews 表以(audit,case_id,revision)为主键，追加action/verdict/note/source/created_at；source为user或executor。用户结论优先于执行者，未复核项仍沿用原判。该库与训练产物不进入题库备份、不修改标注框。audit-cache/按图/提示/模型/请求参数及渠道指纹保存成功调用；content-round-1.json记录整个实验轮次的实际请求次数、参考费用和未知usage次数，请求前持久计数。

内容数据快照保留全部旧train/val/test归属；test用途标为historical_regression，全新分组才可进入independent。相近验证/测试新图隔离，桥接不同冻结集合拒绝构建。草稿框只读chat_training_boxes，接受人工或人工编辑来源；同SHA相同标签去重，冲突标签排除。困难加权快照只从同manifest的train评测读取已复核错误，记录复核证据；不修改旧数据版本。

### 受管服务目录

`<训练根>/managed/snapshots/<元数据哈希>/` 保存经过 SHA 验证的 model.onnx/model.json 副本；active 为原子替换的相对符号链接。state.json 保存 revision、current、previous、operation；operations/请求ID.json 保存幂等请求、前后模型 SHA、服务端认证方式/会话 ID/可信来源 IP、候选的独立验收状态与人工确认、时刻、运行状态、错误和回退错误，不记录 PIN/Cookie，也不把共享 PIN 会话认定为具体人。events.jsonl 追加完成或恢复事件。状态与请求快照用临时文件加原子替换写入，operation.lock 用 flock 串行化，预检/重启还与 training.lock 互斥。运行中的请求记录允许更新到终态，追加事件不会改写。

受管映射不跟随models/current；初始化只由部署者执行bootstrap_control.py且拒绝覆盖已有state。只发现有export.json、identity.json、eval.json及匹配权重/ONNX哈希的实验。删除或修改实验不会改变已复制的在线模型。独立训练目录仍需单独备份，不随题库备份。
