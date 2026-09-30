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

未执行：GitHub 推送和生产切换在本日志初稿完成后执行，结果补在「生产部署」一节。

## 生产部署

待代码提交和生产切换后补写发布提交、备份目录、服务状态、生产浏览器验收和回退方式。
