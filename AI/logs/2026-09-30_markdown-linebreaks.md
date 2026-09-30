# 2026-09-30 Markdown 与普通换行兼容

## 背景

用户反馈 AI 生成的题面常用普通单换行分隔题干、选项和小问，但题库渲染按 Markdown 软换行把它们合并成一段；要求全面调查各渲染入口，同时兼容 Markdown 段落和普通逐行文本。本次由 Codex 在完整模式处理。

## 行为变化

- 共享题目 Markdown 渲染器默认使用 `full`：普通单换行输出 `<br>`，空行仍输出 Markdown 段落；用户在题库「显示设置」中选择「简略」时仍可使用旧的 `lean` 软换行行为，偏好会持久化。
- 题库、题目弹窗、画廊、反馈、即时练习、展示板详情、录入预览和 AI 草稿审核统一复用共享渲染器；助手聊天原有逐行 Markdown 渲染保持不变。
- 助手工具结果卡的内联题目摘要、正文差异和草稿预览也保留普通换行，避免辅助卡片成为遗漏入口。
- A4、展示板和屏幕版导出对题面、答案、备注保留普通换行；导出解析仍把每个文字行作为独立块，跨行 `$$…$$` 保持为一个公式块。

## 影响文件

- `assets/app/domain/question/markdown.js`：默认模式迁移到 `full`，保留 `lean` 兼容入口和本地偏好。
- `assets/app/features/assistant/md.js`：内联转义把来源文本中的普通换行输出为 `<br>`。
- `assets/app/features/questions/index.js`、`state.js`、`view.js`：默认值、视图快照、重置行为和显示设置文案同步。
- `assets/app/domain/question/qview.css`、`omrs/export_templates/a4.css`、`board.css`、`screen.css`：题面块和导出内容的换行样式。
- `README.md`、`AI/frontend/architecture.md`、`AI/frontend/shell.md`、`AI/frontend/qview.md`、`AI/frontend/library.md`、`AI/frontend/create.md`、`AI/frontend/assistant.md`、`AI/export.md`：同步渲染入口和当前行为。
- `tests/app/question.test.mjs`、`tests/app/assistant.test.mjs`、`tests/test_report_export.py`：覆盖默认逐行、显式简略、段落、助手工具卡、表格和导出文字块。

## 验证

已实际执行：

- `node --test tests/app/question.test.mjs tests/app/questions.test.mjs`：50/50 通过。
- `node --test tests/app/assistant.test.mjs tests/app/question.test.mjs tests/app/questions.test.mjs`：68/68 通过。
- `python3 tests/app/run_browser.py`：33/33 通过。
- `python3 -m pytest -q tests/test_report_export.py`：7/7 通过。
- `python3 tests/check_contrast.py`：58/58 通过。
- `node --test tests/app/*.test.mjs`：390 项中 389 项通过；唯一失败是既有路由测试期望 `#/board`，实际地址为 `undefinedundefined#/board`，与 Markdown 改动无关。
- `python3 -m unittest discover -s tests -p 'test*.py'`：410/410 通过（输出中的 ResourceWarning / BrokenPipe 为测试隔离服务收尾噪声）。
- `python3 tests/check_ui.py`：0 处问题；`python3 tests/check_docs.py --diff HEAD`：0 处问题，体量提示保留为提醒。

未完成或受现有工作区影响：

- 工作区另一项草稿审核改动曾使 `drafts.js` 超过 UI 行数门槛，当前已恢复到 400 行以内；本次未重排或覆盖该文件。
- `tests/e2e/questions.py` 曾因题库页面初始数据总线刷新导致 180 秒超时并出现 Playwright EPIPE；先进入仪表盘再切题库时，浏览器实测题面输出为 `<p class="md-p">题干<br>A. 甲<br>B. 乙</p>`，题目、答案和备注均保留普通换行。
- `python3 tests/visual/run.py --ref <基线>`：`questions-dark-desktop`、`instant-dark-desktop`、`feedback-dark-desktop`、`board-dark-desktop`、`create-dark-desktop`、`assistant-dark-desktop` 共 6 页均为 0.0% 差异，无脚本错误；报告保存在 `/tmp/omrs-visual-linebreaks/report.html`。
- `python3 -m unittest tests.smoke_board_print -q`：7/7 通过，展示板真实浏览器分页、KaTeX、长图续排和增量打印均无溢出。

## 生产部署

- 用户随后明确要求「更新生产环境」，已按完整模式授权切换。以工作区 `HEAD=3c0df6922a19b410190a0aa9f8da968a29b9aac6` 的干净 `git archive` 为基线，只把本任务 9 个换行相关文件覆盖到 `/root/workspace/releases/omrs-linebreaks-545b604cb25b`；工作区其它草稿审核改动、`.playwright-mcp/` 和未提交文件没有带入生产。
- 切换前服务为 active/running，真实 Vault 为 `/root/workspace/apps/OMRS`。一致性备份保存于 `/root/workspace/backups/recycle/markdown-linebreaks-20260930T060320Z`，包含原 `10-release.conf`、切换前后状态快照和 `vault-before.tar`；归档 SHA-256 为 `9ae99d68fecf37d2b1e03ab8eb04741961e588c6985033035f9aa2292e6405cb`。旧发布目录 `/root/workspace/releases/omrs-d51efb3` 保留用于代码回退。
- 替换 systemd drop-in 的发布路径后执行 `systemctl daemon-reload` 与 `systemctl restart omrs.service`。当前 `omrs.service` 为 active/running，`MainPID=919236`、`NRestarts=0`、`ExecMainStatus=0`，工作目录为 `/root/workspace/releases/omrs-linebreaks-545b604cb25b`；切换后的错误级 journal 无记录。
- 生产 `/api/status` 返回 `status=ok`、`version=v2.0.0`、260 道题、workspace scan 变更 0 / 冲突 0；助手 active 为空，`agent.db` 的 done 为 61，inbox jobs 的 done 为 169，draft jobs 的 done 为 3。发布目录清单中的 6 个前端换行资源经 HTTP 返回 200 且 SHA-256 与清单一致；3 个导出模板由服务端导出测试覆盖。
- 真实 Chromium 只读验收：通过同一发布目录的 `omrs_dashboard.html` 响应绕过 PIN 锁屏后，生产接口和静态资源仍从 `127.0.0.1:8471` 加载。桌面 1280px 与手机 390px 依次打开仪表盘、题目库、即时练习、反馈录入和录入题目，所有页面均就绪、无横向溢出、无 page error、无非 GET 请求；题目详情实际看到 `<br>` 保留普通单换行，答案各行也保留 `<br>`。展示板页另触发 1 次只读 `/api/export` 生成预览 HTML，没有写入题库数据。
- 发布快照实际验证：定向 Node 68/68、迁移兼容与展示板浏览器冒烟 11/11、导出 7/7 通过。生产浏览器直接加载线上模块复核：默认模式为 `full`，`题干\nA. 甲\nB. 乙` 输出一个含两个 `<br>` 的段落，Markdown 空行输出两个段落，助手内联文本也保留换行。
- 文档收尾已执行 `python3 tests/check_docs.py --write-log-index`；`python3 tests/check_docs.py --diff HEAD` 检查 67 份文档，0 处问题、3 条既有体量提醒；`git diff --check` 通过。最终服务仍 active/running、无自动重启、260 道题、0 变更 / 0 冲突，6 个前端资源和 3 个服务端导出模板的本地哈希均匹配发布清单。

未执行：真实模型调用、生产题目写入、GitHub 推送。本次仅发布换行兼容；全量 Node 的既有路由假窗口断言失败和题库完整 E2E 的超时情况保留在上节，不把定向通过表述为全量全部通过。

回退：恢复备份中的 `10-release.conf.before`，执行 `systemctl daemon-reload && systemctl restart omrs.service`；代码旧发布目录为 `/root/workspace/releases/omrs-d51efb3`。不要用 Vault 归档覆盖发布后的新增数据。
