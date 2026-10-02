# 系统运行记录

> **速查**
> - 职责：独立 MCP 工具调用的生命周期、脱敏摘要与草稿/板/报告/导出关联
> - 入口：`omrs/runtime_records.py`、`omrs/mcp/server.py`、`omrs/cli.py`
> - 不变量：只记录工具调用；运行记录不进入学习 Ledger；写入故障不改变工具结果；只保存白名单摘要
> - 必跑测试：`tests/test_runtime_records.py`、`tests/app/runtime-history.test.mjs`、`tests/e2e/runtime_history.py`
> - 相关：`AI/mcp.md`、`AI/api.md`、`AI/data.md`、`AI/security.md`、`AI/frontend/records.md`

## 存储与生命周期

路径 `错题/.omrs/runtime.db`，由 `omrs/runtime_records.py` 管理。首批来源固定 `mcp`，独立于学习 Ledger、草稿和助手库；首个工具调用才创建数据库，空库查询和详情使用只读连接且不建库。SQLite 启用 WAL、5 秒等待，模块写锁串行写入，连接在操作后关闭；创建文件权限为 0600，拒绝数据库符号链接。备份整个 `错题/` 时随目录保留，不由 Ledger 重放或 `state.restore` 还原。

`records` 表含自增 `seq`、唯一随机 `call_id`、`source/tool/title`、`key_id/key_name`、UTC `started_at/finished_at`、`status/duration_ms`、`arguments_json/result_json`、`error_code/draft_id`；按草稿和密钥建立索引。开始插入 `running`，结束仅将同一进行中行更新到 `success/failure/interrupted`，普通已结束行不改写；关联确认操作随独立确认库同步到已应用、拒绝、到期或冲突。耗时取单调时钟；未知完成耗时为 null。`serve` 监听前将遗留 `running` 改为中断并补完成时间，不推测其业务结果。

## 摘要与关联

参数摘要只保留科目、分类、题目 / Session / 草稿编号、状态、来源、范围、匹配模式、有界筛选数值、题图下标 image_index 和图片 / 块 / 标签 / 知识点等数量。结果摘要只留稳定标识、状态、计数与 `reused`；SDK JSON / 文本结果都按同一白名单提取。文字限长并隐藏 Key、Bearer、HTTP / data URL；不存正文、图片字节、附件地址、签名、客户端名称、幂等请求自由文本或原始异常。错误码对应固定安全说明。

get_question_image 的名称登记为“读取题图”，成功的 ImageContent 结果不保存内容或 Base64，参数只记录 UID 与下标。

调用的 `draft_id` 可供只读查询当前草稿状态，以及 Ledger 中已存在 `_draft.draft_id` 的人工入库提交；学习摘要的 `source_draft_id` 只是这一原字段的读取投影。旧调用不补造，没有来源记录时返回空列表。记录写入故障不改变工具结果，读取故障通过接口固定说明报告；接口与页面契约见 `AI/api.md` 和 `AI/frontend/records.md`。

## 扩展查询记录

批量读题、完整正文、草稿原图、单题历史和学习时间线登记中文标题。not_found/content_conflict 使用稳定说明；正文、HTML 和图片不会进入结果摘要。

分析与报告工具登记中文标题；报告 HTML 不保存到 runtime 摘要，幂等冲突使用 request_conflict。

草稿修订登记中文运行标题与版本、状态、操作恢复等稳定错误码；原结果正文和建议细节不保存到运行摘要。

草稿修订返回 wrote=false 时显示“草稿未修改”，避免将人工保护建议误记为完成；稳定错误由 `omrs/errors.py` 共享，运行模块的普通导入不依赖可选 MCP SDK。

## 网页确认操作

独立 错题/.omrs/mcp_operations.db 0600/WAL 保存完整参数、影响预览、预期快照和幂等身份，不混入 runtime.db。有效期10分钟。pending_confirmation 显示“尚未变更”；applied/rejected/expired/conflict 分别显示应用、拒绝、到期和冲突。applying 表示网页已确认但执行待恢复。

确认持共享领域写锁重新鉴权和预览；快照不同返回冲突。执行前持久化 applying，领域变更与回执原子提交，重启按回执恢复：已提交不重做，无回执则重新校验后恢复。重复确认、拒绝或到期均不会多次变更。读系统记录时同步到期及已确认的中断操作。

运行摘要仅添加 board_id/folder_id/report_id/export_id/operation_id、版本与有限计数，完整补丁、HTML、题目文字和链接均不保存。详情从确认库取得网页影响预览，不把工具生成预览表示成已完成。

导出工具登记中文标题，结果摘要仅保存export_id/board_id/板版本/大小等标识。网页详情关联板、报告与导出，可打开展示板、沙箱报告或下载快照；链接在页面按稳定编号构造，不从工具自由URL保存。


## 审计修复契约

运行库连接与磁盘入口先取得 Vault 生命周期租约再取模块锁；全库备份采用 SQLite 在线快照，包含仍在 WAL 的已提交调用。MCP 调用持任务世代而不持网络租约，恢复后的旧调用不能写入新运行库。恢复运行库后把遗留 running 标为 interrupted，见 `AI/backup.md`。
