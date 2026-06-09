# 2026-06-09 导出从 Word(docx) 迁移到自包含 HTML

## 背景与决策

导出长期受两个问题困扰：超长题图被截断、双栏栏底大片留白。根因是 **Word/OOXML 是封闭版面引擎**——生成时无法查询「这一栏还剩多少高度」，只能盲排；再加上 **LibreOffice 与 WPS 渲染保真度差**，本地预览正常、用户机器跑偏。此前为此投入大量精力做 Python+Pillow 的长图切片，仍反复失败。

改用 **HTML**：浏览器既是排版引擎、又是用户最终查看/打印的引擎——所见即所打印，跨渲染器保真度差消失；长图切片用「读像素找白缝 + overflow 裁切同一张内嵌图」，浏览器里完全可靠。**附带把 Pillow 依赖一并移除，项目恢复零第三方依赖。**

编辑性（在导出件里直接改）被有意舍弃——改源题后重导即可；换来产品优化的机会。

## 后端：`omrs/exporting.py`（1042 → 377 行）

**保留（未改）**：`_load_export_questions` 及其依赖 `_format_export_tags`/`_parse_notes_subsections`/`_normalize_export_request`；图片尺寸纯标准库解析 `_png_size`/`_jpeg_size`/`_gif_size`/`_read_image_info`；`_find_image`、`_extract_embeds`；`QUESTION/NOTES/ANSWER_SECTION` 常量。

**删除**：所有 docx/OOXML 模板与构造（`_DOCX_*`、`_run`/`_para`/`_heading`、`_drawing_xml`、`_feedback_table`、`_build_content_types`/`_build_doc_rels`、`_build_docx_bytes`、`export_schedule_docx`）；OMML 数学（`_latex_to_omml`/`_tokenize_latex`/`_parse_*`/`_parse_math_runs`/`_m_*` 及符号表）；版面几何与 Python 端像素切片（`_section_geometry`/`_row_ink_profile`/`_plan_image_slices`/`_compute_image_emu`/`_render_image_embed`/`_render_text_block`）。**`import PIL` 随之消失。**

**新增**：`_img_payload`（图→`{src:data-uri,w,h}`）、`_text_to_blocks`（正文→块列表，按行成块）、`_build_export_data`（→`{meta,questions,feedback,answers}`）、`_read_template`、`_build_html`（读 `export_templates/{variant}.css+.js` 内联，数据 JSON 做 `</`→`<\/` 转义）、`export_schedule_html(variant)`。`export_schedule_artifact` 改为 `format='a4'`(默认)/`'screen'`，旧 `docx`/`word`/`html`/空 一律按 `a4`；文件名 `OMRS-{sid}-{variant}.html`，类型 `text/html; charset=utf-8`。

## 新增模板：`omrs/export_templates/`

包内资源，可当普通 JS/CSS 编辑：
- `a4.css` / `a4.js`：A4 打印版样式 + 排版引擎（浏览器端测高 → 贪心填双栏 → 缝带切长图；FORCE 防截断 / PACK 填栏不切穿；每页底渲染页码；顶栏打印按钮 + 显示切口开关 + 告警计数）。几何沿用旧 docx：A4 / 上下 0.5in / 左右 0.25in / 双栏 / 栏距 0.5in。
- `screen.css` / `screen.js`：屏幕阅读版（单栏滚动、不切图；答案默认隐藏+全局开关、图片灯箱、主题筛选 chips + 搜索）。

详见 `export.md`。

## 调用方改动

- `omrs_engine.py`：`export_schedule_docx` 导入改为 `export_schedule_html`。
- `omrs/server.py`：`/api/export` 默认 `format` `docx`→`a4`（其余透传不变）。
- `omrs/cli.py`：export 帮助「Word 文档」→「HTML(A4/屏幕)」；`--format` 选项 `["docx"]`→`["a4","screen"]` 默认 `a4`。
- `assets/schedule.js`：`downloadDocxResponse`→`downloadExportResponse`；新增 `setExportVariant/getExportVariant`（读 `[data-expvar]` 激活按钮，默认 `a4`）；`doExportSelected`/`exportSession` 用所选格式 + `.html` 文件名；Session 列表导出按钮「Word」→「导出」。
- `omrs_dashboard.html`：导出面板标题/说明改 HTML；导出动作区与 Session 区各加「A4 打印版 / 屏幕版」切换按钮（`data-expvar`，a4 默认 active）；按钮「导出选中为 Word」→「导出选中」；「导出 Word 时附带答案」→「导出时附带答案」；录入页错因占位「导出 Word」→「导出」。

## 验证

构造与真实导出一致的测试库（16 题 + 15 附件 + mastery CSV），走真实管线 `export_schedule_artifact('testvault', uids, '', variant, include_answers=True)` 产出 A4 与屏幕两份 HTML（各 ~7.9MB）：
- 导入冒烟（omrs_engine/cli/server/exporting）全通过；确认无 `export_schedule_docx`、无 `_build_docx_bytes`、`PIL` 未导入。
- CLI 导出（a4 + screen）正常落盘。
- 用无头 Chrome 渲染 A4→PDF：**7 页 A4**（旧 docx 11 页），第 1 页排版整洁、长 pH 曲线图跨左右栏切在不可见白缝处、页码「1 / 7」正确、无截断、各栏留白个位数（旧版 65%/49%/30%）。
- 屏幕版截图：卡片布局、难度徽标、整图全宽、顶栏搜索 + 显示全部答案、单科目时筛选自动隐藏，均正确。

## 待办

`$...$`/`$$...$$` 目前在导出里是辨识样式占位，**KaTeX 真渲染**留作后续（仅改模板 `mathText`，后端不动）。
