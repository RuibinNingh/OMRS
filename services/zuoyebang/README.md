# 作业帮独立网关

标准库 HTTP + SQLite、无构建中文暗色面板。源码位于OMRS同一仓库的 `services/zuoyebang/`，与主应用同版本发布。网关独立持有设备会话、账号/扫码、签名/解码、调用密钥与脱敏审计，不导入 OMRS，也不读取 OMRS 题库或旧凭据。

## 安装与前台运行

需要 Python 3.10+（本次使用 3.13）。可使用OMRS根目录的虚拟环境；单独使用时也可在本目录创建独立环境：

```bash
cd /path/to/OMRS/services/zuoyebang
python3 -m venv .venv
PIP_CACHE_DIR="$PWD/.pip-cache" .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m zyb_gateway init --data-dir "$PWD/.state"
.venv/bin/python -m zyb_gateway serve --data-dir "$PWD/.state"
```

默认面板 `http://127.0.0.1:8745/`。控制台**只显示**管理员初始密码文件位置，不显示秘密。使用服务器本机可信编辑器读取 `.state/admin-secret.txt`，登录后可移走/删除该明文初始文件；不要粘贴到聊天、截图或日志。数据库只保存加盐 scrypt 摘要，删除初始文件不影响登录；重新启动不会重置密码。忘记密码时执行下列命令，会重新生成受限文件并注销全部管理会话：

```bash
.venv/bin/python -m zyb_gateway rotate-admin --data-dir "$PWD/.state"
```

Ctrl+C / SIGTERM 正常停止。可更改本机端口 `--port 8746`；`--port 0` 用于随机端口隔离验收。`--bind ::1` 支持 IPv6 本机。完整选项：`.venv/bin/python -m zyb_gateway serve --help`。可选安装包入口：在独立 venv 执行 `pip install .` 后使用 `zuoyebang-gateway`。

## 首次使用

1. 登录独立管理员；**调用密钥不能登录或管理面板**。
2. “账户与会话”导入**真实已登记设备**的 direct-session.json（最多 256 KiB）。不从空账号伪造设备；导入不等于官方验证成功。本服务不提供设备初始化、签名种子自助获取或 ADB 桥接。
3. 已有设备可导入账号凭据，或“创建登录二维码”后使用官方作业帮 App 扫码/确认，再点“检查扫码结果”。可取消，5 分钟是本地扫码流程期限，不是官方账号 TTL。
4. 主动“检查账号”/“刷新账号”；只读状态不联系官方。网络/协议错误不会被误报为账号失效。
5. “调用密钥”填写名称、生成并立即复制。完整 Key **只在创建响应和当次页面展示一次**；刷新后仅显示 ID、短前缀、指纹、时间和有效/吊销状态。吊销立即生效。
6. 在 OMRS 的作业帮服务设置选择本地/外部模式并填地址与 Key。两种模式都走相同的已鉴权网关协议；管理 URL 为 `/`，不带 Key。

本机调用也必须使用 Bearer Key。API 文档见 [docs/api.md](docs/api.md)，安全与默认预算见 [docs/security.md](docs/security.md)。

## 外部访问与反向代理

默认 `allow_external=false`，默认监听 `127.0.0.1`。应用开关和监听地址互相独立：面板开启外部访问**不会**修改防火墙、Nginx 或监听地址；误监听 `0.0.0.0` 时关闭开关仍拒绝外部 API/管理请求。

外部部署需配置HTTPS和可信代理。可使用独立域名，或与OMRS共用HTTPS入口的 `/zuoyebang/` 路径；同仓反代模板见 [deploy/zuoyebang.nginx.example](deploy/zuoyebang.nginx.example)。管理页资源／API使用相对地址，反代须剥离前缀并重写Cookie路径。配置示例（域名和代理地址由运维者替换）：

```bash
.venv/bin/python -m zyb_gateway serve --data-dir "$PWD/.state" \
  --bind 127.0.0.1 --port 8745 \
  --public-origin https://zyb.example.com --secure-cookie \
  --trusted-proxy 127.0.0.1/32
```

反代必须保留/设置公开 Host，并**覆盖而非照抄不可信用户头**产生 X-Forwarded-For；代理 CIDR 必须精确、不能 `/0`。公开 Origin 自动进入 Host allowlist，其余可信 Host 用 `--allow-host hostname:port` 明确增加。首次配置公开 Origin 时，本机 HTTP Origin 不再被视为同源：应先在原本机面板开启外部开关并停止自己的实例，再以公开 Origin 重启；或由运维者显式加 `--allow-external` 后通过 HTTPS 面板登录。开关持久化，重启保留。X-Forwarded-Proto/Forwarded 从不决定安全权限。外部真实 socket 来源不能被 XFF 洗成 local。服务不自建TLS或自动安装unit；同仓systemd模板见 [../../deploy/zuoyebang.service](../../deploy/zuoyebang.service)，独立安装模板见 [deploy/zuoyebang.service.example](deploy/zuoyebang.service.example)。生产目录与私有数据由部署者指定。

**每个私有目录只运行一个服务进程**，不要让多个进程共享同一套设备文件。私有目录 0700、文件 0600，不放入静态目录、源码导出或公开备份。备份应先停止自己的实例，完整保留私有目录；API Key 摘要不可还原原 Key。

## 验证

```bash
.venv/bin/python -m unittest discover -s tests -t . -v
node --check zyb_gateway/assets/panel.js
PIP_CACHE_DIR="$PWD/.pip-cache" .venv/bin/python -m pip install -r requirements-dev.txt
ZYB_TEST_CDP_URL=http://127.0.0.1:9222 .venv/bin/python tests/browser_acceptance.py
```

浏览器测试复用共享 Chrome，只创建/关闭自己的 context，**不关闭共享浏览器**。所有数据在 `docs/` 下隔离临时目录，测试结束删除。官方边界明确为 `SYNTHETIC`，没有调用真实作业帮、真实账号或模型。

本轮验收与已知验证边界见 [docs/verification.md](docs/verification.md)，任务记录见 [docs/2026-10-11_codex-acceptance.md](docs/2026-10-11_codex-acceptance.md)。桌面/390px 截图位于 `docs/`；可设置 `ZYB_TEST_EVIDENCE_DIR` 将浏览器证据写入指定目录。RED 失败见证和完整测试输出在 `docs/acceptance-2026-10-11/`。

本地独立包已重新构建安装并在源码目录外运行真实 HTTP 冒烟。测试不等于真实官方登录或生产上线验收；OMRS的渲染、识别与题库录入在同仓主应用执行；仓库根 `tests/e2e/zuoyebang_gateway_integration.py --with-prefix` 验证两个真实进程及前缀入口，官方边界仍为合成数据。
