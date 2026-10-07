# 2026-10-07 MCP HTTPS 原图下载修复

## 范围与授权

用户原话：「这是什么情况?调查一下OMRS MCP 不需要委派子代理」，随后「修复,然后版本号+0.0.1,部署生产,提交GitHub」。本任务由 Hermes 完整模式直接执行，没有委派。

基线 main `ddf9a69b3c07a6dca0a3162bea1a2858fc89ff93`；开工前工作区干净。旧生产有效 release 为 `9785fa4` / v2.3.3；Git 工作区不是运行源码根。仅修复 MCP URL 图片下载路径，版本升至 v2.3.4；不更改 OMR 扫描基座、业务模型、Key 权限、PIN、端口、Nginx 或 Tunnel 配置。

## 原因与行为

截图对应的两次带图创建失败，之后纯文字创建成功；原文字草稿 `DR-20261007-da1ead` 的图片关联数为零，不是前端漏显示。附件摘要表明走 URL 下载而非 Base64 原字节上传。原下载 URL 未保留，不能声称已重放用户的原始签名附件。

`_PinnedHTTPSConnection.connect` 在固定公共 IP 的 TCP 连接后误读 `self._host`。标准库 HTTPSConnection 使用 `self.host`，因此在 TLS 握手前抛 AttributeError，并被工具层转为 `internal_error`。只将 SNI 的主机属性更正为 `self.host`；公共地址校验、固定 IP、证书验证、重定向禁用、限时限大小和人工审核边界不变。

历史纯文字草稿不会自动补图；本次不写入或重建该草稿，避免重复录题。`update_draft` 也不接受新增附件。

## 影响文件

- `omrs/mcp/server.py`：修正原主机名 TLS SNI 属性。
- `tests/test_mcp_download_connection.py`：只替换 DNS/socket/TLS I/O，保留真实 HTTPS 连接方法、HTTP 解析及工具/草稿保存；覆盖固定 IP/SNI、默认 TLS 验证、证书拒绝、失败不建草稿和完整原字节。
- `omrs/version.py`、`omrs_dashboard.html`、根 `README.md`、`AI/README.md`、`AI/changelog.md`：同步 v2.3.4。
- `AI/mcp.md` 与 `AI/plans/mcp-integration/progress.md`：当前下载契约、验证范围和本批进度；`AI/frontend/shell.md` 取消过期重复版本文字，改为核源码与接口；本日志及自动生成索引记录实际发布。

## 已执行验证

- 在未修改的 v2.3.3 release 上加载新四项回归：默认 TLS 配置通过，两个真实连接用例因 `_host` 属性错误失败，URL 工具创建因 `internal_error` 失败；明确证明覆盖原故障。补充失败不建草稿后，新代码五项全部通过，无跳过。
- 首轮全量 unittest 817 项通过；补充第五项后的818项复跑因未带 CDP 环境变量启动独立浏览器，两项出现 Page crashed/Target crashed，未记为通过；已带 `OMRS_TEST_CDP_URL` 重跑完整测试，结果将在发布收尾登记。Node 449 项、浏览器组件、展示板与 A4 冒烟、UI纪律及对比度均退出 0。
- 旧 venv 缺 pytest，未把缺依赖算作通过；使用本机已安装 pytest 的 Python 实跑 `tests/test_report_export.py`，7 项通过，没有修改生产依赖。
- 官方 SDK/MCP 浏览器 `tests/e2e/mcp.py`：39/39。原图顺序、PNG/JPEG/GIF 原字节、草稿审核、Key 生命周期和响应式界面通过。
- 隔离真实 SDK 服务调用 `create_draft`，由下载器实际访问 Python 官网 HTTPS PNG：45,187 字节，SHA256 `ea0e73137c1c8561e91241771e3c81e5b3e8f5ab2cbfdad1a00d8eea524815fa`；保存原字节相等、重复请求只有一份 review 草稿、Ledger 提交数不变。不是 ChatGPT 原生附件端到端验收。
- GitHub 公共 PNG 首次直接下载成功，后续两次外网读取超时；改用 Python 官网成功，不调整下载器超时或网络配置，也未伪造下载结果。
- 相对 `ddf9a69` 的录入页浅/深、桌面/手机视觉比较四对：桌面两对各 0.002% 为侧栏版本文字，手机无差异；无页面脚本错误。

## 扩展门禁与既有失败

额外运行全仓浏览器 E2E，首段 18 个脚本中 4 个失败。逐项在未改动的生产 v2.3.3 源码上、临时 Vault 和随机端口复跑，同四个脚本仍失败：

- `ai_review.py` 等待 `.drf-id` 超时。
- `assistant.py` 58/59，唯一失败为 favicon.ico 的既有 404。
- `audit_identity.py` 等待题目预览 HTTP response 超时。
- `drafts.py` 的已丢弃草稿直达导航断言失败；新版首次还出现两个未在旧版复跑失败的队列时序断言，两版业务/测试源码未改。

这些是已重现的基线失败/时序波动，不宣称全仓 E2E 全绿，也不扩展本次修改范围。中断的首段没有伪记为完整运行；剩余 E2E 与升级兼容用独立受管任务续跑，结果在收尾补充。没有访问生产题库执行浏览器测试。

## 发布状态

本次代码、版本及专项隔离验证完成；生产切换和 GitHub 推送尚未执行。按授权继续：精确提交归档 → 新 release 复验 → 停服冻结并完整备份/解包验证 → 原子切换主服务 → live API、MCP/HTTPS 与数据核验 → 记录并推送。仅回滚代码，不用旧 Vault 覆盖当前事实。
