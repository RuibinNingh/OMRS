# 2026-09-25 前端重构 P6：统计数据所有权反转到 domain/data.js；仪表盘迁到 features/dashboard

---

## 执行者与模式

- 执行者：Claude（claude.ai 沙箱，等同 CCW），**受限模式**：源码来自 P5 第 4 轮交付的完整包 `OMRS-v1.24.2-p5r4-2026-09-25.zip`，无网络、无 systemd、碰不到生产与 Git 远端。
- 基线：解压后 `git init` 提交 `de25a6e`（v1.24.2）。环境探测：Python 3.12.3、Node 22.22.2、git 2.43.0、Chromium 141、出网 403、1 核 4GB，与 `AI/environment.md` 一致。
- 本轮跨三次会话：第一次只完成调查与轮次登记（工具预算用完，交付物只有 `WIP-p6r1.patch`）；第二次写完主体（WIP 补丁持续更新）；第三次跑门禁、补文档、交付。每次会话开头都先把 WIP 补丁写进下载目录。
- 后端零改动，接口与数据格式不变。版本 v1.24.2 → **v1.25.0**。

## 本轮范围（P6 第 1 轮）

按用户可见度排轮次（登记在 `AI/plans/frontend-rearch/progress.md` §9）：第 1 轮 `DATA` 加载与快照所有权、详情缓存、仪表盘（D8）。`SESSIONS` 的加载与复习调度的计划列表绑在一起（`refreshSessions` 同时驱动计划列表的加载态），移到第 2 轮随复习调度页一起反转；筛选语义 `filterItems` 仍在旧 `core.js`（两个 node 旧测试直接在沙箱里调它），随调度与导出迁移。

## 行为变化

1. **统计数据所有权**（`assets/app/domain/data.js`）：拉 `/api/stats`、持有快照、写旧 `DATA` 镜像、跑旧刷新链、经 bus 发 `data`。旧 `DATA`、`store.data`、`currentData()` 是同一个对象。
2. **并发合并**：进行中再调用只排一次补拉，后来的调用共享它。原来每次调用各发一次请求，先发后到时旧数据会覆盖新数据。
3. **失败保留旧快照**：原来 `/api/stats` 失败时换成 `core.js` 的 `demo()`（6 道假题），服务重启的几秒里首页会闪出假数字；`demo()` 已删。首次加载就失败时，仪表盘在「今天」的位置显示原因与「重新加载」。
4. **详情缓存**归 `domain/question/mount.js`；`QUESTION_CACHE` / `QUESTION_PENDING` 是过渡桥挂的只读全局（board.js、export.js 读）。
5. **仪表盘**（`features/dashboard/`）：
   - D8：「今天」放进独立卡片，数字按状态着色；「开始复习」是卡片里的普通按钮，不再是紧贴行动推荐的通栏黑条；各块之间统一 16px。
   - 行动推荐：规则与文案原样，跳转从闭包改成描述对象；字符图标换 SVG；图标圈与指标数字按级别着色（可选、状态良好的数字用次文字色）。
   - 近 30 天：两行各 15 格，不再在格子里写日期（首尾标日期，悬停看次数）。最薄弱科目的条换原生 `<progress>`。
   - 最近动态：自己拉 `/api/history?limit=40`（原来优先读历史页已加载的 240 条），投影规则不变；超过 300ms 才出骨架，失败给原因与重试，空时给空状态。
   - 跳题库：切页后发 bus `questions:preset`，题库页挂载期间监听它（先清空条件再套用）。
6. **数据复盘页**：「每日练习趋势」「标记分布」两张图的函数搬进 `data.js`（`renderDataCharts()`），标记分布的条改用原生 `<progress>`。

## 影响文件

- 新增：`assets/app/features/dashboard/`（`index.js` 110、`plan.js` 154、`state.js` 99、`view.js` 121、`dashboard.css` 116 行）、`assets/app/domain/history.js`、`assets/app/domain/schedule.js`、`tests/app/dashboard.test.mjs`、`tests/app/data.test.mjs`、`tests/e2e/dashboard.py`、本日志。
- 重写：`assets/app/domain/data.js`。
- 删除：`assets/dashboard.js`、`assets/actions.js`；`styles.css` 净删 223 行。
- 修改：`assets/app.js`（`reloadData` → `legacyDataRefresh`，`init()` 不再调 `renderActionPlan`，改时区发 `ledger:tz`）、`assets/core.js`（删 `demo()` 与两个缓存 `let`）、`assets/schedule.js`（删一行 `renderActionPlan`）、`assets/data.js`、`assets/app/legacy-bridge.js`（`installDataBridge`）、`assets/app/main.js`、`legacy-pages.js`、`shell.js`、`core/bus.js`（注释）、`domain/question/mount.js`、`domain/question/index.js`、`features/questions/index.js`（`questions:preset`）、`styles/index.css`、`omrs_dashboard.html`（仪表盘面板只留空容器，删两个 `<script>`，版本串）。
- 测试调整：`tests/smoke_frontend_actions_catalog.js` 场景 1–3 与 `tests/test_question_suspend_frontend.js` 的行动计划断言迁入 `tests/app/dashboard.test.mjs`（用例只增不减）；`tests/e2e/shell_router.py` 就绪标记改 `[data-dash-ready]`、「完整时间线」改点 `data-action`；`questions.py` / `instant.py` 的旧入口改调过渡桥的 `questionsLoadPreset` / `instLoadPractice`。
- 文档：`AI/frontend/dashboard.md`（仪表盘部分重写）、`AI/frontend/architecture.md`、`AI/frontend/components.md`、`AGENTS.md`（映射表加 `features/dashboard/`）、`AI/changelog.md`、`README.md` / `AI/README.md`（版本）、`AI/plans/frontend-rearch/progress.md`。

## 验证（全部为本轮实际运行结果）

| 门禁 | 结果 |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 156 OK（第一次全量 1 个失败：`test_ui_gates` 调 `check_ui.py`，当时 `AGENTS.md` 还没登记 `features/dashboard/`；登记后重跑 156 OK）|
| `node --test tests/*.js tests/app/*.test.mjs` | 210 / 210（原 197：+9 dashboard、+4 data）|
| `python3 tests/app/run_browser.py` | 34 / 34 |
| `python3 tests/e2e/shell_router.py` | 20 / 20（第一次停在旧选择器 `.recent-head .btn`，改后重跑）|
| `python3 tests/e2e/ui_bridge.py` | 15 / 15 |
| `python3 tests/e2e/dashboard.py`（新增）| 26 / 26 |
| `python3 tests/e2e/instant.py` | 23 / 23 |
| `python3 tests/e2e/feedback.py` | 31 / 31 |
| `python3 tests/e2e/questions.py` | 92 / 92 |
| `python3 tests/check_ui.py` | 0 处问题；存量 handlers 215→205、html_assign 141→122、inline_style 195→185、color_literals 160→118、font_size_literals 307→280（已 `--update-baseline`）|
| `python3 tests/check_contrast.py` | 58 组，0 不达标 |
| `python3 tests/check_docs.py --diff de25a6e` | 见交付说明 |

**运行时审计（`tests/visual/run.py --ref de25a6e`）**：仪表盘字号 16 → 5 种、最小字号 9 → 12px、小于 28px 的可点目标 4 → 0、行内样式 8 → 0（桌面 / 手机 × 浅 / 深相同）。数据复盘行内样式 180 → 177。页面脚本错误：无。

**截图差异（28 / 48 有差异，逐项解释）**：
- 仪表盘 8 张（24–34%）：本轮重做，见上。
- 数据复盘：桌面约 0.3%、手机 8–11%。标记分布的条从带描边的渐变条（8px）换成 `ui-progress`（6px），卡片矮约 12px；手机单栏时下面整页随之上移，所以差异比例大，其余内容不变。
- 其余 16 张桌面图 0.001–0.005%：侧栏底部版本号 v1.24.2 → v1.25.0。手机图侧栏收起，无差异。

**过程中发现并纠正**：删旧 CSS 的脚本用了跨注释的懒惰匹配（`/\*.*?\*/` 在 fullmatch 下会越过规则连到后面的注释），把一个仍在用的 `@media(min-width:1161px)` 工作台块误判为「只含注释」删掉了；对照 `git diff` 发现后从提交还原，改成不跨 `*/` 的写法重删，并逐条核对被删的 4 个 `@media` 块（900px 为 P3 遗留的纯注释块，720 / 1000 / 560px 只含旧仪表盘规则）。dashboard E2E 最终数字是修正后重跑的结果。

## 未执行

- Safari / Firefox 未测；`tests/smoke_schedule_workbench.py` 未跑（基线即失败，属第 2 轮复习调度页）。
- 生产部署、`--write-log-index`：受限模式不做，见 UPGRADE 交接清单。

## 下一步

P6 第 2 轮：复习调度（`SESSIONS` 所有权、`smoke_schedule_workbench.py` 余下失败）、数据复盘、历史记录（`domain/history.js` 的转调换成真实现）。详见 `AI/plans/frontend-rearch/progress.md`。

---

## 第 2 轮：数据复盘迁到 features/data（v1.25.1）

- 执行者与模式同上；开工基线是第 1 轮交付后的提交（标签 `p6r1`，与 `OMRS-v1.25.0-p6r1-2026-09-25.zip` 一致）。开工先写 WIP 补丁到下载目录。
- 范围按 `progress.md` §9 再拆：第 2 轮只做数据复盘（只读页、旧行内样式最多、不涉及写操作，一次会话能收口）；复习调度、历史记录顺延到第 3 轮。

### 行为变化

1. 数据复盘页由 `assets/app/features/data/` 渲染：八格概览一张卡；20 张图表卡自动成两栏，四张宽内容整行；标题去掉 emoji；表格是 `ui/table`（手机降级为卡片，原来横向截断）；横条是原生 `<progress>`；颜色经 `data-tone` 走状态 token；三张 SVG（趋势、雷达、气泡）几何原样，颜色与字号搬进 CSS。统计口径、分档配色、区块顺序、表格列不变。
2. 数据更新时机：进入页面、点「刷新」、统计快照变化（写操作后的 `reloadData()`）都重拉 `/api/analytics`；原来只在进入和刷新时拉。首次失败显示原因与「重试」；已有数据时刷新失败保留旧数据、只在页首报错。
3. 导出经 `core/download.js`（新）：文件名取 `Content-Disposition`，缺省 `OMRS-复盘-日期.md`（原缺省名是 `.html`，服务端实际给的是 `.md`）；成功弹 toast，失败原因写在页首 `#data-status`。
4. 旧数据刷新链 `legacyDataRefresh()` 不再画数据复盘的两张图，页面自己订阅统计快照。

### 影响文件

- 新增：`assets/app/features/data/`（`index.js` 99、`state.js` 116、`charts.js` 71、`view.js` 116、`data.css` 101 行）、`assets/app/core/download.js`、`tests/app/analytics.test.mjs`、`tests/e2e/data.py`。
- 删除：`assets/data.js`；`styles.css` 净删 74 行（趋势、标记分布、横条、热力格、气泡图例、`stat-sub`、`tbl-wrap`、`sched-controls` 等只服务旧数据页的规则，以及它们留下的 4 条孤立注释；删后孤立注释集合与基线一致）。
- 修改：`omrs_dashboard.html`（数据复盘面板只留空容器，删 `<script src="assets/data.js">`，版本串）、`assets/app.js`（刷新链去掉 `renderDataCharts`）、`assets/app/main.js`、`legacy-pages.js`、`legacy-bridge.js`（注释）、`styles/index.css`、`tests/ui_baseline.json`。
- 文档：`AI/frontend/records.md`（数据页一节重写）、`AI/frontend/architecture.md`（`core/download.js`、旧页面登记表）、`AI/frontend/design-system.md`、`AI/frontend/dashboard.md`、`AGENTS.md`（映射表加 `features/data/`）、`AI/changelog.md`、版本号四处、`progress.md`。

### 验证（本轮实际运行）

| 门禁 | 结果 |
|---|---|
| unittest | 156 OK |
| node | 215 / 215（+5 analytics）|
| 浏览器单测 | 34 / 34 |
| shell_router / ui_bridge | 20 / 15 |
| dashboard / data（新增）| 26 / 21 |
| instant / feedback / questions | 23 / 31 / 92 |
| check_ui | 0 处问题；存量 handlers 205→201、html_assign 122→104、inline_style 185→143、color_literals 118→106、font_size_literals 280→264 |
| check_contrast | 58 组，0 不达标 |

- `tests/e2e/data.py` 第一次 19 / 21：①导出的文件实际是 `.md`（测试写成了 `.html`，页面缺省名同样写错），改正；②页首状态行是 `<p>`，里面嵌 `ui/status` 的 `<p>` 被解析器拆开，导出失败原因落到了 `#data-status` 外面，改成 `<div>`。重跑 21 / 21。
- 门禁启动后又改了文档、版本号与 `legacy-bridge.js` 一行注释；代码与样式在门禁期间未变。
- 第一次截图对比的审计指出两处，E2E 当时没拦住：①标记芯片沿用旧 `.lbl` 的 9.6px（E2E 只查了字号种数，没查最小值）——本页加 `.dat .lbl { font-size: var(--text-xs) }`（先例：即时练习的 `.inst .lbl`），E2E 审计补上「最小字号 ≥12px」；②手机上 6 个元素被判为可见溢出，是 `ui/table` 叠卡模式里只给读屏用的表头行（1px 裁剪容器里的 `tr` 带内边距）——`ui/table.css` 给它去掉内边距并设 `overflow: hidden`，属审计误报，页面本身不横向滚动。修后重跑 data E2E 与截图对比，数字见下。

**截图对比（`tests/visual/run.py --ref p6r1`，修正后重跑）**：26 / 48 有差异。数据复盘 4 张（桌面 17–20%、手机 37–39%）是本轮重做；其余 22 张桌面图约 0.003% 是侧栏版本号 v1.25.0 → v1.25.1；手机图侧栏收起，除数据复盘外无差异。页面脚本错误：无。运行时审计：数据复盘字号 14 → 3 种（该脚本只数 HTML 文字，不含 SVG 内文字）、最小字号 8.7 → 12px、行内样式 177 → 0、手机可见溢出 1 → 0、小于 28px 的可点目标 0 → 0。

修正后重跑：data 21 / 21、questions 92 / 92、浏览器单测 34 / 34；`check_ui`、`check_contrast`、`check_docs --diff p6r1` 均通过。

### 未执行

- Safari / Firefox 未测；`smoke_schedule_workbench.py` 未跑（基线即失败，属第 3 轮）；生产部署与 `--write-log-index` 按受限模式不做。

---

## 第 3 轮：复习调度迁到 features/schedule，Session 列表归 domain/sessions（v1.25.2）

- 开工基线：第 2 轮交付后的提交（标签 `p6r2`，与 `OMRS-v1.25.1-p6r2-2026-09-25.zip` 一致）；开工先写 WIP 补丁。
- 范围按 §9 再拆：复习调度一页（连同推荐、导出三个旧脚本约 40KB）是 P6 最大的一页。本轮做页面外壳、标签栏、「已有计划」与 `SESSIONS` 所有权；「安排复习」「全题库导出」保持旧 DOM，挂在页面挂载点里由页面切显隐，下一轮迁。历史记录顺延到第 4 轮。

### 行为变化

1. 复习调度是 features 页面：`#panel-schedule` 里新增 `#sch-app`（标签栏 + 「已有计划」），旧 `#recommend-panel-v2`、`#export-panel` 是它的兄弟节点。导出面板从 `style="display:none"` 改为 `hidden`；「返回」按钮改为 `schShow('back')`。
2. 「已有计划」原生实现（筛选、搜索、列表、详情、删除、导出、录入结果、预览），行为与原来一致；另外：打印选项的展开状态与勾选重绘后保留；刷新列表时详情保留内容；被删的计划不会被随后的刷新重新打开；手机上列表与详情分两屏。
3. `domain/sessions.js` 成为 Session 列表所有者（`refreshSessions` 只认最新、失败保留、删除作废进行中的旧加载；bus 发 `sessions`）；旧 `SESSIONS` 是镜像。`sessionProgress` / `sessionUniqueUids` 从反馈页 state 搬进 domain，反馈页原名再导出；反馈页刷新计划改读返回值（新实现不抛出）。
4. 从别的工作区切回「安排复习」时重拉推荐。原来只重绘旧数据，而 P1 起点侧栏当前页不再重新进入，冒烟测试因此一直停在「空推荐提示查看已有计划」。
5. `recommend_v2.js` 删掉生成计划后直接写旧计划筛选 DOM 的两行（改由 `schOpenPlan` 的页面事件复位筛选）。

### 影响文件

- 新增：`assets/app/features/schedule/`（`index.js` 160、`state.js` 66、`view.js` 79、`schedule.css` 70 行）、`tests/app/schedule.test.mjs`、`tests/e2e/schedule.py`。
- 重写：`assets/app/domain/sessions.js`、`assets/app/domain/schedule.js`；`assets/schedule.js` 从 184 行缩到 10 行（只剩录入题目、全局扫描与 `feedbackSession` / `refreshFbSessionPicker` 两个旧入口）。
- 删除：`tests/test_schedule_sessions.js`（4 个用例：列表后发先至、详情后发先至、删除确认去重与取消、删除业务错误——前后两个进 node 单测，中间两个进 E2E）；`styles.css` 34 条只服务旧标签栏与计划列表的规则（孤立注释集合与基线一致）。
- 修改：`omrs_dashboard.html`、`assets/recommend_v2.js`、`assets/app/legacy-bridge.js`（`installScheduleBridge`）、`legacy-pages.js`、`main.js`、`styles/index.css`、`features/feedback/state.js` 与 `index.js`、`tests/smoke_schedule_workbench.py`（`.sch-plan` → `.schd-plan`）、`tests/ui_baseline.json`。
- 文档：`AI/frontend/review.md`（复习调度一节重写）、`architecture.md`、`components.md`、`feedback.md`、`design-system.md`、`AGENTS.md`（映射表加 `features/schedule/`）、`AI/changelog.md`、版本号四处、`progress.md`。

### 验证与过程

- `tests/e2e/schedule.py` 第一次 16 / 23：①「后开的详情不被旧响应覆盖」是测试写错——两个 Session 编号一个是另一个的前缀（`EXP-…` 与 `EXP-…-A`），按子串判断必然失败，改为读详情里的 `data-sid`；②刷新 Session 列表时页面会重拉当前详情，原实现先清空再拉，打印选项被收起、勾选丢失——改为同一计划重拉时保留内容，`<details>` 的展开状态存进页面状态（点 summary 时阻止默认切换，由状态驱动）；③「打印选项」的 summary 只有 17px 高——加到控件高度；④删除成功后详情仍显示已删计划——删除成功立即清空选中并重绘，列表刷新时选中项不在列表里就清掉；测试也改为等删除后的刷新链结束再做下一步。第二次 23 / 25，第三次 25 / 25。
- 审计中字号出现 15px：这个实例是紧凑密度（`--text-lg` 为 15px），是 token 值，不是写死的字号。

### 门禁（第 3 轮，最终代码上实际运行）

| 门禁 | 结果 |
|---|---|
| unittest | 156 OK |
| node | 216 / 216（删 `test_schedule_sessions.js` 4 个、加 `schedule.test.mjs` 5 个）|
| 浏览器单测 | 34 / 34 |
| shell_router / ui_bridge | 20 / 15 |
| dashboard / data / schedule（新增）| 26 / 21 / 25 |
| instant / feedback / questions | 23 / 31 / 92 |
| check_ui | 0 处问题；存量 handlers 201→184、html_assign 104→98、inline_style 143→142、font_size_literals 264→256 |
| check_contrast / check_docs | 58 组 0 不达标 / 0 处问题 |

- 第一次全量里 instant 是 22 / 23（「标记筛选」，progress 登记过的偶发项），单独重跑 23 / 23。
- feedback 第一次 27 / 28：「旧入口」一段还在点旧计划按钮 `.sch-plan`，改成按 `data-arg` 点 `.schd-plan`、等详情加载后再点「录入结果」，重跑 31 / 31。这一段因为中途出错少跑了 3 项，所以第一次合计不是 31。
- `tests/smoke_schedule_workbench.py` 仍失败在第 79 行（「安排复习」画廊题面预览），开工基线相同，属第 4 轮。

**截图对比（`tests/visual/run.py --ref p6r2`）**：24 / 48 有差异。复习调度 4 张（桌面约 8%、手机 14–15%）：顶部换成新标签栏（「全题库导出」改为次要按钮、标签高 40px），下面的「安排复习」随之上移，内容不变；其余 20 张桌面图约 0.002% 是侧栏版本号 v1.25.1 → v1.25.2。页面脚本错误：无。该脚本审计的是页面默认工作区「安排复习」（仍是旧 DOM），所以复习调度的字号种数 10 → 9、小目标 41、行内样式 44 基本不变，下一轮迁「安排复习」时才会降；本轮原生的「已有计划」由 `tests/e2e/schedule.py` 的审计覆盖（字号 ≤6 且 ≥12px、可点目标桌面 ≥28 / 手机 ≥40、无行内样式与溢出，浅 / 深 × 桌面 / 手机全过）。

### 未执行

- Safari / Firefox 未测；生产部署与 `--write-log-index` 按受限模式不做。

---

## 第 4 轮：「安排复习」迁进复习调度页（v1.25.3）

- 开工基线：第 3 轮交付后的提交（标签 `p6r3`，与 `OMRS-v1.25.2-p6r3-2026-09-25.zip` 一致）；开工先写 WIP 补丁。本轮只做「安排复习」；「全题库导出」、历史记录、目录顺延（§9）。

### 行为变化

1. 「安排复习」由 `features/schedule/` 原生渲染：`arrange.js`（筛选、排序、轮选、选择、提示文案的纯函数）、`arrange-ctl.js`（拉推荐只认最新、选择、生成计划、画廊懒加载）、`arrange-view.js`（模板，保留 `#recommend-panel-v2`、`#rec-*` 旧 id）。规则与文案原样；标记筛选按钮改为 `data-action="schedule.label"`（不再挂旧 labels.js 的 `data-label-filter` 委托）。
2. 画廊题面恢复显示：旧推荐画廊用的 `QV_CARD_OPTS` 在 P5 之后不是全局（过渡桥没挂），`qvRender` 一直没执行成功，题面停在「正在加载题面…」——这就是冒烟测试第 79 行的失败原因。新实现从 `domain/question` 取；挂载点 `data-morph="skip"`，用 WeakSet 记已挂的节点（不写属性，morph 会同步挂载点自身属性）。
3. 手机列表每行两行（勾选与题目 / 理由、熟练度与「预览」），UID 只是文字（「预览」按钮负责打开），行高回到旧版以内（冒烟测试断言 <140px）；分段切换 28 / 40 高。
4. 删除调度后详情区显示「调度已删除」；列表刷新时选中项消失也按已删除处理。
5. `tests/smoke_schedule_workbench.py` 全部通过：选择器改到新标记（`.schd-cand`、`.schd-cand__preview`、`[data-preview-uid]`、`[data-action="schedule.label"]`、按钮名去掉旧箭头）；删除流程里每次点完确认框按钮后等 `dialog[open]` 消失再继续——ui/dialog 有标题栏关闭与「取消」两个 `data-dialog-cancel`，退场动画期间旧确认框的「删除调度」也还在无障碍树里。

### 影响文件

- 新增：`assets/app/features/schedule/arrange.js`、`arrange-ctl.js`、`arrange-view.js`、`tests/app/arrange.test.mjs`（原 `test_recommend_v2_filters.js` 的用例全部迁入，另加提示文案、复燃标识、chip、视图偏好）。
- 删除：`assets/recommend_v2.js`、`tests/test_recommend_v2_filters.js`；`questions.js` 的 `reviveChipHtml`；`app.js` 刷新链里的 `initRecommendV2`；`styles.css` 97 条只服务旧推荐区的类规则、4 条 `#rec-*` 规则、2 个随之变空的 `@media` 块与 1 条孤立注释（孤立注释集合与基线一致）。
- 修改：`features/schedule/index.js`、`view.js`、`state.js`、`schedule.css`；`domain/schedule.js`（只剩导出面板）；`legacy-bridge.js`；`omrs_dashboard.html`（删旧推荐区与 `<script>`）；`tests/e2e/schedule.py`（加「安排复习」一段与该工作区的审计）；`tests/smoke_schedule_workbench.py`；`tests/ui_baseline.json`。
- 文档：`AI/frontend/review.md`（安排复习、列表 / 画廊两节重写）、`shell.md`（文件树与加载顺序，顺带删掉前几轮已删脚本的残留条目）、`qview.md`、`architecture.md`、`components.md`、`design-system.md`、`AI/changelog.md`、版本号四处、`progress.md`。

### 过程

- 冒烟测试依次停在：第 168 行（手机候选行 169px，改两行布局后 148px，再把 UID 从按钮改成文字、预览挪到第二行后通过）→ 第 262 行（确认框的两个取消按钮）→ 第 265 行（退场中的确认框）→ 删除后的提示文字。逐项修完后全部通过。
- `tests/e2e/schedule.py` 加「安排复习」段后第一次 31 / 33：分段切换只有 22px 高（桌面审计），改为控件高度后 33 / 33。

### 门禁（第 4 轮，最终代码上实际运行）

| 门禁 | 结果 |
|---|---|
| unittest | 156 OK |
| node | 216 / 216（删 `test_recommend_v2_filters.js` 6 个、加 `arrange.test.mjs` 6 个）|
| 浏览器单测 | 34 / 34 |
| shell_router / ui_bridge | 20 / 15 |
| dashboard / data / schedule | 26 / 21 / 33 |
| instant / feedback / questions | 23 / 31 / 92 |
| `python3 -m unittest tests.smoke_schedule_workbench` | OK |
| check_ui | 0 处问题；存量 handlers 184→153、html_assign 98→93、color_literals 106→103、font_size_literals 256→234 |
| check_contrast / check_docs | 58 组 0 不达标 / 0 处问题 |

**截图对比（`tests/visual/run.py --ref p6r3`）**：26 / 48 有差异。复习调度 4 张（桌面约 15%、手机约 25%）是「安排复习」重做；其余 22 张桌面图约 0.003% 是侧栏版本号。页面脚本错误：无。运行时审计：复习调度字号 9 → 4 种（手机 11 → 4）、最小字号 9.6 → 12px、小于 28px 的可点目标 41 → 0。

**未解释的一项**：该脚本报告复习调度页「带行内样式的元素」前后都是 44。同一视图在两个实例上（工作实例、用 full fixture 新起的实例）用同样的判定（`.panel.active` 下可见且带 `style` 属性）实测都是 0，`tests/e2e/schedule.py` 对 `#sch-app` 的审计也是 0。差异可能来自截图脚本自身的环境（冻结 Date、遮罩、关动效的注入），本轮没有查清，留给第 5 轮：先在 `run.py` 里打印这 44 个元素的选择器。

### 未执行

- Safari / Firefox 未测；生产部署与 `--write-log-index` 按受限模式不做。

---

## 第 5 轮：「全题库导出」迁进复习调度页（v1.25.4）

- 开工基线：第 4 轮交付后的提交（标签 `p6r4`，与 `OMRS-v1.25.3-p6r4-2026-09-25.zip` 一致）；开工先写 WIP 补丁。本轮只做「全题库导出」；历史记录、目录顺延（§9）。
- 先查第 4 轮留下的「截图脚本报告复习调度 44 处行内样式」：按截图脚本的顺序（仪表盘 → 数据复盘 → 题库 → 展示板 → 目录 → 复习调度）逐页切过去，再用同样判定数，仍是 0。本轮没能复现，也没改截图脚本；本轮删掉了旧导出面板（44 处行内样式最可能的来源：它的每行都带 `style=`），截图对比的新数字见下。

### 行为变化

1. 「全题库导出」由 `features/schedule/` 原生渲染：`exporter.js`（筛选、已选、请求体的纯函数）、`exporter-ctl.js`（画廊懒加载、A4 单双栏确认、导出）、`exporter-view.js`（模板，保留旧 id）。复习调度三个工作区至此都是原生的，`#sch-app` 之外没有旧 DOM。
2. 导出请求统一由 `domain/exporting.js` 发出、`core/download.js` 下载；「已有计划」的导出也改走它，结果写进详情（原来由旧 export.js 往 `#sch-status` 里写 HTML，需要 `data-morph="skip"`，现已去掉）。
3. 屏幕版时「附带答案」勾选且禁用、留白禁用（原来可勾但服务端按屏幕版一律附带答案）；已选区限高内部滚动。
4. 仪表盘「开始复习」改为切页后发 `schedule:view`；`domain/schedule.js` 删除。

### 影响文件

- 新增：`assets/app/features/schedule/exporter.js`、`exporter-ctl.js`、`exporter-view.js`、`assets/app/domain/exporting.js`、`tests/app/exporter.test.mjs`。
- 删除：`assets/export.js`、`assets/app/domain/schedule.js`；`core.js` 两个 `let`；`app.js` 刷新链两项；过渡桥 `schShow`、`showRecommendPanel`；`styles.css` 22 条规则与 3 条孤立注释。
- 修改：`features/schedule/index.js`、`view.js`、`state.js`、`schedule.css`；`features/dashboard/index.js`；`legacy-bridge.js`（`renderExportPicker`、`downloadExportResponse` 转新实现）；`omrs_dashboard.html`（删旧导出面板与 `<script>`）；`tests/e2e/schedule.py`（加「全题库导出」段与审计）；`tests/smoke_schedule_workbench.py`（返回按钮名）；`tests/ui_baseline.json`。
- 文档：`AI/frontend/review.md`（新增「全题库导出」一节，改入口与已有计划的导出说明）、`AI/export.md`、`architecture.md`、`components.md`、`dashboard.md`、`settings.md`、`shell.md`、`AI/optimization.md`、`AI/changelog.md`、版本号四处、`progress.md`。

### 过程

- 画廊式题面第一次截图时没等到：已选区很长时画廊在视口下方，懒加载按设计不挂——截图脚本改为先滚到画廊；顺带给已选区限高。
- `tests/e2e/schedule.py` 45 / 45（新增导出段 9 项与「全题库导出」审计 4 项），冒烟测试仍全过。

### 门禁（第 5 轮，最终代码上实际运行）

| 门禁 | 结果 |
|---|---|
| unittest | 156 OK |
| node | 220 / 220（+4 exporter）|
| 浏览器单测 | 34 / 34 |
| shell_router / ui_bridge | 20 / 15 |
| dashboard / data / schedule | 26 / 21 / 45 |
| instant / feedback / questions | 23 / 31 / 92 |
| `python3 -m unittest tests.smoke_schedule_workbench` | OK |
| check_ui | 0 处问题；存量 handlers 153→127、html_assign 93→84、inline_style 142→126、font_size_literals 234→227 |
| check_contrast / check_docs | 58 组 0 不达标 / 0 处问题 |

**截图对比（`tests/visual/run.py --ref p6r4`）**：24 / 48 有差异，全部是桌面图约 0.003% 的侧栏版本号 v1.25.3 → v1.25.4。截图脚本只拍各页默认视图，复习调度默认是「安排复习」（本轮未改），「全题库导出」的前后对照见截图包里的手工截图。页面脚本错误：无。

**「44 处行内样式」仍未解决**：旧导出面板删掉之后，截图脚本对复习调度的计数仍是 44（前后都是），可见它不来自导出面板；在实例上逐页切换复现两次都是 0，E2E 对 `#sch-app` 的审计也是 0。差异在截图脚本的运行环境里（冻结 Date、关动效样式、全页截图时临时改视口高度等），第 6 轮在 `run.py` 里打印这些元素定位。

---

## 本机接手（2026-09-26）

### 阶段 0 实测与隔离

- 开工目录 `/root/workspace/apps/OMRS`，分支 `main`，HEAD `4fd4827`；`git status --short --untracked-files=all` 有 305 条状态，`git stash list` 为空。版本文件为 v1.25.4，已删旧文件均不存在，`AI/logs/log.md` 存在。
- `omrs.service` 为 active，主进程 PID 1936793；`WorkingDirectory=/root/workspace/apps/OMRS`，`ExecStart` 使用该目录的 `omrs_engine.py` 和 8471 端口。`/api/status` 返回 v1.25.4、215 题、启动时间 `2026-09-26T02:29:31.268397+00:00`。这与交接说明记录的 v1.19.1 不同，以本次实测为准。
- 属于执行说明阶段 0 的情况 A。用连接本机 CDP 的真实 Chromium 只读打开生产的 12 个页面，均有一个活动面板、标题正确，页面脚本错误为 0。基线提交之后，生产目录不再编辑；开发区是 `/root/.codex/worktrees/frontend-rearch/OMRS`。
- 在 `rearch/base-v1.25.4` 建立快照提交 `7ebfc6c`：纳入 300 个项目文件，包含此前未提交的本机改动、P6 第 5 轮及以前补丁合并结果、规划说明。未纳入的 5 个 `.playwright-mcp/` 临时文件留在原目录。快照内两份既有历史日志含 Markdown 行尾空格；未改写历史事实。

### 阶段 0 门禁

在生产目录只运行只读检查与隔离实例测试；在开发 worktree 又独立复跑一遍。两处结果一致。所有测试实例启动时去掉 `OMRS_SYSTEMD_SERVICE`，浏览器测试使用本机 `OMRS_TEST_CDP_URL=http://127.0.0.1:9222`，只关闭自己创建的 context。

| 验证 | 两处实际结果 |
|---|---|
| Python unittest / Node | 159 通过 / 220 通过 |
| 浏览器单测 | 34 通过 |
| shell_router / ui_bridge | 20 / 15 通过 |
| instant / feedback / questions | 23 / 31 / 92 通过 |
| dashboard / data / schedule | 26 / 21 / 45 通过 |
| `tests.smoke_schedule_workbench` | 1 通过 |
| `check_ui` / `check_contrast` | 0 处问题；58 组对比度均达标 |
| `check_docs --diff HEAD`（未修改开发 worktree 时） | 0 处问题，2 条篇幅提醒 |

`check_docs` 比进度原记的多一条提醒：除 `AI/api.md` 外，新的执行说明为 48KB。开发 worktree 补记本节与进度时，曾在写日志及生成索引前运行 `check_docs --diff HEAD`，该次报告 2 处文档同步问题；运行 `--write-log-index` 后重跑为 0 处问题、2 条篇幅提醒。生成索引同时移除了一条指向不存在的 2026-08-16 日志的旧条目。
