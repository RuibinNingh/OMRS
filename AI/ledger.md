# Ledger 架构

> **速查**
> - 职责：不可变提交链、投影缓存、历史修正与迁移边界
> - 入口：`omrs/ledger.py`、`omrs/projections.py`
> - 不变量：提交只追加不改写，修正以新的 commit 表达；追加在 `BEGIN IMMEDIATE` 事务里；已入账的题目 Markdown 版本存进 blobs，commit 只引用哈希
> - 必跑测试：`tests/test_history_projection.py`、`tests/test_sessions_feedback.py`、`tests/test_ledger_concurrency.py`、`tests/test_agent_tools.py`
> - 相关：`AI/data.md`、`AI/frontend/records.md`、`AI/agent.md`

> 题目结构化元数据、反馈、熟练度与 Session 以 `错题/.omrs/ledger.db` 为事实源；兼容 CSV 由投影器生成，也可作旧数据迁移输入和调试查看。展示板、助手对话、草稿、收件箱和标注集使用独立存储，不由 Ledger 重放，见 `AI/data.md`。

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
页码:
相关知识点: []
tags:
  - 状态/待攻克
录入日期: 2026-06-12
---
```

旧题首次迁移时会自动补 `_omrs_id` 与缺失的已知字段。正文、答案、备注和 LaTeX/图片引用仍保持 Markdown/Obsidian 兼容。

---

## 4. 投影缓存

`omrs/projections.py` 从提交链重放出以下投影表：

- `question_projection`（含 `suspended` 停用标记）
- `question_knowledge_points`
- `question_labels`（题目用户标记的查询投影）
- `mastery_projection`
- `session_projection`
- `workspace_fingerprint`
- `snapshots`

其中数据库 `snapshots` 表目前只是预留结构，投影器尚未持久化或读取它。`_project_state()` 会在单次重放内对每 100 个 seq 和 `state.restore` 节点保存内存快照；跨请求的 `rebuild_projection()` 仍从完整链重放，这也是 `optimization.md` 记录的性能债。

投影可删除重建；`rebuild_projection()` 会从 Ledger 重新导出兼容 CSV：

- `mastery_data.csv`
- `history_log.csv`
- `sessions.csv`

现有统计、推荐和前端大部分接口仍读取这些兼容 CSV，因此外部响应结构尽量保持稳定。

v1.14.0 的用户标记不另建一条事实链：标记定义保存在
`错题/.omrs/labels.json`，题目归属保存在 Markdown YAML 的 `标记:` 字段。
工作区扫描或网页标记修改产生 `question.metadata_update_external` /
`question.metadata_update`，投影器从提交 payload 的题目元数据重建
`question_labels` 与 CSV `Labels` 列。删除并重建投影时，标记归属随题目元数据
一起恢复；`labels.json` 本身不进入 Ledger。

---

## 5. 反馈与历史修正

`POST /api/feedback` 不再直接修改 CSV，而是追加 `review.batch_submit` commit，再重建投影。每条反馈包含：

- `question_id`
- `uid_at_that_time`
- `session_id`
- `source`
- `is_correct`
- `sub_score`
- `note`
- `occurred_at`
- `recorded_at`

反馈**不会**向题目 Markdown 的 `# 历史` 小节追加行。该小节仍由新题骨架保留，且旧格式解析器仍在兼容旧手工文本，但它不属于结构化复习记录，不能用于推断练习次数、正确率或累计答错次数。

题目库的单题删除先把文件当前正文存入 `blobs`，再删除 Markdown 并追加 `question.archive` commit。投影将该题标记为 archived 并从活动题库/兼容 CSV 排除，既有提交与反馈仍可审计；已入账正文可按 `question_id` 列出并按哈希取回。`/api/question/content/restore` 只接受活动题目的 UID，不直接重建已归档题目。附件图片保留，以免删除其他题共用的文件。

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

修正 commit 不直接写“反向熟练度补丁”。`_project_state()` 保存题目初始 `mastery_baseline` / `question_tag_baseline` 和原始 `review_commits`，并维护：

- `retracted_sessions`
- `retracted_reviews` / `restored_reviews`
- `review_replacements`

遇到 `review.retract`、`review.restore`、`review.replace`、`session.retract` 或 `session.restore` 后，投影器从 baseline 重新播放全部有效 review：被撤销的反馈跳过，恢复后重新采用原反馈，替换则把 replacement 合并到原记录；被撤销 Session 的反馈整体跳过。这样恢复操作会真正重新计算 Mastery、EF、SM-2、标签、累计击杀次数（`kill_count`）和兼容 history，而不是只改变 UI 状态。

`mastery_projection` 的 `kill_count` 是 2026-09 新增列（`NOT NULL DEFAULT 0`），只在 `tag_action == "kill"` 时累加、答错降级时**不**重置，`scheduling.revive_dormant_days()` 据它决定这题下次休眠多久（`algorithm.md` §11）。老库缺列时 `ledger.py::_ensure_schema()` 用 `PRAGMA table_info` 探到缺失后执行 `ALTER TABLE mastery_projection ADD COLUMN kill_count INTEGER NOT NULL DEFAULT 0` 补齐（与 `question_projection.suspended` 同一套做法），所以从旧库直接启动不会报错；老数据一律按「还没击杀过」处理，首次击杀即第 1 次。老 CSV 缺 `Kill_Count` 列同理按 0 读，重放不失败。

`state.restore` 会取目标 `target_seq` 的内存快照；若没有快照，则递归重放到该 seq，再继续处理还原 commit 之后的新提交。`ledger_retraction_state()` 把有效的 Session/反馈撤销集合提供给 `/api/history` 和前端。

`server.py::_history_commit()` 在追加前校验目标：反馈修正必须指向存在的 `review.batch_submit` 和合法 `target_review_index`，Session 修正必须指向链上出现过的 Session，`state.restore` 的 seq 必须存在。无效请求返回 400，不写脏 commit。对应回归测试在 `tests/test_history_projection.py`。

---

## 6. 工作区自检

`omrs/workspace_sync.py` 在服务启动后立即扫描，之后每 10 分钟扫描一次。扫描使用 `workspace_fingerprint` 比较：

- `metadata_hash`：结构化 YAML 字段哈希。
- `content_hash`：完整 Markdown 文本哈希。

规则：

- 仅正文变化：追加 `question.content_update`，把当前 Markdown 存入 `blobs`，再更新 fingerprint。
- YAML 结构化字段变化：写 `question.metadata_update_external`。
- 文件移动或改名：通过 `_omrs_id` 写 `question.move_external`。
- 新增 Markdown 且缺少 `_omrs_id`：分配 `OP-*` 并写 `question.create_external`。
- 文件消失：写 `question.archive_external`。
- 题目库主动删除：删除 Markdown 后写 `question.archive`，并重建投影与完整 `workspace_fingerprint`；后者会移除已归档题目的旧指纹，避免后续扫描重复追加外部归档事件。
- 重复 UID、重复 `_omrs_id` 等冲突不会静默覆盖，会写入扫描状态并返回冲突。

手动触发入口：`POST /api/workspace/scan`。

---

## 7. 旧数据迁移

首次没有 `ledger.db` 时，`omrs/migration.py::ensure_ledger_bootstrap()` 会：

1. 备份旧 CSV、config 和 Markdown 文件清单到 `错题/.omrs/legacy_backup/<时间戳>/`。
2. 为现有题目注入 `_omrs_id` 并补完整 YAML 模板。
3. 创建 `GENESIS`。
4. 创建 `legacy.bootstrap`，导入题目结构、mastery 快照、sessions 快照和旧 history。
5. 重建投影并更新 fingerprint。

手动工具：`python tool/migrate_ledger.py --vault <path>`。

常用选项：

- `--check-only`：只检查现有 Ledger，不创建或迁移。
- `--scan`：迁移/重建后立即执行工作区自检。
- `--report <path>`：写出 JSON 审计报告。
- `--json`：将审计报告打印为 JSON。
- `--write-ai-prompt [path]`：写出 AI 迁移审计提示词，默认路径为 `tool/ledger_migration_ai_check_prompt.md`。

`--write-ai-prompt` 输出用于 v1.1.0 迁移审计的旧模板；其中“正文不做版本控制”的条款不适用于当前正文历史功能，当前行为以 §10 为准。

旧 history 缺少完整来源上下文，迁移后按 legacy 展示；从 v1.1.0 后的新反馈开始严格记录来源。

---

## 8. 恢复边界

Ledger 的 `state.restore` 可恢复目标节点的题目结构化状态、熟练度、调度、Session 和统计；它不重写 Markdown 正文，也不恢复展示板、助手、草稿、收件箱或标注集的独立存储。

Markdown 正文另按 §10 入账：

- 已存入 `blobs` 的完整 Markdown 版本含题干、答案、错因、备注、排版、LaTeX 与图片引用文本，可列出和取回；活动题目可显式还原到其中一个版本。
- 附件图片二进制不在 `blobs` 中。外部删除文件前若该正文从未入账，无法仅凭 Ledger 还原；已归档题目可查询正文版本，但正文还原接口只接受活动题目。
- 网页编辑通过原子写和 fingerprint 同步减少重复外部变更提交；写前发现未入账的文件修改时，先记录当前版。正文版本恢复与结构化 `state.restore` 是两个独立操作。

## 9. 追加原子性与写入来源

`append_commit_in_db` 在读链头之前执行 `BEGIN IMMEDIATE` 拿到 SQLite 写锁，读链头、插入、回填 `commit_id`、存 blobs 在同一事务里提交；`reserve_operation_id` 的计数同样如此。连接一律带 `busy_timeout=5000`，别的线程或进程在超时内等待，不会读到同一个链头而分叉。连接已处于调用方开启的事务时沿用该事务。`verify_ledger` 另外校验每个 blob 的内容与哈希一致。

写入来源：`api`（用户经界面或接口）、`self_check`（工作区扫描发现的外部修改）、`migration`、`system`，以及 `agent`——`omrs/actor.py` 的 `agent_actor(...)` 上下文里，原本记为 `api` 的 commit 改记 `agent`，payload 加 `_agent: {conversation_id, run_id, tool_call_id}`（参与哈希，投影忽略）。按运行撤销产生的逆操作在 `revert_marker(...)` 上下文里，payload 加 `_revert: {run_id, commit_id}`。见 `AI/agent.md` §9。

## 10. 正文入账

`blobs(hash, content, created_at)` 存题目 Markdown 的全文，哈希是 UTF-8 正文的 sha256；commit 只引用哈希。入账的时机：`question.create` 之后（录入的正文）、`question.content_update`（只改正文，payload 有 `before_hash` / `after_hash`）、经 `omrs/content_history.py` 写文件时的 `question.metadata_update`（同样带前后哈希）、工作区扫描发现的只改正文（`self_check`）、删除前的最后一版（`question.archive` 带 `content_hash`）、首次启动时一次性的 `question.content_snapshot`（`source=migration`，`items` 列出每题当前哈希；投影不处理它）。

写文件前对齐：`ensure_content_recorded` 发现文件正文与投影记录的哈希不同（例如刚在 Obsidian 里改过），先以 `self_check` 补记这一版，再做本次写入；调用方给了 `expected_content_hash` 而对不上时抛 `ContentConflict`（HTTP 409）。投影处理 `question.content_update` 时只更新 `content_hash`。历史、取回与还原的接口见 `AI/api.md`。

## 草稿创建的追溯与恢复

草稿通过调用创建题目入口时，question.create 的 payload 顶层加入 `_draft:{draft_id,conversation_id}` 后再追加与计算哈希；人工入口为 api，agent_actor 内转换为 agent 并保留 `_agent`。建草稿、编辑和丢弃不追加 Ledger。创建提交是入库恢复的事实依据：草稿状态写回或投影重建失败后，重试先找到原提交，不重复建题，且不删除已被 Ledger 引用的文件。
