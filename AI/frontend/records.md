# 前端：历史记录、数据复盘与报告

> **速查**
> - 职责：Ledger 时间线、数据复盘页、AI 报告托管页
> - 入口：`assets/app/features/history/`、`assets/app/features/data/`（数据复盘）、`assets/app/features/reports/`
> - 不变量：历史修正只在「修正模式」下可用；报告在 sandbox 中渲染，不获得 OMRS 同源权限
> - 必跑测试：`tests/test_history_projection.py`、`tests/app/history.test.mjs`、`tests/e2e/history.py`、`tests/test_report_export.py`、`tests/app/reports.test.mjs`、`tests/e2e/reports.py`、`tests/app/analytics.test.mjs`、`tests/e2e/data.py`
> - 相关：`AI/frontend.md`（索引）

## 历史记录页

历史页由 `features/history/` 按页面契约挂载到 `#hist-app`，读取 `/api/history` 的 Ledger commit。`index.js` 管理加载与修正请求，`state.js` 投影视图状态，`view.js` 渲染时间线，`history.css` 提供样式。`domain/history-model.js` 持有撤销状态、节点分类、标题、时间格式与排序的纯函数；`domain/history.js` 负责读取、修正请求和跨页通知，仪表盘最近动态直接复用同一投影。

- 视觉结构为竖线时间线：旧节点在上方，最新节点在底部，进入页面后自动滚到底部；主时间线只展示非修正、且**当前未被撤销**的节点。
- **节点按 commit 族着色**：`historyCommitFamily(commit_type)` 决定 `data-family`，圆点和节点标题据此取语义色。`review.batch_submit` 节点额外由 `reviewVisual()` 渲染「对错配比条 + 每题色块」，不展开即可看出本批练习结果。
- 顶部提供排序选择：`旧 → 新（最新在底部）` 或 `新 → 旧（最新在顶部）`，选择会保存在浏览器本地。
- 顶部提供「修正模式」开关：默认关闭，主节点只读；开启后才显示 `修改 / 撤销 / 还原` 操作面板，避免日常浏览时误触危险操作。
- 顶部提供「修正记录」按钮：`review.replace`、`review.retract`、`review.restore`、`session.retract`、`session.restore`、`state.restore` 等修正节点从主时间线移出，集中在该列表里查看。
- **被撤销的节点从主时间线隐藏**：优先使用 `/api/history` 返回的完整链 `retraction_state`；旧响应则回退到 `historyRetractionState()` 按 seq 顺序重放 `session.retract/restore`、`review.retract/restore`。`session.create` 整个 Session 被撤销、或 `review.batch_submit` 批次内所有反馈都被撤销（或其 Session 被撤销）时，该主节点（`isNodeRetracted`）不再显示，状态栏提示「N 个已撤销已隐藏」。Ledger 底层仍保留全部 commit，不做删除。
- 隐藏的节点可在「修正记录」面板恢复：被撤销且**当前仍处于撤销态**的 `session.retract` / `review.retract` 修正行带「恢复」按钮，点按调用对应 restore API 追加新 commit，节点随即回到主时间线。
- 每个节点显示时间、题目优先摘要、副标题、commit_id、source、seq 和 commit_type；`formatLedgerTime()` 将带时区偏移的 Ledger `created_at` 按设置页时区显示，仪表盘最近动态复用同一格式化函数；`review.batch_submit` 标题优先展示 UID（单题直接显示题目，多题显示前几题），副标题再显示有效题数、对错和已撤销条数。
- 节点默认只显示头部数据；下方挂只读 `查看详情` 折叠块。开启修正模式后，再额外显示默认关闭的 `修改 / 撤销 / 还原` 操作折叠块。
- 无可操作内容的节点（如 `legacy.bootstrap`、外部扫描类）**不显示**操作折叠块，只保留 `查看详情`。
- `legacy.bootstrap` 等大 payload 会在「查看详情」里做摘要/截断，避免页面被完整迁移数据撑爆。
- 操作折叠块内的面板：
  - `review.batch_submit`：选择批次内某条反馈，执行修改、撤销、恢复。
  - 含 `session_id` 的节点：撤销整次 Session 或恢复 Session。
  - 非 genesis 节点：追加 `state.restore`，还原结构化状态到该 seq。
- 所有按钮都调用历史修正 API 追加新 commit，不会修改旧节点。
- 修正请求统一返回 `{ok, data, error}`。请求期间操作按钮置忙；成功后依次清题目详情缓存、重载统计与 Session、发 `history:changed` 通知仪表盘，再重拉时间线。刷新失败时保留现有列表并显示原因；首次加载超过 300ms 才显示骨架。

## 数据页（复盘，`features/data/`，v1.25.1 起）

> 对应 Tab：「数据复盘」（位于「仪表盘」与「题目库」之间）；面板 `#panel-data`；数据来源 `GET /api/analytics` 与统计快照（`store.data`）；导出 `GET /api/export-review`。

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
| 顽固题 / 屡练不熟 | `leeches` / `struggling` | 表格；「查看」开题目弹窗（上下文 `leech`，可翻页），「加入展示板」开选板浮层 |

- 百分比与语气：`pct(v)`（空值显示「—」）、`accTone(v)`（≥80% success、≥50% warning、其余 danger、空值 muted）。`by_hour` 的键是字符串，按 `h` 与 `String(h)` 都取。

### 导出

「导出复盘报告」`fetch('/api/export-review')` 后经 `core/download.js` 存成文件：文件名取 `Content-Disposition`（含 `filename*=UTF-8''` 中文名），没有时用 `OMRS-复盘-日期.md`。成功弹 toast「已导出 …」，失败把原因写在页首 `#data-status`。该页依赖实时计算，没有演示数据回退。

## 报告页（AI 报告托管）

> 对应 Tab：`报告`（历史记录与设置之间）；面板 `#panel-reports` 的 `#rp-app` 由 `features/reports/` 挂载。后端见 `omrs/reports.py` 与 api.md 报告端点。

- **创建**：填名称 + 用 `ui/filedrop` 拖入或选择 `.html` / `.htm` 文件 → `FileReader.readAsText` 读出文本，`POST /api/report/create {name, html}`。非 HTML、空文件、读取失败都在上传区或状态栏显示原因；上传期间按钮置忙并阻止重复提交。
- **准备 AI 材料**：创建卡片提供「复制 AI 报告提示词」和「下载分析数据」。`#rp-include-images` 控制是否带题图：关闭时下载 Markdown；开启时请求 `/api/export-review?include_images=1` 下载 Markdown + `images/` 的 ZIP。提示词同步切换图片约束，并要求 AI 只返回可直接上传的完整单文件 HTML、不得虚构数据。报告允许通过 HTTPS 使用外部字体、图表和图标资源，但禁止广告/追踪脚本，并要求依赖加载失败时核心内容仍可阅读。
- **列表**：挂载和刷新时读取 `/api/reports`，失败保留现有列表并显示原因；每行列出名称、创建时间、大小和 id。
- **浏览**：点「浏览」后在页面下方用 `iframe sandbox="allow-scripts allow-downloads allow-popups"` 预览，不带 `allow-same-origin`；「新标签打开」沿用 `/api/report/view?id=...`。报告脚本运行于独立来源的 CSP 沙箱；后端为静态题图 URL 加单图签名，图片仍可加载，脚本不能读取 OMRS API。
- **删除**：先用 `ui/dialog` 确认，再 `POST /api/report/delete`；成功后重拉列表。进入报告页时读取列表，离开后迟到的结果不再渲染。

### 报告如何引用题目图片（与后端对接）

AI 生成报告时，对某道题用 `<img src="/api/image?name=<URL编码文件名>">` 即可显示其原图（让人一眼认出是哪道题）。文件名来源：`/api/question?uid=` 或 items 的 `images` 字段、或导出复盘报告 JSON。即使下载了含 `images/` 的 ZIP，该目录也只供 AI 读取，最终 HTML 仍不得引用相对路径、`file://` 或 base64。仅在“由本程序托管 + 在程序内打开”时 `/api/image` 才加载（同源）；脱离服务直接双击本地 HTML 不会显示题图。
