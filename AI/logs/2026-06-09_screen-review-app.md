# 2026-06-09 屏幕版导出重做为全屏卡片复习 App

## 背景

屏幕版导出原是「单栏阅读 + 答案折叠 + 筛选搜索」的静态阅读视图。需求升级为**可在智能设备上实际复习的轻应用**：一题一屏的卡片、能看答案、能判对错并打分、作答全程记录且**刷新不丢**、能查看当前作答情况，移动端重点优化、观感与桌面端统一、整体「像个软件」。

> 同时修掉一处早前遗留 bug：`assets/data.js` 调用了未定义的 `downloadDocxResponse`（docx→HTML 迁移残留），导致「导出复盘报告」按钮报 `is not defined`（请求其实是通的）。改为复用 `schedule.js` 既有的 `downloadExportResponse`，文件名后缀 `.md`→`.html`。

## 改了什么（仅 3 处，后端数据管线与 A4 完全没动）

1. **`omrs/export_templates/screen.css`** —— 整套重写。
   - 调色板/字体直接对齐桌面端 `assets/styles.css`（`--accent:#8b5e3c`、米色底、Noto Sans SC、8px 圆角、柔和阴影），让导出件与主程序一眼是同一个产品。
   - 全屏三段式布局：顶栏（logo + Session + 进度环 + 抽屉键）/ 卡片舞台（`#track` 横向位移翻页，单卡 `overflow-y` 内滚）/ 底部操作条。`100dvh`、`env(safe-area-inset-*)` 适配刘海屏与底部 Home 条。
   - 移动优先，`@media(min-width:760px)` 桌面适配（卡片定宽居中、抽屉变居中弹窗）、`@media(max-width:380px)` 小屏微调、`prefers-reduced-motion` 降级。

2. **`omrs/export_templates/screen.js`** —— 整套重写为 App 逻辑。
   - **卡片**：题头（题号/UID/难度徽标/科目分类/标签 chips/状态点）+ 题面 + 错因/关联批注 + 答案区（折叠）+ 评分区。
   - **翻题**：手机左右滑动（`touchstart/move/end`，锁主轴、阈值 55px）；桌面方向键 ←/→；底栏箭头；抽屉网格点题跳转。
   - **作答**：「显示答案」展开解析 → 互斥的 **答对/答错** → **0–10 分**自评（`range` step=1 + 快捷档 0/4/6/8/10）。判对默认 10、判错默认 4，可调。
   - **判分释义（实时）**：分数框下随「对错 + 分数」即时更新文案，直接对应 `omrs/scheduling.py::compute_mastery_update` 的四象限（高分阈值 = `common.py::DEFAULT_TUNING['high_score_threshold']` = 7）：

     | | 分 ≥ 7 | 分 < 7 |
     |---|---|---|
     | 答对 | 高分待确认（再对一次即「已击杀」） | 磨合中 |
     | 答错 | 粗心 / 陷阱 | 真不会 |

   - **作答情况抽屉**：统计卡 **已作答 X/N · 答对 · 答错**（**无总分/平均分**，按需求去掉聚合分数）；各科作答条形（绿对/红错，多科目才显示）；常驻**评分标准**速查卡；**跳转网格**（按判定着色 + 显示自评分 + 当前题描边）；「跳到第一道未判定」「清空记录」。
   - **持久化**：`{cur, items:{uid:{revealed,verdict,score}}}` 防抖写 `localStorage`，key = `omrs_review_` + (`meta.sub` + UID 列表) 的 32-bit 指纹哈希 → 不同导出件互不串档。启动探测 `localStorage` 可用性，禁用环境降级提示且功能不受影响。

3. **`omrs/exporting.py`** —— 只改 `_SCREEN_BODY` 常量为新结构（顶栏进度环 SVG、`#track`、底部操作条、抽屉 [统计/各科/评分标准/网格/操作]、灯箱、toast）。`_build_export_data` 产出的 `{meta,questions,answers}` 字段一字未改——新前端完全吃旧数据。

## 设计取舍

- **不回写题库**：导出件仍是离线自评工具（沿用「改源题后重导」）。0–10 分只为本机复习参考，与 OMRS 主观分同量纲，方便用户事后手动录入 feedback。
- **不做总分**：明确去掉平均分/总分类聚合，回归「单题要么对要么错，再打分」。统计只呈现对错计数与进度。
- **判分标准内置且与算法对齐**：释义文案与速查卡都映射 `compute_mastery_update` 四象限；若 `high_score_threshold` 等调参变动，需同步 `screen.js` 的 `paintRubric` 与 `exporting.py` 速查卡文案、以及 `export.md` 表格。

## 验证

- 构造测试库（4 题：含 LaTeX、选择题、超高长图、无答案题 + mastery CSV），走真实管线 `export_schedule_artifact('testvault', uids, '', 'screen', include_answers=True)` 产出 HTML。
- 导入冒烟：`omrs.exporting/server/cli/__init__` + `omrs_engine` 全通过；确认无 Pillow、A4 模板未改、无 `downloadDocxResponse` / `st-acc` / `st-avg` / `/100` 残留。
- CLI 经 `omrs_engine.py export --format screen` 正常落盘。
- 无头 Chromium 截图（390×844 手机 + 1100 桌面）：卡片/题头/批注/答案展开、答对默满分、判分四象限文案（高分待确认→绿、磨合中→琥珀、粗心陷阱→琥珀、真不会→红）、抽屉统计（已作答/答对/答错、各科条形、评分标准速查、着色跳转网格）、无答案题降级、桌面布局，均正确。
- **持久化**：判完两题后读 `localStorage` 确认 `score` 落在 0–10；`reload()` 后位置、每题 verdict/score、统计与网格全部恢复。

## 待办

- `$...$`/`$$...$$` 仍是辨识样式占位，KaTeX 真渲染留作后续（只改模板 `mathText`）。

## 补丁（同日）：屏幕版导出每题都显示「未附答案」

**现象**：导出屏幕版，每道题都是「（本题未附答案——按你的理解自评即可）」。

**定位**：后端与模板均无误——`include_answers=True` 时 `_build_export_data` 正常产出 `answers[]`（UID 与 questions 对齐、blocks 有内容），无头浏览器里 `window.OMRS_DATA.answers` 也确实有数据、卡片正常渲染答案。根因在前端：导出请求里 `include_answers` 取自「附带答案」复选框，**该框默认不勾**，于是屏幕版导出实际是「不带答案」，每张卡只能落到占位文案。A4 不带答案是合理用法（纯题面练习），但**屏幕版是「看答案→判分」的复习 App，不带答案毫无意义**。

**修复（`assets/schedule.js` + `omrs_dashboard.html`，后端/模板未动）**：
- `doExportSelected` / `exportSession`：屏幕版**强制** `include_answers=true`（请求时兜底，与复选框状态无关），A4 仍读复选框。这是根治——屏幕版导出不可能再空答案。
- `setExportVariant`：切到屏幕版时把两个「附带答案」框**勾上并禁用**（存原值），切回 A4 **恢复**用户原选择，并给 label 加 title 说明。
- 导出区说明文案更新：A4「可选是否附带答案」、屏幕版「始终附带答案」（原文案还停留在旧的「答案默认隐藏便于自测」）。

**验证**：重新导出屏幕版，两张卡均渲染真实答案、无占位；变体切换的勾选/禁用/恢复四种路径单测通过。
