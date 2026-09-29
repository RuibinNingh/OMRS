# 2026-09-29 收件箱截图重置

## 背景

用户要求：「录入题目-框选 加一个重置功能 点击后会情况这个截图的所有进度 因为我发现有时候AI识别不出来就一直卡着」。完整模式，基线为本任务开工时的 HEAD；已有未提交日志和 `.playwright-mcp/` 保留在工作区，本任务未纳入。

## 行为变化

「录入题目 → 框选」增加「重置此图」。确认后只清空当前截图的框、提取结果、题卡表单、盲标和处理状态，版式回默认，原图保留；即使提取卡住也可操作。待保存补丁被取消，晚到的保存响应、框选、提取与分类结果按 `reset_epoch` 拒绝回写。已有题卡入库、已丢弃和训练专用图不能重置，避免重复创建已入库题目。重置记录 `item.reset` 标注事件，但不计作拒绝 AI 框。

## 影响文件

- `omrs/inbox.py`、`omrs/server.py`：原子重置、处理代次校验和接口。
- `assets/app/features/create/`：重置按钮、确认、保存队列取消和旧任务结果保护。
- `tests/test_inbox.py`、`tests/app/create-inbox.test.mjs`、`tests/e2e/create.py`：旧结果、保存竞态和真实页面路径。
- `AI/inbox.md`、`AI/api.md`、`AI/data.md`、`AI/frontend/create.md`、`AI/frontend/architecture.md`、`AI/routes.md`、`README.md`：同步当前行为、接口和测试路径。

## 验证

已执行：`python3 -m unittest tests.test_inbox`（21 通过）；`node --test tests/app/create-inbox.test.mjs`（13 通过）；`node --test tests/app/*.test.mjs`（367 通过）；`python3 tests/e2e/create.py`（100/100）；`python3 tests/app/run_browser.py`（32 通过）；`python3 tests/check_ui.py`（0 处问题）；`python3 tests/check_contrast.py`（58 组、0 组不达标）；`python3 -m py_compile omrs/inbox.py omrs/server.py tests/e2e/create.py`（通过）；`git diff --check`（通过）；`python3 tests/check_docs.py --diff HEAD`（0 处问题、2 条现有大文件提醒）。

视觉对比 `python3 tests/visual/run.py --ref HEAD --pages create --create-stage process` 已执行，4 张截图均有预期差异：桌面浅色 1.713%、深色 1.644%，手机浅色 6.38%、深色 6.515%。差异来自区域面板标题行新增「重置此图」按钮；手机标题行增高使其下方区域内容整体下移，截图中无脚本错误和异常遮挡。`python3 tests/check_docs.py --write-log-index` 已生成索引。

未执行：生产部署与重启；本任务没有收到单独的生产发布授权。
