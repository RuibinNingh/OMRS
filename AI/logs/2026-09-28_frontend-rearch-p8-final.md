# 2026-09-28 前端重构 P8 与终检

## 背景

按用户要求执行 P6「合入」后继续 P8，并在终检完成后更新生产目录、重启服务。工作树为 `codex/frontend-p8`；生产目录为 `/root/workspace/apps/OMRS`。

## 行为变化

- 筛选语义、标记选择器与标记管理迁入 `assets/app/domain/`。
- 删除旧全局脚本、过渡桥、旧样式和 UI 基线；前端入口由 `main.js` / `shell.js` 装配。
- `check_ui.py` 改为全仓零容忍，所有页面通过 hash 路由和原生模块挂载。

## 影响文件

代码、样式、仪表盘外壳、测试与文档均按 `git diff --name-status` 纳入本提交；新增模块包括 `domain/labels/*`、`domain/items.js`、`core/activity.js`、`styles/controls.css`。

## 验证

- `python3 -m unittest discover -s tests -p 'test_*.py' -q`：160 OK。
- `node --test tests/*.js tests/app/*.test.mjs`：330 / 330。
- `python3 tests/check_ui.py`：0；`python3 tests/check_contrast.py`：58 组通过。
- `python3 tests/app/run_browser.py`：33 / 33。
- `tests/e2e/shell_router.py`：20 / 20；`ui_bridge.py`：6 / 6；`dashboard.py`：26 / 26；`data.py`：21 / 21；`create.py`：80 / 80。
- `git diff --check` 通过。

## 部署

部署前记录生产 `omrs.service` 为 active，工作目录 `/root/workspace/apps/OMRS`，旧版本 v1.27.0。生产目录已备份后同步最终提交，服务重启后核对 `/api/status` 与页面主路径。回滚方式为恢复备份目录并重启同一 systemd 服务。
