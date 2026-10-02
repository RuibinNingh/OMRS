# MCP 技术存储与恢复

> **速查**
> - 职责：MCP 写入幂等回执、网页确认与导出快照的持久化和恢复
> - 入口：`omrs/reports.py`、`omrs/draft_write.py`、`omrs/boards.py`、`omrs/mcp_operations.py`、`omrs/mcp_exports.py`
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

`错题/.omrs/mcp_operations.db` 是独立的 0600/WAL SQLite。`operations` 保存 operation_id、唯一幂等 identity、key_id/tool、digest、payload_json/impact_json/snapshot、status、创建/过期秒数、result_json/error_code。完整待确认参数只在此库，`runtime.db` 只保存脱敏摘要。

待确认有效期 10 分钟，重启后继续待确认。网页批准先保存 applying，再执行领域事务；进程中断时优先用板的原子幂等回执恢复终态，没有回执则复核当前权限和目标后恢复已批准操作。拒绝、到期和冲突不写板；详细状态见 `AI/runtime.md`。

## 导出快照

`错题/.omrs/mcp_exports.db` 是 0600/WAL SQLite。`exports` 保存请求摘要、稳定 export_id/key_id/board_id、revision、范围、创建/过期时间、大小、SHA 和安全文件名；`contents` 保存完整 HTML 恢复副本。`错题/.omrs/mcp_exports/` 是 0700 目录，快照文件权限为 0600。

元数据与 HTML 恢复副本先同事务提交，再原子落文件。重试或下载可从恢复副本重建原字节，不按已变板重建。24 小时后在下一次导出或下载访问时清理文件和恢复副本，保留幂等墓碑，旧编号不能重新生成；读取边界与下载见 `AI/export.md`。

## 备份与恢复边界

这些文件随整个 `错题/` 目录备份，不参与学习 Ledger 重放或状态还原。确认操作和导出快照含完整业务内容，不能当作脱敏运行日志公开；备份访问沿用现有 Web 授权。工具错误、生命周期和关联的脱敏记录统一见 `AI/runtime.md`。


## 审计修复契约

MCP 技术库、报告及导出文件参与全库生命周期屏障和 SQLite 在线备份。工具调用传播开始时的 Vault 世代，网络调用不持长租约；恢复后的旧确认和迟到写入拒绝生效。快照回执的事务不会提前关闭仍在使用的连接，存储操作结束时关闭连接。备份与启动恢复见 `AI/backup.md`。
