# 2026-09-30 AI 草稿审核台右侧布局重设计

## 背景

用户原话：改一下 AI 草稿的 UI 设计，右侧布局重设计。执行者为 Codex，完整模式；工作区开工前已有其他未提交改动，本任务未重置或覆盖这些改动。

## 行为变化

- 桌面 AI 草稿详情改为内容审核区 + 右侧 Inspector：题目 / 答案解析保持阅读优先，题目信息、入库检查和保存 / 入库操作固定在右侧。
- 来源对照与框选改成独立 `workspaceMode`：`review` 显示正文审核，`source` 让 Canvas 占主区域、来源截图和训练状态位于右侧；来源 Canvas 不再追加在正文底部。
- 移动端增加「来源」审核标签，队列仍可折叠；块的移动 / 删除动作收进「更多」菜单，降低审核态噪声。
- 新增只读的 `reviewChecks(value)` 前端提示，展示科目、分类、题目正文和图片框选状态；入库业务校验仍由原有 `commitProblem` 与服务端负责。

## 影响文件

- `assets/app/features/create/drafts-view.js`：重排审核 / 来源工作区、Inspector、入库检查与块操作菜单。
- `assets/app/features/create/drafts.css`：新增桌面双栏、来源模式、移动端四标签和紧凑状态样式。
- `assets/app/features/create/drafts.js`：用 `workspaceMode` 替代底部来源展开状态，并保留切换、未保存保护和 Canvas 生命周期。
- `assets/app/features/create/drafts-state.js`：新增前端审核检查计算。
- `assets/app/features/create/index.js`：登记工作区切换动作。
- `tests/app/create-drafts.test.mjs`：覆盖 Inspector、来源模式和审核检查。
- `tests/e2e/drafts.py`：按新的来源工作区路径验证截图、框选和转文字。
- `AI/frontend/create.md`：同步草稿审核工作区与样式职责。

## 验证

已实际执行：

- `python3 tests/check_ui.py`：全仓 UI 计数 0，0 处问题。
- `python3 tests/check_contrast.py`：58 组对比度全部通过。
- `node --test tests/app/create-drafts.test.mjs`：7/7 通过。
- `python3 tests/app/run_browser.py`：浏览器单测 33/33 通过。
- `python3 tests/e2e/drafts.py`：草稿桌面 / 手机、来源 Canvas、框选、训练、提取和深浅主题审计 56/56 通过。
- `python3 -m compileall -q omrs tests`、`git diff --check`、相关模块 `node --check`：通过。
- `python3 tests/check_docs.py --diff HEAD`：0 处问题（仅有既存文件大小提醒）。

未作为本任务阻塞项处理：全量 `node --test tests/app/*.test.mjs` 中已有的 `core.test.mjs` 路由 hash 用例仍因测试环境 `location` 前缀为 `undefinedundefined` 失败；单独运行该文件可稳定复现，与本次草稿 UI 文件无依赖关系。
