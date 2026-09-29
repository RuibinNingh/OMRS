# 2026-09-30 OMRS 2.0 P7 旧库迁移兼容

## 背景

用户要求完成 OMRS v2.0.0 升级，P7 需验证旧数据兼容、重复迁移和备份恢复。本切片由 Codex · 完整模式的 GPT-6 Sol / High 子代理在独立工作树实现，基于 P5 主线提交 `2a478d8`；P6 同期仍在其他工作树实施。未接触生产、真实 Vault 或远端。

计划提到的 `tool/migrate_ledger.py` 只存在于主工作区本机，整个 `tool/` 被 `.gitignore` 忽略，Git 跟踪源码和本隔离工作树均无此文件。依照保护已有文件的要求，没有修改或强制入库它；可跟踪的迁移入口是 `omrs_engine.py --vault <隔离副本> scan`。本机忽略工具的 `--check-only` 曾观察到重建投影，不能据其名字认定只读；本切片不使用它验收。

## 行为变化

- 旧 Markdown 首次迁移时，只有原文已有 `页码` 才保留其值；没有页码的旧题不再被补写空 `页码:`。已有题目、答案、错因、图片说明和附件维持原内容。
- 迁移说明改为以仓库可跟踪的 `scan` 命令为准，并明确该命令会写盘，`legacy_backup/` 只是 CSV、配置和文件清单备份，不能当作完整恢复备份。
- 应用版本仍为 v1.35.0；v2.0.0 版本与全仓发布门禁须在 P6 集成后由主代理完成。

## 影响文件

- `omrs/migration.py`：条件保留旧页码，不对无页码旧题新增字段。
- `tests/test_migration_compat.py`：用临时旧 Vault 覆盖带/不带页码、反馈与草稿 note、图片说明、重复扫描，以及静止 Vault 的完整 ZIP 备份恢复。
- `AI/data.md`、`AI/ledger.md`：同步当前迁移与备份契约。
- `AI/plans/v2.0.0/progress.md`、`AI/logs/log.md`：登记独立切片与自动日志索引。

## 验证

已执行：`python3 -m unittest tests.test_migration_compat -q`，4/4 通过；`python3 -m unittest discover -s tests -p 'test_*.py' -q`，398/398 通过；`node --test tests/app/*.test.mjs`，385/385 通过；`python3 tests/check_docs.py --diff 2a478d8`，67 份文档 0 处问题（3 条既有体量提醒）；`git diff --check` 通过。专项备份恢复在两个临时 Vault 间运行，无活动写入者，核对 Markdown、附件、分类锚点、配置、agent/drafts/inbox/annotate 数据库哈希及 Ledger 链。

未执行：本切片未改页面，UI、对比度和浏览器门禁留待 P7 主线全仓验证；Android/iOS 真机软键盘及版本同步也待 P6 合并后执行。用户目前无真机，不能据桌面模拟宣称真机已通过。

## 主线集成复核

P6 完成后，主代理把独立切片 `716568d` 合入主线，保留历史、用量文档与既有计划进度。主线执行 `python3 -m unittest tests.test_migration_compat -q`（4/4）、`python3 -m unittest discover -s tests -p 'test_*.py' -q`（408/408）、`node --test tests/app/*.test.mjs`（387/387）、`python3 tests/check_docs.py --diff HEAD`（67 份 0 处问题）与 `git diff --cached --check`（通过）。上述测试均使用临时旧 Vault；Python 全套输出既有资源未关闭提醒和测试请求中断日志，退出码为 0。版本、全仓浏览器与真机验收仍按 P7 后续切片执行。
