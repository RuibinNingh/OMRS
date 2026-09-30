# 2026-09-30 锁屏入口

## 背景

用户要求首次进入 OMRS 时统一显示类似电脑锁屏的入口；启用 PIN 时直接在该入口输入 PIN 解锁，未启用 PIN 时进入工作台。本次按完整模式在本机 Git 工作区实现。

## 行为变化

- `/` 与 `/login` 首次返回独立锁屏页，显示当前时间、日期、星尘和轨道背景动效。
- 已配置 PIN 时入口显示 4–12 位数字输入框，成功后沿用现有登录 Cookie，再进入工作台。
- 未配置 PIN 且当前来源有访问权限时显示「进入 OMRS」；没有可用访问方式的远端继续提示在本机配置。
- 工作台地址使用 `?unlocked=1` 通过原有 `_authorize` 校验；配置了 PIN 时本机也必须先建立 PIN 会话，未登录远端不能借入口页访问题库、API 或静态资源。Hash 路由和 `/login?next=` 目标会保留。
- `prefers-reduced-motion` 下关闭入口背景动画。

## 视觉重设计追加

用户随后要求完整复刻参考站样式。本轮把入口背景替换为参考站同源的 Three.js/WebGL 场景：48 组公式曲面、金白色黑洞与吸积环、星尘、滚动镜头、指针扰动、拖拽黑洞和点击脉冲；顶部 `( Deploy ) / ( Preview ) / ( Ship )` 与底部工作区信息按参考站网格排版。PIN / 无 PIN 解锁入口作为同一叠加层保留，WebGL 不可用时使用本地参考主视觉降级。场景源码、公式 atlas 与降级图存放在 `assets/vendor/entry-*`，入口只在首次访问时加载。

为避免重型场景使带 hash 的入口跳转产生二次导航，工作台路由监听提前安装，入口在已有 hash 时立即完成自动解锁，路由恢复非法 hash 时保留现有查询串。

## 影响文件

- `omrs/server.py`：新增锁屏入口响应，调整根页面与 `/login` 的进入路径。
- `assets/vendor/entry-scene.js`、`assets/vendor/entry-math-atlas.svg`、`assets/vendor/entry-fallback.webp`：参考站 WebGL 场景及降级资源。
- `assets/app/main.js`、`assets/app/core/router.js`：提前安装路由监听并稳定入口跳转。
- `AI/frontend/architecture.md`、`AI/frontend/shell.md`：同步启动顺序、入口场景与资源边界。
- `tests/test_security.py`：覆盖入口公开响应、PIN 表单和未登录远端仍被工作台拦截。
- `tests/e2e/shell_router.py`：首次打开时点击无 PIN 入口后再执行外壳回归。
- `AI/api.md`、`AI/security.md`、`AI/frontend/shell.md`、`AI/routes.md`、`README.md`：同步入口和授权行为。

## 验证

已实际执行：

- `python3 -m py_compile omrs/server.py`。
- `python3 -m unittest tests.test_security`：13 个测试通过。
- `python3 tests/e2e/shell_router.py`：23 个检查通过，0 个失败；包含桌面、手机和静态资源缓存检查。
- `python3 tests/check_ui.py`：0 个问题；vendor 场景不计入应用层行数门禁。
- `python3 tests/check_contrast.py`：58 组对比度全部通过。
- `node --test tests/app/*.test.mjs`：389 个测试通过。
- `python3 tests/app/run_browser.py`：33 个浏览器单测通过。
- 手工 Playwright 验证：无 PIN 本机入口按钮可进入工作台；配置 PIN 后输入正确 PIN 可进入；远端未登录访问 `?unlocked=1` 仍返回登录跳转。
- 手工 Playwright 验证：桌面 1440×900 与手机 390×844 均加载真实 WebGL 场景（`data-status=ready`），黑洞 / 公式曲面 / 星尘可见，无脚本错误和横向溢出；截图保存于 `/tmp/omrs-entry-ref-desktop.png`、`/tmp/omrs-entry-ref-mobile.png`。
- `python3 tests/check_docs.py --write-routes` 已更新路由索引。

未执行：生产发布后的真实 WebGL 浏览器验收尚未执行，需在新发布目录上线后补做；完整业务 E2E 未因本轮只改入口而重复运行。

## 生产部署

- 用户已明确授权「更新生产」。提交 `cdca589` 已归档到 `/root/workspace/releases/omrs-cdca589`；发布目录中的 `omrs/server.py` 与工作区提交哈希一致。
- 切换前服务为 active，版本 v2.0.0，真实 Vault `/root/workspace/apps/OMRS`，题目数 239，工作区扫描为 0 变更 / 0 冲突；助手无活动运行，收件箱 145 个后台任务均为 done。停服后真实 Vault 的 SQLite `quick_check` 全部为 `ok`。
- 备份目录：`/root/workspace/backups/recycle/lock-screen-cdca589-20260930T011933Z`；完整 Vault 归档 `vault-before.tar`，SHA-256 为 `dc4cde0f59d68a17c6b4983bb2ac5bd3fc69629f91d0982d7ea85b9520364be6`，原 drop-in 保存为 `10-release.conf.before`。
- systemd drop-in 已切到 `/root/workspace/releases/omrs-cdca589`，执行 `systemctl daemon-reload` 后启动 `omrs.service`。上线后 active/running、`MainPID=116370`、`NRestarts=0`、`ExecMainStatus=0`；`/api/status` 返回 v2.0.0、239 题、0 冲突。
- 生产入口验收：`/` 与 `/login` 返回锁屏页；配置 PIN 的本机在无会话访问 `/?unlocked=1` 时返回 302 到 `/login`；真实 Chromium 桌面 1440×900 与手机 390×844 均看到 PIN 输入框、无横向溢出、脚本错误 0；错误级 journal 为空。验收证据保存在备份目录 `verification.json`。
- 回退：恢复备份中的 `10-release.conf.before`，执行 `systemctl daemon-reload` 和 `systemctl restart omrs.service`；旧发布目录 `/root/workspace/releases/omrs-1b0558c` 保留。不得用旧 Vault 归档覆盖发布后的新增数据。
