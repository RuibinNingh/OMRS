# 作业帮搜题与保真录入

> **速查**
> - 职责：设备会话、扫码账号、搜题候选、后端完整长图、AI 保真提取与幂等创建
> - 入口：`omrs/zuoyebang/`、`omrs/http/zuoyebang.py`；页面见 `AI/frontend/create.md`
> - 不变量：题干答案按候选绑定；题目/答案各一张1080像素完整图；失败保留来源；凭据不进入响应或日志
> - 必跑测试：`tests/test_zuoyebang.py`、`tests/app/create-zyb.test.mjs`、`tests/e2e/zuoyebang.py`
> - 相关：`AI/api.md`、`AI/security.md`、`AI/data/storage.md`、`AI/inbox.md`

## 1. 设备与账号

首次使用在「录入题目 → 作业帮」导入已验收的 direct-session.json，提供已登记设备字段、固定搜题地址和签名种子；源码包不含该私有文件，不能从空账号伪造设备身份。导入限制256KiB，校验后原子保存，不视为在线核对成功。扫码确认使用官方账号接口，二维码由本地 Segno 生成；5分钟仅为本地二维码流程期限，不代表账号 TTL。同一 Vault 共用一份账号。

检查账号调用 userinfo；刷新账号调用 relogin 并重新核对。网络操作只使用临时私有快照，发布时核对 Vault 世代、会话指纹和扫码流程，迟到授权不能覆盖新会话或已取消流程。普通搜题和账号请求不依赖 ADB、APK 或原生库；没有设备初始化/签名种子自助刷新入口，签名失效时重新导入已更新的设备会话。

`observations.json` 分别保存 account/signing 的最后成功、首次确认失效、有效时间区间、恢复结果和最近100事件；`session-events.jsonl` 追加全部脱敏观察。登录提醒或无有效用户记账号失效，errNo=6 只记签名失效，网络故障不改变有效状态。没有官方 TTL，只能确定最后成功到首次确认失效的区间。日志白名单仅含操作、类别、整数错误码、时刻和恢复标志，不包含凭据、Cookie、签名或上游原文。

## 2. 搜题与后端渲染

图片以 zuoyebang 用途的既有分块上传引用发送，不重编码原件；仅 JPG/PNG/WebP、不超过8MiB且不超过4000万像素，完成上传时用 Pillow 验证完整解码。用途不能借用于普通题目创建；旧上传用途仍仅支持 PNG/JPEG/GIF。解码后的结果按照片位置和显式候选保存，不合并相似题树；题干和对应答案一起选择。接口返回摘要，原始上游内容留在独立记录。

HTMLParser 白名单保留文字、列表、表格、上下标和图片，移除可执行内容与任意 CSS。附图只允许作业帮/百度 CDN 域族，每次跳转复核域名和公网 IP，实际连接固定已校验 IP，下载不携带账号 Cookie。图片验证后内联原字节；Chromium 拦截器只读取 OMRS 本地字体和 KaTeX，不访问外网、Vault或任意文件。正文中的局部数学定界符由 KaTeX 转换；跨 HTML 节点拆开的定界符不自动合并。

SVG、MathML、canvas和音视频等不能按当前白名单保真渲染的视觉内容会明确报错并保留来源，不静默删除必要图形。搜题响应结构或解码格式异常记 protocol，不当作账号或签名过期。

真实 Chromium deviceScaleFactor=1，题干与答案各一张宽1080的 PNG，高度按全文。答案不分块、分页或裁断。等待字体、公式和所有图片 decode，校验 PNG 尺寸与 SHA256。缺图、公式错误、横向超出1080均整体失败并保留原候选。单附图12MiB、附图总量80MiB、单输出1亿像素是物理资源预算，超限报错，不缩放或截断。纸面固定白底，前端主题只改变外框；HTML 预览用文本显示，内联图片字节以提示替代。

## 3. 后台作业与 AI

search/render/extract 在守护线程执行，每个 Vault 最多同时两个任务，同一来源去重。开始捕获世代，网络与浏览器期间不持磁盘租约或业务写锁，快照读写与发布取短租约/写锁。作业状态持久化，并保存内部开始世代；重启或同进程整库恢复后，旧 running 记录只读显示中断，不永远等待，也不自动重放网络调用。

AI 复用 extract_region、judge=True 和现有识别配置；每个角色一次读取完整图。完整转录文字/公式时保存文本，否则保留整图，不补写解答。两区独立保存，重试只处理失败项；分类只补科目、分类、难度和知识点，不写标记。模型 finish_reason=length/max_tokens 时拒绝当作完整转录。供应商自身的图像和输出限额仍适用，失败可按整图入库。

## 4. 创建与恢复

用户核对后主动创建；客户端提交 render_id、人工表单和两区 mode/text。图片由后端读取不可变 PNG，不接受外部 HTML/路径。空答案使用 none，非空答案不可隐式丢弃，文本要求非空。

首次提交冻结内容摘要、UID/question_id/路径和日期，复用 CreationOperation 产物校验与 Ledger op_results 回执；其它录入入口跳过作业帮预留 UID。中断重试用同一身份，已有回执直接复用；不同内容重试返回409并保留首次内容，浏览器可从记录恢复。正式提交为 question.create，actor=zuoyebang，内部来源 _inbox.zuoyebang_render_id 关联渲染。

工作区扫描跳过尚未入账的作业帮预留身份，避免已写出的中间文件被当作外部新增题目。恢复由用户从原渲染记录重试，不在启动时重放网络或自动创建。全库备份包含这份私有目录，恢复世代使在途任务及旧上传引用失效。

## 5. HTTP 契约

全部沿用 OMRS Web 鉴权、POST 同源校验及 MCP Key 边界，不返回第三方凭据。

| 方法与路径 | 请求与响应 |
|---|---|
| `GET /api/zuoyebang/status` | 配置/账号凭据是否存在、脱敏观察；不主动联网 |
| `POST /api/zuoyebang/profile` | `{profile}`；导入并使旧二维码失效，返回状态摘要 |
| `POST /api/zuoyebang/account` | `{operation,flow_id?}`；verify/refresh/qr_start/qr_poll/qr_cancel，返回 account 摘要；qr_start 另含本地二维码 |
| `POST /api/zuoyebang/jobs` | `{type:"search",image:{upload_ref},grade?:0..12}` / `{type:"render",search_id,candidate_index}` / `{type:"extract",render_id,force?:boolean}`，返回 job |
| `GET /api/zuoyebang/job` | `?id=job-…`；running/done/failed，含 result 或 error/code |
| `GET /api/zuoyebang/record` | `?id=search-…或render-…`；候选摘要或渲染/images/extraction/创建预留和回执，不返回 source |
| `GET /api/zuoyebang/history` | 最近30份渲染的状态、尺寸、摘要与时间 |
| `GET /api/zuoyebang/image` | `?id=render-…&role=question或answer`；核对SHA后返回 PNG，private/no-store |
| `POST /api/zuoyebang/commit` | `{render_id,form:{subject,category,difficulty,related_tags,labels,cause},sections:{question:{mode,text},answer:{mode,text}}}`；返回身份、图片名、commit_id、reused |

非法输入400；会话/流程/预留过时409；并发预算429；依赖缺失503；上游故障502。后台渲染和识别错误经 job 报告，轮询HTTP本身仍200，原内容保留。
