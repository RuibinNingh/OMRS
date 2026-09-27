# 前端：仪表盘与目录页

> **速查**
> - 职责：仪表盘（今天、行动推荐、概览、近 30 天、最薄弱科目、最近动态）与目录树页
> - 入口：`assets/app/features/dashboard/`（`index.js` 页面契约、`plan.js` 行动推荐规则、`state.js` 派生、`view.js`、`dashboard.css`）；`assets/app/features/catalog/`
> - 不变量：仪表盘只读统计快照（`domain/data.js`）与 Session 列表，唯一自己发的请求是最近动态的 `/api/history?limit=40`；停用题不进入行动计划；页面之间不互相 import
> - 必跑测试：`tests/app/dashboard.test.mjs`、`tests/e2e/dashboard.py`、`tests/app/catalog.test.mjs`、`tests/e2e/catalog.py`、`tests/test_catalog_tree.py`、`tests/test_question_suspend_frontend.js`
> - 相关：`AI/frontend.md`（索引）、`AI/frontend/architecture.md`（数据所有权、过渡桥）

## 仪表盘（`features/dashboard/`，v1.25.0 起）

首页只回答「今天做什么」，自上而下是：今天 → 行动推荐 → 概览 → 近 30 天活动 / 最薄弱的科目（两栏，窄了自动单栏）→ 最近动态。分布类图表不在首页，在「数据复盘」页（`features/data/`，见 `AI/frontend/records.md`）。

- **数据**：统计快照读 `store.data`（`domain/data.js` 发布）；Session 列表经 `domain/sessions.js`。`store.data` 变化、bus 的 `sessions` 都重绘；每次数据刷新或收到 `history:changed` 后重拉最近动态；bus 的 `ledger:tz`（设置里改 Ledger 时区，`app.js` 发）只重新投影时间。
- **渲染**：`morph(root, view(env))`，每块带 `data-key`；根节点 `.dsh[data-dash-ready]` 是 E2E 的就绪标记。模板不写 `style=`：热力格用 `data-level`，进度与科目条用原生 `<progress>`（`ui/progress`）。
- **字号**只用六档：display 40（今天的数字，全站唯一）、xl 20（概览与指标数字）、lg 16（卡片标题）、md 14（正文）、sm 13（按钮、说明）、xs 12（元信息、标签）。可点目标桌面 ≥28、手机 ≥40。

| 块 | 数据 | 说明 |
|---|---|---|
| 今天 `.dsh-today` | 快照 `items` / `daily_trend` + 未结束 Session | `state.todaySummary()`：待复习 = 未停用、未击杀、逾期或今日到期；分项标签（逾期 / 今日到期 / 未录反馈 / 没有到期的题）；今天已练对比 `plan.todayTarget()`（到期 + 至多 3 道顽固题，封顶 20）；一句提示；主按钮「开始复习」或「随便练几题」，次按钮「只看逾期 N 题」或「去录反馈」。数字按状态着色（逾期红、清空绿）。空库显示「题库还是空的」与「去录入题目」；首次加载失败（没有快照）时这里显示原因与「重新加载」 |
| 行动推荐 `.dsh-plan` | 同上 | `plan.buildPlan()`，规则见下节；默认显示前 4 条，「还有 N 条建议」展开、「收起」收回。图标是 `ui/icon` 的 SVG，图标圈与指标数字按级别着色 |
| 概览 `.dsh-kpis` | 快照 `total` / `killed` / `attacking` / `avg_mastery` / `suspended` | 五格（击杀率、「不参与复习」为附注）；末尾「重新扫描」（`data-action="app.scan"`，见 `AI/frontend/shell.md`）。窄屏 3 列，手机 2 列 |
| 近 30 天活动 | 快照 `recent_activity` | `state.heatmap()`：两行各 15 格，末格是今天；级别 0–4 按当天次数占峰值比例；上方是总复习、活跃天数、单日峰值，下方首尾日期与图例。格子的 `title` 给日期与次数 |
| 最薄弱的科目 | 快照 `items` | `state.weakSubjects()`：未停用题按科目求衰减后熟练度均值，题量 ≥5 才纳入，升序取 6 个；每行是按钮，点了跳题库并按该科目、熟练度升序筛选 |
| 最近动态 | `/api/history?limit=40` | `domain/history.js` 取数与投影，直接复用 `domain/history-model.js` 的标题和撤销判定：去掉修正类与已撤销节点，按 seq 倒序取 4 条。超过 300ms 才显示骨架；失败显示原因与「重试」；「完整时间线」切到历史记录 |

### 跳转

行动推荐与「今天」的按钮是跳转描述（不是闭包），`index.js` 统一执行：

| `go` | 做什么 |
|---|---|
| `questions` | 切到题库后发 bus `questions:preset`（预设键沿用旧元素 id，如 `{'q-filter-due': 'overdue'}`），题库页先清空全部条件再套用 |
| `instant` | 切到即时练习后发 `instant:load`（预设如 `{'inst-subject': '数学'}`） |
| `review` | 切到复习调度后发 `schedule:view`（打开「安排复习」） |
| `feedback` | 切到反馈录入；带 Session 时再发 `feedback:session` 选中它 |
| `page` | 切到某页（录入题目、数据复盘、历史记录） |

## 行动推荐规则（`plan.js` 的 `buildPlan()`）

纯函数，输入 `{ items, data, sessions, dueDays, today }`，node 单测全覆盖。每条建议 `{ key, level, icon, metric, title, detail, actions }`，按级别排序（紧急 → 建议 → 可选 → 状态良好）。只看未停用、未击杀的题。

| key | 级别 | 条件 | 动作 |
|---|---|---|---|
| `empty` | 可选 | 题库为空（唯一一条） | 去录入题目 |
| `overdue` | 紧急 | 有逾期题；详情写最久逾期天数 | 立刻练逾期题（即时练习）、在题库查看（逾期、到期升序） |
| `due_today` | 建议 | 有今日到期 | 开始常规复习（复习调度「安排」）、查看清单 |
| `pending_feedback` | 建议 | 有未结束的 Session | 去录反馈（选中第一个） |
| `leech` | 紧急 | 有顽固题 | 看顽固题清单（数据复盘）、按熟练度排题库 |
| `untouched` | 可选 | ≥3 道从没练过 | 挑出来练一轮（题库按日期） |
| `cold` | 建议 | ≥3 道上次复习超过 30 天 | 按最近复习排序 |
| `idle` / `never` | 建议或可选 | 最近一次练习距今 ≥3 天（≥7 天为建议）/ 从没有练习记录 | 做 5 道找回手感 / 开始第一轮练习 |
| `low_not_due` | 可选 | ≥3 道未到期但衰减后 <50% | 按衰减挑题 |
| `weak_subject` / `weak_category` | 可选 | 题量 ≥3 的组里最低、且均值 <55% / <45%（只有一组时不算） | 专练该科目（或分类）、看该科目题目 |
| `all_good` | 状态良好 | 没有紧急与建议项时插到最前 | 加练几道 |

## 目录页（`features/catalog/`，v1.25.6 起）

Tab「目录」挂载到 `#cat-app`。`index.js` 管理请求和页面生命周期，`state.js` 纯函数构建后备树、统计和搜索匹配，`view.js` 渲染，`catalog.css` 提供响应式样式。后端仍由 `omrs/catalog.py` 提供只读 `GET /api/tree`。

### 数据和失败处理

- **磁盘结构**来自 `/api/tree`，页面内强制「重新读取」；非强制进入可复用上次快照。首次请求超过 300ms 才显示骨架。刷新失败时保留旧树并显示原因；首次失败则由 `fallbackTree(items)` 按题目路径构建后备树，只含题目文件，状态栏说明来源。
- **学习状态**来自 `store.data.items`，`folderStats()` 按路径前缀叠加题数、已击杀数、到期数、顽固题数和衰减熟练度。统计快照变化时重算这些值，不重新扫盘；后备树同时按新题目列表重建。
- **扫描联动**：工具栏的「重新扫描」仍是外壳统一的 `app.scan`；扫描成功后外壳发 `catalog:refresh`，本页重新读取磁盘树。失败时保留原树。页面卸载后取消订阅，迟到的请求结果不再渲染。

### 浏览与操作

- `each()` 以路径为 key 渲染嵌套目录。首次进入默认展开根目录与一级目录；切页后保留展开集合。「全部展开 / 全部折叠」批量更新路径集合。搜索命中目录、文件或后代时临时展开匹配分支，不改动原集合，清空后恢复原状态。
- 「显示图片等其他文件」勾选后显示 `/api/tree` 的非题目文件；默认只显示题目文件。题目行有到期标记、熟练度条与百分比，非题目文件显示大小。目录行有题数、待复习、顽固题和平均熟练度。
- 已入库题目行经 `domain/question` 打开题目弹窗；每个目录的复制按钮复制相对路径，浏览器拒绝剪贴板时在页首显示可手动复制的路径。
- `#catalog-stat` 用四张统一统计卡显示文件夹、题目文件、全部文件和占用；`#catalog-status` 说明降级、孤立文件、层级截断、搜索或复制结果。空目录与无搜索结果都有说明和下一步操作。
- 窄屏下统计卡两列、控件高度至少 40px，文件名截断，题目到期标记和数值分行；无行内事件或样式。对应 Node 测试在 `tests/app/catalog.test.mjs`，主路径和四种视觉审计在 `tests/e2e/catalog.py`。
