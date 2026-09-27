# 2026-09-24 局域网直连免 PIN

## 用户诉求

用户指出局域网访问没有免 PIN 功能，并询问当前是否存在局域网 PIN 豁免。此前只有本机回环地址直连免 PIN；生产服务的 `192.168.0.145:8471` 会跳转登录，而公网 HTTPS 部署尚未初始化 PIN。

## 行为变化

- 设置页新增 `lan_pin_exempt_cidrs` 输入框。默认空列表；只接受 RFC1918 IPv4 或 IPv6 ULA 的规范 CIDR，最多 8 个。配置在保存后立即生效。
- 豁免仅按 TCP 直连对端 IP 判断。可信代理的请求无论代理头内容如何均不享受网段豁免；公网 HTTPS 入口继续要求 PIN。未配置 PIN 时，非豁免远端仍拒绝访问。
- 启用 `allow_external` 时允许使用 PIN 或免 PIN 网段建立访问边界。跨站 POST 检查仍对豁免设备生效。免 PIN 网段内设备可访问完整应用，包括备份和源码下载。
- 生产配置加入 `192.168.0.0/24`，重启 `omrs.service` 后局域网直连可免 PIN；公网 HTTPS 代理仍进入登录页。

## 影响文件

`omrs/common.py`、`omrs/security.py`、`omrs/server.py`、`assets/app/main.js`、`omrs_dashboard.html`、`tests/test_security.py`、`README.md`、`AI/api.md`、`AI/data.md`、`AI/frontend.md`、`AI/inbox.md`、`AI/optimization.md`、`AI/security.md`、本日志和 `AI/logs/log.md`。生产运行配置 `错题/.omrs/config.json` 增加 `lan_pin_exempt_cidrs`。

## 验证

- `python3 -m unittest discover -s tests -p 'test_*.py' -q`：125 项通过；`node --test tests/test_*.js`：120 项通过。
- 临时题库真实 HTTP 服务及 Chromium：`192.168.0.0/24` 直连进入桌面页，设置页回显网段；模拟 Nginx 的请求仍显示登录页。
- 生产 `omrs.service` 重启后 active；直连 `http://192.168.0.145:8471/` 与 `/api/status` 返回 200，Chromium 能进入设置页并看到免 PIN 网段与 PIN 状态；同一直连入口的跨站 POST 返回 403。`https://home.ruibin-ningh.top:8472/` 仍返回 302 到 `/login`。
- `git diff --check` 与 `python3 tests/check_docs.py` 通过。
