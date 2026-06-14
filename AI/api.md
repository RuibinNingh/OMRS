# HTTP API

> 对应源文件：`omrs/server.py`  
> 默认端口：8471  
> 启动命令：`python omrs_engine.py --vault <path> serve -p 8471`

---

## GET 端点

### `/api/stats`
返回完整统计与题库条目列表。

**响应字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `total` | int | 题目总数 |
| `killed` | int | 已击杀数 |
| `attacking` | int | 未击杀数 |
| `avg_mastery` | float | 平均熟练度 |
| `subject_dist` | object | 各科目统计 |
| `difficulty_dist` | object | 各难度分布 |
| `recent_activity` | object | 近30天每日反馈数 |
| `mastery_histogram` | object | 10个区间的题数分布，其中 `90-100` 桶包含 `Mastery = 1.0` |
| `daily_trend` | object | 近30天每日练习趋势 |
| `scatter_data` | array | 每题的散点数据 |
| `review_alert` | object | 预警统计（urgent/warning/cold/total_due/leech） |
| `items` | array | 所有题目条目，每条含 `fail_count`（累计答错次数）、`is_leech`（顽固题标记）与 `images`（题面引用的图片文件名列表） |

---

### `/api/status`
返回服务运行状态，用于辨别当前运行的 OMRS 版本和题库实例。

**响应字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | string | 当前服务状态，正常为 `ok` |
| `version` | string | OMRS 版本号，当前为 `v1.1.1` |
| `started_at` | string | 服务启动时间（ISO 8601，UTC） |
| `uptime_seconds` | int | 已运行秒数 |
| `question_count` | int | 当前托管题目数 |
| `vault_path` | string | 当前服务使用的 vault 根路径 |
| `workspace_scan` | object | 最近一次工作区自检状态：时间、变更数、冲突数、冲突列表和错误 |

---

### `/api/analytics`
返回「数据」复盘页所需的全面派生统计（不新增持久化，实时从 `mastery_data.csv` + `history_log.csv` 计算）。对应源文件：`omrs/analytics.py` → `get_analytics()`。

**主要分组：**

| 字段 | 说明 |
|---|---|
| `overview` | 总题数/已击杀/待攻克/leech/从未复习、平均熟练度/衰减后/EF/复习次数、总复习次数/答对/答错/正确率、活跃天数/当前连续/最长连续、近 7/30 天复习、首次/最近复习 |
| `subjects` | 各科目：题数、击杀、待攻克、leech、平均熟练度、平均 EF、复习次数、正确率（按平均熟练度升序） |
| `categories` | 各分类：题数、平均熟练度、复习次数、正确率、leech（按平均熟练度升序） |
| `distributions` | `mastery_histogram`/`decayed_histogram`（各 10 桶）、`ef_dist`/`difficulty_dist`/`repetition_dist`/`interval_dist` |
| `accuracy` | `by_score`（各主观分次数/答对/正确率）、`weekly`（近 12 周复习/答对/正确率） |
| `behavior` | `by_weekday`（周一..周日）、`by_hour`（0–23）、`daily_trend`（近 30 天） |
| `forecast` | 未来 7 天到期预测 + `overdue` |
| `review_alert` | urgent/warning/cold/total_due/leech/overdue/due_today |
| `weak_spots` | `leeches`/`struggling`/`traps`/`recently_killed` 列表 |
| `items` | 全量题目快照（含 `eff_difficulty`/`fail_count`/`is_leech`/`is_killed` 等） |

### `/api/export-review`
导出复盘报告 Markdown 文件（`text/markdown`）。对应 `build_review_markdown()`。文件含两部分：**一、复盘数据**（程序统计的表格，供人阅读）；**二、历史数据（供 AI 分析）**——全量题目快照表 + 完整复习历史表 + 一个 ```json``` 机器可读块（派生指标 + items + 原始 history）。文件名 `OMRS-复盘-YYYY-MM-DD.md`（经 `filename*=UTF-8''` 传递中文名；plain `filename` 用 ASCII 回退，避免 HTTP 头 latin-1 编码错误）。

---

### `/api/sessions?status=active`
返回常规 Session 列表，可按 `status` 过滤。

### `/api/session?id=<session_id>`
返回单个 Session 及其 UIDs 对应的题目详情。

### `/api/question?uid=<uid>`
返回题目的完整内容（题面、历史、标签、知识点）。另含 `images` 字段：题面引用的图片文件名列表（解析 `![[名]]`/`![](路径)`），与 `/api/image?name=` 对接，供报告引图。

### `/api/history?before_seq=&limit=`
返回 Ledger 时间线，旧 `history_log.csv` 兼容记录仍放在 `history` 字段中。

**响应字段：**
- `commits`：按时间自上而下排列的提交节点，含 `seq`、`commit_id`、`created_at`、`source`、`commit_type`、`message`、`summary`、`payload`。
- `retraction_state`：后端基于完整 Ledger 重放出的当前撤销集合，含 `retracted_sessions` 与 `retracted_reviews`，供前端在只加载最近节点时仍能正确隐藏/恢复。
- `history`：最近 100 条兼容 CSV 记录，供旧表格或调试使用。

### `/api/ledger/verify`
校验不可变提交链，返回 `{status, valid, commits, head_commit_id, errors}`。

### `/api/optimize/summary`
返回设置页“优化”块所需状态：依赖状态、当前存储体积和最近压缩任务。

**响应字段：**
- `dependencies.pillow`：Pillow 是否可用与版本。缺失时 PNG 优化不可用。
- `dependencies.jpegtran`：`jpegtran` 是否可用。缺失时 JPG/JPEG 无损优化不可用。
- `sizes.data_chain`：活跃 `.omrs` 数据大小，排除 `legacy_backup`、`backups` 和 zip。
- `sizes.question_files`：`错题/` 下非 `.omrs`、非 `附件` 的题目/报告等文件大小。
- `sizes.question_images`：`错题/附件/` 下附件大小。
- `images`：图片数量与图片字节数。

### `/api/optimize/job?id=<job_id>`
查询图片压缩后台任务。返回 `{status:"ok", job}`，`job` 含 `status/job_id/total/processed/saved_bytes/current_file/errors/done`。

### `/api/scan`
兼容扫描入口：触发工作区自检与投影重建，返回更新后的题目数量。

### `/api/image?name=<filename>`
以二进制流返回 `错题/附件/` 中的图片文件。**这是报告/前端引用题目图片的统一入口**：报告 HTML 内用 `<img src="/api/image?name=<URL编码文件名>">` 即可显示对应题图（同源由本程序提供）。

### `/api/reports`
返回已托管的 AI 分析报告元数据列表（按创建时间倒序）。

**响应：** `{ "status": "ok", "reports": [{id, name, filename, created_at, size}] }`

### `/api/report/view?id=<report_id>`
以 `text/html` 返回指定报告内容（同源，报告内 `/api/image?name=...` 可正常加载题图）。前端「报告」页点「浏览」即新标签打开此 URL。

### `/api/recommend?due_count=10&prof_count=10&subject=数学&category=三角函数&knowledge_tag=二倍角公式`
返回双列表推荐（到期列表 + 熟练度列表），互斥分配。

后端会排除仍处于 `active` 状态的持久化 Session 中已有的 UID，避免同一题重复进入多个进行中 Session。

可选筛选参数：

| 参数 | 说明 |
|---|---|
| `subject` | 科目精确匹配 |
| `category` | 分类精确匹配 |
| `knowledge_tag` | 相关知识点精确匹配（命中 `Knowledge_Tags` 中任一项） |

**响应字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `due` | array | 到期题目列表（Due_Date ≤ 今天），按逾期优先+EF升序排列 |
| `proficiency` | array | 熟练度题目列表（Due_Date > 今天），按薄弱程度降序排列 |

每条题目含 `_source`（`due`/`proficiency`）、`_overdue_days`、`fail_count`、`is_leech` 等元数据。leech 题（algorithm.md §11）在熟练度列表会获得优先级加成。

---

### `/api/config`
返回当前服务配置。

**响应字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `allow_external` | bool | 是否允许外部访问（绑定 0.0.0.0） |
| `tuning` | object | 算法可调参数（若已设置），键见 algorithm.md §10 |
| `ai_base_url` | string | AI 接口基础地址（OpenAI 兼容，如 `https://api.openai.com/v1`），可空 |
| `ai_api_key` | string | AI 接口密钥（Bearer），可空 |
| `ai_model` | string | AI 模型名（需支持图片输入，如 `gpt-4o`），可空 |
| `ai_restrict_tags` | bool | 「AI 自动识别」是否把相关知识点限定在「已有分类 ∪ 已有知识点」内（默认 `true`，见设置页开关） |

配置持久化在 `错题/.omrs/config.json`。`ai_*` 键供「AI 自动识别」使用，缺失时该功能报「尚未配置」；`ai_restrict_tags` 缺失按 `true` 处理。

### `/`、`/index.html`
返回 `omrs_dashboard.html`。

### `/assets/<file>`
通用静态资源路由（`_serve_asset()`），提供 `assets/` 下的样式与脚本（css/js/图片等），含路径穿越防护。原 `/omrs_dashboard.js` 路由已移除（脚本已拆分到 `assets/`）。

服务端是白名单静态路由：除 `/`、`/index.html`、`/assets/` 和明确 API 端点外，其余路径返回 404，不透传仓库文件；API 响应不主动设置跨域读取头。

---

## POST 端点

### `POST /api/schedule`
创建常规 Session 并持久化到 `sessions.csv`。

**请求体：**
```json
{ "subject": "数学", "count": 10 }
```
`subject` 可省略（全科）。

**响应：** Session 信息 + 题目列表。

---

### `POST /api/session/delete`
兼容旧入口。v1.1.0 内部不物理删除 Session，而是追加 `session.retract` commit。

**请求体：**
```json
{ "session_id": "EXP-20260422120000" }
```

---

### `POST /api/feedback`
提交本次练习反馈。v1.1.0 起先追加 `review.batch_submit` commit，再重建熟练度、EF、标签、Session 和兼容 CSV 投影；Markdown 历史不再作为算法事实源。

**请求体：**
```json
{
  "session_id": "EXP-20260422120000",
  "feedbacks": [
    { "uid": "三角函数1", "sub_score": 8, "is_correct": true, "source": "due", "note": "" }
  ]
}
```

`sub_score` 范围 0–10，越大越熟练。
`source` 可选，取值 `due` / `proficiency` / `instant` / `manual` / `legacy_unknown`。若 `session_id` 对应持久化 Session，则优先使用 Session 中保存的来源；无 Session 的即时练习可逐题传 `source` 以保留 SM-2 策略差异。

**响应：** 每条反馈的 `label`、`old_mastery`、`new_mastery`、`tag`、`source`、`new_interval`、`new_due_date`。

---

### `POST /api/create`
创建题目 Markdown 文件。可只建骨架，也可直接写入完整内容（正文/答案/备注/图片）。

**请求体：**
```json
{
  "subject": "数学",
  "category": "三角函数",
  "difficulty": 6,
  "note": "p.23",
  "related_tags": ["二倍角公式"],
  "question_text": "题目正文（可选，含 LaTeX/多行）",
  "answer_text": "答案/解析（可选）",
  "cause": "错因（可选，写入 ## 错因）",
  "question_images": [{ "data": "data:image/png;base64,..." }],
  "answer_images":   [{ "data": "data:image/png;base64,..." }]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `subject` / `category` | string | 必填。科目 / 分类 |
| `difficulty` | int | 难度 1-10，默认 5 |
| `note` | string | 笔记本页码，写入 YAML `页码`（此前被忽略，现已生效） |
| `related_tags` | array | 相关知识点，写入 YAML `相关知识点` 为 `[[双链]]` |
| `question_text` | string | 题目正文，写入 `# 题目`；为空则写占位提示 |
| `answer_text` | string | 写入 `# 答案` |
| `cause` | string | 错因（为什么做错），写入 `# 备注` 的 `## 错因` 子标题（导出会带上）；`## 关联` 子标题保留 |
| `question_images` | array | 题目图：每项 `{data}`，存为 `<uid>-q-N.<ext>`，以 `![[名]]` 追加到 `# 题目` |
| `answer_images` | array | 答案图：每项 `{data}`，存为 `<uid>-a-N.<ext>`，以 `![[名]]` 追加到 `# 答案` |

**响应：** `{ "status":"ok", "uid", "file_path", "images":[全部], "question_images":[...], "answer_images":[...], "message" }`。  
图片存到 `错题/附件/`；文件名含 UID 与 `_omrs_id` 短后缀，避免迁移后附件覆盖。建索引失败会回滚（删除本次 md 与已存图片）。图片服务仅支持 PNG/JPEG/GIF。

### `POST /api/workspace/scan`
手动触发工作区自检。会检测正文变化、结构化 YAML 修改、文件移动/改名、新增 Markdown、文件消失和冲突。

### `GET /api/question/raw?uid=<uid>`
返回题目的完整 Markdown 原文与文件路径，用于纯文本编辑器。

### `POST /api/question/markdown`
保存完整 Markdown 原文。

请求体：
```json
{ "uid": "三角函数1", "markdown": "---\n_omrs_id: OP-000001\n..." }
```

若用户试图修改 `_omrs_id`，后端拒绝保存。保存后立即执行该文件的结构化字段自检：仅正文变化不写 commit；结构化字段变化写 `question.metadata_update_external`。

### `POST /api/question/move`
迁移题目到目标分类，使用最小缺口 UID 分配算法。

请求体：
```json
{ "uid": "三角函数4", "subject": "数学", "category": "二次函数" }
```

响应返回新 UID、旧 UID 和新路径。迁移不重命名旧附件。

### 历史修正端点

以下端点都只追加 commit，不修改旧记录：

- `POST /api/history/review/replace`
- `POST /api/history/review/retract`
- `POST /api/history/review/restore`
- `POST /api/history/session/retract`
- `POST /api/history/session/restore`
- `POST /api/history/state/restore`

提交前会校验目标：反馈修正要求 `target_commit_id` 指向 `review.batch_submit` 且 `target_review_index` 未越界；Session 修正要求该 Session 曾在 Ledger 中出现；`state.restore` 要求目标 `seq` 存在。校验失败返回 400，不追加脏 commit。

---

### `POST /api/ai-recognize`
用已配置的 OpenAI 兼容多模态模型识别一张图片，返回**自动填充建议**（不落库，纯识别）。对应源文件：`omrs/ai_assist.py`。

请求只用 user 角色：指令文本 + 图片（`image_url` 传 data URL）都放在 user 的 `content` 里（不设 System Message，符合 Qwen-VL 推荐用法）；协议为 `POST {ai_base_url}/chat/completions`，`Authorization: Bearer <key>`，由本地后端用标准库 `urllib` 转发（不经第三方、规避浏览器跨域）。

**请求体：**
```json
{ "image": "data:image/png;base64,...", "mode": "classify", "subject": "数学", "category": "手拉手模型" }
```
`mode='classify'` 时可选带 `subject` / `category`（用户在表单里**已填**的值）：后端会把它们写进提示词并要求模型**原样沿用、不要改动**，据此判断难度与知识点。前端拿到结果后**只填空缺项、不覆盖已填的科目/分类**（知识点与已填的合并去重）。

是否把识别出的知识点限定在「已有分类 ∪ 已有知识点」内，由配置 `ai_restrict_tags`（默认 `true`，见设置页「AI 自动识别 → 仅从已有知识点中选择」开关）决定，**每次请求读盘、即时生效、无需重启**；该端点不接受 per-request 覆盖。

| `mode` | 用途 | 提示词 | 返回 |
|---|---|---|---|
| `classify`（默认） | 读**题目**图，判断科目/分类/难度/相关知识点（不抄题、不解题） | 注入当前科目/分类/知识点；`ai_restrict_tags=true` 时要求 knowledge_tags **只能取自已有分类+已有知识点**，`false` 时**优先复用、无贴切项才可新建**；只输出 `{"subject","category","difficulty","knowledge_tags"}` JSON | `{subject, category, difficulty, knowledge_tags, restrict_tags, raw}` |
| `answer` | 读**答案**图，把答案/解析提取为纯文本 | 要求只输出答案文本 | `{answer}` |

**响应：** `{ "status":"ok", "mode", ...上表字段 }`。
- `classify`：`difficulty` 夹在 1-10；`restrict_tags` 回传本次实际采用的开关值；`knowledge_tags` 在 `restrict_tags=true` 时由后端**硬过滤**为「已有分类 ∪ 已有知识点」的子集（模型若造新词一律剔除，空池则返回 `[]`），在 `false` 时仅归一化去重并**上限 4 个**（允许新词）；模型未按 JSON 返回时 `raw` 回传原文（前端可提示重试）。
- `answer`：`answer` 为去围栏后的纯文本。
- 未配置 `ai_base_url/ai_api_key/ai_model`、网络不可达、上游 HTTP 错误或解析失败 → `{ "status":"error", "msg":"…" }` + 400。

---

### `POST /api/config`
更新服务配置。`save_config` 按键合并，故可单独提交任意子集。

**请求体：**
```json
{ "allow_external": true }
```
保存 AI 配置（前端「设置 → AI 自动识别」用此，**无需重启**，因 `load_config` 每次读盘）：
```json
{ "ai_base_url": "https://api.openai.com/v1", "ai_api_key": "sk-...", "ai_model": "gpt-4o", "ai_restrict_tags": true }
```
（`ai_restrict_tags` 单独切换也可，例如只发 `{ "ai_restrict_tags": false }`。）

**响应：** `{ "status": "ok" }`

### `POST /api/restart`
触发程序重启。

后端会先返回响应，然后在后台线程中关闭当前服务器、延迟 1.5 秒释放端口，再启动新进程接管同一端口。

**响应：** `{ "status": "ok", "msg": "正在重启..." }`

### `POST /api/backup/export`
打包整个 `错题/` 目录并以 zip 下载，文件名 `OMRS-backup-YYYYMMDD-HHMMSS.zip`。响应头 `X-OMRS-Backup-Token` 是本次会话压缩图片前的备份凭证；备份 zip 不写入数据目录，由浏览器下载给用户保存。

### `POST /api/backup/import`
导入用户选择的备份 zip（`multipart/form-data` 字段 `file`），只做校验和预览，不立即覆盖当前数据。

**响应：** `{ "status":"ok", "restore_id", "preview": { "filename", "files", "bytes", "md_files", "image_files", "has_attachments" } }`

### `POST /api/backup/restore`
按 `restore_id` 恢复备份，恢复前后端会先在临时目录重建索引，验证通过后才替换当前 `错题/` 目录。

**请求体：**
```json
{ "restore_id": "restore-xxxx", "confirm": true }
```

**响应：** `{ "status":"ok", "restored": true, "question_count": 155 }`

### `POST /api/optimize/scan`
启动图片快扫后台任务。快扫只枚举 `错题/附件/` 图片、统计格式与体积，并筛出可进入深扫压缩的范围；不会生成优化副本，也不会做像素校验。PNG 在 Pillow 可用时进入深扫范围；JPG/JPEG 仅在 `jpegtran` 可用时进入深扫范围；GIF/WebP/BMP 只统计跳过原因。

**响应：** `{ "status":"ok", "job": { "kind":"scan", "job_id", "total", "processed", "done" } }`。前端继续轮询 `/api/optimize/job?id=<job_id>`；完成后 `job.result` 含 `{ "exact": false, "scan_id", "candidate_count", "potential_bytes", "candidates", "skipped" }`。

### `POST /api/optimize/compress`
启动深扫压缩后台任务。必须先通过 `/api/backup/export` 获得有效 `backup_token`，并显式确认。任务会逐张生成优化副本、校验 PNG 像素一致或调用 `jpegtran`，只在新文件更小时替换原文件。

**请求体：**
```json
{ "scan_id": "scan-xxxx", "backup_token": "backup-xxxx", "confirm": true }
```

**响应：** `{ "status":"ok", "job": { "job_id", "status", "total", "processed", "saved_bytes" } }`

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

**响应：**
- ≥2 题：常规 Session（EXP- 前缀），写入 sessions.csv，`session_type: "exp"`
- 1 题：自定义调度（TMP- 前缀），不写入 sessions.csv，`session_type: "tmp"`

如果请求包含已在 active Session 中的 UID，后端返回 400 并拒绝创建，避免重复调度。

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
- `"include_answers": true`：在「一、题目」「二、反馈勾选表」之后追加「三、答案」一节。

返回 HTML 文件流（`Content-Type: text/html; charset=utf-8`），文件名 `OMRS-{session}-{a4|screen}.html`（经 `filename*=UTF-8''` 传中文/带后缀名）。临时调度导出的批次号前缀为 `TMP-`，不写入 `sessions.csv`。

**版面与长图切片全部在浏览器端完成**（见 `export.md`）：Python 仅读题、解析分节、抽 `![[名]]`/`![](路径)` 嵌入并把图片读成 base64，连同模板 JS/CSS 内联进 HTML；A4 的双栏分页与超长图按白缝切片由打开文件的浏览器即时计算（所见即所打印，无跨渲染器保真度差，也不再依赖 Pillow）。题目与答案走同一条解析路径（`exporting._text_to_blocks`），两处图片一致处理。`$...$`/`$$...$$` 暂以辨识样式呈现（未接 KaTeX，留作后续）。

题目块显示 UID、科目、分类、难度、状态标签和知识点标签，便于打印后按标签复盘。

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
