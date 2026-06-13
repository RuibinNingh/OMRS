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

- `question_projection`
- `question_knowledge_points`
- `mastery_projection`
- `session_projection`
- `workspace_fingerprint`
- `snapshots`

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

历史修正只追加新 commit：

- `POST /api/history/review/replace`
- `POST /api/history/review/retract`
- `POST /api/history/review/restore`
- `POST /api/history/session/retract`
- `POST /api/history/session/restore`
- `POST /api/history/state/restore`

`POST /api/session/delete` 兼容旧前端，但内部语义改为 `session.retract`。

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
