# 2026-11-12 题目静态 SVG 配图

> **任务**
> - 标识：svg-questions
> - 状态：已交付

## 背景

用户希望用SVG丰富题目、保持Obsidian阅读和其他功能可用，强调双栏打印下信息适中。用户原话与默认决策见AI/plans/svg-questions/plan.md。Codex完整模式，开工工作区干净，基线5762ded1a43003e42f1e29f578f3f1a76fcd2fe0。

## 行为变化

快速录入可添加题目与答案SVG，上传时检查静态安全、白底、viewBox、title与双栏纸面尺寸；不合格直接显示原因，密度仅给提示。正文采用Obsidian原生图片引用，按90mm设计、文字至少8.5pt、线条至少0.5pt、图高最多90mm，推荐30–70mm；图意、遮挡和字体仍需人工核对。

受管附件采用稳定题目身份与完整内容哈希，原字节保存、修改另存、读取复核哈希；旧图保留给历史正文与全库备份。正式改题通过diagrams提案新增／替换SVG，批准前不落附件，新旧图在审核中心及助手既有详情可核对，批准后沿用正式改题journal与Ledger回执。

A4、屏幕及展示板离线HTML保留向量原件。打印整图换栏，实际窄栏复核字号和线宽；SVG缺失、解码或尺寸失败均明确报错。展示板排版失败会清空有效版面并禁止沿用旧成功版面记录纸面，改宽后可恢复。原位图切片与截图契约继续有效。

AI和MCP看图按需转PNG，正式SVG不变；转换依赖可选Playwright及Chromium，离线且限制并发、缓存、超时和子进程回收。网页单／多图识别已通过真实HTTP至本机合成模型边界验证。本地版本仍为v2.9.0，未部署、未重启、未推送。

## 影响文件

已通过git diff --name-status并结合未跟踪清单逐项复核，本任务没有接管既有未提交改动。

- 新增 `omrs/question_svg.py`、`omrs/question_diagrams.py`：统一规范、不可覆盖发布、受审改图与PNG派生。
- 修改 `omrs/creation.py`、`omrs/uploads.py`、`omrs/question_images.py`、`omrs/http/core.py`、`omrs/ai_assist.py`：录入、共享读取、响应隔离与模型兼容。
- 修改 `omrs/question_update.py`、`omrs/question_update_journal.py`、`omrs/agent/tools/write.py`、`omrs/mcp/tool_docs.py`：提案白名单、原图快照、附件先落盘、回执和工具说明。
- 修改 `omrs/exporting.py`、`omrs/mcp_exports.py`、`omrs/export_templates/a4-layout.js`、`omrs/export_templates/a4.js`、`omrs/export_templates/board.js`：向量内联、重复引用预算、整图分页与失败反馈。
- 修改 `omrs/backup_store.py`、`omrs/optimization.py`：SVG计入备份与图片容量，压缩保持跳过。
- 修改 `assets/app/core/uploads.js`、`assets/app/features/create/quick.js`、`assets/app/features/create/quick-view.js`、`assets/app/features/ai-review/preview-view.js`：上传状态、规范提示和新旧图审核预览。
- 修改 `assets/app/features/board/detail.js`、`assets/app/features/board/preview.js`、`assets/app/features/board/print.js`：识别排版失败来源，清除失效版面与打印任务，禁止错误纸面记录。
- 新增 `tests/test_question_svg.py`、`tests/e2e/question_svg.py`；修改 `tests/test_mcp_question_update.py`、`tests/app/board-preview.test.mjs`、`tests/app/board-print.test.mjs`：真实SDK、审批／恢复／备份／篡改保护、超时清理和前端回归。
- 新增 `AI/question-svg.md`、`AI/plans/svg-questions/` 及本日志；修改根README与AI的README、agent、ai-review、api及mutations/queries分册、backup、board、data、environment、export、inbox、ledger、mcp、security、frontend的ai-review/architecture/board-ui/create分册、plans索引；日志索引由门禁生成。

## 已执行验证

- git status --short：无已有改动；只读核对录入、读取、审核、打印、备份和历史链路。
- Playwright实际启动Chromium151.0.7922.34成功；Python可导入Playwright、Pillow、MCP。
- `PYTHONPATH=tests:. python3 -m unittest tests.test_question_svg tests.test_question_update tests.test_question_images tests.test_question_creation_metadata tests.test_mcp_tool_docs tests.test_mcp_exports tests.test_mcp_question_update tests.test_backup_recovery tests.test_board_export tests.test_ai_review tests.test_agent_tools tests.test_zuoyebang_svg tests.test_ai_assist_taxonomy -q`：最终164项全部通过。日志 `/tmp/omrs-svg-backend-final.log`；包含真实隔离MCP服务与SDK原生PNG返回、历史恢复、备份还原、审批冲突及实际超时子进程回收。
- `node --test tests/app/*.test.mjs`：最终575项全部通过，日志 `/tmp/omrs-svg-node-final.log`。`python3 tests/app/run_browser.py`：35项通过，日志 `/tmp/omrs-svg-components.log`。
- `python3 tests/e2e/create.py`：122/122；`python3 tests/e2e/ai_review.py`：48/48；`python3 tests/e2e/board.py`：73/73。分别见 `/tmp/omrs-svg-create.log`、`/tmp/omrs-svg-review.log`、`/tmp/omrs-svg-board.log`；均为临时Vault、随机高端口，移除了生产控制环境变量。
- `python3 tests/e2e/question_svg.py`：最终23/23，日志 `/tmp/omrs-svg-e2e-final.log`；实际经过录入、小字拒绝、SVG安全响应、共享弹窗、桌面／手机深浅审核、批准换图、原图保留、单／多图模型请求、PNG解码、离线答案隐藏、A4／展示板PDF、窄栏阻止与修正恢复。模型HTTP边界使用本机合成服务，检查收到的图片均为至少1000px的PNG；无付费模型调用。
- `python3 -m unittest tests.smoke_a4_print tests.smoke_board_print -q`：13项全部通过，日志 `/tmp/omrs-svg-print-regression.log`。SVG专项实际PDF与截图位于 `/tmp/omrs-svg-browser-6m4qbicb`；人工查看了专项A4及手机深色审核截图，配图清晰，无截断与横向溢出。
- `python3 tests/check_ui.py`：全仓0问题。`python3 tests/check_contrast.py`：58组、0失败。
- `python3 tests/visual/run.py --ref HEAD --pages create,board --out /tmp/omrs-svg-visual`：8组前后对比、0差异、0脚本错误。默认录入停在上传工作区，常规页面没有新增视觉差异；SVG新增／审核状态由专项截图覆盖。
- `python3 tests/check_docs.py --write-log-index`、`python3 tests/check_docs.py --diff HEAD` 与 `git diff --check`：最终退出码均为0；文档160个、0问题，3条既有大文件提醒（前端执行说明、v2计划及根README）。文档门禁早先仅因新增日志尚未生成索引而失败，收尾生成后通过。

早期验证失败与重跑：新测试最初误用Ledger的ok字段，改为valid；一次误加载不存在的test_uploads、一次MCP测试未带PYTHONPATH，均修正入口后通过。SVG E2E初次受同目录mcp.py遮蔽SDK，后续被未关闭的题目弹窗挡住批准按钮，截图还发现复用桌面上下文导致手机侧栏遮挡；已分别修正导入路径、关闭弹窗及逐视口新建上下文，最终23/23。SDK环境探测只启动Playwright驱动曾产生清理warning，改为实际启动并关闭浏览器后最终组合不再出现；既有作业帮测试仍报告Pillow getdata的弃用提示，不影响通过。

## 未执行验证

- Obsidian桌面／手机真机和实际打印机未验证：当前环境没有这些设备；不承诺设备字体替换、图意与标注遮挡由自动检查保证。
- Windows真机、taskkill及目标文件系统硬链接能力未实测；无目录FD的存储分支已在Linux用替代能力标志验证，不能替代Windows验收。
- 未调用真实模型供应商、未跑全仓所有可选服务门禁；已运行本任务涉及的后端、页面与打印检查。没有生产部署、systemd操作、真实题库验证或Git推送授权，这些均未执行。
