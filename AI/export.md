# 导出（HTML）

错题清单导出为**自包含 HTML**（图片、KaTeX 资源均内联，单文件可拷给任何带浏览器的设备）。三种入口为：**A4 打印版**、**展示板打印版**（左题右空）与**屏幕版**（手机/平板上的全屏卡片复习 App，可判对错、打分、记录进度）。复习调度工作台的已有计划详情可以直接按 Session 导出，并保留原有 A4/屏幕版选择；全题库导出从调度页独立进入。后端只产结构化文字/图片/表格数据与内联模板，**版面、长图切片、公式和表格渲染、作答交互全部交给浏览器**。

## 为什么是 HTML（而非 docx）

旧 docx 导出长期受两个问题困扰：超长题图被截断、双栏栏底大片留白。根因是 **Word/OOXML 是封闭的版面引擎**——你无法在生成时查询「这一栏还剩多少高度」，于是只能盲切盲排；再加上 **LibreOffice 与 WPS 渲染存在保真度差**，本地预览正常、用户机器上却跑偏。

HTML 把这两个问题一起消掉：**浏览器既是排版引擎、又是用户最终查看/打印的引擎**——所见即所打印，没有跨渲染器保真度差。长图切片用「读像素找白缝 + overflow 裁切同一张内嵌图」，在浏览器里完成（没有 WPS 那个 `srcRect` 白底涂白 bug，且图只存一份）。**附带收益：基础导出不再依赖 Pillow；Pillow / `jpegtran` 只用于可选图片优化。**

## 后端职责（`omrs/exporting.py`）

只做四件事，全部纯标准库：
1. **读题**：`_load_export_questions()` 从 mastery CSV + 题目 `.md` 取题（与旧实现一致，停用标记为 `1` 的题目在此处跳过）。
2. **解析**：`_text_to_blocks()` 把正文转成三种块——非空文字行→`{t:'txt'}`，`![[名]]` / `![](路径)`→`{t:'img'}`，Markdown 表头 + 分隔行 + 数据行→`{t:'table', headers, rows}`。表格支持 `\|` 转义；对齐冒号会被识别但当前不保留对齐语义，行宽按表头补空或截断。跨行 `$$...$$` 会先合并为单个文字块，不能按行拆散。
3. **取图**：`_img_payload()` 用 `_find_image()` 定位、`_read_image_info()`（纯 `struct` 解析 PNG/JPEG/GIF 尺寸，无 Pillow）读出宽高，base64 成 data-uri。
4. **组装**：`_build_export_data()` 产出 `{meta, questions, feedback, answers}`，其中 `meta.question_gap_lines` 经 `_normalize_question_gap_lines()` 钳制到 `0–20`，`meta.a4_two_columns` 经 `_normalize_a4_two_columns()` 归一化；`_build_html()` 读 `export_templates/{variant}.css` 与 `.js`，并把本地 `assets/vendor/katex/` 的 CSS/JS/字体一起内联（`_read_katex_bundle()`）。数据 JSON 会做 `</` 转义防提前闭合脚本，最终仍是单个自包含 HTML。

对外入口 `export_schedule_artifact(vault, uids, session_id, export_format, include_answers, question_gap_lines=0, a4_two_columns=True)`：
- `export_format`：`'a4'`（默认）/ `'screen'`；为兼容旧调用，`'docx'`/`'word'`/`'html'`/空 一律按 `a4`。
- `question_gap_lines`：仅 A4 使用；每两道题之间加入 `lines × 18px` 留白，最后一题后不追加。
- `a4_two_columns`：仅 A4 使用；默认 `true` 为双栏，`false` 时整份文件使用单栏。
- 返回 `(bytes, session_id, "OMRS-{sid}-{variant}.html", "text/html; charset=utf-8")`。

模板是包内资源，放在 `omrs/export_templates/`，可直接当普通 JS/CSS 文件编辑：

| 文件 | 作用 |
|---|---|
| `a4.css` / `a4.js` | A4 打印版样式 + 排版引擎（引擎与应用层合并） |
| `board.css` / `board.js` | 展示板 A4 左题右空样式、分页与答案附页 |
| `screen.css` / `screen.js` | 屏幕版样式 + 复习 App 逻辑（卡片/判分/进度/持久化） |

导出模板中的 `$...$` / `$$...$$` 由内联 KaTeX 在浏览器端渲染；跨行行间公式在后端块化时保持完整，再交给模板的 `mathText()`。若 KaTeX 资源缺失或单个公式解析失败，会安全降级为原始公式文本。KaTeX 字体在导出时改写为 data URI，因此离线打开 HTML 也不需要访问 `assets/` 目录。

`_read_katex_bundle()` 改写 `@font-face` 时**每个字体族只内联 woff2**（现代浏览器全部支持，
其余格式不会被请求），只有某族找不到 woff2 才回退内联它的全部格式；改写结果按 `katex.min.css`
/ `.js` 的修改时间与大小缓存在进程内（`_KATEX_BUNDLE_CACHE`），同一次运行不重复读盘和 base64。
含公式的导出因此从约 2.0MB 降到约 0.95MB，服务端单次导出稳定在十几毫秒，三种变体同时受益。

### 调用入口

- Web API：`POST /api/export` 接受 `question_gap_lines` 与 `a4_two_columns`；后端负责归一化，详见 `api.md`。
- 前端：题库选题导出和 Session 导出分别使用 `#export-question-gap` / `#sch-question-gap`；`assets/export.js::getQuestionGapLines()` 在发送前做同样的 `0–20` 归一化。
- CLI：`python omrs_engine.py export ... --question-gap-lines N`；默认 `0`。

## A4 排版引擎（`a4.js`，浏览器端）

默认几何沿用旧 docx 的 A4、上下 0.5in、左右 0.25in、双栏、栏距 0.5in，栏宽约 `348.85px`（9.23cm）。2026-07-14 起页底另扣 `FOOTER_SAFE = 8.5mm`，有效栏高约 `994.39px`（26.31cm），页码底距为 `32px`，避免浏览器或打印机裁切。维护时必须同步 `a4.js::FOOTER_SAFE/COL_H` 与 `a4.css --col-h`。

1. **选择栏模式**：`meta.a4_two_columns` 默认为 `true`（双栏），设为 `false` 时**整份** A4 导出切为单栏；前端每次导出 A4 都弹出确认，遇到表格或长公式时提示用户选单栏。引擎不会自行检测表格改变栏模式。表格单元格仍使用 `mathText()` 渲染公式。
2. **测真实高度、块级防截断与公式续栏**：每个文字、表格和图片块按当前栏宽 `colW` 塞进离屏测量容器，读 `getBoundingClientRect().height`。排版器不把整道题包成不可拆的大块，也不额外预留整题空白；题头、小问、错因等仍按原有内容块顺序尽量填满当前栏。某个块放不下时只把该块完整移到下一栏/页，避免落入固定栏高的裁剪区。若一段含 `$...$` / `$$...$$` 的文字放不进当前栏，排版器会从靠后的公式边界拆开：前缀留在当前栏，公式及后文从下一栏/下一页顶部继续；无公式文字仍整段换栏。
3. **稳定排版与二次校验**：初次排版等待图片和已有字体，生成含 KaTeX 的 DOM 后再等待 `document.fonts.ready` 与两帧浏览器布局稳定，并用最终数学字体重新排版一次；否则首轮可能用 fallback 字体测量，打印时 KaTeX 字体完成会把栏底内容挤出裁剪区。排版完成后不在 `beforeprint` 或打印媒体变化时重新分页，浏览器预览和打印直接复用同一批固定 A4 页面 DOM，避免两者出现不同版面。屏幕态与打印态只允许改变工具栏、页间距和阴影，不改变 `.page`、`.page-inner`、`.col` 及其内容的尺寸与分页。页面创建后立即挂到 `#stage`，因此测量到的是浏览器真实盒模型高度而非未挂载节点的零高度；每次实际插入后都以元素底边复核是否仍在 `COL_H` 内，放不下就撤回并把当前块移到下一栏/页。`keepNext`（题头/小标题）若落在栏底 `ORPHAN`（56px）内则整体推到下一栏/页。`question-gap` 是普通定高块，仅插在题目之间。
4. **长图切片**（核心）：
   - 整张能进当前栏剩余 → 不切。
   - **PACK**（图能进一整栏但进不了当前栏剩余）：仅当能找到干净白缝时，切一片把当前栏填满、余下顺到下一栏；**找不到干净缝就整段顺到下一栏，绝不为填栏切穿内容**。
   - **FORCE**（图高过一整栏，必须切防截断）：优先用当前栏剩余里的白缝切，否则按整栏切；极端情况（密排长图无任何白缝）在墨最少处切并**标红虚线 + 顶栏告警计数**。
   - 切口靠 `analyze()` 读像素：逐行墨量 → 自适应底噪（5 分位 floor + 宽度相关容差）→ 连续 ≥G 行安静即「缝带」，切在缝带中心。
   - 切片用 `.slice`（固定高 + `overflow:hidden`）裹同一张 `<img>`、负 `margin-top` 平移——即 `srcRect` 的 HTML 安全版：浏览器零渲染怪癖、图只存一份。
5. **页码**：因分页由引擎掌控，每页底部居中渲染 `i / 总页数`（打印可见，对应反馈表的「页码」列）。

顶栏（不打印）有「打印/导出 PDF」「显示切口」开关与状态（页数/排版耗时/切穿告警数）。

> 实测：同一份 16 题数据，旧 docx 11 页、栏底留白高达 65%/49%/30%；A4 HTML 压到 7 页、各栏留白个位数，长图跨栏切在不可见的白缝处，无截断。

## 展示板打印版（`board.css` / `board.js`，v1.14.0）

展示板导出是独立的 `format:"board"` 变体，输入为 `board_id` 而不是临时 UID 列表。
服务端（`build_board_export_data`）读取 `boards.json` 中的题目引用，跳过缺失题和停用题
（不自动从板里清理），分块、内联图片与标记颜色后交给浏览器；**分页、切片、续排全部在
浏览器完成**，与 A4 引擎同一套思路。完整设计见 `board.md`，这里只记导出契约。

### 固定几何与纸面规则

- A4 纵向 `793.7 × 1122.52px`，`@page{size:A4;margin:0}`；左右 10mm、上下 12mm，
  页脚安全带 8.5mm，不额外预留装订区。
- 页眉每页固定「错题集」；`show_meta` 开启且数据有生成日期时在标题右侧显示日期，否则只有标题。页脚只印板内**绝对页码**；
  板名不上纸。
- 题栏宽 = `(内容宽 − 24px) × (1 − note_ratio)`，`note_ratio` 默认 0.50（0.30–0.55）；
  扣除 24px 间距后题栏与右侧留白默认等宽。右侧留白不生成任何 DOM（无横线 / 底纹 / 笔记框）。
- `mode:"new"` 使用 `printed.print` 中记录的原纸 `note_ratio / gap_lines` 排版占位区之后的新题，
  不使用当前板设置覆盖原纸几何；锁定板因此能保持已打印的比例。每次浏览器排版完成都会把实际采用的
  `PRINT_STATE` 写进 `layout.print`；记录纸面时，`mode:"all"` 保存这份快照，`mode:"new"` 保留原纸
  快照；缺少该字段的旧导出件在整板记录时回退当前板设置。
- 题间留白由**每题绝对行数**决定（每行 18px）：导出数据里每道题都带算好的 `gap_lines`
  （0–48），继承关系已在服务端解开，模板不需要再知道板的全局值。留白放不下就贴到页底，
  不为它另起一页。
- 题头「第 N 题 [UID] 标记芯片」单行，元信息「科目 · 分类 · 难度」一行；题目跨页时新页顶部
  补「第 N 题（续）」。文字按公式边界拆段、表格整块、长图切白缝——与 `a4.js` 相同规则。
- 长图找白缝时，宽于 600px 的图先等比缩到 600px 宽再逐行统计墨量，缝位按比例映射回原图坐标
  （`analyze()` 的 `ANALYZE_W`）。手机拍的大图从逐像素扫描的几百毫秒降到几毫秒，缝位误差在
  一两个原图像素内，落在切片安全余量里；600px 以内的图行为与原来完全一致。
- 标记芯片打印变体：18% 淡底 + 同色相压暗到 AA 对比度的文字（`_board_label_ink`，与
  `labels.js::lblInk` 同算法），高 15px。
- 不绘制装订导引线、3 孔、26 孔或其他打孔圆圈。
- **切割线**（`.cut-line`）画在每题留白的末尾，是「这道题写到这里为止」的提示。样式由
  `cut_line` 决定：`none` 不画、`dash` 淡虚线、`solid` 淡实线；`cut_label` 开启时右端加一枚
  「第 N 题止」小标。线画在 `.page-inner` 上而不是 `.col` 里（`.col` 是 `overflow:hidden`，
  画在里面会被裁掉），`top = HEAD_H + 留白末尾相对题栏顶的偏移`，宽度等于**内容全宽**
  （题栏 + 24px 间距 + 右侧留白区）。打印色比屏幕深一档（`#ddd6c9`），否则喷墨印不出来。
- `answers:"append"` / `include_answers:true` 时答案排在新页附页，不占右侧留白。

#### 四种情况不画切割线

`recordCut()` 的守卫，改动时要连同 `tests/smoke_board_print.py::BoardCutLineSmokeTest` 一起看：

1. `cut_line: "none"`；
2. 留白贴到页底（`y >= COL_H - 2`）——撕下来就是整页，标了没有意义；
3. 留白被顶到新页顶部（`y <= 0.5`）；
4. 答案页，以及仅新增模式里已打印占位区之内的位置（`y <= cursor.y`）。

所以「切割线条数 ≤ 题数」，不是恒等；断言条数时只能用上界。

### 打印模式与纸面记录

`mode:"all"`（默认）整板从第 1 页排；`mode:"new"` 只排尚未进入纸面记录的题目：模板在
`printed.cursor.page` 页顶部放一个高度为 `cursor.y` 的占位块（屏幕上斜纹提示，打印时透明，
该页页眉页脚也隐藏），新题从占位块下方续排，需要新页时跳到 `printed.pages + 1`；占位页
没放进任何新题时不输出。`mode:"new"` 沿用纸面记录里的 `note_ratio / gap_lines`；预览内的
增量 `relayout` 也固定使用本次导出初始化时的纸面快照，宿主后来改变的当前板比例不会改变旧纸的
占位几何。
没有纸面记录或没有新题时服务端返回 400（`RuntimeError`）。

### 宿主 ↔ 模板消息协议

导出 HTML 既是打印产物，也是展示板页里那个常驻预览 iframe 的内容，两边靠 `postMessage`
对话（同源 `srcdoc`，`sandbox="allow-same-origin allow-scripts allow-modals"`）。
**模板 → 宿主**（`opener` 与 `parent` 都发）：

| 消息 | 时机 | 载荷 |
|---|---|---|
| `omrs-board-layout` | 首轮排完、每次 relayout 之后 | `{boardId, mode, layout, view}` |
| `omrs-board-view-state` | 单页 / 缩放变化后 | 同上，`layout` 复用上一次 |
| `omrs-board-printed` | 顶栏点「✓ 已打印，记录纸面」（嵌入式预览里顶栏是收起的，这条只来自独立窗口） | `{boardId, mode, layout}` |
| `omrs-board-select` | 点纸面上某道题 | `{boardId, uid, idx, page}` |

**宿主 → 模板**：

| 消息 | 作用 |
|---|---|
| `omrs-board-relayout {print, gaps}` | 就地重算几何并重排；`gaps` 是 `uid → 绝对行数 \| null`（null = 继承 `print.gap_lines`），整份覆盖 |
| `omrs-board-goto {page}` / `{uid}` | 翻到某页 / 跳到某题所在页 |
| `omrs-board-view {single, page, scale, embedded}` | 一次一面 / 页码 / 缩放；只写一条 `<style>`，不重排。`embedded:true` 给 `<body>` 加 `.embedded`，收起顶栏 `#bar` 并去掉它留下的上边距 |
| `omrs-board-request-layout` | 补要一次已有的 layout |

关键取舍：**几何类改动全程零网络请求**。拖版面滑块、改题间留白、换切割线样式都走
`omrs-board-relayout` 在 iframe 里就地重排，不重新请求那份将近 1MB 的导出 HTML；
只有增删题、排序、换模式这类**内容**变化才重新导出。

排版完成后模板写 `window.OMRS_LAYOUT`（`{mode, print, pages, page_numbers, rendered_pages,
partial_page, cursor, items[{question_id, uid, segments[{page,top,height}]}], answer_pages,
warnings}`）与 `window.OMRS_LAYOUT_TIMING`（`{total_ms, passes}`），设置
`<html data-omrs-layout-ready="1">`，并向 `opener`/`parent` 发送
`{type:"omrs-board-layout"}`；顶栏「✓ 已打印，记录纸面」发送 `omrs-board-printed`。主程序
用同一份 HTML 在隐藏 iframe 里测量，`POST /api/board/printed` 记录纸面；展示板页的「预计页数」
也直接采用预览窗口回传的这份 layout（见 `board.md` §4.2）。

`board.js` 的 `initialRun()` 在首轮排版前先并行做两件事：预载图片、按数据里是否出现 `$`
决定要不要 `document.fonts.load()` 预热常用 KaTeX 字体族。首轮排完再比对
`document.fonts` 里新加载的字体，只有确实多出字体时才用最终字体重排第二遍。含公式的板因此
通常一趟排完（`passes: 1`），30 题板的就绪时间约 0.28s；纯文本板本来就不会触发第二遍。

顶栏（不打印）有「打印 / 导出 PDF」「已打印，记录纸面」「显示切口」和状态（本次页数 / 页码范围 /
排版耗时 / 告警数）；仅新增模式另有橙色提示条说明哪一页要放回原纸。

### API 形态

```json
{"format": "board", "board_id": "BD-20260904-a1b2c3", "mode": "new", "include_answers": false}
```

响应为 `text/html; charset=utf-8` 自包含文件，文件名 `OMRS-BD-<板名>[-新增]-错题集.html`
（`Content-Disposition` 带 ASCII 兜底 + `filename*`）。

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
