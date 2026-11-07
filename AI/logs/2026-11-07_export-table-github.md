# 2026-11-07 打印表格既有改动提交与 GitHub 推送

> **任务**
> - 标识：export-table-github
> - 状态：进行中

## 背景

用户查看未提交改动后原话：「那提交吧」「推送GitHub」。执行者：Codex；完整模式。开工基线 `b7e1f07`，当前分支 `codex/data-review-progress`，远端为 `https://github.com/RuibinNingh/OMRS.git`。授权范围是此前列出的九个文件：八个修改、一个未跟踪日志；同时补本次提交验证记录，不部署生产。

打印修复承接 `2026-10-29_export-table-widths.md`，保留其原始内容与历史验证结果。维护清单已有的 `acceptance_decisions` 删除也按本次授权纳入；`omrs-maintenance/plan.md` 与 `progress.md` 仍保留「真实环境验收先跳过」的决定，清单整理不改变验收边界或 R14 来源核实要求。

## 行为变化

A4 与展示板只有恰好三列的表格采用 `8% / 39% / 53%`，其它列数均分栏宽，避免末列近零宽与异常行高。题面与答案、屏幕与打印媒体共用规则；本轮未再改业务实现、版本号或真实数据。

提交前 `git fetch origin` 成功，`origin/main...HEAD` 左右计数均为零。按本轮沟通推送当前分支，远端 `main` 不在本次推送目标中。提交与推送完成后用远端分支哈希复核。

## 影响文件

- `omrs/export_templates/a4.css`、`omrs/export_templates/board.css`：提交既有列宽修复。
- `tests/smoke_a4_print.py`：提交既有 1–6 列真实浏览器回归。
- `AI/export.md`、`AI/board.md`、根 `README.md`：提交既有导出规则说明。
- `AI/plans/omrs-maintenance/validation.json`：原样纳入既有删除；`progress.md` 记录本轮整理与验收范围不变。
- `AI/logs/2026-10-29_export-table-widths.md`：纳入此前未跟踪的修复日志；本日志记录当前基线上的复验，`AI/logs/log.md` 由门禁生成。

## 已执行验证

- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 -m unittest tests.test_export_fonts tests.test_board_export tests.smoke_a4_print tests.smoke_board_print -q`：25 项通过，含真实 Chromium、1–6 列表格、屏幕／打印媒体及 PDF。
- `python3 -m pytest tests/test_report_export.py -q`：7 项通过。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/e2e/schedule.py`：46 项通过、零失败，含隔离服务、实际 A4 下载、离线字体与 PDF 页数核对。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/visual/run.py --ref HEAD --pages schedule,board --themes light --viewports desktop --out /tmp/omrs-submit-20261107-visual`：2 对截图零差异，页面脚本错误零。常规页面 fixture 没有本次多列表格，页面截图不变符合预期；列宽变化由上述表格浏览器回归验证，旧任务日志另有专项前后对比。
- `python3 tests/check_ui.py`：五类计数均为零；`python3 tests/check_contrast.py`：58 组通过。
- `validation.json` 的 JSON 解析通过；`git diff --check` 通过。提交前已复核 `git diff --name-status` 与全部既有差异。
- `python3 tests/check_docs.py --write-log-index` 已生成索引；`python3 tests/check_docs.py --diff HEAD` 在补日志前后均为157份文档、零问题、3条既有大文件提醒，退出码均为零。

## 未执行验证

全仓后端、Node 与组件全集未重跑：仅提交已实现的打印 CSS 修复，已复验对应导出及真实页面链路。Windows Edge 实机与物理打印机不在当前 Linux 环境中；生产部署、服务重启和真实题库操作未执行。

提交与 GitHub 推送待门禁最终通过后执行，完成结果继续记入本日志。
