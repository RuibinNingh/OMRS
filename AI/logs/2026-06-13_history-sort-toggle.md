# 历史时间线排序切换

## 摘要

- 历史记录页新增排序选择器。
- 支持 `旧 → 新（最新在底部）` 和 `新 → 旧（最新在顶部）` 两种方向。
- 选择结果保存到浏览器本地，下次进入历史页沿用。

## 改动

- `omrs_dashboard.html`：历史工具栏新增排序下拉框。
- `assets/schedule.js`：新增 `currentHistorySort()` / `setHistorySort()`，渲染时间线时按 seq 排序并按方向滚动到最新节点。
- `assets/styles.css`：补充历史工具栏布局样式。
- `AI/frontend.md`：同步历史页排序说明。
