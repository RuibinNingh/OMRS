# 2026-10-21 MCP 答案内容边界

> **任务**
> - 标识：mcp-answer-scope
> - 状态：已交付

## 背景

用户原话：「OMRS Mcp录入是不是没有写明白」「AI总是会录入题目的时候答案里面多写一些东西」「除了答案解析还有练习,甚至还有概念解析之类的不必要的」「调查一下」。补充原话：「来自ChatGPT,大部分我都删了,物质分类与变化34  你可以找到多余的」。调查后要求：「那么改一下mcp的规范吧」。

执行者 Codex，完整模式，所属计划为 AI/plans/mcp-integration/ 的答案内容边界维护，基线 e0ef9ed / v2.8.4。开工已有 AI/plans/omrs-maintenance/validation.json 未提交改动，施工期间另出现 assets/app/features/ai-review/drafts.css、tests/e2e/ai_review_entry.py、tests/visual/run.py 及配套文档、计划、日志的其它任务改动，均保留且不纳入本批。

前置只读调查确认样本末尾“易错提醒”重复详解（5）（6），对应 MCP 草稿与正式答案一致。临时 Vault 实测包含“概念解析”“巩固练习”的答案可原样创建待审草稿；现有服务端只作格式及容量等校验。当前会话暴露的简版工具说明与仓库新版不同，不能把本地说明更新当作 ChatGPT 已刷新。

## 行为变化

MCP 答案默认只保存本题结论和必要解析，保留必要步骤、全部小问及解题必需的简短概念。默认不追加练习、变式题、独立概念讲解、方法总结、易错提醒或学习建议；聊天中讲过不等于用户要求保存，未要求保存的内容不转存备注。用户明确要求保存的补充仅按指定范围纳入，修订不越过用户要求的范围。

创建、草稿修订和正式改题，以及相关文字字段和 instructions 共用规则；示例展示直接解答和应排除的重复教学补充。这是客户端调用规范，不新增关键词过滤，不自动改写或清理已有题目与草稿，参数、权限、审核和版本保持。

## 影响文件

- omrs/mcp/tool_docs.py：共享答案内容规则、三个写工具及相关文字字段说明，调整公开纯文字示例。
- AI/mcp.md、AI/drafts.md、AI/api.md、README.md：同步当前调用规范、正反例和客户端刷新边界。
- AI/plans/mcp-integration/plan.md、progress.md：登记本批目标、实施终点、验证和后续账户效果边界，历史发布记录保留。
- AI/logs/2026-10-21_mcp-answer-scope.md、AI/logs/log.md：本次任务记录与自动生成索引；交付前按实际差异复核。

已用 git diff --name-status 和 git diff --check 复核。共享索引按脚本生成，会包含其它任务当前存在的日志条目；其它任务源码及文档 hunk 不纳入本批交付说明。

## 已执行验证

- env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_mcp_tool_docs.py' -q：1/1 通过，无跳过，说明元数据未改变参数接受范围。
- env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_mcp*.py' -q：132/132 通过，13.605 秒，无跳过；包括真实协议公开示例创建、读取、原图、重试与非正式入库边界。完整输出在 /tmp/omrs-mcp-answer-scope-StnrDCSp/mcp-tests.log。
- 临时 Python heredoc 复用 tests.test_mcp_protocol.MCPServerProcess，官方 SDK 调用 initialize/tools/list：44 工具，instructions、三个写工具 description 和三个相关文字字段共 7/7 携带共享规则。使用临时合成 Vault、随机高端口，并清除两个生产控制环境变量；证据在 /tmp/omrs-mcp-answer-scope-StnrDCSp/sdk-discovery.json。
- python3 tests/check_docs.py --write-log-index：已生成索引。python3 tests/check_docs.py --diff HEAD：多次复核均为 155 文档、0 问题、退出码 0。首轮 3 条非阻断大小提醒；共享工作区 AI/environment.md 的并行修改曾使提醒增为 4 条，后续复核回到 3 条；提醒未作为失败或本批改动处理。
- git diff --check：退出码 0。

## 未执行验证

- ChatGPT 刷新与实际生成效果、生产发布、推送：未执行；本批交付本地规范修改，不操作生产或账户配置。
- 页面、浏览器与视觉门禁：本批未修改前端或页面行为，不运行；共享工作区的其它任务 CSS 不属于本批。
