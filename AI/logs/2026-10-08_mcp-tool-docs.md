# 2026-10-08 MCP 工具说明与录题规范补齐

## 背景

用户原话：「OMRS MCP工具说明是不是不够详细?」「帮我补齐,尤其是题目录入部分的规范」。执行者为 Codex，完整模式，开工基线 ef92753，最初工作区干净。施工期间出现另一批草稿页面、样式、版本及文档改动；按路径和 README 独立 hunk 保留，不混入本批提交。不部署、不推送、不扩权；本批不另调整版本。

## 行为变化

外部客户端工具发现返回完整的 40 工具用途、前置读取、字段来源、分页单位、返回结构与后续操作；162 个顶层参数及附件、块、计划条目和自由补丁字段有中文说明。权限名称由现有 TOOL_SCOPES 派生。工具描述集中在 omrs/mcp/tool_docs.py，注册入口直接引用，参数 schema 在既有约束生成后仅补说明和示例；回归确认校验约束不变。服务端 instructions 可由真实 SDK 初始化读取。

录题规范强调一道完整题目一份草稿、保留全部条件和相关小问、忠实转述及 LaTeX、答案无图时单文字块、来源完整原图与从零开始下标、note 不执行裁剪、错因附用户原话、创建仅为待审。全文字转述也保留来源；附件失败不能静默去图并声称保存成功；生成解答标注待核对。公开 schema 提供纯文字、完整原图和图文混排示例。草稿修订只改白名单及已有块，人工保护不拆请求绕过。

MCP 查询直接返回业务字段，去掉内置助手的 result 包装；说明中的推荐 selection、读题 images、question_id/content_hash 按实际响应写。正式计划及改题先返回审核操作，未批准不声称完成；客户端更新服务后须刷新工具清单和 instructions。

## 影响文件

- omrs/mcp/tool_docs.py：集中说明、录题规范、字段注释与示例；元数据补充函数不增加校验约束。
- omrs/mcp/server.py 与 8 个注册模块：引用集中说明，注册后补参数说明、派生权限名称。注册模块为 analysis_reports、board_export、board_read、board_write、draft_edit、queries、question_write、session_write。
- tests/test_mcp_protocol.py、tests/test_mcp_tool_docs.py：真实客户端发现/初始化及例子闭环；比较补说明前后实际参数约束。
- tests/e2e/runtime_history.py：跳转后等待草稿入库按钮出现再断言详情，原断言不弱化。
- AI/mcp.md、AI/drafts.md、AI/api.md、AI/environment.md、AI/frontend/architecture.md、README.md：同步实际说明机制、录题规范及浏览器载入等待；README 仅本批 MCP 说明 hunk。
- AI/plans/mcp-integration/progress.md、本日志与生成索引：登记本批事实、验证与后续，保留历史批次结果。

已用 git diff --name-status 复核已跟踪路径，并以 git status --short 纳入本批新增文件。本批没有覆盖或暂存其它任务的 assets、版本、前端文档及测试。最终暂存前这些外部改动从共享工作区撤回，本批未执行该撤回；随之被撤回的 README/环境文档本批说明已重新补上。

## 已实际执行的验证

测试服务均使用临时 Vault 和随机高端口；启动环境清除 OMRS_SYSTEMD_SERVICE 和 OMRS_BOXDETECT_CONTROL，没有连接生产端口、真实错题或外部模型。

| 命令 | 实际结果 |
| --- | --- |
| `python3 -m unittest discover -s tests -p 'test_mcp*.py' -q` | 最终 128/128，无 skip；首轮新增测试误导入私有 scope 常量，修正后完整重跑通过；最终轮含真实 instructions 验证 |
| `python3 -m unittest discover -s tests -p 'test_agent_draft_tools.py' -q` | 16/16 |
| `python3 -m unittest discover -s tests -p 'test_ai_review_mcp.py' -q` | 4/4；输出包含既有审核回执故障模拟日志，测试通过 |
| `python3 tests/e2e/mcp.py` | 官方 SDK / 浏览器 39/39 |
| `python3 tests/e2e/mcp_expansion.py` | 17/17 |
| `python3 tests/e2e/mcp_review_sessions.py` | 17/17 |
| `python3 tests/e2e/runtime_history.py` | 修正等待后最终共享工作区 34/34，无 skip |
| `python3 tests/check_docs.py --write-log-index` | 已生成，仅新增本批索引项 |
| `python3 tests/check_docs.py --diff HEAD` | 102 个文档，0 问题，2 条既有大文件提醒，退出 0 |
| `git diff --check` | 通过 |

SDK 对公开 schema 做有效性检查并按示例实际调用，验证纯文字、整图、图文混排及全文字带来源和错因原话；返回 review、固定难度 5、完整来源与 original 整图框，get_draft_image 原字节一致，技术重试复用原草稿，创建前后 Ledger 提交数不变。另一个回归去掉 description/examples 和无约束字段说明后比较所有工具 schema，确认说明没有收紧或放宽既有参数校验。

共享工作区的运行记录 E2E 首次与复跑均为 33/34，失败为“查看草稿跨页定位对应 MCP 草稿”。干净 ef92753 及该基线仅叠加本批 MCP 源码均为 34/34；实际脚本只等待可提前显示的 .drf-detail 加载占位。改为等待详情入库按钮出现，保留科目/来源原断言后，最终共享工作区 34/34。没有用隔离结果替代最终共享工作区验证，也没有覆盖其它任务的前端改动。

## 未执行的验证与后续

未执行生产部署、生产 SDK、Git 远端推送、ChatGPT 账户原生附件联调、Windows 实机或全仓 Python/Node/视觉门禁。本批只改 MCP 文档元数据和相关测试，页面/样式变化属于另一个任务；与本批相关的官方 SDK 及浏览器主路径已实际执行。生产与远端变更需另行明确授权；上线后刷新客户端工具清单及 instructions，现有会话缓存不会自行更新。
