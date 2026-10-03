# MCP 技术存储与恢复

> **速查**
> - 职责：MCP 写入幂等回执、网页确认与导出快照的持久化和恢复
> - 入口：`omrs/ai_review.py`、`omrs/mcp_operations.py`、`omrs/question_update.py`、`omrs/reports.py`、`omrs/draft_write.py`、`omrs/boards.py`、`omrs/mcp_exports.py`
> - 不变量：技术存储不进入学习 Ledger；回执绑定密钥、工具和请求编号；不保存密钥明文
> - 必跑测试：`python3 -m unittest discover -s tests -p 'test_mcp*.py' -q`、`python3 tests/e2e/mcp_expansion.py`
> - 相关：`AI/data.md`、`AI/mcp.md`、`AI/runtime.md`、`AI/export.md`

## 报告回执

`错题/.omrs/mcp_reports.db` 保存请求身份摘要、内容摘要、预留元数据和 applied 状态，权限为 0600。报告仍保存在 `错题/report/`；先预留稳定编号，再原子保存 HTML 并登记 `index.json`，索引登记中断可以重试恢复。同一请求不会生成第二份报告；完成后人工删除的报告不因重试复活。

## 草稿修订回执

草稿库的 `mcp_patch_requests` 保存请求/内容摘要、draft_id、编辑身份、原结果及时间。补丁和回执同事务提交；草稿的 `last_mcp_edit_json` 与原 `source_channel/source_key_id` 独立，修订不改原来源。相同请求返回原结果，人工保护导致的整次未写入也有回执。

## 展示板版本与回执

`boards.json` 的 v4 顶层包含 `catalog_revision` 和 `mcp_receipts`，每板包含 `revision`。旧文件读取只在内存规范化，首次实际写入迁移。共享领域锁保护版本检查与读改写；回执随板变更同次原子 JSON 替换，后续 Web 写入继续保留回执。纸面历史属于展示板存储，不进入 Ledger；引用与纸面字段见 `AI/data/storage.md` §4。

## 网页确认库

`错题/.omrs/ai_review.db` 是 MCP 与助手共用的 0600/WAL 审核权威，保存原始请求摘要、有效提案、影响预览、身份快照、来源、版本、期限、审核决定和结果。完整提案不进入脱敏 `runtime.db`。旧 `mcp_operations.db` 仅为兼容证据；监听前导入为只读历史，未结束的旧记录标中断，不允许重新批准。

MCP 新待审提案有效期 10 分钟；尚未批准的提案可在普通重启后继续等待至原期限。网页批准先保存 approved/applying，再执行原生领域事务。原生板回执、Session 事务回执和正式题目回执证明已有提交时，只补记终态；无回执不重放写入。GET 只读核对原生回执和到期，不迁移旧库或更新存储。整库恢复废止全部未结束的新旧审批。统一状态与助手原运行规则见 `AI/ai-review.md`。

旧 `/api/mcp/operations/decide` 兼容入口接受可选 expected_revision。未提供版本只允许第 1 版，人工修订后缺少版本或版本过时返回 revision_conflict，不能让旧页面批准未看过的提案。审核中心始终显式提交当前版本。

## 导出快照

`错题/.omrs/mcp_exports.db` 是 0600/WAL SQLite。`exports` 保存请求摘要、稳定 export_id/key_id/board_id、revision、范围、创建/过期时间、大小、SHA 和安全文件名；`contents` 保存完整 HTML 恢复副本。`错题/.omrs/mcp_exports/` 是 0700 目录，快照文件权限为 0600。

元数据与 HTML 恢复副本先同事务提交，再原子落文件。重试或下载可从恢复副本重建原字节，不按已变板重建。24 小时后在下一次导出或下载访问时清理文件和恢复副本，保留幂等墓碑，旧编号不能重新生成；读取边界与下载见 `AI/export.md`。

## 备份与恢复边界

这些文件随整个 `错题/` 目录备份，不参与学习 Ledger 重放或状态还原。确认操作和导出快照含完整业务内容，不能当作脱敏运行日志公开；备份访问沿用现有 Web 授权。工具错误、生命周期和关联的脱敏记录统一见 `AI/runtime.md`。


## 审计修复契约

MCP 技术库、报告及导出文件参与全库生命周期屏障和 SQLite 在线备份。工具调用传播开始时的 Vault 世代，网络调用不持长租约；恢复后的旧确认和迟到写入拒绝生效。快照回执的事务不会提前关闭仍在使用的连接，存储操作结束时关闭连接。备份与启动恢复见 `AI/backup.md`。


## 复习调度回执

复习计划技术回执复用 ledger.db 的 op_results 表，op_id 使用 mcp:session: 命名空间与密钥、工具、请求编号的摘要；result_json 保存规范化内容摘要和稳定 session_id，不保存密钥明文。回执与 session.create 事实、SQL Session 投影同事务提交，发布失败整体回滚并失效内存投影缓存。该表是技术回执，不是学习 commit；学习撤销或 state.restore 不删除回执，整库备份及恢复沿用 ledger.db 生命周期边界。

重试先读回执再检查 active 占用；相同内容返回原计划当前状态，撤销或状态恢复排除后返回原编号和不可用状态，不复活。新编号同时避开全部历史投影、已有技术回执和不可变创建事实中的编号，防止恢复后误指另一份计划。输入 uid 展示快照不进入稳定身份摘要，题目移动后同请求仍可复用；顺序和 due/proficiency 来源属于请求内容。
