# 2026-11-15 复习调度暂停与恢复

> **任务**
> - 标识：schedule-pause
> - 状态：已交付

## 背景

用户原话：「给生成的复习调度加一个暂停功能」。执行者为 Codex，完整模式；基线为 `56de242`，开工 `git status --short` 为空。本次为独立功能任务，不属于既有执行计划。保留当前版本 v2.11.4，不涉及生产部署、systemd 或推送。

## 行为变化

已有未完成计划提供「暂停调度／恢复调度」和「已暂停」筛选。暂停持久保留题目、来源及已录入进度，移出待完成计数与首页提醒，题目可重新安排。暂停详情可预览、导出；反馈页标明暂停并禁止提交，但不清除未提交的表单。恢复沿用原进度，不平移题目复习日期或冻结衰减；题目被其它待完成计划占用时提示关联编号，保持暂停。

后端在同一 SQLite 写事务中检查新鲜投影、验证恢复占用、追加 `session.pause`／`session.resume` 并发布投影。重复设置不重复追加事实；已完成、已撤销计划拒绝切换。投影失败整体回滚。助手与 MCP 的只读计划筛选增加 paused，创建幂等重试反映当前暂停状态且可反馈题数为0。历史页以 Session 类型显示暂停和恢复记录。

## 影响文件

按 `git diff --name-status` 和未跟踪新文件复核：

- `omrs/session_operations.py`、`omrs/projections.py`、`omrs/feedback.py`：事务状态变更、重放和反馈边界。
- `omrs/http/learning.py`、`omrs/http/registry.py`：网页暂停／恢复接口；`AI/routes.md` 由脚本重新生成。
- `omrs/agent/tools/read.py`、`omrs/mcp/server.py`、`omrs/mcp/tool_docs.py`：只读筛选支持暂停状态。
- `assets/app/domain/sessions.js`、`assets/app/domain/history-model.js`：共享状态发布、旧响应失效与历史分类。
- `assets/app/features/schedule/` 的 index/state/view，以及 `assets/app/features/feedback/` 的 index/view：操作入口、状态展示、忙态、筛选与反馈保护。
- `tests/test_session_pause.py`、`tests/app/schedule.test.mjs`、`tests/e2e/schedule.py`：持久化、回滚、并发占用、只读查询、前端旧响应和真实浏览器路径。
- `AI/api.md`、`AI/api/boards.md`、`AI/data.md`、`AI/ledger.md`、`AI/algorithm.md`、`AI/agent.md`、`AI/mcp.md`：接口、数据、事务和查询当前契约。
- `AI/frontend/architecture.md`、`AI/frontend/review.md`、`AI/frontend/feedback.md`、`AI/frontend/records.md`、根 `README.md`：页面与使用说明；本日志及自动生成的日志索引记录验证。

## 已执行验证

全部业务检查仅使用临时 Vault 和随机高端口，启动环境清除 `OMRS_SYSTEMD_SERVICE`、`OMRS_BOXDETECT_CONTROL`，未访问真实题库。

- 首轮后端：`python3 -m unittest tests.test_session_pause tests.test_session_operations tests.test_schedule_workbench tests.test_sessions_feedback tests.test_session_queries -q`，54项通过；其中新增暂停专项当时为8项。
- `node --test tests/app/*.test.mjs`：599项通过，无失败或跳过，输出 `/tmp/omrs-schedule-pause-node.log`。
- `python3 tests/app/run_browser.py`：35项通过，输出 `/tmp/omrs-schedule-pause-components.log`。
- `python3 tests/check_ui.py`：全仓0问题；`python3 tests/check_contrast.py`：58组全部达标。
- 首轮 `python3 tests/e2e/schedule.py`：53项通过，覆盖暂停失败、忙态防重复、部分进度、刷新、占用冲突、恢复和手机；输出 `/tmp/omrs-schedule-pause-e2e.log`，状态截图在 `/tmp/omrs-schedule-pause-shots-ypz7lqkt/`。
- `python3 tests/e2e/feedback.py`：43项通过，输出 `/tmp/omrs-schedule-pause-feedback.log`。
- `python3 tests/visual/run.py --ref HEAD --pages schedule,feedback,history --out /tmp/omrs-schedule-pause-visual`：12组前后截图，页面脚本错误为0。报告在 `/tmp/omrs-schedule-pause-visual/report.html`；逐项差异见下文。
- 首次扩展后端调用失败：114个测试条目中2个模块加载错误，分别为按包名调用 MCP 测试时缺少 tests 导入路径，以及误写不存在的 `tests.test_mcp_boundary`。这是调用错误，不能计为整组通过。
- 修正后的 `python3 -m unittest tests.test_session_pause tests.test_session_operations tests.test_schedule_workbench tests.test_sessions_feedback tests.test_session_queries tests.test_history_projection tests.test_ledger_concurrency tests.test_agent_tools tests.test_security tests.test_http_boundaries -q`：115项通过，其中暂停专项11项，输出 `/tmp/omrs-schedule-pause-python-rerun.log`。补充验证学习状态恢复、两个并发请求竞争同一题目，以及共享只读筛选。
- `python3 -m unittest discover -s tests -p test_mcp_review_sessions.py -q`：4项通过，输出 `/tmp/omrs-schedule-pause-mcp.log`。
- 补充反馈页暂停检查后的调度 E2E 首次复跑为53通过／1失败，断言在推荐刷新结束前检查仍处忙态的录入按钮。保留产品忙态，只让断言等待操作完成；最终 `python3 tests/e2e/schedule.py` 为54项通过／0失败，输出 `/tmp/omrs-schedule-pause-e2e-verified.log`。暂停计划的反馈页提示、禁用提交及桌面／手机路径均实际通过。
- `python3 tests/check_docs.py --write-routes`、`python3 tests/check_docs.py --write-log-index`、`python3 tests/check_docs.py --diff HEAD` 与 `git diff --check` 已执行，文档门禁0问题；最终交付前再次核对状态和索引。

视觉差异：调度与反馈各4组均无像素差异，覆盖未选中暂停计划的默认入口；历史手机浅深色也无差异。已裁剪查看历史桌面浅色0.004%、深色0.003%的微小差异，位于初始化操作时间的秒数字，来自两次隔离服务的真实启动时刻，布局与内容一致；裁剪证据 `/tmp/omrs-schedule-pause-history-diff.png`。暂停功能本身由真实 E2E 的详情及手机截图覆盖，不以默认入口的零差异代替验收。

## 未执行验证

未运行全仓 Python 全量和无关业务 E2E，按本次风险选择调度、反馈、Ledger、查询、鉴权与 MCP 专项。生产部署、真实题库、Windows 实机和实体手机未执行，本轮没有外部变更授权。本次无已知未完成的功能项；下一步可在获授权后发布当前源码，保留最新 Vault。
