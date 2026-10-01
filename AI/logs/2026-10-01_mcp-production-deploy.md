# MCP 生产部署与 GitHub 同步

## 背景与授权

Hermes Agent，完整模式。用户先要求只读核验生产，确认 MCP 仅在开发分支后明确授权「推送一下，然后部署生产」。合入 `codex/mcp-integration` 的 `14eeeb0`，发布前修正草稿控制器行数门禁得到 `bbf3757`。生产仍为 v2.0.0，此次不是版本号升级。用户随后提供 ChatGPT Tunnel ID 并要求稍后接入，本次不启动新 Tunnel，不修改现有 Logseq、墨墨连接。

## 发布行为

- 主服务 `omrs.service` 从 `/root/workspace/apps/releases/omrs-bbf3757` 运行，独立 venv 安装 `requirements-mcp.txt`；真实 Vault 仍是 `/root/workspace/apps/OMRS`。
- 有效启动参数为 `serve --port 8471 --mcp-port 18472 --mcp-public-url https://home.ruibin-ningh.top:8472/mcp`。Web 与 MCP 同进程，复用主进程写锁；不启动第二个直接写 Vault 的 MCP 服务。
- 公网 HTTPS 8472 共用：`/` 仍转发 Web 8471，`/mcp` 转发 `127.0.0.1:18472/mcp`；内部 MCP 只监听回环。不新增公网端口，不降低 PIN 或 MCP Key 鉴权。
- 受限 MCP 固定发现十个工具（九个查询、唯一写工具 `create_draft`），写工具只创建待人工审核草稿。部署验收使用临时 `omrs:read` Key，不创建真实草稿，结束立即吊销。

## 备份与回滚

停服冻结数据后备份到 `/root/workspace/apps/releases/OMRS-mcp-rollback-20261001-114502/`，包括原 systemd unit/drop-in、Nginx 配置、旧源码归档、完整 Vault 归档、文件哈希与数据库逻辑快照。Vault 归档覆盖 872 个文件，SHA-256 为 `531390644d91741c6ecf5d1c60e2e7ec8045a43f2a1464becdf605acbbdefd42`。`MANIFEST.sha256` 全部通过；隔离解包校验文件与数据库逻辑状态通过。恢复检查副本随后用于新 schema 兼容性核验，不作为冻结原备份的替代。

代码回滚需先获授权：恢复备份的 `/etc/systemd/system/omrs.service.d/10-release.conf` 和 `/www/server/panel/vhost/nginx/omrs-home-8472.conf`，检查配置、daemon-reload、受控重启主服务并重载 Nginx，再核有效 ExecStart、Web/API 与端口。原发布目录 `/root/workspace/releases/omrs-2957939` 保留。检测服务与模型不随主服务回滚切换。Vault 归档仅供专项数据恢复，不能覆盖部署后用户的新数据；不使用 `git reset --hard` 或整树覆盖。

## 候选门禁

以下结果来自实际运行并保留的候选日志，不以计划勾选代替实测：

- Python 全量 470/470，通过；Node 全量 399/399，通过。
- 隔离真实 MCP/浏览器闭环 15/15，通过，覆盖原图字节、来源与 Key 创建/隐藏/刷新/吊销/离页清空。
- UI 全仓 0 问题，58 组对比度全部通过；文档门禁 0 问题、3 条既有大文件提醒。
- 此次文档收尾只改文档，不改已通过门禁的发布源码，不再次重启生产。

## 生产验收与数据边界

- 运行进程 PID 725560，`active/running`，重启计数 0。`/api/status` 返回 200、v2.0.0、262 题、0 冲突；有效 ExecStart 指向 `omrs-bbf3757`。
- 通过公网 HTTPS 的真实官方 SDK Client 完成 initialize（协议 2025-11-25）、tools/list 与 `get_overview`、`list_taxonomy`、`list_drafts` 调用。
- 只读 scope 调用 `create_draft` 返回权限错误；缺失/错误 Key 返回 401；MCP Key 访问普通 Web API 返回 403；临时 Key 吊销后返回 401。
- 6 个 SQLite 数据库 `PRAGMA integrity_check` 均为 ok，题目 Markdown 哈希变化 0；Ledger 验证通过，717 个提交，HEAD 为 `CMT-000717`。
- 草稿库新增 `mcp_requests` 表，并为旧草稿增加五个来源/错因校验字段；旧有列投影的 27 条草稿内容保持一致。原业务表逻辑内容不变；Ledger 仅 `workspace_fingerprint.last_seen_at` 与 `workspace_scan_status.last_scan_at` 等扫描时间元数据更新。不能把 schema/启动扫描变化误报为新增题目或业务写入。

## 浏览器与外部客户端限制

真实浏览器访问生产入口可见 PIN 闸门；`/?unlocked=1` 仍要求有效 PIN 会话，未绕过或更改设置。当前 PIN 已配置；本机 API 的免 PIN 状态不等于浏览器拥有页面登录会话。没有保存的浏览器凭据，因此本次未进入生产主应用、设置或审核页；页面功能验收为隔离实例结果，不能冒充生产登录后验收。

ChatGPT 尚未接通。后续使用 Secure MCP Tunnel 独立 `main` 绑定连接回环 MCP，由 Tunnel 客户端从受限文件注入 Authorization；不要使用其他 Tunnel 的 `main`，不要将 Key 放 URL，也不需要为 Tunnel 移除公网鉴权。Tunnel ready 与 ChatGPT 工具发现/实际调用必须分别验收；读取或草稿创建权限按用户后续要求配置。

## 文档与 Git

更新 `AI/environment.md` 的当前生产事实、`AI/mcp.md` 的端口与认证边界、`AI/plans/mcp-integration/progress.md` 的上线和未验收状态，并由生成器更新 `AI/logs/log.md`。代码提交 `14eeeb0` 和门禁修正 `bbf3757` 已分别核对 GitHub 分支；本次部署文档随后独立提交、推送并读取远端精确 SHA。运行源码仍固定在已验证的 `bbf3757`，文档提交不触发发布切换。
