# 2026-06-11 即时练习与调度批量选择

## 背景

调度页需要更快维护推荐题目的勾选状态，并新增一个不生成调度 Session 的在线复习入口：按算法直接推荐题目，也允许按科目、分类、知识点收窄范围。

## 改动

- `omrs/scheduling.py`：`generate_recommendations()` 新增 `category`、`knowledge_tag` 筛选，筛选发生在到期/熟练度双列表分配前。
- `omrs/server.py`：`GET /api/recommend` 透传 `category`、`knowledge_tag` 查询参数。
- `omrs_dashboard.html`：调度推荐面板新增「选择当前筛选 / 全选推荐 / 移除当前筛选」；新增「即时练习」Tab 与页面骨架。
- `assets/recommend.js`：新增批量维护推荐勾选的函数，支持当前筛选批量选择、全选推荐、当前筛选批量移除。
- `assets/instant.js`：新增即时练习模块。它调用 `/api/recommend` 取题、`/api/question` 渲染题面/答案、`/api/feedback` 提交已判定反馈，使用 `IMM-YYYYMMDDHHMMSS` 标记历史记录但不写 `sessions.csv`。
- `omrs/feedback.py`：`POST /api/feedback` 支持每条反馈携带 `source`（`due`/`proficiency`）；持久化 Session 仍优先使用 Session 内保存的来源。
- `assets/core.js` / `assets/app.js` / `assets/styles.css`：新增即时练习全局状态、筛选下拉、Tab 初始化与页面样式。
- `AI/api.md`、`AI/algorithm.md`、`AI/frontend.md`：同步 API 参数、推荐筛选逻辑和前端模块说明。

## 行为边界

- 即时练习不调用 `/api/confirm-schedule`，不会生成 EXP/TMP 调度记录。
- 即时练习提交反馈仍走 `process_feedback()`，并逐题传入推荐来源，因此会按到期/熟练度来源差异更新 mastery、EF、Interval、Due_Date 与历史记录。
- 推荐页「全选推荐」只选择当前 `/api/recommend` 返回的双列表，不等于全题库全选。
