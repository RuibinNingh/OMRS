# 2026-10-01 OMRS MCP 接入

## 背景与范围

执行者 Codex，完整模式；基线 `295793933ce814b4696d002e18729efac773f807`。本任务延续同一用户 Goal 与 `AI/plans/mcp-integration/exec-2026-10-01-mcp-v1.md`，附件是执行计划来源，用户明确的权限、完整原图与闭环验收要求优先。恢复时已有本任务的并行未提交产物，保留并审查后统一集成；没有覆盖其他工作区或历史改动。

本轮始终使用临时 Vault、随机高端口，并从测试进程环境移除 `OMRS_SYSTEMD_SERVICE`。生产服务、systemd、Nginx、真实 Vault 和 Git 远端均未修改。分期作为集成检查点，恢复后的共享产物按完整接入闭环提交一个可运行垂直切片，不交付独立骨架。

## 行为变化

- 官方 `mcp==1.28.1` Streamable HTTP 与 Web 同进程托管，复用主进程写锁；取消直接写同一 Vault 的独立 MCP 入口。`serve --mcp-port` 启用，回环监听；`--mcp-public-url` 配置 HTTPS 代理 Host/Origin 白名单。
- Key 具有独立的查询/创建草稿 scope、到期、吊销和最近使用时间。只保存摘要与非秘密元数据，0600；跨进程文件锁防止 CLI/Web 并发覆盖吊销。管理响应 `no-store`，普通 Web 路由在登录及管理入口之前拒绝 MCP 凭据。
- 九个只读工具和唯一 `create_draft` 明确注册；查询复用助手实现与 schema，草稿只读视图不恢复作业或创建训练任务。输入模型禁额外字段并验证类型、数量和长度；同步领域操作在工作线程执行，持 RLock 期间不跨 await。
- HTTP 有体积/超时/每 Key 限流/并发上限。下载禁止重定向和非公共地址，固定经过校验的 IP、保留 TLS 主机验证；限流式响应长度和时长。Pillow 完整解码校验格式/像素/帧数，原件仍保留实际收到的字节。
- 草稿来源由服务端构造，固定 `mcp`、`review`、难度 5；答案合并复用共享内容准备规则。规范化内容和原图 SHA 用于幂等，稳定 file_id 重试可避开已过期签名 URL；inline 字节改变仍拒绝复用。
- 原图原子落盘，关系/草稿/请求记录同一 SQLite 事务；故障回滚只清理本次新文件，不删除共享文件或已提交原件。半文件按实际 SHA 恢复，符号链接拒绝。POSIX 同步目录，Windows 仅同步原件文件并原子替换，未作 Windows 实机验收。
- 全幅引用标 `box_origin=original`；PNG/JPEG/GIF 原字节保存且普通图片接口也不截 JPEG 尾数据。创建及普通正文修改不触发框选、OCR、模型、训练或正式入库；人工明确训练操作仍沿用原流程。
- 设置页管理 Key，明文只在页面内存，隐藏、刷新和离开时清空；草稿列表/详情显示 MCP 来源、外部错因待核对、完整原图提示并保留来源关联。人工仍可编辑正文和审核入库。
- 脱敏源码导出包含 `requirements-mcp.txt`，排除 Vault Key 数据及秘密。

## 影响文件

后端：`omrs/mcp/`、`omrs/cli.py`、`omrs/server.py`、`omrs/drafts.py`、`omrs/draft_write.py`、`omrs/draft_training.py`、`omrs/draft_prepare.py`、`omrs/agent/tools/drafts.py`、`omrs/source_export.py`、`requirements-mcp.txt`。

前端：设置页 MCP 卡片及控制器、挂载与样式；录入页草稿来源、全幅语义及人工改框来源处理。

测试：`tests/test_mcp*.py`、`tests/e2e/mcp.py`、`tests/test_source_export.py`、设置/草稿 Node 用例；修复 `tests/app/core.test.mjs` 窗口替身和视觉脚本锁屏入口/草稿工作区支持。

文档：MCP 专题及 API/权限/草稿/数据/助手/前端/环境文档、README、计划进度、自动路由与日志索引。交付前已复核 `git diff --name-status` 及未跟踪文件，临时日志/截图均在 `/tmp`，秘密和缓存未纳入提交。

## 已实际执行的验证

运行环境：Python 3.13.5、Node v22.23.0、mcp 1.28.1、uvicorn 0.51.0、Pillow 12.3.0。

| 命令/验收 | 最终结果 |
| --- | --- |
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 470/470，通过 |
| MCP 五组与源码导出 `python3 -m unittest tests.test_mcp tests.test_mcp_keys tests.test_mcp_http tests.test_mcp_protocol tests.test_mcp_draft_atomic tests.test_source_export -q` | 49/49，通过 |
| `node --test tests/app/*.test.mjs` | 399/399，通过 |
| `node --test tests/app/settings.test.mjs` | 24/24，通过 |
| `python3 tests/app/run_browser.py` | 34/34，通过 |
| `python3 tests/e2e/settings.py` | 62/62，通过，四档布局 |
| `python3 tests/e2e/assistant.py` | 58/58，通过 |
| `python3 tests/e2e/drafts.py` | 56/56，通过 |
| `python3 tests/e2e/drafts_p4.py` | 修复测试准备后连续两次24/24，通过 |
| `python3 tests/e2e/mcp.py` | 15/15，通过，含手机原图和离开页面密钥清空 |
| `python3 -S -m unittest tests.test_mcp_http tests.test_mcp_protocol -q` | 18 项，6 标准库用例通过，12 SDK 用例明确 SKIP |
| `python3 tests/check_ui.py` | 0 问题 |
| `python3 tests/check_contrast.py` | 58 组，0 不达标 |
| `python3 tests/check_docs.py --write-routes --write-log-index` | 已执行并生成索引 |
| `python3 tests/check_docs.py --diff HEAD` | 0 问题，3 条既有大文档提醒 |
| `git diff --check` | 通过 |

真实 SDK Client 协商 `2025-11-25`，固定发现 10 工具；查询临时 Vault 中真实题目、练习记录、熟练度、推荐和 Session，与助手结果一致。创建 review/MCP 草稿，PNG、JPEG 尾数据和 GIF 的磁盘/Web 字节一致；并发重试、过期附件 URL、非法参数、只读 scope、吊销/到期/错误/缺少 Key、普通 API 越权、恶意 Host/Origin 全部覆盖。创建前后的正式题目 Markdown SHA 和 Ledger commit 集合不变。

Key 测试包括多个真实独立进程、验证与吊销的强制交错、文件锁和损坏记录拒绝；原子测试注入图片、数据库、提交后响应/事件故障，并覆盖共享原件与半文件恢复。真实浏览器打开草稿区验证人工审核入口和原图，设置页创建/隐藏/刷新/吊销 Key，审查截图 `/tmp/omrs-mcp-e2e.png`。

## 视觉与门禁调查

执行 `python3 tests/visual/run.py --ref HEAD --pages settings,create --settings-section access --create-stage drafts --out /tmp/omrs-mcp-visual`。浅色/深色、桌面/手机共 8 对截图，脚本错误为 0，横向溢出/过小点击目标/行内样式均为 0。四个空草稿队列截图无像素差；设置页因新增 MCP 卡片和页面增高出现差异：桌面 27.55%，手机 31.626%/31.629%。报告在 `/tmp/omrs-mcp-visual/report.html`；MCP 来源内容由真实浏览器截图补充。

初始全量 Node 为 396/397，既有失败源于 fakeWindow 只有 hash，而实际路由保留 pathname/search，替身把完整地址错误当 hash。本次只修测试替身按 URL 解析，并新增入口查询串保持断言，生产路由未改。

P4 第一次运行8/9，拖动 AI 框后保存仍禁用，后续主路径未执行；干净 HEAD 24/24，当前代码临时加调试读取也24/24。页面全局平滑滚动导致阶段位置前后移动57px，测试读到滚动中的旧坐标，拖动未命中。只修测试：等待图片解码，hover 等稳定与命中，中心点确认缩放柄后再实际拖动；保存、ai_box、ai_edited、后续业务断言均保留。正式脚本连续两次24/24，业务 AI 分支与权限未变。调查记录 `/tmp/omrs-mcp-drafts-p4-final.log`。

视觉脚本初次参数不支持 drafts，继而直接打开锁屏导致 router 不存在；补支持草稿工作区并用本地授权外壳入口重跑完成，未改生产鉴权。

## 计划差异与未执行项

同进程托管代替计划默认的薄适配进程加受限主入口，满足共享写锁和权限白名单，避免第二进程直接写 Vault。没有添加第二套 Agent Runtime、题库、草稿或用户权限模型；未对现有来源作无依据归类，迁移仅在真实助手运行/调用/对话匹配时标 agent，其余 legacy。

官方 ChatGPT Developer Mode 认证为 OAuth/No/Mixed，static credentials 指 OAuth 客户端凭据，不能证明支持任意 API Key。文件 schema 已按官方 fileParams 声明。已实测官方外部 MCP Client 的 API Key 链路；没有目标 ChatGPT 账户，未执行账户联调，未宣称 ChatGPT 原生接通。未来原生入口若不能发送 Header，应提供保持同一 scope 边界的 OAuth 兼容入口，不能无鉴权或 URL 传 Key。

未执行生产发布、systemd 重启、Nginx 配置、公网 HTTPS 联调、Git 推送、Windows 实机验收。外部 MCP Client 的闭环交付可以在本机复现；生产与账户配置属于后续授权范围。
