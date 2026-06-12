# 2026-06-12 仪表盘与数据页图表分工调整

## 背景

首页仪表盘已经有每日练习趋势、活动热力、分布与预警；难度-熟练度散点图偏诊断分析，继续放在首页会挤占行动信号空间。数据页的科目维度只有表格，不够直观看出各科熟练度差异。

## 改动

- `omrs_dashboard.html`
  - 首页移除「难度-熟练度散点图」卡片。
  - 「待复习队列预警」提前到首页第二行，与「每日练习趋势」并排。
  - 首页「熟练度分布」与「难度分布」并排，减少底部孤立大卡片。
  - 数据页新增 `data-scatter`，承接难度-熟练度散点图。
  - 数据页科目维度卡片新增 `data-subject-radar`，放在科目表格上方。
- `assets/dashboard.js`
  - 删除首页散点图渲染逻辑，避免移除 DOM 后空引用。
  - 待复习队列预警改成二乘二布局，更适合半宽卡片。
- `assets/data.js`
  - 新增 `renderSubjectRadar()`，基于 `analytics.subjects[].avg_mastery` 画各科平均熟练度雷达图。
  - 新增 `renderDataScatter()`，基于 `analytics.items` 画难度-熟练度散点图。
- `AI/frontend.md`
  - 同步更新仪表盘与数据页图表归属。

## 验证

- `node --check assets/dashboard.js`
- `node --check assets/data.js`
- 浏览器刷新 `http://127.0.0.1:8471/`，确认首页无散点图、预警提前、数据页出现科目雷达图与散点图。
