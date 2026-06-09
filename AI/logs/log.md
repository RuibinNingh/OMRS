# 变更日志总索引

> 每次有实质性代码改动，在此补一行，并在同目录新建 `YYYY-MM-DD_<主题>.md` 详细记录。

| 日期 | 主题 | 摘要 |
|---|---|---|
| 2026-06-09 | [screen-review-app](2026-06-09_screen-review-app.md) | **屏幕版导出从「阅读视图」重做为全屏卡片复习 App**，移动优先、UI 与桌面端同步（共用调色板/字体）。一题一屏：滑动/方向键翻题、显示答案、判**对/错**、**0–10 分**自评（与 OMRS 主观分同量纲；判分实时给四象限释义：高分待确认/磨合中/粗心陷阱/真不会，取自 `compute_mastery_update`）。作答情况抽屉：已作答/答对/答错（**去掉总分·平均分**）、各科条形、评分标准速查、着色跳转网格。全部判定 + 位置存 `localStorage`（按 Session+UID 指纹隔离），**刷新不丢**、可一键清空。仅改 `screen.js`/`screen.css`/`exporting.py` 的 `_SCREEN_BODY`；A4 与后端数据管线未动。顺带修早前遗留的 `downloadDocxResponse`→`downloadExportResponse`（导出按钮 `is not defined`）。 |
| 2026-06-09 | [github-upload-prep](2026-06-09_github-upload-prep.md) | 新增发布用 `.gitignore`，明确 GitHub 上传边界：保留代码/前端/AI 文档/技能说明，屏蔽个人错题库、`.omrs` 学习数据、报告、根目录运行日志、缓存、临时目录和 AI 截图工作区。 |
| 2026-06-09 | [html-export](2026-06-09_html-export.md) | **导出从 Word(docx) 全面改为自包含 HTML**，彻底解决长图截断/栏底留白（病根：Word 是封闭版面引擎、LibreOffice≠WPS 保真度差）。新增 A4 打印版（浏览器端分页+缝带切片引擎，所见即所打印）与屏幕阅读版（答案折叠自测/图片灯箱/主题筛选搜索）。`exporting.py` 1042→377 行、删除全部 OOXML/OMML/Pillow 切片代码，**移除 Pillow 依赖、恢复零第三方依赖**；模板落在 `omrs/export_templates/`。`/api/export` 增 `format=a4\|screen`（旧 docx 调用兼容按 a4）；前端导出面板/Session 区加 A4/屏幕切换。新增 `export.md`。 |
| 2026-06-08 | [answer-img-ai-restrict](2026-06-08_answer-img-ai-restrict.md) | 修复导出 Word 带答案时答案区 `![[..]]` 图片不渲染（题目/答案统一走 `_render_text_block`）；「AI 自动识别」新增「仅从已有知识点中选择」开关（`config.ai_restrict_tags`，默认开=硬过滤，关=允许新建上限 4 个），含前端复选框与文档同步。 |
| 2026-06-08 | [ai-recognize](2026-06-08_ai-recognize.md) | 录入题目页支持直接录入正文/答案/备注 + 粘贴题目图/答案图；新增 AI（OpenAI 兼容，Qwen-VL 文档）两按钮：`classify` 回填科目/分类/难度、`answer` 提取答案文本；设置页新增 AI 配置卡片；新增 `POST /api/ai-recognize`(mode)，扩展 `POST /api/create`(question_images/answer_images)。 |
| 2026-06-08 | [word-latex-clipboard](2026-06-08_word-latex-clipboard.md) | 导出 Word 时把 `$...$`/`$$...$$` 转成原生公式(OMML，含上下标/分数/根号/希腊字母/常用符号，失败安全回退源码)；录入页每个图片区加「从剪贴板读取」按钮 + 当前粘贴目标高亮。 |
