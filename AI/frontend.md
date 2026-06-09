# 前端

> 入口：`omrs_dashboard.html`（仅结构）。样式与脚本拆分到 `assets/` 资源文件夹。

无第三方依赖、无构建步骤，所有图表使用纯 CSS + 内联 SVG 实现。

## 文件组织（assets/）

```
omrs_dashboard.html   ← 仅 HTML 结构，<link> 引样式 + 7 个 <script> 引脚本
assets/
├── styles.css        ← 全部样式（原 <style> 内联块抽出）
├── core.js           ← 全局状态、api()、通用工具/筛选/Markdown 渲染
├── dashboard.js      ← 仪表盘图表 renderDash
├── questions.js      ← 题目库表格/画廊视图 + 题目 Modal
├── schedule.js       ← 复习调度：导出选题、Session 列表/创建/预览/删除
├── recommend.js      ← 推荐面板（双列表 + 勾选确认）
├── data.js           ← 数据复盘页 + 复盘报告导出
├── reports.js        ← 报告托管页：列表/上传创建/浏览/删除
└── app.js            ← 应用入口：switchTab/reloadData/设置 + 录入页图片粘贴/AI 识别/AI 设置 + init()
```

**加载约定（重要）：**
- 脚本均为普通 `<script>`（非 ES module），共享同一全局作用域；顶层 `let`/`const` 跨文件可见，行内 `onclick` 仍可直接调用各函数。
- **加载顺序固定**：`core.js` 最先（定义全部全局变量，只能声明一次，不可在其他文件重复 `let`）；`app.js` 最后（末尾 `init()` 自调用，依赖前面所有文件已就绪）。
- 后端由 `/assets/<file>` 通用静态路由提供（`server.py` → `_serve_asset()`，含路径穿越防护与按扩展名的 content-type）。原 `/omrs_dashboard.js` 路由已移除。
- 修改样式 → 改 `assets/styles.css`；改某模块行为 → 改对应 `assets/*.js`；新增全局工具 → 放 `core.js`。

---

## 1. 仪表盘图表（`renderDash()`）

| 图表 | HTML 容器 | 数据来源 | 实现方式 |
|---|---|---|---|
| 熟练度分布直方图 | `chart-mastery` | `stats.mastery_histogram` | CSS flex 横向条形图，10 个桶固定渲染；`30-60%` 使用 `.bar-fill.yellow`，`90-100%` 桶显示 `Mastery ∈ [0.9, 1.0]` |
| 每日练习趋势 | `chart-trend` | `stats.daily_trend` | SVG `<polyline>` + `<linearGradient>` 面积图 |
| 难度-熟练度散点图 | `chart-scatter` | `stats.scatter_data` | SVG `<circle>`，悬停显示 UID tooltip |
| 待复习队列预警 | `chart-alerts` | `stats.review_alert` | 四宫格彩色卡片 |

预警指标定义（后端 `stats.py` 计算）：
- **急需复习**：衰减后熟练度 < 30% 且超过 7 天未复习
- **警告队列**：衰减后熟练度 < 50% 且超过 14 天未复习
- **长期冷落**：超过 30 天未复习
- **建议今日**：调度优先级 > 0.3

---

## 2. 双视图

### 平铺式（List View）
- 高密度列表，每行显示 UID、科目、分类、难度、熟练度进度条、标签。
- 可直接点击加入/移除临时调度选题。

### 画廊式（Gallery View）
- 卡片形式，异步拉取 `/api/question?uid=...` 渲染题面。
- 卡片中同样使用 `.m-bar` / `.m-bar-fill` 渲染熟练度进度条。
- 题面中的 `![[图片.png]]`、`![[图片.png|300]]`、`![alt](路径)` 均改写为 `/api/image?name=...`。
- 使用 `renderMdContent()` 统一处理 HTML 转义与图片替换。
- 题目详情缓存在 `QUESTION_CACHE` / `QUESTION_PENDING`，避免重复请求。

---

## 3. 筛选控件（`filterItems()`）

全局筛选，题库页和临时调度页共用：

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
- **自定义练习** → 全题库筛选面板（与旧版临时调度相同，生成 TMP- 批次）

### 推荐面板流程

1. `GET /api/recommend` 获取双列表（到期 + 熟练度，互斥不重复）
2. 用户勾选题目（两侧列表均可勾选），实时显示已选计数 + 预计耗时
3. 可选操作：
   - **预览计划**：展示 4 种视图（列表/卡片/分组/时间）
   - **一键智能确认**：自动勾选到期列表前 N 道题
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

## 5. 临时调度 vs 常规 Session

| 维度 | 自定义练习（TMP） | 常规 Session（EXP） |
|---|---|---|
| 选题方式 | 前端手动筛选勾选 | 双列表推荐 + 勾选确认 |
| 持久化 | 不写 `sessions.csv` | 写入 `sessions.csv` |
| 批次号前缀 | `TMP-YYYYMMDDHHMMSS` | `EXP-YYYYMMDDHHmmss` |
| SM-2 影响 | 不更新 Interval/Due_Date | 根据来源差异化更新 |
| 反馈闭环 | 可选 | 必须反馈 |
| 导出方式 | `POST /api/export` 传 `uids` | `POST /api/export` 传 `session_id` |

自定义练习操作：
- 当前筛选全选
- 当前筛选批量移除
- 清空已选
- 生成自定义练习（TMP-）
- 直接导出 HTML（A4 打印版 / 屏幕版）

---

## 6. 设置页面（`panel-settings`）

位于「设置」标签页，包含以下功能卡片：

### 服务设置
- **允许外部访问**：开关绑定 `config.allow_external`。
  - 关闭（默认）：服务器绑定 `127.0.0.1`，仅限本机访问。
  - 开启：服务器绑定 `0.0.0.0`，局域网/公网可访问。
- **保存并重启**：先 `POST /api/config` 保存配置，再 `POST /api/restart` 触发重启。前端在请求成功后延迟 2.5 秒自动刷新页面。
- **立即重启**：直接调用 `POST /api/restart`，不修改配置。

重启期间前端预期连接中断，catch 后不报错，继续等待刷新。

### AI 自动识别
- 字段：`#st-ai-base`（API 地址，OpenAI 兼容，如 `https://api.openai.com/v1`）、`#st-ai-key`（API Key，密码框 + `#st-ai-key-toggle` 显隐切换）、`#st-ai-model`（模型名，带常见模型 datalist）、`#st-ai-restrict`（复选框「仅从已有知识点中选择」，对应 `config.ai_restrict_tags`，默认勾选）。
- **保存 AI 配置**：`saveAiSettings()` → `POST /api/config {ai_base_url, ai_api_key, ai_model, ai_restrict_tags}`。**不重启**（`load_config` 每次读盘，保存即生效）；状态写入 `#st-ai-settings-status`。
- `loadSettings()` 进入设置页时一并回填四项（与 `allow_external` 同批 `GET /api/config`；`#st-ai-restrict` 按 `cfg.ai_restrict_tags!==false` 置勾，即默认开）。
- `ai_restrict_tags` 开关含义：开启时 `classify` 的知识点被后端硬过滤为「已有分类 ∪ 已有知识点」；关闭时允许 AI 在无贴切已有项时新建知识点（仍优先复用，上限 4 个）。仅影响知识点，**科目/分类一直允许新建**。
- 仅作配置入口；实际识别在「录入题目」页触发，调用 `POST /api/ai-recognize`（后端转发，见 api.md）。

### 关于
展示项目基本信息（入口文件、前端文件、数据目录）和重启提示。

---

## 7. 录入题目页（`panel-create`）与提交后表单状态

> 脚本分布：表单提交 `doCreate` / 重置 `resetCreateForm` 在 `assets/schedule.js`；科目/分类 datalist `populateCreateLists` 在 `core.js`；**图片处理、AI 识别、AI 设置**在 `assets/app.js`；题目图与答案图分别暂存在全局 `CR_Q_IMAGES` / `CR_A_IMAGES`（`CR_IMG_SEQ` 为自增 id），均在 `core.js` 声明。

录入页左卡有两个图片区，各配一个 AI 按钮，可混用手动录入：
- **题目图片区**（`#cr-q-paste` / `#cr-q-file` / `#cr-q-images`）：粘贴/拖拽/点击选择题目截图，随题保存并嵌入 `# 题目`。按钮 **「🤖 提取并填充信息」**（`#cr-classify-btn`）→ `crClassify()` 取第 1 张题目图 `POST /api/ai-recognize {mode:'classify', subject, category}`，回填**科目/分类/难度/相关知识点**（不抄题、不解题）。其中 `knowledge_tags` 是否限定在「已有分类 ∪ 已有知识点」由设置页 `ai_restrict_tags` 开关决定（默认开=硬约束；关=允许新建，上限 4 个）。**用户已填的科目/分类会作为 hint 传给模型（要求其沿用），且前端只填空缺项、不覆盖已填值；知识点与已填的合并去重；难度给估计值。** 状态写 `#cr-classify-status`。
- **答案图片区**（`#cr-a-paste` / `#cr-a-file` / `#cr-a-images`）：粘贴/拖拽/点击选择答案截图，嵌入 `# 答案`。按钮 **「🤖 提取答案」**（`#cr-extract-btn`）→ `crExtractAnswer()` 取第 1 张答案图 `POST /api/ai-recognize {mode:'answer'}`，把答案/解析**提取为文本**填入 `#cr-answer`。也可不提取（答案图直接嵌入）或手动输入。状态写 `#cr-extract-status`。
- 字段顺序（自动填充项集中在上方）：`#cr-subject`/`#cr-category`/`#cr-diff`/`#cr-related`（相关知识点，**classify 会自动填**，紧随难度之后；输入框挂 `cr-ktag-list` datalist，由 `populateCreateLists` 填入「已有分类 ∪ 已有知识点」供手动挑选）、`#cr-question`（题目正文，**手动可选**，AI 不抄题）、答案图片区、`#cr-answer`（答案文本）、`#cr-note`（页码）、`#cr-cause`（**错因**，写入 `# 备注` 的 `## 错因`）。

图片交互（题目区 / 答案区各一套）：
- **显式读取剪贴板**：每个区下方有「📋 从剪贴板读取到「题目/答案」」按钮 → `crReadClipboard(kind)`（用 `navigator.clipboard.read()`，需 https 或 localhost 且浏览器授权；无图 / 不支持 / 被拒时弹提示）。这是把图读到**指定区**的最可靠方式，解决「想粘到答案却进了题目」。
- **Ctrl/⌘+V 粘贴**：`document` 级 `paste` 监听仅本页激活时拦截图片；落到「当前目标区」——由 `crSetPasteTarget`（点击/聚焦某区、点其「读取剪贴板」时）记录，默认题目区；目标区会高亮（`.paste-active`）提示 Ctrl+V 将粘到此；文本粘贴不受影响。
- 拖拽 / 点击选择按区独立（`crHandleDrop` / `crPickFiles` 带 `kind` 参数 `'q'|'a'`）。缩略图带删除 ✕ 与序号（`crRenderImages(kind)`），并据此启用/禁用对应按钮。
- 提交时 `doCreate` 把两区图片分别映射为 `question_images` / `answer_images` 一并发送；成功提示含已保存图片数。

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
| 科目维度 | `data-subjects` | 表格（最薄弱在前） |
| 分类维度 Top 15 | `data-categories` | 表格 |
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
- **列表**：`loadReports()` 拉 `/api/reports`，`renderReports()` 用 `sched-item` 样式列出（名称 / 创建时间 / 大小 / id）。
- **浏览**：`openReport(id)` → `window.open('/api/report/view?id=...')` 新标签打开。因同源，报告内 `<img src="/api/image?name=...">` 能正常加载题图。
- **删除**：`deleteReport(id)` → `POST /api/report/delete`。
- `switchTab('reports')` 触发 `loadReports()`。

### 报告如何引用题目图片（与后端对接）

AI 生成报告时，对某道题用 `<img src="/api/image?name=<URL编码文件名>">` 即可显示其原图（让人一眼认出是哪道题）。文件名来源：`/api/question?uid=` 或 items 的 `images` 字段、或导出复盘报告 JSON。仅在“由本程序托管 + 在程序内打开”时图片才加载（同源）；脱离服务直接双击本地 HTML 不会显示题图。
