# 2026-09-29 AI 助手最大输出 Token 设置

## 背景

用户要求：「写一个功能,可以在设置里面调最大输出Token,默认10240」。此前助手每轮模型请求沿用客户端的 4096 默认值，长思考可能使建草稿工具参数截断。本任务为 Codex 完整模式直接实现，不属于进行中的分期执行说明。

## 行为变化

- 「设置 → AI 助手 → 接口」增加「最大输出 Token」，旧配置缺失时显示并使用 10240；保存后新运行的每轮模型请求都发送该上限。连接测试仍使用短请求上限。
- 输入可留空恢复默认值，只接受 1–65536 的整数；页面原地拒绝非法值，配置接口也返回 400。模型服务商自身的上限仍然生效。
- 已开始的运行沿用启动时读取的配置；保存无需重启，对之后的新运行生效。

## 影响文件

- `omrs/common.py`、`omrs/agent/config.py`、`omrs/agent/loop.py`、`omrs/agent/runtime.py`：配置默认值、校验、运行快照与每轮请求传参。
- `assets/app/features/settings/agent.js`、`agent-view.js`：设置页读取、校验、保存与输入控件。
- `tests/test_agent_loop.py`、`tests/test_security.py`、`tests/app/settings.test.mjs`、`tests/e2e/settings.py`：请求传参、配置 API、页面和真实浏览器验证。
- `AI/agent.md`、`AI/api.md`、`AI/data.md`、`AI/frontend/settings.md`、`AI/frontend/architecture.md`、`AI/frontend/shell.md`、根 `README.md`：同步当前行为与验证范围。
- `AI/logs/log.md`：由文档脚本重建索引。

## 验证

已执行：

- `python3 -m unittest tests.test_agent_loop tests.test_security -q`：23 项通过。
- `python3 -m unittest tests.test_agent_draft_tools -q`：14 项通过；运行时出现未关闭 SQLite 连接的资源提醒，测试结果为通过。
- `node --test tests/app/settings.test.mjs`：21 项通过。
- `node --test tests/app/*.test.mjs`：369 项通过。
- `python3 tests/e2e/settings.py`：临时 Vault、随机端口、真实浏览器，59/59 通过；含默认值、保存回读、非法输入和四档助手分区布局。
- `python3 tests/app/run_browser.py`：32/32 通过。
- `python3 tests/check_ui.py`：0 处问题；`python3 tests/check_contrast.py`：58 组检查，0 组不达标。
- `python3 tests/check_docs.py --write-log-index`：已生成任务日志索引；`python3 tests/check_docs.py --diff HEAD`：54 个文档，0 处问题、2 条既有文件大小提醒。
- `python3 tests/visual/run.py --ref HEAD --pages settings --settings-section assistant --themes light,dark --viewports desktop,mobile --out /tmp/omrs-output-tokens-visual`：4/4 有预期差异，页面脚本错误为 0。桌面浅色 0.166%、深色 0.167%，新增控件占用接口区原有第三列；手机浅色 7.931%、深色 7.899%，新增控件单列使后续内容下移。四档均无横向溢出、小点击目标或行内样式。

未执行：真实外部模型请求；当前验证使用模型调用桩、配置 API 与隔离浏览器，不需要生产密钥。
