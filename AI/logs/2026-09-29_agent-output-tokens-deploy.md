# 2026-09-29 AI 助手输出上限合入与生产发布

## 背景

用户原话：「合并生产,提交GitHub」。承接 `6e9afc2` 的「最大输出 Token」功能。执行者 Codex · 完整模式；用户已授权合并、生产切换与 GitHub 推送。本轮是功能交付后的新部署任务，单独记录。

## 发布前事实

- 工作分支 `codex/agent-output-tokens` 比本地 `main` 多功能提交；本地 `main` 又比抓取后的 GitHub `origin/main` 多一个已提交的项目现状文档提交。三者是线性历史，可快进合入并推送。
- 发布前 `omrs.service` 从 `/root/workspace/releases/omrs-e339183` 运行 v1.33.1，真实 Vault 为 `/root/workspace/apps/OMRS`，本地 API 返回 232 道题，AI 助手没有活动运行。
- 本轮把版本更新为 v1.34.0；发布目录、数据备份、切换与验收结果在执行后补记。

## 行为变化

待生产验收后补记。

## 影响文件

- `omrs/version.py`、`omrs_dashboard.html`、根 `README.md`、`AI/README.md`、`AI/changelog.md`：版本同步与摘要。
- `AI/frontend/shell.md`：记录侧栏版本展示的当前契约。
- 本日志与自动生成的 `AI/logs/log.md`：发布记录。

## 验证

发布前已执行：

- `env -u OMRS_SYSTEMD_SERVICE python3 -m unittest discover -s tests -p 'test_*.py' -q`：351 项通过；运行中有现有资源提醒和测试服务的断连输出，退出码 0。
- `node --test --test-reporter=dot tests/app/*.test.mjs`：369 项通过。
- `python3 tests/check_ui.py`：0 处问题；`python3 tests/check_contrast.py`：58 组对比，0 组不达标。
- `python3 tests/check_docs.py --write-log-index`：已生成索引；`python3 tests/check_docs.py --diff HEAD`：54 个文档、0 处问题，另有 2 条已有文件大小提醒。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/visual/run.py --ref main --pages settings --settings-section assistant --themes light,dark --viewports desktop,mobile --out /tmp/omrs-v134-visual`：4/4 有预期差异，页面脚本错误为 0。桌面浅色 0.169%、深色 0.170%，新增控件占用接口区第三列且侧栏版本更新；手机浅色 7.931%、深色 7.899%，新增控件单列使后续内容下移，截图无横向溢出。

发布目录和生产验收待执行后补记。
