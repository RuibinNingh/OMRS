# 导出（HTML）

错题清单导出为**自包含 HTML**（图片、KaTeX 资源均内联，单文件可拷给任何带浏览器的设备）。两种版本：**A4 打印版**（默认，纸面复习）与**屏幕版**（手机/平板上的全屏卡片复习 App，可判对错、打分、记录进度）。后端只产结构化文字/图片/表格数据与内联模板，**版面、长图切片、公式和表格渲染、作答交互全部交给浏览器**。

## 为什么是 HTML（而非 docx）

旧 docx 导出长期受两个问题困扰：超长题图被截断、双栏栏底大片留白。根因是 **Word/OOXML 是封闭的版面引擎**——你无法在生成时查询「这一栏还剩多少高度」，于是只能盲切盲排；再加上 **LibreOffice 与 WPS 渲染存在保真度差**，本地预览正常、用户机器上却跑偏。

HTML 把这两个问题一起消掉：**浏览器既是排版引擎、又是用户最终查看/打印的引擎**——所见即所打印，没有跨渲染器保真度差。长图切片用「读像素找白缝 + overflow 裁切同一张内嵌图」，在浏览器里完成（没有 WPS 那个 `srcRect` 白底涂白 bug，且图只存一份）。**附带收益：基础导出不再依赖 Pillow；Pillow / `jpegtran` 只用于可选图片优化。**

## 后端职责（`omrs/exporting.py`）

只做四件事，全部纯标准库：
1. **读题**：`_load_export_questions()` 从 mastery CSV + 题目 `.md` 取题（与旧实现一致，未改）。
2. **解析**：`_text_to_blocks()` 把正文转成三种块——非空文字行→`{t:'txt'}`，`![[名]]` / `![](路径)`→`{t:'img'}`，Markdown 表头 + 分隔行 + 数据行→`{t:'table', headers, rows}`。表格支持 `\|` 转义；对齐冒号会被识别但当前不保留对齐语义，行宽按表头补空或截断。
3. **取图**：`_img_payload()` 用 `_find_image()` 定位、`_read_image_info()`（纯 `struct` 解析 PNG/JPEG/GIF 尺寸，无 Pillow）读出宽高，base64 成 data-uri。
4. **组装**：`_build_export_data()` 产出 `{meta, questions, feedback, answers}`，其中 `meta.question_gap_lines` 经 `_normalize_question_gap_lines()` 钳制到 `0–20`，`meta.a4_two_columns` 经 `_normalize_a4_two_columns()` 归一化；`_build_html()` 读 `export_templates/{variant}.css` 与 `.js`，并把本地 `assets/vendor/katex/` 的 CSS/JS/字体一起内联。数据 JSON 会做 `</` 转义防提前闭合脚本，最终仍是单个自包含 HTML。

对外入口 `export_schedule_artifact(vault, uids, session_id, export_format, include_answers, question_gap_lines=0, a4_two_columns=True)`：
- `export_format`：`'a4'`（默认）/ `'screen'`；为兼容旧调用，`'docx'`/`'word'`/`'html'`/空 一律按 `a4`。
- `question_gap_lines`：仅 A4 使用；每两道题之间加入 `lines × 18px` 留白，最后一题后不追加。
- `a4_two_columns`：仅 A4 使用；默认 `true` 为双栏，`false` 时整份文件使用单栏。
- 返回 `(bytes, session_id, "OMRS-{sid}-{variant}.html", "text/html; charset=utf-8")`。

模板是包内资源，放在 `omrs/export_templates/`，可直接当普通 JS/CSS 文件编辑：

| 文件 | 作用 |
|---|---|
| `a4.css` / `a4.js` | A4 打印版样式 + 排版引擎（引擎与应用层合并） |
| `screen.css` / `screen.js` | 屏幕版样式 + 复习 App 逻辑（卡片/判分/进度/持久化） |

导出模板中的 `$...$` / `$$...$$` 由内联 KaTeX 在浏览器端渲染；若 KaTeX 资源缺失或单个公式解析失败，会安全降级为原始公式文本。KaTeX 字体在导出时改写为 data URI，因此离线打开 HTML 也不需要访问 `assets/` 目录。

### 调用入口

- Web API：`POST /api/export` 接受 `question_gap_lines` 与 `a4_two_columns`；后端负责归一化，详见 `api.md`。
- 前端：题库选题导出和 Session 导出分别使用 `#export-question-gap` / `#sch-question-gap`；`assets/export.js::getQuestionGapLines()` 在发送前做同样的 `0–20` 归一化。
- CLI：`python omrs_engine.py export ... --question-gap-lines N`；默认 `0`。

## A4 排版引擎（`a4.js`，浏览器端）

默认几何沿用旧 docx 的 A4、上下 0.5in、左右 0.25in、双栏、栏距 0.5in，栏宽约 `348.85px`（9.23cm）。2026-07-14 起页底另扣 `FOOTER_SAFE = 8.5mm`，有效栏高约 `994.39px`（26.31cm），页码底距为 `32px`，避免浏览器或打印机裁切。维护时必须同步 `a4.js::FOOTER_SAFE/COL_H` 与 `a4.css --col-h`。

1. **选择栏模式**：`meta.a4_two_columns` 默认为 `true`（双栏），设为 `false` 时**整份** A4 导出切为单栏；前端每次导出 A4 都弹出确认，遇到表格或长公式时提示用户选单栏。引擎不会自行检测表格改变栏模式。表格单元格仍使用 `mathText()` 渲染公式。
2. **测真实高度与公式续栏**：每个内容块按当前栏宽 `colW` 塞进离屏测量容器，读 `getBoundingClientRect().height`。若一段含 `$...$` / `$$...$$` 的文字放不进当前栏，排版器会从靠后的公式边界拆开：前缀留在当前栏，公式及后文从下一栏/页顶部继续；无公式文字仍整段换栏。单个公式本身高过完整栏的极端情况不自动缩放或改写。所有参与分页的纵向间距使用 `padding`，避免外边距不计入测量。
3. **贪心填栏与二次校验**：页面创建后立即挂到 `#stage`，因此测量到的是浏览器真实盒模型高度而非未挂载节点的零高度。维护「当前页/当前栏/当前 y」，逐块填入固定高度区域；双栏模式填满左栏转右栏，单栏模式直接换页。每次实际插入后都以元素底边复核是否仍在 `COL_H` 内，字体或行距差异导致的超出会撤回并换栏。`keepNext`（题头/小标题）若落在栏底 `ORPHAN`（56px）内则整体推到下一栏/页。`question-gap` 是普通定高块，仅插在题目之间。
4. **长图切片**（核心）：
   - 整张能进当前栏剩余 → 不切。
   - **PACK**（图能进一整栏但进不了当前栏剩余）：仅当能找到干净白缝时，切一片把当前栏填满、余下顺到下一栏；**找不到干净缝就整段顺到下一栏，绝不为填栏切穿内容**。
   - **FORCE**（图高过一整栏，必须切防截断）：优先用当前栏剩余里的白缝切，否则按整栏切；极端情况（密排长图无任何白缝）在墨最少处切并**标红虚线 + 顶栏告警计数**。
   - 切口靠 `analyze()` 读像素：逐行墨量 → 自适应底噪（5 分位 floor + 宽度相关容差）→ 连续 ≥G 行安静即「缝带」，切在缝带中心。
   - 切片用 `.slice`（固定高 + `overflow:hidden`）裹同一张 `<img>`、负 `margin-top` 平移——即 `srcRect` 的 HTML 安全版：浏览器零渲染怪癖、图只存一份。
5. **页码**：因分页由引擎掌控，每页底部居中渲染 `i / 总页数`（打印可见，对应反馈表的「页码」列）。

顶栏（不打印）有「打印/导出 PDF」「显示切口」开关与状态（页数/排版耗时/切穿告警数）。

> 实测：同一份 16 题数据，旧 docx 11 页、栏底留白高达 65%/49%/30%；A4 HTML 压到 7 页、各栏留白个位数，长图跨栏切在不可见的白缝处，无截断。

## 屏幕版（`screen.js` / `screen.css`）—— 全屏卡片复习 App

定位：**用手机/平板复习的轻应用**，与桌面端仪表盘（`assets/styles.css`）共用同一套设计令牌（暖棕 `--accent:#8b5e3c`、米色底、Noto Sans SC、8px 圆角、柔和阴影），导出件与主程序观感一致。移动优先、所有交互在拇指区可达，桌面端自动适配（卡片定宽居中、抽屉变居中弹窗、支持方向键）。

题面和答案的 `{t:'table'}` 块由 `renderBlocks()` 输出为可横向滚动的 `.md-table-wrap`，每个单元格继续用 `mathText()` 渲染 LaTeX。屏幕版保持一题一卡，不因表格切换整份布局。

**一题一屏。** 顶栏 = 圆形 logo + Session 号 + **进度环**（随判定填充，signature 元素）+ 抽屉按钮；中部 = 单张全屏卡片（题面过长则卡内滚动）；底栏 = 上一题 / 下一题箭头 + 题号 + 主操作按钮。翻题：手机左右**滑动**、桌面方向键或箭头按钮、抽屉网格点任意题跳转。

**作答流程（每张卡）**：读题 → 点「显示答案」展开解析 → 判 **答对 / 答错**（互斥，红绿高亮）→ 给 **0–10 分**自评（滑杆 step=1 + 快捷档 0/4/6/8/10）。判对默认 10 分、判错默认 4 分，均可调。

**评分释义（实时）**：分数框下方的提示随「对错 + 分数」即时变化，文案直接取自 OMRS 熟练度算法 `compute_mastery_update` 的四象限（高分阈值 = `high_score_threshold` = 7）：

| | 分 ≥ 7 | 分 < 7 |
|---|---|---|
| **答对** | 高分待确认（再答对一次即「已击杀」） | 磨合中（答案对但不熟） |
| **答错** | 粗心 / 陷阱（思路对，栽在细节） | 真不会（关键步骤没掌握） |

抽屉里另有一张**常驻评分标准**卡片，把这四象限写死作速查；阈值若在 `common.py` 调整，此处文案需同步。

**作答情况抽屉**（点进度环或顶栏 ☰）：
- 三张统计卡 **已作答 X/N · 答对 · 答错**——只计对错，**不做总分/平均分**（按需求刻意去掉聚合分数）。
- **各科作答** 条形（绿=对、红=错段，多科目才显示）。
- **评分标准**速查卡。
- **跳转网格**：每格按判定着色（绿对 / 红错 / 空未判），格内显示该题自评分；点格跳题。当前题描边高亮。
- **「📋 复制作答 JSON（导入主程序反馈）」**（accent 配色独占一行）+「跳到第一道未判定」「清空记录」。复制按钮（`copyAnswersJson`）只导出**已判定**的题：`{type:"omrs-feedback", version:1, session_id, exported_at, total, graded, items:[{uid, is_correct, sub_score}]}`（score 未动过滑杆时按默认对→10 / 错→4 落盘；完整格式见 `data.md` §11）。`session_id` 优先取 `meta.session_id`（`_build_export_data` 已注入），旧导出件回退正则解析 `meta.sub`。复制走三级兜底：`navigator.clipboard` → `execCommand('copy')` → 自动**下载 .json 文件**（文件内容同样可粘进主程序导入框）。

**持久化**：每题 `{revealed, verdict, score}` + 当前题号写入 `localStorage`，key = `omrs_review_` + (Session 子标题 + UID 列表) 的指纹，**换一份导出件互不串档**；防抖写入，刷新/重开自动恢复进度。隐私浏览等禁用 `localStorage` 的环境会降级（顶部提示「无法保存」），功能仍可用、仅不持久。

**图片灯箱**：点任意图全屏放大，点击 / Esc 关闭。

> 注：导出件本身仍**不直接回写题库**（沿用「改源题后重导」的取舍）；0–10 分与 OMRS 主观分同量纲。复习完成后用「复制作答 JSON」→ 主程序「提交反馈」页**导入作答 JSON**，即可半自动回写（自动关联 Session、填充反馈行，人工核对后提交）。

## 待办

- Markdown 表格当前只保留结构与公式，不保留对齐语义；A4 把整张表格作为一个不可拆块，极端超长表格可能超出单页。后续扩展时应同时修改 `_text_to_blocks()`、A4 与屏幕版模板，并补两种变体的回归测试。
