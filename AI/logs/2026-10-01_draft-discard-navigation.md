# 2026-10-01 AI 草稿丢弃后继续审核

## 背景

用户原话：「OMRS有一个反人性的设计,AI草稿点击丢弃后,会直接切换到"丢弃"分类,这样我还要切换分类」「提供一个修复方式」，随后确认「修复」。执行者为 Codex · 完整模式；这是已完成的草稿功能之后的独立交互修复，不属于进行中的计划。基线为 `692728d`，开工时工作区干净，版本保持 v2.1.0。

## 行为变化

- 丢弃成功后保持「待审核」，打开原队列中的下一份；当前是末项时选择上一份。取消和请求失败保留当前草稿及未保存编辑。
- 丢弃与入库共用队列推进。清空详情时同步清除会话选中记录，空队列返回或刷新后不会重新打开已处理的草稿。
- 丢弃成功但列表读取失败时显示列表错误，清空已处理项的选择，重试后可继续审核。
- 手动选择「已丢弃」或指定草稿导航仍保留只读查看能力；后端接口、原图保留与并发版本保护不变。
- 真实浏览器首轮回归发现画布在空草稿、空检测结果时会解引用不存在的检测结果，已补上空值处理。

## 影响文件

- `assets/app/features/create/drafts.js`：抽出队列推进方法，丢弃成功后继续审核并清除旧选择。
- `assets/app/features/create/drafts-canvas-ctl.js`：画布刷新兼容空检测结果与空详情。
- `tests/e2e/drafts.py`：更新成功丢弃的预期，覆盖队列相邻选择、取消、失败、空队列记忆和列表重试。
- `tests/e2e/drafts_blocks.py`：更新多块审核的丢弃预期，手动进入已丢弃分类检查只读正文。
- `AI/frontend/create.md`、`AI/frontend/architecture.md`、`README.md`：同步当前交互及验证边界。
- 本任务日志与 `AI/logs/log.md`：记录实际改动及验证，索引由脚本生成。

## 验证

已实际执行：

- `node --test tests/app/*.test.mjs`：403/403 通过。
- `python3 tests/app/run_browser.py`：34/34 通过。
- `python3 tests/check_ui.py`：全仓五类计数均为 0，0 问题。
- `python3 -m unittest tests.test_ui_gates -q`：12/12 通过，退出码 0；控制器共 399 行，保持单文件门禁。
- `python3 tests/check_contrast.py`：58 组通过，0 不达标。
- `python3 tests/e2e/drafts.py`：75/75 通过，覆盖新增丢弃队列路径、原有审核 / 入库 / 框选与浅 / 深色桌面 / 手机审计。
- `python3 tests/e2e/drafts_blocks.py`：59/59 通过，含丢弃后下一份、手动查看只读正文及 320 / 390 / 1024 / 1440px 审计。
- `python3 tests/visual/run.py --ref 692728d --pages create --create-stage drafts --out /tmp/omrs-draft-discard-visual`：浅 / 深色、桌面 / 手机共 4 组截图，0 差异、0 页面脚本错误。改动只涉及操作后的队列推进，默认审核布局没有变化；交互由专用 E2E 覆盖。
- `python3 tests/check_docs.py --write-log-index`：已生成本次任务的日志索引。
- `python3 tests/check_docs.py --diff HEAD`：77 份文档，0 问题，退出码 0；3 条提醒均为本次未涉及文档的体积提醒。
- `git diff --check`、`git diff --name-status`：检查通过，已复核修改范围；新增日志同时由 `git status --short` 核对。

首轮多块回归在入库后清空详情时报错，21/23 通过；修复画布空值处理后最终 59/59 通过。新增队列回归一轮因取消按钮选择器同时命中标题关闭按钮与底部取消按钮而失败，已限定为对话框底部，最终 75/75 通过。

未执行：全量 Python 后端套件，本次未改后端逻辑，实际 HTTP 与持久化由草稿 E2E 验证。生产部署、重启和远端推送未获本任务授权；所有浏览器实例均使用临时 Vault 与随机端口，启动前去掉 `OMRS_SYSTEMD_SERVICE`，不访问真实题库。
