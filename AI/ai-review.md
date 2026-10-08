# 统一 AI 审核

> **速查**
> - 职责：MCP 与内置助手业务写意图、分级审批、人工修订、执行结果与历史追溯
> - 入口：`omrs/ai_review.py`、`omrs/http/ai_review.py`；页面见 `AI/frontend/ai-review.md`
> - 不变量：审批只在 ai_review.db；读取不执行业务重放；原领域回执证明真实提交；恢复废止未终结审批
> - 必跑测试：`tests/test_ai_review.py`、`tests/test_question_update.py`、`tests/test_mcp_question_update.py`、`tests/e2e/ai_review.py`
> - 相关：`AI/agent.md`、`AI/mcp.md`、`AI/mcp-storage.md`、`AI/drafts.md`、`AI/backup.md`

## 1. 范围与分级

只登记 MCP 与内置助手的业务写调用。读取、图片读取与转述缓存、技术运行日志和导出下载快照不列入审核中心。录入页独立 OCR、识别与框选沿用原流程。分类由服务端固定工具清单决定；没有业务写分类的新工具不能写入。

| 操作 | 规则 |
| --- | --- |
| 草稿创建、修订；助手聊天练习卡 | 自动执行并登记实际结果 |
| MCP 新建报告、普通展示板管理 | 自动执行并登记实际结果 |
| 创建正式复习计划 | 执行前人工批准 |
| 助手正文/知识点/标记/移动/停用/恢复/反馈/分类/草稿入库 | 执行前人工批准 |
| MCP 正式题目修改 | 执行前人工批准，可修订原提案字段 |
| MCP 删除展示板/文件夹、清空非空板、重置纸面历史 | 执行前人工批准 |

待审核列表同时展示长期待审草稿与限时确认操作；正在请求入库的草稿以对应操作代替同一草稿行，待办按稳定草稿身份去重。记录页展示调用结果和原生草稿的当前状态；它们是不同对象，调用成功不代表草稿已经正式入库。

## 2. 唯一审批存储

`错题/.omrs/ai_review.db` 为 0600/WAL SQLite。`operations` 存操作身份、来源/工具、原请求摘要、有效提案摘要、当前 payload、来源 actor、preview、目标 snapshot、可修订字段、状态、版本、创建/更新/到期时间、开始世代、实际 result、error_code、commits，以及历史只读/不完整标记。`revisions` 保留修订前 payload 和摘要；`decisions` 在 pending→approved/rejected 同事务保存版本、决定、时间和服务端操作者信息。MCP Key、PIN 和 Cookie 不保存。

业务事实仍在原存储：正式题目/Ledger、草稿、展示板、报告与 Session。审核库不参与学习投影重放。旧 mcp_operations.db 仅供启动迁入历史，旧 HTTP 确认接口代理到统一服务，不能形成第二条执行路径。

新自动写先登记 running 意图，登记失败拒绝新业务写。MCP 草稿与报告在原生事务的 `ai_review_receipts` 同时记录 operation_id、有效提案摘要与结果；统一记录落盘失败时，启动阶段可据此补记已提交事实，不再次调用工具。附件意图只保存是否提供和摘要，完整图像仍在草稿原图存储；签名 URL 和 Base64 不复制到审核库。

## 3. 状态、修订与执行

状态包括 running、pending_confirmation、approved、applying、applied、rejected、expired、conflict、interrupted、failed、partial、unchanged、cancelled。批准、执行中与已执行有不同含义；失败和部分成功保留原生逐项结果与提交编号。没有回执不能推断成功，也不能由查询重新执行批准操作。

MCP 在业务提交后丢失审核结果时，详情可以通过精确操作身份及摘要匹配的原生回执展示既成事实；记录列表对未终结的 running/approved/applying 意图采用同一只读视图，状态筛选、总数和详情保持一致。无变更回执显示 unchanged，摘要不匹配显示 conflict。查询只在当前连接建立临时状态索引，不修改审批状态或领域库，也不恢复写入许可；持久终态由启动收束补齐。

人工修订必须携带 expected_revision，且 patch 键属于原 editable_fields。修订保留原请求摘要，递增版本、更新有效摘要和预览；不能改目标身份、来源、基线、权限或请求编号。批准与修订通过统一写锁及 CAS 竞争，只能批准看过的版本。批准后的提案不可修订。重试原 MCP 请求不会覆盖人工版本。

助手确认由原运行线程等待十分钟，不持写锁或数据库连接。聊天与中心调用同一决定函数；决定先持久保存，再唤醒原线程。修订旋转聊天确认票据，不延长原期限；执行使用批准的最终内容，并把实际应用内容和修订信息返回模型。停止、拒绝、过期竞争同一终态；普通重启失效旧助手等待，不重启模型或执行业务。

正式题目底层只接受持久 applying 状态及匹配的提案版本、两摘要和快照；替换文件前再次验证来源权限、期限和运行停止状态。执行前再次核验运行停止状态、实时权限、期限、目标稳定身份、正文磁盘哈希及相关配置；题目移动或变化不能沿用旧提案。锁顺序为生命周期租约 → 全局写锁 → 确认对象锁 → 存储事务。题目文件与 Ledger 的跨存储协议见 `AI/ledger.md`。

## 4. 查询与 Web 写接口

所有接口沿用 Web 登录、同源检查与服务器推导的身份；普通 Web 端口拒绝 MCP Bearer 与 X-OMRS-MCP-Key。详情有完整私人提案，运行历史继续脱敏。

| 接口 | 契约 |
| --- | --- |
| GET `/api/ai-review/items` | view=pending/records，source、type、status、from/to 时间，limit 1–100、offset 非负（兼容 cursor 偏移字符串）；返回 items/total/has_more/next_offset/next_cursor |
| GET `/api/ai-review/detail` | id 或 operation_id；返回 item；草稿沿用原生 draft 详情，操作包含 original_payload、当前提案与决定 |
| GET `/api/ai-review/counts` | 返回 counts.pending/drafts/operations；按草稿去重 |
| POST `/api/ai-review/update` | id 或 operation_id、expected_revision、非空 patch；返回修订后的 item |
| POST `/api/ai-review/decide` | id 或 operation_id、expected_revision、decision=approve/reject；返回真实状态的 item |

type 是 draft/question/session/feedback/board/report/category/practice。错误返回 status=error、msg、code；旧版本为 revision_conflict/409，旧状态为 state_conflict/409，缺目标为 not_found/404。过期视图在读取时计算，不因 GET 更新领域。

## 5. 启动、恢复与历史

监听前先收束整库恢复 journal 和题目跨存储意图，再初始化审核库、导入历史并核对领域回执；助手残留线程等待随后失效。GET 列表、详情和运行历史不导入审批、不重放业务。

已存在的草稿库在启动阶段由原生模块迁移。首次并发创建草稿库时，文件已出现而表尚未提交，审核查询视为空草稿队列；新表一次声明完整的当前字段，避免建表与旧库补列之间的缺列窗口。GET 保持只读，不抢先初始化或迁移来源库；损坏或残缺的已有审批架构仍报告错误。

整库恢复显式废止导入库中新旧全部未终结审批；恢复权限不能只比较数字世代。旧历史未终结记录迁入为只读中断，不恢复批准入口。匹配领域回执只证明已发生事实，不赋予未来写权限。

历史导入按稳定源身份去重：助手运行/调用身份，MCP call_id，以及旧审批 operation_id。SQLite 游标有界读取 tool_calls/run_events，结合 Ledger 的 _agent 身份与原生草稿/练习卡证据；旧 done 确认记录不能当实际成功。证据不足标 history_incomplete，历史操作禁止再批准，不制造审核人。重复启动不增加同源记录。

## 标记整理审批

新增 `propose_label_plan` 的标记整理类型，复用十分钟期限、唯一审批、版本与人工决定。人工修订只允许原定义名称/颜色/排序、原操作或题目开关和原集合内归属；排除级联题目会关闭对应定义操作，取消新标记会取消依赖归类。每次修订换票据，不延长期限。
