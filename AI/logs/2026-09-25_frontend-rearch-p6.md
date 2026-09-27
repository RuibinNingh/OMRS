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

### 阶段 2.1：截图审计修正

`tests/visual/run.py` 的审计现在只统计非空 `style` 属性，字号与行内样式都排除 KaTeX 内部。`tests/test_visual_diff.py` 用真实浏览器验证空属性、空白属性、有效行内样式及 KaTeX 小字号的计数。`AI/environment.md` 与计划进度同步了审计口径。

已实际执行：`python3 -m unittest tests.test_visual_diff -v`，2 项通过；`tests/visual/run.py --audit-only --pages questions,schedule --themes light,dark --viewports desktop,mobile`，8 种组合均为 0 处行内样式、页面脚本错误为 0。题库页全页面审计另显示最小字号 9.6px，复习调度为 12px；浏览器定位到题库的旧 `.lbl` 标记芯片字号 9.6px、`ui-kbd` 11px。该旧样式属于进度 §8 登记的 P8 遗留，迁 P6 页时仍需核查相同组件。浏览器使用本机 CDP，实例使用临时 Vault 和随机端口。

全量门禁在本次改动后再次执行：Python 160 项、Node 220 项、浏览器单测 34 项；shell_router / ui_bridge 20 / 15，instant / feedback / questions 23 / 31 / 92，dashboard / data / schedule 26 / 21 / 45，`smoke_schedule_workbench` 1 项，均通过。`check_ui` 0 处问题，对比度 58 组均达标，`check_docs --diff HEAD` 0 处问题、2 条篇幅提醒。均在独立 worktree、临时 Vault、本机 CDP 模式下运行；未执行生产变更。

## 历史记录页迁移（2026-09-26，v1.25.5）

### 盘点与实现

- 原 `assets/history.js` 持有 Ledger 撤销状态、节点分类与标题、时间格式、主时间线和修正记录渲染，以及反馈、Session、状态修正操作。旧 `#panel-history` 含排序、修正模式、修正记录和时间线 DOM，专用样式在 `assets/styles.css`。仪表盘最近动态曾经通过 `domain/history.js` 转调旧全局；旧 `app.js` 初始化和题目写操作也引用历史刷新入口。
- 新 `assets/app/features/history/` 有页面契约、状态投影、模板和样式；`assets/app/domain/history-model.js` 持有纯投影，`domain/history.js` 负责读写与跨页通知。`main.js` 注册页面，旧页面登记、脚本、DOM 与专用 CSS 已删。题目写成功后通知历史页，历史修正成功后刷新题目详情缓存、统计、Session、仪表盘最近动态和历史列表。
- 历史修正只在修正模式下可用，请求期间按钮置忙；首次加载慢于 300ms 才显示骨架，失败时保留已有列表并给出原因。Ledger 时区变化后重新投影时间。
- 原历史页没有独立 Node 测试；后端 `tests/test_history_projection.py` 保持原样。新增 `tests/app/history.test.mjs` 5 项纯函数测试、`tests/e2e/history.py` 22 项，覆盖列表、排序、反馈与 Session 撤销 / 恢复、状态还原、仪表盘同步、失败恢复和四种视觉审计。
- 旧代码存量减少后用 `check_ui.py --update-baseline` 下调 `tests/ui_baseline.json`。同步 `AGENTS.md` 映射、相关前端分册、版本号、README、changelog 和本进度文件。

### 验证

已实际执行：Python unittest 160 项、Node 225 项、浏览器单测 34 项；E2E shell_router 20、ui_bridge 15、dashboard 26、data 21、schedule 45、instant 23、feedback 31、questions 92、history 22，全部通过。`check_ui.py` 0 处问题，旧存量为 handlers 115、html_assign 77、inline_style 122、color_literals 99、font_size_literals 216；`check_contrast.py` 58 组均达标；`git diff --check` 通过。浏览器测试使用本机 CDP；隔离实例使用临时 Vault、随机端口，环境中移除 `OMRS_SYSTEMD_SERVICE`。

`tests/visual/run.py --ref HEAD` 的 48 组截图有 25 组像素差异：历史页桌面浅 / 深色约 7.339% / 8.796%，手机浅 / 深色约 22.171% / 23.199%，对应旧时间线换为 token 化卡片、工具栏和修正记录新布局；其余 21 组是侧栏版本号 v1.25.4 → v1.25.5 的小范围变化。页面脚本错误为 0。历史页四种组合的运行时审计均为 2 种字号、最小 12px、0 个小目标、0 处有效行内样式、0 处横向溢出。

`python3 -m unittest tests.smoke_schedule_workbench -q` 的 1 项冒烟测试通过；`python3 tests/check_docs.py --write-log-index` 已生成索引；`python3 tests/check_docs.py --diff HEAD` 为 0 处问题、2 条篇幅提醒。

### 现状勘查

根目录 `SOURCE_EXPORT_MANIFEST.txt` 仍是 20260926T022359Z 的历史导出清单，列有已删除的 `AI/rearch-plan.md` 与 `assets/history.js`，与执行说明中的「已重新生成」不一致。该清单由源码导出命令在新导出包中生成；本页不改写旧导出的时间戳和文件清单。后续验证「导出脱敏源码包」时检查新包清单不含已删文件。

---

## 目录页迁移（2026-09-27，v1.25.6）

### 盘点与行为变化

- 原 `assets/catalog.js` 持有 `CATALOG_TREE`、`CATALOG_SUMMARY`、展开路径、搜索词、全部文件开关和文件夹统计等全局状态；`loadCatalog`、`renderCatalog` 以及 `catalog*` 函数负责请求、后备树、渲染、复制与开题。旧面板依赖 `#catalog-*`、`.tree-*`，目录专用 CSS 集中在 `assets/styles.css`。跨页入口是旧 `app.js` 的初始化、`legacy-pages.js` 的进入钩子；旧测试 `smoke_frontend_actions_catalog.js` 含目录场景。
- 新 `features/catalog/` 的 `state.js` 提供纯后备树、文件夹统计、搜索与路径投影；`index.js` 持有页面状态和请求生命周期；`view.js` 用带 key 的 `each()` 渲染目录树。默认只展开根层，搜索会展开匹配分支；题目文件通过 `domain/question` 打开，剪贴板拒绝时显示可手动复制的路径。`/api/tree` 首次失败用题目路径建后备树，刷新失败保留现有树并显示原因。
- 目录工具栏保留重新扫描；旧 `doScan()` 返回扫描是否成功，外壳仅在成功时发 `catalog:refresh` 让目录重读。扫描失败保留目录树。桌面和手机的目录行、到期标记、统计卡及工具栏改用语义 token 与统一控件尺度。
- 删除旧目录脚本、只服务旧目录的 39 行 CSS、旧目录冒烟文件；`main.js` 注册新页面，HTML 只留挂载根。旧目录测试场景迁到 `tests/app/catalog.test.mjs` 的纯函数与模板断言，以及 `tests/e2e/catalog.py` 的真实浏览器主路径。仪表盘旧 E2E 的热力格断言改为按浏览器当地日期与统计快照核对，避免跨时区当天记录为 0 时误报。

### 影响文件

`assets/app/features/catalog/`、`assets/app/main.js`、`assets/app/legacy-pages.js`、`assets/app/shell.js`、`assets/app/styles/index.css`、`assets/app.js`、`assets/schedule.js`、`omrs_dashboard.html`、`assets/styles.css`、`assets/catalog.js`、`tests/app/catalog.test.mjs`、`tests/e2e/catalog.py`、`tests/e2e/dashboard.py`、`tests/smoke_frontend_actions_catalog.js`、`tests/ui_baseline.json`；同步 `AGENTS.md`、`README.md`、`AI/README.md`、前端对应分册、`AI/optimization.md`、`AI/changelog.md`、`AI/routes.md`、`omrs/version.py`、本进度文件与日志索引。旧 CSS 删除逐段对照 `git diff`，`git diff --check` 通过。

### 验证

- 实际运行：Python unittest 160 项、Node 234 项、浏览器单测 34 项；E2E shell_router 20、ui_bridge 15、dashboard 26、data 21、schedule 45、instant 23、feedback 31、questions 92、history 22、catalog 24，全部通过。`smoke_schedule_workbench` 1 项通过。
- `check_ui.py --update-baseline` 后为 0 处问题，旧存量 handlers 107、html_assign 73、inline_style 117、color_literals 95、font_size_literals 207；`check_contrast.py` 58 组达标。
- `tests/visual/run.py --ref HEAD --pages catalog` 的四张截图都有预期变化：桌面浅 / 深约 28.990% / 29.626%，手机浅 / 深约 51.000% / 51.721%。旧树的紧凑文字行、emoji 和行内进度条换成留白更清楚的统计卡、原生目录按钮和 SVG 图标；手机工具栏换行、到期标记与数字分行，差异占比因纵向重排较高。运行时目录审计四种组合均为 3 档字号、最小 12px、小目标 0、有效行内样式 0、横向溢出 0；旧版桌面小目标 25、行内样式 50。页面脚本错误为 0。
- 仪表盘 E2E 首轮 25/26，失败项只因旧断言假设当天一定有练习记录；按快照与浏览器当地日期核对后重跑为 26/26。目录扫描 E2E 首轮等待条件过早满足，改成等 `/api/tree` 请求后为 24/24。

未执行：生产部署（需要用户单独授权）；Firefox 与 WebKit 留给计划的终检阶段。

---

## 报告页迁移（2026-09-27，v1.25.7）

### 盘点与行为变化

- 旧 `assets/reports.js` 持有 `REPORTS` 全局和 `fmtSize`、`buildReportAiPrompt`、`copyReportAiPrompt`、`downloadReportData`、`loadReports`、`renderReports`、`openReport`、`readFileText`、`createReport`、`deleteReport`。`#panel-reports` 的旧 DOM 包含图片开关、材料按钮、名称与文件输入、列表；专用 `.rp-*` 样式在 `assets/styles.css`。跨页旧引用仅有 `legacy-pages.js` 的进入钩子和 `legacy-bridge.js` 的旧调用方说明；后端接口和沙箱协议未改。
- 新 `features/reports/` 用纯 `state.js` 保存文件验证、大小格式、材料说明和 AI 提示词；`index.js` 管理列表、文件读取、上传、删除和下载的生命周期；`view.js` 提供 token 化卡片、`ui/filedrop`、空态与嵌入预览。`ui/filedrop` 的 `bindFileDrop` 新增可选拒绝回调，让非 HTML 文件在上传区直接显示原因；空文件、读取失败、上传失败也明确提示，上传期间防重。
- 「浏览」在页内用 `iframe sandbox="allow-scripts allow-downloads allow-popups"` 预览；没有 `allow-same-origin`，报告脚本仍处于后端 CSP 沙箱。原新标签入口保留为单独按钮。删除经 `ui/dialog` 确认；材料提示词随题图选项切换，下载继续走 `/api/export-review` 和 `core/download.js`。
- 删除旧脚本、旧 HTML 表单及 13 条专用 CSS，`main.js` 登记页面并移除旧页面项。原报告页无独立前端 Node 测试；新增 `tests/app/reports.test.mjs` 4 项纯规则与模板断言、`tests/e2e/reports.py` 23 项真实浏览器路径，后端 `tests/test_report_export.py` 保持不变。

### 影响文件

新增 `assets/app/features/reports/`、`tests/app/reports.test.mjs`、`tests/e2e/reports.py`；删除 `assets/reports.js`；修改 `assets/app/ui/filedrop.js`、`assets/app/main.js`、`assets/app/legacy-pages.js`、`assets/app/legacy-bridge.js`、`assets/app/styles/index.css`、`assets/styles.css`、`omrs_dashboard.html`、`tests/ui_baseline.json`。同步 `AGENTS.md`、`AI/frontend/records.md`、`AI/frontend/components.md`、`AI/frontend/architecture.md`、`AI/frontend/shell.md`、`AI/frontend/create.md`、版本号四处、`AI/changelog.md`、`README.md` 与本进度文件。旧 CSS 精确删除已逐段对照差异。

### 验证

- 实际运行：`tests/app/reports.test.mjs` 4/4，`tests/e2e/reports.py` 23/23；上传路径含拖入非法文件、空文件、读取错误、真实创建、沙箱预览、带图 ZIP 下载、删除取消和确认、列表错误重试。`check_ui.py` 为 0 处问题，旧存量 handlers 101、html_assign 61、inline_style 100、color_literals 95、font_size_literals 198；`check_contrast.py` 58 组达标。
- `tests/visual/run.py --ref HEAD --pages reports` 四张截图差异：桌面浅 / 深 3.439% / 5.945%，手机浅 / 深 13.868% / 21.487%。左侧材料区与上传区换成更清楚的同尺度卡片，右侧列表空态调整，手机由旧表单单列改为分段卡片，因此手机差异较高。运行时四种组合均为 3 档字号、最小 12px、小目标 0、有效行内样式 0、横向溢出 0；旧版 7 档字号、最小 10.2px、有效行内样式 3。页面脚本错误为 0。
- E2E 首轮失败于确认框有两个关闭按钮，以及审计把复选框和文件输入本身的尺寸当成点击目标；测试改为定位对话框脚部取消按钮、量包裹输入的 label 后通过。读取失败模拟后 Playwright 序列化原生 FileReader 构造器报错，改为只恢复不返回构造器后通过。

全量回归实际运行：Python unittest 160 项、Node 238 项、浏览器单测 34 项；E2E shell_router 20、ui_bridge 15、dashboard 26、data 21、schedule 45、instant 23、feedback 31、questions 92、history 22、catalog 24、reports 23，全部通过。`smoke_schedule_workbench` 1 项通过。`check_docs.py --write-routes`、`--write-log-index` 已运行；`--diff HEAD` 为 0 处问题、2 条篇幅提醒。`git diff --check` 通过。隔离实例均使用临时 Vault、随机端口，且移除了 `OMRS_SYSTEMD_SERVICE`。最后补强了 FileReader 错误在文件拖放区内的提示，报告页 E2E 重跑仍为 23/23。

未执行：生产部署（需用户单独授权）；Firefox 与 WebKit 留给计划终检。

---

## 设置页迁移（2026-09-27，v1.25.8）

### 盘点与行为变化

- 旧 `assets/app.js` 的设置段包含五分区导航、外观、本机与远端访问、PIN、AI 配置、运行状态、备份和图片优化；对应 DOM 在 `omrs_dashboard.html`，设置专用规则在 `assets/styles.css` 的优化卡、外观控件和设置分区段。旧抽函数测试为 `test_settings_ui.js`（8 项）、`test_restart_ui.js`（6 项）、`test_auth_activity_ui.js`（4 项）；最后一份还覆盖 `core.js` 的活动续期和手机页 `/m` 的会话过期处理。
- 新 `features/settings/` 按外观、访问、AI、数据、服务五区拆分，`state.js` 与 `storage-state.js` 保留纯投影。设置页成为路由页面契约，旧 `app.js` 设置段和专用 CSS 已删除。主题、密度、反色和 Ledger 时区沿用原 localStorage 键；访问范围以运行中的监听状态为准，免 PIN 网段单独保存不重启。PIN 与 AI Key 的校验和非回显保持；重启只在新 `instance_id` 出现后刷新。
- 备份导入先确认上传、校验后再确认覆盖；图片扫描和压缩经任务接口轮询，离开页面再进入可继续读取任务或已完成的扫描候选。源码下载保留 `/api/source/export`。访问、AI、存储和服务的错误原地提示，重复写操作在请求期间受控。
- 三份旧 Node 测试的 18 个用例迁到 `tests/app/settings.test.mjs`，用例总数为 18；其中活动续期与 `/m` 的 4 项保留原断言，P8 清理 `core.js` 时仍需改成新模块 import。新增 `tests/e2e/settings.py` 覆盖五区、非法网段、只改网段不重启、PIN、Key 不回显及清除、备份、扫描轮询、切页保留扫描、源码下载、重启新实例判定及四种显示组合的每区审计。重启请求由 Playwright route 拦截，没有真的重启实例；临时 Vault 不含源码目录，源码下载前端路径由固定 ZIP 响应验证，服务端打包由 `tests/test_source_export.py` 实测。

### 影响文件

新增 `assets/app/features/settings/`、`tests/app/settings.test.mjs`、`tests/e2e/settings.py`；删除三份旧 Node 设置测试；修改 `assets/app.js`、`assets/app/main.js`、`assets/app/legacy-pages.js`、`assets/app/styles/index.css`、`assets/styles.css`、`omrs_dashboard.html` 和 `tests/ui_baseline.json`。同步 `AGENTS.md`、`AI/frontend/settings.md`、`AI/frontend/design-system.md`、`AI/frontend/architecture.md`、`AI/frontend/shell.md`、`AI/security.md`、`AI/inbox.md`、`AI/optimization.md`、`AI/routes.md`、版本号四处、`AI/changelog.md`、本计划进度和日志索引。旧 CSS 按设置专用段精确删除，通用 `.status-grid` 仍留给其它页面；`git diff --check` 通过。

### 验证

- 实际运行：Python unittest 160 项；Node 238 项（设置新文件 18 项）；浏览器单测 34 项；E2E shell_router 20、ui_bridge 15、dashboard 26、data 21、schedule 45、instant 23、feedback 31、questions 92、history 22、catalog 24、reports 23、settings 50，全部通过；`tests.smoke_schedule_workbench` 通过；源码导出后端单测 3 项通过。隔离实例使用临时 Vault、随机高端口，移除 `OMRS_SYSTEMD_SERVICE`，浏览器经本机 CDP 运行。
- `check_ui.py --update-baseline` 下调旧代码存量后为 0 处问题：handlers 69、html_assign 48、inline_style 67、color_literals 95、font_size_literals 173。`check_contrast.py` 58 组均达标。设置页 E2E 的五分区 × 桌面/手机 × 浅/深共 20 项审计均满足字号 ≤6 档、最小 ≥12px、小目标 0、有效行内样式 0、横向溢出 0。
- `tests/visual/run.py --ref HEAD --pages settings` 四张截图差异：桌面浅 / 深 3.787% / 4.337%，手机浅 / 深 14.307% / 14.737%。导航由旧紧凑列改成统一间距与清晰选中边，卡片布局和开关尺寸扩大，手机控件纵向重排；侧栏版本号从 v1.25.7 改为 v1.25.8。首屏运行时审计从旧版 5–6 档字号、最小 10.2/10.8px 改为 3 档、最小 12px，四种组合均无脚本错误。已人工审阅桌面浅色与手机深色截图。

未执行：生产部署（需要用户单独授权）；Firefox、WebKit 和 12 页空态终检属于后续计划阶段。

---

## 录入题目外壳与工作区导航（2026-09-27，v1.25.10）

### 盘点与行为变化

- `assets/inbox.js` 的 673 行分为上传与收件箱筛选、框选画布与保存、检测 / 提取任务、题卡与提交、训练数据和策略五组；`ibBind()` 在 `#panel-create` 上委托点击 / 输入 / 变更，并在 `document` 捕获粘贴、监听处理区快捷键 Q / A / X / Delete / Enter / Ctrl+Enter / Esc，还在画布上绑定指针事件。`assets/app.js` 保留 `cr*` 快速录入图片与 AI 识别，`assets/schedule.js` 保留 `doCreate` / `resetCreateForm`，`assets/labels.js` 保留录入标记选择器。`omrs_dashboard.html` 的 `#panel-create` 包含 `ib-stage-upload / process / create / train / quick` 五区；`styles.css` 的 `.ib-*`、`.cr-*` 规则仍覆盖旧工作区。`tests/e2e/ui_bridge.py` 直接调全局 `ibToast`，其余调用方和旧内联事件仍保留。
- `features/create/` 新增页面契约、导航状态与模板、导航样式；`main.js` 注册它，`legacy-pages.js` 移除 create 项。旧工作区放在 `#create-app`，挂载时仍调用旧 `inboxInit()`，保证上传、处理、录入、训练和快速录入都能继续使用。`ibGo()` 同步按钮的 `aria-current`，切页返回后旧控制器的阶段状态和导航保持一致。
- 工作区入口改成原生按钮，前三步显示编号，AI 训练和快速录入使用统一 SVG 图标。手机导航采用三项加两项的两行排列，修掉首次截图发现的文字重叠。当前旧工作区的字体和行内样式仍待后续分步迁移，不能算 P6 页面指标已达标。

### 影响文件

- 页面与样式：`assets/app/features/create/`、`assets/app/main.js`、`assets/app/legacy-pages.js`、`assets/app/styles/index.css`、`assets/inbox.js`、`omrs_dashboard.html`。
- 测试：`tests/e2e/create.py` 新增隔离实例的导航、上传与快速录入主路径。
- 文档与版本：`AGENTS.md` 映射表、`AI/frontend/create.md`、`AI/frontend/architecture.md`、`AI/frontend/design-system.md`、`AI/frontend/shell.md`、`AI/inbox.md`、`AI/changelog.md`、`AI/README.md`、`README.md`、`omrs/version.py`、本计划 `progress.md`。

### 验证

已实际执行：`python3 tests/e2e/create.py` 8 / 8，使用临时空 Vault、随机端口与独立 Chromium，启动时移除了 `OMRS_SYSTEMD_SERVICE`；覆盖五个入口、图片暂存上传、键盘进入处理区、快速录入写入题库、切页返回保留工作区和页面脚本错误。`python3 tests/check_ui.py` 为 0 处问题，旧存量计数未增加；`python3 tests/check_contrast.py` 58 组达标；`git diff --check` 通过。

`tests/visual/run.py --ref HEAD --pages create` 的四组截图均有差异：桌面浅 / 深色 3.893% / 4.005%，手机浅 / 深色 20.252% / 20.944%。桌面变化集中在按钮边框、编号与 SVG；手机导航由拥挤的一行改成两行，所以下方内容整体下移。浏览器页面脚本错误为 0；当前页桌面 12 档字号、最小 9.9px，手机 11 档、最小 10.5px，四组均有 6 处有效行内样式，属于尚未迁移的旧工作区。手机整页横向溢出由有变无；后续各工作区迁完再按 P6 验收指标审计。

本提交的全量门禁实际运行：Python unittest 160 项通过；Node 238 / 238；组件浏览器测试 34 / 34；E2E 的 shell_router、ui_bridge、dashboard、data、schedule、instant、feedback、questions、history、catalog、reports、settings、create 依次为 20、15、26、21、45、23、31、92、23、26、24、50、8，均全部通过；`tests.smoke_schedule_workbench` 1 项通过。浏览器测试均使用临时 Vault、随机端口与独立 Chromium，隔离实例环境中移除 `OMRS_SYSTEMD_SERVICE`。

`python3 tests/check_docs.py --write-log-index` 已运行；`python3 tests/check_docs.py --diff HEAD` 为 0 处问题、2 条既有的篇幅提醒。最后重跑 `check_ui.py` 为 0 处问题（旧存量 handlers 69、html_assign 48、inline_style 67、color_literals 95、font_size_literals 173），`check_contrast.py` 58 组均达标，`git diff --check` 通过。

未执行：生产部署与远端设备验证（需用户单独授权）；Firefox、WebKit 和全站空态终检属于后续计划阶段。
