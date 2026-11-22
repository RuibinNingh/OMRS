# 2026-11-21 反馈录入单题处置与结单

> **任务**
> - 标识：feedback-closeout
> - 状态：已交付

## 背景

用户原话「可以,委派Codex执行」「不需要验收,到时候部署生产」。Codex 在无 Git 的隔离源码副本执行确认稿 A+B，开发基线为 c5a1fda，发布参照为 v2.12.1 的 819d297 归档加既有文档。开发源与只读副本开工文件比较无差异。

## 行为变化

反馈页按原号显示已录、待录、不可录、本次跳过和身份待确认。录入可分批。题库停用和归档只影响当时可录性，关闭后以 Ledger 的处置快照显示历史。全部有效反馈仍自动完成。存在例外时用户可在反馈页或调度详情确认结束。全批无反馈的计划明确显示无反馈。

## 影响文件

- 后端的 Session 查询、事务、反馈、HTTP 适配、Ledger 加列与重放。
- 前端的 Session 领域模块、反馈工作台、调度与首页，版本和资源指纹随源码更新。
- 合成 Vault 回归、浏览器开发回归、API 和维护文档。

## 已执行验证

- Python RED 为 16 项，1 失败和 4 子用例报错。复现停用后最后一次成功反馈提前完成，以及缺失新进度字段。
- `PYTHONPATH=.:tests python3 -m unittest test_sessions_feedback test_session_queries test_session_pause test_session_operations test_session_closeout test_mcp_review_sessions test_config_publication test_asset_cache test_web_assets` 退出 0。98 项，4 跳过。合成 Vault 覆盖双进程结单、事务回滚、增量与全量重放、重启和备份恢复。
- `PYTHONPATH=. python3 -m unittest discover -s tests` 退出 1。候选 1054 项，基线 1041 项。两边均为 3 失败、48 错误、70 跳过，失败与错误项目名称逐条一致。本机缺 Pillow、MCP、Pydantic 等可选依赖，其余基线失败仍存在。
- `TZ=Asia/Shanghai node --test --test-reporter=tap tests/app/*.test.mjs` 退出 0，606 项通过。按上海时区复跑了一个既有的时间显示断言。
- `node tests/e2e/feedback_closeout.mjs` 退出 0，14 项通过。通过 Chromium CDP 执行仓库组件页，35 项通过。两项均无页面脚本错误。UI 门禁零违规，58 组对比度达标。
- 路由与日志索引均由脚本生成。文档检查与以只读文件副本供给差异的检查均退出 0，169 个文档、零问题、6 条体积提醒。
- 旧表升级演练保留原 8 条链记录。投影切换追加既有启动重算事件。发生新跳过和结单事实后，旧版重建无法呈现处置，原链 12 条记录仍逐条一致。新版从原链恢复快照。

## 未执行验证

Playwright 入口已尝试，当前容器缺依赖，原脚本未完成。独立验收、线上浏览、真机和视觉比对由本轮需求免除。工作区没有 Git，实际 `--diff c5a1fda` 退出 1，主代理在带 Git 的工作区复验。生产切换由主代理负责。
