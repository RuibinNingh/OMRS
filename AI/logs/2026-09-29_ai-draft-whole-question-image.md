# 2026-09-29 AI 草稿完整题目图片

## 背景

用户指出生产草稿 `DR-20260929-2e495e` 在题目含不可完整转述的曲线图时，仍把题干、两幅图和小问拆成多个题目块；用户要求这类题的整个题目保留为图片。Codex 以完整模式只读核对真实 Vault：该草稿为待框选、revision 1，一张来源截图 1080×3634，题目块顺序为文字、图片、图片、文字，答案为文字。`agent.db` 中对应 `create_draft` 调用提交的就是这些块，审核页没有自行拆分。后续 detect 作业返回两个候选框，但因两个题目图片块与候选无法唯一映射，结果为 suggested／ambiguous，没有自动写入任一框。

## 行为变化

助手现在按整道题目判断是否可转文字；只要关键图表无法完整转述，就以覆盖题干、图表和全部小问的图片块保存题目，同一来源图在同一道题中只引用一次。答案仍可独立保存为文字。`create_draft` 工具拒绝题目文字与图片混排、同图重复建题目图片块，提示助手修正后重试；人工审核的有序块编辑能力不变。既有生产草稿未改写。

## 影响文件

- `omrs/agent/prompts/system.md`：明确整道题目图片规则。
- `omrs/agent/tools/drafts.py`：更新工具说明并校验 AI 建草稿的题目块。
- `tests/test_agent_draft_tools.py`：覆盖本次生产记录同型的混排和重复图拒绝，以及完整图片题目加文字答案。
- `AI/agent.md`、`README.md`：同步当前行为。
- `AI/logs/log.md`：由检查脚本生成索引。

## 验证

已执行：`python3 -m unittest tests.test_agent_draft_tools tests.test_drafts tests.test_agent_images -q`，46 项通过；`python3 tests/e2e/assistant.py`，真实浏览器隔离 Vault 58/58 通过；`git diff --check`，0 问题。`python3 tests/check_docs.py --write-log-index` 已生成索引。按 HEAD 归档构建只含本任务改动的临时基线后执行 `python3 tests/check_docs.py --diff HEAD`，67 份文档、0 问题、3 条现有超长提醒，退出码 0。

当前共享工作树直接执行同一 `--diff HEAD` 返回 6 处问题，均来自本任务开工前后其他人正在修改的 `omrs/ai_assist.py`、`omrs/server.py`、`assets/app/features/create/`、`assets/app/styles/ui.css`、`assets/app/ui/` 及对应测试而尚未更新其映射文档。本任务未覆盖、暂存或修订这些改动。

未执行：未用真实模型重放该生产截图；未修改生产草稿、部署代码或重启服务。新规则需发布后才会影响后续 AI 建草稿，已有草稿须人工审核调整。

## 方向调整与最终行为

用户随后明确“修改方向,允许混排,但是模型要知道规则”。首版提交 `3002532` 的工具层混排／同图重复校验因此撤回；保留 `create_draft` 原有的有序图文块契约。最终提示词和工具说明允许准确、独立的局部图与完整文字按阅读顺序混排；当题干、图表和小问相互依赖，或拿不准拆分会否漏信息时，要求模型保留整题图片。同一来源图确有多个独立局部时可建多个图片区块。生产草稿 `DR-20260929-2e495e` 是需要整题图片的案例，不把这种判断硬编码成对所有图文题的禁止规则。

调整后已执行：`python3 -m unittest tests.test_agent_draft_tools tests.test_drafts tests.test_agent_images -q`，46 项通过；`python3 tests/e2e/assistant.py`，隔离浏览器 58/58 通过；`git diff --check`，0 问题。按首版提交 HEAD 归档并仅覆盖本次调整的文件后执行 `python3 tests/check_docs.py --diff HEAD`，67 份文档、0 问题、3 条现有超长提醒，退出码 0。生产记录和服务仍保持只读、未发布。
