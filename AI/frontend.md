# 前端

> 入口：`omrs_dashboard.html`（仅结构）。样式与脚本拆分到 `assets/` 资源文件夹。

无构建步骤。后端与本地前端代码不需要打包依赖；主仪表盘和移动收件箱从 `assets/vendor/fonts/fonts.css` 加载本地 Noto Sans SC 与 JetBrains Mono WOFF2 Unicode 分片，字体 CSS 不含远程 URL。KaTeX 从 `assets/vendor/katex/` 本地加载并渲染 LaTeX（不可用时降级为可辨识的公式源码片段）。所有图表使用纯 CSS + 内联 SVG 实现。

> 本文只描述**当前**的前端结构与行为。各版本改了什么、为什么改，统一放在 [`changelog.md`](changelog.md)（按版本倒序），这里不再逐版堆叙述；需要考古时先看 changelog，再看 `logs/`。

## 目录

1. 仪表盘图表 · 1.1 行动推荐 · 1.2 整屏工作台布局
2. 题库双视图 · 2.1 目录页 · 2.2 共享题目视图 qview
3. 筛选控件 · 3.1 用户标记筛选 · 3.2 题库页 · 3.3 标记组件 · 3.4 展示板页
4. 推荐面板
5. 即时练习 · 5.1 反馈录入工作台 · 5.1.1 答题卡 JSON 导入
6. 临时调度 vs 常规 Session
7. 设置页面
8. 历史记录页
9. 录入题目页 · 9.1 收件箱录入流程
10. 数据页（复盘）
11. 报告页
12. 主题与深色对比度

## 文件组织（assets/）
```
omrs_dashboard.html   ← 仅 HTML 结构，<link> 引样式 + 多个 <script> 引脚本
assets/
├── styles.css        ← 全部样式（原 <style> 内联块抽出）
├── vendor/fonts/     ← 本地 Noto Sans SC / JetBrains Mono 字体分片、许可与来源清单
├── core.js           ← 全局状态、api()、通用工具/筛选/Markdown 渲染 + 做题记录解析（v1.16.0）
├── dashboard.js      ← 仪表盘图表 renderDash
├── labels.js         ← 用户标记芯片、LabelPicker、标记管理与筛选状态
├── questions.js      ← 题目库表格/画廊视图 + 题目 Modal + 安全 Markdown/LaTeX/表格渲染 + 原文编辑/迁移/删除/停用恢复入口
├── qtable.js         ← 题库筛选抽屉、激活 chips、批量条、列设置、密度、视图预设与快捷键
├── qview.js          ← 共享题目视图：题面/答案双栏组件 + 底部记录模块 + Modal 翻页（v1.10.0 新增，v1.16.0 加记录模块，见 §2.2）
├── schedule.js       ← 复习 Session 数据同步、工作区扫描 + 录入提交（doCreate/resetCreateForm）；复习调度页不再渲染 Session 历史/反馈表，旧端点保留兼容
├── export.js         ← 错题导出：选题/画廊预览、A4/屏幕变体、A4 单双栏确认、题间留白、下载（v1.5.0 从 schedule.js 拆出）
├── feedback.js       ← 反馈录入工作台：session 选择、题目列表/判定面板、AI 提示词、JSON 导入、提交（v1.5.0 从 schedule.js 拆出；v1.10.0 改三栏；v1.11.0 加答题卡扫描 JSON 解析）
├── history.js        ← 数据复盘/历史：Ledger 时间线、修正面板、撤销/恢复/还原（v1.5.0 从 schedule.js 拆出）
├── recommend.js      ← 推荐面板（双列表 + 勾选确认）
├── recommend_v2.js   ← 优化推荐面板；使用私有 `recV2GetFilterState` / `recV2FilterItems`，不覆盖 core.js 公共筛选 API
├── actions.js        ← 行动推荐：由 DATA + SESSIONS 派生「现在该做什么」（v1.7.0 新增）
├── catalog.js        ← 目录页：错题/ 文件夹树，读 GET /api/tree（v1.7.0 新增）
├── instant.js        ← 即时练习：推荐取题、在线翻答案、即时反馈
├── data.js           ← 数据复盘页 + 复盘报告导出
├── board.js          ← 展示板 CRUD、排序、添加题目、打印（全部 / 仅新增）与纸面记录
├── board_preview.js  ← 展示板常驻预览 iframe 的生命周期与消息协议（必须排在 board.js 之后）
├── reports.js        ← 报告托管页：列表/上传创建/浏览/删除
└── app.js            ← 应用入口：switchTab/reloadData/设置 + 录入页图片粘贴/AI 识别/AI 设置 + init()
```

**加载约定（重要）：**
- 脚本均为普通 `<script>`（非 ES module），共享同一全局作用域；顶层 `let`/`const` 跨文件可见，行内 `onclick` 仍可直接调用各函数。
- **v1.14.0 加载顺序**：`labels.js` 在 `questions.js` 之前，供题库渲染直接调用
  `lblChip()`；`qtable.js` 在 `questions.js` 之后、`qview.js` 之前；`board.js`
  在 `export.js` 之后、`app.js` 之前。当前 HTML 的完整顺序为
  `core → labels → dashboard → questions → qtable → qview → schedule → export →
  feedback → history → recommend → actions → catalog → instant → data → inbox →
  board → board_preview → reports → app`。`board_preview.js` 必须排在 `board.js`
  **之后**：`board.js` 只在第一次真正用到预览时才 `boardPreviewOn(...)` 注册回调
  （`boardBindPreview()` 的惰性注册），否则模块顶层注册时 `boardPreviewOn` 还不存在。
- **新增文件的插入位置（v1.10.0）**：`qview.js` 必须排在 `questions.js` 之后、`schedule.js` 之前——它依赖 questions.js 的 `renderMdContent` / `ensureQuestionDetail` / `QUESTION_CACHE`，而 `feedback.js`、`instant.js`、`export.js`、`data.js` 又依赖它的 `qvRender` / `qvHtml` / `qvSetContext`。
- **新增文件的插入位置（v1.7.0）**：`actions.js` 和 `catalog.js` 排在 `recommend.js` 之后、`instant.js` 之前。两者都只在运行时被调用（`renderDash()` / `switchTab('catalog')`），对同批次内的先后不敏感，但必须在 `core.js` 之后——它们依赖 `getItems` / `getDueDays` / `isKilledItem` / `daysSinceReview` / `escapeHtml` 等。
- **加载顺序固定**：`core.js` 最先（定义全部全局变量，只能声明一次，不可在其他文件重复 `let`）；`app.js` 最后（末尾 `init()` 自调用，依赖前面所有文件已就绪）。
- 后端由 `/assets/<file>` 通用静态路由提供（`server.py` → `_serve_asset()`，含路径穿越防护与按扩展名的 content-type）。原 `/omrs_dashboard.js` 路由已移除。
- 修改样式 → 改 `assets/styles.css`；改某模块行为 → 改对应 `assets/*.js`；新增全局工具 → 放 `core.js`。
- **拆分（v1.5.0）**：原 `schedule.js`（约 100 行的杂烩，混了导出 / Session / 反馈页 / 录入提交 / 历史时间线 / 扫描）按职责拆为 `export.js`、`feedback.js`、`history.js`，`schedule.js` 仅留 Session + 扫描 + 录入提交。因共享全局作用域且行内 `onclick` 在运行时调用，拆分只是「搬运函数 + 增加 `<script>`」，函数名 / 签名 / 调用关系全不变；加载顺序：四者都在 `core.js` 之后、`app.js` 之前。

---

## 1. 仪表盘图表（`renderDash()`）

首页只回答「今天做什么」（v1.15.0 起）。顶部是一条 `.kpi-strip`，格子 id 为 `s-total` / `s-killed` / `s-kill-pct` / `s-attack` / `s-avgm` / `s-suspended`，由 `renderDash()` 赋值；分布类图表不在首页，在「数据复盘」页。
> - **容器搬到 `panel-data`、id 不变**：`chart-trend`（每日练习趋势）、`chart-labels`（标记分布）。`renderTrendChart` / `renderLabelChart` 仍由 `renderDash()` 调用，函数零改动。
> - **容器直接删除**：`chart-subjects` / `chart-alerts` / `chart-mastery` / `chart-diff`——这四张在复盘页已有同口径的更全版本（`data-subject-radar` / `data-alerts` / `data-mastery` / `data-difficulty`）。对应 render 函数保留且都以 `if(!el)return` 开头，找不到容器即空转，不报错。

| 图表 | HTML 容器 | 数据来源 | 实现方式 |
|---|---|---|---|
| 今天 | `dash-today` | `DATA`（`items` / `daily_trend`）+ `SESSIONS` | `dashboard.js::renderTodayHero()`：整页唯一大字号。待复习总数 = 逾期 + 今日到期，下方拆「逾期 / 今日到期 / 未录反馈」，中列今日已练对比 `actionTodayTarget()`，右列主 CTA。左边框按状态着色（`.lv-overdue` 红 / `.lv-due` 黄 / `.lv-clear` 绿）；空题库走 `.is-empty` 引导态。根类是 `.today-card`，不是 `.today`——`today` 在目录页和推荐页是 chip 的状态修饰类。不新增接口 |
| 近 30 天活动 | `chart-activity` | `stats.recent_activity` | 30 个本地日期热力格，按当期最大次数分 0–4 级；同时显示总复习、活跃天数和单日峰值。紧凑档下 `.activity-heatmap` 改 15 列、隐藏 `.activity-cell small` |
| 最薄弱的科目 | `dash-weak` | `DATA.items` | `dashboard.js::renderWeakSubjects()`：按 `decayed_mastery`（缺省回落 `mastery`）升序取前 6，**题量 ≥ 5 才纳入**，避免一两道题把均值拉到底；每行是 `<button>`，点击调 `actionGoQuestions()` 跳题库对应筛选 |
| 最近动态（Ledger） | `recent-ledger` | `GET /api/history?limit=12`（或复用已加载的 `window.HISTORY_COMMITS`） | `dashboard.js::renderRecentLedger()`：取最近 4 条「非修正、未撤销」的主链节点，渲染精致行——族色圆点 + `historyNodeTitle()` 标题 + `commit_id/seq` + 复习节点显示「N 对 · N 错」chip；卡片右上「完整时间线 →」跳 `switchTab('history')`。复用时间线的 `historyCommitFamily/historyNodeTitle/historyReviewBatchStats/isNodeRetracted` 等函数（现于 `history.js`），故 `dashboard.js` 于运行时（所有脚本就绪后）调用。`renderDash()` 末尾 fire-and-forget 调用它 |

仪表盘四张到期卡的定义（后端 `stats.py`）：

- **今日到期**：`Due_Date == today`；逾期题由 API 单独统计为 `overdue`，不并入该卡。
- **未来 3 天到期**：`1 <= due_delta <= 3`；不含今天。
- **未来 7 天到期**：`1 <= due_delta <= 7`；包含“未来 3 天”集合，不是互斥分桶。
- **未到期低熟练度**：有未来 `Due_Date` 且 `decayed_mastery < 0.5`。

API 为兼容仍返回 `urgent` / `warning` / `cold` / `total_due`，但仪表盘不再用它们渲染四卡。

---

## 1.1 行动推荐（`assets/actions.js`，v1.7.0）

容器 `#action-plan`，位于仪表盘 stat 卡之下、「最近动态」之上。**纯前端派生模块**：只读已经加载好的 `DATA`（`/api/stats`）与 `SESSIONS`（`/api/sessions`），不新增接口、不写 Ledger、不改任何持久化状态。刷新时机跟着 `renderDash()`（末尾调 `renderActionPlan()`）与 `refreshSessions()`（拉完 session 后若 `DATA` 已就绪再重画一次，「未反馈 Session」那条依赖它）；`init()` 在 `refreshSessions()` 之后也补调一次。

### 规则集（`buildActionPlan()`）

按 `level` 排序输出，四级：`urgent` / `warn` / `info` / `good`（`ACTION_LEVEL_META` 定义排序 rank 与中文标签）。除「题库为空」外，所有判据都排除已击杀题和停用题（`actionActiveItems()` 过滤 `!item.suspended && !isKilledItem(item)`）。

| key | level | 触发条件 | 主按钮落点 |
|---|---|---|---|
| `empty` | info | 题库 0 题（此时直接返回，不再算其他规则） | 录入题目页 |
| `overdue` | urgent | `getDueDays(item) < 0` | 即时练习（`actionGoInstant`） |
| `due_today` | warn | `getDueDays(item) === 0` | 复习调度 → 推荐面板 |
| `pending_feedback` | warn | `SESSIONS` 中 `status === 'active'` | 反馈录入（复用 `feedbackSession`） |
| `leech` | urgent | `item.is_leech` | 数据复盘页（顽固题表） |
| `untouched` | info | `attempts === 0` 且 ≥3 道 | 题库，按录入时间排序 |
| `cold` | warn | `last_review` 距今 > 30 天且 ≥3 道 | 题库，按最近复习排序 |
| `idle` | warn(≥7天) / info | `daily_trend` 里最后一个非零日距今 ≥3 天 | 即时练习，题数预设 5 |
| `never` | info | 完全没有练习记录 | 即时练习 |
| `low_not_due` | info | 未到期但 `decayed_mastery < 0.5` 且 ≥3 道 | 题库，未到期 + 熟练度升序 |
| `weak_subject` | info | 最薄弱科目（≥3 题）平均衰减熟练度 < 0.55 | 即时练习，预设该科目 |
| `weak_category` | info | 最薄弱分类（≥3 题）平均 < 0.45 | 即时练习，预设该分类 |
| `all_good` | good | 上述规则没产生任何 urgent / warn | 即时练习 |

`actionWeakestGroup(items, field, minCount)` 要求组内至少 `minCount` 道题、且总组数 > 1，避免一两道题就把某科目均值拉到底。

### 渲染与交互

- `renderActionPlan()` 默认只渲染前 4 条，其余折叠在「还有 N 条建议，展开 ↓」（`toggleActionPlanAll()` 切 `ACTION_SHOW_ALL`）。
- `actionTodayTarget()`（逾期 + 今日到期，再加最多 3 道顽固题，封顶 20）**v1.15.0 起改由首页「今天」条消费**（`renderTodayHero()` 的「建议 N 题」）；行动推荐卡头不再重复显示这个数字，`renderActionPlan()` 内保留 `void target;` 标明该值已算但不在此渲染。
- 按钮的回调是**闭包**，存在 `ACTION_PLAN[i].actions[j].run` 上，行内 `onclick` 只写 `runActionPlanItem(i,j)` 下标——不要改成把函数名拼进 HTML 字符串。
- 跳转辅助：`actionGoQuestions(preset)` 会**先清空**题库页全部筛选控件（含停用状态）再套 preset，然后 `switchTab('questions')` + `renderQ()`；`actionGoInstant(preset)` 同理清空 `inst-*` 后 `instLoadPractice()`。preset 的键就是元素 id。
- 样式在 `styles.css` 的 `.act-*` 段，等级色由 `.lv-urgent/.lv-warn/.lv-info/.lv-good` 决定，全部走 `--red-rgb` 等 token，深浅色自动跟随。≤720px 时改为图标 + 正文两列、按钮整行。v1.15.0 起 `.act-item` 在宽屏是**单行**栅格（`"icon body metric buttons"`），按钮右对齐不换行；间距走密度变量。

---

## 1.2 整屏工作台布局（`.is-workbench`，v1.15.0）

功能复杂的多栏页原先各自为战：收件箱处理页写死 `height:calc(100vh - 200px)`，反馈工作台和题库则靠
`position:sticky` 让侧栏跟随、整页一起滚。前者的 `200` 是数出来的，页头一旦加减工具栏就算错；
后者在长列表下会把工具条、表头和「提交反馈」按钮一起滚出视口。

v1.15.0 统一成一条链路：

1. `app.js::switchTab(name)` 给 `.content` 切 `.is-workbench` 类，命中五页：
   `questions` / `feedback` / `create` / `board` / `instant`。
2. `styles.css` 在 `@media(min-width:1161px)` 内让 `.content.is-workbench` 变成
   `height:100vh; overflow:hidden` 的 flex 列，`.topbar` 不收缩，`.panel.active` 拿走剩余高度。
3. 各页把自己的滚动容器标成 `flex:1; min-height:0; overflow-y:auto`。

因此高度是从 `.content` 一路分下去的，**不再出现 `calc(100vh - 魔数)`**；页头加减工具栏无需重算。

| 页面 | 撑高的容器 | 各自滚动的区域 |
|---|---|---|
| 题目库 | `.qb-card` → `.qb-wrap` → `.qb-main` | `#q-table-wrap` / `.question-gallery-wrap` / `.qb-drawer` |
| 反馈录入 | `.fb-work`（`grid-template-rows:minmax(0,1fr)`） | `.fb-rail` / `.fb-stage` / `.fb-panel` 三栏独立 |
| 录入题目 | `.ib-stage.on`；处理页额外 `#ib-stage-process.on` → `.ib-proc` | 处理页三栏；上传 / 录入 / AI 训练三个 stage 整体滚 |
| 展示板 | `.bd-layout` | `.bd-layout > .card` 三张 |
| 即时练习 | `.inst-work` | `.inst-main` / `.inst-queue-wrap` |

配套：`#q-table-wrap thead th` 加 `position:sticky; top:0`，列表再长表头也在。
`.qb-drawer` 在工作台模式下从 `position:sticky` 改回 `static`（父级已经限高，再 sticky 会双重定位）。

**只在 ≥1161px 生效**。窄屏保持 v1.14.x 的既有响应式：反馈工作台仍走 1160 / 820 两档重排，
题库抽屉仍在 1100px 落到列表上方，都不受影响。

改这几页时的注意点：
- 新增的滚动容器必须同时写 `min-height:0`，否则 flex 子项按内容撑开，`overflow` 不生效。
- 往工作台页面加新的顶部工具栏，记得给它 `flex-shrink:0`，否则会被压扁。
- 新增工作台型页面时，改 `switchTab()` 里的那个数组即可，不需要动 CSS 结构。

---

## 2. 双视图

### 题目停用筛选与操作

题目库顶部 `#q-filter-suspended` 默认选择“活动题目（不含停用）”，也可切换“仅停用题目”或“含停用全部”。停用题行/卡片以灰色虚线弱化，并显示“停用”标签；编辑菜单根据状态显示“停用题目”或“恢复题目”。操作调用 `POST /api/question/suspend` / `POST /api/question/resume`，成功后刷新题库和历史动态。


### 平铺式（List View）
- 高密度列表，每行显示 UID、科目、分类、难度、熟练度进度条、标签。
- 可直接点击加入/移除临时调度选题。

### 画廊式（Gallery View）
- 卡片形式，异步拉取 `/api/question?uid=...` 渲染题面；v1.10.0 起缩略预览走 `qvHtml(detail, item, QV_CARD_OPTS)`（`bare` + `clamp:6`），与 Modal、反馈台同一份渲染。导出选题器的画廊卡同理。
- v1.11.0 修掉预览框顶部约 220px 的空白：容器上的 `white-space:pre-wrap` 会把 qview HTML 里标签之间的换行渲染成空行，见 §2.2 末尾。
- 卡片中同样使用 `.m-bar` / `.m-bar-fill` 渲染熟练度进度条。
- **脚注战绩带（v1.16.0，默认开；v1.16.1 改读 Ledger 记录）**：`galleryFootHtml()` 里原来的「N 次」换成 `galleryStreakSlotHtml()` 产出的
  `.gc-streak-slot` 占位（先显示 `attempts` 数字），`hydrateQuestionGalleryPreviews()` 拿到同一次 `ensureQuestionDetail(uid)`
  的结果后调 `galleryStreakBodyHtml(item, detail)` 就地替换成 `qStreakHtml()` + 记录数 +（仅连错 ≥2 时）「连错 N」。
  记录来源是 `detail.records[]`（`GET /api/question` 从 Ledger 投影派生），经 `core.js::qRecordsFromDetail()` 统一取出；
  题目 Markdown 的 `# 历史` 旧文本只在后端没给 `records` 时兜底。
  **不额外发请求**：画廊本来就要为题面预览拉一次 `/api/question`，战绩带搭同一趟车；详情拉取失败时占位数字原样留着。
  开关 `QB_STREAK`（`localStorage('omrs-qb-streak')`，缺省即开）在「列 / 密度」菜单画廊段，关掉走 `attempts` 纯数字分支。
- 题面中的 `![[图片.png]]`、`![[图片.png|300]]`、`![alt](路径)` 均改写为 `/api/image?name=...`。
- 使用 `renderMdContent()` 统一处理 HTML 转义、图片替换与 `$...$` / `$$...$$` LaTeX 渲染。
- 题目详情缓存在 `QUESTION_CACHE` / `QUESTION_PENDING`，避免重复请求。

### 编辑菜单
- List View 和 Gallery View 每题都有「编辑」按钮；v1.10.0 起题目 Modal、反馈工作台和即时练习题卡内也直接带「编辑 Markdown」等操作按钮（由 qview 的 `actions` 渲染），不必退回列表找入口。
- 点击后在按钮下方自然展开操作列表，不再用编号 prompt 选择操作。
- 「迁移到其他分类」调用 `POST /api/question/move`，后端按目标分类已有 UID 的最小缺口分配新 UID。
- 「编辑 Markdown」调用 `GET /api/question/raw` 打开纯文本 textarea，保存时调用 `POST /api/question/markdown`。编辑器不做富文本渲染，完整显示 `.md` 原文。
- 「删除题目」调用 `POST /api/question/delete`；二次确认明确说明会删除 Markdown 正文、只保留 Ledger 归档和历史反馈、附件图片不删。成功后清除详情缓存，重载题库与历史时间线。
- 保存后立即刷新数据；如果只改正文，后端只更新 fingerprint；如果改 YAML 结构化字段，后端写 metadata update commit。

### 通用 Markdown / LaTeX 渲染
- `renderMdContent()` 只允许三类受控 HTML：图片 `<img>`、KaTeX 输出、降级公式 `<span class="math">`；普通文本始终先转义。
- 支持 Obsidian 图片 `![[name.png]]`、`![[name.png|300]]` 和 Markdown 图片 `![alt](path)`，图片名统一取 basename 后走 `/api/image?name=...`。
- 支持行内 `$...$` 和行间 `$$...$$`，包括跨多行的 `$$` 块（先合并后再交给 KaTeX，`cases` 等环境不会被按行拆散）。KaTeX 加载成功时使用 `katex.renderToString(..., {throwOnError:false})`；加载失败时保留公式内容并加 `.math` 样式。
- 题目库 Modal 的题面、备注、答案，调度/推荐中的题目预览，以及即时练习的题面、答案、备注都应复用该函数；不要再用 `<pre>${escapeHtml(...)}</pre>` 展示需要图片或公式的字段。

- 支持带表头和分隔行的 Markdown 表格（分隔单元格匹配 `:?-{3,}:?`，`\|` 表示单元格内竖线）。`renderMdContent()` 逐行识别后输出 `.md-table-wrap > table.md-table`，缺失单元格补空、超出表头的单元格忽略。
- 表格单元格继续走 `renderMdInline()`，因此文本先转义，图片和 LaTeX 仍遵循同一安全规则；小屏通过 `.md-table-wrap` 横向滚动。这里不是通用 Markdown 引擎，标题、粗体、列表等语法仍按普通文本显示。
---

## 2.1 目录页（`assets/catalog.js`，v1.7.0）

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
- `reloadData()` 里若目录页正处于激活状态且 `CATALOG_TREE` 已有，会重画一次——录题或提交反馈后目录上的熟练度条随之更新，但**不会重新扫盘**（结构变化仍需点「重新读取」或顶栏「重新扫描」）。

样式在 `styles.css` 的 `.catalog-bar` / `.tree-*` 段。≤720px 缩小缩进步长、收窄右侧栅格，并只隐藏文件夹行的 chip（题目行的到期 chip 仍显示）。

`today` / `overdue` / `new` 这类词在本页是 chip 的状态修饰类，任何组件都不能拿它们当根类；未加限定的 `.m-bar` 规则也不得声明伸缩属性（`flex` / `flex-*` / `gap`），窄容器里靠限定后的规则单独覆盖。

---

## 2.2 共享题目视图 qview（`assets/qview.js`，v1.10.0）

在此之前，同一份题目内容有三处互不相同的渲染副本：`viewQ()` 的 `.q-body/.q-md/.q-answer-md`、画廊卡的 `.gallery-preview`、即时练习的 `.instant-block/.instant-md`。三处各自演化，改一处样式其余两处不跟。qview 把它们收敛成一个组件，「反馈页能看题」和「预览改双栏」这两件事因此变成同一件事的两个用法。

### 对外接口

```js
qvHtml(q, item, opts)          // 纯函数：详情 + 投影条目 → HTML，可在 node 侧单测
qvRender(mount, uid, opts)     // 挂载：走 ensureQuestionDetail 缓存 → 渲染 → 登记 QV_MOUNTS
qvInvalidate(uid)              // 清 QUESTION_CACHE[uid]，重绘所有挂着该 uid 的容器
qvSetContext(name, uids)       // 登记一段 uid 序列，供 Modal 翻页使用
```

`opts` 默认值：`layout:'split'`（`'stack'` 为单栏）、`reveal:true`、`showAnswer/showNotes/showHistory/showMeta:true`、`bare:false`、`actions:[]`、`clamp:0`。`showHistory` 控制的是题目详情**最下面的通栏记录模块** `qvRecordHtml()`（四个派生数 + 主观分 sparkline + 明细，首屏 3 条其余折叠）。

- **记录模块的数据源（v1.16.1）**：`qRecordsFromDetail(detail)`——`detail.records` 是数组就以它为准（空数组 = 后端明确说没练过，显示「还没练过。」，不再出现「熟练度表记了 N 次…」这类自相矛盾的话）；只有老后端没给 `records` 时才退回 `parseQHistory(detail.history)` 解析 Markdown 旧行，此时若旧行解析不出才把原文 `<pre class="qv-rec-raw">` 原样保留。返回数组带 `source:'ledger'|'markdown'`。
- **缓存失效**：`QUESTION_CACHE` 里的详情现在含记录，所以反馈提交（`feedback.js::submitFb`、`instant.js::instSubmitPractice`）和历史修正（`history.js::historyPost`）成功后调 `qvInvalidateMany(uids)`（不传则全清）丢掉过期详情并重绘挂着的视图。

- **`reveal:false` 不渲染答案 DOM**，只渲染「显示答案」按钮（`opts.onReveal` 回调）——少渲染一遍 KaTeX，也不必担心答案躺在 DOM 里被翻出来。
- `actions` 可含 `'edit'`（编辑 Markdown）、`'suspend'`（按当前状态自动显示停用/恢复）、`'delete'`、`'open'`（跳题目库并按 UID 过滤）。按钮只转调 questions.js 已有的全局函数，qview 自己不写业务逻辑。
- `bare:true` + `clamp:N` 供画廊缩略卡使用：去掉正文边框底色、按行数截断。
- `QUESTION_CACHE` 的降级副本带 `_fallback:true` 标记（由 `ensureQuestionDetail` 写入），qview 据此渲染「无法加载题目预览 + 重试」而不是把坏数据当正文显示；重试即 `qvInvalidate`。

### 交互与 DOM 约定

- 结构：`.qv > .qv-head`（UID / chips / 工具栏）+ `.qv-q`（题目）+ `.qv-a`（答案 / 备注）+ `.qv-rec`（记录模块，v1.16.0 新增，双栏下通栏）。
- **不把函数名拼进 HTML 字符串**：所有按钮带 `data-qv-act`，由文件底部一个文档级委托处理器分发；翻页按钮带 `data-qv-nav`。
- **双栏塌陷用容器查询**（`container-type:inline-size` + `@container qv (max-width:680px)`），因为同一个组件既进 1180px 的 Modal、又进约 420px 的反馈中栏和 300px 的画廊卡，只有容器查询能让三处各自决定；`@supports not` 下降级为 900px 视口断点。
- 答案块走 `rgba(var(--green-rgb),α)`，不再有写死浅色的 `rgba(39,134,74,.04)`；深色无需单独规则。深色「反转题图」的选择器覆盖 `.qv .q-md img`。

### 四处调用点

| 调用点 | 用法 |
|---|---|
| `viewQ(uid, context)` | `qvRender('#modal-stage', uid, {layout:'split', actions:['edit','suspend','delete']})` |
| `fbRenderStage()` | `qvRender('#fb-stage', uid, {layout:'split', actions:['edit','suspend','open']})` |
| `instRender()` | `qvRender('#inst-qv', uid, {reveal:row.revealed, showHistory:false, actions:['edit'], onReveal:instReveal})`——练习中不显示记录，免得未答先看见历史分数 |
| 画廊 / 导出选题卡片 | `qvHtml(detail, item, QV_CARD_OPTS)`，即 `{layout:'stack', showMeta:false, showAnswer:false, showNotes:false, showHistory:false, bare:true, clamp:6}` |

### 画廊缩略预览与 `white-space`（v1.11.0 修复）

`.gallery-preview` 上有一条 `white-space:pre-wrap`，是 v1.10.0 之前留下的——那时框里装的是一段纯文本。改用 qview 之后框里装的是 HTML，而 `qvHtml()` 是多行模板字符串，标签之间带换行和缩进；`pre-wrap` 下这些纯空白文本节点**不会折叠**，每个都渲染成空行：

```
<div class="qv …">          ← 后面 "\n    " = 2 行
    <section class="qv-q">  ← 后面 "\n    " = 2 行
    <div class="qv-label">题目</div>
    <div class="q-md" …>…</div>
  </section>                ← 前后各一段空白 = 4 行
  </div>
```

合计 10 个空行 × `.82rem × 1.7 ≈ 22.3px` ≈ **223px**，而预览框 `max-height` 只有 240px——题面被挤到框底还要滚动，「题目」标签上方有约 89px 空白。这与题目内容无关，所有卡片完全一致。

修复只动样式，不碰 `qview.js`：

```css
.gallery-preview .qv{white-space:normal}
[data-theme="dark"] .qv-bare .q-md{background:transparent}
```

第一条关掉 qview 子树继承来的 `pre-wrap`；正文自己的 `.qv .q-md` 单独声明了 `white-space:pre-wrap`，直接命中元素，优先于继承，所以题目里的换行照常保留。`recommend.js` 的画廊仍走 `renderMdContent()` 老路径、DOM 里没有 `.qv`，不受影响，其容器上的 `pre-wrap` 保留。

第二条是同一处的另一个 bug：`bare:true` 本意是给缩略卡去掉正文的边框底色，但深色主题的 `[data-theme="dark"] .qv .q-md`（三个类）权重高于 `.qv-bare .q-md`（两个类），把底色又加了回去，缩略卡看起来像「卡中卡」。

### 题目 Modal（双栏 + 翻页）

`omrs_dashboard.html` 原来的 `#modal-title` / `#modal-meta` / `#modal-body` / `#modal-notes` / `#modal-answer` / `#modal-hist` 六个节点，由 `.qv-nav` 翻页条 + 单个挂载点 `#modal-stage` 取代；`.modal-wide` 放宽到 `min(1180px,94vw)` / `88vh`。

`viewQ(uid, context)` 的第二个参数是可选的翻页上下文，可传 uid 数组，也可传 `qvSetContext()` 登记过的上下文名；不传就退化成单题，行为与改版前一致。现有上下文：`'q'`（题目库表格 + 画廊，按当前筛选结果）、`'export'`（导出选题器）、`'export-selection'`（已选导出列表）、`'leech'`（数据复盘的顽固题 + 屡练不熟表）。

`Esc` 关闭（`app.js` 既有监听），`←/→` 翻页（qview 自己监听，Markdown 编辑器打开时让位）。`#md-editor` 的 `z-index` 由 999 抬到 1000，否则从 Modal 里点「编辑 Markdown」会叠在同层；`saveMarkdownEditor()` / `suspendQuestion()` / `resumeQuestion()` 成功后追加 `qvInvalidate(uid)`，让底下的 Modal 或反馈舞台同步刷新。

---

## 3. 筛选控件（`filterItems()`）

全局筛选，题库页、调度页和即时练习页共用：

| 控件 | 对应字段 |
|---|---|
| 搜索词 | UID / 科目 / 分类 / 标签模糊匹配 |
| 科目 | `subject` |
| 分类 | `category` |
| 状态标签 | `tag` |
| 知识标签 | `knowledge_tags` |
| 难度上下限 | `difficulty` |
| 熟练度上下限 | `mastery` |
| 排序 | 多种排序方式 |

### 3.1 用户标记筛选

`filterItems()` 额外接受 `labels: string[]` 与 `labelMode: 'any'|'all'`。
全文搜索同时匹配标记名；`any` 为命中任一标记，`all` 要求全部命中。题库、推荐、
导出选题、即时练习和展示板添加题目都复用这份筛选语义。

### 3.2 题库页（`assets/qtable.js` + `assets/questions.js`，v1.14.0）

`#panel-questions` 一张 `.qb-card`：常驻工作栏只有搜索（`/` 聚焦）、「筛选」按钮（带激活
条件数徽标）、排序下拉、表格/画廊切换和「列 / 密度 ▾」菜单；下方计数条是四个可点的快捷
筛选（逾期 / 待攻克 / 顽固题 / 停用）+ 总数与显示数；再下方是激活条件 chips（每个可单独 ✕，
标记条件直接显示芯片）。

右侧 `#qb-drawer`（340px，sticky；窄屏时折到列表上方）承载高级条件：科目 / 分类 / 知识点下拉、
标记芯片（点亮即选）+ 任一 / 全部命中、难度与熟练度**双滑块**（`.qb-dual`：两条 range 叠放，
拖动时只预览命中数，松手才重排）、到期 / 状态 / 题目三组分段按钮（`data-qb-seg` 驱动隐藏的
`select`，所以 `getFilterState('q')` 契约不变）、视图预设。`qbActiveFilters()` 把「用户设了什么」
转成 chips，滑块处于两端或下拉为空都算未设。

默认表格列：勾选、UID / 科目·分类、标记（芯片 + 「＋」直接开 picker）、熟练度、到期、状态、
`⋯`；难度、衰减后、次数、上次复习、EF 可在列设置打开；行密度舒适 / 紧凑。状态列去掉
`状态/` 前缀。**表格的「次数」列保持纯数字**——表格视图不拉题目详情，若也画战绩带会让一屏
几十行各发一次 `/api/question`，故 v1.16.0 的战绩带只做进画廊卡。整行点击进 Modal；`⋯` 菜单：查看 / 加入展示板 / 打标记 / 编辑 Markdown /
迁移分类 / 停用·恢复 / 删除（画廊卡同一菜单）。停用、删除、迁移都用 `uiConfirm / uiDialog`。

批量条（fixed，底部）：加入展示板（`B`，锚定选板浮层）、打标记（`L`，添加 / 移除勾选弹层，可
现场新建）、停用 / 恢复、导出 A4、清空（`Esc`）。键盘：`F` 抽屉、`V` 视图、`↑↓` 行游标、
Space 勾选、Enter 打开。

「列 / 密度 ▾」菜单按当前视图只露相关的一半：表格段是列设置 + 行密度，画廊段是列数、
**战绩带**（`data-qb-streak` → `qbSetStreak()`，v1.16.0，默认开）和显示元数据
（`data-qb-gallery-detail`，默认关），两段共用题面换行与「恢复默认显示」。

列和密度存于 `localStorage`；命名视图把筛选字段、标记、排序、视图、列设置、密度、战绩带与
元数据开关存于 `localStorage('omrs-question-views')`，不上传服务端。

### 3.3 标记组件与接入

`assets/labels.js` 的 `lblChip()` / `lblChips()` 输出 `<=>` 双尖形芯片，三种变体：soft
（默认，淡底 + 同色相钳亮度文字）、solid（原色实底，管理弹层）、print（导出 15px）；尺寸
18 / 20（`lg`）/ 15px。`lblInk()` 按主题钳亮度保证 AA 对比度，`labelFg()` 为 solid 选黑白字。
`openLabelPicker()` 支持搜索、新建、最近标记、键盘 ↑↓ / Space / Enter / Esc，点「完成」保存
（乐观更新 + 回滚）；`openLabelManager()` 提供行内编辑（名称 / 色板 / 调度加成）、合并、删除。
`uiToast / uiDialog / uiPrompt / uiConfirm`（core.js）替代 `alert / prompt / confirm`。v1.16.1 起**全站**都换完了（此前只有题库、标记、展示板换了，app / export / feedback / history / inbox / instant / recommend / reports / schedule 里还剩 35 处原生弹窗）：`alert(x)` → `uiToast(x,{kind:'warn'|'error'})`（文案含「失败 / 无法 / 不支持 / 错误」的走 error）；`confirm` → `await uiConfirm(title,{hint,okText,cancelText,danger})`，多行说明进 `hint`，按钮写动词（「删除」「恢复」「双栏 / 单栏」）；`prompt` → `await uiPrompt`，取消返回 `null` 与原生语义一致。调用点所在函数因此都是 `async`（`history.js` 的 `historyReviewRestoreDirect / historySessionAction / historyStateRestore` 本次改成 async）。新代码不要再写原生弹窗。

标记接入录入表单、收件箱题卡、题库、题目 Modal、反馈、即时练习、推荐、导出、
展示板、数据复盘和仪表盘。数据页显示按标记正确率/平均分，仪表盘显示活动题目的
标记分布；`boardPickerOpen()` 统一处理各页面的「加入展示板」入口，接受单个 UID 或 UID 数组；
`boardQuickAdd()` / `boardChooseAndAdd()` 是它的薄封装，调用点函数名不变。

### 3.4 展示板页（`assets/board.js`）

侧栏「题目库」与「目录」之间的「展示板」Tab。页面是**状态条 + 三栏**：状态条 `#bd-statusbar`、
板列表 `#bd-list`、舞台 `#bd-content`、检查器 `#bd-inspector`。每个区一句话职责——状态条回答
「这叠纸现在什么状态、下一步做什么」，舞台只回答「怎么看」，检查器放所有设置。三条不变量
（舞台里没有设置控件 / 一个设置只有一个入口 / 主行动全页唯一）由 `tests/test_board_regions.js`
守着，完整说明见 `board.md` §3。

**状态条**：板名（双击重命名）、题数与科目分布、纸面状态 chips（`.bd-status-chip`，
paper / new / changed / wait 四种修饰）、一句「为什么」、打印范围分段 `[data-board-modes]`、
唯一主行动 `[data-board-primary]`，以及「下载 HTML」「↻ 重新生成」。文案全部来自纯函数
`boardStatusModel()`，见 `board.md` §4.2。打印范围放在这里而不是浮层里：它决定纸上会多出什么，
改完必须当场在舞台的纸面上看见结果。

**板列表**：`.bd-folder` 是文件夹行，`.bd-folder-body` 用 8px 缩进加一条 `border-left` 发丝竖线
兜住组内的板；空文件夹显示 `.bd-folder-empty` 虚线占位。文件夹名比板名弱一档（`--fs-sm` /
`--fg2`），因为文件夹是结构、板才是内容，视线应该优先落在板上。`⋯` 平时 `opacity:0`，
悬停 / `focus-within` 时出现，`@media(hover:none)` 下常显；它不用 `display:none`，
所以出现时不挤动板数。

**选板浮层 `.bd-picker-pop`**：与 `labels.js` 的 `.label-picker-pop` 同一套浮层语言——同样
body 挂载 + `getBoundingClientRect` 锚定 + 空间不足向上翻、同样的 `keyboard-active` 高亮和
`head / search / options / foot` 结构，只是行里多了「这个板已经有几道」的状态列。传 `anchor`
锚定弹出，不传则加 `.centered` 居中（`fadeUp` 结尾是 `transform:none`，会吃掉居中位移，所以
居中态单独走 `bdPickerIn`）。分组标题 `position:sticky` 贴顶，滚动时始终看得见当前文件夹。
提示符列固定 14px，`↵ / ✓ / ↗` 切换时行内容不位移。行为与键盘见 `board.md` §3.2。

**舞台**：`.bd-stagebar` 一行放视图分段 `[data-board-views]` 与内容操作（添加题目 / 按标记同步 /
排序 ▾ / 清空），纸面视图下 `.bd-pager` 另占一行。每个列表行是一行高的四列网格（手柄 / 序号 /
主内容 / 操作）；「留白」与「详情」平时 `opacity:0`，`:hover`、`.is-selected`、`:focus-within`
或已覆盖过留白（`.bd-gap-view.has`）时才显示，窄屏（≤760px）常显。行里的留白是只读回显
（`[data-board-gap-view]`），点它 = 选中该题并把焦点送进检查器的输入框。

**检查器**：`.bd-ins-sec[data-sec="item|layout|paper"]` 三段，sticky 在右栏。次级设置沿用
`.bd-field` / `.bd-field-row` / `.bd-checks` / `.bd-lock` / `.bd-paper` 这套字段样式。
会随别处改动而变的读数一律挂 `[data-board-live]`（`item-gap` / `gap-lines` / `col-width`），
由 `boardRefreshLiveReadouts()` 统一刷新：拖滑杆时不重建整段 DOM（否则丢焦点），
但继承板级留白的单题读数、列表行与画廊卡的只读回显都要跟着走——同一个数字不能两处不同。
「右侧留白」滑块范围 30%–55%，新建板与缺失配置的默认值为 50%；扣除 24px 间距后，
题栏与手写留白区默认等宽。已有板明确保存的比例继续按原值显示和排版。

**锁定保护纸面，不冻结题目集合：** `boardPaperLayoutChanged()` 与服务端 `update_board` 使用同一边界，增删引用、排序、未印题留白、等值留白不弹重印确认。只有真实版式变化或保留的已印题有效留白变化才调用确认；无纸面不需破坏性确认，取消不改本地设置、不入脏队列、不提交该变更。单独切锁、答案附页以及关闭切割线时的线标签不作废纸面；全局留白仅在影响已印题时触发保护。

统一 picker 的各加题入口由 `boardAddToBoard()` 直接追加，标签同步也直接追加去重；移除、清空、清理缺失/停用、拖拽/键盘/菜单排序保留纸上旧占位。安全操作不授予下一次真实版式修改的确认权限。细节见 `board.md` §4.6；行为覆盖为 `tests/test_board_locked_incremental.js`，隔离 HTTP/Chromium 覆盖为 `tests/smoke_board_lock.py`。

**布局**：`.bd-layout` 是 `200px / minmax(0,1fr) / 268px` 三列网格；≤1180px 检查器
`grid-column:1/-1` 折到底部通栏并取消 sticky，≤760px 整体纵向堆叠。整屏工作台模式
（`.is-workbench`，见 §1.2）下状态条 `flex-shrink:0`，三栏各自滚动。

#### 常驻预览 iframe（`assets/board_preview.js`）

中栏「纸面」视图是一个**常驻**的同源 `srcdoc` iframe，内容就是 `/api/export` 的展示板导出
HTML。常驻而不是每次新建：那份 HTML 内联了将近 1MB 的 KaTeX 字体，重建节点等于重新解码一次
字体。全页只留一个 iframe（`BP_FRAME`），切板换 `srcdoc`。

刷新分三档，**只有第三档走网络**：

| 档 | 触发 | 动作 | 去抖 |
|---|---|---|---|
| 几何 | 留白比例 / 题间留白 / 切割线 | `postMessage` `omrs-board-relayout` | 120ms |
| 内容 | 增删题 / 排序 / 换模式 | 重新拉 `/api/export` | 500ms |
| 切板 | 选了别的板 | 立即拉导出 | — |

导出指纹是 `板 + 模式 + 题目签名 + 纸面时间`（`boardPreviewKey`），**刻意不含
`board.updated_at`**：拖一次版面滑块就会 bump 它，而版面改动本该走 relayout，把它算进指纹
等于每拖一下都重新请求近 1MB 的导出。HTML 缓存只留最近一份（`BP_HTML_CACHE`），
不把几份 1MB 的字符串攒在内存里。

不在前台就不排版：切到别的 Tab、或预览滚出视口（`IntersectionObserver`）时几何改动只记不发，
回来再 `boardPreviewFlushPending()` 补一次。切板时进行中的导出请求会被 `AbortController`
取消，晚到的结果按 `BP_STATE.key` 丢弃。

页数不再单独跑一遍排版估算：翻页条直接读预览已经排好的 `layout`（`page_numbers` / `pages`），
`boardRenderPager()` 只替换 `[data-board-pager]` 这一个节点——整块 `innerHTML` 会把 iframe
卷进去重载。「标记为已打印」同样优先复用预览测出的 layout（板 id 与模式都对得上才采纳），
预览不可用时才回退到隐藏 iframe 测量。

**正文变更如何失效：** 内容签名只覆盖题目集合、顺序、停用 / 缺失状态和纸面时间，
**不覆盖题目正文**。正常路径没有问题——题目 Modal 保存、反馈提交都会走
`reloadData()` → `boardReloadData()` → `boardPreviewInvalidate()`，下一次同步就重新导出。
留下的缺口是「在应用外改了文件」「第三方链路没触发重载」，人工兜底是检视条上的
「↻ 重新生成」（`boardRegenPreview()`，清缓存后强制重新导出）。

续印预览的几何以本次导出初始化时的纸面快照为准：`mode:"new"` 从 `printed.print` 读取原纸的
`note_ratio / gap_lines`，常驻 iframe 收到 `omrs-board-relayout` 时也继续使用这份快照。宿主当前
设置的比例不会覆盖已打印锁定纸面；只有重新打印全部才会生成新的整板几何。

#### 保存队列：按字段记脏、合并成一次 POST

行内留白与版面滑块曾各自持有同一个 `BOARD_SAVE_TIMER` 并互相 `clearTimeout`，
「先改留白再拖滑块」会把前一次改动整个丢掉。现在改成按字段记脏
（`boardDirtyMerge` → `{items?:true, print?:true}`），到点由 `boardSavePayload()`
合并成**一次** `POST /api/board/update`——后端本就支持同一请求里同时收 `items` 与 `print`，
且会用请求后的全局留白去折算 v2 的 `extra_gap_lines`。

三个落盘时机：去抖 500ms；离开展示板 Tab 前（`click` 捕获阶段跑在 `switchTab` 之前）；
关页 / 刷新时用 `navigator.sendBeacon` 交给浏览器后台发送同一份 payload。
保存失败不丢脏标记，下次改动会再试。

#### 视图与每题留白

舞台是「纸面 / 列表 / 画廊」三段（`[data-board-views]`），选择存
`localStorage['omrs-board-view']`。画廊按题目缩略展示板内题面，列表行、画廊卡和检查器的
「打开题目」都调用统一 `viewQ()`。收件箱中状态为「已录入」的条目点击后也直接打开题目详情。
换视图只换呈现：三个视图下状态条与检查器都在原处，能做的事完全一样。

检查器里的留白输入框留空 = 继承板的全局设置（`placeholder` 显示继承成几行），填数字 = 覆盖成
**绝对行数**（0–48）。`boardItemsPayload()` 原样把 `null` 传回后端，否则会被当成 0 行，
留白一保存就退化成「不留白」。`boardEffectiveGap()` 与服务端 `effective_gap_lines()` 必须同解。
`boardSetItemGap()` 是唯一写入口，列表行与画廊卡上的数字只读。

打印范围两种：**打印全部**（整板从第 1 页排）与**仅新增**（只有纸面记录存在时可选：
新题接在纸面 `cursor` 所在页的空白处续排，需要新页时用绝对页码 `pages+1`）。范围分段在状态条上，
改完纸面当场重排。「✓ 记录纸面」优先复用常驻预览测出的版面（板 id 与模式都对得上才采纳），
预览不可用时才把同一份导出 HTML 放进隐藏 iframe 测量（`boardMeasureLayout`），
再 `POST /api/board/printed`；打印预览窗口的「已打印，记录纸面」通过
`postMessage('omrs-board-printed')` 触发同一流程。常驻预览里那份导出的顶栏动作条已由
`embedded` 收起，不构成第三个入口。

打印预览（v1.14.1 起）必须**先同步 `window.open('', '_blank')` 拿到窗口、写入占位提示，再
`await` 导出**，最后 `preview.location.replace(blobURL)` 填入内容：浏览器只在用户手势的同步
调用栈里允许开新窗口，先 `await` 会让手势过期而被拦截（板子越大越明显，Safari 尤其严）。
`location.replace` 不换窗口对象，`BOARD_WINDOWS.get(event.source)` 的回传不受影响；导出失败
时关闭占位窗口。纸面记录可重置。快捷键：`N` 新建、`A` 添加、`P` 预览、`↑↓` 选行、`Ctrl/⌘+↑↓` 排序、
Enter 打开、Delete 移除。完整设计见 `board.md` §3 与 §4。

---

## 4. 复习调度工作台（`assets/recommend_v2.js` / `assets/schedule.js`）

> 新增于 2026-05，替代旧版”直接塞题”流程。

### 入口与状态

复习调度页直接进入「安排复习」工作区，并在顶部并列显示「已有计划」及待完成数量。推荐在页面加载时自动读取；没有候选题时提示已有计划入口。全题库导出仍可从调度页进入，导出面板提供返回调度入口。

### 安排复习

`GET /api/recommend?due_count=1000&prof_count=1000` 默认加载全部可安排候选。列表保留后端返回顺序：到期题按到期优先，熟练度题按统一优先级；均衡模式在各科目间轮选，其他模式按到期/熟练度来源排列。每题显示来源、到期原因、科目、分类、难度和熟练度，并可打开题目预览。

顶部保留科目、搜索和推荐方式；更多筛选折叠包含分类、知识点、状态、到期范围、难度、熟练度、排序和标记匹配。筛选条件以 chips 显示并可单独移除，筛选刷新不会清空已选题；「只看已选」与选择栏会提示被筛选隐藏但仍会加入计划的题目。建议题量默认为 10，可编辑；按建议选择替换当前选择，也可以逐题勾选或全选当前结果。

生成计划会把全部已选题以 `persist:true` 提交，成功后自动切换到已有计划、打开新计划详情并刷新推荐；请求失败保留选择并显示错误。加载请求用序号丢弃过期响应，错误状态提供重试。

计划列表和详情请求也带请求序号：较早的网络响应不能覆盖后来选择的计划；列表加载失败提供重试，详情 404/网络错误在当前详情区域提供重试。安排/已有计划页签支持点击、左右方向键以及 `Home`/`End`，焦点跟随当前页签。调度工作台在窄屏把候选行折成两行网格，保留原因、熟练度和预览按钮，390px 宽度不产生横向溢出。

### 已有计划

已有计划页支持待完成、已完成、全部筛选和编号搜索。列表显示计划状态、题量和反馈进度；详情显示题目、进度、预览、导出和跳转反馈入口。刷新后计划列表与详情保持可见，完成状态来自 Session 数据而不是页面临时状态。

计划详情提供「删除调度」，待完成与已完成计划均可删除。确认框说明关联反馈也会撤销并重新计算熟练度和复习日期，题目正文保留，历史记录可恢复 Session。前端调用 `/api/session/delete`，校验 `status` 与 `deleted` 后清除当前详情及关联反馈表单、刷新列表/待完成数量/推荐和题目缓存；删除失败保留详情并提示重试。同一计划在确认与请求期间阻止重复删除，删除前发出的列表和当前详情响应不能重新显示已删除计划。

推荐优化面板（`assets/recommend_v2.js`）的筛选状态和筛选函数使用 `recV2GetFilterState()`、`recV2FilterItems()` 私有命名。`core.js` 的 `getFilterState()` / `filterItems()` 是题库、展示板、导出和即时练习共用契约，不应由推荐面板覆盖。

### 列表 / 画廊视图

候选区提供「列表 / 画廊」切换。列表视图一行一道题，显示 UID、科目、分类、难度、来源原因和熟练度；画廊视图将同一批候选呈为卡片，并保留勾选、来源原因、熟练度和题目预览。切换只改变候选区的呈现，不重新加载推荐、不清空筛选条件或已选题目。

视图偏好保存在 `localStorage['omrs-schedule-view']`，页面再次进入时恢复 `list` 或 `gallery`，未知值回退列表。画廊卡的题面预览复用共享 qview：调用 `qvRender()`，以 `QV_CARD_OPTS` 为基础并使用 `clamp:8`，只显示题面，不渲染答案；图片、公式和 Markdown 沿用 qview 的安全渲染。预览节点通过 `IntersectionObserver` 懒加载，浏览器不支持观察器时直接加载全部卡片。预览失败沿用 qview 的降级与重试状态。

画廊在桌面端使用自适应卡片网格，≤760px 收为单列；卡片内部的题面预览有独立滚动和高度上限，长题不会撑开整个页面。

### 来源标记

每道题携带 `_source` 字段（`due` / `proficiency`），在反馈时决定 SM-2 排期策略：
- `due`：到期来源 → 标准 SM-2 全量更新
- `proficiency`：熟练度来源 → 答对时间隔 × 0.7 折中

调度页的新页面始终传 `persist:true`，因此即使只选 1 题也创建正式 `EXP-` Session；旧调用不传该字段时仍保留单题 `TMP-` 兼容行为。

---

## 5. 即时练习

入口 Tab：`即时练习`；面板 `#panel-instant`；脚本 `assets/instant.js`。

流程：
1. `GET /api/recommend` 按算法取双列表推荐，可传 `subject` / `category` / `knowledge_tag` 筛选。
2. 前端合并到期列表与熟练度列表，按数量上限形成 `INSTANT_QUEUE`，不调用 `/api/confirm-schedule`，不写 `sessions.csv`。
3. 每题在线拉 `/api/question?uid=...`，先显示题面，点击后显示答案与备注。
4. 用户判对/错并给 0-10 主观分，结果存在 `INSTANT_RESULTS`。
5. 「提交已判定」调用 `POST /api/feedback`，`session_id` 使用 `IMM-YYYYMMDDHHMMSS`，只写历史与 mastery 更新，不创建调度 Session。

即时练习复用 `process_feedback()` 的熟练度、EF、SM-2 更新逻辑。**v1.10.0 起题面 / 答案 / 备注块由 qview 渲染**（`instRender()` 内 `qvRender('#inst-qv', uid, {reveal:row.revealed, showHistory:false, actions:['edit'], onReveal:instReveal})`），原 `.instant-block` / `.instant-md` / `.instant-notes` / `.instant-answer-locked` 及其样式已删除，未翻答案时不再渲染答案 DOM，题卡内也多了「编辑 Markdown」入口。`instRender` / `instGo` / `instReveal` / `instSetVerdict` / `instSetScore` / `instSubmitPractice` 的签名与 `/api/recommend`·`/api/feedback` 流程均未改。

即时练习页是 `.inst-work` 网格工作台（v1.5.0 起），用 `grid-template-areas` 排布四块，DOM 顺序固定、靠 CSS 在窄屏重排：`#inst-summary`（进度 + 提交按钮，按钮由 JS 渲染在块内）/ `.inst-queue-wrap`（队列）/ `.inst-main`（题卡）/ `#inst-submit-results`（提交结果）。

- **桌面**：左题卡（1fr）+ 右栏（进度+提交置顶 → 队列竖列 → 提交结果）。
- **移动端（≤900px）**：顺序改为 进度+提交 → 队列 → 题卡 → 结果。队列变成横向圆点条（`.instant-queue` flex-row 横滚，`.instant-qbtn` 隐藏 `.instant-qmain`、只留 `.qn` + `.qmk`，点按跳题）；评分 `.instant-grade` 竖排整行（`.fb-toggle` 占满，主观分滑杆单独一行，无写死 `min-width`）；导航 `.instant-nav` 2 列网格（「下一道未判定」整行，上/下各半）；题头 `.instant-head` 竖排；筛选 `.inst-filters` 2×2 网格全宽，题数带可见标签 `.inst-count-field`。
- **逻辑层不变**：`instant.js` 的 `#inst-*` id、`instLoadPractice` / `instGo` / `instReveal` / `instSetVerdict` / `instSetScore` / `instSubmitPractice`，以及 `/api/recommend` → `/api/feedback` 流程都只和骨架的 id 绑定，改版式不用动 JS。
>
> **同日修订**：① 桌面右栏队列会随题卡高度变化而上下漂移 / 看似居中——`.inst-work` 由 `grid-template-areas` 改为显式列/行 + 末尾 `1fr` 空行吸收题卡多出的高度，队列改为稳定贴顶；移动端 `.inst-work` 改 `display:flex` 竖排（DOM 顺序天然即 进度→队列→题卡→结果）、`align-items:stretch` 占满宽，筛选项加 `min-width:0` 让 2 列等宽、题数标签 `white-space:nowrap`。② 深色「反转题图」失效——旧规则错指 `.instant-qmain img`（队列项无图），改为正确的 `.instant-md img` / `.instant-notes img`（题面 / 答案 / 备注图）。

---

## 5.1 反馈录入工作台（`assets/feedback.js`，v1.10.0；答题卡导入 v1.11.0）

入口 Tab：`反馈录入`；面板 `#panel-feedback`。复习调度页只保留推荐与导出，Session 历史和反馈表卡片已移除；Session 选择、题目判定和提交集中在这个独立工作台中。骨架与即时练习的 `.inst-work` 同源，复用三栏布局和移动端重排规则。

### 布局

```
┌────────────────────────────────────────────────────────────────────┐
│ [Session ▾] 已录 3/12·剩 9 [🔄 刷新] [📋 读剪贴板填写] [＋ 添加行]   │
├────────────┬──────────────────────────────────┬────────────────────┤
│ ① .fb-rail │ ② .fb-stage（qview split）        │ ③ .fb-panel        │
│  题目列表   │  题目 | 答案 / 备注 / 做题记录     │  判定 · 统计 · 提交 │
└────────────┴──────────────────────────────────┴────────────────────┘
```

- 宽屏工作台：`236px / minmax(0,1fr) / 300px`；在 `.content.is-workbench` 下 rail、题目 stage 和判定面板均为独立滚动区域，`position:static`，不再依赖整页滚动时的 `position:sticky`。
- ≤1160px：判定面板落到底部通栏并吸底。
- ≤820px：三栏塌成竖排，rail 转横向滚动条并隐藏 `.fb-railmain`（只留序号 + 状态点），做法与 `.instant-queue` 一致。

### rail 显示**全部**题目，不只是待录入的

只渲染 `pending_uids` 是「切换太多次」的隐形推手——用户看不到已录的题录成了什么，也没有 Session 全貌。`fbRailEntries(session, rows)`（纯函数，已导出可单测）改为渲染 `sessionUniqueUids(session)` 全量：

- **序号沿用 Session 原始顺序**（`fbSessionPositions()`，v1.8.2 明确修过的行为，不能回退）。
- 已录入的行 `.is-done` 置灰 + `✔`，可点击查看题目内容，但判定面板显示只读提示，不可编辑。
- 待录入的行按 `fbRows[i].correct` 显示状态点：`✓` / `✗` / 当前高亮 / `○` 未判。
- 导入或手动添加、但不属于本 Session 的行追加在列表末尾（`entry.extra`），判定面板为其显示可编辑的 UID 字段。

**这不需要改 `fbSessionProgress()` 的返回契约**——它本来就同时返回 `feedback_uids` 和 `pending_uids`，渲染层多读一个字段即可，`tests/test_feedback_ui.js` 保持绿。

### 渲染层拆三块，停止整块 innerHTML

```js
fbRenderRail()      // 只重绘题目列表
fbRenderPanel()     // 只重绘右侧判定面板
fbRenderStage()     // 只在当前题变化时调用 → qvRender
renderFb()          // 三者依次调用；名字保留，兼容既有调用点
```

`renderFb()` 这个名字必须保留，`onFbSessionChange` / `importFeedbackJson` / `addFbRow` / `submitFb` 都在调它。点「对 / 错」只走 `fbPatchRailRow()`（就地改一行的 class 与状态点）+ `fbRenderPanel()`，题目 DOM 与 KaTeX 不重渲染；`FB_STAGE_UID` 记录舞台上正在显示的 uid，相同则跳过重绘。

判定面板内的控件全部走 `data-fb-act` 事件委托（`fbBindPanel()` 在 `#panel-feedback` 上绑一次），rail 行走 `data-fb-go="<下标>"`；不再把函数名和下标拼进行内 `onclick`。

### 状态与快捷键

- 游标 `FB_CURSOR` 是 rail 条目下标，每次渲染前经 `fbSetCursor()` 夹取，切 Session / 导入后自动定位到第一道未判定题。
- 分数默认值随判定走：用户没手动拖过时点「对」置 9、点「错」置 4（与 `importFeedbackJson()` 的 `correct?10:4` 同一心智）；拖过之后 `row.scoreTouched=true`，不再自动改。
- 快捷键（`fbHandleKey`，仅在本面板激活、Modal / Markdown 编辑器未打开、焦点不在输入控件时生效）：`J`/`↓` 下一题、`K`/`↑` 上一题、`1` 判对、`2` 判错、`0`–`9` 设主观分（需已判定）、`Enter` 跳下一道未判定、`E` 打开当前题的 Markdown 编辑器、`⌘`/`Ctrl`+`V` 读答题卡 JSON（见 §5.1.1）、`⌘`/`Ctrl`+`Enter` 提交。面板底部一行极小字提示，不做弹窗帮助。

### 提交结果走弹窗（v1.18.1 起）

提交后的「本次处理结果」明细在 `#fb-result-modal`（`.modal-overlay` + `.modal.fb-result-modal`，与 `#modal` / `#md-editor` 同一套骨架），不在页内。页内只留 `.fb-statusbar` 一行：`#fb-status` 一句小结 + `#fb-result-reopen`「查看本次结果」按钮。

- `fbOpenResults(payload)` 传 `{rows, okCount, total, sessionId, at}` 时记进 `FB_LAST_RESULT` 并弹出；不传参数就是重开上一次的结果，`#fb-result-reopen` 走这条。
- `fbCloseResults()` 只关弹窗，`FB_LAST_RESULT` 留着，所以关掉之后还能再打开；`fbClearResults()` 连结果一起丢并收起重开按钮，用在换 Session（`onFbSessionChange(true)`）与两条导入路径上——上一批结果已经不对应当前这批题了。
- 关闭入口四个：右上 `✕`、底部「知道了」、点遮罩、`Escape`。弹窗开着时 `fbHandleKey` 只认 `Escape` 就 return，`J`/`K`/`1`/`2`/`⌘`+`Enter` 都打不到后面的判定面板，`fbHandlePaste` 同样让路。
- 明细行仍是 `.result-row.ok` / `.err`（与即时练习同一套样式），由 `fbResultRowsHtml(rows)` 生成；`.fb-result-list` 自己滚，头尾不跟着走，所以批次再大关闭按钮也在视野里。

这一条的动因是布局：宽屏 `.content.is-workbench` 下 `.panel.active` 是整屏 flex 列且 `overflow:hidden`，页内结果块会把 `.fb-work` 三栏挤矮，明细多了还会被裁到屏幕外，而它此前只有换 Session 才消失。

### 5.1.1 答题卡扫描 JSON 导入（v1.11.0）

反馈页可把答题卡扫描（OMR）的 `/api/v1/recognitions/<id>/result` JSON 读进 `fbRows`：「📋 读剪贴板填写」按钮、`⌘`/`Ctrl`+`V`、或选择 JSON 文件，三个入口一套解析。协议校验、题号→UID 对应、逐题判定规则见 [`omr-import.md`](omr-import.md)。

### 不变的部分

`fbRows` 行结构只多一个 `scoreTouched` 布尔；`fbRowsForSubmit()` 与提交体 `{uid, sub_score, is_correct, note}` 完全不变；`/api/feedback` 零改动；分批提交与「未判定题保留到下一批」的 v1.8.2 行为不变；JSON 导入与 AI 提示词路径不变。

---

## 6. 临时调度 vs 常规 Session

| 维度 | 自定义练习（TMP） | 常规 Session（EXP） |
|---|---|---|
| 选题方式 | 前端手动筛选勾选 | 双列表推荐 + 勾选确认 |
| 持久化 | 不写 `sessions.csv` | 写入 `sessions.csv` |
| 批次号前缀 | `TMP-YYYYMMDDHHMMSS` | `EXP-YYYYMMDDHHmmss` |
| SM-2 影响 | 反馈同样更新 Interval/Due_Date（无 Session 来源时按 `due` 处理，可逐题传 `source`） | 根据来源差异化更新 |
| 反馈闭环 | 可选 | 必须反馈 |
| 导出方式 | `POST /api/export` 传 `uids` | `POST /api/export` 传 `session_id` |

自定义练习操作（「导出」面板，`assets/export.js`）：
- 选择当前筛选 / 移除当前筛选 / 清空已选（`selectFilteredExportItems` / `clearFilteredExportItems` / `clearExportSelection`）
- 平铺式 / 画廊式切换，每行/卡可单独加入/移除，题目可预览（`viewQ`）
- A4 打印版 / 屏幕版切换（`setExportVariant`）、附带答案、题间留白（`getQuestionGapLines`）
- 导出选中（`doExportSelected` → `POST /api/export` 传 `uids`，批次号 TMP-，不写 `sessions.csv`）

---

## 7. 设置页面（`panel-settings`）

位于「设置」标签页，包含以下功能卡片：

### 外观（主题 / 题图反转 / Ledger 时区）
- `浅色 / 深色` 分段开关 `#st-theme-switch`（`setThemeMode()`）写 `localStorage('omrs-theme')` 并切 `<html data-theme>`；当前首帧脚本在没有保存值时选择**深色**，但设置页帮助文案仍写“默认浅色”，两者尚未同步。
- 「深色模式下反转题目图片颜色」`#st-invert-img`（`setInvertImg()`）写 `localStorage('omrs-invert-img')` 并切 `<html data-invert-img>`；仅在 `[data-theme="dark"][data-invert-img="1"]` 时对题图 `img` 应用 `filter:invert(1)`（简易白↔黑）。
- `#st-ledger-time-zone` 可选「跟随浏览器」（默认）、中国标准时间、UTC 和若干常用 IANA 时区；`setLedgerTimeZone()` 将选择写到 `localStorage('omrs-ledger-time-zone')`，立即重绘 Ledger 时间线和仪表盘最近动态。`formatLedgerTime()` 只转换带 `Z` 或 `±HH:MM` 偏移的时间戳；没有偏移的旧记录保留原有墙上时间，避免无依据地猜测来源时区。
- `syncThemeControls()` 与 `syncLedgerTimeZoneControl()` 由 `loadSettings()` 回填控件状态。外观和时区状态仅存浏览器 localStorage，**不入 config.json / Ledger**，故无需重启。

### 服务设置
- **允许外部访问**：开关绑定 `config.allow_external`。
  - 关闭（默认）：服务器绑定 `127.0.0.1`，仅限本机访问。
  - 开启：服务器绑定 `0.0.0.0`，局域网/公网可访问。
- **保存并重启**：先 `POST /api/config` 保存配置，再 `POST /api/restart` 触发重启。前端在请求成功后延迟 2.5 秒自动刷新页面。
- **立即重启**：直接调用 `POST /api/restart`，不修改配置。
- **数据备份**（卡片下半，`数据备份` 分隔区；**v1.5.0 起从「优化」卡移到这里**，导出/导入函数不变，仅 DOM 位置与状态元素变化）：
  - **导出备份**（操作卡 `#svc-a-export`）：`exportOptimizeBackup()` → `POST /api/backup/export`，复用 `downloadExportResponse()` 下载 `OMRS-backup-YYYYMMDD-HHMMSS.zip`，并把响应头 `X-OMRS-Backup-Token` 存入 `OPT_BACKUP_TOKEN`（v1.5.0 起仅作记录，压缩不再依赖它）。
  - **导入备份**（操作卡 `#svc-a-import` → 触发隐藏 `#opt-import-file`）：`importOptimizeBackup()` 用 `multipart/form-data` 调 `POST /api/backup/import` 预览（文件数/大小/Markdown/图片），二次确认后 `POST /api/backup/restore {restore_id, confirm:true}` 覆盖恢复并 `reloadData()`。
  - 状态写 `#svc-backup-status`。

重启期间前端预期连接中断，catch 后不报错，继续等待刷新。

### AI 自动识别
- 字段：`#st-ai-base`（API 地址，OpenAI 兼容，如 `https://api.openai.com/v1`）、`#st-ai-key`（API Key，密码框 + `#st-ai-key-toggle` 显隐切换）、`#st-ai-model`（模型名，带常见模型 datalist）、`#st-ai-restrict`（复选框「仅从已有知识点中选择」，对应 `config.ai_restrict_tags`，默认勾选）。
- **保存 AI 配置**：`saveAiSettings()` → `POST /api/config {ai_base_url, ai_api_key, ai_model, ai_restrict_tags, ai_model_detect, ai_model_extract, ai_model_classify}`。后三个字段分别覆盖收件箱框选、转文本和分类模型，留空时回退 `ai_model`。**不重启**（`load_config` 每次读盘，保存即生效）；状态写入 `#st-ai-settings-status`。
- `loadSettings()` 进入设置页时一并回填四项（与 `allow_external` 同批 `GET /api/config`；`#st-ai-restrict` 按 `cfg.ai_restrict_tags!==false` 置勾，即默认开）。
- `ai_restrict_tags` 开关含义：开启时 `classify` 的知识点被后端硬过滤为「已有分类 ∪ 已有知识点」；关闭时允许 AI 在无贴切已有项时新建知识点（仍优先复用，上限 4 个）。仅影响知识点，**科目/分类一直允许新建**。
- 仅作配置入口；实际识别在「录入题目」页触发，调用 `POST /api/ai-recognize`（后端转发，见 api.md）。

### 优化（存储概览 + 图片压缩）
- 进入设置页 `loadSettings()` 调 `GET /api/optimize/summary`，`renderOptimizeChart()` 渲染：① 顶部「存储概览」标题 + 副标题状态（刚刚更新 / 扫描中… / 压缩中… / 快扫完成，由 `updateOptimizeControls()` 据 `OPT_JOB_TIMER`+`OPT_SCAN` 推断）+ 右侧总占用大数（`#opt-total`，取 `optValues()` 的 `center`）；② 三张**指标卡** `#opt-m-data/-files/-images`（写 `opt-l-/v-/d-/b-*`：标签取自 `item.label`、值 `formatBytes`、明细=文件数+note、卡底 3px 比例条按 `item.color`）；③ 一条**堆叠比例条** `#opt-seg-data/-files/-images` + 图例；④ 依赖 pill `#opt-deps`（Pillow / jpegtran / 题图总量）。**v1.5.0 起删除环状图**（信息密度低；连同引线 / `renderOptimizeCalloutLines` 一并移除）。
- **扫描图片**（操作卡 `#opt-a-scan`）：`scanOptimizeImages()` → `POST /api/optimize/scan` 起快扫 job，`startOptimizeScanPolling()` 轮询 `GET /api/optimize/job?id=`；进度区 `#opt-progress`（**固定占位**、无任务 `display:none`，不再 pop-in）显示已扫描/总数，`#opt-m-images` 加 `.scanning` 暖色高亮，完成后第三张卡标签切「可压缩大小 / 待深扫图片」。
- **确认压缩**（操作卡 `#opt-a-compress`）：`updateOptimizeControls()` 在「Pillow 可用 + 快扫有候选」时解锁——**v1.5.0 起不再要求先导出备份**。`confirmOptimizeCompression()` 仍弹**二次确认**（提示会改写图片、可先到「服务设置 → 数据备份」导出），随后 `POST /api/optimize/compress {scan_id, backup_token, confirm:true}`（`backup_token` 允许为空：后端 `start_compression` 已去掉令牌强制校验，只保留 `confirm`），`startOptimizeJobPolling()` 轮询进度/已节省，结束后 `loadOptimizeSummary()` 刷新。
- 扫描/压缩结果状态写 `#opt-status`；备份状态写 `#svc-backup-status`（在服务设置卡）。全局 `OPT_SUMMARY/OPT_SCAN/OPT_BACKUP_TOKEN/OPT_JOB_TIMER` 保留语义不变。

### 运行状态 / 关于
- **运行状态**：进入设置页时 `loadSettings()` 会额外调用 `GET /api/status`，在卡片中展示版本号、已运行时间、托管题目数、服务状态和 vault 路径；「刷新状态」按钮可手动重新读取。
- `GET /api/status` 还返回 `workspace_scan`，用于判断最近一次后台/手动自检是否发现冲突。
- **关于**：展示项目基本信息（入口文件、前端文件、数据目录）和重启提示。

### 工作区扫描
- 原「扫描」按钮继续走 `/api/scan` 兼容入口。
- 后端服务启动后也会立即扫描，并每 10 分钟后台扫描一次。

---

## 8. 历史记录页

历史页现在读取 `/api/history` 的 Ledger commit，而不是只显示 `history_log.csv` 表格。

- 视觉结构为竖线时间线：旧节点在上方，最新节点在底部，进入页面后自动滚到底部；主时间线只展示非修正、且**当前未被撤销**的节点。
- **节点按 commit 族着色（v1.2.0）**：`renderHistoryNode` 调 `historyCommitFamily(commit_type)` 给节点加 `fam-review/fam-session/fam-question/fam-system` 类——圆点和 commit 类型标签据此取 `--fam-*` 色。`review.batch_submit` 节点额外由 `historyReviewVisual()` 渲染「对错配比条 + 每题色块」（对=`--green`、错=`--red`、已撤销=`--bg4`），不展开即可看出本批练习结果。
- 顶部提供排序选择：`旧 → 新（最新在底部）` 或 `新 → 旧（最新在顶部）`，选择会保存在浏览器本地。
- 顶部提供「修正模式」开关：默认关闭，主节点只读；开启后才显示 `修改 / 撤销 / 还原` 操作面板，避免日常浏览时误触危险操作。
- 顶部提供「修正记录」按钮：`review.replace`、`review.retract`、`review.restore`、`session.retract`、`session.restore`、`state.restore` 等修正节点从主时间线移出，集中在该列表里查看。
- **被撤销的节点从主时间线隐藏**：优先使用 `/api/history` 返回的完整链 `retraction_state`；旧响应则回退到前端按 seq 顺序重放 `session.retract/restore`、`review.retract/restore`（前端函数 `historyRetractionState`）。`session.create` 整个 Session 被撤销、或 `review.batch_submit` 批次内所有反馈都被撤销（或其 Session 被撤销）时，该主节点（`isNodeRetracted`）不再显示，状态栏提示「N 个已撤销已隐藏」。Ledger 底层仍保留全部 commit，不做删除。
- 隐藏的节点可在「修正记录」面板恢复：被撤销且**当前仍处于撤销态**的 `session.retract` / `review.retract` 修正行带「恢复」按钮（`correctionRestoreButton`），点按调用对应 restore API 追加新 commit，节点随即回到主时间线。
- 每个节点显示时间、题目优先摘要、副标题、commit_id、source、seq 和 commit_type；`formatLedgerTime()` 将带时区偏移的 Ledger `created_at` 按设置页时区显示，仪表盘最近动态复用同一格式化函数；`review.batch_submit` 标题优先展示 UID（单题直接显示题目，多题显示前几题），副标题再显示有效题数、对错和已撤销条数。
- 节点默认只显示头部数据；下方挂只读 `查看详情` 折叠块。开启修正模式后，再额外显示默认关闭的 `修改 / 撤销 / 还原` 操作折叠块。
- 无可操作内容的节点（如 `legacy.bootstrap`、外部扫描类）**不显示**操作折叠块，只保留 `查看详情`。
- `legacy.bootstrap` 等大 payload 会在「查看详情」里做摘要/截断，避免页面被完整迁移数据撑爆。
- 操作折叠块内的面板：
  - `review.batch_submit`：选择批次内某条反馈，执行修改、撤销、恢复。
  - 含 `session_id` 的节点：撤销整次 Session 或恢复 Session。
  - 非 genesis 节点：追加 `state.restore`，还原结构化状态到该 seq。
- 所有按钮都调用历史修正 API 追加新 commit，不会修改旧节点。

---

## 9. 录入题目页（`panel-create`）与提交后表单状态

> 脚本分布：表单提交 `doCreate` / 重置 `resetCreateForm` 在 `assets/schedule.js`；科目/分类 datalist `populateCreateLists` 在 `core.js`；**图片处理、AI 识别、AI 设置、运行状态加载**在 `assets/app.js`；题目图与答案图分别暂存在全局 `CR_Q_IMAGES` / `CR_A_IMAGES`（`CR_IMG_SEQ` 为自增 id）；通用工具 `parseLooseJson` / `copyTextToClipboard` / `looseBool` 均在 `core.js` 声明；反馈页 JSON 导入 `importFeedbackJson` 与 AI 反馈提示词 `copyFeedbackAiPrompt` 在 `assets/feedback.js`。

> **布局重设计（v1.5.0，双栏工作台）**：原「左卡＝整张表单 / 右卡＝使用说明」改为**双栏工作台** `.cr-workbench`（≤900px 转单列）：**左栏「截图工作区」**`.card` 放两个截图区（题目 / 答案，中间 `.cr-div` 发丝分隔 + `.cr-tip` 提示），**右栏「题卡内容」**`.card` 放结构化字段。顶部 `.cr-steps` 编号步骤条（截图→识别→核对→保存——真序列才编号）；底部 `.cr-actionbar` 横跨双栏，含「重置」（直接调既有 `resetCreateForm()`）+「创建题目」（`#cr-btn`）与一行静态保存说明，`#cr-result` 紧随其后；原使用说明 / 文件结构树收进底部折叠块 `<details class="cr-help">`。右栏的科目 / 分类 / 难度 / 相关知识点包进 `.cr-aigroup` 卡片（标题「🤖 AI 自动填充 · 可改」，提示这组可被识别自动填、且可改）；**错因** `#cr-cause` 独立成暖色块 `.cr-cause`（`--trap-bg` 微染 + `.cr-flag` 赭色旗标 + 「复习时先看这里」脚注，作为错题本的核心字段）。**纯样式 + 结构改动：所有 `#cr-*` 元素 id、内联处理函数、`doCreate`/`crClassify`/`crExtractAnswer`/`crSetPasteTarget` 等逻辑与后端接口全部不变。**

录入页有两个图片区（现分列于左栏上下），题目区配两个 AI 按钮、答案区配一个 AI 按钮，可混用手动录入：
- **题目图片区**（`#cr-q-paste` / `#cr-q-file` / `#cr-q-images`）：粘贴/拖拽/点击选择题目截图，随题保存并嵌入 `# 题目`。按钮 **「🤖 识别题目信息」**（`#cr-classify-btn`）→ `crClassify()` 取第 1 张题目图 `POST /api/ai-recognize {mode:'classify', subject, category}`，只回填**科目/分类/难度/相关知识点**（不抄题、不解题）。按钮 **「🤖 提取题目文本」**（`#cr-question-text-btn`）→ `crExtractQuestionText()` 取第 1 张题目图 `POST /api/ai-recognize {mode:'question_text'}`，把题干/条件/选项/图表说明**提取为文本**填入 `#cr-question`；若图片开头带题号（如 `11.`），只去掉该开头题号，选项和正文内部编号保留。其中 `knowledge_tags` 是否限定在「已有分类 ∪ 已有知识点」由设置页 `ai_restrict_tags` 开关决定（默认开=硬约束；关=允许新建，上限 4 个）。**用户已填的科目/分类会作为 hint 传给模型（要求其沿用），且前端只填空缺项、不覆盖已填值；知识点与已填的合并去重；难度给估计值。** 两个题目区按钮共用状态 `#cr-classify-status`。
- **答案图片区**（`#cr-a-paste` / `#cr-a-file` / `#cr-a-images`）：粘贴/拖拽/点击选择答案截图，嵌入 `# 答案`。按钮 **「🤖 提取答案文本」**（`#cr-extract-btn`）→ `crExtractAnswer()` 取第 1 张答案图 `POST /api/ai-recognize {mode:'answer'}`，要求模型忠实保留图片内全部答案、解析、推导和步骤；若开头是对应题号加“答案/解析”等标题，只去掉题号，解析内部步骤编号保留；不得摘要或补写，再填入 `#cr-answer`。也可不提取（答案图直接嵌入）或手动输入。状态写 `#cr-extract-status`。
- 字段分两栏：**左栏（截图工作区）** 题目截图区 + 答案截图区；**右栏（题卡内容）** 自上而下为 `.cr-aigroup`{`#cr-subject` / `#cr-category`（并排）/ `#cr-diff` 难度滑杆 / `#cr-related` 相关知识点（**classify 自动填**，挂 `cr-ktag-list` datalist，由 `populateCreateLists` 填入「已有分类 ∪ 已有知识点」供手动挑选）} → `#cr-question`（题目正文，可留空、手动输入或由 `question_text` 提取）→ `#cr-answer`（答案文本）→ `#cr-cause`（**错因**，`.cr-cause` 暖色块，写入 `# 备注` 的 `## 错因`）→ `#cr-note`（页码）。

图片交互（题目区 / 答案区各一套）：
- **显式读取剪贴板**：每个区下方有「📋 从剪贴板读取到「题目/答案」」按钮 → `crReadClipboard(kind)`（用 `navigator.clipboard.read()`，需 https 或 localhost 且浏览器授权；无图 / 不支持 / 被拒时弹提示）。这是把图读到**指定区**的最可靠方式，解决「想粘到答案却进了题目」。
- **Ctrl/⌘+V 粘贴**：`document` 级 `paste` 监听仅本页激活时拦截图片；落到「当前目标区」——由 `crSetPasteTarget`（点击/聚焦某区、点其「读取剪贴板」时）记录，默认题目区；目标区会高亮（`.paste-active`，并由 CSS `::after` 角标「粘贴目标」始终跟随当前目标区）提示 Ctrl+V 将粘到此；文本粘贴不受影响。
- 拖拽 / 点击选择按区独立（`crHandleDrop` / `crPickFiles` 带 `kind` 参数 `'q'|'a'`）。缩略图带删除 ✕ 与序号（`crRenderImages(kind)`），并据此启用/禁用对应按钮。
- 提交时 `doCreate` 把两区图片分别映射为 `question_images` / `answer_images` 一并发送；成功提示含已保存图片数。

录入页不再提供外部 AI 题目 JSON 导入，也不再维护本地录入队列；外部 JSON 导入只保留在反馈页。

**反馈页「从屏幕版或 AI 导入反馈」**（`panel-feedback` 顶部卡片，`importFeedbackJson` / `copyFeedbackAiPrompt` in `feedback.js`）：
- **屏幕版导入**：粘贴屏幕版导出件「复制作答 JSON」的产物（格式见 `data.md` §11；容忍围栏、接受 `items`/`feedbacks`/裸数组），逐条校验 `uid` 非空、`is_correct` 经 `looseBool` 宽松解析（true/1/"对"…），`sub_score` 缺省按对→10 / 错→4、钳 0–10。
- **AI 导入**：「复制 AI 反馈提示词」会按当前已选 Session / 反馈行生成 UID 清单与输出骨架，让外部 AI 根据纸面批改结果或口述反馈整理为同一份 `omrs-feedback` JSON。导入端兼容 AI 常见别名：`correct` 等价 `is_correct`，`score` 等价 `sub_score`。
- `session_id` 在 `SESSIONS` 中 → 自动选中 picker 并关联；不在列表（如 TMP- 临时卷）→ 仍以该 ID 提交写入历史并在 `#fb-session-info` 说明；无 ID → 按手动录入。填充 `fbRows` 后 `renderFb()`，**不自动提交**——用户核对后点「提交反馈」。误贴旧题目 JSON 时提示当前只支持反馈 JSON。

提交后表单状态：
- 新题目创建成功后，清空全部输入框、两区图片与两处 AI 状态，难度滑块恢复为 5；保留创建成功提示。
  `#cr-result` 的成功提示里带「📋 加入展示板」按钮（调 `boardQuickAdd(uid)`），与收件箱提交后的
  入口一致；`boardQuickAdd` 未定义时不渲染该按钮。
- 反馈提交成功后，清空反馈行和 Session 选择状态；保留处理结果列表，便于核对本次提交。

---

## 9.1 收件箱录入流程（`assets/inbox.js`，v1.12.0）

`#panel-create` 改为顶部 `.ib-flow`：**上传 → 处理 → 录入**（编号真序列）+ AI 训练 + 快速录入；原单题表单整段搬进 `#ib-stage-quick`，所有 `#cr-*` id 与 `doCreate` / `crClassify` 等逻辑不变。新脚本 `assets/inbox.js` 排在 `data.js` 之后、`reports.js` 之前（依赖 `core.js` 的 `api`/`escapeHtml` 与 `questions.js` 的 `renderMdContent`）；`switchTab('create')` 调 `inboxInit()`。样式集中在 `styles.css` 末段，类名全部 `ib-` 前缀；画布标注色 `--ib-role-*` 固定不随主题。粘贴分流：`ibPaste`（捕获阶段）只在上传阶段拦截图片；`crHandlePaste` 只在快速录入阶段生效。设置页「AI 自动识别」新增三个按用途的模型输入框（`#st-ai-model-detect/-extract/-classify`），随 `saveAiSettings` 一起保存。交互细节、job 轮询、沿用框位的像素锚定规则见 `AI/inbox.md` §5。v1.13.0：处理页 / 队列脚 / 批量条加「▦ 模板框选」（`ibDetect(ids, 'template')`，零联网）；「AI 训练」页加盲标评估集与存储概览、清理按钮、以及「框选提供方与自动策略」表单（`.ib-pl-grid`，`ibLoadPolicy / ibSavePolicy` 读写 `/api/config` 的 `inbox_*` 键，与设置页共用同一 config）；大裁图自动改 JPEG。

---

## 10. 数据页（复盘）

> 对应 Tab：`数据`（位于「仪表盘」与「题目库」之间）；面板 `#panel-data`；数据来源 `GET /api/analytics`；导出 `GET /api/export-review`。

进入该页（`switchTab('data')`）触发 `loadAnalytics()`，把 `/api/analytics` 渲染成大量卡片。全部复用既有 CSS（`stat-card`/`bar-row`/`heatmap`/`table`/`tag`），无新依赖。

### 展示区块（`renderAnalytics()`）

| 区块 | 容器 | 形式 |
|---|---|---|
| KPI（两行各 4 张） | `data-kpi`/`data-kpi2` | stat-card：总复习/正确率/连续/leech；平均熟练度/EF/活跃天数/近 30 天 |
| 科目维度 | `data-subject-radar`/`data-subjects` | 雷达图显示各科平均熟练度，表格按最薄弱在前 |
| 分类维度 Top 15 | `data-categories` | 表格 |
| 难度×熟练度密度图 | `data-scatter` | 按（难度 1–10 × 熟练度 5 档）分箱的气泡图：`<circle>` 半径 = 该格题量（`sqrt(count)`，封顶 26）、填色 = 该格平均熟练度（`--red` 低 / `--yellow` 中 / `--green` 高），悬停 `<title>` 显示题量与均值。取代旧的逐点散点（散点只能看大致分布、无法反映题量）；纯内联 SVG，颜色全部走 `var()` |
| 熟练度分布（原始/衰减后） | `data-mastery`/`data-decayed` | 条形图 |
| EF / 难度 / Repetition / Interval 分布 | `data-ef`/`data-difficulty`/`data-repetition`/`data-interval` | 条形图 |
| 各主观分正确率 | `data-score-acc` | 条形图（值显示「正确率(次数)」） |
| 按周正确率（近 12 周） | `data-weekly` | 表格 |
| 按星期复习量 | `data-weekday` | 条形图 |
| 按时段复习量 | `data-hour` | 24 格热力（00–23） |
| 未来 7 天到期预测 | `data-forecast` | 条形图（今日 / +1..+7 / 7天+） |
| 复习预警 | `data-alerts` | 六宫格（逾期/今日/急需/警告/冷落/顽固题） |
| 顽固题 Leech | `data-leeches` | 表格（带「查看」打开题目 Modal） |
| 屡练不熟 | `data-struggling` | 表格 |

### 通用渲染辅助

- `_kpiCard(cls,label,value,sub)`：生成 stat-card。
- `_bars(id,rows)`：rows = `[{label,value,cls,display?}]`，按最大值归一化宽度，复用 `.bar-*`。
- `_tbl(id,headers,rows)`：rows 为二维数组（单元格允许内嵌 HTML）。
- `pctFmt(v)` / `accColor(v)`：百分比格式化与按正确率/熟练度上色（绿≥80%、黄≥50%、红<50%）。
- `by_hour` 的键经 JSON 序列化为字符串，访问时 `bh[h]||bh[String(h)]` 兼容。

### 导出（`exportReview()`）

直接 `fetch('/api/export-review')` 拿 Markdown blob，复用通用下载辅助 `downloadExportResponse()`（其按 `Content-Disposition` 的 `filename*=UTF-8''` 解析出中文名，故对任意文件类型通用）。状态写入 `#data-status`。后端离线时 `loadAnalytics()` 在 `#data-status` 给出「需后端运行」提示（该页依赖实时计算，无 demo 回退）。

---

## 11. 报告页（AI 报告托管）

> 对应 Tab：`报告`（历史记录与设置之间）；面板 `#panel-reports`；脚本 `assets/reports.js`（在 data.js 后、app.js 前加载）。后端见 `omrs/reports.py` 与 api.md 报告端点。

- **创建**：填名称 + 选 `.html` 文件 → `createReport()` 用 `FileReader.readAsText` 读出 HTML 文本，`POST /api/report/create {name, html}`。
- **准备 AI 材料**：创建卡片提供「复制 AI 报告提示词」和「下载分析数据」。`#rp-include-images` 控制是否带题图：关闭时下载 Markdown；开启时请求 `/api/export-review?include_images=1` 下载 Markdown + `images/` 的 ZIP。提示词同步切换图片约束，并要求 AI 只返回可直接上传的完整单文件 HTML、不得虚构数据。报告允许通过 HTTPS 使用外部字体、图表和图标资源，但禁止广告/追踪脚本，并要求依赖加载失败时核心内容仍可阅读。
- **列表**：`loadReports()` 拉 `/api/reports`，`renderReports()` 用 `sched-item` 样式列出（名称 / 创建时间 / 大小 / id）。
- **浏览**：`openReport(id)` → `window.open('/api/report/view?id=...')` 新标签打开。因同源，报告内 `<img src="/api/image?name=...">` 能正常加载题图。
- **删除**：`deleteReport(id)` → `POST /api/report/delete`。
- `switchTab('reports')` 触发 `loadReports()`。

### 报告如何引用题目图片（与后端对接）

AI 生成报告时，对某道题用 `<img src="/api/image?name=<URL编码文件名>">` 即可显示其原图（让人一眼认出是哪道题）。文件名来源：`/api/question?uid=` 或 items 的 `images` 字段、或导出复盘报告 JSON。即使下载了含 `images/` 的 ZIP，该目录也只供 AI 读取，最终 HTML 仍不得引用相对路径、`file://` 或 base64。仅在“由本程序托管 + 在程序内打开”时 `/api/image` 才加载（同源）；脱离服务直接双击本地 HTML 不会显示题图。

---

## 12. 主题与深色对比度（`styles.css`，v1.7.0 修订）

主题切换机制不变（见 §7 外观：`<head>` 内联脚本 + `localStorage('omrs-theme')` + `<html data-theme>`）。本节记录 v1.7.0 为解决「深色下配色显示不明显」所做的两层改动，浅色 `:root` 未改。

### token 层（`[data-theme="dark"]`）

| 变量 | v1.6.0 | v1.7.0 | 原因 |
|---|---|---|---|
| `--bg` | `#1a1916` | `#141311` | 页面底压暗一档，给卡片让出层次 |
| `--bg2` / `--bg3` / `--bg4` | `#211f1c` / `#2b2925` / `#3a3732` | `#211f1d` / `#2e2b27` / `#433f38` | 内层面依次拉开 |
| `--fg` / `--fg2` / `--fg3` | `#ece7df` / `#a39c91` / `#6f685e` | `#f0ebe3` / `#b3aa9e` / `#8f887c` | `--fg3` 原本对 `--bg2` 只有约 3:1，抬到约 4.7:1 |
| `--red` / `--green` / `--yellow` / `--blue` | `#d98a7e` / `#82ab8b` / `#cda35f` / `#7e9bbf` | `#e59a8c` / `#8fbf9a` / `#dcb06a` / `#8fb0d8` | 语义四色整体提亮一档，对 `--bg2` 均 ≥7:1；`--*-rgb` 同步 |
| `--kill/attack/trap-bg` | `.16` | `.20` | 状态 chip 底色需要看得出 |
| `--border` / `--border2` | `.10` / `.17` | `.13` / `.23` | 深色下卡片主要靠描边区分，不能太淡 |
| `--chart-surface` / `--chart-line` | `.035` / `.11` | `.055` / `.17` | 空热力格与坐标网格原本近乎不可见 |
| `--accent-fg` | `#1a1916` | `#17150f` | 跟随新底色 |

`.stat-card` / `.card` 的深色规则由半透明白渐变（`rgba(255,255,255,.045→.024)`）改为**实色 `var(--bg2)` + `--border` 描边 + 更实的投影**；侧栏由 `#161410` 改 `#0f0e0c`。

答案块只有一条规则 `.qv .q-answer-md`，走 `rgba(var(--green-rgb),α)`，深色不需要单独补丁（旧的 `.modal .q-answer .q-md` / `.instant-answer .instant-md` 写死浅绿的规则在 v1.10.0 随 qview 落地删除）。深色「反转题图」的选择器是 `.q-md img` / `.qv .q-md img` / `.gallery-preview img`。

### 规则层：写死浅色的几处

根因是这些规则写死了浅色时代的颜色，token 切深色后它们不跟着走。全部新增为 `[data-theme="dark"]` 覆盖，集中在 `styles.css` 末尾「v1.7.0 深色对比度修订」注释段：

- `.modal .q-answer .q-md` / `.instant-answer .instant-md`：原 `rgba(39,134,74,.04)` 深绿底，深色下等于没有 → 改 `rgba(var(--green-rgb),.10)`，边框 `.30`。
- `.timeline-head .tag.fam-review` / `.fam-session`：原写死 `rgba(47,125,79,.1)` / `rgba(53,106,156,.1)` → 改走 `--green-rgb` / `--blue-rgb` 的 `.18`；`.fam-question` / `.fam-system` 一并改用 token 前景色。
- `.heat-0`～`.heat-4`：空档 `.07` 看不出网格 → `.14`；中间档同步抬；`.heat-3` / `.heat-4` 的白字压浅绿底 → 改深墨 `#17150f`；`.heat-cell` 文字改 `--fg2`。
- `.level-fill` 与 `.bar-fill` / `.chart-fill` 的渐变低位：原停在 `.42` / `.72`，深色下淡进背景让柱子像被截断 → 抬到 `.58` / `.82`（accent 抬到 `.70`）；`.bar-track` / `.m-bar` 轨道改 `rgba(236,231,223,.10)`。
- `.btn.danger:hover`：`color:#fff` 压在浅色语义红上 → 深色下改 `#17150f`。
- 卡中卡（`.instant-md` / `.rec-item` / `.sched-item` / `.picker-row` 等）由 `.04` 抬到 `.07` 并补描边；`.btn` 底 `.05→.07`、hover `.10→.14` 并明确前景色；`.input` 深色底改 `--bg3`；`.img-thumb` 角标底改 `.70`。

**维护约定**：新写深色规则一律走 `var(--*)` 或 `rgba(var(--*-rgb), α)`，不要再写死十六进制或裸 `rgba(r,g,b,a)`；确需固定的深墨字用 `#17150f`（与 `--accent-fg` 同值）。


---
