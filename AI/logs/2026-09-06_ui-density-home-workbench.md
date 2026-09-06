# 2026-09-06 · UI 改版：密度层 + 首页重构 + 整屏工作台

版本：v1.14.2 → **v1.15.0**。纯前端与文档改动，**后端 Python 未改动一行**。

---

## 1. 动机

- 首页是「5 张 KPI 大卡 + 行动推荐 + 最近动态 + 7 张图表卡」。其中熟练度分布、难度分布、
  待复习队列预警在「数据复盘」页有同口径的更全版本，属于纯重复；而每天打开首页真正想知道的
  「今天该做什么」被压在第二屏。
- 间距、圆角、行高全部写死 px，想整体收紧只能逐条改。
- 复杂页各自为战：收件箱处理页写死 `height:calc(100vh - 200px)`（那个 200 是数出来的），
  题库和反馈工作台靠 `position:sticky` + 整页滚动，长列表下工具条、表头和「提交反馈」会滚出视口。

## 2. 行为变化

### 2.1 界面密度（新功能，用户可见）

设置页「外观」新增「紧凑 / 舒适」开关，**默认紧凑**。状态存 `localStorage('omrs-density')`，
`<head>` 内联脚本与 theme / invert-img / sidebar 同批应用防闪。

`styles.css` 的 `:root` 新增 `--pad / --pad-sm / --gap / --row / --ctl / --fs / --fs-sm / --fs-xs`；
舒适档取值即改版前原值，所以关掉紧凑后外观与 v1.14.2 一致。
`html[data-density="compact"]` 额外覆盖 `--radius / -sm / -lg`，故所有引用这三个既有圆角变量的
规则自动跟随，无需逐条改写。

15 处写死 px 换成变量：`.card` `.stat-card` `.cols` `.card-title` `.btn` `.btn.sm` `.input`
`thead th` `tbody td` `.content` `.topbar` `.sched-item` `.sched-controls` `.stat-grid` `.qb-card`。

> `.input` 用 `padding:var(--ctl) 12px` 而非固定 `height`——录入页的 Markdown 编辑器是
> `textarea.input`，设死高度会坏。

### 2.2 首页重构

新顺序：**今天 → 行动推荐 → 概览条 → 近 30 天活动 + 最薄弱科目 → 最近动态**。

- 新增 `#dash-today`（`renderTodayHero()`）：整页唯一大字号。待复习总数 = 逾期 + 今日到期，
  下方拆「逾期 / 今日到期 / 未录反馈」，中列今日已练对比 `actionTodayTarget()`，右列主 CTA。
  左边框按状态着色；空题库走 `.is-empty` 引导态。数据全部来自已加载的 `DATA` / `SESSIONS`，
  **不新增接口**。
- 5 张 `.stat-card` → 一条 `.kpi-strip`。**id 全部保留**（`s-total` / `s-killed` / `s-kill-pct` /
  `s-attack` / `s-avgm` / `s-suspended`），`renderDash()` 的赋值一行未改。
- 新增 `#dash-weak`（`renderWeakSubjects()`）：按 `decayed_mastery` 升序取前 6，题量 ≥ 5 才纳入；
  每行是 `<button>`，点击调 `actionGoQuestions()` 跳题库对应筛选。
- 图表去向：
  - **搬到 `panel-data`、id 不变**：`chart-trend`、`chart-labels`。`renderTrendChart` /
    `renderLabelChart` 仍由 `renderDash()` 调用，函数零改动。
  - **容器删除**：`chart-subjects` / `chart-alerts` / `chart-mastery` / `chart-diff`，复盘页已有
    同口径更全版本。对应 render 函数保留且都以 `if(!el)return` 开头，找不到容器即空转（已逐个核对）。
- `.act-item` 在宽屏改单行栅格（`"icon body metric buttons"`）；卡头右上的「建议今天练 N」删除
  ——该数字已由「今天」条承担，避免同一数出现两次。

### 2.3 整屏工作台

`switchTab()` 给 `.content` 切 `.is-workbench`，命中 `questions` / `feedback` / `create` /
`board` / `instant` 五页。`@media(min-width:1161px)` 内 `.content.is-workbench` 变成
`height:100vh; overflow:hidden` 的 flex 列，高度一路分给各页的滚动容器。

结果：页面本身不滚，只有内容区滚；工具条、表头、判定按钮永远在原位。
**取代了原先 `calc(100vh - 魔数)` 的写法**（收件箱处理页那个 `200` 也一并去掉）。
详见 `AI/frontend.md` §1.2。

题库另外两处：`#qb-counts` 从表格上方独立一行搬进 `.qb-bar`（表格上方由 3 行变 1 行，
`qbRenderSummary()` 照旧写这个 id，JS 未改）；`#q-table-wrap thead th` 加 `position:sticky`。

窄屏（<1161px）保持 v1.14.x 既有响应式，未触碰。

## 3. 影响文件

| 文件 | 改动 |
|---|---|
| `assets/styles.css` | 密度 token 层；15 处 px → 变量；新增首页组件段、工作台段、紧凑档热力图覆盖；`.act-*` 单行化 |
| `omrs_dashboard.html` | `<head>` 读 `omrs-density`；仪表盘面板整块重写；`chart-trend` / `chart-labels` 移入 `panel-data`；`#qb-counts` 移入 `.qb-bar`；设置页加密度开关；侧栏版本号 |
| `assets/dashboard.js` | 新增 `renderTodayHero()` / `renderWeakSubjects()` / `dashSessions()`；`renderDash()` 增两处调用 |
| `assets/actions.js` | 行动条按钮内联；卡头去掉重复的目标数 |
| `assets/app.js` | 新增 `setDensity()`；`syncThemeControls()` 同步密度按钮；`switchTab()` 切 `.is-workbench` |
| `omrs/version.py` | v1.14.2 → v1.15.0 |
| `README.md` / `AI/README.md` / `AI/api.md` / `AI/frontend.md` | 版本号、特性表、版本历史、§1 图表表格订正、新增 §1.2 |

后端 `omrs/*.py` 除 `version.py` 外未改动；`/api/*` 请求与响应字段无变化。

## 4. 验证

- `node --check` 全部 `assets/*.js` 通过。
- **前端测试 10 个全绿**：`test_qtable_ui.js`、`test_feedback_ui.js`、`test_labels_ui.js`、
  `test_board_ui.js`、`test_md_linebreaks.js`、`test_omr_import.js`、
  `test_recommend_v2_filters.js`、`test_question_suspend_frontend.js`、
  `smoke_feedback_omr_import.js`、`smoke_frontend_actions_catalog.js`。
- 后端 unittest 抽查通过（未改动后端，仅确认未被波及）。
- **浏览器实机回归**：临时 vault 灌 34 道题 + 建 1 个 10 题 Session，起
  `omrs_engine.py serve`，用 Playwright（Chromium，1440×950）逐页截图——
  仪表盘（紧凑 / 舒适 / 浅色三态）、题目库（含筛选抽屉）、反馈录入（选中 Session 后三栏有内容）、
  展示板、即时练习、录入题目（`ibGo('process')` 处理页）、数据复盘、设置。
  **控制台 0 报错、0 page error**。
- 溢出自查：工作台页面 `document.documentElement.scrollHeight === clientHeight`（950 = 950），
  即页面级纵向滚动条确实消失。

### 过程中发现并修掉的问题

第一版工作台用 `height:calc(100vh - 206px)`，截图发现反馈页三栏溢出视口底部——该页在
`.fb-work` 上方还有 `.fb-session-bar` 和 `.fb-import` 两条，魔数算不准。改为 `.is-workbench`
flex 链路后复测通过。这也是顺手把收件箱处理页那个 `calc(100vh - 200px)` 一起换掉的原因。

## 5. 待办（本次未做）

- `AI/optimization.md` 的「前端大量 `innerHTML` + 行内 `onclick`」条目状态未更新：本次新增的
  `renderTodayHero()` / `renderWeakSubjects()` 仍是整块 `innerHTML` 渲染，沿用现有模式，
  没有改善也没有恶化该技术债。
- 密度只做了两档。若要更细（如表格单独一档），建议在 `--row` / `--ctl` 上再分层，不要新开变量组。
