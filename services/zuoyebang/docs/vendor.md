# vendor 协议来源与改动

`zyb_gateway/vendor/direct.py`、`account.py`、`qr.py` 源于本机公开 OMRS 候选的 `omrs/zuoyebang/`，基线 `e614f3a6f625f8385714aac4171870459a537c15`。只复制这三个协议模块；不复制 session/store/Vault、题库、.omrs 或任何真实会话。没有运行时路径拼接、import omrs、旧仓库 sys.path 或环境依赖。

保留官方固定端点、字段、签名/RC4/gzip/base64 解码、multipart 原图以及官方扫码/账号核对逻辑；网关状态包装、私有快照、权限、预算、审计由本项目独立实现。

明确差异：
- direct/account 的响应读取改接 `zyb_gateway.transport.bounded_read`：Content-Length 预检、累计 wire 字节上限、总读取期限；关闭环境代理和 redirects 的原行为保留。
- DirectClient 增加可由网关注入的 timeout；AccountClient.request 改为实例方法，保留协议参数，实例 timeout 默认 30 秒。
- direct 解码多页 gzip 增加 24 MiB **累计**预算；官方成功信封里的登录提醒按 login_required 拒绝，不误记账号有效。
- direct/account 官方连接或读取中的 OSError（包括连接直接断开）归为 network，交由网关稳定脱敏为 502，不重试。
- direct补齐answers.locs／angles的主Key、非gzip解码；最多200项，计入累计预算，单项失败留空。当前OMRS协议来源实现同步该规则，manifest保留初始来源commit／SHA并更新vendor交付SHA。
- qr.py 原样保留本地 Segno 二维码逻辑；只在真实官方 qr_create 返回挑战后生成，不伪造设备或账号。

源文件/交付文件哈希见 `vendor-manifest.json`，由工具从真实字节生成。公开源码根未发现独立 LICENSE；本轮为用户授权的本地跨项目复用，不进行公共再分发。若未来公开发布，应先核实协议来源与上游授权，不能自行给 vendor 加造假的许可证。
