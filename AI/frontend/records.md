# 前端：历史记录、数据复盘与报告

> **速查**
> - 职责：学习与变更时间线、MCP 系统运行记录、数据复盘页、AI 报告托管页
> - 入口：`assets/app/features/history/`、`assets/app/features/data/`（数据复盘）、`assets/app/features/reports/`
> - 不变量：学习修正只在「修正模式」下可用；系统运行详情只读并链接审核中心；报告在 sandbox 中渲染，不获得 OMRS 同源权限
> - 必跑测试：`tests/test_history_projection.py`、`tests/app/history.test.mjs`、`tests/app/runtime-history.test.mjs`、`tests/e2e/history.py`、`tests/test_runtime_records.py`、`tests/e2e/runtime_history.py`、`tests/test_report_export.py`、`tests/app/reports.test.mjs`、`tests/e2e/reports.py`、`tests/app/analytics.test.mjs`、`tests/e2e/data.py`
> - 相关：`AI/frontend.md`（索引）

## 历史记录页

历史页由 `features/history/` 按页面契约挂载到 `#hist-app`，分为「学习与变更」和「系统运行」。两区按设置页的 Ledger 时区分日，列表选中记录后在右侧显示详情；≤760px 在列表与详情之间切换，返回时还焦点到原记录。标签页支持方向键、Home、End。样式沿用共享 token 和控件，深浅主题共用布局。

`index.js` 管理学习加载与原有修正操作，`runtime-controller.js` 管理系统分页、详情与进行中轮询；`state.js` 负责分组、时区日界线和状态，`view.js` 渲染外框，`learning-view.js` / `runtime-view.js` 渲染各区详情。`domain/history-model.js` 持有撤销状态、节点分类、标题和时间投影的纯函数；`domain/history.js` 负责两类读取、修正请求和跨页通知，仪表盘最近动态仍读取 Ledger。

### 学习与变更

- 默认最新在前，保留用户已有升序或降序偏好；支持搜索和全部时间、今天、最近 7 / 30 天。筛选先于服务器分页，时间区间以所选时区的本地午夜计算，覆盖夏令时。
- `/api/history?view=summary` 首屏读取最近 60 条摘要，「加载更早记录」按游标追加。升序前插、降序追加都保留可见节点的滚动锚点。列表只显示中文动作、摘要、时分和来源，提交 ID 与类型放入详情。
- 主时间线只展示非修正且当前未撤销的节点。修正状态优先取后端完整链 `retraction_state`，旧响应回退到按 seq 重放。整次 Session 或整批反馈被撤销后主节点隐藏，状态栏显示隐藏数量；底层 Ledger 不删除。
- 选择记录后按需读取 `/api/history/detail`。反馈详情显示科目分布、提交时的题面短句、对错色条和色块；逐题与技术详情默认折叠。字段变化、移动分类和正文短差异取当时事件，旧快照缺失明确显示「无可用历史摘要」，不以当前题目补历史。迁移大载荷按现有摘要 / 截断规则显示。
- 草稿人工入库节点的「来源调用」能返回对应 MCP 调用，包含首屏以外的记录；跳转时清空筛选并按编号读取详情。旧草稿没有调用记录时明确说明缺失，关联存储读取失败显示原因且不阻断学习详情。
- 「修正记录」集中显示 `review.replace/retract/restore`、`session.retract/restore`、`state.restore` 等修正节点；仍处于撤销态的修正行在修正模式下提供「恢复」。
- 修正模式默认关闭，偏好存于浏览器。开启后所选记录的「修改 / 撤销 / 还原」面板支持原有反馈修改、撤销和恢复，整次 Session 撤销和恢复，以及非起始节点的结构化状态还原。所有写操作只追加新 commit。
- 请求期间禁用全部修正写操作，重绘保留展开面板。成功后清题目缓存、重载统计与 Session、发 `history:changed` 通知，再读取历史；刷新失败保留旧列表并显示原因。首次等待超过 300ms 才显示骨架，详情失败可单独重试。筛选改变立即使旧列表请求失效，卸载后迟到结果不重绘。

### 系统运行

- 展示真实 MCP 工具调用。每行包含工具中文动作、白名单范围与结果摘要、密钥名称快照、状态和耗时；支持时间、搜索、密钥及执行/确认状态筛选，确认状态见下方「MCP 网页确认」。默认全部时间、最新在前，不补造旧调用。
- `/api/runtime/records` 每页 60 条，筛选先于分页；顶部总次数、失败、进行中和中断统计覆盖筛选全集，底部显示实际加载条数。空记录、无匹配、首次失败和已有结果刷新失败各有明确说明。
- 详情按需读取 `/api/runtime/records/detail`，显示状态、固定安全错误说明、时间、密钥、耗时和调用性质；参数摘要、结果摘要、技术信息默认折叠。详情与列表刷新失败保留上次成功数据，可以重试。
- 有关联草稿时显示当前状态并通过 `domain/drafts.js` 的 `openDraft` 进入既有审核页；人工入库后显示 Ledger 关联节点，并能跳到「学习与变更」。不存在的草稿禁用查看入口；幂等复用记录显示「复用已有草稿」。系统记录保留只读摘要；关联写操作进入审核中心核对与决定。
- 当前系统区存在进行中调用时每 2.5 秒轮询；结束后同步更新列表与所选详情。刷新覆盖已加载范围，保留已翻页记录；离开系统区或页面卸载停止轮询并使旧列表请求失效。切换筛选不会被迟到响应覆盖，搜索防抖 250ms 且保留输入焦点和光标。

## 数据页（复盘，`features/data/`，v1.25.1 起）

> 对应 Tab：「数据复盘」（位于「仪表盘」与「题目库」之间）；面板 `#panel-data`；数据来源 `GET /api/analytics` 与统计快照（`store.data`）；导出 `GET /api/export-review`。

页面统计快照沿用 `get_stats` 的默认全局范围；助手/MCP 科目概况通过同一内部入口限定科目，不改变页面请求。平均熟练度由原始行最后舍入，停用题按 CSV 与当前投影状态排除。

- **文件**：`index.js`（页面契约 `id: 'data'`、控制器）、`state.js`（把 analytics 整理成视图行的纯函数）、`charts.js`（三张 SVG）、`view.js`、`data.css`；node 单测 `tests/app/analytics.test.mjs`，E2E `tests/e2e/data.py`。
- **何时拉数据**：每次进入页面、点「刷新」、以及统计快照变化（写操作之后 `reloadData()`）时重拉 `/api/analytics`；首次加载超过 300ms 才出骨架。失败时：没有旧数据就在页面位置显示原因与「重试」，有旧数据则保留旧数据、只在页首报错。
- **「每日练习趋势」「标记分布」**直接取统计快照（`daily_trend`、未停用题的 `labels`），随快照自动更新。
- **版式**：说明与动作（「刷新」「导出复盘报告」）→ 八格概览 → 图表卡自动成两栏（`minmax(32em, 1fr)`；按标记正确率、复习预警、顽固题、屡练不熟整行）。卡片标题不带 emoji；模板不写 `style=`：横条是原生 `<progress>`（`ui/progress`，`info` 语气由 `data.css` 补），表格是 `ui/table`（手机降级为卡片），颜色一律 `data-tone` 映射到状态 token。
- **字号**：xl 20（概览数字）、lg 16（卡片标题）、sm 13（说明、表格、数值）、xs 12（标签、坐标轴、元信息）；SVG 文字的字号与颜色在 CSS 里，属性里不写。
- `#data-status` 是页首的元信息行（数据基准时间 / 刷新或导出失败的原因），`tests/visual/run.py` 的 `MASKS` 按这个 id 遮住实时时间。

### 展示区块（顺序同旧页）

| 区块 | data-key | 形式 |
|---|---|---|
| 概览（两行各 4 格） | `kpis` | 总复习（答对 / 答错）、总体正确率、当前连续（最长）、顽固题（从未复习）；平均熟练度（衰减后）、平均 EF（平均复习次数）、活跃天数（自首次）、近 30 天复习（近 7 天） |
| 每日练习趋势 | `trend` | 摘要三格 + 平滑折线（峰值点另色），近 30 天 |
| 标记分布 | `labels` | 标记芯片 + 横条 + 题数 |
| 科目维度 | `subjects` | 雷达图（科目 ≥3 才画）+ 表格（最薄弱在前） |
| 分类维度 | `categories` | 表格，最薄弱 15 个 |
| 难度与熟练度 | `scatter` | 难度 1–10 × 熟练度 5 档分箱的气泡：半径 = 题数（`sqrt(count)`，封顶 26），颜色 = 该格平均熟练度（≥70% 高、≥45% 中、其余低），悬停看题数与均值 |
| 熟练度分布（原始 / 衰减后）、EF、难度、连续答对、复习间隔 | `mastery` `decayed` `ef` `difficulty` `repetition` `interval` | 横条；分档配色同旧页（熟练度 0–2 档危险、3–5 拉升、6–7 稳定、8–9 掌握） |
| 各主观分正确率 | `score` | 横条，值为「正确率（次数）」，只列有反馈的分数 |
| 按周正确率 | `weekly` | 表格，近 12 周 |
| 按星期 / 按时段复习量 | `weekday` / `hour` | 横条 / 24 格热力（级别 0–4 按占峰值比例，悬停看次数） |
| 未来 7 天到期预测 | `forecast` | 横条：今日、+1…+7 天、7 天以后 |
| 按标记正确率与平均分 | `label-acc` | 表格 |
| 复习预警 | `alerts` | 六格：逾期、今日到期、未来 3 天、未来 7 天、未到期低熟练度、顽固题 |
| 顽固题 / 屡练不熟 | `leeches` / `struggling` | 表格；「查看」开题目弹窗（上下文 `leech`，可翻页），「加入展示板」经 `domain/board/index.js` 开选板浮层 |

- 百分比与语气：`pct(v)`（空值显示「—」）、`accTone(v)`（≥80% success、≥50% warning、其余 danger、空值 muted）。`by_hour` 的键是字符串，按 `h` 与 `String(h)` 都取。

### 导出

「导出复盘报告」`fetch('/api/export-review')` 后经 `core/download.js` 存成文件：文件名取 `Content-Disposition`（含 `filename*=UTF-8''` 中文名），没有时用 `OMRS-复盘-日期.md`。成功弹 toast「已导出 …」，失败把原因写在页首 `#data-status`。该页依赖实时计算，没有演示数据回退。

## 报告页（AI 报告托管）

> 对应 Tab：`报告`（历史记录与设置之间）；面板 `#panel-reports` 的 `#rp-app` 由 `features/reports/` 挂载。后端见 `omrs/reports.py` 与 api.md 报告端点。

- **创建**：填名称 + 用 `ui/filedrop` 拖入或选择 `.html` / `.htm` 文件 → `FileReader.readAsText` 读出文本，`POST /api/report/create {name, html}`。非 HTML、空文件、读取失败都在上传区或状态栏显示原因；上传期间按钮置忙并阻止重复提交。
- **准备 AI 材料**：创建卡片提供「复制 AI 报告提示词」和「下载分析数据」。`#rp-include-images` 控制是否带题图：关闭时下载 Markdown；开启时请求 `/api/export-review?include_images=1` 下载 Markdown + `images/` 的 ZIP。提示词同步切换图片约束，并要求 AI 只返回可直接上传的完整单文件 HTML、不得虚构数据。报告允许通过 HTTPS 使用外部字体、图表和图标资源，但禁止广告/追踪脚本，并要求依赖加载失败时核心内容仍可阅读。
- **列表**：挂载和刷新时读取 `/api/reports`，失败保留现有列表并显示原因；每行列出名称、创建时间、大小和 id。
- **浏览**：点「浏览」后在页面下方用 `iframe sandbox="allow-scripts allow-downloads allow-popups"` 预览，不带 `allow-same-origin`；「新标签打开」沿用 `/api/report/view?id=...`。报告脚本运行于独立来源的 CSP 沙箱；后端为静态题图 URL 加单图签名，图片仍可加载，脚本不能读取 OMRS API。
- **删除**：先用 `ui/dialog` 确认，再 `POST /api/report/delete`；提交期间禁用报告操作，避免重复删除，成功后重拉列表。首次列表请求超过 300ms 才显示骨架；失败时列表旁显示原因和「重试」。进入报告页时读取列表，离开后迟到的结果不再渲染。

### 报告如何引用题目图片（与后端对接）

AI 生成报告时，对某道题用 `<img src="/api/image?name=<URL编码文件名>">` 即可显示其原图（让人一眼认出是哪道题）。文件名来源：`/api/question?uid=` 或 items 的 `images` 字段、或导出复盘报告 JSON。即使下载了含 `images/` 的 ZIP，该目录也只供 AI 读取，最终 HTML 仍不得引用相对路径、`file://` 或 base64。仅在“由本程序托管 + 在程序内打开”时 `/api/image` 才加载（同源）；脱离服务直接双击本地 HTML 不会显示题图。

## 详细分析范围

共享分析入口支持先筛选科目/分类再聚合，分类桶以科目加分类区分。日期仅筛选练习行为指标，熟练度和预测仍是当前快照。报告网页沿用沙箱预览，可查看由获授权 MCP 保存的报告。

## 关联审核

系统运行详情展示调用轨迹和已核实关联，提供「查看审核记录」进入 `#/ai-review?operation=编号`，不再提供独立批准 / 拒绝按钮。旧 `#/history?operation=编号` 直接兼容跳转审核中心；PIN 登录保留完整 hash。当前提案、修订版本和执行结果以中心接口为准，系统运行记录继续保存只读脱敏摘要。

运行详情按脱敏 board_id / report_id / export_id 显示领域入口；展示板走既有 domain 详情端口，报告打开沙箱接口，HTML 快照通过受 Web 登录保护的下载端点取得，提示 24 小时期限。草稿关联经 `domain/drafts.js` 跳中心，人工入库仍可往返学习记录与来源调用。
