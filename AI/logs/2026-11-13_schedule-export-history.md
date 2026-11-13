# 2026-11-13 复习导出参数面板与练习历史微型图

> **任务**
> - 标识：schedule-export-history
> - 状态：已交付

## 背景

用户原话：「我打算更新复习调度打印的信息」「在导出的时候加上一个参数面板」「包括各种参数涵盖在内,然后自动记忆上次参数」「我现在还要加上显示历史记录的功能,柱状图,按照分数高低,然后这个可以选择在反馈页面显示还是在题目显示」「还有按照对错给柱状图标颜色」。随后明确：「导出文件的」「按照答题时间排序,越往后越早」「然后记得不要让这个占太多空间,规划好,精致」，最后授权「修改吧 做好了给我看UI」。

执行者为 Codex，完整模式。基线为 `01ec30b`，开工 `git status --short` 为空。本任务在当前工作区实现，不涉及既有进行中计划；不更改版本，不操作生产、systemd 或远端。

期间另一个任务更新并提交了 SVG 生产发布文档（`f33f6f7`，涉及 `AI/environment.md`、SVG 计划进度与其任务日志），本任务保留这些内容，不将其算作本任务修改。本任务代码尚未提交或部署。

## 行为变化

- 已有计划与全题库选题导出共用参数面板：文件版本、单双栏、答案、留白、历史位置与条数，折叠选项控制分数和首尾日期。桌面有明确标为示例的排版示意，窄屏仅保留表单。
- 同源浏览器只记住成功导出的参数；取消与失败不覆盖。失败留在面板内重试，存储受限不阻止导出；回车确认会读取数字框最后输入。
- 默认反馈区显示最近 8 次，支持 1–16 次与关闭。按业务作答时间从左新到右旧，分数决定柱高，对错独立决定绿色或红色，附 ✓ / ×，零分保留细条。
- 图高 51px（约 13.5mm），8 次以内与题头并排，更多记录移到下方；无历史不占位。历史位置独立于附带答案开关。A4 与屏幕版均内嵌 SVG，离线可用；屏幕版反馈历史在显示答案后出现。
- 从稳定题目身份读取当前有效反馈，仅包含日期、时间、分数、对错；不包含历史备注，关闭时不查询。省略新 API 字段时默认关闭，保留原 CLI / MCP 行为。

## 影响文件

当前以 `git diff --name-status` 和 `git status --short` 复核：调度 feature 的面板、参数、控制器和视图，样式入口；导出数据与 HTTP 适配，A4/屏幕模板、共用历史模板和字体固定文案；新增参数、有效历史、真实浏览器验证并更新调度回归及打印专项。

同步文档为 `AI/export.md`、`AI/api.md`、`AI/api/boards.md`、`AI/frontend/review.md`、`AI/frontend/design-system.md`、`AI/frontend/architecture.md` 与根 `README.md`。任务日志及自动索引随本次交付维护；截图、HTML/PDF 和门禁日志在 `/tmp/omrs-export-ui-20261113` 及相关临时证据目录，不进入源码。供用户查看的面板、实际打印局部与示例 PDF 另存于 `/root/.codex/visualizations/2026/11/13/01a1d339-e5f3-7000-8c04-45c83f10ba2e/omrs-export/`。

## 已执行验证

- 参数与导出专项：`python3 -m unittest tests.test_schedule_export_history -q` 6 项通过；既有报告导出、字体、正式记录 pytest 共 13 项通过。首轮历史测试发现读取了兼容大写字段，已改为 SQL 实际 `question_id` 后通过。新增同分钟混合时区回归，比较真实时间戳以确保 UTC 与 +08:00 表示正确排序。
- `node --test tests/app/*.test.mjs`：578 项通过，无失败或跳过，见 `/tmp/omrs-node-20261113.log`。`python3 tests/app/run_browser.py`：组件真实浏览器 35 项通过，见 `/tmp/omrs-export-components-20261113.log`。
- `python3 tests/e2e/schedule.py`：现有复习调度 E2E 46 项通过，见 `/tmp/omrs-schedule-regression-20261113.log`。首次适配使用隐藏 radio 点击不稳定，改为点击可见标签后通过；业务面板保持原生 radio 语义。
- `python3 tests/e2e/schedule_export.py`：最终复跑 22 项通过，包含真实下载、回车确认捕获数字框最后输入、离线图表、A4/PDF、刷新、取消、失败重试、跨入口共享，以及浅深主题 320/390/1440px，页面脚本错误为零。证据为 `/tmp/omrs-export-ui-20261113.log`，截图与 HTML/PDF 在 `/tmp/omrs-export-ui-20261113`。早期截图阶段 SVG 使用 HTMLElement 文本 API、截图过程中重排导致节点失效，已分别改为 text_content 与坐标截图。
- `python3 tests/smoke_a4_print.py`：A4 / 展示板打印专项 15 项通过，含新增 8/16 次历史、单/双栏跨页、打印媒体、关闭标签和不含答案的反馈历史；无联网请求，见 `/tmp/omrs-export-print-20261113.log`。
- `python3 tests/check_ui.py` 零违例，`python3 tests/check_contrast.py` 对比度 58 组全部通过。`python3 tests/visual/run.py --ref 01ec30b --pages schedule --out /tmp/omrs-export-visual-20261113`：调度首页浅深色、桌面与手机 4 档前后比较无像素差异、无脚本错误；原因是首页仍为安排复习，新增参数面板另由专项截图覆盖。
- 扩展后端最终使用 `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL PYTHONPATH=tests:. python3 -m unittest tests.test_schedule_export_history tests.test_export_fonts tests.test_board_export tests.test_question_records tests.test_history_projection tests.test_http_boundaries tests.test_web_assets tests.test_asset_cache tests.test_mcp_exports -q`，77 项通过，见 `/tmp/omrs-export-backend-20261113.log`。首次运行 70 项时，MCP 测试导入 `test_mcp` 缺少 tests 搜索路径，产生 1 个导入错误，修正后通过。
- `git diff --name-status` 与 `git status --short` 已复核本任务已跟踪及新增路径。`python3 tests/check_docs.py --write-log-index` 生成索引，`python3 tests/check_docs.py --diff HEAD`：160 文档、0 问题，3 条体积提醒；`git diff --check` 通过。

所有服务测试使用临时 Vault 与随机高端口，清除 `OMRS_SYSTEMD_SERVICE` 和 `OMRS_BOXDETECT_CONTROL`，不连接生产或真实题库。页面验证使用 Linux Chromium 151。

## 未执行验证

实体打印机、Windows Edge 与实体手机触摸未执行；本轮使用 Chromium 和 PDF 验证排版。生产发布未执行，未操作生产服务。
