# 2026-09-28 合并工作区与 v1.28.0，补完前端重构 P8 的清理（v1.28.1）

## 背景

用户原话：「合并,然后全面审查上次重构的完成情况,我发现似乎有很多冗余,审核整个项目,然后修复后替换展示板为目标样式」，随后「继续」。受限模式：新导出包 `OMRS-source-sanitized-20260928T000336Z`（v1.27.0，比上一包多 7 个文件的修复），本地基线提交 `54c53eb`；在它上面应用上一任务的 `changes-2026-09-28-ai-agent.patch`（v1.28.0）。目标样式页 `omrs-board-redesign.html` 存为 `AI/plans/board-redesign/target.html`；展示板改版本次只完成分析与计划（`AI/plans/board-redesign/`），实现留到下一任务。

## 行为变化

- 设置页、标记选择器与管理器、题目视图、录入页的按钮与输入框改用 `ui-*` 组件（外观与其他页一致，尺寸档位不变）。其余页面无可见变化。
- 版本 v1.28.1。

## 影响文件

- 合并：v1.28.0 补丁的 83 个文件（见上一任务日志）。
- 删除：`assets/` 下 `actions.js`、`app.js`、`board.js`、`board_picker.js`、`board_preview.js`、`catalog.js`、`core.js`、`dashboard.js`、`data.js`、`export.js`、`feedback.js`、`history.js`、`inbox.js`、`instant.js`、`labels.js`、`qtable.js`、`questions.js`、`qview.js`、`recommend.js`、`recommend_v2.js`、`reports.js`、`schedule.js`、`styles.css`；`tests/test_*.js` 14 个与 `tests/smoke_*.js` 2 个（测上面这些死文件，其中 13 个在 `tests/app/` 有标注的迁移版）；`tests/smoke_board_integrity.py`、`smoke_board_lock.py`、`smoke_board_print_geometry.py`（调用 P7 起就不存在的 `boardReloadData` 等全局）；`assets/app/styles/controls.css`。
- 代码：`assets/app/shell.js`（去 `enter(win)`、注释）、`features/board/runtime.js`（`legacyCall` → `unwrap`、注释）、`features/schedule/index.js`（`openFromLegacy` → `openPlan`）、10 个模板文件的类名、5 处百分比格式、`features/feedback/view.js`（import 位置）、`styles/ui.css` / `gallery.css` / `base.css` / `ui/dialog.css` / `labels.css` / `settings.css` 的选择器。
- 测试：`tests/app/browser_tests.js`（删旧 `.btn` 用例）、`tests/app/core_tests.js`（外壳只认 `mount`）、`tests/e2e/questions.py` / `schedule.py` / `instant.py` / `feedback.py` / `ui_bridge.py`、`tests/visual/run.py`。
- 文档：`AI/frontend.md`、`AI/frontend/architecture.md` / `components.md` / `design-system.md` / `shell.md` / `qview.md` / `board-ui.md` / `dashboard.md` / `library.md`、`AI/board.md`、`AI/environment.md`、`AI/optimization.md`、`AGENTS.md`、`AI/plans/frontend-rearch/progress.md`（审查结论）、新增 `AI/plans/board-redesign/`、版本号四处与 `AI/changelog.md`。

## 验证

审查方法：列 `assets/` 根目录文件并查引用；建 `assets/app` 的 import 图找无人引用的模块与导出；按类名族查重复组件；在基线 worktree 与当前树逐个跑 E2E 对比。

- `check_ui.py`：0 问题（基线 88 处，全部来自旧文件）。`check_contrast.py` 58 组 0 不达标。`check_docs.py --diff 54c53eb` 0 问题。
- `python3 -m unittest discover -s tests -p 'test_*.py'`：182 个全过。`node --test tests/app/*.test.mjs`：336 个全过。`tests/app/run_browser.py`：32 / 0。
- E2E（各自隔离实例）：assistant 22/22、settings 50/50、feedback 31/31、questions 92/92、schedule 45/45、instant 23/23、ui_bridge 6/6、shell_router 20/20、dashboard 26/26、data 21/21、history 23/23、catalog 26/26、reports 24/24、board 35/35。基线上 questions（3）、schedule（4）、instant（中途崩）、feedback（1）都失败，原因都是调用已删全局。
- `board_picker` 30/31：「已全部在板中」一项在基线上同样失败；「Enter 加入并关闭」偶发失败（两次重跑均通过），未处理。
- 未执行：`tests/visual/run.py --ref` 视觉对比（类名统一后设置页等处像素会有细微差异）。

## 合入（仅受限模式交付）

- 补丁：`changes-2026-09-28-merge-cleanup.patch`，基线为导出包 `20260928T000336Z`（v1.27.0），**已包含** v1.28.0 AI 助手。在该包的干净工作区执行 `git apply --check` 后 `git apply --index`，作为一个提交 `合并 v1.28.0 并补完 P8 清理（v1.28.1）`。补丁删除上文所列文件；若本机工作区里还有这些旧文件的未跟踪副本（导出包里有，说明本机磁盘上也有），一并删除。
- 预期门禁：同「验证」。
- 完整模式补做：① `--write-log-index`；② `tests/visual/run.py --ref v1.27.0`，差异只应在按钮 / 输入框改用 `ui-*` 的几处；③ 部署等用户授权。
