# HTTP API：收件箱、草稿、标注、训练与 MCP

> **速查**
> - 职责：收件箱、草稿、标注、训练与 MCP的请求、响应及错误语义
> - 入口：`omrs/http/registry.py`、`omrs/http/` 领域适配
> - 不变量：统一鉴权、读取期限和生命周期边界见 `AI/api.md`；注册表是路由唯一来源
> - 必跑测试：`tests/test_http_boundaries.py`、`tests/test_security.py`
> - 相关：`AI/api.md`、`AI/routes.md`、`AI/security.md`

## 收件箱端点 `/api/inbox/*` 与 `/m`

上传 → 框选 → 转换 → 提交 的暂存层，**不进 Ledger**；`commit` 复用 `create_question`。完整定义、job 单元格式、数据模型见 `AI/inbox.md` §3。`GET /items` 和 `/item` 的 item 含持久 `revision` 与 `reset_epoch`；`POST /item/update` 仅修改显式字段（明确传入的 regions 整体替换），更新、重置、丢弃和录入都必须携带 `expected_revision` 与 `reset_epoch`。旧版本、缺版本或代次冲突返回 409 `{status:"error",code,msg,current_revision}`，数据库不变；批量丢弃先检查全部项，再同事务修改。`ready` 仍由服务端校验。其余上传、任务、裁图、数据集与手机页入口见 `AI/inbox.md` §3；`POST /api/config` 可写 `inbox_*` 策略键（§8）。

`/api/ai-recognize` 行为不变；`ai_assist.py` 新增 `detect_regions`、`extract_region`、`parse_detect_output`，并按用途读 `ai_model_detect / ai_model_extract / ai_model_classify`（缺省回退 `ai_model`）。AI 助手附图另用 `transcribe_image`（截图转述成 `{summary, layout, blocks}`）与 `describe_image`（针对一张图回答具体问题），两者都走 `ai_model_extract`，见 `AI/agent.md` §1「附图」。

`extract` job 的响应契约不变：模型先判断删去区域裁图后是否仍能保留解题或理解原解析所需的全部信息，再返回 `{convertible, reason, text}`。依赖图形或图表且无法无损转写时应返回 `convertible=false`，服务端据此保存区域图片；实际判断仍需人工审核，细则见 `AI/inbox.md` §4。

区域提取兼容模型漏转义的数学定界符：严格 JSON 解析失败后只补齐 `\(`、`\)`、`\[`、`\]` 的转义，并将正文中成对的定界符统一为 `$…$` / `$$…$$`。其它格式错误、缺失布尔判断和空正文仍报错；本地兼容不额外调用模型或修改框位，详见 `AI/inbox.md` §4。

---

## 框选标注集端点 `/api/annotate/*` 与 `/annotate`

独立于收件箱的训练数据标注集，存储见 `AI/data/storage.md` §6，页面见 `AI/frontend/annotate.md`。访问控制与其他端点相同（`_authorize`；POST 走同源校验并在进程级写锁内处理，模块自带 `annotate._LOCK`）。保存和删除以持久 `revision` 做条件写入；版本冲突返回 409 `{status:"error",code:"revision_conflict",msg,current_revision}`，其他非法输入返回 400。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/annotate` | 标注页 `assets/app/annotate.html` |
| GET | `/api/annotate/images` | `{images:[{id, file, width, height, bytes, status, boxes, revision, uploaded_at, updated_at}], stats}`，按上传顺序 |
| GET | `/api/annotate/stats` | `{images, done, todo, boxes:{question, answer}}`；AI 训练页入口栏用它显示进度 |
| GET | `/api/annotate/raw?id=` | 原图二进制（`Cache-Control: private, max-age=86400`） |
| GET | `/api/annotate/export?format=yolo\|omrs_jsonl&all=1` | zip：`images/<sha256>.<ext>`、`labels.jsonl`（每行一张图，`boxes` 归一化）、`README.txt`；yolo 另含 `labels/<sha256>.txt` 与 `classes.txt`（0=question，1=answer）。默认只含 `status=done`，`all=1` 连未完成一起导出。服务端先写临时文件再分块发送，原图按 ZIP_STORED 存 |
| POST | `/api/annotate/upload` | multipart 多文件（按 `filename=` 识别）；只收 PNG / JPEG / GIF，任一文件不是图片则整批报错不写；sha256 去重 → `{images:[新建], duplicates:[{file, id}]}` |
| POST | `/api/annotate/save` | `{id, expected_revision, boxes:[{role, x, y, w, h}], status?}`：框整体覆盖；`role` 只能是 question / answer，坐标先按原值算右下角再夹到 0–1，宽或高小于 0.002 的框丢弃，一张最多 200 个；`status` 为 `todo` / `done`，缺省保留原状态 → `{image}`，revision 加一 |
| POST | `/api/annotate/delete` | `{id, expected_revision}`：版本吻合才删除记录与原图文件 → `{id}` |

## AI 草稿区端点 `/api/drafts/*`

草稿存 `错题/.omrs/drafts/`；创建、编辑和丢弃不写 Ledger，通过才写题目。存储、来源、revision、一次性入库及完整请求体见 `AI/drafts.md`。GET 保留原包装，新增写接口沿用登录、同源与全局写锁。

| 方法 | 路径 | 请求与响应 |
|---|---|---|
| GET | `/api/drafts/list?status=&conversation=&limit=` | `{status:"ok",drafts}`；pending 联合两种活动态，缺省排除 discarded |
| GET | `/api/drafts/item?id=` | `{status:"ok",draft}`，含 revision、blocks 与 source_images |
| GET | `/api/drafts/image?sha=` | 图片二进制，private/max-age=86400 |
| GET | `/api/drafts/counts` | `{status:"ok",counts}`，四态计数 |
| POST | `/api/drafts/update` | `{id,revision,fields,blocks,source_images?}` → `{status:"ok",draft}` |
| POST | `/api/drafts/discard` | `{id,revision}` → `{status:"ok",draft}` |
| POST | `/api/drafts/commit` | `{id,revision,crops?}` → `{status:"ok",draft,result,reused,training}` |
| POST | `/api/drafts/boxes` | `{id,revision,blocks?,training_boxes?}` → `{status:"ok",draft}` |
| POST | `/api/drafts/extract` | `{id,revision,block_ids,crops?}` → `{status:"ok",job}` |
| POST | `/api/drafts/detect` | `{id,revision,sha?}` → `{status:"ok",job}`；后台复核共享、人工框与 revision |
| POST | `/api/drafts/image/train` | `{id,revision,sha,enabled}` → `{status:"ok",draft,image}` |
| GET | `/api/drafts/job?id=` | `{status:"ok",job}`，持久后台任务及错误摘要 |
| POST | `/api/drafts/cleanup` | `{}` → `{status:"ok",cleaned,retained}`，不接受路径或自定义参数 |

写接口非法输入 400、不存在 404、状态/版本冲突 409、锁忙 503，错误含 msg/code，版本冲突含 current_revision。重复入库按持久操作与 `_draft` 提交恢复原题；不能用一次旧确认提交已编辑的新版本。

## 训练面板（只读接口）

`omrs/trainpanel.py` 只读配置 `train_dir` 指向的外部训练目录（空值为 `~/omrs-train`），不加载 torch／onnxruntime、不启动或停止训练。`/train` 为独立训练面板入口，前端说明见 `AI/frontend/trainpanel.md`。以下 GET 沿用登录授权：

| 方法 | 路径 | 响应 |
|---|---|---|
| GET | `/api/trainpanel/overview` | 训练目录 `training_model`（兼容 `model`）、实际服务 `online_state` / `online_model`、最新 dataset 摘要、latest、runs（各含 `current` 训练目录标记与 `online` 在线身份标记）、live 完成图计数／新增图数、commands、collect、独立 errors |
| GET | `/api/trainpanel/run?name=` | 指定实验 status、metrics、evaluation 与各字段 errors；JSONL 最后未写完的一行留待下次 |
| GET | `/api/trainpanel/overlay?run=&name=` | 仅返回该实验 eval.json 登记的 JPG／PNG 叠加图，private/no-store |
| GET | `/api/trainpanel/service` | 对配置检测地址的同源 `/health` 做 2 秒探测，state 为 online/offline/unconfigured；离线附启动命令 |

`status.json` 的 running 状态在 pid 不存在或更新时间超过 max(3×每轮秒数, 600 秒) 时只在响应中改为 interrupted，不写回文件。文件缺失是空状态；损坏文件仅在对应字段返回读取失败，不影响其他实验／指标。路径参数拒绝穿越及符号链接越界；不提供任意文件读取。新增完成图数按来源 ID 对照 manifest 中已纳入与已排除记录，不把旧排除图误算成新增训练数据。配置格式见 `AI/data/storage.md` §8。


### 实时测试 `/api/trainpanel/try`

POST multipart 单文件 PNG／JPEG／GIF，文件 ≤15 MB、解码后 ≤4000 万像素（长图可超过 10000 高）；原图与条带都在内存，不开积累时不创建文件或库。复用 slice_plan → JPEG 85 → detect_regions_local → merge_strip_boxes，返回 `{status:"ok", boxes, width, height, strips, elapsed_ms, collected?}`，框置信度为 conf。每进程最多同时测试一图，繁忙、非法文件、超限、服务未配置／离线／非法响应均返回 400 与中文 msg，离线附启动命令；继续沿用来源与登录校验。

配置 train_try_collect 为 true 时，仅积累阶段取得进程写锁，调用 annotate.upload 并以模型框 annotate.save(status=None)，保持 todo；返回 collected `{id, duplicate:false, status:"todo"}`。重复 SHA 返回 `{id, duplicate:true}`，不覆盖旧框或完成状态。积累失败仍返回检测结果，并带 collect_error。`POST /api/config` 保存开关，默认 false；推理不持有写锁，等待锁后重查开关，已关闭时不写。

### 内容评测与复核

`omrs/trainaudit.py` 读取外部 audits 目录，不加载训练框架。`GET /api/trainpanel/audits` 返回最近至多200份评测摘要；`GET /api/trainpanel/audit?id=&role=&verdict=&review=&case=&offset=&limit=` 返回筛选分页案例（默认30、最多100），review 为 pending/reviewed/disagreed。`GET /api/trainpanel/audit-image?id=&resource=` 仅返回 audit.json 登记资源，拒绝路径穿越、越界符号链接及超过30MB图片；缓存 private/no-store。

`GET /api/trainpanel/reviews?id=&case=` 返回最近100次追加历史。`POST /api/trainpanel/review` 接收 `{audit,case,revision,action,verdict?,note?}`；action 为 agree/correct/uncertain，verdict 为 usable/needs_adjustment/unusable/uncertain。说明最多2000字、请求最多16KB；成功返回 revision/verdict，版本冲突409、参数非法400。HTTP来源固定user，不能伪装执行者。沿用登录、同源校验与全局写锁，SQLite再用BEGIN IMMEDIATE保证跨进程revision检查与插入原子性。GET不建库，不调用付费模型。

评测案例损坏以独立error显示，SQLite读取/保存错误返回400；单条详情附最近调用尝试摘要。待复核筛选指尚无用户结论，执行者已看过仍可由用户复核；同一案例用户结论优先。

评测摘要附prompt_versions；详情支持prompt_version筛选，用于同一次历史导入内对比v1和v2。汇总指标始终标示整份实验，筛选仅改变案例列表。

评测整图通过统计要求调用状态为done/cached；调用错误即使被人工标记内容可用也仍计失败。复核内容与调用状态分别保留。

### 受管检测服务

`GET /api/trainpanel/manager` 返回 supported、revision、operation、实际 online 健康身份、selected 配置身份、matches、previous、models（至多100个完整导出实验及匹配阈值的内容评测摘要）、errors、最近20次 history。候选含 `independent_reviewed`、`independent_passed`、`independent_status`（passed/failed/incomplete/missing）；未登记实例返回 supported=false 与说明。此 GET 只读，不触发中断操作恢复；主服务在监听前同步调用恢复，失败时其他页面仍可使用。

`POST /api/trainpanel/control` 请求最多4096字节，接收 `{action,revision,request_id,model_id?,sha256?,conf?,imgsz?,confirm_unverified?}`。action 为 start/stop/restart/activate/rollback；request_id 为32位小写十六进制，activate 必须匹配当前登记候选身份与参数。独立内容验收缺失、未完成或未通过时，activate 须显式传 `confirm_unverified:true`，操作快照记录验收状态与确认。返回202及 operation，异步结果从 manager 查询；相同请求ID与内容复用记录，变更内容/旧revision/其他操作繁忙返回409，非法参数或未登记返回400。后台工作持有文件锁，长操作不占全局HTTP写锁。登录和写请求来源保护与现有接口一致。

控制操作的 `actor` 由服务端按认证结果生成，仅记 `auth_mode`（本机、局域网豁免或 PIN 会话）、会话 ID 与可信来源 IP，不接受客户端自报身份，也不记录 PIN 或 Cookie。受管 `local_http` 检测请求前后核对登记指针和实际健康身份；不一致时拒绝框选结果。

应用模型先限额预检，再原子修改受管指针、重启与核验健康SHA/输入/阈值；失败恢复原模型及原在线/离线状态，回退失败单独显示。正常启停不改变模型。离线启动提示优先显示已登记unit；手动模式使用本机配置端口，远程地址提示在服务所在机器启动。

## MCP 分析与报告扩展

独立 MCP get_analytics 的科目/分类过滤发生在聚合前，日期只筛选练习；同名分类按科目分别统计。list_reports/get_report 查询元数据与分页 HTML 源码；create_report(name, html, request_id) 新建，需 report:create，2 MiB 上限，同编号内容冲突返回 request_conflict。回执和恢复见 AI/mcp.md；Web 报告仍在原沙箱预览。

## MCP 草稿修订

update_draft(draft_id, expected_revision, request_id, fields?, block_patches?, cause_statement?) 同时需要 omrs:read/draft:update；返回 draft_id/revision/wrote/suggestions/reused。人工保护整次不写；重复请求返回原回执，版本/状态冲突有稳定错误码。只修订待审核草稿，不改变 Web 审核或内置助手的归属规则。

请求触及任一受保护字段/块，即使内容未变也整次拒绝写入；错因修改和清空均需 cause_statement，实际修改标 client_asserted。领域稳定错误在 `omrs/errors.py`，普通 Web/CLI 启动不加载可选 MCP SDK。

## 展示板并发契约

GET /api/boards 返回 catalog_revision，各板摘要含 revision，详情亦含目录版本。全部已有板修改、引用增删、纸面记录/重置携带 expected_revision；目录变化同时携带 expected_catalog_revision。缺失版本返回 400，过期返回 409 revision_conflict；检查和读改写在同一领域锁。响应返回当前 catalog_revision，客户端仅采用已成功写入的版本。

## MCP 权限编辑与确认接口

POST /api/mcp/keys/update 只接受 key_id/scopes，编辑有效密钥权限，失效不可复活。GET /api/mcp/operations/detail?operation_id=编号 返回 operation 含工具、影响、生命周期和结果；POST /api/mcp/operations/decide 只接受 operation_id/decision（confirm 或 reject）。所有端点沿用 Web 会话、来源校验、禁止缓存及 MCP 凭据拒绝；读不到返回 not_found，存储故障503。确认变化返回 operation.status=conflict 和稳定 error_code，重复决定返回现有状态。

### MCP 展示板快照下载

GET /api/mcp/exports/download?export_id=编号 仅Web授权可用，返回text/html附件，中文安全文件名、Cache-Control:no-store、nosniff。编号非法/不存在404，到期410及export_expired；文件损坏拒绝下载。完整HTML不出现在工具响应或运行记录中。

## 上传引用入口

`POST /api/inbox/upload-refs`、`POST /api/annotate/upload-refs` 接收 `{images:[{upload_ref,filename}]}`，按所属用途验证已完成上传并逐图入库。元数据正文使用 `http_json_mib`，默认2MiB；总图片字节放在分块暂存文件，不随JSON再次传输。原 `/api/inbox/upload`、`/api/annotate/upload` 仍支持multipart及引用JSON。

## AI 审核中心

GET `/api/ai-review/items`、`/api/ai-review/detail`、`/api/ai-review/counts` 为受保护的只读业务视图；POST `/api/ai-review/update` 与 `/api/ai-review/decide` 使用 Web 身份和同源保护。版本、分页、状态与错误完整契约见 `AI/ai-review.md`；MCP Key 不能调用批准接口。
