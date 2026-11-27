# 2026-11-27 题库与复习调度录入日期筛选

> **任务**
> - 标识：entry-date-filters
> - 状态：进行中

## 背景

用户原话：「OMRS复习调度我打算升级筛选方式，比如筛选录入时间」「计划一下，题库也是这样筛选」「Please implement the plan.」「接下来合并生产和main,提交GitHub」。Codex 完整模式。功能工作树从 GitHub `main` 基线 `e5daa45` 创建；生产当前为 v2.14.0、源码提交 `84f3f9f`。没有 `production` 分支，按用户授权准备将新版本合入 `main` 并发布生产。

## 行为变化

题库筛选抽屉与复习调度「更多筛选」加入录入日期条件：全部、今天、最近 7／30 天、自定义起止日。相对范围包含上海当天；自定义日期在点击应用后生效，可只设置一端，倒置范围会提示并保留现有结果。条件与其它筛选取交集并可单独移除。

新增最早／最近录入排序。使用有效 `entry_date`，缺失时回退到 `created_at` 对应的上海日期；日期缺失的题在不限制日期时保留、日期排序时置后，同日按 UID 升序。日期筛选或排序生效时显示录入日。题库预设保存相对模式或固定端点，旧预设仍默认不筛日期。

## 影响文件

- 共用日期逻辑与 UI：`assets/app/domain/entry-date.js`、`entry-date-field.js`、`entry-date.css`、`items.js`，以及 `assets/app/styles/index.css`、`assets/app/styles/tokens.css`。
- 题库：`assets/app/features/questions/index.js`、`list.js`、`state.js`、`view.js`。
- 复习调度：`assets/app/features/schedule/arrange.js`、`arrange-ctl.js`、`arrange-view.js`、`index.js`、`schedule.css`。
- 验证：新增 `tests/app/entry-date.test.mjs`、`tests/e2e/entry_date_filters.py`；`tests/visual/run.py` 增加展开筛选截图入口。
- 文档与版本：`README.md`、`AI/README.md`、`AI/changelog.md`、`AI/environment.md`、`AI/features.md`、`AI/frontend/architecture.md`、`AI/frontend/design-system.md`、`AI/frontend/library.md`、`AI/frontend/review.md`、`omrs/version.py`、`omrs_dashboard.html`。准备发布版本 v2.15.0。

## 已执行验证

- `node --test tests/app/*.test.mjs`：612 项通过。
- `python3 -m unittest tests.test_asset_cache tests.test_web_assets -q`：17 项通过。
- `python3 tests/check_ui.py`：0 处问题；`python3 tests/check_contrast.py`：58 组通过。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/app/run_browser.py`：35 项通过。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/e2e/entry_date_filters.py`：首次运行在旧计划详情文案「共 1 题」断言失败；根据 v2.14.0 实际显示「原计划 1 题」修正后，13 项通过、0 个页面脚本错误。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/e2e/questions.py`：106 项通过；`tests/e2e/schedule.py`：54 项通过。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/visual/run.py --ref HEAD --pages questions,schedule --filters-open --out /tmp/omrs-entry-date-v2150-visual`：脚本错误为 0，8 档均有预期差异；题库桌面约 2.18%–2.48%、手机约 9.22%–9.97%，调度桌面约 1.78%–1.81%、手机约 13.10%–14.56%。差异来自新增筛选行及后续控件下移；完整报告在 `/tmp/omrs-entry-date-v2150-visual/report.html`。
- `python3 tests/check_docs.py --write-log-index` 已生成索引；`python3 tests/check_docs.py --diff e5daa45` 检查 173 份文档，0 问题、0 提醒；`git diff --check` 通过。

## 未执行验证

尚未执行发布归档门禁、生产预检、GitHub 推送和生产切换。实体手机上的 Safari 原生日期弹层未验证，现有验证使用 Chromium 触屏视口。
