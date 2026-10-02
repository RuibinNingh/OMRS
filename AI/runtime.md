# 系统运行记录

> **速查**
> - 职责：独立 MCP 工具调用的生命周期、脱敏摘要与草稿入库关联
> - 入口：`omrs/runtime_records.py`、`omrs/mcp/server.py`、`omrs/cli.py`
> - 不变量：只记录工具调用；运行记录不进入学习 Ledger；写入故障不改变工具结果；只保存白名单摘要
> - 必跑测试：`tests/test_runtime_records.py`、`tests/app/runtime-history.test.mjs`、`tests/e2e/runtime_history.py`
> - 相关：`AI/mcp.md`、`AI/api.md`、`AI/data.md`、`AI/security.md`、`AI/frontend/records.md`

## 存储与生命周期

路径 `错题/.omrs/runtime.db`，由 `omrs/runtime_records.py` 管理。首批来源固定 `mcp`，独立于学习 Ledger、草稿和助手库；首个工具调用才创建数据库，空库查询和详情使用只读连接且不建库。SQLite 启用 WAL、5 秒等待，模块写锁串行写入，连接在操作后关闭；创建文件权限为 0600，拒绝数据库符号链接。备份整个 `错题/` 时随目录保留，不由 Ledger 重放或 `state.restore` 还原。

`records` 表含自增 `seq`、唯一随机 `call_id`、`source/tool/title`、`key_id/key_name`、UTC `started_at/finished_at`、`status/duration_ms`、`arguments_json/result_json`、`error_code/draft_id`；按草稿和密钥建立索引。开始插入 `running`，结束仅将同一进行中行更新到 `success/failure/interrupted`，已结束行不改写。耗时取单调时钟；未知完成耗时为 null。`serve` 监听前将遗留 `running` 改为中断并补完成时间，不推测其业务结果。

## 摘要与关联

参数摘要只保留科目、分类、题目 / Session / 草稿编号、状态、来源、范围、匹配模式、有界筛选数值、题图下标 image_index 和图片 / 块 / 标签 / 知识点等数量。结果摘要只留稳定标识、状态、计数与 `reused`；SDK JSON / 文本结果都按同一白名单提取。文字限长并隐藏 Key、Bearer、HTTP / data URL；不存正文、图片字节、附件地址、签名、客户端名称、幂等请求自由文本或原始异常。错误码对应固定安全说明。

get_question_image 的名称登记为“读取题图”，成功的 ImageContent 结果不保存内容或 Base64，参数只记录 UID 与下标。

调用的 `draft_id` 可供只读查询当前草稿状态，以及 Ledger 中已存在 `_draft.draft_id` 的人工入库提交；学习摘要的 `source_draft_id` 只是这一原字段的读取投影。旧调用不补造，没有来源记录时返回空列表。记录写入故障不改变工具结果，读取故障通过接口固定说明报告；接口与页面契约见 `AI/api.md` 和 `AI/frontend/records.md`。

## 扩展查询记录

批量读题、完整正文、草稿原图、单题历史和学习时间线登记中文标题。not_found/content_conflict 使用稳定说明；正文、HTML 和图片不会进入结果摘要。

分析与报告工具登记中文标题；报告 HTML 不保存到 runtime 摘要，幂等冲突使用 request_conflict。

草稿修订登记中文运行标题与版本、状态、操作恢复等稳定错误码；原结果正文和建议细节不保存到运行摘要。
