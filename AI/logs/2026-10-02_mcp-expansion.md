# 2026-10-02 MCP 全量扩展

## 背景

用户批准完整 38 工具扩展，要求 Codex 完整模式连续完成 P0–P7。本批基线 d716157，开工工作区干净。执行说明在 AI/plans/mcp-integration/exec-2026-10-02-expansion.md。生产变更、推送、版本升级不在授权范围。

## 行为变化

P0 只固定规范，无业务代码变化。扩大原计划范围但保留历史执行与发布事实。

## 影响文件

AI/plans/mcp-integration 的总纲、进度、扩展执行说明和本日志；日志索引由检查脚本生成。

## 验证

本批开工只读复核 Git 状态和现有代码。规划基线历史通过 527 Python 和 39 SDK/浏览器，不计入新增功能验收。P0 实跑 docs --diff HEAD：82 文档、0 问题、3 条既有大文件提醒；git diff --check 通过。

## P1 查询

实现 5 个查询工具及共同分页/稳定错误契约；当前正文后续页必查哈希，历史版本只读已登记 blob，草稿图验证来源 SHA 和普通路径。时间线先按题/科目/日期筛选、显示当前修正状态；测试发现 Session 投影 UIDs 实际为对象数组，已按代码修正解析。

影响 omrs/mcp/server.py、queries.py、common.py、question_images.py、runtime_records.py，相关 MCP/查询回归及模块文档。实跑 MCP 专项 73/73（含 5 项新增、真实 SDK，无 SKIP）；MCP SDK/浏览器 39/39；docs 82 文档、0 问题；git diff --check 通过。未运行全量 Python，留 P7。
