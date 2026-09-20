# 2026-09-20 本地界面字体

## 变更摘要

界面字体改为本地静态资源。`assets/vendor/fonts/` 提供 Noto Sans SC 100–900 与 JetBrains Mono 100–800 的 WOFF2 Unicode 分片，`fonts.css` 使用同目录相对路径，未保留远程 URL 或 `local()` 覆盖；主仪表盘和移动收件箱均加载同一份字体 CSS。目录同时包含上游来源、SHA-256、文件体积清单和两套 SIL Open Font License 文本。

## 修改文件

- `assets/vendor/fonts/`：字体 CSS、107 个 WOFF2 分片、来源清单、许可与目录说明。
- `omrs_dashboard.html`、`assets/inbox_mobile.html`：改用本地字体 CSS。
- `assets/styles.css`：基础表单控件继承页面字体。
- `AI/frontend.md`、`AI/README.md`、`README.md`：同步本地字体和离线依赖边界。

## 验证

断网浏览器验证确认主页面无外部字体请求，24 个本地字体请求均返回 200；标题、复习调度画廊、侧栏版本和 `/m` 标题均使用自定义本地字体，零 `pageerror`，调度画廊回归正常。代码回归通过：`PYTHONPATH=. python3 tests/smoke_schedule_workbench.py`、`PYTHONPATH=. python3 tests/smoke_board_print_geometry.py`、`python3 tests/smoke_board_lock.py`。无后端改动，不需要重启服务。`git diff --check` 与 `python3 tests/check_docs.py` 均通过。

## 同步过的文档

已移除页面运行时依赖 Google Fonts 的过时描述，补充本地字体目录、字体 CSS、Unicode 分片、许可和来源清单说明。
