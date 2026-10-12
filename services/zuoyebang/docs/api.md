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

`grade` 严格整数 0..12（不能 bool、字符串、浮点数）。原图片单帧 PNG/JPEG/WebP，最多 8 MiB、4000 万像素；完整验证解码后仍使用**上传原字节**构造官方 multipart，不重编码。必须唯一 Content-Length，不接受 chunked、重复 JSON 字段、非对象、NaN/Infinity；总请求 JSON 预算为原图标准 base64 长度加 1024 字节信封。

成功精确封装 DirectClient.search 已解码对象，不执行候选归一化、渲染或入库：

```json
{"status":"ok","result":{"ok":true,"data":{"answers":{}}}}
```

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
| GET `/api/admin/settings` | `{status,allow_external,limits}`；预算来自 CLI，只读 |
| POST `/api/admin/settings` | **只允许** `{allow_external:boolean}`；持久化，不更改监听/主机网络 |
| GET `/api/admin/history` | page/page_size/source/result/key_id；返回 status/items/total/page/page_size/has_more |

`qr_start` 的 result 含 flow_id/state/expires_at/poll_interval/message 与官方挑战对应的 qr_url/qr_image；二维码由本地 Segno 生成，仅管理员创建响应含挑战。终态不返回挑战或令牌，面板禁用继续检查与取消按钮。轮询有至少 2 秒间隔与本地 300 秒有效期；需用户点击检查，不后台无限轮询。检查/刷新不返回官方用户对象，不修改并发取消或替换后的二维码流程。

密钥 metadata：`id,name,prefix,fingerprint,created_at,last_used_at,revoked_at,state`（active/revoked）。ID 为 16 个小写 hex；prefix 是很短的原 Key 前缀，fingerprint 为 SHA-256 前 12 位，不能恢复完整 Key。最近使用指有效 Key 通过认证的时间（包括后续输入失败）。

历史分页从 1 开始，默认 page_size=30、上限 100。最多 20 个查询字段，重复或未知参数 400；source 为 local/external；result=ok 为成功、error 为所有 HTTP>=400，也可指定稳定错误 code；key_id 必须是 16 位小写 hex。排序按记录 ID 倒序。读取历史自身也审计，所以没有 key_id 筛选时，下一次读取总数可能增加。

审计 row 字段：`id,time,method,action,path,source,client_ip,peer_ip,key_id,result,http_status,latency_ms`。尚未认证/先被外部开关拒绝时 key_id=null。path 不含 query，未知 path 固定 `/[unknown]`，HTTP 总并发拒绝为 `/[overload]`。不保存任意请求正文或官方结果。

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
