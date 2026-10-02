# OMRS MCP 接入

> **速查**
> - 职责：向获授权外部 AI 提供 OMRS 只读查询和待审核草稿创建
> - 入口：`omrs/mcp/server.py`、`http.py`、`keys.py`；`serve --mcp-port`
> - 不变量：二十读三写；Key 与 Web 权限分离；共享主进程写锁；完整原图进入既有审核队列
> - 必跑测试：`python3 -m unittest tests.test_mcp tests.test_mcp_keys tests.test_mcp_http tests.test_mcp_protocol tests.test_mcp_draft_atomic tests.test_runtime_records -q`、`python3 tests/e2e/mcp.py`、`python3 tests/e2e/runtime_history.py`
> - 相关：`AI/api.md`、`AI/drafts.md`、`AI/security.md`、`AI/agent.md`、`requirements-mcp.txt`

## 1. 安装与启动

MCP 使用官方 Python SDK 的 Streamable HTTP。安装可选依赖后与主 Web 服务同进程启动；普通 Web 启动无需这些依赖：

```bash
python3 -m pip install -r requirements-mcp.txt
python3 omrs_engine.py --vault /path/to/vault serve --port 8471 --mcp-port 18472
```

MCP 只监听 `127.0.0.1`，示例地址是 `http://127.0.0.1:18472/mcp`。外部客户端使用 HTTPS 反向代理，仅转发 `/mcp`，并在启动时指定 `--mcp-public-url https://your-host/mcp`，登记精确 Host/Origin 白名单。SDK 负责协议协商、JSON-RPC、认证 challenge 和传输安全；启动失败时主命令明确退出。没有独立读写 Vault 的 MCP 进程入口。生产 HTTPS 8472 已由 Web/Nginx 共用，不能把内部 MCP 绑定到该端口；实际发布根与参数见 `AI/environment.md`。

在 OMRS 设置 → 访问与安全 → 外部 AI / MCP 点击“创建密钥”，在窗口选择查询权限（`omrs:read`）、创建待审核草稿（`draft:create`）或两者，并可指定到期时间。成功后同一窗口显示一次明文，关闭后无法再次查看；列表展示可用密钥，失效记录默认折叠，时间按设备本地时区显示。页面行为见 `AI/frontend/settings.md`。也可以本机使用 `mcp-key create --name 名称`、`mcp-key list`、`mcp-key revoke --id key_id` 管理。MCP 请求使用 `Authorization: Bearer <key>` 或 `X-OMRS-MCP-Key: <key>`；密钥不得放进 URL、模型参数或日志。

## 2. 工具与权限

固定开放二十个查询工具：`list_taxonomy`、`search_questions`、`get_question`、`get_question_image`、`get_overview`、`get_recommendations`、`list_sessions`、`get_session`、`list_drafts`、`get_draft`。七个学习数据查询直接复用 `omrs/agent/tools/read.py` 的实现和 schema，继承筛选、排序、分页、正文截断、练习记录和推荐口径。草稿查询使用同一草稿库的只读业务视图，不触发作业恢复、来源关系回填或训练；存储初始化仍执行既有技术 schema 迁移。

`create_draft` 需要 `draft:create`，`create_report` 需要 `report:create`。它不启动内部模型或 Agent 循环。未知工具、额外参数、非法类型和 scope 不足均由服务端拒绝。不存在正式建题、提交/丢弃草稿、反馈、标记、Session、设置、任意文件读取或任意 HTTP 转发工具；普通 Web 端口在登录及业务路由之前拒绝 MCP 凭据。

每次协议请求和领域调用重新验证 Key；创建在下载及等锁之后、实际写入前复查，URL 快速复用、inline 处理后复用及新建都在结果封装前再次校验 `draft:create`。处理中吊销、到期或权限变化返回 `forbidden`，提交后失效仍保留草稿与原图。`tools/list` 按当前 Key 的实时 scope 按当前 scope 返回查询、草稿创建及报告创建；发现与调用共用显式工具→scope 映射。过滤只作用于当前请求的描述，完整注册表保持，SDK 共享定义缓存不承担授权；直接点名隐藏工具仍拒绝。`错题/.omrs/mcp_keys.json` 仅保存 SHA-256 摘要和非秘密元数据，0600；线程锁和操作系统文件锁共同避免本机 CLI 与 Web 的创建/吊销/最近使用时间互相覆盖。Key 管理响应禁止缓存。

审查修复验收状态统一见 `AI/optimization.md`「MCP 修复」，实施按 `AI/plans/mcp-integration/exec-2026-10-01-mcp-fixes.md`。

`get_overview(subject=...)` 的全部概况字段来自共享统计入口中的同一科目范围，未知科目返回零计数与空明细；统计口径见 `AI/api.md` 与 `AI/agent.md`。

### 按需读取题图

get_question_image(uid, image_index) 必须提供非空 UID（去首尾空白、最多 200 字符）和从 0 开始的严格整数下标；布尔值、小数、字符串和额外参数拒绝。先调用共享 get_question 并按其 images[] 当前顺序选图，包含题目与答案图片，不从已截断正文重新提取。每次重新定位，不缓存图片或授权。

get_question 与 get_draft 保持正文、图片引用及元数据输出，不自动附加图片内容。正式题图需单独调用 get_question_image，不能用草稿编号代替 UID；草稿原图由 get_draft_image 单独提供。外部客户端须刷新工具清单并启用新工具；ChatGPT 的应用详情支持刷新工具、描述与服务端 instructions，必要时在提示中明确指定工具名和参数顺序。

工具需要 omrs:read，在线程内完成受限附件读取与完整解码；读取前和返回前复查实时权限。成功仅返回一个原生 ImageContent，MIME 根据实际原件确认为 image/png、image/jpeg 或 image/gif；SDK 只做 Base64 封装，不返回图片 JSON、服务器路径或下载链接。读取允许的文件树、大小和像素保护见下方领域说明。

注解为 readOnlyHint=true、destructiveHint=false、idempotentHint=true、openWorldHint=false，显式使用非结构化图片输出。schema/严格参数模型拒绝非法输入时返回 invalid_arguments；题目不存在、无图、越界、缺失、歧义、格式无效和容量超限返回 invalid_request 及可区分中文说明，OS 异常不回显本地路径。该工具只在 MCP 注册，不加入内置助手注册表。

## 3. 创建契约

必填 `subject`、`category`、`request_id` 和 `blocks`。块沿用 OMRS 的 `section=题目|答案`、`kind=text|image`；文字块提供 `text`，图片块的 `image` 是 `images` 从 0 开始的下标，可带 `note`。相邻答案文字通过 `omrs/draft_prepare.py` 与内置助手共用的规则合并，图片断开文字段。科目、分类、知识点与文字边缘空白规范化后计算幂等摘要。

文件元数据声明 `_meta["openai/fileParams"]=["images"]`。每个文件对象必须有 `download_url` 和 `file_id`，可选 `mime_type`、`file_name`；实际格式取决于收到的图片内容。可发送 HTTPS 下载地址，支持自定义文件传输的外部客户端也可在同一对象提供 `data_base64` 原字节；不接受本地路径。最多 6 张、单张 8 MiB，PNG/JPEG/GIF 每张解码总像素不超过 4000 万、最多 100 帧；校验只解码，不重编码。

最多 40 个输入块、8 个知识点；每块文字或说明最多 20000 字符，总文字最多 500000 字符。不能指定草稿状态、难度、正式 UID、来源、SHA、本地路径、坐标或训练设置。错因必须同时带 `cause_statement`，保存为 `client_asserted` 并在页面标明待核对；不冒充已验证的本地用户消息。

### 原字节校验与题图领域读取

完整解码校验集中在 omrs/question_images.py 的 validate_original_image，上传与题图读取共用 PNG/JPEG/GIF、8 MiB、4000 万累计像素及 100 帧边界。Pillow 延迟导入，校验返回原字节；截断或损坏的像素流统一拒绝。

read_question_image 按共享 get_question.images 的当前下标读取题目/答案附件，定位仅限错题/附件及普通子目录；拒绝符号链接、重解析点、非普通文件、同名歧义及读取期间文件变化，不解码 URL 或回退到其它路径。目录文件描述符与文件身份核对保护读取边界，最多读取上限加一个字节。

## 4. 原子保存与人工审核

草稿连接在全局写锁与草稿锁内串行建表、迁移；初始化失败关闭连接。下载与图片校验在全局写锁之外，最后幂等复查和原子创建使用同一领域写锁，不持独立 MCP 模块锁。

来源由服务端固定写入 `source_channel=mcp`、`source_key_id`、`source_request_id`。创建复用 `drafts.create_draft` SQL，在同一写锁与数据库事务内关联原图、草稿和幂等记录。原图按实际字节 SHA 原子落盘；失败回滚并清理本次新文件，保留共享原件，提交后的响应失败不会删除已提交原图。崩溃留下的半文件按实际收到的原字节校验和恢复，拒绝符号链接。

草稿固定 `review`、难度 5。正文图片块是固定全幅 `0,0,1,1`、`box_origin=original`，页面显示“完整原图”；这种全幅引用不代表框选或训练标注。原图不裁剪、压缩、标注或重编码，普通草稿图片接口也返回完整字节。创建和普通人工正文编辑不会自动打开训练或创建训练任务；用户明确操作训练功能时才进入既有训练流程。

`(source_key_id, request_id)` 唯一。相同内容重试返回原草稿及 `reused=true`，不同内容拒绝。稳定 `file_id` 的下载附件允许更新短期签名 URL 后重试，无需重新下载已保存原件；带 inline 原字节的重试仍验证内容 SHA。人工已修改或丢弃的草稿只返回当前状态，不复建或覆写。

用户在已有草稿区查看“来源：MCP”和完整来源图片，再编辑、审核、通过或丢弃。正式入库仍由当前人工流程决定；MCP Key 可按 draft:update 修订，不能提交或丢弃。未收到图片的文字草稿同样进入审核队列。

## 5. HTTP 与下载边界

有效 Key 每分钟最多 120 个请求、最多 4 个并发请求。请求体上限 72 MiB，声明长度及分块流都计数，总读取期限 30 秒；错误为 400/408/413/429。查询字符串、工具参数和异常响应不包含认证凭据，生产适配器关闭访问日志。

图片只从 HTTPS 443 下载，不带用户信息或 fragment；禁止重定向。DNS 全部地址必须是公共地址，随后固定已校验 IP 并保留 TLS 主机证书验证，阻止 DNS 重绑定、私网、回环和元数据访问。连接读取超时 10 秒，流式下载总期限 30 秒，URL 不超过 8192 字符，响应超过 8 MiB 立即失败。下载从不转发 MCP Key。

## 6. 客户端兼容性与验收

已使用官方 `mcp==1.28.1` ClientSession，对真实临时 Vault 的同进程服务完成 initialize、tools/list、tools/call、连续 Bearer 鉴权、查询、原图草稿、并发重试、吊销和越权拒绝，并用真实浏览器验证草稿区和 Key 管理。可运行速查头中的测试重现，无 SDK 时协议测试明确 SKIP。

ChatGPT Developer Mode 官方文档列出的认证方式为 OAuth、No Authentication、Mixed Authentication。文档中的 static credentials 是 OAuth 客户端凭据，不证明直接 URL 连接支持任意 API Key 请求头。可使用 Secure MCP Tunnel 私有连接，由客户侧 Tunnel 客户端从受限文件注入 Authorization，仍由本 MCP 验证 scope；无需把公网入口改成无鉴权。直接 URL 模式若不能发送 Key，则需另行提供保持相同 scope 的 OAuth 兼容入口。当前 ChatGPT 账户尚未联调，不能把外部 SDK 或 Tunnel 健康检查当成账户已接通。

## 7. 工具调用记录

`RestrictedMCP.call_tool` 在工具执行边界通过工作线程写入 `omrs/runtime_records.py`：开始时记 `running`，正常结束记 `success`，稳定工具错误记 `failure`，取消记 `interrupted`。耗时采用单调时钟，错误仅保留固定错误码与安全说明。记录含当次密钥编号和公开名称快照，不额外改变既有权限复查次数。只记录到达工具执行边界的调用；握手、工具发现、健康检查及 HTTP 层未认证 / 限流请求不生成调用记录。

题图调用登记为“读取题图”，参数摘要只保存脱敏 UID 和 image_index；原生图片结果不写入运行库。成功创建、幂等复用和读取草稿的结果可保存 `draft_id`；详情读取当前草稿状态及 Ledger 中 `_draft.draft_id` 对应的人工入库节点。没有旧记录时不推测或补造来源。独立运行库不进入学习 Ledger，也不参与学习修正或状态还原；格式与启动恢复见 `AI/runtime.md`，页面见 `AI/frontend/records.md`。

记录存储故障不会改变已授权工具的结果或撤回已有合法提交，只输出固定无敏感内容的诊断。记录结束写入失败可能留下 `running`，下次 `serve` 启动会恢复为中断；中断不证明草稿未写入，重试前仍需核对草稿或使用原幂等请求。读取接口独立报告故障，学习详情的来源关联读取失败则保留学习信息并给出说明。

生产当前运行 `/root/workspace/apps/releases/omrs-ba6501b`，同进程 MCP 仅监听回环端口并经 HTTPS 反代，包含运行记录和按需题图读取。公网官方 SDK 发现 10 个只读工具，按共享读题 images[] 下标返回原生 PNG，Base64 解码与磁盘原件一致；题图调用只保留 UID、下标和终态。普通 Web API 对 MCP Key 返回 403，吊销后的 Key 返回 401。生产未创建验收题目或草稿，临时只读验收密钥已吊销；公网 PIN 入口可见且无页面脚本错误。主应用浏览器因缺少 PIN 会话未进入，完整页面闭环仍以发布目录的隔离实例结果为准。部署与数据核验见 `AI/plans/mcp-integration/progress.md`。

官方参考：[Developer Mode](https://developers.openai.com/api/docs/guides/developer-mode)、[Apps SDK 文件参数](https://developers.openai.com/apps-sdk/reference/)、[认证](https://developers.openai.com/apps-sdk/build/auth/)、[Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)。

## 8. 扩展查询

get_questions(uids, detail=false) 按输入顺序返回最多 20 题，保留重复编号并逐项报告 not_found；默认摘要，可选原有 get_question 详情。get_question_content 读取题目、答案、错因、备注或全文，默认 4000/最多 8000 字，返回全文件 content_hash/next_offset；当前正文后续页必带 expected_hash，换版返回 content_conflict。version 只接受该题已登记且可验证的正文哈希，不恢复或回填内容。

get_question_history 提供 reviews 和 content_versions，默认 50/最多 100，按最新优先分页。练习记录复用有效反馈投影并优先稳定 Question_ID；正文版本只查询。get_learning_history 从 Ledger 计算当前修正状态，按 subject/uid/since/until/before_seq 先筛选后分页，批量练习节点只带匹配题目的摘要。日期含首尾，ISO 时间戳的结束边界不含；未指定时不筛选。

get_draft_image 按 get_draft.source_images 的从 0 开始下标读取原件，验证来源 SHA、普通目录和文件身份，共用完整解码及 8 MiB 限制，前后复查 omrs:read；返回原生图片，不包含其它对话图片、不裁剪或转码。

## 9. 分析与报告

get_analytics 提供 overview/trends/accuracy/distributions/weak_spots/forecast；先筛选科目和分类，再按有效反馈聚合，同名分类按科目和分类分桶。since/until 只影响练习行为和正确率；熟练度、薄弱项和预测标为当前快照，失败计数和连续错误仍用当前完整有效反馈。空库和未知范围返回零计数/空明细。

list_reports 默认 50/最多 100 项；get_report 返回 HTML 源码字符串、元数据、哈希和下一页位置，默认 4000/最多 8000 字，不执行报告脚本。create_report 仅新建，名称最多 200 字、HTML 非空且最多 2 MiB，必填 request_id；report:create 默认不授予，旧 Key 和默认创建仍只具有原两项权限。

报告回执在 mcp_reports.db：先提交稳定报告编号与请求摘要，再原子落 HTML、登记 index.json、完成回执。相同内容重试复用编号，内容不同返回 request_conflict，文件已保存而索引中断可恢复。已完成后人工删除报告，技术重试仍返回原编号，不复活报告。保存及回执返回前复查权限。

## 10. 受保护草稿修订

update_draft 需同时 omrs:read/draft:update；expected_revision 和 request_id 必填，允许各来源 cropping/review 草稿，仅科目/分类/知识点/错因/备注及现有块 text/note。图片、框位、顺序、来源、状态和训练不允许修改；人工保护任一变化目标则整次不写、返回 suggestions。内置助手继续检查本对话及完整运行身份；两入口共用补丁校验。

MCP 错因需 cause_statement，保存 client_asserted；原草稿 source_channel/原来源身份保留，last_mcp_edit 单独记录本次密钥和请求身份。草稿补丁与 mcp_patch_requests 幂等回执同一 SQLite 事务；相同请求优先复用回执，内容不同为 request_conflict，新请求旧版本为 revision_conflict，已结束为 state_conflict。返回前复查权限，失败事务不部分写入。

## 11. 展示板读取与版本

list_boards 默认 50/最多 100，返回分页板摘要及完整文件夹/catalog_revision。get_board 同上分页题目引用，含 revision、catalog_revision、版式与纸面摘要。boards v4 首次实际写入升级，旧文件读取不落盘；每板和目录单调版本、MCP 回执保留在同一原子 JSON 中。
