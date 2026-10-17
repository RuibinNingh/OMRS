# HTTP v1 与管理接口

> 所有 API 响应 JSON，成功 `status="ok"`，失败只返回稳定 `{status:"error",msg,code}`，不返回异常原文、凭据或上游错误正文。静态面板/资源返回 HTML/CSS/JS。时间字段为 Unix 秒，`latency_ms` 是毫秒。

## 冻结的客户端协议

### GET /healthz

不鉴权（仍校验可信 Host）。仅返回：

```json
{"service":"zuoyebang-gateway","version":"1.0.0","status":"ok"}
```

### GET /api/v1/status

本机和外部都必须带唯一 `Authorization: Bearer <调用Key>`。不主动联网，也不执行账号刷新。响应字段必须保持：

```json
{
  "status":"ok",
  "account":{
    "local_session_ready":false,
    "has_account_credential":false,
    "observations":{"account":{},"signing":{},"events":[]}
  },
  "panel_url":"/"
}
```

有设备后 observations 对应部分可含 `state`（unknown/valid/invalid）、`imported_at`、`last_success_at`、`first_invalid_at`、`valid_until_after`。事件仅 `event/kind/at`、可选整数 `code` 与恢复标志；最多最近 100 项。不返回设备标识、签名种子、Cookie、账号令牌或二维码挑战。

### POST /api/v1/search

同样必须 Bearer 鉴权。请求必须为 JSON 对象，字段只允许：

```json
{"image_base64":"原图片字节的标准base64，不含data前缀","grade":0}
```

`grade` 严格整数 0..12（不能 bool、字符串、浮点数）。原图片单帧 PNG/JPEG/WebP，最多 8 MiB、4000 万像素；完整验证后原字节留存在历史中。官方 multipart 使用JPEG：JPEG原样发送，PNG/WebP生成同尺寸、质量95的JPEG副本，透明处合成白底，不转置、不缩放；picMD5及签名依实际发送字节计算。副本超过8MiB返回image_invalid，不自动压缩降质或重试。必须唯一 Content-Length，不接受 chunked、重复 JSON 字段、非对象、NaN/Infinity；总请求 JSON 预算为原图标准 base64 长度加 1024 字节信封。

成功精确封装 DirectClient.search 已解码对象，不执行候选归一化、渲染或入库：

```json
{"status":"ok","result":{"ok":true,"data":{"answers":{}}}}
```

result中的answers.locs与angles逐项解base64／主Key RC4，不使用正文gzip或tidKey；未能解码的项为空字符串，可读候选仍返回。locs最多200项并计入累计解码预算，rotateAngle保留；坐标转换及题框分组由调用方执行。

示例仅示意结构，`result` 来自真实 DirectClient；服务不生成伪造题目。搜题每次只调用一次官方，不自动重试。会话更换期间的迟到结果返回 409，不能发布到新账号。响应/解码预算见安全文档。

## 管理认证

`/api/admin/*` **不接受调用 Key 作为管理权限**，即使同时附有该头也拒绝。登录 POST 必须精确同源 Origin；其余管理 POST 同时要求登录 Cookie、同源 Origin 和 `X-CSRF-Token`。不要在 URL/query 中带 Key 或管理员秘密。

| 方法/路径 | 请求 / 响应 |
|---|---|
| POST `/api/admin/login` | `{password}`；Set-Cookie `zyb_admin`，JSON `{status,csrf_token,expires_at}` |
| GET `/api/admin/session` | 已登录 Cookie；返回 csrf_token/expires_at，便于页面刷新 |
| POST `/api/admin/logout` | `{}`；服务端立即删除 session、清 Cookie |
| GET `/api/admin/account` | `{status,account}`，与 v1.account 脱敏形状一致 |
| POST `/api/admin/profile` | `{profile}`；固定官方 URL、已登记 fields/headers/session_token；返回 account；旧二维码失效 |
| POST `/api/admin/credential` | `{credential}`；先有设备会话，导入新账号凭据；不回显、使旧二维码失效 |
| POST `/api/admin/account` | `{operation,flow_id?}`；verify/refresh/qr_start/qr_poll/qr_cancel；返回 `{status,result,account}` |
| GET `/api/admin/keys` | `{status,keys:[metadata...]}`；绝无原 Key 或密钥摘要 |
| POST `/api/admin/keys` | `{name}`，1..80 字符；返回 `{status,key,metadata}`，**只此响应一次显示完整 Key** |
| POST `/api/admin/keys/revoke` | `{id}`；立即吊销，幂等，不泄漏 Key |
| GET `/api/admin/settings` | `{status,allow_external,limits,history_retention}`；预算与记录保留上限来自 CLI，只读 |
| POST `/api/admin/settings` | **只允许** `{allow_external:boolean}`；持久化，不更改监听/主机网络 |
| GET `/api/admin/history` | page/page_size/source/result/key_id/action；返回 status/items/total/page/page_size/has_more |
| GET `/api/admin/history/<id>` | 管理员会话；返回 `{status,item,detail}`，详情未留存时detail=null |
| GET `/api/admin/history/<id>/image` | 管理员会话；返回已校验的PNG/JPEG/WebP上传原字节，未留存／清理后404 |

`qr_start` 的 result 含 flow_id/state/expires_at/poll_interval/message 与官方挑战对应的 qr_url/qr_image；二维码由本地 Segno 生成，仅管理员创建响应含挑战。终态不返回挑战或令牌，面板禁用继续检查与取消按钮。轮询有至少 2 秒间隔与本地 300 秒有效期；需用户点击检查，不后台无限轮询。检查/刷新不返回官方用户对象，不修改并发取消或替换后的二维码流程。

密钥 metadata：`id,name,prefix,fingerprint,created_at,last_used_at,revoked_at,state`（active/revoked）。ID 为 16 个小写 hex；prefix 是很短的原 Key 前缀，fingerprint 为 SHA-256 前 12 位，不能恢复完整 Key。最近使用指有效 Key 通过认证的时间（包括后续输入失败）。

历史分页从 1 开始，默认 page_size=30、上限 100。最多 20 个查询字段，重复或未知参数 400；source 为 local/external；result=ok 为成功、error 为所有 HTTP>=400，也可指定稳定错误 code；key_id 必须是 16 位小写 hex；action只接受空值或search。排序按记录 ID 倒序。读取历史自身也审计，所以没有 key_id或action 筛选时，下一次读取总数可能增加。

审计 row 字段：`id,time,method,action,path,source,client_ip,peer_ip,key_id,result,http_status,latency_ms,has_detail`。尚未认证/先被外部开关拒绝时 key_id=null。列表不包含图片或搜题正文。path 不含 query，未知 path 固定 `/[unknown]`，HTTP 总并发拒绝为 `/[overload]`，详情／原图读取归并为 `/api/admin/history/{id}`／`/api/admin/history/{id}/image`，action分别为history_detail／history_image。

### 搜题详情与保留

详情的item是对应审计row；detail为 `{grade,image,response}`。grade在原图通过校验后保存，未通过校验时null；image为 `{content_type,width,height,bytes,sha256}`，没有有效图片时null。response精确保留本次客户端收到的已解码成功信封或固定安全错误信封，不保存官方错误原文、认证头、Cookie、账号／设备信息。详情不另返回上传原图的base64字段，原回执中的内联附图仍完整保留；上传原图通过独立管理员接口按原字节读取，不重编码。图片与JSON都返回 `Cache-Control: no-store`、`X-Content-Type-Options: nosniff`。

搜题通过调用鉴权与API限流后开始捕获安全回执；只有完整通过PNG/JPEG/WebP及像素／大小校验的原件才保存。此后的设备缺失、并发／每日预算、网络或官方错误仍保留原图。错误输入只保存安全错误；鉴权、来源策略或API限流阶段拒绝不会保存请求正文。会话更换导致的409只保存实际错误，不能保存未发布的旧成功内容。审计元数据与详情在同一SQLite事务中提交，写入失败返回503/audit_unavailable，不自动重试官方请求。

id为正十进制SQLite整数，详情接口不接受查询参数；记录不存在或已过期返回404。既有无详情的记录、未开始捕获的拒绝或被容量清理的记录仍返回item，detail=null。完整Key即使有效也不能读取详情或图片；必须使用独立管理员Cookie，附带Authorization头仍拒绝。

默认记录保留30天／10000条，详情内容总预算256MiB；CLI `--history-days`、`--history-limit`、`--history-detail-bytes`可调整，字节预算为1..2147483648。`history_retention`返回 `{days,limit,detail_bytes}`。审计写入、列表和详情／原图读取均执行清理：过期／超条数的历史级联删除图片与返回数据，字节超预算优先删除较早详情而保留元数据；单条详情超过总字节预算则不留存，不挤掉已有详情。预算计原图、原图元数据和响应JSON的UTF-8内容字节，不是SQLite物理文件大小；删除复用空闲页，不每次VACUUM。

## 稳定错误

| 状态 | 常见 code |
|---|---|
| 400 | json_invalid/body_invalid/body_budget/image_invalid/profile_invalid/filter_invalid/settings_invalid/operation_invalid/flow_invalid/credential_invalid/path_invalid/proxy_invalid |
| 401 | key_invalid/admin_required/admin_invalid |
| 403 | external_disabled/host_forbidden/origin_forbidden/csrf_forbidden/management_key_forbidden |
| 404 | not_found/key_missing |
| 408 | request_timeout |
| 409 | session_changed |
| 429 | rate_limited/budget_exceeded/concurrency_limited/login_limited |
| 502 | network/protocol/signing_session/login_required/upstream/response_budget |
| 503 | profile_missing/dependency_missing/audit_unavailable |
| 500 | internal_error（固定错误，不含异常文本） |

接口不开放 CORS。客户端后端（例如 OMRS）不需要 Origin；若 v1 请求附带 Origin，必须同源。非 loopback 的拒绝优先于 Key 鉴权，不能凭伪造 XFF 获得本机调用权限。官方 socket 断开归为 502/network；普通请求或并发满时审计存储失败归为 503/audit_unavailable，不返回底层异常原文。
