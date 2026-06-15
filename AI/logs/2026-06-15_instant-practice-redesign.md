# 2026-06-15 即时练习页（`panel-instant`）响应式重设计

> 范围：纯前端（视觉 / 结构 / 响应式）。**版本号不变，仍 `v1.5.0`**。`instant.js`、所有 `#inst-*` id 与处理函数、`/api/recommend`·`/api/feedback` 流程均未改动。

## 动机

旧版两点问题：
1. **移动端差**：固定 `1fr / 320px` 双栏，≤1000px 塌成单列后把整条竖直队列列表压到题卡下方（要狂滚）；筛选栏 5 个控件挤成参差一行；评分行写死 `min-width:280px` 在小屏溢出；「提交」按钮埋在侧栏最底。
2. **布局草率**：v1.4.2「首批两页」现代化时把新规则叠在旧规则上、没删旧的，留下重复 / 失效声明（`.instant-head .uid` / `.meta-line` / `.tag-row`、被覆盖的 `.fb-toggle`、两套 `.instant-qbtn` 网格）。

## 改动

`omrs_dashboard.html` 的 `panel-instant` 骨架 + `assets/styles.css`：

- 骨架重排为 `.inst-work` 网格工作台，用 `grid-template-areas` 摆放四块（`#inst-summary` 进度+提交 / `.inst-queue-wrap`〔含「队列」label + `#inst-queue`〕/ `.inst-main`〔`#inst-empty` + `#inst-review`〕/ `#inst-submit-results`）。DOM 顺序固定，靠 grid-area 在桌面 / 移动两套布局间切换。
- **桌面**：左题卡（`minmax(0,1fr)`）+ 右栏 300px（进度+提交置顶 → 队列竖列 → 提交结果）。
- **移动端（≤900px）**：四块重排为 进度+提交 → 队列 → 题卡 → 结果。
  - 队列 `.instant-queue` 由竖列表转**横向圆点条**（flex-row + 横滚），`.instant-qbtn` 隐藏 `.instant-qmain`、只留 `.qn` + `.qmk`，点按跳题。
  - 评分 `.instant-grade` 竖排整行：`.fb-toggle` 占满、主观分滑杆单独一行（删 `min-width:280px`，桌面也更稳——改 `.instant-score{min-width:0}`）。
  - 导航 `.instant-nav` 改 2 列网格：`:nth-child(2)`（「下一道未判定」）`grid-column:1/-1;order:-1` 整行置顶，上一题 / 下一题各半。
  - 题头 `.instant-head` 竖排；筛选 `.inst-filters` 转 2×2 网格全宽、题数加可见标签 `.inst-count-field`、加载按钮整行。
- 提交按钮（JS 渲染在 `#inst-summary` 内）随进度块置顶，移动端不再埋底。
- **清理**：删除孤立 / 失效规则 `.instant-topbar` / `.instant-layout` / `.instant-side` / `.instant-summary` / `.instant-filters`、`.instant-head .uid` / `.meta-line` / `.tag-row`、旧 `@media(max-width:1000px)` 即时块；新样式收拢成一段并入文件末尾。

## 契约保持

静态 id：`inst-status` / `inst-subject` / `inst-category` / `inst-ktag` / `inst-count` / `inst-empty` / `inst-review` / `inst-summary` / `inst-queue` / `inst-submit-results` 全部保留。JS 生成的内容类（`.instant-head` / `.instant-pos` / `.instant-uid` / `.instant-chips` / `.instant-prog` / `.instant-tagrow` / `.instant-md` / `.instant-block` / `.instant-answer` / `.instant-grade` / `.fb-toggle` / `.instant-score` / `.instant-nav` / `.instant-qbtn` / `.qn` / `.qmk` / `.result-row` 等）只重新着色 / 排版，未改其结构与 `instReveal` / `instSetVerdict` / `instSetScore` / `instGo` / `instSubmitPractice` 等 onclick 契约。

## 涉及文件

- `omrs_dashboard.html` — 替换 `panel-instant` 内部骨架（panel 标签 / id 不变）。
- `assets/styles.css` — 删除 9 条孤立 / 失效即时规则；末尾追加一段 `.inst-*` 响应式样式。
- `AI/frontend.md` — §5 增补「响应式工作台」布局说明。

---

## 同日修订（bug 修复）

1. **桌面队列漂移 / 居中**：`.inst-work` 原用 `grid-template-areas` 且 `.inst-main` 跨越右栏三行 → 题卡高度变化时多出的高度被均摊进右栏各行，队列被撑开、上下漂移、看着像居中。改为显式 `grid-column` / `grid-row` 放置 + `grid-template-rows:auto auto auto 1fr`，让末尾 `1fr` 空行吸收题卡的多余高度，右栏（进度 / 队列 / 结果）稳定贴顶。移动端 `.inst-work` 改 `display:flex;flex-direction:column;align-items:stretch`（DOM 顺序本就是 进度→队列→题卡→结果，无需 order）。
2. **筛选两列不等宽**：题数字段 min-content 较宽，把它那一列撑大。给 `.inst-filters>*` 加 `min-width:0`，2 列恢复等宽；题数标签 `.inst-count-field span` 加 `white-space:nowrap` 防止窄屏折成两行。
3. **深色「反转题图」不生效**：invert 规则旧选择器是 `.instant-qmain img`（队列项里并没有图），题面 / 答案实际渲染进 `.instant-md`（备注进 `.instant-notes`）。改为 `html[data-theme="dark"][data-invert-img="1"] .instant-md img, … .instant-notes img{filter:invert(1)}`；并修正 `AI/frontend.md` v1.3.0 注记里过时的 `.instant-q` 选择器。

均为 CSS 改动，`instant.js` 仍未改。
