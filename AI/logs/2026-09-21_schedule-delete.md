# 2026-09-21 错题调度删除入口

## 用户诉求

- “帮我给错题调度加上可以删除调度的功能”

## 变更摘要

在复习调度「已有计划」详情增加「删除调度」按钮，支持待完成与已完成计划。复用现有 `/api/session/delete`，确认框明确说明会同时撤销关联反馈、重新计算熟练度与复习日期，题目正文保留，历史记录可恢复 Session。

删除成功清理当前详情、关联反馈表单和结果，刷新计划、待完成数量、推荐与题目缓存。检查 HTTP 200 中的业务失败字段；失败保留计划并显示原因。确认与请求期间阻止同一计划重复操作，避免删除前的列表/详情响应重新显示旧数据。

## 行为与兼容性

后端、Ledger 格式和调度算法不变。使用现有 `session.retract` 语义，删除不是抹除账本记录。测试使用临时题库，不操作用户题目。保留任务前已有的未跟踪 `.playwright-mcp/` 目录。

## 修改文件

- `assets/schedule.js`：删除按钮、确认、请求与状态同步。
- `tests/test_schedule_sessions.js`：重复操作、取消、业务失败回归。
- `tests/smoke_schedule_workbench.py`：真实 HTTP 服务与 Chromium 删除流程。
- `AI/frontend.md`、`AI/api.md`、`README.md`：入口及删除语义。
- 本日志与 `AI/logs/log.md`：任务记录和索引。

## 验证

- `node --test tests/test_schedule_sessions.js`：4 项通过。新增用例首次运行暴露测试跨 VM 微任务等待不足，改为等待事件循环后通过。
- `python3 -m unittest tests.test_schedule_workbench tests.test_history_projection tests.test_sessions_feedback`：13 项通过。
- `python3 -m unittest tests.smoke_schedule_workbench`：1 项通过；真实 HTTP + Chromium，包含取消、业务失败、重试成功、推荐释放、反馈选择器清理、待完成/已完成删除和刷新持久性，页面无 JavaScript 异常。
- `git diff --check`：通过。
- `python3 tests/check_docs.py`：通过。

## 同步过的文档

`AI/frontend.md`、`AI/api.md`、根 `README.md` 和日志索引。复核 `AI/README.md`，项目摘要与索引无需调整。
