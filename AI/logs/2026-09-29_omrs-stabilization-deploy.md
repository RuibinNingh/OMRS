# 2026-09-29 OMRS v1.35.0 生产部署与 GitHub 推送

## 背景

用户原话：「部署一下生产,提交GitHub」。本任务由 Codex · 完整模式执行，承接 `codex/omrs-stabilization` 的三个提交 `15301b8`、`0130415`、`c94e459`。用户在本轮单独授权生产部署与 GitHub 推送；此前本地实现日志为 `2026-09-29_omrs-stabilization.md`。

## 发布前事实与备份

发布前 `omrs.service` 从 `/root/workspace/releases/omrs-82d396f` 运行 v1.34.0，真实 Vault 为 `/root/workspace/apps/OMRS`，在线模型 `v2-20260929-b` 与受管指针一致。用户题目只读审计为活动题 237、当前缺 blob 24、文件冲突 0、旧版本缺口 63；24 个当前缺口都能从身份与哈希匹配的当前 Markdown 安全回填。助手无活动运行，收件箱、草稿、助手的后台任务没有运行或排队项，受管模型操作为 done。

本地 `main` 从 `c2dee40` 快进到 `c94e459`，原工作区未跟踪的 `.playwright-mcp/` 原样保留。固定发布目录 `/root/workspace/releases/omrs-c94e459` 由 `git archive` 生成，863 个跟踪文件与提交工作树逐字节一致；在该目录用系统 Python、临时 Vault 跑正文、收件箱、模型控制与标注测试 **63/63** 通过。

停止主服务后，在 `/root/workspace/backups/recycle/omrs-stabilization-v135-20260929T131104Z` 保存旧 drop-in 与完整 `错题/` 归档。目录权限 0700，归档和清单 0600；归档含 793 个文件、210716931 字节，SHA-256 为 `ef46cebc845efe145cdabac9bdbb734dbd1686850de022a3c87dbff57c0467cd`。逐文件哈希与归档内文件比对一致，归档前后真实 Vault 文件哈希一致；5 个 SQLite 数据库的 `quick_check` 均为 ok。备份目录内保留 `content-audit-before.json`、`file-hashes.json`、`db-checks.json`、`backup-summary.json` 与发布后核验报告。

## 行为变化

仅将主服务 systemd drop-in 的工作目录和入口改为 `/root/workspace/releases/omrs-c94e459`，执行 `daemon-reload` 并启动 `omrs.service`。真实 Vault 路径、8471 端口、Nginx、检测服务及模型配置均未改变。v1.35.0 在监听前自动补齐 24 个当前正文 blob，新增 1 条回填提交；63 个旧版本缺口没有用当前正文代填。

生产 API 返回 v1.35.0、237 道题。回填后的只读审计为当前缺 blob **0**、文件冲突 **0**、历史缺口 **63**；Ledger 链校验 `valid=true`，提交数 691。与备份相比，255 份 Markdown 哈希全部不变，另外 532 个非数据库文件不变；唯一变化的非数据库文件为生成的 `.omrs/mastery_data.csv.bak.3`，启动扫描轮转后与当前 `mastery_data.csv` 内容完全一致。5 个数据库再次 `quick_check=ok`，表行数只有 Ledger 的 blobs 增 24、commits 增 1；收件箱与标注旧库的 `revision` 列已存在且没有空值或负值。

主服务为 active/running、`NRestarts=0`、`ExecMainStatus=0`，错误级 journal 无记录。检测服务保持 active/running，在线模型仍为 `v2-20260929-b`，SHA-256 `f62581b7c28353d5d7799973018a6986e706cd7dcf4fb43ccd10972be4a4c7c3`、输入 640、置信度 0.1，受管指针匹配；独立内容验收状态为 missing，本次未触发模型切换或评测。

## 验证

- 发布目录定向 Python：`env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL /usr/bin/python3 -m unittest tests.test_content_integrity tests.test_inbox tests.test_traincontrol tests.test_annotate -q`，**63/63** 通过。
- 生产只读接口：`/api/status` v1.35.0、237 道题；`/api/ledger/verify` 返回 `valid=true`、错误为空；`content-audit --json` 返回 237/0/0/63；模型管理页身份与 `/health` 一致。
- 真实浏览器在桌面 1440px、手机 390px 各检查仪表盘、录入、助手、展示板、训练、标注，共 **12/12** 路径通过；无脚本错误、横向溢出或业务写请求，训练页显示真实在线模型。展示板预览使用不写数据的 `POST /api/export` 生成 HTML；首次全拦 POST 时预览未加载，单独放行此接口后桌面和手机均复验通过。5 份关键前端资源与发布目录哈希一致。
- 备份与发布后文件、数据库和浏览器核验分别记录在上述备份目录的 `verification.json`、`browser-summary.json` 等文件；最新只读审计再次确认当前缺口为 0。

## 回退与未执行事项

代码回退可把备份目录中的 `10-release.conf.before` 恢复到 `/etc/systemd/system/omrs.service.d/10-release.conf`，执行 `systemctl daemon-reload` 后重启主服务，并复核版本和在线模型。旧 `omrs-82d396f` 发布目录保留；真实 Vault 的备份仅用于专项数据恢复，不能整目录覆盖发布后新增内容。已补齐的 blob 与回填提交可保留，重复启动不会新增相同回填。

未执行真实用户数据写入试验、付费模型调用、旧版本缺口恢复或模型切换。16:59 的旧模型操作仍无法归因具体操作者，结论保留在前次任务日志。

## GitHub 推送

发布记录提交 `c079cef` 前执行 `python3 tests/check_docs.py --write-log-index`、`python3 tests/check_docs.py --diff HEAD` 与 `git diff --check`；文档检查为 57 份、0 处问题、2 条既有大文件提醒，差异检查退出码为 0。随后 `git fetch origin main` 确认远端 `c2dee40` 是本地 `main` 的祖先，执行 `git push origin main` 成功，远端从 `c2dee40` 快进到 `c079cef`。本节与计划进度的最终收尾另行提交并再次推送；最终远端指针以推送后 `git ls-remote origin refs/heads/main` 为准。

## 影响文件

- `AI/environment.md`、`AI/training/README.md`：同步当前发布目录、备份与实际在线模型身份。
- `AI/plans/omrs-stabilization/progress.md`：登记生产回填、验收与下一步。
- 本日志及自动生成的 `AI/logs/log.md`：记录生产部署和推送证据。
