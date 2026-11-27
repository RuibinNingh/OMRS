# 2026-11-27 题库与复习调度录入日期筛选

> **任务**
> - 标识：entry-date-filters
> - 状态：已交付

## 背景

用户原话：「OMRS复习调度我打算升级筛选方式」「比如筛选录入时间」「计划一下」「题库也是这样筛选」「Please implement the plan.」「接下来合并生产和main,提交GitHub」。Codex 完整模式。功能工作树从 GitHub `main` 基线 `e5daa45` 创建；生产原为 v2.14.0、源码提交 `84f3f9f`。仓库没有 `production` 分支，功能提交 `ac2965f305befe0e462766bbf7c3b67b942cc4e5` 已推送到 `main` 并按用户授权发布到生产。

## 行为变化

题库筛选抽屉与复习调度「更多筛选」加入录入日期条件：全部、今天、最近 7／30 天、自定义起止日。相对范围包含上海当天；自定义日期在点击应用后生效，可只设置一端，倒置范围会提示并保留现有结果。条件与其它筛选取交集并可单独移除。

新增最早／最近录入排序。使用有效 `entry_date`，缺失时回退到 `created_at` 对应的上海日期；日期缺失的题在不限制日期时保留、日期排序时置后，同日按 UID 升序。日期筛选或排序生效时显示录入日。题库预设保存相对模式或固定端点，旧预设仍默认不筛日期。

## 影响文件

- 共用日期逻辑与 UI：`assets/app/domain/entry-date.js`、`entry-date-field.js`、`entry-date.css`、`items.js`，以及 `assets/app/styles/index.css`、`assets/app/styles/tokens.css`。
- 题库：`assets/app/features/questions/index.js`、`list.js`、`state.js`、`view.js`。
- 复习调度：`assets/app/features/schedule/arrange.js`、`arrange-ctl.js`、`arrange-view.js`、`index.js`、`schedule.css`。
- 验证：新增 `tests/app/entry-date.test.mjs`、`tests/e2e/entry_date_filters.py`；`tests/visual/run.py` 增加展开筛选截图入口。
- 文档与版本：`README.md`、`AI/README.md`、`AI/changelog.md`、`AI/environment.md`、`AI/features.md`、`AI/frontend/architecture.md`、`AI/frontend/design-system.md`、`AI/frontend/library.md`、`AI/frontend/review.md`、`omrs/version.py`、`omrs_dashboard.html`。版本 v2.15.0 已发布；本次收尾更新 `AI/environment.md` 与本任务日志。

## 已执行验证

- `node --test tests/app/*.test.mjs`：612 项通过。
- `python3 -m unittest tests.test_asset_cache tests.test_web_assets -q`：17 项通过。
- `python3 tests/check_ui.py`：0 处问题；`python3 tests/check_contrast.py`：58 组通过。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/app/run_browser.py`：35 项通过。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/e2e/entry_date_filters.py`：首次运行在旧计划详情文案「共 1 题」断言失败；根据 v2.14.0 实际显示「原计划 1 题」修正后，13 项通过、0 个页面脚本错误。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/e2e/questions.py`：106 项通过；`tests/e2e/schedule.py`：54 项通过。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/visual/run.py --ref HEAD --pages questions,schedule --filters-open --out /tmp/omrs-entry-date-v2150-visual`：脚本错误为 0，8 档均有预期差异；题库桌面约 2.18%–2.48%、手机约 9.22%–9.97%，调度桌面约 1.78%–1.81%、手机约 13.10%–14.56%。差异来自新增筛选行及后续控件下移；完整报告在 `/tmp/omrs-entry-date-v2150-visual/report.html`。
- `python3 tests/check_docs.py --write-log-index` 已生成索引；`python3 tests/check_docs.py --diff e5daa45` 检查 173 份文档，0 问题、0 提醒；`git diff --check` 通过。
- 发布收尾文档门禁：`python3 tests/check_docs.py --diff ac2965f305befe0e462766bbf7c3b67b942cc4e5` 检查 173 份文档，0 问题、0 提醒；`git diff --check` 通过。
- 精确归档包含 1,761 个文件，与 Git 提交内容一致；归档门禁 `ui`、`contrast`、`pytest`、`components`、`schedule`、`export`、`reminders`、`print`、`shell`、`backend`、`node`、`questions`、`entry_date_filters`、`assets` 均退出码 0。结果记录在 `/root/workspace/apps/releases/OMRS-entry-date-v2150-20261127/gates.json`：分别有 0 个 UI 问题、58 组对比度、7 项 pytest、35 项组件浏览器、54 项调度、39 项导出、30 项提醒、17 项打印、24 项 shell、102 项后端、612 项 Node、106 项题库、13 项日期筛选及 17 项资源测试通过。
- 第一次部署预检在停服前被测试产生的未归档 `__pycache__` 拦截；清理缓存并将清理加入预检后重跑成功，生产服务未因首次拦截中断。
- 生产预检确认无有效进行中操作、无遗留恢复意图，保留 9 条 runtime proposals；`omrs.service` 已从 v2.14.0 切至 v2.15.0，PID `165400`，重启计数 0，实际运行目录 `/root/workspace/apps/releases/omrs-ac2965f`。题库仍为 384 题，工作区冲突 0，相邻网关和框选服务 PID 未变。
- 生产备份验证 1,625 个文件及 9 个数据库；切换前后 57 张业务表、1,428 个受保护文件哈希一致。9 个核心静态资源返回正确归档内容并通过 ETag 304 验证；本机入口和两项相邻健康端点返回 200，公网首页返回 200，匿名 API 与私有静态资源返回 401，systemd 错误日志为空。部署结果见 `/root/workspace/apps/releases/OMRS-entry-date-v2150-20261127/result.json`。
- 发布后复核：主服务 v2.15.0、384 题、工作区扫描冲突 0，PID `165400`、重启计数 0；生产归档与 GitHub `main` 上的功能提交 `ac2965f305befe0e462766bbf7c3b67b942cc4e5` 一致。

## 未执行验证

实体手机上的 Safari 原生日期弹层未验证，现有移动端验证使用 Chromium 触屏视口。
