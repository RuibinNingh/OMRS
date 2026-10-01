# MCP 发布前 UI 门禁修正

## 背景

用户授权“推送一下，然后部署生产”。Hermes Agent，完整模式；候选基线 `14eeeb0`。独立发布快照重新运行门禁发现 `assets/app/features/create/drafts.js` 为 403 行，违反 R8 的 400 行限制；同一问题可在当前工作区稳定复现，上一生产基线 `2957939` 为 400 行。本次修正不将开发交付日志中的通过声明当成当前验收结果。

## 行为变化与影响文件

仅合并来自同一模块的两个 import 声明、移除两行空白，将控制器恢复为 400 行；MCP 权限、来源与审核业务逻辑未改。修改 `assets/app/features/create/drafts.js`，新增本日志并用生成器更新 `AI/logs/log.md`。无业务契约变化，既有模块说明继续适用。

## 已执行验证

- 修正前 `python3 tests/check_ui.py` 和 `tests.test_ui_gates.RepositoryGatesTest.test_repository_passes_ui_gate` 因 403 行失败。
- 修正后 `python3 tests/check_ui.py`：0 处问题。
- `python3 -m unittest tests.test_ui_gates -q`：12 项通过；保留既有 ResourceWarning，不修改测试或放宽门禁。
- `node --test tests/app/create-drafts.test.mjs`：8 项通过。
- `git diff --check`：通过。

首次完整候选 Python 验收另报测试环境缺少 playwright；该项为测试依赖缺失，不是业务回归。生产发布前补齐隔离测试依赖，再执行完整门禁与真实浏览器闭环。生产部署结果另记新任务日志，不写回开发交付的历史记录。
