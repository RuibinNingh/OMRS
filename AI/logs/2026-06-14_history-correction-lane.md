# 历史修正独立列表

## 背景

历史页原先把反馈修改、撤销、恢复和状态还原节点直接混入 Ledger 主时间线，且每个节点默认显示操作面板后再显示完整变更项。实际使用时会让主线被修正记录打散，也会让节点下方状态和表单占用太多空间。

## 改动

- `omrs_dashboard.html`：历史工具栏新增「还原历史」按钮和独立列表容器。
- `assets/schedule.js`：主时间线过滤 `review.replace`、`review.retract`、`review.restore`、`session.retract`、`session.restore`、`state.restore` 等修正节点；这些节点集中渲染到「还原历史」列表。
- `assets/schedule.js`：主时间线节点默认只保留一个「修改概要」折叠块，操作面板和完整 payload 都收进折叠块内。
- `assets/styles.css`：新增还原历史列表样式，并把历史操作面板调整为折叠块内的紧凑区域。
- `AI/frontend.md`：同步历史页主线/修正线分离的交互说明。

## 说明

Ledger 底层仍然追加所有修正 commit，保证可追溯和可重建；本次只调整历史页展示方式，避免把“还原到/撤销到/恢复到”的操作记录混进日常修改主线。
