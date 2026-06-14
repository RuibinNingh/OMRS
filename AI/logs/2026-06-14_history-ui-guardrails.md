# 历史页 UI 防误触与摘要优化

## 背景

历史页已经支持 Ledger 时间线和修正记录，但默认节点里直接暴露「修改 / 撤销 / 还原」操作，日常浏览时信息层级偏重，且 `review.batch_submit` 这类节点摘要偏技术化。

## 改动

- `omrs_dashboard.html`：历史工具栏新增「修正模式」开关；「还原历史」改名为「修正记录」。
- `assets/schedule.js`：默认关闭修正模式，主时间线只显示只读详情；开启后才显示节点内「修改 / 撤销 / 还原」操作面板。
- `assets/schedule.js`：主节点摘要改成题目优先格式，练习反馈节点标题直接显示 UID（多题显示前几题），副标题显示有效题数、对错数、已撤销条数和 Session。
- `assets/styles.css`：补充修正模式开关和节点副标题样式。
- `AI/frontend.md`：同步历史页 UI 行为说明。

## 验证

- `node --check assets/schedule.js`
