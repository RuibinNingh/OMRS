# 2026-06-12 反馈导入与运行状态

## 背景

录入题目的外部 JSON 导入和本地录入队列不再需要；反馈页需要同时支持屏幕版导出的作答 JSON 和外部 AI 整理出的反馈 JSON。系统还需要明确版本号，并提供一个可查询运行状态的接口，方便以后区分正在运行的实例。

## 改动

- `omrs/version.py`
  - 新增版本元数据，当前版本为 `v1.0.0`。
- `omrs/server.py`
  - 新增 `GET /api/status`，返回 `version`、`started_at`、`uptime_seconds`、`question_count`、`vault_path` 与运行状态。
- `omrs_dashboard.html`
  - 录入题目页移除「JSON 导入与录入队列」卡片和「暂存到队列」按钮。
  - 反馈页顶部改为「从屏幕版或 AI 导入反馈」，新增「复制 AI 反馈提示词」入口。
  - 设置页新增「运行状态」卡片，展示版本、运行时间、托管题目数、状态与 vault 路径。
- `assets/app.js` / `assets/core.js`
  - 删除录入队列的前端状态和函数。
  - 新增 `loadRuntimeStatus()`，进入设置页时读取 `/api/status`。
- `assets/schedule.js`
  - 新增 `copyFeedbackAiPrompt()` / `buildFeedbackAiPrompt()`。
  - 反馈 JSON 导入兼容外部 AI 常见字段别名：`correct` / `score`。
- `AI/api.md` / `AI/data.md` / `AI/frontend.md` / `AI/README.md`
  - 同步 API、数据交换格式、前端行为和版本说明。

## 影响范围

- 题目录入：只保留表单、图片粘贴、内置 AI 识别，不再有外部题目 JSON 队列。
- 反馈录入：同一个入口可导入屏幕版 JSON 或外部 AI 整理的反馈 JSON，导入后仍需人工核对再提交。
- 设置页：可直接查看当前运行实例版本和题目数。
