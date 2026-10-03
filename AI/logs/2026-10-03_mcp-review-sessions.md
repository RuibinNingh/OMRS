# 2026-10-03 MCP 正式复习调度

## 背景

用户要求给 OMRS MCP 添加创建调度和查询调度情况，批准执行并要求版本增加 0.0.1；按现有 v2.2.0 升级为 v2.2.1。执行者 Codex 完整模式，基线 afbad60，开工工作区干净。计划见 AI/plans/mcp-review-sessions/plan.md。

## 行为变化

新增 create_review_session，按稳定 question_id/source 创建 1–100 题正式 EXP Session，单题也持久化。任一非法、停用、归档或被活动计划占用的题整次拒绝；创建事实、投影和回执同事务提交。技术重试先查原回执，内容冲突拒绝，撤销或学习恢复排除后不复活；提交前复查身份、链头和权限，提交后吊销保留已合法完成事实。

推荐提供稳定身份；list/get 支持分页、完整反馈进度及停用、归档、待绑定计数。新增 session:create 权限默认关闭、旧密钥不增权，设置页显式授权；运行记录只记选择数量、编号等脱敏摘要。权限完整时 39 工具、只读仍 22 工具。

独立复核发现既有网页创建可能同秒复用已撤销/恢复排除的编号，使 MCP 旧回执查到另一计划。增加共享历史编号预留：SQL 投影、MCP 回执和不可变 session.create / legacy.bootstrap 中的编号都保留，Web 与 MCP 均使用。固定时钟回归覆盖撤销、状态恢复和投影重建。最终审查又复现 A–Z 后缀用尽后微秒后备编号未查重，补上后备查重与固定时钟数字候选碰撞回归，再执行完整 Python 门禁。

## 影响文件

收尾通过 git diff --name-status 和未跟踪文件清单复核，本次修改如下：

- `AI/README.md`
- `AI/agent.md`
- `AI/api/mutations.md`
- `AI/api/queries.md`
- `AI/changelog.md`
- `AI/data.md`
- `AI/frontend/architecture.md`
- `AI/frontend/review.md`
- `AI/frontend/settings.md`
- `AI/ledger.md`
- `AI/logs/2026-10-03_mcp-review-sessions.md`
- `AI/logs/log.md`
- `AI/mcp-storage.md`
- `AI/mcp.md`
- `AI/plans/README.md`
- `AI/plans/mcp-review-sessions/plan.md`
- `AI/plans/mcp-review-sessions/progress.md`
- `AI/routes.md`
- `AI/runtime.md`
- `AI/security.md`
- `README.md`
- `assets/app/features/settings/mcp-keys-view.js`
- `omrs/agent/tools/read.py`
- `omrs/mcp/keys.py`
- `omrs/mcp/server.py`
- `omrs/mcp/session_write.py`
- `omrs/runtime_records.py`
- `omrs/session_operations.py`
- `omrs/sessions.py`
- `omrs/version.py`
- `omrs_dashboard.html`
- `tests/app/settings.test.mjs`
- `tests/e2e/mcp_expansion.py`
- `tests/e2e/mcp_review_sessions.py`
- `tests/test_mcp_board.py`
- `tests/test_mcp_review_sessions.py`
- `tests/test_runtime_records.py`
- `tests/test_session_ids.py`
- `tests/test_session_operations.py`
- `tests/test_session_queries.py`

## 实际验证

测试使用临时 Vault 与随机高端口，启动前移除 OMRS_SYSTEMD_SERVICE，未访问真实错题或重启生产。最终完整 Python 回归在编号预留及领域锁处理修复后执行。

| 验证 | 命令 / 结果 |
| --- | --- |
| 领域、查询、编号、SDK 专项 | test_session_operations 26/26；test_session_queries 12/12；test_session_ids 6/6；test_mcp_review_sessions 3/3 |
| Python 完整门禁 | python3 tests/run_gates.py --ref afbad60 --groups unit --out /tmp/omrs-mcp-review-unit-final；unittest 718/718 无 skip，pytest 导出 7/7 |
| 前端完整基础门禁 | python3 tests/run_gates.py --ref afbad60 --groups ui --only node,components,discipline,contrast --out /tmp/omrs-mcp-review-ui；Node 437/437 无 skip，组件浏览器 34/34，UI 0 问题，对比度 58/58 |
| 相关网页 E2E | python3 tests/run_gates.py --ref afbad60 --groups e2e --only e2e-mcp,e2e-mcp_expansion,e2e-mcp_review_sessions,e2e-schedule,e2e-settings,e2e-runtime_history --out /tmp/omrs-mcp-review-e2e；六组均退出 0 |

E2E 实际计数：MCP 39/39，MCP 扩展 17/17，新调度闭环 14/14，运行历史 34/34，调度 45/45，设置 71/71，共 220 项。新增闭环用真实 SDK 创建两题，浏览器检查已有计划、授权和反馈进度，网页撤销后重试不复活；全部路径无脚本错误。

领域专项包括 SQLite 真实 BUSY/LOCKED、投影与回执发布故障回滚、同/不同请求竞争、跨进程链头变化、等锁及提交前/返回前权限变化、UID 移动重用、状态恢复后的旧回执。运行记录最终 15/15 无 skip；并行期间模块尚未落地的 skip 未作为通过依据。

初次新 SDK 测试错误地期待共享 result 包装，实际 MCP 一直返回扁平结果；修正测试后 3/3。首次旧工具清单回归未更新精确集合，补入新工具后在完整回归通过；未放宽权限或参数校验。

## 视觉验证

python3 tests/visual/run.py --ref afbad60 --pages settings,schedule --out /tmp/omrs-mcp-review-visual，8 组比较：浅/深色桌面设置均 0.002%，调度均 0.001%，只来自侧栏补丁版本号；四组手机均 0%。

python3 tests/visual/run.py --ref afbad60 --pages settings --settings-section access --out /tmp/omrs-mcp-review-access-visual，4 组比较：浅色桌面 6.235%、深色桌面 6.216%、浅色手机 5.868%、深色手机 6.101%。变化来自新增复习调度能力卡、引导文字与后续卡片/页脚位置移动，是预期界面变化。人工查看浅色桌面和深色手机当前截图，排版正常；所有审计均 0 小目标、0 行内样式、0 横向溢出、0 脚本错误。

## 文档与提交

同步版本四处、changelog、MCP、权限、安全、共享查询、数据/回执、Ledger、前端相关文档及本计划进度。生成 routes 与日志索引。收尾运行 python3 tests/check_docs.py --diff afbad60 和 git diff --check，均退出 0；文档检查 96 份、0 问题，另有两份既有超大计划文件提示，不属于本次改动。

按计划一次功能提交含代码、测试、文档、日志及 progress。未推送或部署。

## 未执行与下一步

未执行生产发布、Git 推送、公网写入和 ChatGPT 账户连接验收，因为用户没有单独授权生产变更。未运行无关模型数据 E2E 或访问训练材料。新增工具在隔离实例可用，生产仍待发布；发布后需在密钥权限中显式启用 session:create，并刷新客户端工具清单。
