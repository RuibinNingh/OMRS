# 前端

> 入口：`omrs_dashboard.html`（仅结构）。样式与脚本拆分到 `assets/` 资源文件夹。

无构建步骤。后端与本地前端代码不需要打包依赖；页面运行时外链 Google Fonts，并从 `assets/vendor/katex/` 本地加载 KaTeX 渲染 LaTeX（不可用时降级为可辨识的公式源码片段）。所有图表使用纯 CSS + 内联 SVG 实现。

> **v1.2.0 视觉刷新（精修暖色）**：`styles.css` 的 `:root` 收敛为「编辑式暖色」——卡片去阴影/去 stat-card 顶部彩条、发丝级分隔线。图表条 `.bar-fill.*`/`.chart-fill.*` 以 `rgba(var(--accent-rgb),…)` 淡入主色的渐变填充（见 L500–505 的 `linear-gradient` 段，后者覆盖早期纯色定义）。新增语义族变量 `--fam-review`（复习/绿）、`--fam-session`（Session/蓝）、`--fam-question`（题目/棕）、`--fam-system`（系统/灰），用于时间线圆点、commit 类型标签和仪表盘「最近动态」圆点。`:root` 下方保留一段注释版「夜间账本」深色 token，整段替换即切深色；但仪表盘雷达/热力/趋势图与散点仍有内联浅色需先改用 `var()` 才能正确切到深色。图表内联色尽量走 `var()`（散点已改）。

> **v1.3.0 深色模式 + 现代化**：首次打开且本地没有主题设置时，`<head>` 启动脚本当前选择**深色**；之后由设置页「外观」切换并存 `localStorage('omrs-theme')`。内联脚本在首帧前给 `<html>` 打 `data-theme` / `data-invert-img` 防闪。`:root` 圆角加大（`--radius:14 / -sm:10 / -lg:20`）、恢复柔和阴影 `--card-shadow`、新增 `--accent-rgb`；`[data-theme="dark"]` 为完整深色 token。`dashboard.js`/`data.js` 图表颜色已**全部 token 化**（含 SVG fill/gradient 改 `var()`+opacity），深色可正确显示。深色 + 「反转题图」开启时，`.q-md / .q-body / .gallery-preview / .instant-md / .instant-notes` 内 `img` 套 `filter:invert(1)`（简易白↔黑，彩色一并反相，保色版待后续）。

> **v1.4.0 应用骨架（侧边栏 shell）**：顶部 `<header>` + `.tabs` 横条 → 左侧 `<aside class="sidebar">`（`.sidebar-brand` 品牌 + `.sidebar-nav`）+ `<main class="content">`（`.topbar` 页面标题 + 动作按钮）。导航项**仍是 `.tab[data-tab]` + `onclick="switchTab()"`**，`switchTab` 逻辑不变，只新增：按 `name→中文` 映射更新 `#topbar-title`。图标为 `<body>` 顶部一段隐藏 `<svg><symbol id="i-*">` 雪碧图，导航用 `<svg class="nav-ico"><use href="#i-*"/></svg>`（描边走 `currentColor`，无外部图标依赖）。`modal-overlay` 与 `datalist` 仍是 `.shell` 外的兄弟节点。响应式：≤860px 侧栏转为顶部横向滚动条。

> **v1.4.2 页面内部现代化（首批两页）**：即时练习 `instRender` 题头改「题 N/M + chip + 进度条」、`instRenderSide` 队列项右侧改状态圆点（对/错/当前/未答）；反馈录入 `renderFb` 改卡片行（对/错分段 + 分数滑杆 + 备注 + 按 UID 反查科目分类）并在顶部加实时对错统计条。字段与 `/api/feedback`、`/api/recommend` 接口不变。**侧边栏应用式 shell 为下一独立改动**。

> **v1.5.0 深色主题：暖石墨 Warm Graphite**：早期 v1.5.0 的「玻璃拟态」深色（半透明卡片 + `backdrop-filter` 模糊 + body 四道极光径向渐变 + 紫青 `--grad`/`--glow` 辉光 + 渐变裁切文字）整段下线，改为与浅色同源的「暖石墨」——浅色用近黑墨、深色用骨白墨，互为镜像。`[data-theme="dark"]` token 改为实色暖面（`--bg:#1a1916` 等暖中性梯度）、发丝描边、单色骨白墨：`--accent` 由紫 `#b794f6` 改骨白 `#ece7df`、`--accent-fg` 深墨，故 `.btn.primary` 成「浅底深字」与浅色「深底白字」镜像；语义色由霓虹 400 收成大地色（黏土红 / 鼠尾草绿 / 赭黄 / 灰灰蓝）。删除 `--grad`/`--glow` 与 body 极光、玻璃卡片 / 玻璃侧栏 / 渐变按钮 / 紫色激活态 / 渐变 `.stat-value` 等深色特例，卡片 / 数值 / 进度条 / 品牌块 / 激活态全部回退到 token 驱动（深色覆盖块由约 53 行瘦到 ~16 行）。图表内联色仍走 `var()`，自动跟随。版本号不变（仍 v1.5.0）。

> **v1.7.0 行动推荐 + 目录页 + 深色对比度修订**：① 仪表盘顶部新增「行动推荐」卡（`#action-plan`，在「最近动态」上方），脚本 `assets/actions.js`，见 §1.1；② 侧栏在「题目库」和「复习调度」之间新增「目录」页（`#panel-catalog`，图标 `#i-tree`），脚本 `assets/catalog.js`，数据来自新接口 `GET /api/tree`，见 §2.1；③ `styles.css` 的 `[data-theme="dark"]` token 与若干写死浅色的规则按对比度重配，见 §10。版本号提到 **v1.7.0**（`omrs/version.py` + HTML 侧栏 `v1.7.0 · 本地服务`）。

> **v1.8.2 部分判定提交 + 吸顶概览**：反馈页不再要求本批所有题都先判定；点击「提交反馈」时只提交已经选择「对 / 错」的题，未判定题自动保留到下一批。`fb-tally` 以吸顶“灵动岛”样式显示总数、对/错/未判和进度条，滚动题目时持续可见；每道反馈题增加序号徽标，选择已部分录入的 Session 时仍显示该题在 Session 原始题目列表中的序号，不会因过滤已录入题而从 1 重新编号。HTML 的 `styles.css`、`schedule.js`、`feedback.js` 资源查询参数同步更新，避免浏览器缓存旧交互。

> **v1.8.1 分批反馈交互优化**：`GET /api/sessions` 与 `GET /api/session` 的每个 Session 现在附带 `feedback_uids`、`pending_uids`、`feedback_count`、`pending_count`、`feedback_complete`，按 Session 原始题目顺序去重。反馈页选择 Session 时调用 `fbRowsForSession()` 自动只载入 `pending_uids`，已录入题目不再进入编辑行；顶部显示 `已录入 / 总数` 与剩余题数，Session 列表按钮改为「继续录入」。一次提交成功后保留当前 Session，刷新数据并自动载入剩余题目；全部完成时显示无需重复提交。反馈 JSON 导入同样自动跳过该 Session 已录入 UID，并在状态栏报告跳过数量；手动反馈仍可通过「添加行」使用。

> **v1.9.0 题目停用机制**：题目库支持停用/恢复。停用题目保留 Markdown、题目库管理入口和 Ledger 历史，但不参与复习调度、行动推荐、统计、数据分析、反馈和复习导出；题目库筛选提供活动/仅停用/全部三种口径，仪表盘显示停用数。

## 文件组织（assets/）
```
omrs_dashboard.html   ← 仅 HTML 结构，<link> 引样式 + 多个 <script> 引脚本
assets/
├── styles.css        ← 全部样式（原 <style> 内联块抽出）
├── core.js           ← 全局状态、api()、通用工具/筛选/Markdown 渲染
├── dashboard.js      ← 仪表盘图表 renderDash
├── questions.js      ← 题目库表格/画廊视图 + 题目 Modal + 安全 Markdown/LaTeX/表格渲染 + 原文编辑/迁移/删除/停用恢复入口
├── schedule.js       ← 复习 Session：预览/删除/列表 + 工作区扫描 + 录入提交（doCreate/resetCreateForm）；旧「新建 Session」（createSession/POST /api/schedule）UI 入口已随推荐面板移除，端点保留兼容
├── export.js         ← 错题导出：选题/画廊预览、A4/屏幕变体、A4 单双栏确认、题间留白、下载（v1.5.0 从 schedule.js 拆出）
├── feedback.js       ← 反馈录入页：session 选择、行编辑、AI 提示词、JSON 导入、提交（v1.5.0 从 schedule.js 拆出）
├── history.js        ← 数据复盘/历史：Ledger 时间线、修正面板、撤销/恢复/还原（v1.5.0 从 schedule.js 拆出）
├── recommend.js      ← 推荐面板（双列表 + 勾选确认）
├── actions.js        ← 行动推荐：由 DATA + SESSIONS 派生「现在该做什么」（v1.7.0 新增）
├── catalog.js        ← 目录页：错题/ 文件夹树，读 GET /api/tree（v1.7.0 新增）
├── instant.js        ← 即时练习：推荐取题、在线翻答案、即时反馈
├── data.js           ← 数据复盘页 + 复盘报告导出
├── reports.js        ← 报告托管页：列表/上传创建/浏览/删除
└── app.js            ← 应用入口：switchTab/reloadData/设置 + 录入页图片粘贴/AI 识别/AI 设置 + init()
```

**加载约定（重要）：**
- 脚本均为普通 `<script>`（非 ES module），共享同一全局作用域；顶层 `let`/`const` 跨文件可见，行内 `onclick` 仍可直接调用各函数。
- **新增文件的插入位置（v1.7.0）**：`actions.js` 和 `catalog.js` 排在 `recommend.js` 之后、`instant.js` 之前。两者都只在运行时被调用（`renderDash()` / `switchTab('catalog')`），对同批次内的先后不敏感，但必须在 `core.js` 之后——它们依赖 `getItems` / `getDueDays` / `isKilledItem` / `daysSinceReview` / `escapeHtml` 等。
- **加载顺序固定**：`core.js` 最先（定义全部全局变量，只能声明一次，不可在其他文件重复 `let`）；`app.js` 最后（末尾 `init()` 自调用，依赖前面所有文件已就绪）。
- 后端由 `/assets/<file>` 通用静态路由提供（`server.py` → `_serve_asset()`，含路径穿越防护与按扩展名的 content-type）。原 `/omrs_dashboard.js` 路由已移除。
- 修改样式 → 改 `assets/styles.css`；改某模块行为 → 改对应 `assets/*.js`；新增全局工具 → 放 `core.js`。
- **拆分（v1.5.0）**：原 `schedule.js`（约 100 行的杂烩，混了导出 / Session / 反馈页 / 录入提交 / 历史时间线 / 扫描）按职责拆为 `export.js`、`feedback.js`、`history.js`，`schedule.js` 仅留 Session + 扫描 + 录入提交。因共享全局作用域且行内 `onclick` 在运行时调用，拆分只是「搬运函数 + 增加 `<script>`」，函数名 / 签名 / 调用关系全不变；加载顺序：四者都在 `core.js` 之后、`app.js` 之前。

---

## 1. 仪表盘图表（`renderDash()`）

| 图表 | HTML 容器 | 数据来源 | 实现方式 |
|---|---|---|---|
| 科目分布 | `chart-subjects` | `stats.subject_dist` | `.subject-bars` 按题量降序；底层总量条与前景“已击杀占比”条叠加，并显示题数与击杀率 |
| 近 30 天活动 | `chart-activity` | `stats.recent_activity` | 30 个本地日期热力格，按当期最大次数分 0–4 级；同时显示总复习、活跃天数和单日峰值 |
| 待复习队列预警 | `chart-alerts` | `stats.review_alert` | 二乘二卡片：今日到期、未来 3 天、未来 7 天、未到期低熟练度 |
| 每日练习趋势 | `chart-trend` | `stats.daily_trend` | 内联 SVG 平滑三次曲线路径 + 面积填充 + 非零点标记，顶部显示 30 天总量、最近一天和峰值 |
| 熟练度分布 | `chart-mastery` | `stats.mastery_histogram` | 10 个固定区间的横向条；按危险/拉升/稳定/掌握分色，宽度相对当前最大桶归一化 |
| 难度分布 | `chart-diff` | `stats.difficulty_dist` | Lv.1–10 固定竖向轨道；1–3 easy、4–6 mid、7–8 hard、9–10 risk。零题等级保留轨道、标签和数字 `0`，但不创建 `.level-fill`，避免最小高度造成假柱 |
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
- 卡头右上的「建议今天练 N 道」由 `actionTodayTarget()` 算：逾期 + 今日到期，再加最多 3 道顽固题，封顶 20。
- 按钮的回调是**闭包**，存在 `ACTION_PLAN[i].actions[j].run` 上，行内 `onclick` 只写 `runActionPlanItem(i,j)` 下标——不要改成把函数名拼进 HTML 字符串。
- 跳转辅助：`actionGoQuestions(preset)` 会**先清空**题库页全部筛选控件（含停用状态）再套 preset，然后 `switchTab('questions')` + `renderQ()`；`actionGoInstant(preset)` 同理清空 `inst-*` 后 `instLoadPractice()`。preset 的键就是元素 id。
- 样式在 `styles.css` 的 `.act-*` 段，等级色由 `.lv-urgent/.lv-warn/.lv-info/.lv-good` 决定，全部走 `--red-rgb` 等 token，深浅色自动跟随。≤720px 时改为图标 + 正文两列、按钮整行。

---

## 2. 双视图

### 题目停用筛选与操作

题目库顶部 `#q-filter-suspended` 默认选择“活动题目（不含停用）”，也可切换“仅停用题目”或“含停用全部”。停用题行/卡片以灰色虚线弱化，并显示“停用”标签；编辑菜单根据状态显示“停用题目”或“恢复题目”。操作调用 `POST /api/question/suspend` / `POST /api/question/resume`，成功后刷新题库和历史动态。


### 平铺式（List View）
- 高密度列表，每行显示 UID、科目、分类、难度、熟练度进度条、标签。
- 可直接点击加入/移除临时调度选题。

### 画廊式（Gallery View）
- 卡片形式，异步拉取 `/api/question?uid=...` 渲染题面。
- 卡片中同样使用 `.m-bar` / `.m-bar-fill` 渲染熟练度进度条。
- 题面中的 `![[图片.png]]`、`![[图片.png|300]]`、`![alt](路径)` 均改写为 `/api/image?name=...`。
- 使用 `renderMdContent()` 统一处理 HTML 转义、图片替换与 `$...$` / `$$...$$` LaTeX 渲染。
- 题目详情缓存在 `QUESTION_CACHE` / `QUESTION_PENDING`，避免重复请求。

### 编辑菜单
- List View 和 Gallery View 每题都有「编辑」按钮。
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
- 文件夹行右侧：题量 chip、待复习 chip（`.tree-badge.due`）、顽固题 chip（`.tree-badge.leech`）、该目录平均衰减熟练度条（复用 `.m-bar`）、复制相对路径按钮。
- 题目文件行右侧：逾期/今日到期 chip、熟练度条与百分比；未进投影的显示「未入库」。点击调 `catalogOpenQuestion(uid)` → `viewQ(uid)` 开题目 Modal（该题在 `DATA.items` 里才可点）。
- 搜索框 `catalogSearch()` 写 `CATALOG_QUERY`（小写）。`catalogMatches()` 递归判断「自己或任一后代命中」，命中期间**所有节点视为展开**（`open` 判定里 `|| !!CATALOG_QUERY`），不改动 `CATALOG_OPEN`，清空搜索后回到原来的展开状态。
- 「显示图片等其他文件」复选框切 `CATALOG_SHOW_ALL_FILES`，关闭时只列 `kind === 'question'` 的文件。
- 顶部 `#catalog-stat` 四张 stat 卡：文件夹数 / 题目文件 / 全部文件 / 占用；`#catalog-status` 汇报降级、孤立文件、层级截断和当前筛选词。
- `reloadData()` 里若目录页正处于激活状态且 `CATALOG_TREE` 已有，会重画一次——录题或提交反馈后目录上的熟练度条随之更新，但**不会重新扫盘**（结构变化仍需点「重新读取」或顶栏「重新扫描」）。

样式在 `styles.css` 的 `.catalog-bar` / `.tree-*` 段。≤720px 缩小缩进步长并隐藏 chip 列。

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

---

## 4. 推荐面板（双列表 + 勾选确认）

> 新增于 2026-05，替代旧版”直接塞题”流程。

### 入口

复习调度页面顶部双按钮：
- **开始常规复习** → 推荐面板（双列表推荐 → 勾选 → 预览 → 确认生成 EXP- Session）
- **导出** → 全题库筛选导出面板（`assets/export.js`）：勾选题目后直接导出 A4/屏幕版自包含 HTML，批次号 TMP-，不写 `sessions.csv`

旧「自定义练习」（新建 Session 表单）入口已移除：TMP- 批次现由两条路径产生——推荐面板**单题确认**，或「导出」面板**导出选中**（`POST /api/export` 传 `uids`）。`POST /api/schedule` 端点保留兼容，前端不再调用。

### 推荐面板流程

1. `GET /api/recommend` 获取双列表（到期 + 熟练度，互斥不重复）
2. 用户勾选题目（两侧列表均可勾选），实时显示已选计数 + 预计耗时
3. 可选操作：
    - **预览计划**：展示 4 种视图（列表/卡片/分组/时间）
    - **一键智能确认**：自动勾选到期列表前 N 道题
   - **选择当前筛选 / 全选推荐 / 移除当前筛选**：批量维护已选题目
    - **确认生成计划**：`POST /api/confirm-schedule`
4. ≥2 题生成 EXP- Session（写入 sessions.csv，必须反馈），1 题生成 TMP- 批次

### 四种预览视图

| 视图 | 说明 |
|---|---|
| 列表视图 | 一行一道题：UID、科目、分类、难度、来源标签、预计时间 |
| 卡片视图 | 每道题一张卡片，显示题目元信息和来源标签 |
| 分组视图 | 按科目分组（如”数学 3 道，约 24 分钟”），显示各组成员 |
| 时间视图 | 按预计耗时升序排列，便于先从简单的开始 |

### 来源标记

每道题携带 `_source` 字段（`due` / `proficiency`），在反馈时决定 SM-2 排期策略：
- `due`：到期来源 → 标准 SM-2 全量更新
- `proficiency`：熟练度来源 → 答对时间隔 × 0.7 折中

---

## 5. 即时练习

入口 Tab：`即时练习`；面板 `#panel-instant`；脚本 `assets/instant.js`。

流程：
1. `GET /api/recommend` 按算法取双列表推荐，可传 `subject` / `category` / `knowledge_tag` 筛选。
2. 前端合并到期列表与熟练度列表，按数量上限形成 `INSTANT_QUEUE`，不调用 `/api/confirm-schedule`，不写 `sessions.csv`。
3. 每题在线拉 `/api/question?uid=...`，先显示题面，点击后显示答案与备注。
4. 用户判对/错并给 0-10 主观分，结果存在 `INSTANT_RESULTS`。
5. 「提交已判定」调用 `POST /api/feedback`，`session_id` 使用 `IMM-YYYYMMDDHHMMSS`，只写历史与 mastery 更新，不创建调度 Session。

即时练习复用 `renderMdContent()` 处理题面、答案、备注中的图片与 LaTeX，复用 `process_feedback()` 的熟练度、EF、SM-2 更新逻辑。

> **布局重设计（v1.5.0，响应式工作台）**：原「顶栏 + `1fr/320px` 双栏（题卡 / `<aside>` 队列）」改为 `.inst-work` 网格工作台，用 `grid-template-areas` 排布四块（`#inst-summary` 进度+提交 / `.inst-queue-wrap` 队列 / `.inst-main` 题卡 / `#inst-submit-results` 结果），DOM 顺序不变也能在窄屏重排。**桌面**：左题卡（1fr）+ 右栏（进度+提交置顶 → 队列竖列 → 提交结果）。**移动端（≤900px）**：重排为 进度+提交 → 队列 → 题卡 → 结果；队列从竖列表变成**横向圆点条**（`.instant-queue` 转 flex-row 横滚，`.instant-qbtn` 隐藏 `.instant-qmain`、只留 `.qn` + `.qmk`，点按跳题）；评分 `.instant-grade` 竖排整行（`.fb-toggle` 占满 + 主观分滑杆单独一行，去掉写死的 `min-width:280px`）；导航 `.instant-nav` 改 2 列网格（「下一道未判定」整行 + 上/下各半）；题头 `.instant-head` 竖排（位置 / UID 一行、chips 落下一行）；筛选 `.inst-filters` 转 2×2 网格全宽，题数加可见标签（`.inst-count-field`）。提交按钮（JS 渲染在 `#inst-summary` 内）随进度块置顶，不再埋在侧栏底部。**清理**：移除 v1.4.2 叠加遗留的孤立 / 失效规则（`.instant-topbar` / `.instant-layout` / `.instant-side` / `.instant-summary` / `.instant-filters` 与 `.instant-head .uid` / `.meta-line` / `.tag-row`），相关样式收拢成一段。**纯 HTML 骨架 + CSS：`instant.js`、所有 `#inst-*` id 与 `instLoadPractice` / `instGo` / `instReveal` / `instSetVerdict` / `instSetScore` / `instSubmitPractice` 等逻辑、`/api/recommend`·`/api/feedback` 流程均未改。版本不变（仍 v1.5.0）。**
>
> **同日修订**：① 桌面右栏队列会随题卡高度变化而上下漂移 / 看似居中——`.inst-work` 由 `grid-template-areas` 改为显式列/行 + 末尾 `1fr` 空行吸收题卡多出的高度，队列改为稳定贴顶；移动端 `.inst-work` 改 `display:flex` 竖排（DOM 顺序天然即 进度→队列→题卡→结果）、`align-items:stretch` 占满宽，筛选项加 `min-width:0` 让 2 列等宽、题数标签 `white-space:nowrap`。② 深色「反转题图」失效——旧规则错指 `.instant-qmain img`（队列项无图），改为正确的 `.instant-md img` / `.instant-notes img`（题面 / 答案 / 备注图）。

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

## 6. 设置页面（`panel-settings`）

位于「设置」标签页，包含以下功能卡片：

### 外观（主题 / 题图反转 / Ledger 时区）
- `浅色 / 深色` 分段开关 `#st-theme-switch`（`setThemeMode()`）写 `localStorage('omrs-theme')` 并切 `<html data-theme>`；当前首帧脚本在没有保存值时选择**深色**。页面里“默认浅色”的帮助文案尚未同步，已列入 `optimization.md`。
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
- **保存 AI 配置**：`saveAiSettings()` → `POST /api/config {ai_base_url, ai_api_key, ai_model, ai_restrict_tags}`。**不重启**（`load_config` 每次读盘，保存即生效）；状态写入 `#st-ai-settings-status`。
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

## 6.1 历史记录页

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

## 7. 录入题目页（`panel-create`）与提交后表单状态

> 脚本分布：表单提交 `doCreate` / 重置 `resetCreateForm` 在 `assets/schedule.js`；科目/分类 datalist `populateCreateLists` 在 `core.js`；**图片处理、AI 识别、AI 设置、运行状态加载**在 `assets/app.js`；题目图与答案图分别暂存在全局 `CR_Q_IMAGES` / `CR_A_IMAGES`（`CR_IMG_SEQ` 为自增 id）；通用工具 `parseLooseJson` / `copyTextToClipboard` / `looseBool` 均在 `core.js` 声明；反馈页 JSON 导入 `importFeedbackJson` 与 AI 反馈提示词 `copyFeedbackAiPrompt` 在 `assets/feedback.js`。

> **布局重设计（v1.5.0，双栏工作台）**：原「左卡＝整张表单 / 右卡＝使用说明」改为**双栏工作台** `.cr-workbench`（≤900px 转单列）：**左栏「截图工作区」**`.card` 放两个截图区（题目 / 答案，中间 `.cr-div` 发丝分隔 + `.cr-tip` 提示），**右栏「题卡内容」**`.card` 放结构化字段。顶部 `.cr-steps` 编号步骤条（截图→识别→核对→保存——真序列才编号）；底部 `.cr-actionbar` 横跨双栏，含「重置」（直接调既有 `resetCreateForm()`）+「创建题目」（`#cr-btn`）与一行静态保存说明，`#cr-result` 紧随其后；原使用说明 / 文件结构树收进底部折叠块 `<details class="cr-help">`。右栏的科目 / 分类 / 难度 / 相关知识点包进 `.cr-aigroup` 卡片（标题「🤖 AI 自动填充 · 可改」，提示这组可被识别自动填、且可改）；**错因** `#cr-cause` 独立成暖色块 `.cr-cause`（`--trap-bg` 微染 + `.cr-flag` 赭色旗标 + 「复习时先看这里」脚注，作为错题本的核心字段）。**纯样式 + 结构改动：所有 `#cr-*` 元素 id、内联处理函数、`doCreate`/`crClassify`/`crExtractAnswer`/`crSetPasteTarget` 等逻辑与后端接口全部不变。**

录入页有两个图片区（现分列于左栏上下），题目区配两个 AI 按钮、答案区配一个 AI 按钮，可混用手动录入：
- **题目图片区**（`#cr-q-paste` / `#cr-q-file` / `#cr-q-images`）：粘贴/拖拽/点击选择题目截图，随题保存并嵌入 `# 题目`。按钮 **「🤖 识别题目信息」**（`#cr-classify-btn`）→ `crClassify()` 取第 1 张题目图 `POST /api/ai-recognize {mode:'classify', subject, category}`，只回填**科目/分类/难度/相关知识点**（不抄题、不解题）。按钮 **「🤖 提取题目文本」**（`#cr-question-text-btn`）→ `crExtractQuestionText()` 取第 1 张题目图 `POST /api/ai-recognize {mode:'question_text'}`，把题干/条件/选项/图表说明**提取为文本**填入 `#cr-question`。其中 `knowledge_tags` 是否限定在「已有分类 ∪ 已有知识点」由设置页 `ai_restrict_tags` 开关决定（默认开=硬约束；关=允许新建，上限 4 个）。**用户已填的科目/分类会作为 hint 传给模型（要求其沿用），且前端只填空缺项、不覆盖已填值；知识点与已填的合并去重；难度给估计值。** 两个题目区按钮共用状态 `#cr-classify-status`。
- **答案图片区**（`#cr-a-paste` / `#cr-a-file` / `#cr-a-images`）：粘贴/拖拽/点击选择答案截图，嵌入 `# 答案`。按钮 **「🤖 提取答案文本」**（`#cr-extract-btn`）→ `crExtractAnswer()` 取第 1 张答案图 `POST /api/ai-recognize {mode:'answer'}`，要求模型忠实保留图片内全部答案、解析、推导和步骤，不得摘要或补写，再填入 `#cr-answer`。也可不提取（答案图直接嵌入）或手动输入。状态写 `#cr-extract-status`。
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
- 反馈提交成功后，清空反馈行和 Session 选择状态；保留处理结果列表，便于核对本次提交。

---

## 8. 数据页（复盘）

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

## 9. 报告页（AI 报告托管）

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

## 10. 主题与深色对比度（`styles.css`，v1.7.0 修订）

主题切换机制不变（见 §6 外观：`<head>` 内联脚本 + `localStorage('omrs-theme')` + `<html data-theme>`）。本节记录 v1.7.0 为解决「深色下配色显示不明显」所做的两层改动，浅色 `:root` 未改。

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

### 规则层：写死浅色的几处

根因是这些规则写死了浅色时代的颜色，token 切深色后它们不跟着走。全部新增为 `[data-theme="dark"]` 覆盖，集中在 `styles.css` 末尾「v1.7.0 深色对比度修订」注释段：

- `.modal .q-answer .q-md` / `.instant-answer .instant-md`：原 `rgba(39,134,74,.04)` 深绿底，深色下等于没有 → 改 `rgba(var(--green-rgb),.10)`，边框 `.30`。
- `.timeline-head .tag.fam-review` / `.fam-session`：原写死 `rgba(47,125,79,.1)` / `rgba(53,106,156,.1)` → 改走 `--green-rgb` / `--blue-rgb` 的 `.18`；`.fam-question` / `.fam-system` 一并改用 token 前景色。
- `.heat-0`～`.heat-4`：空档 `.07` 看不出网格 → `.14`；中间档同步抬；`.heat-3` / `.heat-4` 的白字压浅绿底 → 改深墨 `#17150f`；`.heat-cell` 文字改 `--fg2`。
- `.level-fill` 与 `.bar-fill` / `.chart-fill` 的渐变低位：原停在 `.42` / `.72`，深色下淡进背景让柱子像被截断 → 抬到 `.58` / `.82`（accent 抬到 `.70`）；`.bar-track` / `.m-bar` 轨道改 `rgba(236,231,223,.10)`。
- `.btn.danger:hover`：`color:#fff` 压在浅色语义红上 → 深色下改 `#17150f`。
- 卡中卡（`.instant-md` / `.rec-item` / `.sched-item` / `.picker-row` 等）由 `.04` 抬到 `.07` 并补描边；`.btn` 底 `.05→.07`、hover `.10→.14` 并明确前景色；`.input` 深色底改 `--bg3`；`.img-thumb` 角标底改 `.70`。

**维护约定**：新写深色规则一律走 `var(--*)` 或 `rgba(var(--*-rgb), α)`，不要再写死十六进制或裸 `rgba(r,g,b,a)`；确需固定的深墨字用 `#17150f`（与 `--accent-fg` 同值）。
