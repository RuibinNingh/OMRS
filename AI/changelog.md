# 前端版本变更摘要（changelog）

> 从 `frontend.md` 顶部搬出来的「每版改了什么」叙述，按版本**倒序**排列；`frontend.md` 只保留当前行为。
> 这里每段都是当时写下的原文（未改写），所以段里的「现在 / 原先」以该版本为准；具体文件级变更看 `logs/`。
> 新版本的摘要请追加在最上面；同一版本多次改动时合并进同一段。

## v1.18.2

- 修复展示板锁定后追加新题会清空纸面记录、被迫全部重印的问题：增删引用、排序与调整未打印题留白保留已印题目、页数及续排位置；仅新增导出继续沿用旧纸面。
- 锁定保护只针对会影响已打印区域的版式修改，保留明确确认流程；前端提示与后端判定保持一致。补充后端与前端回归测试。

## v1.18.1

> **v1.18.1 反馈提交结果改弹窗**：起因是「反馈录入后的结果显示占用屏幕空间还关不掉」。原先 `submitFb()` 把「本次处理结果」直接 `innerHTML` 进页内 `#fb-results`；宽屏 `.content.is-workbench` 下 `.panel.active` 是整屏 flex 列且 `overflow:hidden`，这块没有 `flex-shrink:0`，明细一多就把 `.fb-work` 三栏挤矮、超出部分被裁到屏幕外，而它只有换 Session 或重新导入才会消失，没有任何关闭入口。改法：新增 `#fb-result-modal`（`.modal-overlay` + `.modal.fb-result-modal`，与 `#modal` / `#md-editor` 同骨架），`#fb-results` 搬进弹窗当滚动区 `.fb-result-list`，页内只留 `.fb-statusbar` 一行（`#fb-status` 小结 + `#fb-result-reopen`「查看本次结果」）。`feedback.js` 新增 `FB_LAST_RESULT` 与 `fbResultRowsHtml` / `fbResultMetaText` / `fbOpenResults` / `fbCloseResults` / `fbClearResults` / `fbSyncResultReopen`；原先三处「清空 `#fb-results`」（`onFbSessionChange(true)`、`fbImportOmrScan`、`fbImportFeedbackPayload`）统一改调 `fbClearResults()`，关闭与清空分成两件事——关掉只是收起来，结果留着可重开。关闭入口四个：`✕` / 「知道了」/ 点遮罩 / `Escape`；弹窗开着时 `fbHandleKey` 只认 `Escape`，`J`/`K`/`1`/`2`/`⌘`+`Enter` 不再穿透到判定面板，`fbHandlePaste` 同样让路。明细行 `.result-row.ok/.err` 与掌握度、SM-2、来源标记的渲染内容不变，`/api/feedback` 与提交体 `{uid, sub_score, is_correct, note}` 零改动。新增反馈结果弹窗回归用例（20 项），守弹窗开关、快捷键不穿透、换 Session 清结果。`styles.css` 与 `feedback.js` 的 `?v=` 刷成 `20260912-fb-result-modal`。

## v1.18.0

> **v1.18.0 展示板重构：状态条 / 舞台 / 检查器三区**：起因是「展示板的 UI 操作有点太怪」，拆出来是四条职责放错位置——能做什么随视图变（纸面有检视条、列表是行内控件、画廊两样都没有）、打印范围藏在会遮住纸面的浮层里、题后留白有三个彼此不可见的入口、打印状态机没有落脚点（未打印 / 已印 N 页 / 新增 M 题 / K 题已改动散在副标题、警告条、行内徽章和浮层里，没有一处说下一步做什么，所以最容易漏掉「标记为已打印」）。改法：新增纯函数 `boardStatusModel(board, mode, awaiting)` 一处算出状态 chips、打印范围、唯一主行动与一句「为什么」；`#bd-statusbar` 承载它，打印范围分段 `[data-board-modes]` 从浮层提到这里，主按钮 `[data-board-primary]` 全页唯一；触发打印预览 / 下载 HTML 后主按钮翻成「✓ 记录纸面」（`BOARD_AWAITING_RECORD`），记录成功、重置纸面或改范围才复位。新增常驻检查器 `#bd-inspector`，三段 `[data-sec="item|layout|paper"]`；`boardSettingsPopHtml` / `boardPopOpen` / `boardPopClose` / `boardPopPlace` / `boardPopRefresh` / `BOARD_POP` 与 `.bd-pop*` 样式整套删除，旧检视条 `#bd-inspect` 一并移除。题后留白写入口收敛到检查器一个（`[data-board-inspect-gap]`），列表行与画廊卡改 `[data-board-gap-view]` 只读回显，点它 = 选中并把焦点送进检查器；新增 `boardRefreshLiveReadouts()` 让板级 `gap_lines` 一改，继承它的单题读数与两处回显一起刷新。舞台栏 `.bd-stagebar` 只留视图分段与内容操作，翻页条另占一行；缩放档状态化为 `BOARD_ZOOM`（此前初始态两个按钮都不高亮）。常驻预览在 `omrs-board-view` 里带 `embedded:true`，导出模板据此收起顶栏 `#bar`，舞台里不再出现第二套打印与记录入口。`.bd-layout` 改 `200px / 1fr / 268px` 三列，≤1180px 检查器折到底部通栏。顺手修掉一个既有缺陷：`boardEffectiveMode()` 原先不看新增数，「补印新增 → 记录纸面」之后模式仍是 `new` 而新增已归零，下一次导出会报「没有新增题目需要打印」；现在它直接返回 `boardStatusModel().scope`，与状态条同源。新增 `tests/test_board_regions.js`（17 项）守三条不变量与状态机五态。

## v1.17.0

> **v1.17.0 展示板文件夹与统一选板浮层**：八处「加入展示板」入口统一走 `boardPickerOpen(uids, {anchor, exclude, moveFrom, direct, onDone})`——锚定触发元素下方弹浮层、单击板行即加入、无「确定」按钮；`boardQuickAdd` / `boardChooseAndAdd` 保留为薄封装。键盘两键直达（`Enter` 进上次的板，默认高亮跳过「全部已在板中」行）；`Shift`+点击跳过浮层直加；`⌘` 点已加行撤回本次加的题；搜不到时底部变「＋ 新建并加入」。`boards.json` 升 v2：新增单层 `folders`，板新增 `folder_id` / `order`，v1 文件读时自动迁移、悬空 `folder_id` 静默归未归档；左栏板列表改「文件夹 → 板」两级树（折叠、拖拽归类、文件夹排序）。`/api/boards` 响应从 `{boards}` 变 `{boards, folders}`，每板多返回 `uids`；新增 `/api/board/folder/{create,update,delete}` 与 `/api/board/move` 4 条路由。折叠状态存 localStorage 不进 `boards.json`；删除文件夹默认保板可改连删。toast 调整：「换个板…」只保留在 `Shift` 直加路径。

## v1.16.1

> **v1.16.1 练习记录改读 Ledger + 文档整理**：`GET /api/question` 新增 `records[]`（`stats.get_question_records()`，由 Ledger 投影 `history_log.csv` 派生，按 `Question_ID` 优先、`UID` 兜底匹配）；前端 `core.js::qRecordsFromDetail()` 统一取记录，画廊战绩带（`galleryStreakBodyHtml`）与题目详情记录模块（`qvRecordHtml`）都改读它，Markdown `# 历史` 降为老后端兜底，空记录只显示「还没练过。」。反馈提交 / 历史修正后 `qvInvalidateMany()` 清 `QUESTION_CACHE`。设置页「外观」文案改为「首次打开默认深色」。全站 35 处原生 `alert / prompt / confirm` 换成 `uiToast / uiPrompt / uiConfirm`（涉及 app / export / feedback / history / inbox / instant / questions / recommend / recommend_v2 / reports / schedule），长确认改成标题 + hint + 动词按钮；13 个 JS 的 `?v=` 统一刷成 `20260906-v1161`。文档：`frontend.md` 顶部 16 段版本引用搬到本文件并按版本倒序，正文里 3 段「原来 / 现在」叙述改写成当前状态；章节重新编号（设置页 §7、历史页 §8、录入页 §9、收件箱 §9.1、数据页 §10、报告页 §11、主题 §12）；§5.1.1 答题卡导入拆成 `omr-import.md`；`optimization.md` 测试清单改成按主题分组的列表；新增 `tests/check_docs.py` 文档形式体检，三条写法规则与体检门槛写进根 `AGENTS.md` 与 `AI/README.md`。

## 未标版本

> **设置页源码协助**：服务设置新增「下载脱敏源码」按钮，调用 `GET /api/source/export` 下载仅含 Git 已跟踪源码、测试和项目文档的 ZIP；不读取未跟踪文件，并排除个人题库、附件、运行数据、日志和生成导出文件。包内 `SOURCE_EXPORT_MANIFEST.txt` 记录导出范围。

## v1.16.0

> **v1.16.0 题库练习记录：战绩带 + 记录模块**：把「练了几次、对错、分数」做进题库，但按**三层披露**分配，同一份数据只出现在一个层级。① **第一层（画廊卡脚注）**：原来的「N 次」升级成**战绩带**——一根竖条一次练习，绿对红错，高度是主观分（0–10 映射到 3–12px），左→右是时间，更早的几次 `opacity:.45` 淡出；连错 ≥2 时才在带子后补一句「连错 N」，顺利的题不加字。开关在「列 / 密度」菜单的画廊段（`QB_STREAK`，`localStorage('omrs-qb-streak')`，**默认开**，缺省值即开），关掉即回到 v1.15.0 的纯「N 次」，见「画廊式（Gallery View）」与 §3.2。② **第二层（题目详情最下面）**：`qvHtml()` 里原先塞在右栏 `.qv-a` 的 `<details class="qv-hist">` + `<pre>` 原文**整块下线**，改为通栏 `<section class="qv-rec">`，排在 `.qv-q` / `.qv-a` 之后（`.qv-split>.qv-rec{grid-column:1/-1}`）：四个派生数（练习次数 / 正确率 / 平均主观分 / 平均间隔）+ 主观分走势 sparkline（对错用点的颜色叠在同一张图上，不为对错单画第二张）+ 明细行，首屏 3 条、其余进 `<details>`，见 §2.2。③ **第三层不做**：全库聚合仍只在数据复盘页，题库页不重复。**当前实现存在数据源错配**（→ v1.16.1 已修，见上）：`DATA.items[].attempts` 来自 Ledger 重建的 `history_log.csv` 兼容投影，但 `GET /api/question` 的 `history` 仍是题目 Markdown 遗留 `# 历史` 原文；战绩带和记录模块只解析后者。因此正式反馈已记录、但题目文件没有旧历史行时，界面仍可能显示「还没练过」或空记录。Markdown 历史不再由反馈流程写入，也不是正式记录来源；修复记录模块前不应据此判断练习次数。前端正则与后端解析格式相近但并非字面完全一致：前端要求整行匹配并把分数钳到 0–10，后端使用 `re.match` 且未锚定行尾。**表格视图不加战绩带**：表格不拉题目详情，加了会让一屏几十行各发一次 `/api/question`，故 `attempts`（次数）列保持原样。版本号提到 **v1.16.0**（`omrs/version.py` + HTML 侧栏 + 根 `README.md`）。

## v1.15.0

> **v1.15.0 UI 改版：密度层 + 首页重构 + 整屏工作台**：分三块。① **密度层**：`styles.css` 的 `:root` 新增 `--pad / --pad-sm / --gap / --row / --ctl / --fs / --fs-sm / --fs-xs` 一组间距变量，舒适档取值即改版前原值；`html[data-density="compact"]` 额外覆盖 `--radius / -sm / -lg`，因此所有引用这三个圆角变量的既有规则自动跟随，无需逐条改。`.card` / `.stat-card` / `.cols` / `.card-title` / `.btn` / `.btn.sm` / `.input` / `thead th` / `tbody td` / `.content` / `.topbar` / `.sched-item` 等 15 处写死 px 换成变量。注意 `.input` 用 `padding:var(--ctl) 12px` 而非固定高度——录入页的 Markdown 编辑器是 `textarea.input`，设死高度会坏。开关在设置页「外观」（`setDensity()`，`localStorage('omrs-density')`，默认 `compact`），`<head>` 内联脚本与 theme / invert-img / sidebar 同批应用防闪。② **首页重构**：顺序改为「今天 → 行动推荐 → 概览条 → 近 30 天活动 + 最薄弱科目 → 最近动态」，见 §1。③ **整屏工作台**：`switchTab()` 给 `.content` 加 `.is-workbench`（题库 / 反馈录入 / 录入题目 / 展示板 / 即时练习五页），高度自 `.content` 一路 flex 分下去，取代原先 `calc(100vh - 魔数)` 的写法，见 §1.2。

## v1.14.1

> **v1.14.1 题库画廊卡精简**：画廊卡从「8 条等权横带」改为「标识 / 题面 / 脚注」三层，题面成为唯一主角。① 去重：UID 按 `category` 前缀拆成「分类 + 序号」，`knowledge_tags` 过滤掉与 `category` 同名的一条，同一字符串不再一卡三现；② 去卡中卡：`.gallery-preview` 移除 `background` / `border` / `min-height:140px`，画廊内 `.qv-label`（「题目」二字）隐藏，`.qv .q-md` 强制透明无边框；③ 只报异常：`statusTagHtml` 不再逐卡渲染全库同值的「待攻克」，改为 `galleryFlagsHtml()` 仅在逾期 / 今日到期 / 顽固 / 停用时亮标；熟练度为 0 时显示「未练习」而不画空进度条；④ 悬停收纳：复选框、「⋯」菜单、「＋标记」入口 hover / 选中才显形（`@media (hover:none)` 下常显），底部「查看详情」按钮删除——整卡（含题面）点击即开 Modal，`questions.js` 行点击选择器移除 `.gallery-preview` 排除项；⑤ 网格 `minmax(320px)→minmax(260px)`、`gap 16→12`、卡片 `padding 16→12/14`，`.question-gallery-wrap` 限宽 1440px；⑥ 截断改渐隐：`hydrateQuestionGalleryPreviews()` 渲染后量 `scrollHeight` 差值，真被截的卡才加 `.is-clipped`（`mask-image` 底部渐隐），短题不糊。元数据（科目 / 上次复习 / 衰减后 / 知识点）收进「列 / 密度」菜单的**画廊 → 显示元数据**开关（`QB_GALLERY_DETAIL`，`localStorage('omrs-qb-gallery-detail')`，**默认关 = 精简**）。同时 `qbRenderChips()` 在无激活条件时输出空串，配合 `.qb-chips:empty{display:none}` 收起常驻的「未设置筛选条件」提示行。表格视图、`getFilterState('q')`、`renderQ` / `filterQ` / `setQView` 签名与全部接口不变。

## v1.14.0

> **v1.14.0 展示板 + 用户标记 + 题库交互重设计**：题库新增筛选抽屉、激活条件 chips、列/密度设置、视图预设、批量操作和键盘导航；用户标记以 `<=>` 芯片显示，名称写入题目 YAML，支持单题/批量编辑、改名、删除、合并、按标记筛选与可选调度加成；展示板保存题目引用，支持排序、左题右空打印、「仅打印新增」+ 纸面记录与绝对页码。页面与导出统一采用 18% 淡底 + 彩色字标记样式。

## v1.11.0

> **v1.11.0 答题卡扫描回填 + 画廊预览修复**：反馈录入页接上答题卡扫描项目（OMR）的正式 `/api/v1/recognitions/{id}/result` 结果 JSON——扫完卡在识别详情页点「复制结果 JSON」，回本页点「📋 读剪贴板填写」或直接 `⌘`/`Ctrl`+`V`，按题号自动填对错与主观分，见 §5.1.1。OMR 导入只接受顶层 `recognition_id/template_id/mode/status/questions/unresolved`，明确拒绝旧 raw/items、裸数组和包装层。全部在前端完成，`/api/feedback` 零改动。同时修掉画廊缩略预览顶部凭空多出约 220px 空白的问题：`.gallery-preview` 上给旧版纯文本预览留的 `white-space:pre-wrap`，把 v1.10.0 起装进去的 qview 结构化 HTML 里标签之间的换行也渲染成了空行，见 §2.2 末尾。版本号提到 **v1.11.0**（`omrs/version.py` + HTML 侧栏 + 根 `README.md`）。

## v1.10.0

> **v1.10.0 共享题目视图（qview）+ 反馈工作台**：新增 `assets/qview.js`，把原来分散在 `viewQ()`、画廊卡 `.gallery-preview` 和 `instRender()` 的三份题目渲染副本收敛成一个组件，见 §2.2。基于它做了两件用户可见的事：① 题目 Modal 改双栏（题面 | 答案+备注+历史）、加宽到 1180px、支持 `←/→` 在当前列表上下文内翻页；② 反馈录入页从「一列表单」改成三栏工作台（题目列表 / 题目视图 / 判定面板），录反馈时能直接看题和就地编辑，见 §5.1。即时练习的题面/答案块也换成 qview。版本号提到 **v1.10.0**（`omrs/version.py` + HTML 侧栏）。

## v1.9.0

> **v1.9.0 题目停用机制**：题目库支持停用/恢复。停用题目保留 Markdown、题目库管理入口和 Ledger 历史，但不参与复习调度、行动推荐、统计、数据分析、反馈和复习导出；题目库筛选提供活动/仅停用/全部三种口径，仪表盘显示停用数。

## v1.8.2

> **v1.8.2 部分判定提交 + 吸顶概览**：反馈页不再要求本批所有题都先判定；点击「提交反馈」时只提交已经选择「对 / 错」的题，未判定题自动保留到下一批。`fb-tally` 以吸顶“灵动岛”样式显示总数、对/错/未判和进度条，滚动题目时持续可见；每道反馈题增加序号徽标，选择已部分录入的 Session 时仍显示该题在 Session 原始题目列表中的序号，不会因过滤已录入题而从 1 重新编号。HTML 的 `styles.css`、`schedule.js`、`feedback.js` 资源查询参数同步更新，避免浏览器缓存旧交互。

## v1.8.1

> **v1.8.1 分批反馈交互优化**：`GET /api/sessions` 与 `GET /api/session` 的每个 Session 现在附带 `feedback_uids`、`pending_uids`、`feedback_count`、`pending_count`、`feedback_complete`，按 Session 原始题目顺序去重。反馈页选择 Session 时调用 `fbRowsForSession()` 自动只载入 `pending_uids`，已录入题目不再进入编辑行；顶部显示 `已录入 / 总数` 与剩余题数，Session 列表按钮改为「继续录入」。一次提交成功后保留当前 Session，刷新数据并自动载入剩余题目；全部完成时显示无需重复提交。反馈 JSON 导入同样自动跳过该 Session 已录入 UID，并在状态栏报告跳过数量；手动反馈仍可通过「添加行」使用。

## v1.7.0

> **v1.7.0 行动推荐 + 目录页 + 深色对比度修订**：① 仪表盘顶部新增「行动推荐」卡（`#action-plan`，在「最近动态」上方），脚本 `assets/actions.js`，见 §1.1；② 侧栏在「题目库」和「复习调度」之间新增「目录」页（`#panel-catalog`，图标 `#i-tree`），脚本 `assets/catalog.js`，数据来自新接口 `GET /api/tree`，见 §2.1；③ `styles.css` 的 `[data-theme="dark"]` token 与若干写死浅色的规则按对比度重配，见 §12。版本号提到 **v1.7.0**（`omrs/version.py` + HTML 侧栏 `v1.7.0 · 本地服务`）。

## v1.5.0

> **v1.5.0 深色主题：暖石墨 Warm Graphite**：早期 v1.5.0 的「玻璃拟态」深色（半透明卡片 + `backdrop-filter` 模糊 + body 四道极光径向渐变 + 紫青 `--grad`/`--glow` 辉光 + 渐变裁切文字）整段下线，改为与浅色同源的「暖石墨」——浅色用近黑墨、深色用骨白墨，互为镜像。`[data-theme="dark"]` token 改为实色暖面（`--bg:#1a1916` 等暖中性梯度）、发丝描边、单色骨白墨：`--accent` 由紫 `#b794f6` 改骨白 `#ece7df`、`--accent-fg` 深墨，故 `.btn.primary` 成「浅底深字」与浅色「深底白字」镜像；语义色由霓虹 400 收成大地色（黏土红 / 鼠尾草绿 / 赭黄 / 灰灰蓝）。删除 `--grad`/`--glow` 与 body 极光、玻璃卡片 / 玻璃侧栏 / 渐变按钮 / 紫色激活态 / 渐变 `.stat-value` 等深色特例，卡片 / 数值 / 进度条 / 品牌块 / 激活态全部回退到 token 驱动（深色覆盖块由约 53 行瘦到 ~16 行）。图表内联色仍走 `var()`，自动跟随。版本号不变（仍 v1.5.0）。

## v1.4.2

> **v1.4.2 页面内部现代化（首批两页）**：即时练习 `instRender` 题头改「题 N/M + chip + 进度条」、`instRenderSide` 队列项右侧改状态圆点（对/错/当前/未答）；反馈录入 `renderFb` 改卡片行（对/错分段 + 分数滑杆 + 备注 + 按 UID 反查科目分类）并在顶部加实时对错统计条。字段与 `/api/feedback`、`/api/recommend` 接口不变。**侧边栏应用式 shell 为下一独立改动**。

## v1.4.0

> **v1.4.0 应用骨架（侧边栏 shell）**：顶部 `<header>` + `.tabs` 横条 → 左侧 `<aside class="sidebar">`（`.sidebar-brand` 品牌 + `.sidebar-nav`）+ `<main class="content">`（`.topbar` 页面标题 + 动作按钮）。导航项**仍是 `.tab[data-tab]` + `onclick="switchTab()"`**，`switchTab` 逻辑不变，只新增：按 `name→中文` 映射更新 `#topbar-title`。图标为 `<body>` 顶部一段隐藏 `<svg><symbol id="i-*">` 雪碧图，导航用 `<svg class="nav-ico"><use href="#i-*"/></svg>`（描边走 `currentColor`，无外部图标依赖）。`modal-overlay` 与 `datalist` 仍是 `.shell` 外的兄弟节点。响应式：≤860px 侧栏转为顶部横向滚动条。

## v1.3.0

> **v1.3.0 深色模式 + 现代化**：首次打开且本地没有主题设置时，`<head>` 启动脚本当前选择**深色**；之后由设置页「外观」切换并存 `localStorage('omrs-theme')`。内联脚本在首帧前给 `<html>` 打 `data-theme` / `data-invert-img` 防闪。`:root` 圆角加大（`--radius:14 / -sm:10 / -lg:20`）、恢复柔和阴影 `--card-shadow`、新增 `--accent-rgb`；`[data-theme="dark"]` 为完整深色 token。`dashboard.js`/`data.js` 图表颜色已**全部 token 化**（含 SVG fill/gradient 改 `var()`+opacity），深色可正确显示。深色 + 「反转题图」开启时，`.q-md / .q-body / .gallery-preview / .instant-md / .instant-notes` 内 `img` 套 `filter:invert(1)`（简易白↔黑，彩色一并反相，保色版待后续）。

## v1.2.0

> **v1.2.0 视觉刷新（精修暖色）**：`styles.css` 的 `:root` 收敛为「编辑式暖色」——卡片去阴影/去 stat-card 顶部彩条、发丝级分隔线。图表条 `.bar-fill.*`/`.chart-fill.*` 以 `rgba(var(--accent-rgb),…)` 淡入主色的渐变填充（见 L500–505 的 `linear-gradient` 段，后者覆盖早期纯色定义）。新增语义族变量 `--fam-review`（复习/绿）、`--fam-session`（Session/蓝）、`--fam-question`（题目/棕）、`--fam-system`（系统/灰），用于时间线圆点、commit 类型标签和仪表盘「最近动态」圆点。`:root` 下方保留一段注释版「夜间账本」深色 token，整段替换即切深色；但仪表盘雷达/热力/趋势图与散点仍有内联浅色需先改用 `var()` 才能正确切到深色。图表内联色尽量走 `var()`（散点已改）。
