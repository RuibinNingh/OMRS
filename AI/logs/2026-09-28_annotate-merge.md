# 2026-09-28 框选标注页合入当前版本

## 背景

用户要求：「更新生产目录,这个版本是落后的,但是添加了数据标记,合并」。输入为 `OMRS-annotate-page-20260928.zip`。完整模式从工作区 `31b59f4` 合入；生产服务开工时运行 `/root/workspace/releases/omrs-f863761`，真实 Vault 在 `/root/workspace/apps/OMRS`。压缩包里的任务日志是受限模式交付记录，按内容核对源码差异，不整包覆盖当前版本。

## 行为变化

- 新增独立 `/annotate` 页，用于上传截图并框选「题目 / 答案」，支持批量上传、快捷键、完成状态与 YOLO / JSONL 导出。数据独立存于 `错题/.omrs/annotate/`。
- 录入题目页「AI 训练」工作区显示标注集进度，并在新标签页打开标注页。
- 当前分支的 AI 草稿 P1-1 至 P1-3、展示板 UI 和计划状态保持当前版本；没有采用压缩包中较旧的同名计划、环境文档和 AI 助手文件。

## 影响文件

- 代码与测试：新增 `omrs/annotate.py`、`assets/app/annotate.html`、`assets/app/features/annotate/`、三层标注测试；修改 `omrs/server.py`、训练页三个文件及 `tests/check_docs.py`。
- 文档：同步 API、数据、前端、访问控制、维护环境、源码到文档映射、根 README 和自动生成的路由表；新增 `AI/frontend/annotate.md`，保留受限模式原任务日志并生成日志索引。

## 验证

已实际执行：

- `env -u OMRS_SYSTEMD_SERVICE python3 -m unittest discover -s tests -p 'test_*.py' -q`：226 例 OK。
- `node --test tests/app/*.test.mjs`：337 通过 / 0 失败。
- `python3 tests/check_ui.py`：0 处问题；`python3 tests/check_contrast.py`：58 组、0 组不达标。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/app/run_browser.py`：32 通过 / 0 失败。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/annotate.py`：34/34 通过；`env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/create.py`：80/80 通过。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/visual/run.py --ref HEAD --out /tmp/omrs-annotate-visual-20260928`：48 档截图中 0 档有差异，脚本错误无；默认页组不含 AI 训练工作区与独立标注页，这两处由上述 E2E 的主路径与四档审计覆盖。
- `python3 tests/check_docs.py --write-routes` 与 `--write-log-index` 已生成路由表和日志索引；`python3 tests/check_docs.py --diff HEAD`：47 个文档、0 处问题，2 条既有文件体积提醒。

待复核：发布目录隔离实例。发布目录切换、生产重启、生产浏览器验收另记实际结果。
