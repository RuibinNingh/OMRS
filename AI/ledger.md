# Ledger 架构

> v1.1.0 起，结构化状态以 `错题/.omrs/ledger.db` 为唯一可信来源。旧 CSV 仍存在，但只作为兼容投影、迁移输入和调试查看。

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

题目库的单题删除会先删除目标 Markdown，再追加 `question.archive` commit。投影会将该题标记为 archived 并从活动题库/兼容 CSV 排除，但既有提交与反馈仍可审计；因为正文不进入 Ledger，删除后的 Markdown 正文无法由 Ledger 恢复。附件图片保留，以避免删掉可能被其他题引用的文件。

题目停用不删除 Markdown，只追加 `question.suspend`；恢复只追加 `question.resume`。两类 commit 都携带 `question_id`、当时 UID、文件路径和可选 `reason`，投影列 `suspended` 与兼容 CSV 列 `Suspended` 据此派生。停用题保留在题库管理列表和历史链中，但从调度、统计、分析、反馈和复习导出中排除；恢复后沿用原有 Mastery/SM-2 状态。

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

遇到 `review.retract`、`review.restore`、`review.replace`、`session.retract` 或 `session.restore` 后，投影器从 baseline 重新播放全部有效 review：被撤销的反馈跳过，恢复后重新采用原反馈，替换则把 replacement 合并到原记录；被撤销 Session 的反馈整体跳过。这样恢复操作会真正重新计算 Mastery、EF、SM-2、标签和兼容 history，而不是只改变 UI 状态。

`state.restore` 会取目标 `target_seq` 的内存快照；若没有快照，则递归重放到该 seq，再继续处理还原 commit 之后的新提交。`ledger_retraction_state()` 把有效的 Session/反馈撤销集合提供给 `/api/history` 和前端。

`server.py::_history_commit()` 在追加前校验目标：反馈修正必须指向存在的 `review.batch_submit` 和合法 `target_review_index`，Session 修正必须指向链上出现过的 Session，`state.restore` 的 seq 必须存在。无效请求返回 400，不写脏 commit。对应回归测试在 `tests/test_history_projection.py`。

---

## 6. 工作区自检

`omrs/workspace_sync.py` 在服务启动后立即扫描，之后每 10 分钟扫描一次。扫描使用 `workspace_fingerprint` 比较：

- `metadata_hash`：结构化 YAML 字段哈希。
- `content_hash`：完整 Markdown 文本哈希。

规则：

- 仅正文变化：只更新 fingerprint，不写入 Ledger。
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

AI 审计提示词要求外部 AI 按 P0/P1/P2 输出问题清单，并重点检查 Ledger 唯一事实源、链校验、`_omrs_id`、投影重建、备份和正文不版本化边界。

旧 history 缺少完整来源上下文，迁移后按 legacy 展示；从 v1.1.0 后的新反馈开始严格记录来源。

---

## 8. 结构化恢复边界

系统可以通过 Ledger 恢复任意时刻的结构化状态、熟练度、调度、Session 和统计。

系统不承诺恢复 Markdown 正文旧版本：

- 题干正文、答案正文、错因笔记、备注正文、排版、LaTeX 和图片引用顺序不进入版本链。
- 如果用户在文件管理器中彻底删除 Markdown，自检可记录题目被外部归档，但无法无损恢复已丢失正文。
- 网页迁移/编辑会尽量通过原子写与 fingerprint 同步避免重复外部变更提交。
