# 题目停用机制后续修复

## 触发

v1.9.0 推送后进行独立代码审查，发现停用题仍可能进入熟练度直方图、已存在 Session 的待反馈口径和顽固题行动建议；题目迁移后的历史还存在按 UID 误归属风险。

## 修复

- `stats.py` 的熟练度直方图改为只统计活跃题。
- `history_log.csv` 兼容投影新增 `Question_ID`，新反馈和 legacy 重建历史均记录稳定题目身份；stats/analytics/AI 复盘导出按 question_id 过滤与归属，兼容无该列的旧历史。
- `create_session_from_selection()` 先完成 UID/停用状态校验和题目加载，再写 sessions.csv 与 Ledger，避免失败请求留下幽灵 Session。
- 题目停用后，Session 列表、Session 详情和待反馈计数隐藏停用题；若活动 Session 已无可复习题目，则不出现在活动管理列表，原始 Session 仍保留审计。
- 行动推荐的 leech 统计改用活跃题；行动推荐跳转会清除停用筛选。
- 新增 `jsArg()` 安全编码，题库的动态 UID 操作参数不再直接插入 JavaScript 字符串。
- suspend/resume 在请求带 `Origin` 时执行严格同源校验；无 Origin 的本地脚本调用保持兼容。

## 验证

- 修复前新增回归断言按 TDD 运行失败：7 个停用测试中 4 个失败，分别复现直方图、Session 落盘、活动 Session 展示和迁移后历史过滤问题。
- 修复后 `python3 -m unittest discover -s tests -q`：24 个测试全部通过。
- `node --check`：core/questions/actions/dashboard 全部通过。
- `node tests/test_question_suspend_frontend.js`：筛选、行动计划、跳转清理与 UID 参数安全验证通过。
- `TZ=UTC node tests/smoke_frontend_actions_catalog.js`：全部通过。
- 临时 HTTP 服务验证：跨 Origin suspend 返回 HTTP 400「拒绝跨站状态修改请求」且状态不变；无 Origin 请求可正常停用。

## 发布

这是对已发布 `c2f435b release: publish v1.9.0` 的后续修复，已完成本地验证，待提交并推送到 `main`。生产服务未重启，仍需单独授权上线。
