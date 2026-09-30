# 2026-09-30 锁屏入口

## 背景

用户要求首次进入 OMRS 时统一显示类似电脑锁屏的入口；启用 PIN 时直接在该入口输入 PIN 解锁，未启用 PIN 时进入工作台。本次按完整模式在本机 Git 工作区实现。

## 行为变化

- `/` 与 `/login` 首次返回独立锁屏页，显示当前时间、日期、星尘和轨道背景动效。
- 已配置 PIN 时入口显示 4–12 位数字输入框，成功后沿用现有登录 Cookie，再进入工作台。
- 未配置 PIN 且当前来源有访问权限时显示「进入 OMRS」；没有可用访问方式的远端继续提示在本机配置。
- 工作台地址使用 `?unlocked=1` 通过原有 `_authorize` 校验；配置了 PIN 时本机也必须先建立 PIN 会话，未登录远端不能借入口页访问题库、API 或静态资源。Hash 路由和 `/login?next=` 目标会保留。
- `prefers-reduced-motion` 下关闭入口背景动画。

## 影响文件

- `omrs/server.py`：新增锁屏入口响应，调整根页面与 `/login` 的进入路径。
- `tests/test_security.py`：覆盖入口公开响应、PIN 表单和未登录远端仍被工作台拦截。
- `tests/e2e/shell_router.py`：首次打开时点击无 PIN 入口后再执行外壳回归。
- `AI/api.md`、`AI/security.md`、`AI/frontend/shell.md`、`AI/routes.md`、`README.md`：同步入口和授权行为。

## 验证

已实际执行：

- `python3 -m py_compile omrs/server.py`。
- `python3 -m unittest tests.test_security`：13 个测试通过。
- `python3 tests/e2e/shell_router.py`：23 个检查通过，0 个失败；包含桌面、手机和静态资源缓存检查。
- 手工 Playwright 验证：无 PIN 本机入口按钮可进入工作台；配置 PIN 后输入正确 PIN 可进入；远端未登录访问 `?unlocked=1` 仍返回登录跳转。
- `python3 tests/check_docs.py --write-routes` 已更新路由索引。

未执行：`tests/check_ui.py`、`tests/check_contrast.py` 和全量 E2E；本次没有修改 `assets/`、`omrs_dashboard.html` 或设计 token，入口为服务端内联页面。
