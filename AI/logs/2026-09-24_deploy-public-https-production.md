# 2026-09-24 OMRS v1.19.0 公网 HTTPS 部署

## 目标与范围

将 OMRS 当前工作树版本部署到生产，并通过 `home.ruibin-ningh.top` 的非标准 HTTPS 端口公开访问。Homepage 卡片按用户要求不修改。

## 变更摘要

- 生产运行 `omrs.service`，工作目录 `/root/workspace/apps/OMRS`；Nginx 在 `192.168.0.145:8472` 终止 TLS，并反代至 `127.0.0.1:8471`。
- OpenWrt WAN 新增 TCP/8472 DNAT 到 `192.168.0.145:8472`（含 LAN reflection）；主机 UFW 允许 TCP/8472。OMRS 原端口 8471 的 UFW 规则仍仅允许 `192.168.0.0/24`。
- Homepage 配置未改。

## 验证

- 源码门禁：`git diff --check` 通过；Python 124 项通过；Node 120 项通过；文档检查 15 篇、0 问题。
- 生产服务为 active；`/api/status` 返回 `v1.19.0`、208 道题。
- Nginx `-t` 成功；本机通过域名解析到 TLS vhost 的 HTTPS 请求成功，证书校验结果为 0。
- 外部 Chromium 实际访问 `https://home.ruibin-ningh.top:8472/`，到达 OMRS 登录页；路由器 UCI 与 live WAN DNAT 均存在，主机 UFW configured/live 规则均放行 8472。

## 尚待用户完成

新安全实现的 PIN 存储尚未初始化。远端页面明确显示“尚未配置 PIN，请在本机设置页完成配置”；远端内容在设置 PIN 前保持拒绝访问。请在 LAN 打开 `http://192.168.0.145:8471/`，进入“设置”页的“远端访问 PIN”，设置 8–12 位数字并保存；配置后远端才能登录。未代用户生成或设置 PIN，因此尚未做已认证浏览器验收。

## 回滚资料

- 主机与应用快照：`/root/workspace/backups/recycle/omrs-public-https-20260924-195836/`
- OpenWrt 防火墙备份：`/root/hermes-backups/20260924-195836/`
- Nginx vhost：`/www/server/panel/vhost/nginx/omrs-home-8472.conf`
