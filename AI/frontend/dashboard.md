# 前端：仪表盘与目录页

> **速查**
> - 职责：仪表盘（今天、行动推荐、概览、近 30 天、最薄弱科目、最近动态）与目录树页
> - 入口：`assets/app/features/dashboard/`（`index.js` 页面契约、`plan.js` 行动推荐规则、`state.js` 派生、`view.js`、`dashboard.css`）；`assets/catalog.js`
> - 不变量：仪表盘只读统计快照（`domain/data.js`）与 Session 列表，唯一自己发的请求是最近动态的 `/api/history?limit=40`；停用题不进入行动计划；页面之间不互相 import
> - 必跑测试：`tests/app/dashboard.test.mjs`、`tests/e2e/dashboard.py`、`tests/smoke_frontend_actions_catalog.js`、`tests/test_catalog_tree.py`、`tests/test_question_suspend_frontend.js`
> - 相关：`AI/frontend.md`（索引）、`AI/frontend/architecture.md`（数据所有权、过渡桥）

## 仪表盘（`features/dashboard/`，v1.25.0 起）

首页只回答「今天做什么」，自上而下是：今天 → 行动推荐 → 概览 → 近 30 天活动 / 最薄弱的科目（两栏，窄了自动单栏）→ 最近动态。分布类图表不在首页，在「数据复盘」页（`features/data/`，见 `AI/frontend/records.md`）。

- **数据**：统计快照读 `store.data`（`domain/data.js` 发布）；Session 列表经 `domain/sessions.js`。`store.data` 变化、bus 的 `sessions` 都重绘；每次数据刷新后重拉最近动态；bus 的 `ledger:tz`（设置里改 Ledger 时区，`app.js` 发）只重新投影时间。
- **渲染**：`morph(root, view(env))`，每块带 `data-key`；根节点 `.dsh[data-dash-ready]` 是 E2E 的就绪标记。模板不写 `style=`：热力格用 `data-level`，进度与科目条用原生 `<progress>`（`ui/progress`）。
- **字号**只用六档：display 40（今天的数字，全站唯一）、xl 20（概览与指标数字）、lg 16（卡片标题）、md 14（正文）、sm 13（按钮、说明）、xs 12（元信息、标签）。可点目标桌面 ≥28、手机 ≥40。

| 块 | 数据 | 说明 |
|---|---|---|
| 今天 `.dsh-today` | 快照 `items` / `daily_trend` + 未结束 Session | `state.todaySummary()`：待复习 = 未停用、未击杀、逾期或今日到期；分项标签（逾期 / 今日到期 / 未录反馈 / 没有到期的题）；今天已练对比 `plan.todayTarget()`（到期 + 至多 3 道顽固题，封顶 20）；一句提示；主按钮「开始复习」或「随便练几题」，次按钮「只看逾期 N 题」或「去录反馈」。数字按状态着色（逾期红、清空绿）。空库显示「题库还是空的」与「去录入题目」；首次加载失败（没有快照）时这里显示原因与「重新加载」 |
| 行动推荐 `.dsh-plan` | 同上 | `plan.buildPlan()`，规则见下节；默认显示前 4 条，「还有 N 条建议」展开、「收起」收回。图标是 `ui/icon` 的 SVG，图标圈与指标数字按级别着色 |
| 概览 `.dsh-kpis` | 快照 `total` / `killed` / `attacking` / `avg_mastery` / `suspended` | 五格（击杀率、「不参与复习」为附注）；末尾「重新扫描」（`data-action="app.scan"`，见 `AI/frontend/shell.md`）。窄屏 3 列，手机 2 列 |
| 近 30 天活动 | 快照 `recent_activity` | `state.heatmap()`：两行各 15 格，末格是今天；级别 0–4 按当天次数占峰值比例；上方是总复习、活跃天数、单日峰值，下方首尾日期与图例。格子的 `title` 给日期与次数 |
| 最薄弱的科目 | 快照 `items` | `state.weakSubjects()`：未停用题按科目求衰减后熟练度均值，题量 ≥5 才纳入，升序取 6 个；每行是按钮，点了跳题库并按该科目、熟练度升序筛选 |
| 最近动态 | `/api/history?limit=40` | `domain/history.js` 取数与投影：去掉修正类与已撤销节点，按 seq 倒序取 4 条；标题、撤销判定仍转调旧 `history.js`（历史记录页迁移时搬进 domain）。超过 300ms 才显示骨架；失败显示原因与「重试」；「完整时间线」切到历史记录 |

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

## 目录页（`assets/catalog.js`）

Tab `目录`（侧栏图标 `#i-tree`，位于「题目库」与「复习调度」之间）；面板 `#panel-catalog`；`switchTab('catalog')` 触发 `loadCatalog()`。后端见 `omrs/catalog.py` 与 `api.md` 的 `GET /api/tree`。

### 数据来源与叠加

两份数据在前端合并，职责分开：

- **结构**来自 `GET /api/tree`——磁盘上真实的文件夹与文件，包括非题目文件。首次加载后缓存在 `CATALOG_TREE`，「🔄 重新读取」走 `loadCatalog(true)` 强制重取。
- **学习状态**来自本地 `DATA.items`，由 `catalogBuildStats()` 按 `item.path` 的路径前缀逐层累加到每个文件夹上（题量、已击杀、待复习、顽固题、衰减熟练度之和）。`/api/tree` 里没有这些字段，不要去后端加——它是只读扫盘接口，加上就得跟着投影一起维护。
- **降级**：`/api/tree` 请求失败时 `catalogFallbackTree()` 按 `DATA.items` 的 `File_Path` 拼一棵树，此时只有题目文件、没有尺寸，状态栏会说明「后端未响应」。

### 渲染

`renderCatalog()` 递归输出扁平的 `.tree-row` 序列，靠 CSS 自定义属性 `--depth` 控制缩进（`padding-left: calc(12px + var(--depth) * 18px)`），不是嵌套 DOM——所以整棵树是一次 `innerHTML` 赋值，展开/折叠也是整树重绘。

- 展开状态存在 `CATALOG_OPEN`（Set of path）。首次加载默认展开根 + 第一层；`catalogExpandAll()` / `catalogCollapseAll()` 批量切换。
- 每行都是「名称 → chip 区 `.tree-badges` → 右侧栅格 `.tree-right`」。右侧栅格固定三格（进度条 72px / 数值 52px / 操作 22px），文件夹行与题目行共用，两级行的进度条和百分比因此是对齐的；某一格没内容就留空（进度条位置用 `.tree-bar-slot` 占位）。
- 文件夹行：chip 区放题量、待复习（`.tree-badge.due`）、顽固题（`.tree-badge.leech`）；栅格放该目录平均衰减熟练度条（复用 `.m-bar`）、百分比、复制相对路径按钮。
- 题目文件行：chip 区放逾期 / 今日到期（`.tree-due.overdue` / `.tree-due.today`），未进投影的显示「未入库」；栅格放熟练度条与百分比，非题目文件放文件大小。点击调 `catalogOpenQuestion(uid)` → `viewQ(uid)` 开题目 Modal（该题在 `DATA.items` 里才可点）。
- 搜索框 `catalogSearch()` 写 `CATALOG_QUERY`（小写）。`catalogMatches()` 递归判断「自己或任一后代命中」，命中期间**所有节点视为展开**（`open` 判定里 `|| !!CATALOG_QUERY`），不改动 `CATALOG_OPEN`，清空搜索后回到原来的展开状态。
- 「显示图片等其他文件」复选框切 `CATALOG_SHOW_ALL_FILES`，关闭时只列 `kind === 'question'` 的文件。
- 顶部 `#catalog-stat` 四张 stat 卡：文件夹数 / 题目文件 / 全部文件 / 占用；`#catalog-status` 汇报降级、孤立文件、层级截断和当前筛选词。
- `reloadData()` 里若目录页正处于激活状态且 `CATALOG_TREE` 已有，会重画一次——录题或提交反馈后目录上的熟练度条随之更新，但**不会重新扫盘**（结构变化仍需点「重新读取」；有题目文件没进题库时点目录工具栏的「重新扫描」）。

样式在 `styles.css` 的 `.catalog-bar` / `.tree-*` 段。≤720px 缩小缩进步长、收窄右侧栅格，并只隐藏文件夹行的 chip（题目行的到期 chip 仍显示）。

`today` / `overdue` / `new` 这类词在本页是 chip 的状态修饰类，任何组件都不能拿它们当根类；未加限定的 `.m-bar` 规则也不得声明伸缩属性（`flex` / `flex-*` / `gap`），窄容器里靠限定后的规则单独覆盖。
