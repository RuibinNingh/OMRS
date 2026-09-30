# 2026-09-30 入口背景配置

## 背景

用户要求入口锁屏页支持黑洞预设、自定义图片 / 视频背景和高斯模糊参数，配置保存到当前 Vault。本任务按 `AI/plans/entry-background/plan.md` 执行，运行模式为 Codex 完整模式。工作区原有展示板相关未提交改动已保留且未纳入本任务。

## 行为变化

- `GET /api/config` 增加脱敏 `entry_background`；新增 multipart `POST /api/entry-background` 和当前媒体 `GET /api/entry-background`。
- 入口锁屏页按配置显示黑洞 WebGL 或自定义图片 / 视频；媒体失败、配置损坏和资源缺失回退黑洞，视频按 reduced-motion 规则暂停。
- 设置 → 外观与显示增加入口背景卡片：黑洞 / 自定义模式、图片 / 视频本地预览、0–32px 高斯模糊和保存状态。
- 自定义媒体存于 `错题/.omrs/entry-background/`，随现有备份恢复流程包含；切回黑洞时不从公共接口暴露旧文件。

## 影响文件

- 后端：`omrs/entry_background.py`、`omrs/common.py`、`omrs/locking.py`、`omrs/server.py`。
- 前端：`assets/app/features/settings/entry-background.js`、`appearance-view.js`、`index.js`、`settings.css`。
- 测试：`tests/test_entry_background.py`、`tests/app/settings.test.mjs`、`tests/e2e/settings.py`。
- 文档：`AI/api.md`、`AI/data.md`、`AI/security.md`、`AI/frontend/shell.md`、`AI/frontend/settings.md`、`AI/routes.md`、`README.md`、`AI/plans/entry-background/`、本日志及自动生成日志索引。

## 验证

已实际执行：

- `python3 -m py_compile omrs/server.py omrs/entry_background.py`：通过。
- `python3 -m unittest tests.test_entry_background`：6/6 通过。
- `python3 -m unittest tests.test_security`：13/13 通过。
- `node --test tests/app/settings.test.mjs`：23/23 通过。
- `python3 tests/check_ui.py`：通过；`python3 tests/check_contrast.py`：通过。
- `python3 tests/app/run_browser.py`：34/34 通过。
- `python3 tests/e2e/settings.py`：62/62 通过（包含入口背景主路径）。
- `python3 tests/e2e/entry_background.py`：5/5 通过，覆盖桌面 / 手机默认黑洞和自定义图片模糊。
- `python3 -m unittest discover -s tests -p 'test_*.py'`：422/422 通过。
- `node --test tests/app/*.test.mjs`：395/396 通过；唯一失败为与本任务无关的既有 router 测试环境假设。
- `python3 tests/check_docs.py --write-routes` 与 `--write-log-index`：已执行。

未执行：本轮未生成 `tests/visual/run.py --ref HEAD` 的视觉前后对比报告；入口页 E2E 已覆盖桌面 / 手机布局和媒体渲染，视觉基线差异需另行评审。

## 合入

完整模式不生成补丁交付包。本任务提交时只纳入上述入口背景相关文件，保留 `omrs/export_templates/board.js`、`tests/e2e/board.py` 及展示板文档的现有未提交改动。
