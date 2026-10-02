# OMRS MCP 全量扩展执行说明

执行者：Codex，完整模式。基线：d716157。用户已授权本地实现、测试、分期提交；连续完成 P0–P7。版本升级、推送、部署另行授权。

## 1. 任务目标

完整授权共 38 个工具，保留原有 11 个工具的参数和默认行为。新增查询、草稿修订、报告保存、展示板管理和导出；必要网页确认闭环全部完成后交付。

用户原话（均为明确要求）：

> 我打算给OMRS MCP一次性拓展,因为每次都要重建
> 有什么推荐吗
> 这些都很好
> 我还想加上关于展示板的编辑功能
> 比如管理展示板
> 那么计划一下吧
> 所有都要

用户批准的计划确认：草稿修订覆盖所有来源、保护人工修改；高风险通过网页确认；真实 MCP SDK 为验收重点，无需 ChatGPT 账户联调。

## 2. 当前背景与约束

先读 AGENTS.md、AI/README.md 按任务找文档、AI/plans/README.md 和本计划 progress.md。模块为 mcp、drafts、board、api、data、security、export、runtime、ledger、agent 及前端 board-ui/settings/records/architecture。

规划实测：基线工作区干净，Python 527/527、真实 SDK/浏览器 39/39、docs 0 问题。代码已确认 boards v3 无版本、规范化会丢弃额外字段；现有草稿补丁限制助手对话；报告文件与索引分开写；导出旧读图有任意路径回退。以上必须在扩展中按当前代码复核并补齐。

## 3. 最终预期行为

新增 27 个工具：get_questions、get_question_content、get_draft_image、get_question_history、get_learning_history、get_analytics、list_reports、get_report、create_report、update_draft、list_boards、get_board、create_board、update_board、duplicate_board、delete_board、add_board_items、remove_board_items、reorder_board_items、update_board_layout、update_board_item、create_board_folder、update_board_folder、delete_board_folder、move_board、export_board、get_mcp_operation。

批量读题最多 20 UID，默认摘要、可选详情、保留顺序和逐项缺失。正文按分节及当前/已登记版本分页，默认 4000、最多 8000 字；返回哈希，当前后续页检查哈希。草稿图绑定来源列表，PNG/JPEG/GIF 原字节、8 MiB、完整解码、前后鉴权。单题历史为有效反馈或正文版本；时间线先按科目/UID/日期筛选再以 before_seq 分页，不读 Markdown 遗留历史。

分析含概况、趋势、正确率、分布、薄弱项、预测，先限定科目和分类；同名分类按科目加分类分桶。日期作用于练习指标，熟练度与预测标为当前快照。列表默认 50、最多 100；板列表含文件夹及目录版本，详情分页引用、版式、纸面摘要和板版本。报告只返回分页 HTML 源码及元数据。

新写工具必需 request_id。同密钥/工具/编号相同请求复用结果，不同内容返回幂等冲突。草稿 expected_revision，只允许科目、分类、知识点、错因、备注和已有块文字/说明，任一目标人工保护即整次不写并返回建议。错因必须 cause_statement/client_asserted；保留原来源并另记 MCP 编辑身份。报告只新建，HTML 上限 2 MiB、沿用沙箱。

展示板局部编辑，排序必须完整排列；单题只留白与置顶。批量先完整校验，已存在题目跳过并报告实际变化。非法版式拒绝；删文件夹默认移板到未归档；复制不复制纸面记录；移出只移引用。

## 4. 实施计划

| 阶段 | 内容 | 依赖 |
| --- | --- | --- |
| P0 | 总纲、执行说明、进度、日志 | 基线复核 |
| P1 | 批量/正文/图片/单题历史/学习时间线 | P0 |
| P2 | 分析、报告查询和幂等保存 | P1 |
| P3 | 跨来源受保护草稿补丁 | P1 |
| P4 | boards v4、版本/回执、查询、网页保存冲突 | P1 |
| P5 | 板管理、网页确认、状态、权限编辑 | P3/P4 |
| P6 | 安全快照下载与运行记录关联 | P5 |
| P7 | SDK 全链路及网页验收、完整门禁与文档 | 全部 |

每阶段独立提交，包含代码、相关测试、文档、同一任务日志及 progress 更新；通过必要门禁后继续。

## 5. 关键技术决策

scope 保留 omrs:read/draft:create，新增 draft:update/report:create/board:write/board:delete。草稿和板写/删同时要求读权限，新写权限默认不勾选；旧 Key 不增权。网页和 CLI 可编辑既有权限，不复活吊销/到期 Key。工具发现和调用共用实时磁盘权限定义；只读 22、仅创建草稿 1、全权 38。

boards 格式 v4：每板 revision、目录 catalog_revision、MCP 回执，首次写迁移。网页/MCP 已有板写携带预期版本，目录写另检查目录版本，共享领域锁。网页冲突停自动重试、保留本地改动并提示重新读取。草稿补丁/回执同 SQLite 事务；板变更/回执同原子 JSON 写；报告预留稳定编号、原子文件、可恢复索引登记。内置助手对话归属不变。

删除板/文件夹、清空非空板、实际重置已打印记录：先返回 pending_confirmation、编号、影响预览及主 Web 链接，不改板。历史→系统运行详情提供确认/拒绝，PIN 后回同一操作。独立 mcp_operations.db 保存完整待确认参数、10 分钟有效；runtime.db 只脱敏摘要。确认重查 Key/权限/版本/影响，变化即冲突；重复确认一次执行。重启恢复待确认，执行中依领域回执恢复。get_mcp_operation 仅本人，绝不增加模型确认工具。普通引用增删/排序保留纸面记录，解除锁定不能绕过实际重置确认。

export_board 全部/仅新增，不可变自包含 HTML、64 MiB/份、24 小时、Web 登录下载，不返回全文/Base64，不写已打印；PDF 仍浏览器打印。附件只用受限 MCP 读图边界。确认及下载 URL 使用主 Web 地址，MCP Key 仍不能调用普通 Web 接口。中文运行标题、稳定错误、脱敏摘要；待确认/已应用/拒绝/到期/冲突各自显示，不把预览算完成。

## 6. 边界情况

验证空库、未知科目、同名分类、日期边界、超长正文换版、各草稿来源及已结束、人工保护、版本冲突、重复请求及响应丢失、崩溃重启、确认前目标变化/吊销/到期、重复确认。拒绝/过期不得写板；批量非法项整次不写。

## 7. 修改范围

预计涉及 omrs/mcp、draft_write/drafts、analytics/reports、boards、exporting、runtime_records、server/cli，前端板/设置/历史，以及测试和对应文档。明确不改正式题目、学习反馈、熟练度、调度、训练控制。必须完成所有工具和网页闭环；允许修复直接相关的低风险错误；不做无关重构、任意文件读取/HTTP 转发、自动 OCR、框选。

## 8. 验收标准

推荐题→建文件夹/板→批量加题→排序→留白→导出真实 SDK 通过。正文分页及原生题图/草稿图原字节一致。所有分析范围和草稿保护通过。Web/MCP 并发不丢更新，幂等/崩溃恢复不重复。确认前不写，变化/失效/拒绝/到期不写；重复确认一次。权限发现 22/1/38、隐藏工具直接拒绝、Web 凭据边界通过。学习 Ledger、熟练度和调度不因草稿、报告、板操作改变。

## 9. 验证步骤

全部实例临时 Vault/随机高端口，清除 OMRS_SYSTEMD_SERVICE 和 OMRS_BOXDETECT_CONTROL。命令使用 env -u 的环境运行。Python：python3 -m unittest discover -s tests -p 'test_*.py' -q。SDK/浏览器：python3 tests/e2e/mcp.py，展示板/草稿/报告/系统运行相关 E2E。前端：node --test tests/app/*.test.mjs、python3 tests/app/run_browser.py、python3 tests/check_ui.py、python3 tests/check_contrast.py。视觉：python3 tests/visual/run.py --ref d716157（按脚本支持参数选择相关场景），日志解释差异。

文档：python3 tests/check_docs.py --write-routes、--write-log-index、--diff HEAD，最终 --diff d716157；git diff --check。计数记录实跑，SDK 不得 SKIP 代替通过。真实浏览器覆盖网站 Key 权限、草稿、板保存冲突、确认详情、报告和下载。

## 10. 执行原则

先读后改、以代码为准、复用领域抽象。实现可调整但不能改目标/契约/验收；偏差记日志。仅已有改动无法安全隔离、必须改变目标/权限、需未授权外部变更时停止，其余连续执行。中断保存工作区并更新状态，恢复读 git status/git log/状态块。最终中文报告提交哈希（版本保持）、实跑验证、未跑验证及原因、遗留、下一步；明确 SDK 实测与未做账户联调。
