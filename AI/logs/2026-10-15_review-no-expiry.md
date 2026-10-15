# 2026-10-15 审核中心取消待审过期

## 背景

用户原话：

> 取消过期
> 本来放审核中心就是为了长期使用的

执行者为 Codex，运行模式为完整模式。开工 HEAD 为 310186958b802f9c1753fd1be81628c2f609308e；工作区已有作业帮独立页面、题框和协作规则等未提交改动，本任务保留它们，不调整版本、不部署或改动生产数据。本次是新的维护任务，不修改已完成计划及历史执行说明。

## 行为变化

- MCP 改题、正式复习计划、整批标记整理与高风险展示板请求进入审核中心后长期保留，新增待审不设置 expires_at。
- 已有统一审核库中仍待审的旧 MCP 请求忽略原期限；列表、计数、状态筛选、详情、人工修订、批准及普通启动采用相同口径。查询只读计算，不通过 GET 改库、续期或重建申请。
- 取消 MCP 查询恢复和实际提交前的时间判定。批准仍核验当前密钥、权限、提案版本、内容快照、稳定目标与题库世代；回执、幂等及单次执行保持。
- 内置助手的十分钟只限制原聊天线程等待；到时移交中心并长期保留。旧聊天许可、密钥本身的有效期和导出快照期限保持原契约。
- 已经结束的 expired/rejected/conflict/interrupted 等历史与旧只读导入不重新激活；整库恢复仍废止未终结许可。仅因旧期限而在读取时显示 expired、底层仍为 pending_confirmation 的请求可继续审核。

## 影响文件

按 git diff --name-status 复核，仅包含以下审核相关文件或同文件中的审核段落：

- omrs/ai_review.py：MCP 无期限创建与准备、旧期限只读兼容、列表筛选与去重、来源区分的实际写入校验。
- omrs/mcp_operations.py、omrs/mcp/tool_docs.py：移除 MCP 十分钟期限和提交前超时检查，工具发现说明长期待审。
- tests/test_ai_review.py、test_question_update.py、test_mcp_board.py、test_mcp_review_approvals.py、test_label_plan_review.py、test_mcp_question_update.py：长时间等待、旧记录、启动、修订、真实 MCP SDK、提交期间时间变化、撤权及历史不复活。
- tests/e2e/ai_review.py：启动前预置一个月前带旧期限的提案，实际浏览器验证队列、无有效期、修订及批准。
- AI/ai-review.md、mcp.md、mcp-storage.md、api.md、api/extensions.md、data.md、security.md、ledger.md，AI/frontend/ai-review.md、architecture.md，AI/environment.md 与根 README.md：同步当前长期待审和验证契约。共享文档只收录本任务段落。
- 本任务日志及脚本生成的 AI/logs/log.md 索引项。

## 已实际执行的验证

所有业务测试使用临时 Vault，HTTP/MCP 和真实 Chromium 使用随机高端口；清除 OMRS_SYSTEMD_SERVICE 与 OMRS_BOXDETECT_CONTROL，不访问生产端口或真实错题库。时间回归通过替换进程内时间或预置旧记录完成。

| 命令 | 结果 |
| --- | --- |
| env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL PYTHONPATH=.:tests python3 -m unittest tests.test_ai_review tests.test_question_update tests.test_mcp_review_approvals tests.test_mcp_board tests.test_label_plan_review tests.test_agent_permissions tests.test_ai_review_http tests.test_ai_review_mcp tests.test_mcp_question_update tests.test_mcp_review_sessions -q | 最终 124 项通过，无跳过；含真实官方 MCP SDK |
| env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL PYTHONPATH=.:tests python3 -m unittest tests.test_mcp_tool_docs tests.test_agent_review tests.test_agent_loop tests.test_label_plan tests.test_label_plan_recovery tests.test_mcp_label_plan tests.test_mcp_lifecycle tests.test_mcp_expansion -q | 64 项通过，无跳过 |
| env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/e2e/ai_review.py | 最终 48/48 通过，浅深主题及 320/390/1024/1440px 均无脚本错误、横向溢出或控件问题 |
| python3 tests/check_docs.py --write-log-index | 已由脚本生成索引 |
| python3 tests/check_docs.py --diff HEAD | 主工作区 118 个文档、0 处问题；只含本任务改动的干净基线副本 117 个文档、0 处问题，均退出 0 |
| git diff --check | 主工作区及独立副本均通过 |

初轮新增展示板测试错误地期待读取已删除板抛异常，现按领域契约检查返回 None；初轮 100 项中该项失败，修正后的最终 124 项全部通过。故障注入用例输出辅助结果落盘失败日志属于预期，原生回执及不重放断言均通过。

定向测试输出在 /tmp/omrs-review-no-expiry-tests.log 与 /tmp/omrs-review-no-expiry-extra.log，浏览器输出在 /tmp/omrs-review-no-expiry-browser.log，截图在 /tmp/omrs-ai-review-shots。

为确认没有依赖其他任务的未提交代码，从开工 HEAD 建立临时干净副本 /tmp/omrs-review-no-expiry-verify-hs_0o4f4，只应用本任务的代码、测试、文档段落和日志；补丁 git apply --check 通过。该副本合并运行上述两组 Python 模块，188 项通过、无跳过；真实浏览器再次 48/48，通过日志在 /tmp/omrs-review-no-expiry-isolated-tests.log 与 /tmp/omrs-review-no-expiry-isolated-browser.log。文档检查的三条体积提醒来自既有计划与根 README，不影响退出码。

## 未执行的验证与下一步

未运行全仓测试、前端样式门禁或视觉前后比较：本任务不改 assets、HTML 或视觉基线；已有其他任务的界面与作业帮改动不纳入本次验收。审核中心用户主路径已实际起服务并打开浏览器验证。

未进行生产部署、重启、systemd、Nginx、真实 MCP 账户或付费模型调用、远端推送；当前授权为本地实现。生产使用需要单独安排发布；不直接修改生产审批记录或用旧库覆盖最新数据。
