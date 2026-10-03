# 前端：复习调度与即时练习

> **速查**
> - 职责：复习调度工作台、临时调度与常规 Session 的区别（即时练习见 `AI/frontend/instant.md`）
> - 入口：`assets/app/features/schedule/`（页面与三个工作区）、`assets/app/domain/sessions.js`（Session 列表）、`assets/app/domain/exporting.js`（导出下载）
> - 不变量：临时调度（TMP-）不建立常规 Session；常规 Session 走 Ledger `session.create`
> - 必跑测试：`tests/app/schedule.test.mjs`、`tests/app/arrange.test.mjs`、`tests/e2e/schedule.py`
> - 相关：`AI/frontend.md`（索引）

## 复习调度工作台（`features/schedule/`）

### 入口与状态

复习调度是 features 页面（v1.25.2 起）：页面契约在 `assets/app/features/schedule/index.js`，挂载点 `#panel-schedule`，本页只 morph 其中的 `#sch-app`（顶部标签栏、「安排复习」与「已有计划」）。三个工作区：

| 工作区 | 实现 | 说明 |
|---|---|---|
| 安排复习（默认） | 本页原生（v1.25.3 起；`arrange.js` 纯函数、`arrange-ctl.js` 控制器、`arrange-view.js` 模板，保留旧 id `#recommend-panel-v2`、`#rec-*`） | 见下「安排复习」；从别的工作区切回时重拉推荐 |
| 已有计划 | 本页原生（`#sch-plans`） | 见下「已有计划」 |
| 全题库导出 | 本页原生（v1.25.4 起；`exporter.js` 纯函数、`exporter-ctl.js`、`exporter-view.js`，保留 `#export-panel`、`#pick-*` 等旧 id） | 见下「全题库导出」；记住来处，「返回复习调度」回到它（`nextView(…, 'back')`） |

- 进入页面：同时刷新 Session 列表与拉推荐（原 `schEnter` 的做法）。标签页支持点击与 ←/→/Home/End（页面快捷键作用域，焦点跟随）。待完成计数在「已有计划」标签上。
- 页面事件 `schedule:view`（仪表盘「开始复习」发）、`schedule:open-plan`（带 Session id，页面先把计划筛选设回「待完成」再打开该计划）。没有全局入口；E2E 读的 `SCH_VIEW`、`REC_*` 等名字只在测试适配器 `tests/e2e/p8_test_modules.js` 里。
- **Session 列表归 `domain/sessions.js`**：`refreshSessions()` 后发先至时只认最新一次，失败保留旧列表并记原因；成功与失败都经 bus 发 `sessions`。生产不注入旧 `SESSIONS` 或 `refreshSessions`，旧断言由测试适配器提供。删除走 `deleteSession(id)`（服务端 `status: ok` 且 `deleted: true` 才算成功），成功后先在本地去掉，并让进行中的旧加载作废。

### 安排复习（本页原生）

- **候选**：`GET /api/recommend?due_count=1000&prof_count=1000`，到期题与熟练度题各带 `_source`；后发先至只认最新一次。重拉时已选题里仍可安排的换成新对象保留，不再可安排的移出并提示数量。加载中与失败显示在 `#rec-status-v2`（失败带「重试」）。
- **筛选**：科目、搜索、推荐方式在上；「更多筛选」（展开状态存页面状态）里有分类、知识点、状态、到期范围、难度与熟练度上下限、排序、标记匹配与标记按钮（`data-action="schedule.label"`）。语义与题库、导出共用（`domain/items.js` 的 `filterAll`，共享 `filterItems`）；排序为「按推荐方式」时恢复服务端顺序，再按推荐方式排：均衡 = 到期与熟练度两组内各按科目轮选，到期优先 = 先到期，薄弱优先 = 先熟练度来源。难度或熟练度范围不合法时列表为空、状态行说明原因。已生效的条件显示为可单独移除的按钮，另有「清除筛选」（保留推荐方式）。筛选变化不清空已选。
- **选择**：逐题勾选、「全选当前结果」、「只看已选」、按建议题量「按建议选择」（替换当前选择，题量须为正整数）。底部吸底的选择栏显示已选数、预计用时（每题 max(3, 难度×1.5) 分钟）、被筛选隐藏但仍会加入计划的数量（带「查看全部已选」）、「清空」与「生成计划」。
- **每行**：勾选、序号、UID（复燃题带「复燃 ×N」标签，停用题不算）、科目 · 分类 · 难度与标记、理由（复燃 → 「复燃 · 已休眠 N 天」；熟练度来源 → 「提前巩固 · N 天后到期」；到期来源按到期天数）、熟练度、「预览」（题目弹窗，上下文 `schedule-pick`）。候选为空时：没有可安排的题且有未完成计划 → 「查看已有计划」；其他情况 → 「清除筛选」。
- **生成计划**：`POST /api/confirm-schedule`（`persist: true`，全部已选的 `question_id` 与来源；只有一个科目时带 `subject`）。进行中按钮显示「正在生成…」并置灰，重复调用不重复提交。成功后清空选择，切到「已有计划」（筛选设回待完成），刷新 Session 列表并打开新计划，再重拉推荐；失败保留选择，状态行说明原因。

### 已有计划（本页原生）

- 筛选：计划状态（待完成 / 已完成 / 全部，`#sch-plan-filter`）与编号搜索（`#sch-plan-search`），存在页面状态里。列表每条是按钮：创建时间、状态标签、科目与题量、进度条、「已录入 x / 共 y 题」、编号。桌面左列表右详情；手机先列表，点计划进详情，「返回计划列表」回来。
- 详情：`GET /api/session?id=`，后发先至时只认最新一次；同一计划重拉（Session 列表刷新后）保留当前内容不闪骨架；失败在详情区给原因与「重试」。内容：标题、时间与编号、进度摘要、「录入结果」（切到反馈录入并选中该计划；已完成或全部录入时禁用）、导出打印版 / 屏幕版（`domain/exporting.js`，选项取打印选项；A4 先问单 / 双栏；结果写在 `#sch-status`，按钮进行中置忙）、「删除调度」、打印选项（展开状态与两个选项都存页面状态，重绘不丢）、题目列表（序号、UID、科目与分类、已录入 / 待录入、「预览」开题目弹窗，上下文 `schedule-plan`）。
- 删除：确认框说明关联反馈会一并撤销并重算熟练度和复习日期，题目正文保留，历史记录可恢复 Session。确认与请求期间按钮置忙；取消不发请求；业务错误提示「删除失败」并保留计划。成功后清空详情、若反馈页正在录这个计划则清表单与上次结果（bus `feedback:reset` / `feedback:clear-results`），再刷新统计快照、题目缓存、Session 列表与推荐；其中任何一步失败提示「页面刷新失败」。
- 列表加载中与失败显示在 `#sch-session-status`（失败带「重试」）；没有计划时空状态带「安排新复习」。

### 列表 / 画廊视图

候选区可切「列表 / 画廊」（`#rec-view-list` / `#rec-view-gallery`），偏好存在 `localStorage['omrs-schedule-view']`，未知值回退列表；切换只改呈现，不重拉、不清筛选与已选。画廊卡的题面复用共享 qview：`qvRender(挂载点, uid, {...QV_CARD_OPTS, clamp: 8})`，只显示题面；挂载点带 `data-morph="skip"`，进入视口（提前 240px）才挂，重绘不重挂。桌面自适应卡片网格，≤760px 单列；卡片内题面有高度上限、内部滚动。手机上列表每行两行：勾选与题目一行，理由、熟练度与「预览」一行。

### 来源标记

每道题携带 `_source` 字段（`due` / `proficiency`），在反馈时决定 SM-2 排期策略：
- `due`：到期来源 → 标准 SM-2 全量更新
- `proficiency`：熟练度来源 → 答对时间隔 × 0.7 折中

调度页的新页面始终传 `persist:true`，因此即使只选 1 题也创建正式 `EXP-` Session；旧调用不传该字段时仍保留单题 `TMP-` 兼容行为。

## 即时练习

即时练习已迁到 `assets/app/features/instant/`，交互、渲染与快捷键见 `AI/frontend/instant.md`。它与复习调度的区别见下表。

## 临时调度 vs 常规 Session

| 维度 | 自定义练习（TMP） | 常规 Session（EXP） |
|---|---|---|
| 选题方式 | 前端手动筛选勾选 | 双列表推荐 + 勾选确认 |
| 持久化 | 不写 Session 投影 | 写入 Ledger 与 Session 投影 |
| 批次号前缀 | `TMP-YYYYMMDDHHMMSS` | `EXP-YYYYMMDDHHmmss` |
| SM-2 影响 | 反馈同样更新 Interval/Due_Date（无 Session 来源时按 `due` 处理，可逐题传 `source`） | 根据来源差异化更新 |
| 反馈闭环 | 可选 | 必须反馈 |
| 导出方式 | `POST /api/export` 传 `question_refs` | `POST /api/export` 传 `session_id` |

### 全题库导出（本页原生）

- **筛选**：搜索、科目、分类、状态、知识点、难度与熟练度上下限、排序（默认熟练度升序）、标记匹配与标记按钮；语义与题库共用（默认排除停用题）。
- **已选**：有序 uid 列表，离开页面再回来还在；题目从题库消失时自动剔除。「选择当前筛选」「移除当前筛选」「清空已选」；每题「加入 / 移除」「预览」（上下文 `export` / `export-selection`）。已选区超过约 22em 内部滚动，不把选题区挤远。
- **呈现**：平铺式（UID、科目 · 分类 · 难度 · 熟练度 · 上次复习、状态与标记、至多 4 个知识点）或画廊式（卡片带 qview 题面，进入视口才挂，`data-morph="skip"`）。
- **导出**：A4 打印版（可选附带答案、题间留白 0–20 行）或屏幕版（始终附带答案，这两项禁用）。A4 先问单 / 双栏（关掉对话框按单栏）。`POST /api/export`（`uids`、`format`、`include_answers`、`question_gap_lines`、`a4_two_columns`），下载 `OMRS-Export-<版本>.html`；没选题、成功与失败都写在 `#export-status`。

打开某个计划的入口只有总线事件 `schedule:open-plan`（控制器方法 `openPlan`），旧的 `schOpenPlan` 全局已不存在。导出页的熟练度百分比用 `core/format.js` 的 `formatPercent`。

## 稳定身份与不可用条目

安排和全库导出的选择以 `question_id` 保存；刷新后同一身份可显示移动后的 UID，已归档身份被移出选择，复用旧 UID 的新题不会自动补入。新导出发送有序 `question_refs:[{question_id}]`，在 A4 排版确认前冻结引用。

计划详情按 `entries` 展示固定编号与 `availability`：active 可以预览与反馈，archived / suspended 保留位置并说明状态，unresolved 显示「绑定题目」。绑定复用 `domain/question/picker.js`，人工确认后调用 `/api/session/bind`，保留原 Session 历史并追加绑定提交；绑定前禁止反馈或导出。存在不可用条目时导出按钮禁用，仍可反馈其余 active 项。UID-only 导入不会全库解析；身份不确定时必须先绑定。

计划详情的预览按钮及 `schedule-plan` 翻页上下文按条目的稳定 `question_id` 保存。详情仍显示旧UID而全局题库已更新时，移动或复用编号不会把预览及下一题切换到新身份。


## 外部正式计划

获授权的 MCP create_review_session 生成与网页共用的正式 EXP Session，在已有计划中查看、录入反馈或撤销；网页交互契约保持。所有正式创建保留历史编号，包含已撤销及学习状态恢复排除的计划，避免技术重试查到同秒新建的另一计划。MCP 详细查询包含全部停用的 active 计划并显示可用状态，网页原有列表隐藏规则保持。
