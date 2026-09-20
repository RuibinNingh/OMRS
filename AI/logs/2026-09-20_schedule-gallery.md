# 2026-09-20 复习调度画廊视图

## 变更摘要

复习调度的安排复习工作区新增列表/画廊切换。两种视图共享同一份后端候选、筛选状态和勾选状态，切换不会重新请求推荐或丢失已选题。视图偏好存于 `localStorage['omrs-schedule-view']`，默认列表，刷新后恢复已保存的列表或画廊值。

画廊卡复用 `qvRender()` 和 `QV_CARD_OPTS` 渲染题面，使用 `clamp:8`，显示公式、图片和 Markdown，答案不进入卡片 DOM。预览节点使用 `IntersectionObserver` 懒加载；不支持该 API 时直接加载。桌面使用自适应网格，窄屏（≤760px）改为单列，卡片预览设置独立滚动和高度上限。

## 修改文件

- `assets/recommend_v2.js`：视图状态、localStorage 恢复、qview 懒加载挂载和列表/画廊渲染。
- `assets/styles.css`、`omrs_dashboard.html`：切换控件、画廊卡片网格与窄屏布局。
- `tests/test_recommend_v2_filters.js`：补充推荐状态、日期、标记、均衡排序和异步响应测试。
- `AI/frontend.md`、`README.md`：同步当前用户可见行为。

## 验证

`python3 -m unittest tests.smoke_schedule_workbench` 通过，耗时 15.273 秒。真实 HTTP+Chromium 流程覆盖画廊切换、勾选保留、科目筛选同步、公式显示、答案不渲染、预览失败重试、刷新后保留视图、390px 无横向溢出，以及上一轮完整计划主路径。

`node --test tests/test_recommend_v2_filters.js tests/test_schedule_sessions.js` 共 8 项通过。现有 8471 服务只读浏览器检查 41 张候选卡片，首屏附近按需挂载 9 个预览，零 `pageerror`；桌面和手机截图已检查。此次只有前端改动，无需重启服务。`git diff --check` 与 `python3 tests/check_docs.py` 均通过，后者检查 14 个文档、0 处问题。

## 同步过的文档

已同步复习调度的列表/画廊视图、qview 题面预览、答案隐藏、懒加载、持久化视图偏好和窄屏单列行为。
