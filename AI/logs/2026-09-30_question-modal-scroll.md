# 2026-09-30 修复手机版题目详情滚动

## 背景

用户反馈：手机版题目菜单不能滑动，长题内容无法查看。截图对应共享题目详情弹窗 `#modal`。本轮按完整模式在本机 Git 工作区实现，开工前工作区已有其他任务的未提交改动，均保留。

## 行为变化

- 题目详情弹窗在手机窄屏中保持在可视高度内。
- 长题内容由弹窗题面区独立纵向滚动，头部和关闭按钮保持可用，背景页面继续锁定。
- 题面内部公式和表格的横向滚动、桌面双栏布局与翻页行为保持不变。

## 影响文件

- `assets/app/ui/dialog.css`：允许共享对话框面板在受限高度下收缩。
- `assets/app/domain/question/qview.css`：明确题面滚动区填充面板剩余高度。
- `tests/app/browser_tests.js`：增加长内容对话框滚动回归。
- `tests/e2e/questions.py`：增加 390×844 与 320×640 长题弹窗滚动验收。
- `AI/frontend/qview.md`、`AI/frontend/components.md`：同步滚动契约。

## 验证

已实际执行：

- 隔离 HTML flex 复现：修复前面板高度约 1680px；加入 `min-height: 0` 后题面区获得可滚动高度。
- `python3 tests/fixtures/make_vault.py`：成功生成 40 题隔离 fixture。
- `python3 tests/app/run_browser.py`：34/34 通过，包含新增长内容对话框滚动回归。
- `python3 tests/check_ui.py`：通过，handlers / html_assign / inline_style / color_literals / font_size_literals 均为 0。
- `python3 tests/check_contrast.py`：58 组对比度全部通过。
- `node --test tests/app/*.test.mjs`：393/394 通过；唯一失败是现有 `core.test.mjs` 路由 hash 用例，报错 `undefinedundefined#/board`，与本次 CSS 无关。
- 隔离 OMRS 页面直接打开 `viewQ('三角函数3')`：390×844、320×640 均验证面板在视口内、题面区可滚动、滚轮改变 `scrollTop`、可到创建信息末尾、横向溢出为 0，关闭后滚动锁解除，页面错误为 0；1440×900 验证面板边界、双栏布局与无横向溢出保持正常。
- `python3 tests/check_docs.py --diff HEAD`：0 处文档问题；仅有 3 个既有超长文档提醒。
- `python3 -m py_compile tests/e2e/questions.py`、`node --check tests/app/browser_tests.js`：通过。

未通过或未执行：

- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/questions.py`：当前工作区的锁屏 / fixture 启动路径使题库页显示 0 题并最终卡住，已停止进程；完整题库 E2E 未形成有效结果。
- `env -u OMRS_SYSTEMD_SERVICE OMRS_TEST_CDP_URL=http://127.0.0.1:9222 python3 tests/e2e/ui_bridge.py`：在既有锁屏启动问题处报 `window.__omrs` 未定义。
- `python3 tests/visual/run.py --ref HEAD --out /tmp/omrs-question-scroll-visual --pages questions --themes light,dark --viewports desktop,mobile`：同样在既有 `window.__omrs.router` 未定义处停止。
- 真实 Android Chrome / iOS Safari 尚未连接硬件验收；本轮没有进行生产服务或真实 Vault 写入。
