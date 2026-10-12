# 独立服务验收

执行者：Codex；运行模式：本机完整模式。日期：2026-10-11。此次验收使用当前源码重新运行，不复用中断前的通过结论。

## 已实际执行

| 检查 | 命令 | 结果与证据 |
|---|---|---|
| 全部 Python 测试 | `.venv/bin/python -m unittest discover -s tests -t . -v` | 52 项通过；`acceptance-2026-10-11/green-final.log` |
| 新验收回归 | `.venv/bin/python -m unittest tests.test_acceptance -v` | 4 项通过，包含检查/刷新并发取消、审计失败、真实上游 socket 断开、可信代理空/重复 XFF；`green-acceptance.log` |
| CLI 专项 | `.venv/bin/python -m unittest tests.test_cli -v` | 4 项通过；`green-cli.log` |
| 浏览器面板 | `ZYB_TEST_CDP_URL=http://127.0.0.1:9222 .venv/bin/python tests/browser_acceptance.py` | 1 项真实 Chromium 用例通过；`green-browser.log`、`browser-evidence.json` |
| JS 语法 | `node --check zyb_gateway/assets/panel.js` | 退出码 0；`node-check.json` |
| 当前源码本地安装 | `.venv/bin/python -m pip install --no-index --no-deps --no-build-isolation .` | 退出码 0；`package-install.log` |
| 源码目录外安装包 | `.venv/bin/python tests/package_smoke.py` | 4 项 HTTP 断言通过；`package-smoke.json`，自己的子进程 SIGTERM 后退出码 0 |
| vendor 字节来源 | 从 OMRS 指定 Git 基线逐文件读取并计算 SHA-256 | 3 个模块；根目录 `vendor-manifest.json` |

本轮完整日志在 `docs/acceptance-2026-10-11/`，各行只写实际执行过的验证。浏览器截图在 `docs/browser-login.png`、`docs/browser-desktop.png`、`docs/browser-mobile.png`；只显示脱敏摘要与合成测试账号，完整 Key 展示后即关闭再截图。

本轮安装使用项目已有 pip 缓存中的 setuptools 84.0.0 / wheel 0.48.0，先通过 `--no-index --find-links .venv/codex-wheel-cache` 安装构建工具，再离线重建当前包。首次无构建工具的 `--no-build-isolation` 尝试失败，没有据此宣称安装成功。

## 测试边界

测试使用随机高端口、临时私有目录和真实 HTTP/SQLite。非 loopback 来源通过本机容器的实际网络地址请求，覆盖关闭/开启外部开关、有效/无效/吊销 Key、伪造 XFF、可信代理和来源/IP 审计。静态状态读取不联系官方；原图 PNG/JPEG/WebP 字节通过 multipart 到本地合成上游，不重编码。

浏览器复用现有 CDP，仅创建并关闭本测试独立 context，未关闭共享 Chrome。主路径覆盖管理员登录/退出、Key 一次展示/复制/刷新后无回显/吊销、恶意名称转义、设备导入、账号检查/刷新、合成官方扫码确认/取消与终态按钮、外部开关、来源筛选、390px 页面无横向溢出及零 pageerror。

测试使用的设备、账号、扫码挑战均为明确标注的 SYNTHETIC。没有读取真实 OMRS 凭据或错题，没有访问生产端口，没有真实作业帮请求，没有模型请求，没有部署、systemd、Nginx、防火墙、提交或推送。单测/浏览器/安装包创建的私有目录和自己的服务均已清理。

## 未执行

- 真实作业帮账号、官方扫码与签名有效期验证：没有授权使用真实账号；官方边界用合成响应替代，不能据此声称官方兼容性实测成功。
- 公网 HTTPS 反代、安全 Cookie 的真实域名联调和生产上线：此次范围是源码验收，未修改外部部署状态。
- OMRS 上传、渲染、识别及幂等入库：由 OMRS 接入任务独立验证，不计入本服务的 52 项测试。

完整源码验收通过不等于生产已上线。网关默认最大响应为 24 MiB；调用者若设更小读取预算，可能拒绝超过该预算的响应，应按双方明确的协议上限配置。
