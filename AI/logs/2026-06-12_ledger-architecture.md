# v1.1.0 Ledger 架构升级

## 摘要

- 版本号更新为 `v1.1.0`。
- 新增 `错题/.omrs/ledger.db` 作为结构化状态唯一可信来源。
- 旧 `mastery_data.csv`、`history_log.csv`、`sessions.csv` 降级为兼容投影、迁移输入和调试查看。
- 当前工作区已完成首次迁移，旧数据备份位于 `错题/.omrs/legacy_backup/20260612-220826/`。

## 代码改动

- 新增 `omrs/ledger.py`：SQLite 提交链、规范化 JSON 哈希、commit 追加、operation id、链校验。
- 新增 `omrs/projections.py`：从 Ledger 重建题目、熟练度、Session 投影，并导出兼容 CSV。
- 新增 `omrs/migration.py`：首次迁移、旧数据备份、Markdown `_omrs_id` 注入和模板补全。
- 新增 `omrs/workspace_sync.py`：metadata/content 指纹、人工改名/结构化修改/新增/归档检测、后台扫描。
- 新增 `omrs/question_ops.py`：题目迁移、Markdown 原文读取和保存。
- 新增 `tool/migrate_ledger.py`：手动迁移与校验工具。
- `creation.py`：新题直接生成完整 YAML、`_omrs_id`、最小缺口 UID 和防冲突附件名。
- `feedback.py`：反馈改为追加 `review.batch_submit` 后重建投影。
- `sessions.py`：Session 创建/完成/撤销写 Ledger；旧删除入口兼容为 `session.retract`。
- `server.py`：新增 Ledger verify、工作区扫描、历史修正、题目迁移、Markdown 编辑 API。
- `cli.py`：服务启动后开启立即扫描和 10 分钟后台自检。
- `assets/questions.js` / `omrs_dashboard.html`：题库 List/Gallery 增加编辑入口和纯文本 Markdown 编辑器。
- `assets/schedule.js`：历史页优先展示 Ledger 时间线。

## 新增 API

- `GET /api/ledger/verify`
- `GET /api/question/raw?uid=`
- `POST /api/workspace/scan`
- `POST /api/question/markdown`
- `POST /api/question/move`
- `POST /api/history/review/replace`
- `POST /api/history/review/retract`
- `POST /api/history/review/restore`
- `POST /api/history/session/retract`
- `POST /api/history/session/restore`
- `POST /api/history/state/restore`

## 数据边界

Ledger 可恢复结构化状态、熟练度、调度、Session 和统计。

Markdown 正文、答案正文、备注正文、排版、LaTeX 和图片引用顺序不进入版本链，因此不承诺恢复正文旧版本。

## 验证

- `python -m py_compile ...` 通过。
- `python tool/migrate_ledger.py --vault .` 完成迁移：155 道题、9 个 Session、2 个初始提交。
- `verify_ledger()` 返回 `valid=true`，head 为 `CMT-000002`。
