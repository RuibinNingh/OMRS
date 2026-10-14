# 2026-10-14 MCP 公式定界符自动转换

## 背景

用户提供两球相遇的完整答案，询问「能不能自动识别转LaTeX」，随后明确「可以这样,直接转换美元符号」。样例本身是 LaTeX，但题目、聊天与导出原有公式解析只识别美元定界符；MCP 创建 / 修订没有转换反斜杠定界符。

执行者为 Codex，完整模式；基线为 `9bc4201`，开始时工作区干净。任务在 `codex/mcp-math-delimiters` 完成，不属于进行中的计划；版本保持 v2.7.0。

## 行为变化

- MCP 创建 / 修订草稿时，文字块、块说明与实际提交的错因 / 备注自动转换成对定界符；同一行 `\(...\)` 转 `$...$`，可跨行 `\[...\]` 转 `$$...$$`。
- MCP 正式改题提案和网页人工修订使用同一转换，预览和批准后的正文一致；正式改题仍须批准。原请求摘要、重试回执及 `cause_statement` 原话保留，人工保护与版本校验不变。
- 题目共享预览、聊天正文及摘要在 Markdown 分块前转换；已有草稿 / 正式题目可直接显示，不批量改写文件、数据库和历史 blob。KaTeX 尚未加载时不缓存这类公式的源码降级结果。
- A4、屏幕版与展示板新导出在正文块化与备注解析前转换，保留跨行公式完整块，不回写旧正文。公式命令与换行保持；代码、已有美元公式、转义和未配对定界符保持原文。

## 影响文件

已用 `git diff --name-status` 与 `git status --short` 复核本任务路径；没有其它维护者的改动。

- `omrs/math_text.py` 为无 I/O 的转换规则；`omrs/drafts.py`、`omrs/draft_write.py`、`omrs/mcp/question_write.py` 接入业务正文；`omrs/mcp/tool_docs.py` 说明兼容行为；`omrs/exporting.py` 接入三种导出。
- `assets/app/domain/question/math-text.js` 为浏览器共享转换；`markdown.js` 规范化后缓存 / 渲染；`assets/app/features/assistant/md.js` 在聊天分块与摘要前使用同一规则。
- `tests/fixtures/math_delimiters.json` 包含用户完整答案与 14 项边界，Python / Node 共用；`tests/test_math_delimiters.py`、`tests/app/math-delimiters.test.mjs`、`tests/test_mcp_question_update.py` 覆盖存储、重试、审批和渲染；`tests/e2e/math_delimiters.py` 自动进入统一门禁的 E2E 发现列表。
- 同步 `AI/mcp.md`、`AI/drafts.md`、`AI/ai-review.md`、`AI/data.md`、`AI/ledger.md`、`AI/api.md`、`AI/api/extensions.md`、`AI/export.md`、`AI/environment.md`、`AI/frontend/qview.md`、`AI/frontend/assistant.md`、`AI/frontend/architecture.md` 与根 `README.md`；任务索引由检查器生成。

## 已实际执行的验证

以下服务与浏览器命令均清除 `OMRS_SYSTEMD_SERVICE` 和 `OMRS_BOXDETECT_CONTROL`；所有业务写入使用临时 Vault、合成数据和随机高端口。

| 命令 | 结果 |
| --- | --- |
| `python3 -m unittest discover -s tests -p 'test_mcp*.py' -q` | 130 通过，0 跳过；含真实 SDK 改题转换 / 人工修订 / 批准 / 重试 |
| `python3 -m unittest tests.test_math_delimiters tests.test_drafts tests.test_agent_draft_tools tests.test_draft_p3_http tests.test_draft_p4_http tests.test_question_update tests.test_ai_review tests.test_board_export tests.test_export_fonts -q` | 111 通过 |
| `python3 -m pytest tests/test_report_export.py -q` | 7 通过 |
| `node --test tests/app/*.test.mjs` | 519 通过，0 失败 / 跳过 |
| `python3 tests/app/run_browser.py` | 34 通过，0 页面错误 |
| `PYTHONPATH=.:tests python3 tests/smoke_a4_print.py` | 5 通过 |
| `PYTHONPATH=.:tests python3 tests/smoke_board_print.py` | 7 通过 |
| `python3 tests/e2e/math_delimiters.py` | 19/19；完整答案 16 公式、其中 7 行间公式；真实 MCP → 审核 → 网页入库 → 新 / 旧题详情 → 三种离线导出 |
| `python3 tests/e2e/questions.py` | 104 通过，0 失败 |
| `python3 tests/e2e/assistant.py` | 59/59 |
| `python3 tests/check_ui.py` | 五类 UI 违规计数均 0 |
| `python3 tests/check_contrast.py` | 58 组，0 不达标 |
| `python3 -m unittest tests.test_mcp_tool_docs -q` | 完成说明修改后再验，1 通过；参数校验契约不变 |
| `python3 tests/visual/run.py --ref 9bc4201 --pages questions,ai-review,assistant --out /tmp/omrs-math-visual` | 三页 × 双主题 × 桌面 / 手机，共 12 组前后对比，差异全为 0%；脚本错误、行内样式、小目标和页面横向溢出均 0 |

专项产物在 `/tmp/omrs-math-e2e-jcbsesd3`，包含双主题两档审核截图、三种离线 HTML / 截图与 checks.json；已实际查看审核桌面截图，公式分式与方框正确。通用视觉夹具原有美元公式，因此 12 组无差异；新增反斜杠样例的可见行为由专项 E2E 覆盖。

执行修正：打印冒烟直接运行缺少模块搜索路径，补 `PYTHONPATH=.:tests` 后实际通过；专项浏览器初稿引用了不存在的外壳字段，改用真实题库单元格点击及实际导出就绪信号后 19/19 通过。前端样例计数以实测 16 个公式为准。

文档与提交收尾：`python3 tests/check_docs.py --write-log-index` 已生成索引；`python3 tests/check_docs.py --diff HEAD` 检查 117 份文档，0 问题、3 条大小提醒（两个计划文件及根 README，不涉及本次逻辑）；`git diff --cached --check` 通过。提交包含本任务代码、测试、模块文档与任务日志。

## 未执行的验证与下一步

未执行生产部署、重启、远端推送和真实客户端会话验收；没有相应授权。没有改数据库表、依赖、路由或版本，不重复运行全仓升级 / 回退及真实模型链路。当前功能实现与隔离验证完成；生产使用需另行部署本提交。
