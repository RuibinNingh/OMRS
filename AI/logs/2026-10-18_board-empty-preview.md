# 2026-10-18 展示板空板预览修复与 v2.8.4

## 背景

用户要求「那么制定修复计划」「版本号+0.0.1」，随后明确要求实施确认的 v2.8.4 计划。执行者为 Codex，完整模式；基线 94fa3b2，计划位于 AI/plans/board-empty-preview/。

已在隔离 HTTP 与真实 Chromium 中复现：0 题板发起导出，服务端 RuntimeError 被映射为 500，界面显示「预览生成失败」；有题板正常生成一页预览。文档曾声明续印前提失败返回 400，但当前代码实际返回 500，以实测为准修正实现和文档。

任务开始时唯一已有改动为 AI/plans/omrs-maintenance/validation.json，SHA256 为 3d3cdbd203731931981a4db6d940cae48878e1069d55c1c2008c361aa58be9f9。该文件不属于本任务，不修改、不纳入提交。

## 行为变化

- 预览、按钮状态与打印协调共用有效题目过滤，排除缺失／停用及仅新增模式的已印题，保留原有有效打印范围规则。
- 空板显示「板里还没有题，添加题目后可预览」，全部停用／缺失显示「当前没有可打印的题目」。无内容时打印／下载提前拦截，加题自动恢复预览。
- 空板与清空最后一题会取消在途及延迟任务、使旧 token 失效、清空文档与版面，iframe 节点和 morph 边界保持。移除响应已确认空内容时即撤下预览，不等待列表重读。
- 控制器合并同内容的在途同步，成功／失败回调均检查请求及当前内容归属。切板或重试即清除旧错误；真正网络或生成失败保留原因并撤下旧文档。
- BoardExportUnavailable 继承 RuntimeError，携带 status=400，仅替换三个明确业务前提失败；原错误体、HTML 成功响应和未知异常 500 保持。
- 版本统一升级 v2.8.4，未切换生产源码或服务。

## 影响文件

- assets/app/features/board/：有效打印题目与提示、预览清空生命周期、详情回调归属、舞台空状态和导出拦截。
- omrs/exporting.py：专用空内容业务异常与三处失败分支。
- tests/app/：增加空板控制器／导出测试，扩展 iframe 协议测试，并给既有版面替身补齐真实响应中的板 ID／模式。
- tests/e2e/board.py 与同目录 board_empty.py：真实 HTTP 与浏览器专项、四档截图；不注入生产全局或连接真实题库。
- tests/test_http_boundaries.py：真实端点的空内容、续印前提与未知异常状态验证。
- AI/frontend/board-ui.md、AI/frontend/architecture.md、AI/board.md、AI/export.md、AI/api.md 及其 boards 分册：当前行为与验收入口。
- 版本定义、侧栏、README、AI/README.md 和 AI/changelog.md：统一版本与用户可见行为。
- AI/plans/board-empty-preview/、计划索引、本日志及自动日志索引：计划、进度和实际验证。

## 验证

所有 Python 命令使用 /root/workspace/apps/releases/omrs-zyb-deps-20261011/.venv/bin/python，实际版本为 Python 3.13.5。测试使用临时 Vault、随机本机端口，子进程清除 OMRS_SYSTEMD_SERVICE 与 OMRS_BOXDETECT_CONTROL；最终浏览器序列另清除 OMRS_TEST_CDP_URL，使用独立 Chromium。

| 实际命令 | 结果 |
|---|---|
| python3 -m unittest discover -s tests -p 'test_*.py' -q | 1084 项通过，退出 0；日志 /tmp/omrs-board-empty-root-tests.log |
| node --test tests/app/*.test.mjs | 最终 561 项通过，退出 0；日志 /tmp/omrs-board-empty-node-tests.log |
| python3 -m unittest tests.test_asset_cache tests.test_web_assets -q | 版本更新后 17 项通过，退出 0 |
| python3 tests/check_ui.py | 全仓 0 处问题，退出 0 |
| python3 tests/check_contrast.py | 58 组全部达标，退出 0 |
| python3 tests/e2e/board.py | 最终 73 项通过，退出 0 |
| python3 -m unittest tests.smoke_board_print -q | 7 项通过，退出 0 |
| python3 tests/app/run_browser.py | 35 项通过，退出 0 |
| python3 tests/e2e/board_picker.py | 31 项通过，退出 0 |
| python3 tests/visual/run.py --ref 94fa3b2 --pages board --out /tmp/omrs-board-empty-v284 | 四组对比均无差异，无页面脚本错误，退出 0 |
| python3 tests/check_docs.py --write-log-index | 已生成本次任务索引，退出 0 |
| python3 tests/check_docs.py --diff 94fa3b2 | 152 份文档，0 问题、3 条既有体积提示，退出 0 |
| git diff --check | 通过 |

规划基线为 Node 展示板 125 项、Python 展示板 51 项。实施首轮 Node 发现两份旧替身缺少真实版面的 board_id／mode，补齐后通过；随后增加已显示错误的清除与失败时撤下文档回归，Node 全仓由首轮 559 增至 561。未删减原断言。全量 Python 后的改动限于前端、版本与文档，前端重新运行 Node 和浏览器序列，版本另跑资源测试。

最终浏览器序列的命令、退出码与耗时保存在 /tmp/omrs-board-empty-browser-validation.json，对应日志为 /tmp/omrs-board-empty-final-{print,components,board,picker,visual}.log。文档门禁的三条体积提示来自既有 AI/plans/frontend-rearch/exec-2026-09-26-codex.md、AI/plans/v2.0.0/plan.md 与 README.md，不涉及本次新增文档。

## 浏览器与视觉产物

空状态专项保存 1440／390px × 浅／深主题的空板、加题、清空、全停用、全缺失共 20 张截图，目录为 /tmp/omrs-board-empty-v284-states，含 checks.json。首轮已实际查看深色桌面与手机空板截图。真正网络失败与服务端 500 的原因保留在错误提示的 title 中。

前后对比报告为 /tmp/omrs-board-empty-v284/report.html，审计数据为同目录 audit.json。普通有题板的四组对比逐项结果如下，均无像素差异，说明原有纸面与布局保持：

- 浅色桌面：差异 0%，无页面脚本错误。
- 浅色手机：差异 0%，无页面脚本错误。
- 深色桌面：差异 0%，无页面脚本错误。
- 深色手机：差异 0%，无页面脚本错误。

各组基线与当前的小点击目标、行内样式、横向溢出均为 0。空板专项的预期变化另由上述 20 张状态截图与浏览器断言验证：空板撤下纸面、页码清空、打印／下载禁用并显示中性提示；加题自动恢复，清空、全部停用或缺失重新进入空状态。它们是状态验收截图，不冒充空板的基线像素对比。

## 偏差、遗留与下一步

实现未改变目标、接口响应格式或数据模型；复用既有中性空状态样式，无新增设计 token。未知异常仍为 500；没有把空错误全部吞掉。

未执行生产部署、服务重启、推送或真实打印机出纸，均不在本次授权范围；未调查真实「函数」板为何为 0 题，未改真实题目、引用和纸面记录。

本任务的实现、全部计划门禁、文档与截图均已完成，按一个 v2.8.4 本地提交交付。已复核实际变化清单，原有 validation.json 指纹保持且不纳入提交。下一步如需生产发布，由获单独授权的维护者按发布流程执行。
