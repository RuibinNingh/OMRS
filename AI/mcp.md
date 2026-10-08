# OMRS MCP 接入

> **速查**
> - 职责：向获授权外部 AI 提供 OMRS 查询、复习调度创建、受保护草稿修订、报告保存和展示板管理
> - 入口：`omrs/mcp/server.py`、`http.py`、`keys.py`；`serve --mcp-port`
> - 不变量：二十二读十八写；Key 与 Web 权限分离；共享主进程写锁；完整原图进入既有审核队列
> - 必跑测试：`python3 -m unittest discover -s tests -p 'test_mcp*.py' -q`、`python3 tests/e2e/mcp.py`、`python3 tests/e2e/mcp_expansion.py`、`python3 tests/e2e/runtime_history.py`、`python3 tests/e2e/mcp_review_sessions.py`
> - 相关：`AI/api.md`、`AI/drafts.md`、`AI/security.md`、`AI/agent.md`、`requirements-mcp.txt`

## 1. 安装与启动

MCP 使用官方 Python SDK 的 Streamable HTTP。安装可选依赖后与主 Web 服务同进程启动；普通 Web 启动无需这些依赖：

```bash
python3 -m pip install -r requirements-mcp.txt
python3 omrs_engine.py --vault /path/to/vault serve --port 8471 --mcp-port 18472
```

MCP 只监听 `127.0.0.1`，示例地址是 `http://127.0.0.1:18472/mcp`。外部客户端使用 HTTPS 反向代理，仅转发 `/mcp`，并在启动时指定 `--mcp-public-url https://your-host/mcp`，登记精确 Host/Origin 白名单。SDK 负责协议协商、JSON-RPC、认证 challenge 和传输安全；启动失败时主命令明确退出。没有独立读写 Vault 的 MCP 进程入口。生产 HTTPS 8472 已由 Web/Nginx 共用，不能把内部 MCP 绑定到该端口；实际发布根与参数见 `AI/environment.md`。

在 OMRS 设置 → 访问与安全 → 外部 AI / MCP 点击“创建密钥”，在窗口选择下表八项权限，并可指定到期时间。查询与创建草稿默认勾选，六项新增写权限默认关闭；已有密钥不自动增权。成功后同一窗口显示一次明文，关闭后无法再次查看；有效密钥可编辑权限，失效记录默认折叠，时间按设备本地时区显示。页面行为见 `AI/frontend/settings.md`。本机 CLI 支持 `mcp-key create --name 名称`、`list`、`update --id KEY --scope SCOPE` 与 `revoke --id KEY`；`--scope` 可重复。MCP 请求使用 `Authorization: Bearer <key>` 或 `X-OMRS-MCP-Key: <key>`；密钥不得放进 URL、模型参数或日志。

## 2. 工具与权限

完整授权共 40 个工具（22 读、18 写），只读密钥发现 22 个，仅 `draft:create` 发现 1 个。发现与调用共用 `TOOL_SCOPES`，多权限依赖同时满足才开放。草稿创建与报告创建不强制额外授予读权限。

对客户端的工具描述、录题规范、逐参数说明与示例集中维护在 `omrs/mcp/tool_docs.py`。注册入口复用同一份描述，先生成既有参数 schema，再补说明元数据；自由对象的字段说明不增加新的校验约束。完整授权的 40 个工具、162 个顶层参数及附件/块等嵌套字段均有中文说明，权限名称从 `TOOL_SCOPES` 附加。新增参数须同时补说明。真实 SDK 验证见 `tests/test_mcp_protocol.py`，校验契约保持见 `tests/test_mcp_tool_docs.py`。

MCP 学习查询的业务响应直接返回字段，不带内置助手的 `result` 包装。例如推荐读取 `selection`，读题读取 `images`、`question_id` 和 `content_hash`；审核操作自身的 `result` 字段仍是应用结果。SDK 可以通过 structuredContent 或文本 JSON 封装传递这些字段。客户端须刷新工具清单及服务端 instructions 才能加载更新后的说明。

| 权限 | 能力 | 默认 |
| --- | --- | --- |
| `omrs:read` | 下表全部查询、原图与导出 | 勾选 |
| `draft:create` | 创建待审核草稿 | 勾选 |
| `draft:update` | 修订所有来源待审核草稿，同时需要 `omrs:read` | 关闭 |
| `report:create` | 新建报告 | 关闭 |
| `board:write` | 创建、编辑、复制、组织板和文件夹，同时需要 `omrs:read` | 关闭 |
| `board:delete` | 删除板或文件夹，同时需要 `omrs:read` | 关闭 |
| `session:create` | 提交正式复习计划审核，同时需要 `omrs:read` | 关闭 |
| `question:propose` | 提交正式题目修改审核，同时需要 `omrs:read` | 关闭 |

题目写权限只开放提案；MCP 没有人工批准接口。正式计划与改题先返回待确认状态及中心链接，批准后通过 get_mcp_operation 查询领域结果。

### 完整工具清单

| 工具 | 行为 | 所需权限 |
| --- | --- | --- |
| `list_taxonomy` | 科目、分类与知识点词表 | `omrs:read` |
| `search_questions` | 筛选、排序和分页检索题目 | `omrs:read` |
| `get_question` | 稳定 question_id、可编辑字段、正文哈希与图片列表 | `omrs:read` |
| `get_question_image` | 按题目图片下标取原生完整图片 | `omrs:read` |
| `get_overview` | 同科目范围的概况 | `omrs:read` |
| `get_recommendations` | 现有复习推荐 | `omrs:read` |
| `list_sessions` | 分页练习 Session 列表及进度、可用性计数 | `omrs:read` |
| `get_session` | 分页稳定题目条目与完整反馈进度 | `omrs:read` |
| `list_drafts` | 待审核及其它状态草稿列表 | `omrs:read` |
| `get_draft` | 草稿正文、来源与版本 | `omrs:read` |
| `get_questions` | 最多 20 UID，保留顺序并逐项报缺失 | `omrs:read` |
| `get_question_content` | 当前或已登记版本的完整分节正文分页 | `omrs:read` |
| `get_draft_image` | 按来源图片下标取原生完整图片 | `omrs:read` |
| `get_question_history` | 有效反馈或正文版本历史 | `omrs:read` |
| `get_learning_history` | 先筛选再按 Ledger 游标读学习/变更时间线 | `omrs:read` |
| `get_analytics` | 六种详细分析视图 | `omrs:read` |
| `list_reports` | 报告元数据列表 | `omrs:read` |
| `get_report` | 报告 HTML 源码分页，不执行脚本 | `omrs:read` |
| `list_boards` | 分页板列表、完整文件夹与目录版本 | `omrs:read` |
| `get_board` | 分页题目引用、版式、纸面摘要与版本 | `omrs:read` |
| `get_mcp_operation` | 本密钥发起的确认操作状态 | `omrs:read` |
| `export_board` | 全部/仅新增的限时不可变 HTML 快照 | `omrs:read` |
| `create_draft` | 原图或文字创建待审核草稿 | `draft:create` |
| `update_draft` | 受人工保护的字段/块修订 | `omrs:read` + `draft:update` |
| `create_report` | 幂等新建报告，不覆盖旧报告 | `report:create` |
| `propose_question_update` | 白名单正式题目修改提案，待人工修订/批准 | `omrs:read` + `question:propose` |
| `create_review_session` | 按稳定身份幂等创建正式复习计划 | `omrs:read` + `session:create` |
| `create_board` | 新建板，可带初始题目引用 | `omrs:read` + `board:write` |
| `update_board` | 局部修改板名、备注、来源标记 | `omrs:read` + `board:write` |
| `duplicate_board` | 复制引用与版式，不复制纸面记录 | `omrs:read` + `board:write` |
| `add_board_items` | 完整校验后加题，跳过已有引用 | `omrs:read` + `board:write` |
| `remove_board_items` | 移除引用，清空非空板需网页确认 | `omrs:read` + `board:write` |
| `reorder_board_items` | 所有条目引用的完整排列 | `omrs:read` + `board:write` |
| `update_board_layout` | 严格范围的局部版式补丁 | `omrs:read` + `board:write` |
| `update_board_item` | 单题留白与置顶 | `omrs:read` + `board:write` |
| `create_board_folder` | 新建文件夹 | `omrs:read` + `board:write` |
| `update_board_folder` | 文件夹名称或排序 | `omrs:read` + `board:write` |
| `move_board` | 移动板或调整组内位置 | `omrs:read` + `board:write` |
| `delete_board` | 申请删除板，由网页确认 | `omrs:read` + `board:delete` |
| `delete_board_folder` | 申请删除文件夹，默认保留板 | `omrs:read` + `board:delete` |

### 共同授权边界

原有十个查询工具为：`list_taxonomy`、`search_questions`、`get_question`、`get_question_image`、`get_overview`、`get_recommendations`、`list_sessions`、`get_session`、`list_drafts`、`get_draft`。七个学习数据查询直接复用 `omrs/agent/tools/read.py` 的实现和 schema，继承筛选、排序、分页、正文截断、练习记录和推荐口径。草稿查询使用同一草稿库的只读业务视图，不触发作业恢复、来源关系回填或训练；存储初始化仍执行既有技术 schema 迁移。

`propose_question_update` 需要 omrs:read + question:propose，参数为 uid、question_id、expected_content_hash、patch、必填非空 reason（1–2000 字符）、request_id。patch 允许 question_text、answer_text、cause、note、knowledge_points、difficulty、labels；不开放学习状态、路径、整篇 Markdown 或附件修改。修改原因使用 reason 参数；详情与安全写入见 `AI/ai-review.md` 与 `AI/ledger.md`。

工具不启动内部模型或 Agent 循环。未知工具、额外参数、非法类型和 scope 不足均由服务端拒绝。不存在直接正式建题、直接提交/丢弃草稿、反馈、未经审核的题目修改、Session 删除或设置写入、任意文件读取或任意 HTTP 转发工具；普通 Web 端口在登录及业务路由之前拒绝 MCP 凭据。

每次协议请求和领域调用重新验证 Key；草稿创建在下载及等锁之后、实际写入前复查，URL 快速复用、inline 处理后复用及新建都在结果封装前再次校验 `draft:create`。处理中吊销、到期或权限变化返回 `forbidden`，已有合法提交仍保留。`tools/list` 按当前 Key 的实时 scope 返回上表允许的工具；过滤只作用于当前请求的描述，完整注册表保持，SDK 共享定义缓存不承担授权；直接点名隐藏工具仍拒绝。`错题/.omrs/mcp_keys.json` 仅保存 SHA-256 摘要和非秘密元数据，0600；线程锁和操作系统文件锁共同避免本机 CLI 与 Web 的创建/吊销/最近使用时间互相覆盖。Key 管理响应禁止缓存。

所有新增写入和 `export_board` 必填 `request_id`；同密钥、工具和编号的相同请求复用结果，内容不同返回 `request_conflict`。板/草稿版本冲突为 `revision_conflict`；草稿已结束为 `state_conflict`；当前正文换版为 `content_conflict`。修复验收状态统一见 `AI/optimization.md`「MCP 修复」。

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

### 外部 AI 录题规范

只在用户明确要求录入或保存时创建草稿。一道完整题目一份草稿，相关小问留在同一份；多道独立题分别调用并使用不同 request_id。先对齐科目和分类，有查询权限时用 list_taxonomy，没有读权限时沿用用户明确提供的名称；无法判断的分类向用户确认。知识点用简短名称，最多 8 个，不把解题步骤当知识点。创建难度固定 5，创建参数不支持 labels 或 difficulty。

内容按原题阅读顺序组织，保留题干、条件、选项、单位、必要图表与全部小问。能完整转述的写文字，行内公式用 `$LaTeX$`、独立公式用 `$$LaTeX$$`；看不清或无法准确转述的内容保留原图，说明待核对处，不补造数据或漏掉条件。题目和答案分别组织：没有图片的答案只用一个文字块，步骤和段落用换行；有图片时仅在图片边界分块，相邻答案文字合并。答案未知可省略；用户要求生成解答时标明“补充解答，待核对”，不能冒充来源答案。

images 保存本题全部来源原图；即使全部正文转成文字，也关联来源以便审核。image 块只引用该数组从 0 开始的下标，不是 block_id、file_id 或内置助手的 IMG-n。平台文件上传参数可以由客户端转换为附件对象；原始 SDK 按 MCPFile 提供 download_url/file_id，可附 data_base64；服务端不读取客户端本地路径。

MCP 图片块始终保存和显示完整原图。note 是图片说明，不会执行裁剪，不能传框或坐标。来源本身是独立图时可与文字混排；题干、图表和小问不能安全拆开时保留完整题目原图。一页有多题时在 note 指明目标题号和人工核对范围，不把多次引用同一整图说成多个局部裁图。附件获取失败或容量超限时报告缺失，不能静默去掉图再提交并声称原图已保存。

cause 只记录用户明确表达的错因，cause_statement 逐字摘自用户消息；没有原话时两者留空，不阻塞其它完整内容建草稿。模型解题结论不能充当错因证据。外部原话在服务端只能标为 client_asserted，仍需人工核对；与内置助手从本地用户消息中校验原话的机制不同。

create_draft 成功只表示待审核，返回 draft_id/revision/status/source_images，不返回正式题目 UID。将草稿交用户在审核中心核对后入库，不能声称已进入正式题库。相同操作发生响应丢失时沿用原 request_id 和内容重试；内容改动或独立新题使用新编号。修改已建草稿用 get_draft → update_draft，不通过换编号重复建草稿绕过人工保护。

### 最小录题示例

以下是原始 MCP 调用格式；下载地址为示例占位符，实际调用使用平台提供的原附件。客户端发现的 create_draft schema 中也携带纯文字、完整原图和图文混排示例。

纯文字题与单块答案：

```json
{"subject":"数学","category":"方程","request_id":"entry-text-001","blocks":[
  {"section":"题目","kind":"text","text":"解方程 $2x+1=5$。"},
  {"section":"答案","kind":"text","text":"$2x=4$。\n因此 $x=2$。"}
]}
```

完整原图保留，答案尚未知：

```json
{"subject":"物理","category":"力学","request_id":"entry-original-001",
 "images":[{"download_url":"https://files.example.org/question.png","file_id":"file-question-1"}],
 "blocks":[{"section":"题目","kind":"image","image":0,"note":"保留完整题干、图表和全部小问，待核对。"}]}
```

文字转述仍保留来源，把第二例的 images 同时传给第一例即可，不必为了关联原图再加入重复的整图正文块。草稿修订只接受 subject/category/knowledge_points/cause/note 及已有块的 text/note，块新增、调序、图片替换和框选由网页处理。

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

图片只从 HTTPS 443 下载，不带用户信息或 fragment；禁止重定向。DNS 全部地址必须是公共地址，随后固定已校验 IP 建连；TLS SNI 与证书校验使用 `HTTPSConnection.host` 中的原主机名，而不是固定 IP，阻止 DNS 重绑定、私网、回环和元数据访问。连接读取超时 10 秒，流式下载总期限 30 秒，URL 不超过 8192 字符，响应超过 8 MiB 立即失败。下载从不转发 MCP Key。

## 6. 客户端兼容性与验收

使用官方 `mcp==1.28.1` ClientSession 和临时 Vault 重现 initialize、tools/list、tools/call、连续 Bearer 鉴权、全部权限发现、查询与写入工作流。`tests/test_mcp_download_connection.py` 只替换 DNS 与底层 socket/TLS I/O，保留真实 HTTPS 连接方法、HTTP 解析和原图草稿保存，验证固定公共 IP、原主机名 SNI、证书拒绝与原字节相等；该受控回归不等同于 ChatGPT 原生附件联调。真实浏览器覆盖草稿审核、Key 权限、报告、展示板保存冲突、网页确认和快照下载。完整验收必须安装依赖并真正执行 SDK 用例；缺 SDK 时的 SKIP 不能作为通过。

ChatGPT Developer Mode 官方文档列出的认证方式为 OAuth、No Authentication、Mixed Authentication。文档中的 static credentials 是 OAuth 客户端凭据，不证明直接 URL 连接支持任意 API Key 请求头。可使用 Secure MCP Tunnel 私有连接，由客户侧 Tunnel 客户端从受限文件注入 Authorization，仍由本 MCP 验证 scope；无需把公网入口改成无鉴权。直接 URL 模式若不能发送 Key，则需另行提供保持相同 scope 的 OAuth 兼容入口。当前 ChatGPT 账户尚未联调，不能把外部 SDK 或 Tunnel 健康检查当成账户已接通。

## 7. 工具调用记录

`RestrictedMCP.call_tool` 在工具执行边界通过工作线程写入 `omrs/runtime_records.py`：开始时记 `running`，正常查询结束记 `success`；关联确认操作按真实状态记录，稳定工具错误记 `failure`，取消记 `interrupted`。耗时采用单调时钟，错误仅保留固定错误码与安全说明。记录含当次密钥编号和公开名称快照，不额外改变既有权限复查次数。只记录到达工具执行边界的调用；握手、工具发现、健康检查及 HTTP 层未认证 / 限流请求不生成调用记录。

题图调用登记为“读取题图”，参数摘要只保存脱敏 UID 和 image_index；原生图片结果不写入运行库。成功创建、幂等复用和读取草稿的结果可保存 `draft_id`；详情读取当前草稿状态及 Ledger 中 `_draft.draft_id` 对应的人工入库节点。没有旧记录时不推测或补造来源。独立运行库不进入学习 Ledger，也不参与学习修正或状态还原；格式与启动恢复见 `AI/runtime.md`，页面见 `AI/frontend/records.md`。

记录存储故障不会改变已授权工具的结果或撤回已有合法提交，只输出固定无敏感内容的诊断。记录结束写入失败可能留下 `running`，下次 `serve` 启动会恢复为中断；中断不证明草稿未写入，重试前仍需核对草稿或使用原幂等请求。读取接口独立报告故障，学习详情的来源关联读取失败则保留学习信息并给出说明。

工具调用通过task传播题库世代，实际存储段才取租约。恢复后旧工具结果返回 `vault_changed`，维护繁忙返回 `vault_busy`；旧世代的运行结束回执不写入新库，也不覆盖原工具错误。`tests/test_mcp_lifecycle.py` 验证该边界。

生产发布目录和地址见 `AI/environment.md`，当前40工具、统一审核与安全改题已部署v2.3.0，发布状态见 `AI/plans/ai-review-center/progress.md`。正式计划先待审，question:propose默认关闭。账户接入状态见 `AI/plans/mcp-integration/progress.md`；本地 SDK 验收不等同于 ChatGPT 账户联调。

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

update_draft 需同时 omrs:read/draft:update；expected_revision 和 request_id 必填，允许各来源 cropping/review 草稿，仅科目/分类/知识点/错因/备注及现有块 text/note。图片、框位、顺序、来源、状态和训练不允许修改；请求触及任一人工保护目标（即使值相同）则整次不写、返回 suggestions。内置助手继续检查本对话及完整运行身份；两入口共用补丁校验。

MCP 错因修改及清空均需 cause_statement，实际改变后保存 client_asserted；原草稿 source_channel/原来源身份保留，last_mcp_edit 单独记录本次密钥和请求身份。草稿补丁与 mcp_patch_requests 幂等回执同一 SQLite 事务；相同请求优先复用回执，内容不同为 request_conflict，新请求旧版本为 revision_conflict，已结束为 state_conflict。返回前复查权限，失败事务不部分写入。

## 11. 展示板读取与版本

list_boards 默认 50/最多 100，返回分页板摘要及完整文件夹/catalog_revision。get_board 同上分页题目引用，含 revision、catalog_revision、版式与纸面摘要。boards v4 首次实际写入升级，旧文件读取不落盘；每板和目录单调版本、MCP 回执保留在同一原子 JSON 中。

## 12. 展示板管理与网页确认

展示板管理工具分 board:write 和 board:delete，均同时需要 omrs:read；草稿修订同需读权限。新增写权限默认不勾选，旧密钥不增权。设置页可编辑有效密钥权限，本机 mcp-key update --id KEY --scope SCOPE 可重复指定；已到期或吊销不可复活。

写工具必须带 request_id，板写检查 expected_revision；创建、复制、移动、删除、改名和文件夹操作还检查 expected_catalog_revision。局部补丁的白名单、数值边界、完整排序和批量实际变更见 AI/board.md。变更与幂等回执同次 boards.json 原子写入。

删除板/文件夹、清空非空板、实际重置纸面记录均先返回 pending_confirmation、影响预览、operation_id 和网页链接。统一ai_review.db保存完整请求并作为唯一审批权威，旧MCP确认库只提供历史兼容；网页确认时重查密钥、权限、板和目录版本及影响范围。解除版式锁定不能绕过实际纸面重置确认；普通引用增删和排序保留纸面。get_mcp_operation只查本人操作，没有模型确认工具，查询不执行业务重放。

--web-public-url 指定主 Web HTTP/HTTPS 来源（不含路径、查询或凭据）；默认实际 Web 回环端口。确认链接指向该来源的 /#/ai-review?operation=编号，旧history确认链接兼容跳转中心，PIN登录保留hash。MCP凭据仍不可调用任何Web管理端点。

## 13. 展示板安全导出

export_board 需要omrs:read与request_id，支持all/new，可选expected_revision防止导错板版本。原子保存不可变自包含HTML，24小时内返回Web登录下载链接，不返回HTML/Base64，不记录已打印。详细存储恢复及附件边界见AI/export.md。全授权40工具，只读22，仅创建草稿1。


## 14. 正式复习调度

`create_review_session(items, request_id)` 需要同时 `omrs:read` 与 `session:create`。每次 1–100 个有序条目，必填非空 `question_id` 与 `source=due|proficiency`；可选 `uid` 兼容推荐 selection 的展示快照，创建按稳定身份解析当前位置，不靠旧 UID 绑定。相同身份和来源去重并保留首次顺序，同身份来源冲突整次拒绝。单题也创建正式 `EXP-` Session，不走 `TMP-` 兼容路径。只有用户明确要求生成正式计划才调用；查询和推荐不创建计划。

提交前检查当前题目身份、归档、停用和 active Session 占用；任一不合法整次拒绝。单一科目自动写 subject_filter，跨科目为空。创建事实、SQL 投影和技术回执同一 SQLite 写事务提交；不记答题、不改变熟练度、Attempts、EF 或复习日期。回执优先于占用检查：同密钥、请求和规范化条目复用原编号，内容变化为 request_conflict。计划撤销或学习状态恢复后不重新创建，返回原编号、reused=true、available=false 及 retracted 状态。来源为 mcp，回执不进入学习提交 payload。

推荐 due、proficiency 与 selection 均保留 uid/source 并带 question_id。list_sessions 支持 status、offset 和 limit（默认 20、最多 100），共享工具保留 result.sessions 包装，MCP 沿用扁平 sessions 字段，增加 total、next_offset、完整反馈进度及 availability_counts；按创建时间和编号从新到旧排序，包含全部停用的 active 计划。get_session 保留 pending/done/count，增加创建与完成时间、完整进度、total_count、availability_counts 和 entries；entries 默认 100、最多 100，按 offset 翻页，entries_total 与 next_offset 指明后续页。完整进度不受条目分页影响。

条目保持 entry_id、question_id、uid_at_creation、当前 uid、source、availability 和 feedback_submitted。active/completed 沿用持久化领域状态，不按时间过期，也不把待反馈为零当作完成；停用、归档与待绑定状态单独显示。创建在等锁后、提交前和返回前复查权限，提交后的吊销不撤回合法事实。技术存储见 AI/mcp-storage.md，协议回归为 tests/test_mcp_review_sessions.py，网页闭环为 tests/e2e/mcp_review_sessions.py。

## 正式题目修改提案

先通过 get_question 或 get_question_content 读取稳定 question_id 与完整 content_hash，提交 propose_question_update 后正式正文保持原样。题干/答案/错因/补充备注/知识点/难度/已有标记可提案，difficulty 是 1–10 严格整数；不能新增标记定义。人工修订仅限原 patch 字段，技术重试复用原操作，不覆盖修订。MCP 查询 get_mcp_operation 可取得真实终态和结果。

note 管理 `# 备注` 下的 `## 补充备注`，保留旧裸文本、未知子节、错因和关联；不迁移旧备注。章节编辑拒绝系统章节结构注入，知识点/标记规范编码并拒绝控制字符。Obsidian 与普通 Markdown 图片引用的 token、数量、顺序和所属章节保持；不能经正文补丁新增、移动或移除附件。

正式复习计划 create_review_session 先返回 pending_confirmation、operation_id 和中心链接；批准前不创建 Session，不返回新 session_id。成功旧请求重试复用原计划；拒绝或到期后需新 request_id，不能复活撤销的计划。审批撤权、内容换版、目标移动或过期均不继续写。

## 标记整理审批

标记整理的领域提案由网页审核中心确认，来源密钥贯穿准备、提交与执行。正式提案保存完整归类方案，模型没有批准入口；已提交原生回执优先于随后权限变化。
