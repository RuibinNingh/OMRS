# 2026-09-30 入口背景配置生产部署

## 授权与范围

用户明确要求“推送 GitHub，生产环境”。本次发布提交 `541e7f9`，包含入口背景配置功能及其测试、文档；只切换主服务代码发布目录，不修改 Nginx、框选检测服务、模型或真实 Vault 内容。

## GitHub 推送

- `git fetch origin main` 确认远端 `21e5359` 是本地历史祖先，没有分叉。
- `git push origin main` 成功，远端 `main` 已指向 `541e7f9a51925461acd4bf7caa5a7664cbbc4ce3`。

## 发布与备份

- 用 `git archive 541e7f9` 生成 `/root/workspace/releases/omrs-541e7f9`，共 936 个文件；发布目录入口背景单测 7/7、迁移兼容测试 4/4 通过。
- 切换前停止 `omrs.service`，完整归档真实 Vault 到 `/root/workspace/backups/recycle/entry-background-541e7f9-20260930T131801Z/vault-before.tar`；SHA-256 为 `43d3f0b66f409591d7f3c9dd6c3295ef7477f8f8e0fb647658497a6ab72ae21b`。
- 保存切换前后的 systemd drop-in、服务状态、API 状态、发布文件清单和回滚证据。旧发布目录 `/root/workspace/releases/omrs-c663951` 保留。

## 切换结果

更新 `/etc/systemd/system/omrs.service.d/10-release.conf` 后执行 `systemctl daemon-reload` 和 `systemctl start omrs.service`。当前服务 `active/running`，`MainPID=2129716`、`ExecMainStatus=0`、`NRestarts=0`，工作目录为 `/root/workspace/releases/omrs-541e7f9`。生产 `/api/status` 返回 `status=ok`、版本 `v2.0.0`、261 道题、workspace scan 变更 0 / 冲突 0；错误级 journal 无记录。

## 验证

已实际执行：

- 生产入口真实 Chromium 桌面 / 手机只读验收：黑洞状态分别为 `ready`，无横向溢出和脚本错误；证据保存在备份目录的 `entry-desktop.png`、`entry-mobile.png` 和 `production-browser-entry-mobile.json`。
- 生产设置页真实 Chromium 桌面 / 手机只读验收：入口背景卡片、黑洞 / 自定义预设、高斯模糊选项、`max=32` 滑杆均存在，无横向溢出和脚本错误；证据为 `settings-desktop.png`、`settings-mobile.png`、`production-browser-settings.json`。
- 无自定义媒体时 `GET /api/entry-background` 返回 404；伪造非本机 Host 的未登录请求中，`/api/config` 和普通 `/assets/app/main.js` 返回 401，公共 `/assets/vendor/entry-scene.js` 返回 200。
- 生产服务健康检查、systemd 状态和错误级日志均通过。

部署后配置变化：在本轮只读验收期间，真实 Vault 于本地时间 21:32 写入了一份 PNG 自定义背景（配置 ID `d7e6c7cccd252ad4548af3cda28705ff`，1,701,061 字节）。本次部署命令没有执行上传或配置 POST，也没有覆盖该文件；当前入口桌面 / 手机真实浏览器均为 `custom-ready`，媒体请求返回 `image/png`，`?v=bogus` 仍只返回当前媒体。该用户配置发生在部署前备份之后，回退时不得用备份归档覆盖它。

未执行：生产写入型上传 E2E、真实视频上传和真实手机硬件验收；写入验收会改变用户配置，因此保留在隔离 Vault 的完整测试中（Python 422/422、设置页 E2E 62/62、入口页 E2E 5/5）。

## 回退

如需回退，恢复备份目录中的 `10-release.conf.before`，执行 `systemctl daemon-reload && systemctl restart omrs.service`，旧发布目录仍保留。不得用 Vault 归档覆盖上线后新增数据。
