# 2026-10-01 MCP 设置界面打磨

## 背景

用户原话：「重设计设置里面MCP相关的UI」「打磨精致一点」「先给我一个草稿」，展示草稿后用户要求「执行修改」。执行者 Codex，完整模式；基线 `bec821d`，开工工作区干净。属于 `AI/plans/mcp-integration/plan.md` 的 P4 后续 U1，单个 UI 垂直切片交付。

草稿已通过 25 项交互检查，本批将其方向落在实际设置页，沿用原生 ES Module、共享对话框、图标、控件和设计 token，不新增依赖或配色体系。

## 行为变化

- 首屏分为能力说明与密钥管理，创建表单改为按需打开；可用数量、有效状态、权限、最近使用和到期时间分层展示。ID 与完整时间放在详情里，已吊销/已到期记录默认折叠。
- 创建窗口支持可选名称、永不过期/指定未来时间、整卡权限选择。至少一项权限、过去时间原地校验；创建失败保留表单，写入中防重复并锁定关闭。
- 创建成功后同一窗口展示一次性明文和复制反馈，避免连续开关弹窗造成焦点丢失。关闭/卸载清空输入值及 `value` 属性；明文不进入列表元数据、浏览器存储或日志。异步复制反馈只写回原密钥窗口。
- 吊销确认显示名称和影响，默认聚焦保留；失败原地重试。成功先更新元数据，后续读取失败仍保留已完成状态。列表读取失败保留上次成功内容，旧响应不覆盖当前列表。
- 时间按设备本地时区显示，当天简写；到期自动进入失效记录。列表刷新保留历史及单条详情的展开状态；浅深色与手机沿用现有布局尺度。

后端端点、scope、密钥存储、MCP 协议、工具权限和草稿审核流程保持原契约。版本保持 v2.0.0。

## 影响文件

- `assets/app/features/settings/mcp-keys-view.js`：能力面板、列表、创建和明文窗口结构。
- `assets/app/features/settings/mcp-keys-state.js`（新增）：密钥状态分组与本地时间投影。
- `assets/app/features/settings/mcp-keys.js`：窗口生命周期、元数据状态、请求与到期处理。
- `assets/app/features/settings/mcp-keys.css`（新增）、`settings.css`、`assets/app/styles/index.css`：MCP 专用样式分册、移除旧样式并按 features 层导入。
- `tests/app/settings.test.mjs`、`tests/e2e/mcp.py`：状态边界、转义及真实创建/复制/吊销/到期/卸载验证。
- `AI/frontend/settings.md`、`AI/frontend/architecture.md`、`AI/frontend/design-system.md`、`AI/mcp.md`、`README.md`：同步当前页面、测试入口和样式分层。
- `AI/plans/mcp-integration/plan.md`、`progress.md`：登记用户原话、U1 范围、本地验收与未部署状态；本日志与自动生成的 `AI/logs/log.md` 记录交付。

交付前通过 `git diff --name-status` 与 `git status --short` 复核，新增 state/CSS 文件也纳入任务范围，无无关变更。

## 已实际执行的验证

所有测试服务使用临时 Vault、随机高端口并移除 `OMRS_SYSTEMD_SERVICE`，没有访问生产端口或真实题库。

| 命令 | 结果 |
| --- | --- |
| `python3 tests/check_ui.py` | 全仓 0 违规 |
| `python3 tests/check_contrast.py` | 58/58 通过 |
| `node --test tests/app/settings.test.mjs` | 27/27 通过 |
| `node --test tests/app/*.test.mjs` | 403/403 通过，无跳过 |
| `python3 tests/app/run_browser.py` | 34/34 通过，0 页面脚本错误 |
| `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/mcp.py` | 33/33 通过，含真实 SDK 草稿/原图与密钥管理路径 |
| `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/settings.py` | 62/62 通过，含六分区浅深色桌面/手机审计 |
| `env -u OMRS_SYSTEMD_SERVICE python3 -m unittest tests.test_source_export tests.test_ui_gates -q` | 15/15 通过；既有未关闭文件 ResourceWarning，不影响退出码 |
| `env -u OMRS_SYSTEMD_SERVICE python3 tests/visual/run.py --ref bec821d --pages settings --settings-section access --out /tmp/omrs-mcp-ui-visual` | 4/4 截图比较完成，0 页面脚本错误 |
| `git diff --check` | 通过 |

最终补充异步复制的窗口身份保护后，重新执行 Node 全量、MCP 浏览器、UI 与对比度检查，上表计数保持。其余源代码在对应通过后未再改变。

## 视觉差异说明

前后报告为 `/tmp/omrs-mcp-ui-visual/report.html`，审计为同目录 `audit.json`。实际密钥列表截图为 `/tmp/omrs-mcp-ui-desktop.png` 与 `/tmp/omrs-mcp-ui-mobile.png`，已人工审看；截图只有元数据，不含完整密钥。

| 截图 | 像素差异 | 原因 |
| --- | --- | --- |
| 浅色桌面 | 5.803% | 常驻表单替换为能力面板、密钥管理空态与脚注；桌面双列能力与右侧创建按钮使用共享控件 |
| 深色桌面 | 7.456% | 同一结构调整，深色沿用现有语义背景、边框和前景 token |
| 浅色手机 | 10.805% | 能力单列、按钮及脚注适配窄屏，移除常驻表单并新增管理空态 |
| 深色手机 | 13.095% | 同一窄屏结构调整，深色 token 使像素差异比例不同 |

四对差异都从 MCP 区域开始：桌面 y=785、手机 y=1077；之前的 PIN、访问概览与局域网设置像素一致。整页高度桌面 1236→1286、手机 1597→1692，符合面板与空态留白调整。四档审计均无横向溢出、过小目标或行内样式；字号仍为 12/13/15/20px。创建窗口在 1440/390px 的浅深色布局与长名称检查通过。

## 文档终检

已执行 `python3 tests/check_docs.py --write-log-index` 生成索引；`python3 tests/check_docs.py --diff HEAD` 检查 77 个文档，0 问题，退出码 0。3 条既有大文件提醒为 `AI/api.md`、前端重构执行说明及 v2.0.0 总计划，不属于本次范围。

## 未执行与下一步

本次未运行 Python 全量：没有后端行为或存储修改，已运行相关源码导出/UI 门禁专项，及真实 SDK、密钥接口和浏览器闭环。未进行生产发布、systemd/Nginx 变更、GitHub 推送、目标 ChatGPT 账户或 Tunnel 联调；用户本次授权范围为 UI 修改。

本地以一个完整 UI 切片交付。生产仍是已有 `3ae2729`；发布这次 UI 需另行授权，不自动部署。
