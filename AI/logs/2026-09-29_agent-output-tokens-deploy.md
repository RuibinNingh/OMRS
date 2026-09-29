# 2026-09-29 AI 助手输出上限合入与生产发布

## 背景

用户原话：「合并生产,提交GitHub」。承接 `6e9afc2` 的「最大输出 Token」功能。执行者 Codex · 完整模式；用户已授权合并、生产切换与 GitHub 推送。本轮是功能交付后的新部署任务，单独记录。

## 发布前事实

- 工作分支 `codex/agent-output-tokens` 比本地 `main` 多功能提交；本地 `main` 又比抓取后的 GitHub `origin/main` 多一个已提交的项目现状文档提交。三者是线性历史，可快进合入并推送。
- 发布前 `omrs.service` 从 `/root/workspace/releases/omrs-e339183` 运行 v1.33.1，真实 Vault 为 `/root/workspace/apps/OMRS`，本地 API 返回 232 道题，AI 助手没有活动运行。
- 本轮把版本更新为 v1.34.0，发布提交为 `82d396f`。

## 行为变化

本地 `main` 快进合入 `6e9afc2` 和 `82d396f`。固定发布目录 `/root/workspace/releases/omrs-82d396f` 从该提交的 `git archive` 生成；生产 `omrs.service` 的工作目录与入口改为该目录，真实 Vault 与 8471 端口保持原值。服务返回 v1.34.0，设置接口对旧配置显示默认 `agent_max_output_tokens=10240`；既有配置文件本身无须写入新键。

切换前确认助手无活动运行，将 systemd drop-in 原文存入 `/root/workspace/backups/recycle/agent-output-v134-20260929T180808/10-release.conf.before`。停止服务后把完整 `错题/` 归档到同目录 `vault-before.tar`，另存每个文件的 SHA-256 清单；780 个文件、209013459 字节、5 个 SQLite 数据库的 `quick_check` 全部通过。备份目录权限 0700、归档 0600；旧发布目录 `omrs-e339183` 保留。替换 drop-in、`daemon-reload`、启动后健康检查通过，停机约 0.97 秒。

回退代码时将 drop-in 恢复为备份的原文，重载并重启服务，再检查 v1.33.1 健康状态；真实数据归档只在确认数据损坏时专项恢复，不能覆盖发布后新增题目。

## 影响文件

- `omrs/version.py`、`omrs_dashboard.html`、根 `README.md`、`AI/README.md`、`AI/changelog.md`：版本同步与摘要。
- `AI/frontend/shell.md`：记录侧栏版本展示的当前契约。
- `AI/environment.md`：更新实际生产目录、版本和备份路径。
- 本日志与自动生成的 `AI/logs/log.md`：发布记录。

## 验证

发布前已执行：

- `env -u OMRS_SYSTEMD_SERVICE python3 -m unittest discover -s tests -p 'test_*.py' -q`：351 项通过；运行中有现有资源提醒和测试服务的断连输出，退出码 0。
- `node --test --test-reporter=dot tests/app/*.test.mjs`：369 项通过。
- `python3 tests/check_ui.py`：0 处问题；`python3 tests/check_contrast.py`：58 组对比，0 组不达标。
- `python3 tests/check_docs.py --write-log-index`：已生成索引；`python3 tests/check_docs.py --diff HEAD`：54 个文档、0 处问题，另有 2 条已有文件大小提醒。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/visual/run.py --ref main --pages settings --settings-section assistant --themes light,dark --viewports desktop,mobile --out /tmp/omrs-v134-visual`：4/4 有预期差异，页面脚本错误为 0。桌面浅色 0.169%、深色 0.170%，新增控件占用接口区第三列且侧栏版本更新；手机浅色 7.931%、深色 7.899%，新增控件单列使后续内容下移，截图无横向溢出。

发布目录已执行：关键代码和页面文件 8/8 与合并后 `main` 一致；以临时 Vault、随机端口运行 `tests.test_agent_loop` 与 `tests.test_security` 共 23 项通过，`tests/e2e/settings.py` 59/59 通过。

生产已执行：

- `omrs.service` 为 active/running，`ExecMainStatus=0`，主进程从 `omrs-82d396f` 启动；切换后的错误级 journal 无记录。
- 本地只读 API：`/api/status` 返回 ok、v1.34.0、232 道题，与切换前相同；`/api/config` 返回最大输出 10240；助手活动运行数为 0。两份生产设置页 JS 与发布目录 SHA-256 一致。
- 真实生产浏览器只读检查桌面 1440px 和手机 390px：都显示 v1.34.0 与 10240；无页面脚本错误、横向溢出或写请求。
- 备份前的 780 个用户文件均仍存在；除 `ledger.db` 外 SHA-256 全部一致。对该数据库 12 张表逐表比较，只有 `workspace_fingerprint.last_seen_at` 和 `workspace_scan_status.last_scan_at` 随启动扫描更新，行数与其他列一致。
- 发布记录更新后再次运行 `python3 tests/check_docs.py --write-log-index` 与 `python3 tests/check_docs.py --diff HEAD`：54 个文档、0 处问题，另有 2 条已有文件大小提醒；`git diff --check` 通过。

未执行：真实外部模型调用和生产写入测试。功能层已用隔离配置、模型调用桩及真实浏览器验证；本次发布不消耗模型额度，也不创建测试题。

GitHub 推送结果在完成后补记。
