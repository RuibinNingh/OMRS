# 2026-11-16 文档检查与维护

> **任务**
> - 标识：documentation-maintenance
> - 状态：已交付

## 背景

用户要求「维护OMRS文档」「进行全面的检查,维护,修正」。完整模式以 `55afe35` 和开工时的工作区为基线，按入口、前端、后端及其他模块分工，检查文档门禁、索引和重点行为，并对照当前代码与测试修正可确认的差异。既有全面实现检查计划已交付，本次是独立文档维护，不执行该计划的后续业务修复。

开工前 `AI/data.md`、`AI/logs/log.md` 已修改，`AI/logs/2026-11-16_ai-mcp-question-capabilities.md` 未跟踪；其内容属于先前任务，本轮保留。日志索引由脚本重新生成，保留该任务条目并加入本任务。

## 行为变化

无业务行为变化。文档更正 MCP 授权、审核期限、草稿修订和 SVG 配图能力，澄清稳定题目身份、配置事实源、导出参数、调度公式与前端入口，并补充当前页面和工具索引。

## 影响文件

- `README.md`、`AI/README.md`：修正入口、联网与配置说明，补充模块索引。
- `AI/agent.md`、`AI/algorithm.md`、`AI/mcp.md`、`AI/mcp-tools.md`、`AI/runtime.md`、`AI/security.md`：对照注册表、审核、调度与权限实现修正契约；工具表拆分册以保持模块文档体积。
- `AI/api/mutations.md`、`AI/data/storage.md`、`AI/export.md`：修正活动配置、展示板身份解析和导出参数说明。
- `AI/frontend.md`、`AI/frontend/architecture.md`、`AI/frontend/dashboard.md`：补齐页面索引并修正门禁、训练页和事件来源。
- `AI/logs/2026-11-16_documentation-maintenance.md`、`AI/logs/log.md`：记录本次任务及生成索引。
- `AI/data.md` 和上述先前任务日志为开工已有改动，不属于本次修正。

## 已执行验证

- 对照 `omrs/mcp/`、`omrs/agent/tools/`、`omrs/ai_review.py`、`omrs/scheduling.py`、`omrs/exporting.py`、`omrs/boards.py`、配置存储和相关前端入口与测试核查重点声明；检查了文档索引、速查头及关键词，不声称逐条验证所有接口和页面。
- `python3 -m unittest tests.test_docs_gate`：13 项通过。
- `python3 -m unittest tests.test_mcp_question_update tests.test_agent_draft_tools tests.test_schedule_reminders -q`：31 项通过。
- 首次运行 `python3 -m unittest tests.test_security tests.test_board_identity tests.test_config_repository`：17 项通过，1 项因不存在 `tests.test_config_repository` 模块而导入失败；改用 `tests.test_config_publication` 单独运行，13 项通过。
- `python3 -m unittest tests.test_security tests.test_board_identity tests.test_config_publication`：30 项通过。
- `python3 tests/check_docs.py --write-log-index`：生成任务日志索引。
- `python3 tests/check_docs.py --diff HEAD`：检查 168 个文档、0 处问题，3 条既有大文件提醒（两份计划文档及根 README）；退出码 0。
- `git diff --check`：通过。

## 未执行验证

未逐条验证全部历史文档及每个接口，也未运行完整业务门禁、真实浏览器、生产服务或真实供应商；本次仅改文档，专项测试和静态对照不能证明全部功能正确。
