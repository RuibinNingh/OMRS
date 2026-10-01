# OMRS MCP 接入

> **速查**
> - 职责：向获授权外部 AI 提供 OMRS 只读查询和待审核草稿创建
> - 入口：`omrs/mcp/server.py`、`http.py`、`keys.py`；`serve --mcp-port`
> - 不变量：九读一写；Key 与 Web 权限分离；共享主进程写锁；完整原图进入既有审核队列
> - 必跑测试：`python3 -m unittest tests.test_mcp tests.test_mcp_keys tests.test_mcp_http tests.test_mcp_protocol tests.test_mcp_draft_atomic -q`、`python3 tests/e2e/mcp.py`
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

固定开放九个查询工具：`list_taxonomy`、`search_questions`、`get_question`、`get_overview`、`get_recommendations`、`list_sessions`、`get_session`、`list_drafts`、`get_draft`。前七项直接复用 `omrs/agent/tools/read.py` 的实现和 schema，继承筛选、排序、分页、正文截断、练习记录和推荐口径。草稿查询使用同一草稿库的只读业务视图，不触发作业恢复、来源关系回填或训练；存储初始化仍执行既有技术 schema 迁移。

`create_draft` 是唯一业务写工具，需要 `draft:create`。它不启动内部模型或 Agent 循环。未知工具、额外参数、非法类型和 scope 不足均由服务端拒绝。不存在正式建题、提交/修改/丢弃草稿、反馈、标记、Session、设置、文件读取或任意 HTTP 转发工具；普通 Web 端口在登录及业务路由之前拒绝 MCP 凭据。

每次协议请求和领域调用重新验证 Key；创建在下载及等锁之后、实际写入前复查，URL 快速复用、inline 处理后复用及新建都在结果封装前再次校验 `draft:create`。处理中吊销、到期或权限变化返回 `forbidden`，提交后失效仍保留草稿与原图。`tools/list` 按当前 Key 的实时 scope 返回九读、仅 `create_draft` 或全部十项；发现与调用共用显式工具→scope 映射。过滤只作用于当前请求的描述，完整注册表保持，SDK 共享定义缓存不承担授权；直接点名隐藏工具仍拒绝。`错题/.omrs/mcp_keys.json` 仅保存 SHA-256 摘要和非秘密元数据，0600；线程锁和操作系统文件锁共同避免本机 CLI 与 Web 的创建/吊销/最近使用时间互相覆盖。Key 管理响应禁止缓存。

审查修复验收状态统一见 `AI/optimization.md`「MCP 修复」，实施按 `AI/plans/mcp-integration/exec-2026-10-01-mcp-fixes.md`。

`get_overview(subject=...)` 的全部概况字段来自共享统计入口中的同一科目范围，未知科目返回零计数与空明细；统计口径见 `AI/api.md` 与 `AI/agent.md`。

## 3. 创建契约

必填 `subject`、`category`、`request_id` 和 `blocks`。块沿用 OMRS 的 `section=题目|答案`、`kind=text|image`；文字块提供 `text`，图片块的 `image` 是 `images` 从 0 开始的下标，可带 `note`。相邻答案文字通过 `omrs/draft_prepare.py` 与内置助手共用的规则合并，图片断开文字段。科目、分类、知识点与文字边缘空白规范化后计算幂等摘要。

文件元数据声明 `_meta["openai/fileParams"]=["images"]`。每个文件对象必须有 `download_url` 和 `file_id`，可选 `mime_type`、`file_name`；实际格式取决于收到的图片内容。可发送 HTTPS 下载地址，支持自定义文件传输的外部客户端也可在同一对象提供 `data_base64` 原字节；不接受本地路径。最多 6 张、单张 8 MiB，PNG/JPEG/GIF 每张解码总像素不超过 4000 万、最多 100 帧；校验只解码，不重编码。

最多 40 个输入块、8 个知识点；每块文字或说明最多 20000 字符，总文字最多 500000 字符。不能指定草稿状态、难度、正式 UID、来源、SHA、本地路径、坐标或训练设置。错因必须同时带 `cause_statement`，保存为 `client_asserted` 并在页面标明待核对；不冒充已验证的本地用户消息。

## 4. 原子保存与人工审核

草稿连接在全局写锁与草稿锁内串行建表、迁移；初始化失败关闭连接。下载与图片校验在全局写锁之外，最后幂等复查和原子创建使用同一领域写锁，不持独立 MCP 模块锁。

来源由服务端固定写入 `source_channel=mcp`、`source_key_id`、`source_request_id`。创建复用 `drafts.create_draft` SQL，在同一写锁与数据库事务内关联原图、草稿和幂等记录。原图按实际字节 SHA 原子落盘；失败回滚并清理本次新文件，保留共享原件，提交后的响应失败不会删除已提交原图。崩溃留下的半文件按实际收到的原字节校验和恢复，拒绝符号链接。

草稿固定 `review`、难度 5。正文图片块是固定全幅 `0,0,1,1`、`box_origin=original`，页面显示“完整原图”；这种全幅引用不代表框选或训练标注。原图不裁剪、压缩、标注或重编码，普通草稿图片接口也返回完整字节。创建和普通人工正文编辑不会自动打开训练或创建训练任务；用户明确操作训练功能时才进入既有训练流程。

`(source_key_id, request_id)` 唯一。相同内容重试返回原草稿及 `reused=true`，不同内容拒绝。稳定 `file_id` 的下载附件允许更新短期签名 URL 后重试，无需重新下载已保存原件；带 inline 原字节的重试仍验证内容 SHA。人工已修改或丢弃的草稿只返回当前状态，不复建或覆写。

用户在已有草稿区查看“来源：MCP”和完整来源图片，再编辑、审核、通过或丢弃。正式入库仍由当前人工流程决定；MCP Key 没有后续修改或提交权限。未收到图片的文字草稿同样进入审核队列。

## 5. HTTP 与下载边界

有效 Key 每分钟最多 120 个请求、最多 4 个并发请求。请求体上限 72 MiB，声明长度及分块流都计数，总读取期限 30 秒；错误为 400/408/413/429。查询字符串、工具参数和异常响应不包含认证凭据，生产适配器关闭访问日志。

图片只从 HTTPS 443 下载，不带用户信息或 fragment；禁止重定向。DNS 全部地址必须是公共地址，随后固定已校验 IP 并保留 TLS 主机证书验证，阻止 DNS 重绑定、私网、回环和元数据访问。连接读取超时 10 秒，流式下载总期限 30 秒，URL 不超过 8192 字符，响应超过 8 MiB 立即失败。下载从不转发 MCP Key。

## 6. 客户端兼容性与验收

已使用官方 `mcp==1.28.1` ClientSession，对真实临时 Vault 的同进程服务完成 initialize、tools/list、tools/call、连续 Bearer 鉴权、查询、原图草稿、并发重试、吊销和越权拒绝，并用真实浏览器验证草稿区和 Key 管理。可运行速查头中的测试重现，无 SDK 时协议测试明确 SKIP。

ChatGPT Developer Mode 官方文档列出的认证方式为 OAuth、No Authentication、Mixed Authentication。文档中的 static credentials 是 OAuth 客户端凭据，不证明直接 URL 连接支持任意 API Key 请求头。可使用 Secure MCP Tunnel 私有连接，由客户侧 Tunnel 客户端从受限文件注入 Authorization，仍由本 MCP 验证 scope；无需把公网入口改成无鉴权。直接 URL 模式若不能发送 Key，则需另行提供保持相同 scope 的 OAuth 兼容入口。当前 ChatGPT 账户尚未联调，不能把外部 SDK 或 Tunnel 健康检查当成账户已接通。

生产当前运行 `/root/workspace/apps/releases/omrs-3ae2729`，同进程 MCP 仍仅监听回环端口并经 HTTPS 反代。F0–F4 修复已更新：官方 SDK 发现 9 个只读工具，`get_overview(subject="生物")` 返回 19 题、逾期 3、今日到期 16；隐藏的 `create_draft` 调用被拒绝，普通 Web API 对 MCP Key 返回 403，吊销后的 Key 返回 401。生产未创建验收草稿；主应用浏览器因缺少 PIN 会话未进入，完整页面闭环仍以隔离实例结果为准。部署与数据核验见 `AI/plans/mcp-integration/progress.md`。

官方参考：[Developer Mode](https://developers.openai.com/api/docs/guides/developer-mode)、[Apps SDK 文件参数](https://developers.openai.com/apps-sdk/reference/)、[认证](https://developers.openai.com/apps-sdk/build/auth/)、[Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)。
