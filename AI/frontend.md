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

> **v1.10.0 共享题目视图（qview）+ 反馈工作台**：新增 `assets/qview.js`，把原来分散在 `viewQ()`、画廊卡 `.gallery-preview` 和 `instRender()` 的三份题目渲染副本收敛成一个组件，见 §2.2。基于它做了两件用户可见的事：① 题目 Modal 改双栏（题面 | 答案+备注+历史）、加宽到 1180px、支持 `←/→` 在当前列表上下文内翻页；② 反馈录入页从「一列表单」改成三栏工作台（题目列表 / 题目视图 / 判定面板），录反馈时能直接看题和就地编辑，见 §5.1。即时练习的题面/答案块也换成 qview。版本号提到 **v1.10.0**（`omrs/version.py` + HTML 侧栏）。

> **v1.11.0 答题卡扫描回填 + 画廊预览修复**：反馈录入页接上答题卡扫描项目（OMR）的正式 `/api/v1/recognitions/{id}/result` 结果 JSON——扫完卡在识别详情页点「复制结果 JSON」，回本页点「📋 读剪贴板填写」或直接 `⌘`/`Ctrl`+`V`，按题号自动填对错与主观分，见 §5.1.1。OMR 导入只接受顶层 `recognition_id/template_id/mode/status/questions/unresolved`，明确拒绝旧 raw/items、裸数组和包装层。全部在前端完成，`/api/feedback` 零改动。同时修掉画廊缩略预览顶部凭空多出约 220px 空白的问题：`.gallery-preview` 上给旧版纯文本预览留的 `white-space:pre-wrap`，把 v1.10.0 起装进去的 qview 结构化 HTML 里标签之间的换行也渲染成了空行，见 §2.2 末尾。版本号提到 **v1.11.0**（`omrs/version.py` + HTML 侧栏 + 根 `README.md`）。

> **v1.14.0 展示板 + 用户标记 + 题库交互重设计**：题库新增筛选抽屉、激活条件 chips、列/密度设置、视图预设、批量操作和键盘导航；用户标记以 `<=>` 芯片显示，名称写入题目 YAML，支持单题/批量编辑、改名、删除、合并、按标记筛选与可选调度加成；展示板保存题目引用，支持排序、左题右空打印、「仅打印新增」+ 纸面记录与绝对页码。页面与导出统一采用 18% 淡底 + 彩色字标记样式。

> **v1.14.1 题库画廊卡精简**：画廊卡从「8 条等权横带」改为「标识 / 题面 / 脚注」三层，题面成为唯一主角。① 去重：UID 按 `category` 前缀拆成「分类 + 序号」，`knowledge_tags` 过滤掉与 `category` 同名的一条，同一字符串不再一卡三现；② 去卡中卡：`.gallery-preview` 移除 `background` / `border` / `min-height:140px`，画廊内 `.qv-label`（「题目」二字）隐藏，`.qv .q-md` 强制透明无边框；③ 只报异常：`statusTagHtml` 不再逐卡渲染全库同值的「待攻克」，改为 `galleryFlagsHtml()` 仅在逾期 / 今日到期 / 顽固 / 停用时亮标；熟练度为 0 时显示「未练习」而不画空进度条；④ 悬停收纳：复选框、「⋯」菜单、「＋标记」入口 hover / 选中才显形（`@media (hover:none)` 下常显），底部「查看详情」按钮删除——整卡（含题面）点击即开 Modal，`questions.js` 行点击选择器移除 `.gallery-preview` 排除项；⑤ 网格 `minmax(320px)→minmax(260px)`、`gap 16→12`、卡片 `padding 16→12/14`，`.question-gallery-wrap` 限宽 1440px；⑥ 截断改渐隐：`hydrateQuestionGalleryPreviews()` 渲染后量 `scrollHeight` 差值，真被截的卡才加 `.is-clipped`（`mask-image` 底部渐隐），短题不糊。元数据（科目 / 上次复习 / 衰减后 / 知识点）收进「列 / 密度」菜单的**画廊 → 显示元数据**开关（`QB_GALLERY_DETAIL`，`localStorage('omrs-qb-gallery-detail')`，**默认关 = 精简**）。同时 `qbRenderChips()` 在无激活条件时输出空串，配合 `.qb-chips:empty{display:none}` 收起常驻的「未设置筛选条件」提示行。表格视图、`getFilterState('q')`、`renderQ` / `filterQ` / `setQView` 签名与全部接口不变。

> **v1.15.0 UI 改版：密度层 + 首页重构 + 整屏工作台**：分三块。① **密度层**：`styles.css` 的 `:root` 新增 `--pad / --pad-sm / --gap / --row / --ctl / --fs / --fs-sm / --fs-xs` 一组间距变量，舒适档取值即改版前原值；`html[data-density="compact"]` 额外覆盖 `--radius / -sm / -lg`，因此所有引用这三个圆角变量的既有规则自动跟随，无需逐条改。`.card` / `.stat-card` / `.cols` / `.card-title` / `.btn` / `.btn.sm` / `.input` / `thead th` / `tbody td` / `.content` / `.topbar` / `.sched-item` 等 15 处写死 px 换成变量。注意 `.input` 用 `padding:var(--ctl) 12px` 而非固定高度——录入页的 Markdown 编辑器是 `textarea.input`，设死高度会坏。开关在设置页「外观」（`setDensity()`，`localStorage('omrs-density')`，默认 `compact`），`<head>` 内联脚本与 theme / invert-img / sidebar 同批应用防闪。② **首页重构**：顺序改为「今天 → 行动推荐 → 概览条 → 近 30 天活动 + 最薄弱科目 → 最近动态」，见 §1。③ **整屏工作台**：`switchTab()` 给 `.content` 加 `.is-workbench`（题库 / 反馈录入 / 录入题目 / 展示板 / 即时练习五页），高度自 `.content` 一路 flex 分下去，取代原先 `calc(100vh - 魔数)` 的写法，见 §1.2。

> **v1.16.0 题库练习记录：战绩带 + 记录模块**：把「练了几次、对错、分数」做进题库，但按**三层披露**分配，同一份数据只出现在一个层级。① **第一层（画廊卡脚注）**：原来的「N 次」升级成**战绩带**——一根竖条一次练习，绿对红错，高度是主观分（0–10 映射到 3–12px），左→右是时间，更早的几次 `opacity:.45` 淡出；连错 ≥2 时才在带子后补一句「连错 N」，顺利的题不加字。开关在「列 / 密度」菜单的画廊段（`QB_STREAK`，`localStorage('omrs-qb-streak')`，**默认开**，缺省值即开），关掉即回到 v1.15.0 的纯「N 次」，见「画廊式（Gallery View）」与 §3.2。② **第二层（题目详情最下面）**：`qvHtml()` 里原先塞在右栏 `.qv-a` 的 `<details class="qv-hist">` + `<pre>` 原文**整块下线**，改为通栏 `<section class="qv-rec">`，排在 `.qv-q` / `.qv-a` 之后（`.qv-split>.qv-rec{grid-column:1/-1}`）：四个派生数（练习次数 / 正确率 / 平均主观分 / 平均间隔）+ 主观分走势 sparkline（对错用点的颜色叠在同一张图上，不为对错单画第二张）+ 明细行，首屏 3 条、其余进 `<details>`，见 §2.2。③ **第三层不做**：全库聚合仍只在数据复盘页，题库页不重复。**当前实现存在数据源错配**：`DATA.items[].attempts` 来自 Ledger 重建的 `history_log.csv` 兼容投影，但 `GET /api/question` 的 `history` 仍是题目 Markdown 遗留 `# 历史` 原文；战绩带和记录模块只解析后者。因此正式反馈已记录、但题目文件没有旧历史行时，界面仍可能显示「还没练过」或空记录。Markdown 历史不再由反馈流程写入，也不是正式记录来源；修复记录模块前不应据此判断练习次数。前端正则与后端解析格式相近但并非字面完全一致：前端要求整行匹配并把分数钳到 0–10，后端使用 `re.match` 且未锚定行尾。**表格视图不加战绩带**：表格不拉题目详情，加了会让一屏几十行各发一次 `/api/question`，故 `attempts`（次数）列保持原样。版本号提到 **v1.16.0**（`omrs/version.py` + HTML 侧栏 + 根 `README.md`）。

> **设置页源码协助**：服务设置新增「下载脱敏源码」按钮，调用 `GET /api/source/export` 下载仅含 Git 已跟踪源码、测试和项目文档的 ZIP；不读取未跟踪文件，并排除个人题库、附件、运行数据、日志和生成导出文件。包内 `SOURCE_EXPORT_MANIFEST.txt` 记录导出范围。

## 文件组织（assets/）
```
omrs_dashboard.html   ← 仅 HTML 结构，<link> 引样式 + 多个 <script> 引脚本
assets/
├── styles.css        ← 全部样式（原 <style> 内联块抽出）
├── core.js           ← 全局状态、api()、通用工具/筛选/Markdown 渲染 + 做题记录解析（v1.16.0）
├── dashboard.js      ← 仪表盘图表 renderDash
├── labels.js         ← 用户标记芯片、LabelPicker、标记管理与筛选状态
├── questions.js      ← 题目库表格/画廊视图 + 题目 Modal + 安全 Markdown/LaTeX/表格渲染 + 原文编辑/迁移/删除/停用恢复入口
├── qtable.js         ← 题库筛选抽屉、激活 chips、批量条、列设置、密度、视图预设与快捷键
├── qview.js          ← 共享题目视图：题面/答案双栏组件 + 底部记录模块 + Modal 翻页（v1.10.0 新增，v1.16.0 加记录模块，见 §2.2）
├── schedule.js       ← 复习 Session：预览/删除/列表 + 工作区扫描 + 录入提交（doCreate/resetCreateForm）；旧「新建 Session」（createSession/POST /api/schedule）UI 入口已随推荐面板移除，端点保留兼容
├── export.js         ← 错题导出：选题/画廊预览、A4/屏幕变体、A4 单双栏确认、题间留白、下载（v1.5.0 从 schedule.js 拆出）
├── feedback.js       ← 反馈录入工作台：session 选择、题目列表/判定面板、AI 提示词、JSON 导入、提交（v1.5.0 从 schedule.js 拆出；v1.10.0 改三栏；v1.11.0 加答题卡扫描 JSON 解析）
├── history.js        ← 数据复盘/历史：Ledger 时间线、修正面板、撤销/恢复/还原（v1.5.0 从 schedule.js 拆出）
├── recommend.js      ← 推荐面板（双列表 + 勾选确认）
├── recommend_v2.js   ← 优化推荐面板；使用私有 `recV2GetFilterState` / `recV2FilterItems`，不覆盖 core.js 公共筛选 API
├── actions.js        ← 行动推荐：由 DATA + SESSIONS 派生「现在该做什么」（v1.7.0 新增）
├── catalog.js        ← 目录页：错题/ 文件夹树，读 GET /api/tree（v1.7.0 新增）
├── instant.js        ← 即时练习：推荐取题、在线翻答案、即时反馈
├── data.js           ← 数据复盘页 + 复盘报告导出
├── board.js           ← 展示板 CRUD、排序、添加题目、打印（全部 / 仅新增）与纸面记录
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
  board → reports → app`。
- **新增文件的插入位置（v1.10.0）**：`qview.js` 必须排在 `questions.js` 之后、`schedule.js` 之前——它依赖 questions.js 的 `renderMdContent` / `ensureQuestionDetail` / `QUESTION_CACHE`，而 `feedback.js`、`instant.js`、`export.js`、`data.js` 又依赖它的 `qvRender` / `qvHtml` / `qvSetContext`。
- **新增文件的插入位置（v1.7.0）**：`actions.js` 和 `catalog.js` 排在 `recommend.js` 之后、`instant.js` 之前。两者都只在运行时被调用（`renderDash()` / `switchTab('catalog')`），对同批次内的先后不敏感，但必须在 `core.js` 之后——它们依赖 `getItems` / `getDueDays` / `isKilledItem` / `daysSinceReview` / `escapeHtml` 等。
- **加载顺序固定**：`core.js` 最先（定义全部全局变量，只能声明一次，不可在其他文件重复 `let`）；`app.js` 最后（末尾 `init()` 自调用，依赖前面所有文件已就绪）。
- 后端由 `/assets/<file>` 通用静态路由提供（`server.py` → `_serve_asset()`，含路径穿越防护与按扩展名的 content-type）。原 `/omrs_dashboard.js` 路由已移除。
- 修改样式 → 改 `assets/styles.css`；改某模块行为 → 改对应 `assets/*.js`；新增全局工具 → 放 `core.js`。
- **拆分（v1.5.0）**：原 `schedule.js`（约 100 行的杂烩，混了导出 / Session / 反馈页 / 录入提交 / 历史时间线 / 扫描）按职责拆为 `export.js`、`feedback.js`、`history.js`，`schedule.js` 仅留 Session + 扫描 + 录入提交。因共享全局作用域且行内 `onclick` 在运行时调用，拆分只是「搬运函数 + 增加 `<script>`」，函数名 / 签名 / 调用关系全不变；加载顺序：四者都在 `core.js` 之后、`app.js` 之前。

---

## 1. 仪表盘图表（`renderDash()`）

> **v1.15.0 重构**：首页只回答「今天做什么」。原来的 5 张 `.stat-card` 压成一条 `.kpi-strip`（**id 全部保留**：`s-total` / `s-killed` / `s-kill-pct` / `s-attack` / `s-avgm` / `s-suspended`，`renderDash()` 的赋值一行未改）；分布类图表让位给「数据复盘」页。
> - **容器搬到 `panel-data`、id 不变**：`chart-trend`（每日练习趋势）、`chart-labels`（标记分布）。`renderTrendChart` / `renderLabelChart` 仍由 `renderDash()` 调用，函数零改动。
> - **容器直接删除**：`chart-subjects` / `chart-alerts` / `chart-mastery` / `chart-diff`——这四张在复盘页已有同口径的更全版本（`data-subject-radar` / `data-alerts` / `data-mastery` / `data-difficulty`）。对应 render 函数保留且都以 `if(!el)return` 开头，找不到容器即空转，不报错。

| 图表 | HTML 容器 | 数据来源 | 实现方式 |
|---|---|---|---|
| 今天 | `dash-today` | `DATA`（`items` / `daily_trend`）+ `SESSIONS` | `dashboard.js::renderTodayHero()`：整页唯一大字号。待复习总数 = 逾期 + 今日到期，下方拆「逾期 / 今日到期 / 未录反馈」，中列今日已练对比 `actionTodayTarget()`，右列主 CTA。左边框按状态着色（`.lv-overdue` 红 / `.lv-due` 黄 / `.lv-clear` 绿）；空题库走 `.is-empty` 引导态。不新增接口 |
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
- **脚注战绩带（v1.16.0，默认开）**：`galleryFootHtml()` 里原来的「N 次」换成 `galleryStreakSlotHtml()` 产出的
  `.gc-streak-slot` 占位（先显示 `attempts` 数字），`hydrateQuestionGalleryPreviews()` 拿到同一次 `ensureQuestionDetail(uid)`
  的结果后调 `galleryStreakBodyHtml(item, detail)` 就地替换成 `qStreakHtml()` + 记录数 +（仅连错 ≥2 时）「连错 N」。
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
- 文件夹行右侧：题量 chip、待复习 chip（`.tree-badge.due`）、顽固题 chip（`.tree-badge.leech`）、该目录平均衰减熟练度条（复用 `.m-bar`）、复制相对路径按钮。
- 题目文件行右侧：逾期/今日到期 chip、熟练度条与百分比；未进投影的显示「未入库」。点击调 `catalogOpenQuestion(uid)` → `viewQ(uid)` 开题目 Modal（该题在 `DATA.items` 里才可点）。
- 搜索框 `catalogSearch()` 写 `CATALOG_QUERY`（小写）。`catalogMatches()` 递归判断「自己或任一后代命中」，命中期间**所有节点视为展开**（`open` 判定里 `|| !!CATALOG_QUERY`），不改动 `CATALOG_OPEN`，清空搜索后回到原来的展开状态。
- 「显示图片等其他文件」复选框切 `CATALOG_SHOW_ALL_FILES`，关闭时只列 `kind === 'question'` 的文件。
- 顶部 `#catalog-stat` 四张 stat 卡：文件夹数 / 题目文件 / 全部文件 / 占用；`#catalog-status` 汇报降级、孤立文件、层级截断和当前筛选词。
- `reloadData()` 里若目录页正处于激活状态且 `CATALOG_TREE` 已有，会重画一次——录题或提交反馈后目录上的熟练度条随之更新，但**不会重新扫盘**（结构变化仍需点「重新读取」或顶栏「重新扫描」）。

样式在 `styles.css` 的 `.catalog-bar` / `.tree-*` 段。≤720px 缩小缩进步长并隐藏 chip 列。

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

`opts` 默认值：`layout:'split'`（`'stack'` 为单栏）、`reveal:true`、`showAnswer/showNotes/showHistory/showMeta:true`、`bare:false`、`actions:[]`、`clamp:0`。v1.16.0 起 `showHistory` 控制的是题目详情**最下面的通栏记录模块**（原先是右栏里的 `<details>` 原文）。

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

批量条（fixed，底部）：加入展示板（`B`，选板对话框）、打标记（`L`，添加 / 移除勾选弹层，可
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
`uiToast / uiDialog / uiPrompt / uiConfirm`（core.js）替代 `alert / prompt / confirm`。

标记接入录入表单、收件箱题卡、题库、题目 Modal、反馈、即时练习、推荐、导出、
展示板、数据复盘和仪表盘。数据页显示按标记正确率/平均分，仪表盘显示活动题目的
标记分布；`boardQuickAdd()` 统一处理各页面的「加入展示板」入口。

### 3.4 展示板页（`assets/board.js`，v1.14.0）

侧栏「题目库」与「目录」之间的「展示板」Tab，三栏：板列表（`⋯`：重命名 / 备注 / 复制 /
导出 / 删除）、板内容（添加题目对话框复用 `filterItems` + 标记 chips、按标记同步、排序菜单、
拖拽 / `Ctrl+↑↓` 排序、单题额外留白、预览、移除、清空；行内徽章：已印 p.N / 新增 / 已改动 /
停用 / 缺失）、版面与打印（去抖 500ms 保存；「预计页数」由隐藏 iframe 跑导出模板实测）。

打印区两种模式：**打印全部**（整板从第 1 页排）与**仅打印新增**（只有纸面记录存在时可选：
新题接在纸面 `cursor` 所在页的空白处续排，需要新页时用绝对页码 `pages+1`）。「标记为已打印」
把同一份导出 HTML 放进隐藏 iframe（`boardMeasureLayout`）测量版面，`POST /api/board/printed`
记录；打印预览窗口的「已打印，记录纸面」通过 `postMessage('omrs-board-printed')` 触发同一流程。
打印预览（v1.14.1）必须**先同步 `window.open('', '_blank')` 拿到窗口、写入占位提示，再
`await` 导出**，最后 `preview.location.replace(blobURL)` 填入内容：浏览器只在用户手势的同步
调用栈里允许开新窗口，先 `await` 会让手势过期而被拦截（板子越大越明显，Safari 尤其严）。
`location.replace` 不换窗口对象，`BOARD_WINDOWS.get(event.source)` 的回传不受影响；导出失败
时关闭占位窗口。纸面记录可重置。快捷键：`N` 新建、`A` 添加、`P` 预览、`↑↓` 选行、`Ctrl/⌘+↑↓` 排序、
Enter 打开、Delete 移除。完整设计见 `board.md` §4。

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

推荐优化面板（`assets/recommend_v2.js`）的筛选状态和筛选函数使用 `recV2GetFilterState()`、`recV2FilterItems()` 私有命名。`core.js` 的 `getFilterState()` / `filterItems()` 是题库、展示板、导出和即时练习共用契约，不应由推荐面板覆盖。

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

即时练习复用 `process_feedback()` 的熟练度、EF、SM-2 更新逻辑。**v1.10.0 起题面 / 答案 / 备注块由 qview 渲染**（`instRender()` 内 `qvRender('#inst-qv', uid, {reveal:row.revealed, showHistory:false, actions:['edit'], onReveal:instReveal})`），原 `.instant-block` / `.instant-md` / `.instant-notes` / `.instant-answer-locked` 及其样式已删除，未翻答案时不再渲染答案 DOM，题卡内也多了「编辑 Markdown」入口。`instRender` / `instGo` / `instReveal` / `instSetVerdict` / `instSetScore` / `instSubmitPractice` 的签名与 `/api/recommend`·`/api/feedback` 流程均未改。

> **布局重设计（v1.5.0，响应式工作台）**：原「顶栏 + `1fr/320px` 双栏（题卡 / `<aside>` 队列）」改为 `.inst-work` 网格工作台，用 `grid-template-areas` 排布四块（`#inst-summary` 进度+提交 / `.inst-queue-wrap` 队列 / `.inst-main` 题卡 / `#inst-submit-results` 结果），DOM 顺序不变也能在窄屏重排。**桌面**：左题卡（1fr）+ 右栏（进度+提交置顶 → 队列竖列 → 提交结果）。**移动端（≤900px）**：重排为 进度+提交 → 队列 → 题卡 → 结果；队列从竖列表变成**横向圆点条**（`.instant-queue` 转 flex-row 横滚，`.instant-qbtn` 隐藏 `.instant-qmain`、只留 `.qn` + `.qmk`，点按跳题）；评分 `.instant-grade` 竖排整行（`.fb-toggle` 占满 + 主观分滑杆单独一行，去掉写死的 `min-width:280px`）；导航 `.instant-nav` 改 2 列网格（「下一道未判定」整行 + 上/下各半）；题头 `.instant-head` 竖排（位置 / UID 一行、chips 落下一行）；筛选 `.inst-filters` 转 2×2 网格全宽，题数加可见标签（`.inst-count-field`）。提交按钮（JS 渲染在 `#inst-summary` 内）随进度块置顶，不再埋在侧栏底部。**清理**：移除 v1.4.2 叠加遗留的孤立 / 失效规则（`.instant-topbar` / `.instant-layout` / `.instant-side` / `.instant-summary` / `.instant-filters` 与 `.instant-head .uid` / `.meta-line` / `.tag-row`），相关样式收拢成一段。**纯 HTML 骨架 + CSS：`instant.js`、所有 `#inst-*` id 与 `instLoadPractice` / `instGo` / `instReveal` / `instSetVerdict` / `instSetScore` / `instSubmitPractice` 等逻辑、`/api/recommend`·`/api/feedback` 流程均未改。版本不变（仍 v1.5.0）。**
>
> **同日修订**：① 桌面右栏队列会随题卡高度变化而上下漂移 / 看似居中——`.inst-work` 由 `grid-template-areas` 改为显式列/行 + 末尾 `1fr` 空行吸收题卡多出的高度，队列改为稳定贴顶；移动端 `.inst-work` 改 `display:flex` 竖排（DOM 顺序天然即 进度→队列→题卡→结果）、`align-items:stretch` 占满宽，筛选项加 `min-width:0` 让 2 列等宽、题数标签 `white-space:nowrap`。② 深色「反转题图」失效——旧规则错指 `.instant-qmain img`（队列项无图），改为正确的 `.instant-md img` / `.instant-notes img`（题面 / 答案 / 备注图）。

---

## 5.1 反馈录入工作台（`assets/feedback.js`，v1.10.0；答题卡导入 v1.11.0）

入口 Tab：`反馈录入`；面板 `#panel-feedback`。骨架与即时练习的 `.inst-work` 同源——反馈录入本质上就是同一个复习流程，只是题目已经在纸面上做完了，因此复用那套已经调好的三栏布局和移动端重排规则，而不是再造一套。

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

### 5.1.1 答题卡扫描 JSON 导入（v1.11.0）

纸面复习的闭环原本断在「批改结果怎么回到 OMRS」：要么手工逐题点，要么把结果口述给 AI 让它拼反馈 JSON。v1.11.0 接上答题卡扫描项目（OMR）的正式结果输出——扫完卡在识别详情页复制 `/api/v1/recognitions/{id}/result` JSON，回本页读剪贴板，逐题自动落到判定面板上。

**全部在前端完成**，`/api/feedback` 与提交体 `{uid, sub_score, is_correct, note}` 零改动。

#### 题号 → UID 的对应关系

答题卡上只有题号，没有 UID。唯一的对应依据是**当前 Session 的题目顺序**：OMR 的 `seq N` ↔ `sessionUniqueUids(session)[N-1]`，与 `omrs/exporting.py` 打印「第 N 题 [UID]」时用的 `enumerate(questions, 1)` 是同一个口径。因此**没选 Session 就直接拒绝导入**，不做任何猜测。

已知边界：导出答题卡之后再停用某道题，`list_sessions` 会把它从 `uids` 里滤掉，其后所有题号整体前移，纸面与 Session 不再对齐。UI 与导入面板都写明了这一点，中栏题面就是核对手段。

#### 唯一接受的 OMR JSON 形态（`omrReadSheet`）

OMR 剪贴板导入只接受 `GET /api/v1/recognitions/{id}/result` 返回的**顶层对象**：

```json
{
  "recognition_id": 12,
  "template_id": "omrs-2col-normal-30q-tm-v2",
  "mode": "omrs",
  "status": "ready",
  "questions": [{"seq": 1, "page": 1, "result": "C", "level": "9"}],
  "unresolved": []
}
```

六个顶层字段 `recognition_id/template_id/mode/status/questions/unresolved` 必须齐全，`questions` 与 `unresolved` 必须是数组。旧的完整原始记录 `{id,status,template_id,items:[...]}`、详情页 `detail_json`、裸 `items` 数组、`{recognition|record|result|data: ...}` 包装层和扫描记录列表都明确拒绝；错误信息会要求回 OMR 识别详情页点击「复制结果 JSON」。OMRS 不再读取 `raw_value/result_status/manual_value/darkness`，也不再按选项集合反推字段种类，证据到结论的规则只留在 OMR 的 `service.result_export`。

#### 逐题判定规则

- **OMRS mode**：直接读取 `questions[].result`（`C/W`）与 `questions[].level`（字符串 `0`–`10`）；level 为 `null` 且对应字段不在 `unresolved` 时，仍按对错给默认分 `correct?10:4`。
- **Anki mode**：保留原有 SM-2 映射，读取 `questions[].answer`（`A`=错/1 分，`H`=对/5，`G`=对/8，`E`=对/10）。
- **custom mode**：`questions[].answer` 只有选项、推不出对错，一律留给人工。
- `unresolved` 是唯一的待复核信号：只要某个 `seq` 有 unresolved 字段，该题就不自动填写；字段名与状态以 `OMR：` 前缀写进备注，进入三栏工作台人工处理。即使 `questions` 内同时出现了值，也不覆盖 unresolved。
- 任务级：`failed` 拒绝导入；`uploaded`/`queued`/`processing` 提示尚未识别完；`needs_review` 可读取，但其中 unresolved 题仍全部转人工。
- 超出 Session 题数的题号、以及本 Session 已录入过的 UID，都跳过并在状态行报告计数；全部题号都超范围时直接提示「多半选错了 Session」。

#### 三个入口，一套解析

`fbImportText()` → `fbPayloadKind()` 分流 → `fbImportOmrScan()` 或 `fbImportFeedbackPayload()`。三个入口都同时接受答题卡 JSON 和反馈 JSON：

1. 顶栏「📋 读剪贴板填写」（`fbReadClipboardAndFill`，走 `navigator.clipboard.readText`）
2. 本面板内直接 `⌘`/`Ctrl`+`V`（`fbHandlePaste`，document 级监听，焦点在输入控件时让位）
3. 折叠面板里的粘贴框 +「导入 JSON」（`importFeedbackJson`）

第 2 条不是锦上添花：`navigator.clipboard` 只在 HTTPS 或 localhost 可用，局域网 `http://` 打开时按钮会失效，粘贴事件是那种情况下唯一能用的路径，两者都失败时才退回粘贴框。

解析器不依赖 core.js 的 `asNumber`（内部用 `omrInt`/`omrScore`），因此可在 node 侧单独 `require` 出来测：`tests/test_omr_import.js` 覆盖正式协议、旧协议拒绝、OMRS/Anki 映射、unresolved 与状态边界，`tests/smoke_feedback_omr_import.js` 用 vm + 最小 DOM 桩跑整条接线。

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

## 6. 设置页面（`panel-settings`）

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

> **v1.10.0 清理**：`.modal .q-answer .q-md` 和 `.instant-answer .instant-md` 两条写死 `rgba(39,134,74,.04)` 的答案块规则，随 qview 落地一并删除——新的 `.qv .q-answer-md` 直接走 `rgba(var(--green-rgb),α)`，深色不需要单独补丁，对应的 `[data-theme="dark"]` 特例也已移除。深色「反转题图」的选择器改为 `.q-md img` / `.qv .q-md img` / `.gallery-preview img`。

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

## 7.1 收件箱录入流程（`assets/inbox.js`，v1.12.0）

`#panel-create` 改为顶部 `.ib-flow`：**上传 → 处理 → 录入**（编号真序列）+ AI 训练 + 快速录入；原单题表单整段搬进 `#ib-stage-quick`，所有 `#cr-*` id 与 `doCreate` / `crClassify` 等逻辑不变。新脚本 `assets/inbox.js` 排在 `data.js` 之后、`reports.js` 之前（依赖 `core.js` 的 `api`/`escapeHtml` 与 `questions.js` 的 `renderMdContent`）；`switchTab('create')` 调 `inboxInit()`。样式集中在 `styles.css` 末段，类名全部 `ib-` 前缀；画布标注色 `--ib-role-*` 固定不随主题。粘贴分流：`ibPaste`（捕获阶段）只在上传阶段拦截图片；`crHandlePaste` 只在快速录入阶段生效。设置页「AI 自动识别」新增三个按用途的模型输入框（`#st-ai-model-detect/-extract/-classify`），随 `saveAiSettings` 一起保存。交互细节、job 轮询、沿用框位的像素锚定规则见 `AI/inbox.md` §5。v1.13.0：处理页 / 队列脚 / 批量条加「▦ 模板框选」（`ibDetect(ids, 'template')`，零联网）；「AI 训练」页加盲标评估集与存储概览、清理按钮、以及「框选提供方与自动策略」表单（`.ib-pl-grid`，`ibLoadPolicy / ibSavePolicy` 读写 `/api/config` 的 `inbox_*` 键，与设置页共用同一 config）；大裁图自动改 JPEG。
