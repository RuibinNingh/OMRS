# 2026-11-26 修复 A4 打印视图缩放时 SVG 排版误报

> **任务**
> - 标识：a4-svg-print-zoom
> - 状态：已交付

## 背景

用户原话「???生产环境」，附 A4 打印画面，报「题目 组成细胞的分子16 的SVG在当前栏宽下过小」。完整模式。只读核对线上源码目录 `omrs-d2d6268`，A4 排版脚本与 `origin/main` 字节一致。题目只读核对有一张配图，按 90 mm 宽计算的最小字和线条分别约 10.13 pt、0.90 pt。使用基线 `d5148c7` 的独立工作区，避开原工作区的其他未提交修改。测试使用合成配图和临时 Vault。

## 行为变化

A4 按布局像素计算栏宽、栏高、图片和横幅尺寸，落位时将视口中的底边换回布局像素。打印视图统一缩放时，SVG 可读性仍按纸面布局宽度检查，合格 SVG 整图排版。实际栏宽不足时仍禁打印，并提示改单栏或放大图中文字与线条。模板内嵌在新导出的 HTML 中，旧文件需要重新导出。

## 影响文件

- `omrs/export_templates/a4-layout.js`、`omrs/export_templates/a4.js` 调整栏尺寸与落位度量。
- `tests/smoke_a4_print.py` 增加打印视图缩放与实际窄栏两项 Chromium 回归。
- `AI/export.md`、`AI/question-svg.md`、`README.md` 同步当前排版和校验行为。
- 本任务日志和生成的 `AI/logs/log.md` 记录交付与验证。

## 已执行验证

- 新增两项打印回归先在原模板运行，80% CSS 缩放复现 SVG 过小并清空整页，实际窄栏用例通过。修正后 `python -m unittest tests.smoke_a4_print -v` 共 10 项通过，含单栏、双栏、缩放前后题序、完整 SVG、PDF 页数和真实窄栏。
- `python -m unittest tests.test_question_svg tests.test_schedule_export_history tests.test_export_fonts tests.test_board_export tests.smoke_board_print -q` 共 39 项通过。`python -m unittest tests.test_schedule_banner tests.test_schedule_reminders -q` 共 12 项通过。
- `python tests/e2e/question_svg.py` 23 项、`python tests/e2e/schedule_export.py` 31 项、`python tests/e2e/schedule_reminders.py` 30 项通过。使用隔离实例和真实 Chromium，覆盖实际导出、离线文件、题面与答案、首页提醒和 PDF。
- `python tests/visual/run.py --ref HEAD --pages schedule` 的 4 档未见像素差异或页面脚本错误，报告在 `/tmp/omrs-a4-svg-fix-schedule-visual/report.html`。另以同一合成导出对比 A4，普通视图首屏像素一致。80% 打印媒体缩放下旧版只显示错误，新版呈现 24 个题头、1 张完整 SVG 和 4 页，证据在 `/tmp/omrs-a4-svg-fix-print-visual/`。
- 用本机 Chrome 打印预览保存合成 PDF，默认设置与自定义 80% 缩放均未触发该报错。复现条件为打印文档布局上的显示缩放，用户当时的浏览器设置仍未确认。
- `python3 tests/check_docs.py --write-log-index`、`python3 tests/check_docs.py --diff HEAD` 和 `git diff --check` 通过。

## 未执行验证

未在用户设备上复现原截图，未验证实际打印出纸。未部署生产或推送 GitHub。未运行全仓门禁，相关导出链路已按上文验证。
