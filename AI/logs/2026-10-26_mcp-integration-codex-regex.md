# 2026-10-26 MCP 编号正则的 Codex 兼容修复

> **任务**
> - 标识：mcp-integration-codex-regex
> - 状态：已交付

## 背景

用户原话：「什么情况」「ChatGPT Chat能用」「Codex就不行」。后续提供联调报告，建议「OMRS 可以用下面的写法兼容两种校验方式，同时保留现有的空格处理行为」，具体规则为 `^[\s\S]*\S[\s\S]*$`；同时指出 Session 与复习计划同类规则。

本批由 Codex 完整模式执行，属于 AI/plans/mcp-integration/plan.md「Codex 参数校验兼容维护」，基线 87f813e / v2.8.5。开工已有 AI/plans/omrs-maintenance/validation.json 未提交改动，保留且不纳入本任务。用户报告的生产及连接器对照与本批独立执行的本地验证分别记录，不把普通匹配模拟当作连接器内部实现证据。

## 行为变化

题图 UID、Session ID、创建复习计划的请求编号与嵌套稳定题目 ID 共用显式完整字符串正则，普通搜索与整串匹配均接受中文及多字符编号。原有长度、空白处理、领域校验、授权与人工审核保持；空串、纯空白、超长及非法类型仍拒绝。版本保持 v2.8.5。

## 影响文件

- omrs/mcp/common.py、omrs/mcp/server.py、omrs/mcp/session_write.py：统一四处非空白参数规则。
- tests/test_mcp.py：新增四处 schema 的匹配兼容、Pydantic/JSON Schema 及边界回归，移除旧正则字符串的实现断言。
- AI/mcp.md、AI/api.md、README.md：同步当前规则及客户端刷新要求。
- AI/plans/mcp-integration/plan.md、AI/plans/mcp-integration/progress.md：登记本批范围、验证与后续验收。
- 本日志及 AI/logs/log.md：记录实际执行并生成索引。已按 git diff --name-status 复核范围；原有 maintenance/validation.json 改动不纳入本任务。

## 已执行验证

- 修复前执行 `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_mcp.py -k nonblank_id -v`：1 项回归中四个字段均在 xx 的整串匹配断言失败，稳定重现兼容差异。
- 修复后执行 `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_mcp*.py' -q`：133/133，13.391 秒，无跳过，退出码 0。包含原生题图协议与正式计划 SDK 流程，全部实例使用临时 Vault 与随机高端口，并清除生产控制环境变量。输出含审核终态写入失败提示，最终套件为 OK；本批未改回执恢复实现。
- 临时 Python SDK 探测复用 tests/test_mcp_protocol.py::MCPServerProcess，清除相同生产控制变量并使用临时 Vault：真实 tools/list 返回的四处规则接受多字符、中文、首尾空白及换行的整串匹配，纯空白拒绝；get_question → get_question_image 返回中文多字符 UID 对应 PNG 原字节，含首尾空白的 UID 可用；多字符 get_session 查询及 create_review_session 送审成功。实例与临时数据已清理，不作为 Codex 账户联调通过的证据。
- 运行 `python3 tests/check_docs.py --write-log-index` 生成索引；`python3 tests/check_docs.py --diff HEAD` 检查 155 份文档，0 问题、3 条大小提醒，退出码 0。`git diff --check` 通过。

## 未执行验证

生产发布、服务重启、连接器刷新及实际 Codex/Chat 账户读图尚未执行，本轮只做本地修复与验证。当前会话此前调用 OMRS 工具返回不可用，不能声称已从 Codex 连接器获取线上原图。
