# 2026-09-20 复习调度工作台

## 变更摘要

复习调度页改为安排复习与已有计划两个工作区。页面自动加载推荐，默认建议 10 题，支持折叠筛选、筛选 chips、保留已选、直观推荐原因、固定选择栏和按科目均衡选择。已有计划支持状态筛选、搜索、详情、进度、题目预览、导出和跳转反馈。

推荐候选以 `/api/recommend` 的后端顺序、`_source`、到期日期和熟练度为事实来源；前端只做筛选与科目轮选。推荐加载使用请求序号丢弃过期响应，并保留错误状态和重试入口。创建计划传 `persist:true`，单题也生成正式 Session；未传该字段的旧单题请求仍生成 TMP 调度。

新增回归覆盖了正式单题与来源间隔、重复选择去重、非法选择不写入、计划列表/详情的异步竞态，以及标记 any/all、数值范围、日期筛选、隐藏选择保留、导出切换、反馈完成和失败重试。调度页签支持方向键、`Home`、`End`；手机布局在 390px 宽度采用两行候选网格。

## 修改文件

- `omrs_dashboard.html`、`assets/recommend_v2.js`、`assets/schedule.js`、`assets/styles.css`
- `omrs/server.py`、`omrs/sessions.py`、`omrs/scheduling.py`
- `tests/` 中的调度、推荐与接口回归测试
- `AI/frontend.md`、`AI/api.md`、`AI/algorithm.md`、`AI/data.md`、`AI/export.md`、`AI/README.md`、`README.md`

## 验证

已运行 `python3 -m unittest tests.test_schedule_workbench tests.test_recommendations tests.test_sessions_feedback tests.test_question_suspend tests.test_labels`（22 项通过）、`node --test tests/test_recommend_v2_filters.js tests/test_feedback_ui.js tests/smoke_frontend_actions_catalog.js`（10 项通过）、`node --test tests/test_schedule_sessions.js`（2 项通过）和 `python3 -m unittest tests.smoke_schedule_workbench`（浏览器主路径通过，14.747 秒）。浏览器流程覆盖真实 HTTP+Chromium 下 10 题/单题生成、刷新持久化、A4/屏幕版下载、分批反馈至完成、筛选、明暗主题、390px 手机、键盘页签、推荐/计划列表与详情失败重试、题库/即时练习回归；零 `pageerror`。截图保存在 `/tmp/omrs-schedule-verification/`。

生产服务于 23:26:37 执行 `systemctl restart omrs.service`，因现有 TCPServer 地址占用发生短暂自动重试，23:26:56 恢复；最终 PID 为 `2178469`，状态 `active`，`NRestarts=6` 且之后不再增长。只读浏览器检查发现 6 个已有计划、1 个待完成计划、科目选项 6 个、推荐 41 题且零异常；无效 `persist` 请求返回 400，确认运行新接口并在写入前拒绝。未用真实数据执行生成/反馈写入流程，现有计划保留；端口释放问题仅登记于 `AI/optimization.md`，本任务未改 `omrs/cli.py`。

`git diff --check` 通过；最终 `python3 tests/check_docs.py` 通过（14 个文档、0 处问题）。

## 同步过的文档

同步了调度工作台界面、推荐排序来源、`persist:true` 请求兼容语义、正式 Session 数据落盘和计划详情导出入口。
