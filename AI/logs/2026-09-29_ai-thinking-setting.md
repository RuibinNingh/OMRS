# 2026-09-29 AI 识图思考开关

## 背景

用户纠正前次交付：「不,在设置里面AI识图,加一个选项是否启用思考」。执行者：Codex，完整模式；基线 `20107db`。开工前已有 `AI/logs/log.md` 修改、两份未跟踪日志和 `.playwright-mcp/`，均予保留。本任务是前次已交付后的新需求，单独记录。

## 行为变化

「设置 → AI 识别」新增「启用思考」开关，默认关闭，保存到 `config.json` 的布尔键 `ai_thinking`，保存后立即生效。`deepseek-flash` 的 AI 识图请求统一按开关发送 `thinking:{type:"enabled"}` 或 `thinking:{type:"disabled"}`，覆盖提取、分类、框选模型调用与助手的图片转述、看图追问；不改变 AI 助手主模型。其它模型不发送未验证的思考参数，沿用服务商默认行为，设置页直接说明此范围。非布尔配置提交返回 400。此前仅文字提取写死关闭思考的策略已移除。

## 影响文件

- `omrs/common.py`、`omrs/server.py`、`omrs/ai_assist.py`：默认值、输入校验及识图请求的统一参数。
- `assets/app/features/settings/ai-view.js`、`ai.js`：开关展示、读取与保存。
- `tests/test_ai_assist_taxonomy.py`、`tests/test_inbox.py`、`tests/test_security.py`、`tests/app/settings.test.mjs`、`tests/e2e/settings.py`：请求参数、配置和页面验证。
- `tests/visual/run.py`：增加 `--settings-section`，使前后截图能比较指定设置分区。
- `AI/api.md`、`AI/data.md`、`AI/inbox.md`、`AI/agent.md`、`AI/environment.md`、`AI/frontend/settings.md`、`AI/frontend/create.md`、`AI/frontend/architecture.md`、根 `README.md`：同步用户入口、配置契约、测试与视觉工具。
- `AI/logs/log.md`：由脚本生成本日志索引；原有未提交索引变动不纳入本任务提交。

## 验证

- 已执行：`python3 -m unittest tests.test_ai_assist_taxonomy tests.test_inbox tests.test_security`，39/39 通过；收件箱旧测试有三条未关闭文件的 `ResourceWarning`。
- 已执行：`node --test tests/app/settings.test.mjs`，20/20 通过；`node --test tests/app/*.test.mjs`，366/366 通过。
- 已执行：`env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/settings.py`，临时 Vault、随机端口及真实 Chromium，52/52 通过，含开关默认值、保存与回读；无页面脚本错误。
- 已执行：`env -u OMRS_SYSTEMD_SERVICE python3 tests/app/run_browser.py`，32/32 通过。
- 已执行：`python3 tests/check_ui.py`，全仓五类违规计数均为 0；`python3 tests/check_contrast.py`，58 组对比度均达标。
- 已执行：`python3 -m compileall -q omrs/ai_assist.py omrs/common.py omrs/server.py`，通过。
- 已执行：`env -u OMRS_SYSTEMD_SERVICE python3 tests/visual/run.py --ref HEAD --pages settings --settings-section ai --out /tmp/omrs-thinking-ai-visual`，四档均有预期差异，无脚本错误；桌面浅/深 1.511%/1.565%，手机浅/深 15.239%/15.262%。差异仅为新增开关、说明和下方控件纵向移动，手机全页截图因高度变化而有较大像素差。目视桌面浅色和手机深色；四档审计均无横向溢出、过小点击目标或行内样式。
- 已执行：当前配置的 `deepseek-flash` 用合成白图实测开关两档；开启返回 63 个思考 token，关闭后无思考内容，均答「白色」。未发送真实题目图片；极小样本不代表实际提取速度或质量。
- 已执行：`python3 tests/check_docs.py --write-log-index`；`python3 tests/check_docs.py --diff HEAD`，检查 54 个文档、0 处问题，另有 2 条既有体积提醒。
- 未执行：真实用户题图的质量与耗时评估；本次不读取真实错题数据。功能提交阶段未做生产发布或服务重启，后续单独授权后的结果见下。

## 部署

用户随后明确授权上线。生产原发布为 `omrs-ceba925`，服务 active、`NRestarts=0`，助手 25 次运行全为 done，收件箱 113 个 job 全为 done，草稿无 job；工作区扫描 0 变更、0 冲突。已提交源码 `ffccf6b` 归档到固定目录 `/root/workspace/releases/omrs-ffccf6b`，在该目录用系统 Python 跑关键单测 39/39、Node 设置测试 20/20，临时 Vault 的 HTTP 冒烟确认服务正常、`ai_thinking` 默认关闭、控件文件可提供。

停主服务后归档真实 `错题/` 到 `/root/workspace/backups/recycle/ai-thinking-20260929T041052Z/vault-before.tar`（186531840 字节），保存原 `10-release.conf`、文件哈希及数据库表行数基线。切换 systemd drop-in 并重启主服务，若健康检查失败的脚本会恢复旧指向；本次无需回退。框选检测服务未重启，PID 保持 512746。

上线后 `omrs.service` active/running、PID 730077、`ExecMainStatus=0`、`NRestarts=0`，TCP 8471 `/api/status` 正常，当前版本号仍为 v1.33.0；两份设置 JS 的 HTTP 内容与发布目录逐字节一致。730 个非数据库文件哈希一致，5 个数据库 `quick_check` 为 ok、全部表行数一致；近期错误级 journal 为空。未登录远端模拟访问配置、收件箱、助手三个接口均为 401。

生产只读 Chromium 四档（桌面/手机 × 浅/深）均看到「启用思考」默认关闭，无脚本错误、横向溢出或写请求；截图及记录在 `/tmp/omrs-thinking-production-browser/`。另用合成英文题图通过生产 `/api/ai-recognize` 发一次 `question_text` 请求，正确返回 `Find x if x + 2 = 5.`；未使用真实题图或修改配置。机器验收记录在备份目录 `verification.json`。未推送 Git 远端。

回退只需恢复备份的 `10-release.conf.before`、执行 `systemctl daemon-reload` 并重启主服务；旧 `omrs-ceba925` 发布目录保留。不要用旧 Vault 覆盖上线后的数据。下一步由用户刷新页面，在「设置 → AI 识别」切换思考并保存；无需再次重启。
