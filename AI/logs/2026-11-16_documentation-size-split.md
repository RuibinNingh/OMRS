# 2026-11-16 文档体积与分册维护

> **任务**
> - 标识：documentation-size-split
> - 状态：已交付

## 背景

用户要求「对于大小提醒能不能拆分,尽可能保证文档健康」。完整模式以 `55afe35` 和开工工作区为基线；前一轮文档维护及更早任务的未提交修改均保留。本轮针对文档门禁报告的根 README 和两份已完成历史计划文档分册，不改变计划范围、原始事实或业务实现。

## 行为变化

无业务行为变化。根 README 保留简明功能概览，将详细说明移至随源码提供的分册；两份历史计划的原路径保留章节入口，正文移入相邻文件。MCP 主文档修正上轮拆表后遗留的「上表／下表」指代。

## 影响文件

- `README.md`、`AI/features.md`、`AI/README.md`：拆出功能详览并建立索引。
- `AI/plans/frontend-rearch/exec-2026-09-26-codex.md`、`implementation-2026-09-26.md`、`progress.md`：拆出原实施计划，保留原文及历史状态。
- `AI/plans/v2.0.0/plan.md`、`behavior.md`、`progress.md`：拆出原最终预期行为，保留原文及历史状态。
- `AI/plans/README.md`：说明已完成历史文档分册的维护方式。
- `AI/mcp.md`：修正分册后的工具表指代。
- `AI/routes.md`：按功能详览涉及的路由引用重新生成；注册路由未改变。
- `AI/logs/2026-11-16_documentation-size-split.md`、`AI/logs/log.md`：记录本次维护并生成索引。

## 已执行验证

- 脚本逐字比较两份计划分册与 `HEAD` 中的原章节；功能详览按拆分前 SHA-256 比较，三段均一致。检查三个原入口至分册的相对链接均存在。
- 首次 `python3 tests/check_docs.py --diff HEAD`：171 个文档、1 处路由索引不同步、0 条大小提醒；新增功能分册被路由文档发现器识别。随后 `python3 tests/check_docs.py --write-routes`，核对差异仅为 `/annotate` 文档引用顺序。
- `python3 tests/check_docs.py --write-log-index`：生成任务日志索引；随后 `python3 tests/check_docs.py --diff HEAD` 检查 171 个文档，0 处问题、0 条提醒。
- `python3 -m unittest tests.test_docs_gate`：13 项通过；`git diff --check` 通过。

## 未执行验证

未运行完整业务测试或真实浏览器：本轮只整理文档，未改应用代码或页面。历史计划正文原样保留，不作为当前行为事实重新验证。
