# HTTP API：查询与读取

> **速查**
> - 职责：查询与读取的请求、响应及错误语义
> - 入口：`omrs/http/registry.py`、`omrs/http/` 领域适配
> - 不变量：统一鉴权、读取期限和生命周期边界见 `AI/api.md`；注册表是路由唯一来源
> - 必跑测试：`tests/test_http_boundaries.py`、`tests/test_security.py`
> - 相关：`AI/api.md`、`AI/routes.md`、`AI/security.md`

## GET 端点

### `/api/taxonomy`

返回 `{status:"ok",taxonomy:{subjects,categories,categories_by_subject,knowledge_tags}}`。分类词表合并已有题目投影与题库内安全的分类目录锚点；零题分类也在所属科目下可见，同名分类按科目隔离。

### `/api/stats`
返回完整统计与题库条目列表。

内部 `get_stats(vault, subject=None)` 可按科目精确限定原始题目行及练习历史；助手/MCP 的 `get_overview(subject=...)` 共用该入口，所有计数、平均值、明细及助手摘要采用同一范围。平均熟练度以未停用题的原始值求和、除以题数后保留三位；停用状态同时核对 CSV 与当前投影。HTTP `/api/stats` 仍返回全局快照，不增加查询参数。

**响应字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `total` | int | 活跃题目总数，不含停用题 |
| `suspended` | int | 停用题目数；停用题仍出现在 `items` 中供题库管理 |
| `killed` | int | 已击杀数 |
| `attacking` | int | 未击杀数 |
| `avg_mastery` | float | 平均熟练度 |
| `subject_dist` | object | 各科目统计 |
| `difficulty_dist` | object | 各难度分布 |
| `recent_activity` | object | 近30天每日反馈数 |
| `mastery_histogram` | object | 10个区间的题数分布，其中 `90-100` 桶包含 `Mastery = 1.0` |
| `daily_trend` | object | 近30天每日练习趋势 |
| `scatter_data` | array | 每题的散点数据 |
| `review_alert` | object | 到期与风险统计：`overdue`、`due_today`、`due_next_3_days`（明天起 3 天）、`due_next_7_days`（明天起 7 天）、`due_within_3_days`、`due_within_7_days`、`low_mastery_not_due`；兼容保留 `urgent`/`warning`/`cold`/`total_due`/`leech` |
| `items` | array | 所有未归档题目条目（含停用题），每条含 `entry_date`（Markdown 录入日期）与 `created_at`（首次 `question.create` / `question.create_external` 的 Ledger UTC 时间，旧迁移题为空），以及 `suspended`、`fail_count`（累计答错次数）、`wrong_streak`（最近连续答错次数）、`is_leech`（未击杀且连错达到阈值，默认 3 次）与复燃字段 `is_revived` / `kill_count` / `dormant_days` / `next_revive_date`（algorithm.md §11）；停用题只用于题库管理，不参与统计/调度；该端点不返回 `images`，需要图片名时使用 `/api/question` 或 `/api/analytics` |

---

### `/api/labels`
返回未归档的用户标记定义。每项包含 `id`、`name`、`color`、`order`、
`priority_bonus`、`archived`、`created_at` 和引用题目数 `count`。

### `/api/boards`
返回 `{"status":"ok","boards":[…],"folders":[…]}`。

每个板包含 `id`、`name`、`note`、`folder_id`（空串表示未归档）、`order`（组内位置）、
`count`、`uids`、`created_at`、`updated_at`、`print`、`missing`、`suspended` 和纸面摘要
`printed_summary`（`{at, pages, count, new_count, changed_count, cursor, answer_pages, print}`）。
`uids` 是板内题目的当前 UID 列表，供前端选板浮层在点击之前本地算出「这个板已经有几道」，
避免逐板再发一次请求。

每个文件夹包含 `id`、`name`、`order`、`created_at`、`updated_at`。板按「文件夹顺序 + 组内
`order`」返回，未归档的板恒排在最后。

### `/api/board?id=<board_id>`
返回指定展示板及解析后的题目引用。每个 `items[]` 附带
`question_id`、当前 `uid`、`subject`、`category`、`difficulty`、`mastery`、
`due_date`、`labels`、`suspended`、`missing`、`added_at`、`gap_lines`、
`effective_gap_lines` 和 `pin`，以及纸面相关的 `printed`、`printed_page`、`changed`。
`gap_lines` 是这道题之后留白的**绝对行数**，`null` 表示继承板的全局 `print.gap_lines`；
`effective_gap_lines` 是服务端算好的实际行数，前端不必自己再解一遍继承关系。
读取时优先按 `question_id` 命中；题目删除或无法解析时保留引用并标记 `missing`。

---

### `/api/status`
返回服务运行状态，用于辨别当前运行的 OMRS 版本和题库实例。

**响应字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | string | 当前服务状态，正常为 `ok` |
| `version` | string | 从 `omrs.version.__version__` 读取的当前版本号 |
| `started_at` | string | 服务启动时间（ISO 8601，UTC） |
| `uptime_seconds` | int | 已运行秒数 |
| `question_count` | int | 当前托管题目数 |
| `listen_external` | bool | 当前进程实际监听所有网卡为 `true`，仅 `127.0.0.1` 为 `false`；只在重启时随 `allow_external` 变化，设置页据此判断配置是否待重启生效 |
| `vault_path` | string | 当前服务使用的 vault 根路径 |
| `workspace_scan` | object | 最近一次工作区自检状态：时间、变更数、冲突数、冲突列表和错误 |

---

### `/api/analytics`
返回「数据」复盘页所需的全面派生统计，实时读取 Ledger 的 SQL 熟练度与历史投影。统计读取不生成 CSV；仅无 Ledger 事实的迁移前旧库兼容读取 CSV。对应源文件：`omrs/analytics.py` → `get_analytics()`。

**主要分组：**

| 字段 | 说明 |
|---|---|
| `generated_at` | string，服务生成该响应的时间（ISO 8601，UTC） |
| `overview` | 总题数/停用数（停用题不进入分析）/已击杀/待攻克/leech/从未复习、平均熟练度/衰减后/EF/复习次数、总复习次数/答对/答错/正确率、活跃天数/当前连续/最长连续、近 7/30 天复习、首次/最近复习 |
| `subjects` | 各科目：题数、击杀、待攻克、leech、平均熟练度、平均 EF、复习次数、正确率（按平均熟练度升序） |
| `categories` | 各分类：题数、平均熟练度、复习次数、正确率、leech（按平均熟练度升序） |
| `distributions` | `mastery_histogram`/`decayed_histogram`（各 10 桶）、`ef_dist`/`difficulty_dist`/`repetition_dist`/`interval_dist` |
| `accuracy` | `by_score`（各主观分次数/答对/正确率）、`weekly`（近 12 周复习/答对/正确率）、`by_label`（按标记的题数/复习/答对/正确率/平均分） |
| `behavior` | `by_weekday`（周一..周日）、`by_hour`（0–23）、`daily_trend`（近 30 天） |
| `forecast` | 未来 7 天到期预测（键 `"0"`..`"7"`）+ `"7+"`（7 天以上）+ `overdue` |
| `review_alert` | `overdue`、`due_today`、`due_next_3_days`、`due_next_7_days`、`due_within_3_days`、`due_within_7_days`、`low_mastery_not_due`、`leech`；兼容保留 `urgent`/`warning`/`cold`/`total_due` |
| `weak_spots` | `leeches`/`struggling`/`traps`/`recently_killed` 列表 |
| `items` | 全量题目快照（含 `eff_difficulty`/`fail_count` 累计答错/`wrong_streak` 最近连错/`is_leech`/`is_killed`/复燃字段 `is_revived`、`kill_count`、`dormant_days`、`next_revive_date`/`images` 等） |

### `/api/source/export`
本机直连或已登录远端可下载源码包；未登录远端返回 401。
生成并下载脱敏源码 ZIP。按当前工作区的固定项目文件，以及 `AI/`、`Skills/`、`assets/`、`deploy/`、`omrs/`、`tests/`、`web/` 中允许的源码和资源类型收集文件；未提交文件也会收录，不要求 Git 仓库。个人题库、临时目录、根目录运行日志、`AI/logs/`、`AI/omrs_work/`、缓存、构建产物、`tests/` 以外的 JSON（配置与运行数据）、符号链接和生成导出文件不进入 ZIP；`tests/` 下的 JSON 是测试基线（如 UI 基线文件），`assets/app/package.json` 声明 ES 模块，二者随包导出。ZIP 根目录为 `OMRS/`，`SOURCE_EXPORT_MANIFEST.txt` 列出实际包含文件，并提示分享前检查源码内容。没有可导出的源码文件时返回 400。

### `/api/export-review`
导出供 AI 使用的复盘材料，对应 `build_review_export()`：

- 默认或 `?include_images=0`：返回 Markdown（`text/markdown`）。文件含两部分：**一、复盘数据**（程序统计的表格，供人阅读）；**二、历史数据（供 AI 分析）**——全量题目快照表 + 完整复习历史表 + 一个 ```json``` 机器可读块（派生指标 + items + 原始 history）。文件名 `OMRS-复盘-YYYY-MM-DD.md`。
- `?include_images=1`：返回 ZIP（`application/zip`），内含同一份 Markdown 和 `images/` 目录；只打包全量题目快照 `items[].images` 实际引用且当前存在的题面图片，去重并保持原文件名。文件名 `OMRS-AI数据-YYYY-MM-DD-含图片.zip`。

两种响应均以 `filename*=UTF-8''` 传递中文名，plain `filename` 使用 ASCII 回退，避免 HTTP 头 latin-1 编码错误。ZIP 内的 `images/` 只用于向 AI 提供视觉上下文；AI 生成的最终托管报告仍须通过 `/api/image?name=<URL编码文件名>` 引用图片，不能使用 ZIP 相对路径。

数据及安全附件在短租约内捕获，图片逐一写临时staging；压缩在租约外。含图HTTP下载从临时ZIP分块读取，完成或失败后删除，不把整份ZIP常驻内存。

---

### `/api/sessions?status=active`
返回常规 Session 列表，可按 `status` 过滤。每个 Session 附带分批反馈进度：

过滤和推荐排除均以持久化字段 `Status` 为准（缺失时兼容按 `active` 处理）；不会按创建时间隐式套用 7 天过期规则。只有反馈完成或显式撤销后，Session 才不再属于 active 集合。

| 字段 | 类型 | 说明 |
|---|---|---|
| `feedback_uids` | array | 已提交过反馈的 UID，按 Session 原始顺序去重 |
| `pending_uids` | array | 尚未提交反馈的 UID，按 Session 原始顺序去重 |
| `feedback_count` / `pending_count` | int | 已录入 / 待录入题数 |
| `feedback_complete` | bool | 是否所有 Session 题目都已有反馈 |

### `/api/session?id=<session_id>`

权威 `entries` 含 `entry_id`、`question_id`、`uid_at_creation`、当前 `uid`、`source`、`availability`（active/archived/suspended/unresolved）和 `feedback_submitted`。旧 `uids`/`feedback_uids` 是派生兼容字段；不能确定旧条目身份时标为 unresolved，详情允许用户明确绑定。
返回单个 Session 及其 UIDs 对应的题目详情，并返回与 `/api/sessions` 相同的分批反馈进度字段。

复习调度工作台用该端点加载已有计划详情；题目条目保留 Session 中的 `_source`，反馈进度包含 `feedback_count`、`pending_count`、`feedback_uids`。计划不存在或请求失败时前端在详情区域提供重试，不会用过期请求结果覆盖当前计划。

### `/api/question?question_id=<question_id>`（兼容 `uid=`）
返回题目的完整内容（题面、答案、备注、正式练习记录、标签、知识点、录入日期与精确创建时间）。

`entry_date` 是 Markdown 的 `录入日期`；`created_at` 是首次创建提交的 Ledger 时间戳，按前端设置的 Ledger 时区显示。`legacy.bootstrap` 迁移题没有精确时间时返回空字符串，由界面显示 `—`；外部扫描题表示首次纳入 Ledger 的时间。

**响应字段（记录相关）：**
- `records`：**正式练习记录**（v1.16.1 起），数组，按 Ledger 提交顺序旧→新。由 `stats.get_question_records()` 按稳定 `question_id` 查询 SQL 历史投影，改名不断链。每条 `{log_id, date:"YYYY-MM-DD", time:"HH:MM"|"", recorded_at, score:0–10, correct:bool, note, session_id}`；`date`、`time` 默认使用上海业务时间，`recorded_at` 保留原时区。缺 IANA 数据时上海 1992 年起可按 UTC+08 转换；更早历史或其它缺失时区保留原时间，不猜夏令时。旧记录没有精确时间时 `time` 为空。没练过时是 `[]`（不是缺字段）。前端画廊战绩带和题目详情记录模块只认这个字段。
- `history`：题目文件 `# 历史` 小节的**原文**。这是 v1.1.0 之前的手工记录格式，反馈流程早已不再写它，也不参与任何统计；保留只为兼容显示，前端仅在响应里没有 `records` 字段（老后端）时才解析它。

另含 `images` 字段：题面引用的图片文件名列表（解析 `![[名]]`/`![](路径)`），与 `/api/image?name=` 对接，供报告引图。

### `/api/history?before_seq=&limit=&view=summary`
返回 Ledger 时间线。默认响应保留完整 payload 与最近 100 条 SQL 历史投影记录；Ledger 的 `commits` 是正式事实，`history` 为兼容表格字段。`limit` 接口默认 100、范围 1–500；历史页显式传入 60 并使用 `view=summary`，只返回摘要和修正操作所需字段，不返回兼容历史列表，也不逐节点读取正文 blob。时间和游标先在 SQL 中限制；摘要搜索沿游标逐条筛选，不把完整链载入内存。

可选 `q`（最多 200 字符，不区分大小写的摘要搜索）、`since` / `until`（带时区的 ISO 时间，含起点、不含终点）。筛选在分页前执行，`before_seq` 是排他的 seq 游标；两端时间同时存在时开始必须早于结束。无筛选仍返回最近一批，不隐式限制日期。非法条件返回 400。

**响应字段：**
- `commits`：按 seq 升序排列的本页提交节点，含 `seq`、`commit_id`、`created_at`、`source`、`commit_type`、`message`、`summary`、`payload`；前端再按偏好排序。
- `retraction_state`：当前 SQL 修正投影中的撤销集合，含 `retracted_sessions` 与 `retracted_reviews`，供前端在只加载最近节点时仍能正确隐藏/恢复；普通读取复用已发布投影。
- `history`：最近 100 条 SQL 历史投影记录，使用兼容字段供旧表格或调试；不包含题目 Markdown `# 历史` 原文。
- `view=summary` 时另有 `has_more` 和 `next_before_seq`；下一批把该游标传给 `before_seq`。每个 commit 的 `learning` 含当时可验证的科目分布、题面短句、分类或字段变化；缺旧快照的字段保持缺失，页面显示「无可用历史摘要」。
- 草稿入库摘要的 `payload.source_draft_id` 来自原提交 `_draft.draft_id`，供来源关联；不会改写原 Ledger 数据。

### `/api/history/detail?seq=<seq>`
按需读取一条完整 Ledger payload，返回 `{status:"ok",detail:{seq,commit_id,created_at,message,commit_type,source,payload,learning,runtime_calls,content_change?}}`。正文更新详情仅读取该条引用的前后两个 blob；旧 blob 缺失时 `content_change` 为 `{available:false,message:"无可用历史摘要"}`，不会用当前题目补历史。不存在的 seq 返回 404，非法 seq 返回 400。

`runtime_calls` 为同一 `_draft.draft_id` 的最近 20 条调用摘要，最新在前；无记录返回空数组。运行库读取失败时仍返回学习详情与空数组，另附固定说明 `runtime_calls_error`，不输出底层异常。

### `/api/runtime/records`

读取独立 MCP 运行记录，沿用 Web 授权并禁止缓存。可选 `source=mcp`、`q`、`key_id`、`status`、`since`、`until`、`before_seq` 和 `limit`（默认 60，1–200）。状态接受 running/success/failure/interrupted 及 pending_confirmation/applying/applied/rejected/expired/conflict。搜索匹配中文动作、工具名、密钥名称快照和白名单参数摘要；日期规则同历史接口。筛选先于分页，`before_seq` 排他；SQL 通配符按普通搜索文字处理。

响应 `{status:"ok",records,summary,keys,has_more,next_before_seq}`。`records` 按 seq 降序，含 `seq/call_id/source/tool/title/key_id/key_name/started_at/finished_at/status/duration_ms/error_code/draft_id/scope_summary/summary`；未结束时完成时间和耗时为 null。`summary` 的 total 和各状态计数覆盖筛选全集，不受游标影响；原四项计数始终存在，出现确认操作时另带相应状态计数。`keys` 列出记录中出现过的公开密钥编号与最后名称快照。非法条件返回 400，存储故障返回 503 固定说明；空库返回空结果且不建库。

### `/api/runtime/records/detail?seq=<seq>`

返回 `{status:"ok",detail}`，在列表摘要上增加 `arguments`、`result` 白名单摘要及 `related_commits`。关联草稿时另有 `draft:{id,status}`，草稿缺失状态为 `missing`；`related_commits` 从原 Ledger 草稿标识读取人工入库节点的 `seq/commit_id/created_at/title/uid`。确认操作另带 operation，生命周期读取独立确认库；板、报告和导出关联由结果中的稳定编号在页面构造。这些字段表示当前关联状态，不补造旧调用。非法编号 400，不存在 404，存储故障 503；授权与缓存规则同列表。运行事实没有修正/撤销入口，MCP Key 不能读取这些 Web API；确认写入使用专门 Web 端点。

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
GET 返回 405。扫描会写投影，入口是 `POST /api/scan`。

### `/api/tree`
返回 `错题/` 工作区的目录树，供「目录」页展示。**只读扫盘**：不写 Ledger、不改投影、不触发自检，每次请求现走一遍磁盘。源文件 `omrs/catalog.py`。

- 跳过所有以 `.` 开头的目录，因此 `错题/.omrs/`（Ledger 与投影所在）不在树里；返回值单独用 `data_dir` 字段说明它的位置。
- 递归深度上限 `MAX_DEPTH = 12`，超出的分支置 `truncated: true` 并停止下探。
- 文件按扩展名分成四类 `kind`：`question`（匹配 `FILE_PATTERN`，即以数字结尾的 `.md`）、`markdown`（其他 `.md`，如分类索引页）、`image`、`other`。
- `question` 类文件带 `uid`，并按 SQL 熟练度投影补 `indexed` / `subject` / `category` / `tag`。`indexed:false` 表示磁盘上有、题库投影里还没有（通常是手动放进来还没扫描）。
- 题目未建立 `错题/` 目录时返回空树而不是报错。

```json
{
  "status": "ok",
  "root": {
    "name": "错题", "path": "错题", "type": "dir",
    "children": [ { "name": "数学", "path": "错题/数学", "type": "dir", "children": [], "files": [],
                    "question_count": 2, "file_count": 4, "size": 585, "truncated": false } ],
    "files": [],
    "question_count": 3, "file_count": 7, "size": 899, "truncated": false
  },
  "summary": { "dirs": 4, "files": 7, "questions": 3, "size": 899, "orphans": 0, "truncated": false },
  "indexed_total": 3,
  "data_dir": "错题/.omrs"
}
```

`question_count` / `file_count` / `size` 都是含子目录的累计值。`summary.orphans` 是全树 `indexed:false` 的题目文件数。熟练度、到期日等学习状态**不在本接口内**，前端「目录」页由本地 `/api/stats` 的 `items` 按路径前缀聚合后叠加显示。

### `/api/image?name=<filename>`

只解析 `错题/附件/` 内安全普通文件，允许明确的子目录路径；单独文件名只有唯一匹配时可用。拒绝绝对路径、穿越、链接及含糊同名，不重复 URL 解码。HEAD 沿相同 GET 鉴权与文件边界，保留响应头并不发送正文。
以二进制流返回 `错题/附件/` 中的图片文件。**这是报告/前端引用题目图片的统一入口**：报告 HTML 内用 `<img src="/api/image?name=<URL编码文件名>">` 即可显示对应题图（同源由本程序提供）。

### `/api/reports`
返回已托管的 AI 分析报告元数据列表（按创建时间倒序）。

**响应：** `{ "status": "ok", "reports": [{id, name, filename, created_at, size}] }`

### `/api/report/view?id=<report_id>`
以 `text/html` 返回指定报告内容。响应带无 `allow-same-origin` 的 CSP 沙箱，保留脚本和外部图表资源，阻止报告脚本读取 OMRS API。报告内静态 `/api/image?name=...` 附件引用在响应时获得限单图、随会话失效的签名，仍可显示题图；存储的原始 HTML 不变。前端「报告」页点「浏览」即新标签打开此 URL。

### `/api/recommend?due_count=10&prof_count=10&subject=数学&category=三角函数&knowledge_tag=二倍角公式`
返回双列表推荐（到期列表 + 熟练度列表），互斥分配。

后端会排除仍处于 `active` 状态的持久化 Session 中已有的 UID，避免同一题重复进入多个进行中 Session。
`due_count` / `prof_count` 会转为整数并将负数按 `0` 处理；传 `0` 表示不返回对应列表，不会因 Python 负切片而扩大结果。

可选筛选参数：

| 参数 | 说明 |
|---|---|
| `subject` | 科目精确匹配 |
| `category` | 分类精确匹配 |
| `knowledge_tag` | 相关知识点精确匹配（命中 `Knowledge_Tags` 中任一项） |
| `label` | 用户标记精确匹配；可重复传递，多个标记按 OR 过滤 |

**响应字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `due` | array | 到期题目列表（Due_Date ≤ 今天），按逾期优先+EF升序排列 |
| `proficiency` | array | 熟练度题目列表（Due_Date > 今天），按薄弱程度降序排列 |

每条题目含 `_source`（`due`/`proficiency`）、`_overdue_days`、`fail_count`（累计答错）、`wrong_streak`（最近连错）、`is_leech` 等元数据。leech 题（algorithm.md §10）在熟练度列表会获得优先级加成。休眠够久的已击杀题会带 `is_revived`、`kill_count`、`dormant_days` 重新入列（algorithm.md §11），并获 `revive_priority_bonus`。

复习调度工作台以 `due_count=1000&prof_count=1000` 请求完整候选集，再在浏览器按后端顺序筛选与按科目轮选；请求期间的旧响应不会覆盖较新的推荐结果。

---

### `/api/config`
返回当前服务配置。

已设置的 `http_json_mib`、`http_legacy_upload_mib` 随配置返回，缺省分别按2MiB和128MiB处理。配置API即时更新；手改 `config.json` 镜像由服务启动时校验并导入活动配置。

**响应字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `allow_external` | bool | 是否允许外部访问（绑定 0.0.0.0） |
| `lan_pin_exempt_cidrs` | string[] | 直连免 PIN 的私有局域网网段；默认 `[]`，代理访问不豁免 |
| `tuning` | object | 算法可调参数（若已设置），键见 algorithm.md §9；通过 `save_config()` 保存后立即失效缓存 |
| `ai_base_url` | string | AI 接口基础地址（OpenAI 兼容，如 `https://api.openai.com/v1`），可空 |
| `ai_api_key_configured` | bool | AI 接口密钥是否已保存；不回显密钥本身 |
| `pin_configured` / `idle_minutes` | bool / int | 远端 PIN 状态与空闲分钟数，不返回 PIN 哈希 |
| `ai_model` | string | AI 模型名（需支持图片输入，如 `gpt-4o`），可空 |
| `ai_thinking` | bool | AI 识图思考开关，默认 `false`；仅 `deepseek-flash` 显式支持 |
| `ai_model_detect` | string | 收件箱框选模型；为空时回退 `ai_model` |
| `ai_model_extract` | string | 收件箱转文本模型；为空时回退 `ai_model` |
| `ai_model_classify` | string | 收件箱分类模型；为空时回退 `ai_model` |
| `ai_restrict_tags` | bool | 「AI 自动识别」是否把相关知识点限定在「已有分类 ∪ 已有知识点」内（默认 `true`，见设置页开关） |
| `entry_background` | object | 入口锁屏背景的脱敏配置：`mode` 为 `black-hole` 或 `custom`，`style` 当前为 `gaussian-blur`，`blur_px` 为 0–32，`asset` 只含当前媒体的 opaque id、kind、mime、bytes；不返回服务器路径 |
| `inbox_detect_provider` | string | 收件箱框选提供方：`vlm` 或 `local_http`；旧配置 `template` 运行时按 `vlm` 处理，默认 `vlm` |
| `inbox_local_detect_url` | string | `local_http` 提供方的 POST 地址，默认空 |
| `inbox_blind_every` | int | 每 N 张图执行一次盲标，`0` 关闭，默认 `0` |
| `inbox_auto_ready_conf` | number | 框选置信度达到该值时自动提取，仍需人工审核后标记就绪（键名保留兼容），`0` 关闭，默认 `0` |
| `inbox_auto_on_upload` | bool | 上传后是否自动排队处理，默认 `false` |
| `inbox_discard_keep_days` | int | 丢弃原图保留天数，默认 `7` |

配置持久化在 `错题/.omrs/config.json`。`ai_*` 键供 AI 识别与收件箱任务使用，按用途模型为空时回退到 `ai_model`；`ai_restrict_tags` 缺失按 `true` 处理，`ai_thinking` 缺失按 `false` 处理，提交非布尔值返回 400。`inbox_*` 键供收件箱框选、盲标、自动处理和清理策略使用；新提交的 `inbox_detect_provider` 只接受 `vlm` / `local_http`，旧 `template` 值运行时按 `vlm` 处理。AI 与收件箱配置保存即生效；`allow_external` 仍需重启服务才改变监听地址。

`agent_*` 键（AI 助手）的含义见 `AI/agent.md` §2：GET 不回显 `agent_api_key`，只返回 `agent_api_key_configured`；POST 可带 `clear_agent_api_key:true`；`agent_max_output_tokens` 缺省为 10240，只接受 1–65536 的整数，越界或类型不符返回 400；`agent_compat` 取值、开关类型不合法或模型名填 `faux` 时返回 400。

### `GET /api/entry-background`
只返回当前选中的自定义媒体文件，响应为二进制流并带保存时校验过的 `Content-Type`、`ETag` 和 `X-Content-Type-Options: nosniff`。未选择自定义背景、文件缺失或配置损坏时返回 404。该端点是入口页所需的公开资源，只能读取当前配置指向的单个文件，不能用查询参数访问历史媒体或 Vault 中的其他路径。

### `/api/question/content/history?uid=<uid>`（或 `question_id=`）
列出一道题（含已删除的题）在 Ledger 里入账过的正文版本：`{question_id, uid, archived, current_hash, versions:[{seq, commit_id, created_at, source, commit_type, hash, available}]}`，按提交顺序，同一哈希只列一次。找不到返回 404。见 `AI/ledger.md` §10。

### `/api/question/content/version?hash=<sha256>`
取回某个版本的正文：`{hash, markdown}`；不在 blobs 里返回 404。

### `/`、`/index.html`、`/login`
首次访问 `/` 或 `/login` 时返回独立的锁屏入口（不加载工作台静态资源，也不读取题库数据）。入口调用公开的 `GET /api/auth/session` 判断是否显示 PIN 表单；启用 PIN 时提交 `POST /api/auth/login`，未启用 PIN 且当前来源有权限时点击进入。入口视觉资源按需加载 `assets/vendor/entry-scene.js`、公式 atlas 与降级主视觉，不改变 API 契约。入口成功后回到带当前进程 handoff token 的同源 `?unlocked=1` 地址，再由常规授权检查放行并返回 `omrs_dashboard.html`；工作台 HTML 响应带 `Cache-Control: no-store`，Hash 路由会保留。配置了 PIN 时本机的 `?unlocked=1` 也需要 PIN 会话；未登录远端返回 302 或 401。

### `/assets/<file>`
通用静态资源路由（`_serve_asset()`），提供 `assets/` 下的样式与脚本（css/js/图片等），含路径穿越防护。content-type 按扩展名取自 `_ASSET_TYPES`：css、js 与 mjs（ES 模块要求 JavaScript 类型）、html（组件陈列页 `assets/app/gallery.html`）、svg、png、jpg、gif、ico、json、map、woff、woff2；表外扩展名按 `application/octet-stream` 返回。响应带弱 `ETag`（文件 mtime 与大小）与 `Last-Modified`，`Cache-Control: no-cache`；请求带匹配的 `If-None-Match`（弱比较，支持逗号列表与 `*`）或不早于文件修改时间的 `If-Modified-Since` 时回 304、不发正文；两者都带时以 `If-None-Match` 为准。原 `/omrs_dashboard.js` 路由已移除（脚本已拆分到 `assets/`）。

服务端是白名单静态路由：除 `/`、`/index.html`、`/assets/` 和明确 API 端点外，其余路径返回 404，不透传仓库文件；API 响应不主动设置跨域读取头。

---


配置查询额外返回`revision`、`mirror_pending`、规范化`tuning_effective`、`policy_hash`及最后`recalculation`，版本与摘要来自同一SQL读事务。摘要同活动配置与投影原子发布，含status、seconds、questions、feedbacks、revision、policy_hash和projection_version；旧版本缺摘要返回not_recorded，不补造过去的计量。


## MCP 调度查询与共享读模型

外部 list_sessions/get_session 复用 Session 领域进度，返回字段与分页契约见 AI/mcp.md §14。领域 list_sessions 的 include_unavailable 默认 false 保持网页隐藏全停用 active 计划的行为；MCP/助手查询显式传 true，以可用性计数说明这些计划，不把它们漏作完成。网页 HTTP 列表与详情参数保持原契约。
