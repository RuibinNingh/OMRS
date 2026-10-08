# HTTP API

> **速查**
> - 职责：HTTP 安全、并发、传输及领域接口索引
> - 入口：`omrs/server.py`、`omrs/http/registry.py`、`omrs/http/`
> - 不变量：单一注册表分派；POST 先鉴权和读取解析，磁盘段结束后才发送响应
> - 必跑测试：`tests/test_http_boundaries.py`、`tests/test_security.py`、`tests/test_write_lock.py`、`tests/test_asset_cache.py`、`tests/test_web_assets.py`
> - 相关：`AI/routes.md`、`AI/security.md`、`AI/agent.md`、`AI/data.md`

默认启动 `python omrs_engine.py --vault <path> serve -p 8471`。普通 Web 使用标准库 HTTP；`OMRSHandler.services` 为领域适配提供服务引用，已有 handler 方法名与服务替换测试接口保持可用。

## 1. 接口分册

| 范围 | 文档 |
|---|---|
| GET、HEAD 与查询 | `AI/api/queries.md` |
| 题目、反馈、配置、认证与备份写入 | `AI/api/mutations.md` |
| 调度、导出与展示板 | `AI/api/boards.md` |
| 收件箱、草稿、标注、训练与 MCP | `AI/api/extensions.md` |
| 全库备份、恢复协议与回退 | `AI/backup.md` |
| 内置助手、持久事件与分页 | `AI/agent.md` |

外部 MCP 的调用说明随工具发现返回，集中来源为 `omrs/mcp/tool_docs.py`；包括用途、参数来源、分页单位、版本与技术重试、录题示例和网页审核状态。元数据不改变领域校验和 HTTP 路由。录题的原图、块与错因规范见 `AI/mcp.md`，草稿修订协议见 `AI/api/extensions.md`。

收件箱与草稿区域提取的数学定界符转义兼容、正文格式及失败边界见 `AI/api/extensions.md`「收件箱端点」与 `AI/inbox.md` §4。

`omrs/http/registry.py` 是方法、路径及领域分派的唯一清单，`tests/check_docs.py --write-routes` 从它生成 `AI/routes.md`。新增路由必须登记注册表及对应分册。HEAD 使用相同 GET 鉴权、路径和资源处理，返回相同状态及响应头但没有正文。

HTML、普通 JSON 与 CSS / JavaScript / SVG 等文本在客户端接受 gzip、正文至少 1KiB 且压缩有收益时返回 `Content-Encoding: gzip`，`Content-Length` 为压缩字节数，协商响应带 `Vary: Accept-Encoding`。登录和 MCP 密钥等 `/api/auth/`、`/api/mcp/` JSON 回执不压缩，图片、字体、视频及下载附件保持原字节。压缩不新增第三方运行依赖；静态缓存和首屏加载见 `AI/frontend/architecture.md` §7 与 `AI/api/queries.md` 的 `/assets/` 条目。

## 2. 并发与写锁

每个连接一个守护线程。POST 通过task捕获开始世代，先检查凭据与来源、授权，再完整限时接收至临时文件并解析 JSON；网络读取和解析不持业务写锁。普通持久化磁盘段先取得生命周期共享租约，再取得可重入写锁，然后模块锁和 SQLite 事务。写锁等待60秒后返回503。生成的响应先放临时文件；磁盘段及写锁结束后分块发送，慢下载不能阻塞其它写入。

`/api/backup/export`、`/api/backup/import`、`/api/backup/restore` 不取得外层共享租约或写锁；备份内部独占捕获，恢复内部独占交换，压缩和下载在屏障外。禁止共享租约升级为独占。模型网络、助手长轮询和训练服务网络不持租约；领域磁盘入口自行取得短租约。后台任务通过 `task(vault,generation)` 传播代际，恢复后旧结果不能写入新库。

正文接收完成后先核验请求开始世代，恢复期间收到的旧正文返回409且不分派。恢复本身仅在独占维护内部更新任务世代；普通请求不能绕过检查。`/api/export-review` 在短租约内捕获复盘数据及安全附件，释放后生成临时ZIP并分块下载，完成后删除临时件。

auth、uploads、模型识别与重启等路由按领域取得必要的短锁；其它豁免及理由在 `omrs/locking.py`。安全模块 PIN 同 Vault/IP 串行校验，排队最多2秒；认证文件用唯一临时文件原子写回。所有数据库连接在磁盘段取得租约并显式关闭。

聊天 confirm 豁免外层长锁，但在内部按生命周期租约 → 业务写锁 → PendingConfirm 锁 → 审核 SQLite 事务写入决定。落盘成功才唤醒原等待；审核中心决定共用同一权威。修订也按此顺序替换版本与票据，不延长原期限。模型思考、10 分钟等待、长轮询均不持这些锁；真正业务执行在原运行另取短写锁，核对快照、期限和中止状态。普通 GET 只读历史或原生回执，业务恢复只在监听前显式执行，且不重放工具。

CLI `content-recover` 在锁外读取本机清单与候选正文，核验和补入使用同一生命周期租约 → 写锁 → SQLite事务顺序，与HTTP写入及全库恢复协调。它默认只预览，`--apply` 才补缺失blob，不新增HTTP路由；具体清单与原子性见 `AI/ledger.md` §10。

## 3. 请求边界与错误

普通 JSON及上传引用元数据默认2MiB，可通过活动配置 `http_json_mib` 调整为1–8192的整数。旧图片 JSON/multipart 默认128MiB，可通过 `http_legacy_upload_mib` 调整为2–8192的整数；auth/MCP/训练/入口背景和分块接口保持各自的明确上限。两项可通过配置API保存后立即生效，或手改镜像后在启动时导入；布尔、字符串、小数及越界值拒绝。超限返回413；大批操作先按以下协议上传图片，再在业务接口传引用。每张图片、总图数和逻辑批量由业务契约决定，16MiB仅是传输分块大小。

备份导入的JSON引用元数据同样使用 `http_json_mib`，声明超限即413，不暂存正文或执行预检；原始ZIP和备份multipart仍为8GiB传输上限。此限额与展开的32GiB／20万条目边界分开验证。

MIME主类型按大小写无关识别，multipart boundary保持原文。普通接口不能通过声明multipart改用旧图片限额；旧图片限额只用于已有图片业务路径。

普通读取总期限30秒，大上传10分钟；无进展15秒即408。Content-Length 必须为唯一的非负 ASCII 整数，不支持 Transfer-Encoding；短读、非法 UTF-8、非法 JSON 或非对象返回400。非法业务输入400、身份或版本冲突409、存储繁忙503、真实服务故障500，响应为 `{status:"error",msg,code?}`。旧 create/inbox data URL 逐图流式转入暂存文件，旧 multipart 从磁盘逐文件分离。

题目稳定引用为 `{question_id}`；UID 只作显示和兼容。混传 `question_id`/`uid` 必须一致，否则409；未知 ID 不回退 UID。GET `/api/question`、`/api/question/raw` 与单题写入支持稳定引用。CSV 不参与日常读取，显式导出/备份才生成，启动与扫描不生成。

## 4. 分块上传

1. `POST /api/uploads/start`：JSON `{filename,mime,total_bytes,purpose}`。purpose 为 image/create/inbox/annotate/draft/assistant/backup；返回 `{upload_id,chunk_bytes:16777216,expires_at}`。
2. `POST /api/uploads/chunk?upload_id=...&index=N`：原始二进制，顺序从0开始，每块1字节至16MiB。同块同内容重试返回 `reused:true`；冲突内容拒绝。
3. `POST /api/uploads/complete`：JSON `{upload_id,sha256?}`；核对完整长度及可选 SHA-256，返回 `{upload_ref,bytes,mime,sha256,filename,expires_at}`。

暂存放在系统临时目录、权限为目录0700/文件0600，有效期1小时；引用绑定 Web 会话（直连免 PIN 时按客户端 IP）、Vault 世代和用途。恢复后旧引用失效。图片完成时识别 PNG/JPEG/GIF，备份用途仅供 ZIP 导入，不得用于图片。文件是普通非链接原件，完成核对分块累计长度、读取校验哈希；启动和每块空间准入均保留64MiB。引用不会写入学习 Ledger，原业务入库才产生事实。

## 标记整理批次

人工标记 API 保持请求与响应契约，底层改用整批可靠写入；标签与题面聚合读共用一致性锁，待恢复时读取拒绝而不执行恢复。

## 标记整理审批

`GET /api/label-plan/revert-preview?operation_id=...` 只读返回 `ok`、`inverse_digest`、`label_changes`（定义前后值）、逐题变化和冲突。`POST /api/label-plan/revert` 接收 `operation_id`、`inverse_digest`、`request_id`；只有摘要与当前预览一致才执行整批逆操作，重复请求复用回执。普通 Web 登录与同源规则适用，MCP 密钥不能调用。

## 标记整理工具

助手注册分片准备与整批提案能力；准备自动执行，最终整批提案的批准、修订沿用 `/api/ai-review/update` 与 `/api/ai-review/decide`，助手原对话等待对象收到新版本票据与有效方案。

## 整批标记归类

标记整理预览含定义操作的跨范围科目题数、目标名称及逐题实际 `after` 与未纳入的 `proposed_after`，供用户核对默认关闭的级联建议。查询与批次替换共用独立一致性锁，普通业务写锁仍不阻塞统计 GET。
