# 2026-09-30 录入就绪状态提示

## 背景

用户反馈录入时右下角的成功 toast 会遮挡「一键提取」和「标记就绪」按钮，选择将成功反馈移入录入工作区内显示。本轮按完整模式执行，用户授权提交 GitHub 并切换生产。

## 行为变化

- 标记图片就绪并切到下一张后，成功信息显示在处理工作区「区域与转换」标题下的局部状态块中。
- 成功状态块使用语义成功色和 `role="status"`，约 3.2 秒后自动隐藏，不再创建对应的全局 toast。
- 提取失败、保存失败、校验失败和其它警告仍走原有全局 toast；处理队列的就绪状态仍由队列计数和状态标记持久显示。

## 影响文件

- `assets/app/features/create/process-view.js`：增加局部成功状态块。
- `assets/app/features/create/process.js`：管理状态文本、自动隐藏和组件销毁清理；成功标记就绪改为局部提示。
- `assets/app/features/create/process.css`：为状态块增加布局间距。
- `tests/app/create-process.test.mjs`：固定局部状态块存在且使用成功语义。
- `tests/e2e/create.py`：真实浏览器验证成功反馈在工作区内且不再弹同文 toast。
- `AI/frontend/create.md`：同步录入工作区当前行为。

## 验证

已实际执行：

- `node --test tests/app/create-process.test.mjs`：3/3 通过。
- `node --test tests/app/create.test.mjs tests/app/create-process.test.mjs tests/app/create-inbox.test.mjs`：28/28 通过。
- `python3 -m unittest discover -s tests -p 'test_*.py' -q`：410 个测试通过。
- `python3 tests/check_ui.py`：0 个问题。
- `python3 tests/check_contrast.py`：58 组对比度全部通过。
- `python3 tests/app/run_browser.py`：33/33 通过。
- `python3 tests/check_docs.py --diff HEAD`：0 处问题；3 条既有文档超长提醒。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/create.py`：114/114 通过，包含桌面 / 手机、浅色 / 深色录入工作区审计及成功提示主路径。

备注：全量 `node --test tests/app/*.test.mjs` 为 388/389；唯一失败是现有 `core.test.mjs` 路由假窗口缺少 `pathname/search` 导致的 `undefinedundefined#/board` 断言，本次未修改路由或该测试；录入相关 28/28 已单独通过。

GitHub 推送和生产切换结果见下方「生产部署」一节。

## 生产部署

- Git 提交 `d51efb3` 已推送到 GitHub `origin/main`；发布目录由 `git archive d51efb3` 生成于 `/root/workspace/releases/omrs-d51efb3`，发布目录迁移兼容测试 4/4 通过。
- 切换前服务为 active/running，生产 `/api/status` 返回 v2.0.0、239 道题、扫描 0 变更 / 0 冲突；助手 `active=[]`；收件箱 87 条，状态为 done 78 / ready 8 / boxed 1。备份目录为 `/root/workspace/backups/recycle/create-ready-d51efb3-20260930T033859Z`，真实 Vault 归档 `vault-before.tar` 的 SHA-256 为 `74fcf06356266595ac060335b177f3850e5da75738bd6627c2d1dfa7dd6bf78c`，原 drop-in 保存在 `10-release.conf.before`。
- 只替换 `/etc/systemd/system/omrs.service.d/10-release.conf` 的发布目录，执行 `systemctl daemon-reload` 后启动 `omrs.service`；最终 active/running、`MainPID=523356`、`NRestarts=0`、`ExecMainStatus=0`，工作目录为 `/root/workspace/releases/omrs-d51efb3`。
- 上线后 `/api/status` 仍为 v2.0.0、239 道题、0 变更 / 0 冲突；助手无活动运行；收件箱前后 JSON 快照 SHA-256 均为 `2d8912ba4f533ae06e5705882556211a27cc0adfb9f8b12e29957dbfb2c95652`；错误级 journal 为空。
- 生产真实 Chromium 只读验收使用 1440×900 与 390×844：首个 dashboard 文档响应为同一发布目录文件以避开 PIN 输入，之后的模块、静态资源和 API 均从 `127.0.0.1:8471` 读取；六个录入工作区、`#ib-ps-status` 状态槽位和新 `showStatus` 逻辑均存在，无横向溢出、无脚本错误、无 POST / PUT / PATCH / DELETE 请求。证据保存在备份目录 `production-browser.json`。

回退：恢复备份中的 `10-release.conf.before`，执行 `systemctl daemon-reload && systemctl restart omrs.service`；旧发布目录 `/root/workspace/releases/omrs-7108d8e` 保留。不得用 Vault 归档覆盖上线后的新增数据。
