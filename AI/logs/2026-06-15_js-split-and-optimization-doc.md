# 2026-06-15 前端 JS 按职责拆分 + 新增优化清单

> 范围:纯前端结构整理 + 新增文档。**版本不变,仍 `v1.5.0`**。零行为改动:函数名/签名/调用关系与后端接口全不变。

## 动机

代码走查发现 `assets/schedule.js`(约 100 行)是个杂烩,混了六类互不相关的职责;整体也偏臃肿。用户要求「适量的分离」。

## 改动:拆分 `schedule.js`

因所有脚本是普通 `<script>` 共享同一全局作用域、行内 `onclick` 在运行时调用,把函数搬到新文件零风险(只要都在 `app.js` 前加载)。按职责拆出三个文件,`schedule.js` 大幅瘦身:

- `assets/export.js` ← 导出选题 / 画廊预览 / A4·屏幕变体 / 下载(原 schedule.js 行 2–16、88–99)
- `assets/feedback.js` ← 反馈录入页:session 选择、行编辑、AI 提示词、JSON 导入、提交(原行 23–49)
- `assets/history.js` ← 数据复盘/历史:Ledger 时间线、修正面板、撤销/恢复/还原(原行 52–85,最大的一块)
- `assets/schedule.js`(瘦身后)← 复习 Session 创建/预览/删除/列表 + 工作区扫描 + 录入提交(doCreate/resetCreateForm),100 → 12 行

`omrs_dashboard.html`:在 `schedule.js` 后依次加入 `export.js` / `feedback.js` / `history.js` 的 `<script>`(都在 `core.js` 后、`app.js` 前);四个脚本 `?v=` 提到 `20260615-split` 以刷新缓存。

## 校验

- 函数清单:拆分前后 72 个顶层函数完全一致(集合相等、无重复、无丢失)。
- `node --check` 四个文件全部通过。
- 未拆 `export` 的两段是连续的;`app.js` 未改动(录入页图片/AI 逻辑仍在其中,与 `schedule.js` 的 doCreate 协作,属既有安排,本次不动)。

## 同时新增

- `AI/optimization.md` ← 整体代码/架构走查的优化清单(单线程服务器、投影全量重放、CSS 叠加债、路由 if/elif、innerHTML 重渲染、测试缺失、Google Fonts 外链、局域网无鉴权等),按影响/工作量/状态标注,可逐条勾掉。本次拆分对应其中一条,已标完成。
- `AI/frontend.md` §文件组织:更新 assets 树 + 加载约定补「拆分(v1.5.0)」说明;修正三处指向 `schedule.js` 的过时引用(反馈/历史函数现在 feedback.js / history.js)。
