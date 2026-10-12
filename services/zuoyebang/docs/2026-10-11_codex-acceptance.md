# 2026-10-11 独立服务续做验收

执行者：Codex；运行模式：本机完整模式。

用户本轮原话：「验收检查代码,然后继续任务」。此前需求为设置页面可选本地/外部作业帮服务、配置地址与密钥、面板生成密钥和请求历史记录性质/IP。独立服务与 OMRS 接入分开验收；本日志只记录独立服务目录内的修改。

## 开工现状与范围

服务没有自己的 Git 元数据，不初始化或提交。保留中断前实现和历史证据；针对业务契约通读 server、config、security、storage、accounts、search、transport、vendor 三模块、面板以及测试。候选源码摘要基线记录在父任务 scratch 的 `codex-acceptance/gateway/before-sha256.json`，修改文件原件在同目录 `before/`。

初始 48 项 Python 测试本轮重新通过。README 引用的 `docs/verification.md` 和 `vendor-manifest.json` 缺失，实际补齐，文档中的验证结论按本轮执行证据维护。

## 缺陷、失败见证与修复

1. 检查/刷新账号操作持有旧二维码快照，网络返回后无条件写回，能把并发取消后的流程从 cancelled 恢复为 pending，并重新保存二维码挑战。新增真实 HTTP 并发回归，verify/refresh 两个子场景先失败；`accounts.py` 仅在二维码操作时发布二维码文件，账号操作只发布账号与观察摘要。
2. HTTP 工作线程满时，审计存储异常穿出 `process_request`，控制台输出底层异常且 socket 无响应。新增真实 HTTP 回归先出现 RemoteDisconnected；`server.py` 在此路径同样返回稳定 503/audit_unavailable，不输出异常原文。
3. 官方在响应前直接断开连接，真实本地上游复现搜题返回 500/internal_error、账号检查误报 protocol。vendor direct/account 把网络 OSError 归为 network，稳定返回 502；两次请求共两次上游尝试，没有自动重试，观察仍为 unknown，未判账号失效。
4. 二维码进入成功或取消终态，`renderQr` 禁用按钮后，`run` 的 finally 又启用刚点击的按钮。真实 Chromium 新断言先失败；面板最终启用状态取决于 flow 是否仍存在，终态不能再次检查或取消。
5. 全量回归曾暴露 CLI 测试竞争：TextIO.readline 提前缓存监听行，select 只看到第一行后不再可读。服务正常输出，测试误判未启动；改用 select + os.read 按完整字节行消费，保留所有健康与 SIGTERM 断言，没有放宽等待条件或降低业务断言。
6. 可信代理转发头的首项为空时，原代码按真值跳过 XFF 解析；空头或首头为空的重复头被当成本机请求。新增真实 HTTP 两个子场景先得到 200；`security.py` 按头是否存在进入严格解析，两种情况均返回 400/proxy_invalid。

失败记录：`acceptance-2026-10-11/red-acceptance.log`（2 项测试：2 个失败子场景、1 个错误）、`red-network.log`（1 项测试：2 个失败子场景）、`red-proxy.log`（1 项测试：2 个失败子场景）、`red-browser.log`（1 项失败），以及 `regression-cli-read-failure.log`（51 项中 1 项失败）。这些文件包含明确合成的失败数据，不含真实 Key、管理员秘密或官方凭据。

## 影响文件

- 业务代码：`zyb_gateway/accounts.py`、`server.py`、`security.py`、`vendor/direct.py`、`vendor/account.py`、`assets/panel.js`。
- 测试：新增 `tests/test_acceptance.py`；更新 `tests/browser_acceptance.py` 的终态断言与可配置证据目录，更新 `tests/test_cli.py` 的子进程读取。
- 文档与来源：README、安全/API/vendor 文档、本文、`verification.md`、`vendor-manifest.json`；同步本轮截图、脱敏浏览器元数据和 `acceptance-2026-10-11/` 验证输出。

## 验证结果

最终 52 项 Python 测试全绿，专项新回归 4 项、CLI 4 项全绿。真实 Chromium 面板 1 项全绿，桌面和 390px 已截图并检查；共享浏览器保留，仅关闭自己的 context。node 语法检查退出码 0。当前源码离线重建安装后，在源码目录外独立 CLI 随机端口启动，4 项真实 HTTP 冒烟全绿，自己的进程正常 SIGTERM 退出。完整命令与验证边界见 `verification.md`。

## 未执行与下一步

真实官方账号/扫码、生产 HTTPS 反代及部署没有执行；未触碰 OMRS 真实题库或凭据。独立服务可供 OMRS 候选继续联调；OMRS 接入端需独立完成保存配置、连接测试、原图搜题、候选渲染、识别/核对和临时题库入库的浏览器主路径。未提交、推送或合入生产。

开工前 `docs/tmpsretf1_c/private/` 已存在遗留私有文件，本轮未读取/删除。交付源码包必须排除 `.venv/`、缓存、build/dist、所有临时测试目录、`.state/` 与任何私有数据；不能直接无过滤打包整目录。此次新测试自己的临时数据均已删除。
