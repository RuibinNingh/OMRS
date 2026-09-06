# 2026-09-06 · 题库练习记录：战绩带 + 记录模块

版本：v1.15.0 → **v1.16.0**。纯前端与文档改动，**后端 Python 只改了 `omrs/version.py` 的版本字符串**，
接口、CSV / Ledger / Markdown 格式一律未动。

---

## 1. 动机

题库里「这题练了几次、对错、多少分」这三件事当时的呈现是：

- 画廊卡脚注一句 `N 次`——只有频率，看不出好坏；
- 题目 Modal 右栏一个 `<details class="qv-hist">` 包着 Markdown「## 历史」小节的 `<pre>` 原文——
  字符数不少，但读出来是「这题被做过几次」，而不是「这题在变好还是变坏」；
- 表格有一个可选的「次数」列，同样只有频率。

直接加正确率 / 均分 / 最近日期几个 chip 是最省事的做法，但正确率与卡片上已有的熟练度条说的是
同一件事、均分与分数走势说的是同一件事——重复才是臃肿的来源，不是信息量本身。所以按**三层披露**
分配，同一份数据只在一个层级出现。

## 2. 行为变化

### 2.1 第一层：画廊卡脚注的战绩带（用户可见，默认开）

脚注**不新增行**，原来的「N 次」升级成一条战绩带：一根竖条一次练习，绿对红错，高度是主观分
（0–10 映射到 3–12px），左→右是时间，更早的几次 `opacity:.45` 淡出，最多画最近 8 次。
一个控件同时编码频率 / 对错 / 分数 / 时序，宽度与它替代的三个字相当。

只报异常：**连错 ≥2 时**才在带子后补一句「连错 N」；顺利的题一个字都不多说。`attempts` 为 0
时仍走既有的「未练习」分支，不画空带子。

开关在「列 / 密度」菜单画廊段：`QB_STREAK` / `localStorage('omrs-qb-streak')`，**默认开**
（读取用 `!== '0'`，缺省即开），关掉回到 v1.15.0 的纯「N 次」。已接进 `qbResetLayout()` 与
命名视图快照（`qbViewSnapshot().streak`）。

> **不额外发请求**：战绩带要 `detail.history`，`DATA.items` 里没有。画廊本来就会为题面预览
> 对每张可见卡拉一次 `/api/question`，所以 `galleryFootHtml()` 先出 `.gc-streak-slot` 占位
> （显示 `attempts` 数字），由 `hydrateQuestionGalleryPreviews()` 在同一次
> `ensureQuestionDetail(uid)` 返回后就地替换。详情拉取失败时占位数字原样留着，不退化成空白。

### 2.2 第二层：题目详情最下面的记录模块（用户可见）

`qvHtml()` 里右栏那个 `<details class="qv-hist">` + `<pre>` **整块下线**，改为通栏
`<section class="qv-rec">`，排在 `.qv-q` / `.qv-a` 之后（双栏下 `.qv-split>.qv-rec{grid-column:1/-1}`）：

1. 连错提示行——**仅 `tailWrong >= 2` 时出现**，带上次备注；
2. 四个派生数：练习次数 / 正确率（正确 n/m，`rate < 60` 标红）/ 平均主观分 / 平均间隔；
3. 主观分走势 sparkline——**只画分数一条线**，对错用点的颜色叠在同一张图上，不为对错单画第二张图；
4. 明细行（日期 / 对错 / 分数 / 备注），首屏最新 3 条，其余进 `<details>`。

边界：无可解析记录且原文为空 → 一行「还没练过」空态，不画全零图表（`attempts > 0` 时额外说明
熟练度表记了几次但文件里没有可解析历史行）；原文非空但解析不出（历史小节被手改成别的写法）→
原样保留为 `<pre class="qv-rec-raw">`，不假装没有。

生效范围随 `showHistory`：题目 Modal 与反馈工作台显示；即时练习 `showHistory:false`
（未答先看见历史分数会干扰判断），画廊缩略卡 `QV_CARD_OPTS` 同样为 `false`——两处均为既有取值，未改。

### 2.3 第三层：不做

全库聚合（熟练度分布、难度分布、顽固题表）仍只在「数据复盘」页，题库页不重复。

### 2.4 明确没做：表格视图的战绩带

表格视图不拉题目详情。若表格也画战绩带，一屏几十行会各发一次 `/api/question`。
`attempts`（次数）列保持纯数字。

## 3. 影响文件

| 文件 | 改动 |
|---|---|
| `assets/core.js` | 新增 `Q_HISTORY_LINE_RE` / `parseQHistory()` / `qHistoryStats()` / `qStreakHtml()`；文件末尾加 `module.exports` 供 node 单测。正则与后端 `common.py::parse_history_lines()` 格式相近但并非字面完全一致 |
| `assets/qview.js` | 删除 `.qv-a` 里的 `qv-hist` 分支；新增 `qvRecordHtml()` / `qvRecordSparkHtml()` / `qvRecordRowHtml()`，由 `qvHtml()` 在题面 / 答案之后拼入；`QV_DEFAULTS.showHistory` 语义注释更新；导出 `qvRecordHtml` |
| `assets/questions.js` | `galleryFootHtml()` 改用 `qbStreakOn()` + `galleryStreakSlotHtml()`；新增 `galleryStreakBodyHtml()`；`hydrateQuestionGalleryPreviews()` 末尾填充战绩带；导出 `galleryFootHtml` / `galleryStreakBodyHtml` |
| `assets/qtable.js` | 新增 `QB_STREAK`（默认 true）与 `qbSetStreak()`；接进 `qbReadPrefs` / `qbRenderControls` / `qbResetLayout` / `qbViewSnapshot` / `qbApplyView` / change 事件委托 |
| `assets/styles.css` | `.qv-hist` 三条规则替换为 `.qv-rec*` 一组 + `.q-streak` / `.gc-streak-slot` / `.gc-warn`；全部走密度变量与 token，浅色深色自动跟随 |
| `omrs_dashboard.html` | 「列 / 密度」菜单画廊段新增战绩带勾选（`data-qb-streak`）；`styles.css` / `core.js` / `questions.js` / `qtable.js` / `qview.js` 的 `?v=` 统一改 `20260906-practice-record`；侧栏版本号 → v1.16.0 |
| `omrs/version.py` | `v1.15.0` → `v1.16.0` |
| `tests/test_question_record_ui.js` | 新增，10 个用例 |
| `AI/frontend.md` | 顶部 v1.16.0 段；文件组织表 `core.js` / `qview.js` 两行；§2.2 的 `opts` 说明、`.qv` 结构、即时练习调用点备注；「画廊式」一节补战绩带；§3.2 补表格「次数」列说明与菜单开关清单 |
| `README.md` | 当前版本、功能表新增「练习记录」行、版本历史新增 v1.16.0 行 |

## 4. 验证

- `node --test tests/test_question_record_ui.js` → **10 passed / 0 failed**。覆盖：
  正则与后端格式对齐；空行与不可解析行被丢弃而不是猜测；`qHistoryStats` 的 count / rate /
  avgScore / tailWrong / avgGap（手算 `(7+15+24)/3 = 15` 核对）；无记录只返回 `{count:0}`；
  战绩带每次一根条、超过 `max` 截断、按对错着色、空数组返回空串；记录模块在连错时出提示且
  正确率 <60% 标红、干净记录不出任何警示、4 条记录折叠 1 条；空态与不可解析原文两条边界；
  记录模块位置在 `.qv-a` 之后且 `showHistory:false` 能整块关掉；画廊脚注先出占位、
  `galleryStreakBodyHtml()` 填充后含战绩带与「连错 2」。
- 其余 10 个既有 JS 测试逐文件运行全部 PASS（`smoke_feedback_omr_import` / `smoke_frontend_actions_catalog` /
  `test_board_ui` / `test_feedback_ui` / `test_labels_ui` / `test_md_linebreaks` / `test_omr_import` /
  `test_qtable_ui` / `test_question_suspend_frontend` / `test_recommend_v2_filters`）。
- `python3 -m py_compile omrs/*.py` 通过；`python3 -c "import omrs.version"` 输出 `v1.16.0`。
- `node -e "require('vm').compileFunction(...)"` 对四个改动过的 JS 逐个做语法检查，均通过。
- 用改动后的真实函数 + 真实 `assets/styles.css` 渲染了一份静态预览页，肉眼核对三张画廊卡
  （连错 / 稳定上升 / 未练习）与三个记录模块的实际输出。

### 已知问题（非本次引入）

`node --test tests/` 整目录运行会失败：各测试文件都往 `global` 上挂自己的 `document` /
`escapeHtml` 等 shim，同进程内互相覆盖。把本次新增文件移出后整目录运行同样失败，说明与本任务
无关。当前可用的运行方式是逐文件 `node --test tests/<file>.js`。**未在本任务内修复**，
留待专门的测试隔离任务处理。

容器内没有 `pytest`，Python 测试未运行；本次 Python 侧只改了版本字符串，风险相称。

## 5. 事实勘误（2026-09-06 文档审计）

- 正式反馈的事实链是 `POST /api/feedback` → `review.batch_submit` Ledger commit → `rebuild_projection()` → `history_log.csv`；反馈流程不会把记录追加到题目 Markdown 的 `# 历史` 小节。
- Markdown `# 历史` 是旧手工记录的兼容输入；`GET /api/question` 仍返回其原文，所以本次实现实际存在数据源错配：`DATA.items[].attempts` 有次数时，画廊和详情仍可能因没有可解析的 Markdown 历史行而显示「还没练过」。下一次正常反馈也不会自动填充该界面。
- 前端与后端历史行正则的格式相近但并非“完全一致”：前端要求整行匹配并把分数钳制到 0–10，后端使用 `re.match` 且未锚定行尾。
