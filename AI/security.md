# 请求安全与远端 PIN

> **速查**
> - 职责：本机免 PIN、远端 PIN 会话、来源校验、报告隔离与题目路径边界
> - 入口：`omrs/security.py`、`omrs/server.py`、`omrs/path_safety.py`
> - 不变量：免 PIN 只看 TCP 对端地址，代理请求一律须 PIN；会话只保存在进程内存中
> - 必跑测试：`tests/test_security.py`、`tests/app/settings.test.mjs`
> - 相关：`AI/api.md`、`AI/frontend/settings.md`

> 对应源文件：`omrs/security.py`、`omrs/server.py`、`omrs/path_safety.py`。

## 1. 访问边界

本机通过 `127.0.0.1`、`::1` 或 `localhost` 直连时免 PIN。`lan_pin_exempt_cidrs` 可显式指定直连免 PIN 的私有局域网 CIDR；默认空列表。豁免仅看 TCP 对端地址，不适用于 Nginx 等代理请求。其他请求在页面、静态资源和 API 分派前验证会话；未登录的页面请求跳转 `/login`，API 返回 401。启用 `allow_external` 前须设置 4–12 位数字 PIN 或配置免 PIN 网段；没有 PIN 时，非豁免远端仍拒绝访问。本机设置页可补设。`GET /api/auth/session` 与登录页是未登录时可访问的入口。

服务端从 TCP 连接取得地址；只有代理的连接地址在 `OMRS_TRUSTED_PROXIES` 中，才读取其覆写的 `X-Real-IP` 和 `X-Forwarded-Proto`。默认可信代理地址为 `127.0.0.1,::1`，可用逗号分隔的环境变量覆盖。代理必须覆写 `Host`、客户端 IP 和协议头；缺少有效代理头时，非本机 Host 按远端处理。免 PIN 网段只允许 RFC1918 IPv4 与 IPv6 ULA，拒绝公网与不规范 CIDR。Nginx 配置见根 `README.md`。

## 2. PIN 与会话

PIN 的随机盐和 PBKDF2-SHA256 哈希存于 `错题/.omrs/auth.json`，不通过配置 API 返回。登录每个客户端 IP 在 15 分钟内最多失败 5 次。设置页远端修改 PIN 或空闲时间时校验的当前 PIN 与登录共用同一失败计数。成功后服务端持有随机会话令牌的哈希，浏览器仅保存 `HttpOnly; SameSite=Strict; Path=/` Cookie；HTTPS 时追加 `Secure`。重启、退出、更换或停用 PIN 会使会话失效；只改空闲时间不注销会话，新上限在下一次请求时生效。尚未设置 PIN 时，免 PIN 网段设备可直接设置首个 PIN，已设置后远端修改一律须验证当前 PIN。登录页的 `next` 参数按 `new URL()` 解析，只接受同源地址，其余回到 `/`。

默认空闲时间为 30 分钟，可在设置页选择 5–240 分钟；绝对最长时间为 12 小时。后台轮询不续期，桌面和手机页只在点击、键盘、触摸、滚轮或滚动时按分钟节流调用 `POST /api/auth/activity`；监听挂在 `document` 的捕获阶段，页面内部滚动容器里的滚动同样计入。手机页 `/m` 遇到 401 时跳转 `/login?next=/m`，并停止处理剩余上传。框选标注页 `/annotate` 与主页同样经 `_authorize`（未登录的远端跳 `/login?next=/annotate`），页内请求 401 时由 `core/api` 跳登录页。远端 HTTP 登录成功后提示传输风险，同一会话确认一次；使用 HTTPS 不提示。停用 PIN 仅可在关闭 `allow_external` 后由本机操作。

## 3. 请求与报告

所有 POST 在读取请求体前检查 `Sec-Fetch-Site` 和 `Origin`；跨站浏览器请求返回 403。无这些浏览器头的本地 CLI 请求仍可使用；远端请求还需有效会话。会写投影的扫描入口是 `POST /api/scan`，GET 返回 405。`GET /api/config` 不回显 `ai_api_key`，只给出 `ai_api_key_configured`。`GET /api/auth/session` 的 `instance_id` 与 `GET /api/status` 的 `listen_external` 是公开的运行元数据，不含秘密。

报告保存原始 HTML；浏览时加 `Content-Security-Policy: sandbox allow-scripts allow-downloads allow-popups`，脚本在不含 OMRS 同源权限的环境中运行。服务端仅给报告中的静态 `/api/image?name=` 附件文件名加签名链接，签名限单张图片、当前会话和会话时限；原始报告文件不改。远端题图响应禁止浏览器缓存，本机题图维持原缓存策略。源码包、备份和完整 Vault 路径仅供本机、显式豁免的直连局域网设备或已登录远端访问。

## 4. 题目文件路径

创建与移动题目时，科目和分类必须是单个非空目录名，不接受绝对路径、路径分隔符、`.`、`..` 或盘符路径。目标和来源文件均按真实路径确认留在 `错题/` 内，符号链接若指向根目录外也会被拒绝。题图加载失败时由浏览器事件监听器创建文字节点显示文件名，不使用内联脚本。

## 5. AI 助手的权限边界

助手沿用现有访问控制：远端请求同样要 PIN 会话，远端用户与本机用户权限相同。模型能做的事由服务端注册的工具决定，删除、设置、PIN、备份恢复、重启、源码导出没有工具。需确认的写入只在界面 `POST /api/agent/confirm` 带上与参数绑定的确认码时执行，模型无法自行确认；码 10 分钟过期。题库内容（题目、答案、错因、OCR 文字）进入模型上下文时被当作数据，但防提示注入的主防线是上面这两条，而不是提示词。密钥只存在 `config.json`，接口不回显；模型请求日志默认关闭。细节见 `AI/agent.md` §3。

确认入库工具 `commit_draft` 仅在 draft_mode=confirm 时注册，参数包含 draft_id 和 revision；预览与执行都重读配置、对话归属、review 状态和版本。确认期间被编辑或丢弃的草稿不能用旧许可写入。人工审核入口与工具共享草稿领域函数，HTTP 不接受伪造的 actor、uid 或来源。

草稿框选、提取、训练开关与清理继续走登录/同源及现有写锁；客户端不能指定任意文件或跨草稿任务。图级共享训练开关会改变关联草稿 revision，使等待中的旧确认失效。草稿清理只处理已到保留期的丢弃候选，聊天、活动/已入库草稿和训练引用均保护原图；训练登记不授予再次创建题目的权限。
