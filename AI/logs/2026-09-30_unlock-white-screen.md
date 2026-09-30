# 2026-09-30 解锁后白屏

## 背景

用户反馈点击入口页按钮解锁后进入白屏。完整模式，基线为当前 `HEAD`（`e127041`）。隔离 Vault 的无 PIN 与有 PIN 浏览器路径均复现并核对了解锁跳转；代码、测试和服务响应是现状依据。

## 行为变化

入口成功解锁根路径时附带当前服务进程生成的 handoff token，避免浏览器复用重启或部署前缓存的工作台 HTML。工作台 HTML 响应改为 `Cache-Control: no-store`，静态模块资源仍使用原有 ETag / `no-cache` 协商。

## 影响文件

- `omrs/server.py`：入口跳转加入 handoff token；工作台 HTML 禁止缓存。
- `tests/test_security.py`：校验工作台响应的缓存策略。
- `tests/e2e/shell_router.py`：增加配置 PIN 后点击解锁的真实浏览器回归。
- `AI/frontend/shell.md`、`AI/api.md`：同步入口跳转和缓存契约。

## 验证

已实际执行：

- `python3 -m py_compile omrs/server.py tests/e2e/shell_router.py`：通过。
- `python3 -m unittest tests.test_security.SecurityTests.test_lock_screen_is_the_first_page_and_unlocked_dashboard_stays_guarded -q`：1/1 通过。
- `python3 tests/e2e/shell_router.py`：24/24 通过，含有 PIN 解锁、桌面和手机路由回归。
- `python3 tests/e2e/entry_background.py`：5/5 通过，入口背景桌面 / 手机与自定义媒体回归。
- `python3 tests/check_ui.py`：通过（0 处问题）。
- `python3 tests/check_contrast.py`：通过（58 组对比度）。
- `python3 -m unittest discover -s tests -p 'test_*.py' -q`：424/424 通过。
- `python3 tests/check_docs.py --diff HEAD`：通过（0 处问题；仅有既存文档大小提醒）。

`node --test tests/app/*.test.mjs` 共 396 项，其中 395 项通过；剩余 1 项为既有 `core.test.mjs` 路由测试在当前 Node 环境下把 `undefinedundefined#/board` 与 `#/board` 比较失败，与本次改动无关，单独运行该文件仍同样失败。
