# Ledger 架构

> **速查**
> - 职责：不可变提交链、投影缓存、历史修正与迁移边界
> - 入口：`omrs/ledger.py`、`omrs/projection_runtime.py`、`omrs/projections.py`、`omrs/data_repository.py`；本机补回为 `omrs/content_recovery.py`
> - 不变量：提交只追加不改写，修正以新的 commit 表达；追加在 `BEGIN IMMEDIATE` 事务里；已入账的题目 Markdown 版本存进 blobs，commit 只引用哈希
> - 必跑测试：`tests/test_history_projection.py`、`tests/test_sessions_feedback.py`、`tests/test_ledger_concurrency.py`、`tests/test_content_integrity.py`、`tests/test_agent_tools.py`、`tests/test_data_runtime.py`
> - 相关：`AI/data.md`、`AI/frontend/records.md`、`AI/agent.md`

> 题目结构化元数据、反馈、熟练度与 Session 以 `错题/.omrs/ledger.db` 为事实源；运行时读 SQL；兼容 CSV 仅按需导出或备份时生成，启动与扫描不生成，也可作首次迁移输入。展示板、助手对话、草稿、收件箱和标注集使用独立存储，不由 Ledger 重放，见 `AI/data.md`。

---

## 1. 单链模型

`omrs/ledger.py` 使用标准库 `sqlite3` 建立全局线性提交链：

- `commits.seq` 自增，`commit_id` 为 `GENESIS` 或 `CMT-000002` 形式。
- 每个提交保存 `prev_hash` 与 `commit_hash`。
- 哈希输入为 `prev_hash + created_at + source + commit_type + canonical_json(payload)`。
- `canonical_json()` 使用 `sort_keys=True` 和紧凑分隔符，保证同一 payload 序列化稳定。
- `verify_ledger()` 逐节点校验 seq 连续性、`prev_hash`、`commit_hash` 与 payload 可解析性。

`GET /api/ledger/verify` 返回链校验结果。

---

## 2. question_id 与 UID

- 用户可见 UID 仍是 Markdown 文件名（不含 `.md`）。
- 隐藏稳定身份为 `_omrs_id`，格式为 `OP-000001`，写入 Markdown YAML。
- `question_id = _omrs_id`，历史反馈、迁移、归档、恢复均引用 `question_id`，同时保存 `uid_at_that_time` 用于展示当时名称。
- 迁移或重命名后 UID 可以复用，但不同题目的 `question_id` 不会复用。

---

## 3. Markdown 模板

新建题目必须生成完整 YAML：

```markdown
---
_omrs_id: OP-000001
科目: 数学
分类: "[[三角函数]]"
难度: 5
相关知识点: []
tags:
  - 状态/待攻克
录入日期: 2026-06-12
---
```

旧题首次迁移时会自动补 `_omrs_id` 与缺失的已知字段；旧页码可作为历史原文保留，新题不生成该字段。正文、答案、备注和 LaTeX/图片引用仍保持 Markdown/Obsidian 兼容。

---

## 4. 投影缓存

`omrs/projections.py` 从提交链重放出以下投影表：

- `question_projection`（含 `suspended` 停用标记和可空 `created_at`）
- `question_knowledge_points`
- `question_labels`（题目用户标记的查询投影）
- `mastery_projection`
- `session_projection`
- `workspace_fingerprint`
- `snapshots`

`projection_runtime.project()` 校验世代、已发布 seq/head hash、policy hash 与 projector version（`ledger-v3`）。普通追加仅更新受影响的题目、熟练度、Session 和新增历史行；不全链重放或全表删除。跨请求保留最多 2 个 Vault 的当前状态缓存，不保留历史反馈载荷。`snapshots` 保存当前状态及策略/链头校验值，保留最近 2 个；修正索引和反馈明细留 SQL，不重复装入快照。缺失、不匹配或世代变化时流式重建。

题目、熟练度或 Session 投影的删除会在同一事务内废止 `projection_meta`。完整重建在最后重新发布检查点；旧代码全量重写 SQL 后，即使链头未变化，再次启动当前代码也必须重建，不能将旧缓存与当前快照混用。此机制只保护再次升级的派生缓存，不赋予旧代码当前身份与配置契约。

SQL 读模型还包含 `history_projection`、`projection_meta`、`active_config` 和两张修正索引表。历史按题目、Session 和业务日期索引；内部消费者通过 `data_repository` 读取。`export_legacy_csv()` 逐行导出 `mastery_data.csv`、`history_log.csv`、`sessions.csv`，默认 `rebuild_projection()` 不写 CSV。

题目 UID 和路径只对 `archived=0` 建部分唯一索引；旧表的全表 UNIQUE 会自动迁移，从不可变 Ledger 重建被旧缓存遗漏的归档身份。更新按 `question_id` 冲突处理，不通过 REPLACE 删除另一身份。

`created_at` 只在首次 `question.create` 或 `question.create_external` 重放时写入对应 Ledger 提交的 UTC 时间；移动、元数据修改、停用和恢复不会改变它。`legacy.bootstrap` 题目没有可核验的精确时间，保持空值。旧库启动时 `ledger.init_db()` 会自动补列。外部扫描题的时间含义是首次纳入 Ledger，而不是文件系统创建时间。

用户标记不另建一条事实链：标记定义保存在
`错题/.omrs/labels.json`，题目归属保存在 Markdown YAML 的 `标记:` 字段。
工作区扫描或网页标记修改产生 `question.metadata_update_external` /
`question.metadata_update`，投影器从提交 payload 的题目元数据重建
`question_labels` 与 CSV `Labels` 列。删除并重建投影时，标记归属随题目元数据
一起恢复；`labels.json` 本身不进入 Ledger。

---

## 5. 反馈与历史修正

`POST /api/feedback` 在同一 `BEGIN IMMEDIATE` 事务中追加 `review.batch_submit` 并增量发布 SQL 投影。拿到写事务后再次核对链头、检查点与活动算法参数，跨进程更新导致缓存过期时重建后重试；事实或投影发布失败整体回滚，并废止已修改的进程缓存。响应采用实际投影结果，持久化 Session 的完成检查在提交后执行；已撤销计划拒绝新增反馈。每条反馈包含：

- `question_id`
- `uid_at_that_time`
- `session_id`
- `source`
- `is_correct`
- `sub_score`
- `note`
- `occurred_at`
- `recorded_at`：带原时区的精确时间戳
- `review_date` / `review_timezone`：业务日期与 `Asia/Shanghai` 日界线
- `subject` 与 `question_summary`：新反馈提交时从当时的 SQL 题目与安全的 Markdown 路径固定科目、题面短句；读取旧反馈不从当前题目反推这两个字段。

历史时间转换共用 `common.business_time()`。缺 IANA 数据库时只对上海 1992 年起的时间使用 UTC+08 固定偏移；更早历史或其它缺失时区保留原时间和 `recorded_at`，不补造历史夏令时规则。只有日期的旧记录仍不生成精确时分。

聊天练习卡的反馈另带 `attempt_id` 和稳定 `entry_id`（当前为 `question_id`）。服务端在上述反馈事务中检查该 attempt 已提交条目；同一题重试直接返回已成功，不再次增加 Attempts。事务提交后卡片进度写回失败，下次从 Ledger 恢复；`agent.db` 的进度不能代替提交事实。卡片读取在 Ledger 写事务之前完成，避免模块锁与数据库写锁反向嵌套。

反馈**不会**向题目 Markdown 的 `# 历史` 小节追加行。该小节仍由新题骨架保留，且旧格式解析器仍在兼容旧手工文本，但它不属于结构化复习记录，不能用于推断练习次数、正确率或累计答错次数。

题目库的单题删除先核对文件 `_omrs_id` 与投影身份，把当前正文存入 `blobs`，并逐字确认能按哈希取回；不满足时拒绝删除。通过后暂存 Markdown 并追加 `question.archive`，提交失败则恢复文件。投影将该题标记为 archived 并从活动题库/兼容 CSV 排除，既有提交与反馈仍可审计；已入账正文可按 `question_id` 列出并按哈希取回。`/api/question/content/restore` 只接受活动题目的 UID，不直接重建已归档题目。附件图片保留，以免删除其他题共用的文件。

题目停用不删除 Markdown，只追加 `question.suspend`；恢复只追加 `question.resume`。两类 commit 都携带 `question_id`、当时 UID、文件路径和可选 `reason`，投影列 `suspended` 与兼容 CSV 列 `Suspended` 据此派生。停用题保留在题库管理列表和历史链中，但从调度、统计、分析、反馈和复习导出中排除；恢复后沿用原有 Mastery/SM-2 状态。

展示板 `错题/.omrs/boards.json` 同样不进入 Ledger。它只是可重排的呈现层引用
集合，保存 `question_id` / `uid`、打印设置和纸面记录；备份整个 `错题/`
目录时随文件备份，Ledger 恢复不承诺还原展示板。

历史修正只追加新 commit：

- `POST /api/history/review/replace`
- `POST /api/history/review/retract`
- `POST /api/history/review/restore`
- `POST /api/history/session/retract`
- `POST /api/history/session/restore`
- `POST /api/history/state/restore`

`POST /api/session/delete` 兼容旧前端，但内部语义改为 `session.retract`。

### 修正投影如何重放

修正 commit 只追加事实，不写逆向熟练度补丁。完整重放先在 `projection_review_corrections` / `projection_session_corrections` 中建立最终有效修正索引，再逐提交应用；反馈明细直接落 SQL。被撤销反馈或 Session 的反馈跳过；恢复采用原记录；替换把 replacement 合并到原记录。算法状态、状态标签、累计击杀次数和正式历史一起重算，修正数量增长不会扩张 Python 全量集合或载荷字典。

`kill_count` 只在转换结果 `tag_action == "kill"` 时累加，答错降级不重置；旧表缺列自动补 `NOT NULL DEFAULT 0`，旧 CSV 缺列也按 0。元数据变更按前后 Markdown 元数据差量判断：未改的状态字段不会覆盖反馈产生的投影状态。

`state.restore` 按有效目标前缀及恢复后的后缀组成迭代区间，流式重放，避免递归复制累计全状态。恢复、修正和调参统一采用当前活动参数；旧快照必须匹配 policy hash 才可用。`ledger_retraction_state()` 使用当前 SQL 修正索引供历史接口读取。

Session 创建时绑定稳定 `question_id`；普通旧 `session.create` 以创建提交当时的映射解析。首次 bootstrap 的 UID-only 条目没有可靠身份时保留 `unresolved`。详情的权威 `entries` 含 `entry_id`、`question_id`、`uid_at_creation`、当前 UID、source、availability 和 feedback_submitted；人工 `/api/session/bind` 追加 `session.items_bind`，不重写旧提交。已有 Session 的 UID-only 反馈只在其绑定条目内解析，不能查询全局当前 UID 代替身份。

历史列表的摘要模式只读取本批提交载荷并裁剪字段，修正状态由 SQL 索引提供；前端按 `before_seq` 分批请求。单条详情再读取完整提交；正文更新只取该提交引用的前后 blob。新网页正文编辑把节级短差异固定在 `change_summary`，旧版本或缺失 blob 不补写、不取当前正文冒充旧值。题目移动新提交固定 `from_category` 与 `to_category`，旧提交缺值时保持缺失。

历史领域入口 在追加前校验目标：反馈修正必须指向存在的 `review.batch_submit` 和合法 `target_review_index`，Session 修正必须指向链上出现过的 Session，`state.restore` 的 seq 必须存在。无效请求返回 400，不写脏 commit。对应回归测试在 `tests/test_history_projection.py`。

---

## 6. 工作区自检

`omrs/workspace_sync.py` 在服务启动后立即扫描，之后每 10 分钟扫描一次。扫描使用 `workspace_fingerprint` 比较：

- `metadata_hash`：结构化 YAML 字段哈希。
- `content_hash`：完整 Markdown 文本哈希。

规则：

- 仅正文变化：追加 `question.content_update`，当前 Markdown 与 commit 同事务存入 `blobs`，再更新 fingerprint。
- YAML 结构化字段变化：写 `question.metadata_update_external`，当前 Markdown 与 commit 同事务存入 `blobs`。
- 文件移动或改名：通过 `_omrs_id` 写 `question.move_external`；若结构化字段也变化，另记 `question.metadata_update_external` 并存新正文。
- 新增 Markdown 且缺少 `_omrs_id`：分配 `OP-*` 并写 `question.create_external`，当前 Markdown 与 commit 同事务存入 `blobs`。
- 文件消失：写 `question.archive_external`。
- 题目库主动删除：先确认正文可取回，暂存 Markdown 后写 `question.archive`；失败恢复文件，成功后重建投影与完整 `workspace_fingerprint`。指纹移除已归档题目，避免后续扫描重复追加外部归档事件。
- 重复 UID、重复 `_omrs_id` 等冲突不会静默覆盖，会写入扫描状态并返回冲突。

扫描先核对已知题目的当前文件、投影旧哈希与旧 blob。若旧 blob 缺失且文件已变化，或旧 blob 哈希/身份损坏，该题跳过写入并报告冲突；其他题仍可扫描。这样不会把不可验证的旧正文覆盖成新哈希。标签、网页编辑、移动和删除也在各自写入前做同样的正文保全检查。

手动触发入口：`POST /api/workspace/scan`。

---

## 7. 旧数据迁移

首次没有 `ledger.db` 时，`omrs/migration.py::ensure_ledger_bootstrap()` 会：

1. 备份旧 CSV、config 和 Markdown 文件清单到 `错题/.omrs/legacy_backup/<时间戳>/`。
2. 为现有题目注入 `_omrs_id` 并补当前必需的 YAML 字段；原有 `页码` 原样保留，没有该字段的题目不新增空页码。
3. 创建 `GENESIS`。
4. 创建 `legacy.bootstrap`，导入题目结构、mastery 快照、sessions 快照和旧 history。
5. 重建投影并更新 fingerprint。

仓库内可跟踪的手动迁移入口是 `python3 omrs_engine.py --vault <隔离副本路径> scan`：它调用 `build_index()` 完成首次迁移、工作区扫描和投影重建，**会写入**副本。先在静止状态下取得完整一致的 Vault 备份，再在副本执行；旧迁移生成的 `legacy_backup/` 只含 CSV、配置与 Markdown 文件清单，不是完整恢复备份。源码仓库不提供只读迁移审计命令。

旧 history 缺少完整来源上下文，迁移后按 legacy 展示；从 v1.1.0 后的新反馈开始严格记录来源。

---

## 8. 恢复边界

Ledger 的 `state.restore` 可恢复目标节点的题目结构化状态、熟练度、调度、Session 和统计；它不重写 Markdown 正文，也不恢复展示板、助手、草稿、收件箱或标注集的独立存储。

Markdown 正文另按 §10 入账：

- 已存入 `blobs` 的完整 Markdown 版本含题干、答案、错因、备注、排版、LaTeX 与图片引用文本，可列出和取回；活动题目可显式还原到属于该题的已有版本。还原前同时核对 blob 哈希和正文中的 `_omrs_id`，不符时不修改文件或 Ledger。
- 附件图片二进制不在 `blobs` 中。外部删除文件前若该正文从未入账，无法仅凭 Ledger 还原；已归档题目可查询正文版本，但正文还原接口只接受活动题目。旧哈希缺失时不会拿当前正文伪造历史版本。
- 网页编辑通过原子写和 fingerprint 同步减少重复外部变更提交；写前发现未入账的文件修改时，只有投影旧正文可从 blob 验证，才记录当前版。正文版本恢复与结构化 `state.restore` 是两个独立操作。

## 9. 追加原子性与写入来源

`append_commit_in_db` 在读链头之前执行 `BEGIN IMMEDIATE` 拿到 SQLite 写锁，读链头、插入、回填 `commit_id`、存 blobs 在同一事务里提交；`reserve_operation_id` 的计数同样如此。连接一律带 `busy_timeout=5000`，别的线程或进程在超时内等待，不会读到同一个链头而分叉。连接已处于调用方开启的事务时沿用该事务。`verify_ledger` 另外校验每个 blob 的内容与哈希一致。

写入来源：`api`（用户经界面或接口）、`self_check`（工作区扫描发现的外部修改）、`migration`、`system`，以及 `agent`——`omrs/actor.py` 的 `agent_actor(...)` 上下文里，原本记为 `api` 的 commit 改记 `agent`，payload 加 `_agent: {conversation_id, run_id, tool_call_id}`（参与哈希，投影忽略）。按运行撤销产生的逆操作在 `revert_marker(...)` 上下文里，payload 加 `_revert: {run_id, commit_id}`。见 `AI/agent.md` §9。

## 10. 正文入账

`blobs(hash, content, created_at)` 存题目 Markdown 的全文，哈希是 UTF-8 正文的 sha256；commit 只引用哈希。录入题目时，`question.create` 与当前正文 blob 在同一事务提交；若 Ledger 提交失败，已写出的 Markdown 和附件保留为可能的唯一副本，供后续核查与扫描。网页修改正文或结构化字段时，`question.content_update` / `question.metadata_update` 的前后版本随 commit 入账；工作区扫描发现外部新增、正文变化或结构化字段变化时，当前版本随对应 commit 入账。网页迁移题目先保全旧正文，再把新正文随 `question.move` 入账；删除前必须确认最后一版能从 blob 逐字取回。`question.content_backfill` 记录增量补齐的正文版本，投影不处理它；历史补回另带 `historical:true`。

服务启动时在监听请求和启动工作区扫描前调用 `backfill_missing_content`：仅检查活动题当前投影哈希所指的缺失 blob；文件安全路径、`_omrs_id` 和正文哈希都与投影一致才补入。已有 blob 内容与哈希不符时不覆盖，冲突跳过并报告；已有正确 blob 或重复启动不新增回填提交。`python3 omrs_engine.py --vault /path/to/vault content-audit --json` 用同一只读 SQLite 事务盘点活动题、当前缺 blob、文件/投影冲突和历史缺口，兼容升级前的 Ledger 表结构，不初始化或迁移 Ledger，也不输出正文；缺库时不创建错题目录。生命周期租约可建立独立的维护锁文件；存在待恢复 journal 时拒绝盘点，须先由正常启动收束恢复。旧版本缺口只表示对应哈希不可从当前 `blobs` 取回；回填当前文件不会生成该旧版本。

写文件前对齐：`ensure_content_recorded` 先核对 `_omrs_id` 与投影旧正文。旧 blob 缺失但文件哈希仍与投影一致时可补存；旧 blob 缺失且文件已改，或 blob 内容哈希/身份不符时拒绝该题写入。验证通过后，若文件正文有未入账的变化（例如刚在 Obsidian 里改过），以 `self_check` 补记这一版，再做本次写入；调用方给了 `expected_content_hash` 而对不上时抛 `ContentConflict`（HTTP 409）。正文版本列表的 `available` 也要求 blob 哈希及 `_omrs_id` 都正确。历史、取回与还原的接口见 `AI/api.md`。

### 从本机可靠副本补回历史正文

`python3 omrs_engine.py --vault /path/to/vault content-recover --manifest /private/manifest.json` 默认只核验并输出 JSON，不写数据库、不初始化配置、收件箱或旧 Schema。加 `--apply` 后，`omrs/content_recovery.py` 在生命周期租约、写锁和同一 SQLite 写事务内补入缺失 blob，并追加一条带清单哈希的 `question.content_backfill`。已有正确版本直接跳过，重复运行不新增提交；已有损坏 blob、原始提交哈希损坏、身份或引用不一致时拒绝整批。任何事务故障全部回滚。命令不会修改当前 Markdown、元数据、学习状态、Session 或旧提交；已归档题也按稳定身份补回。待恢复 journal 或缺失正文引用索引时拒绝执行，先完成正常恢复或核查。

清单为 `{"version":1,"items":[{"question_id":"OP-000001","hash":"<64位小写SHA256>","first_referenced_seq":2,"file":"blobs/version.md"}]}`。原始提交必须确实引用该题的哈希，且序号与可重建索引的首次引用一致。文件以清单目录为根，接受内部相对普通文件路径，拒绝越界和符号链接。按历史文本读取规则转换 CRLF/CR 为 LF 后，正文哈希和 YAML `_omrs_id` 必须同时匹配。清单最多 2 MiB、100 个不同哈希，单批正文最多 16 MiB；大批次显式拆分。正文和原始来源路径只留本机私有材料，审计提交与 CLI 回执不包含它们。引用抽取由 `ledger.content_ref_pairs()` 供索引、盘点和补回共同使用。回归入口为 `tests/test_content_recovery.py`。

## 草稿创建的追溯与恢复

草稿通过调用创建题目入口时，question.create 的 payload 顶层加入 `_draft:{draft_id,conversation_id}` 后再追加与计算哈希；人工入口为 api，agent_actor 内转换为 agent 并保留 `_agent`。建草稿、编辑和丢弃不追加 Ledger。创建提交是入库恢复的事实依据：草稿状态写回或投影重建失败后，重试先找到原提交，不重复建题，且不删除已被 Ledger 引用的文件。

历史摘要将 `_draft.draft_id` 投影为 `payload.source_draft_id`；单条详情附创建时间、消息、学习摘要和最近来源调用，供列表范围之外的节点独立显示。运行记录详情以同一标识关联 `question.create`，不新增或改写学习 commit。MCP 工具调用的独立 `runtime.db` 不参与修正或状态还原；来源关联读取失败不影响原学习详情。历史的搜索与日期筛选先于游标分页，撤销状态仍基于完整链，见 `AI/api.md`。

## 11. 活动配置与容量验证

配置与投影的事务发布见 `AI/data.md` §8。`config.tuning_update` 保存规范化算法参数、变更键名和脱敏重算摘要，`config.update` 只存变更键名与 revision；均不保存密钥。配置镜像失败不会回退已生效数据库，返回 `mirror_pending`；监听前处理恢复或冲突。

容量门禁：`python3 tests/bench_data_runtime.py`。固定种子生成 10,000 个合法题目 Markdown、blob 和 100,000 条反馈，分别在独立进程测快照读取、启动磁盘流程、全量重放、调参、修正、state.restore、普通反馈及 CSV 导出；Linux 记录 VmHWM，每条路径限制 768MiB。普通反馈额外把全量重放替换为失败断言。耗时与 P50/P95 是环境测量结果，写入任务日志，不作为模块文档的固定性能承诺。


## 外部 MCP 复习计划创建

omrs/session_operations.py 在新鲜链头、活动配置和 SQL 投影检查后同事务追加 source=mcp 的 session.create、发布 Session 投影并写 op_results 技术回执。输入绑定稳定 question_id，创建不更新答题或熟练度。投影失败整体回滚，清理内存缓存；MCP 技术回执不参与学习撤销和 state.restore，详情见 AI/mcp-storage.md。Web/内置助手原有创建调用保持兼容。
