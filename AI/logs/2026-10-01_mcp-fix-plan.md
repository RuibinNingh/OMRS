# 2026-10-01 MCP 审查修复计划

## 背景

用户先要求「审查 omrs mcp 实现，看看有没有 bug」，随后转贴外部读取联调与科目统计错误报告，本轮要求「制定修复计划」。执行环境为 Codex 完整模式；源码调查基线 `79f0a548b7fbfd68b225cbf9f790e1cef619bdc4`，开工 `git status --short` 为空。任务属于 `AI/plans/mcp-integration/`。

## 行为变化

无业务行为变化；仅制定 F0–F4 修复执行说明。先修科目概况，再修数据库迁移竞争、幂等鉴权及 scope 工具发现。执行者 Codex、完整模式；所有草稿创建验收用临时 Vault，生产发布、Tunnel 配置和真实库测试草稿写入单列为后续授权范围。

## 影响文件

- 新增 `AI/plans/mcp-integration/exec-2026-10-01-mcp-fixes.md`：用户原话、证据、四项决策、提交粒度、验收与门禁。
- 更新该计划 `plan.md`、`progress.md`：登记修复批次及计划变更，保留已完成的集成/发布历史，下一步指向新说明。
- 更新 `AI/plans/README.md`：现有计划索引加入 MCP 修复批次。
- 更新 `AI/optimization.md`：统一登记四项尚未修复的缺陷；更新 `AI/mcp.md` 为当前可验证的工具发现与幂等鉴权行为，修复状态指向清单。
- 新增本任务日志；`AI/logs/log.md` 通过文档检查脚本生成。

本轮仅修改文档，未改业务源码、测试或配置；交付前结合 `git diff --name-status` 与未跟踪文件复核范围。

## 已实际执行的验证

本会话前面的只读审查阶段，源码仍为本轮基线：

- `env -u OMRS_SYSTEMD_SERVICE python3 -m unittest tests.test_mcp tests.test_mcp_keys tests.test_mcp_http tests.test_mcp_protocol tests.test_mcp_draft_atomic -q`：46/46 通过。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/mcp.py`：15/15 通过，真实临时实例/SDK/浏览器。
- 补充临时 Vault 验证：未知科目仍有全库到期数；不同 scope 均发现十项工具；图片校验期间吊销仍返回幂等结果；160 次自然并发幂等查询出现 3 次列竞争，120 次完整工具调用出现 1 次内部错误。故障注入和调用方式的性质已在执行说明 §2 分开标注。

本轮计划编写阶段已静态复核函数、测试与锁调用方，并核实展示快照先舍入、统计使用原始熟练度的差别，执行说明要求科目聚合复用原始统计口径。

- `python3 tests/check_docs.py --write-log-index`：已生成索引。
- `python3 tests/check_docs.py --diff HEAD`：77 个文档，0 问题；3 条既有大文件提醒。首次检查只因新增日志尚未生成索引失败，生成后通过。
- `git diff --check`：通过；实际变化为 6 个已跟踪文档及 2 个新文档，未包含源码、测试或配置。

本轮只改文档，不重复已有业务/浏览器测试；最终编辑后复核文档与 diff 门禁。

## 未执行的验证与下一步

尚未实现四项修复，未编写或运行修复后的失败回归；Python/Node 全量、助手/草稿浏览器复验留给执行者按新说明实际执行，不能沿用历史计数。未连接生产端口、读取真实 Vault、创建真实测试草稿、重启服务、修改 Nginx/systemd、推送或配置目标账户/Tunnel。

Codex 完整模式通读新执行说明后按 F0→F4 连续完成，建立独立修复任务日志，不把后续实现写回本规划日志。
