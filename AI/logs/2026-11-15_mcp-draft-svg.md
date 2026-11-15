# 2026-11-15 MCP 新题 SVG 配图

> **任务**
> - 标识：mcp-draft-svg
> - 状态：已交付

## 背景

用户原话「允许创建题目的时候附上svg」「然后更新mcp说明,使其符合事实」，选择源码与文件都支持，并批准实施计划。执行者Codex，完整模式；基线e09bbd5，开工git status --short为空。执行说明见AI/plans/mcp-draft-svg/plan.md。

## 行为变化

新题支持源码与上传SVG，按原顺序在题目或答案中预览、人工审核入库。SVG与来源截图分开保存，不进入裁图、OCR或训练；MCP读图按配图块返回PNG派生图。工具schema、instructions及示例同步真实能力。

## 影响文件

已用git diff --name-status及git ls-files --others --exclude-standard复核本任务改动，开工基线没有其它未提交变更。

- 后端：omrs/draft_svg.py、omrs/drafts.py、omrs/draft_write.py保存配图原字节、迁移、人工暂存及入库恢复；omrs/mcp/server.py、omrs/mcp/queries.py、omrs/mcp/tool_docs.py接通输入、PNG读取、schema、说明与可执行示例；omrs/agent/tools/drafts.py同步共享读取与审核快照。
- 前端：assets/app/features/ai-review/的drafts-svg.js、drafts-review.js、drafts-state.js及preview-view.js，负责预览、说明编辑与安全序列化，复用既有样式。
- 验证：tests/test_mcp_draft_svg.py、tests/e2e/mcp_draft_svg.py新增事务和完整主路径；tests/test_mcp_protocol.py、tests/app/create-drafts.test.mjs适配来源位图与SVG的区别；tests/e2e/mcp_expansion.py补齐既有全部权限操作漏选的问题权限。
- 文档：README.md及AI/下agent、ai-review、api、data及data/storage、drafts、environment、mcp、mcp-storage、question-svg、security、frontend/ai-review、frontend/architecture同步当前契约；plans/mcp-draft-svg与plans/README.md记录计划和进度，logs/log.md由门禁生成。计划索引中的既有SVG发布状态按其progress纠正。版本保持v2.11.4。

## 已执行验证

以下均使用合成临时Vault或静态夹具，服务使用随机高端口并清除OMRS_SYSTEMD_SERVICE与OMRS_BOXDETECT_CONTROL。

| 命令 | 实际结果 |
| --- | --- |
| python3 -m unittest discover -s tests -p 'test_mcp*.py' -q | 149通过，包含新增配图专项9项和官方SDK协议 |
| python3 -m unittest tests.test_drafts tests.test_draft_write tests.test_draft_p3_http tests.test_draft_p4_http tests.test_draft_training tests.test_draft_detect tests.test_agent_draft_tools tests.test_question_svg tests.test_mcp_draft_atomic tests.test_agent_review -q | 124通过 |
| node --test tests/app/*.test.mjs | 600通过，无跳过 |
| python3 tests/app/run_browser.py | 35通过 |
| python3 tests/check_ui.py | 全仓0问题 |
| python3 tests/check_contrast.py | 58组，0不达标 |
| python3 tests/e2e/mcp_draft_svg.py | 27项通过，实际生成A4 PDF |
| python3 tests/e2e/drafts.py | 82项通过 |
| python3 tests/e2e/drafts_blocks.py | 59项通过 |
| python3 tests/e2e/question_svg.py | 23项通过，含A4与展示板PDF |
| python3 tests/e2e/assistant_review.py | 28项通过 |
| python3 tests/e2e/mcp.py | 39项通过 |
| python3 tests/e2e/mcp_expansion.py | 修正既有测试漏选权限后17项通过 |
| python3 tests/e2e/runtime_history.py | 34项通过 |
| python3 tests/e2e/mcp_review_sessions.py | 17项通过 |
| python3 tests/e2e/drafts_p4.py | 24项通过 |
| python3 tests/e2e/ai_review.py | 48项通过 |
| python3 tests/e2e/ai_review_entry.py | 46项通过 |
| python3 -m unittest tests.smoke_a4_print tests.smoke_board_print -q | 15通过 |
| python3 tests/visual/run.py --ref e09bbd5 --pages ai-review --review-kind draft --out /tmp/omrs-mcp-draft-svg-visual | 4组，0差异，0脚本错误 |
| python3 tests/check_docs.py --diff HEAD | 167文档，0问题；三项容量提醒均为基线已有文件 |
| git diff --check | 通过 |

后端、Node、组件和浏览器输出分别保存在/tmp/omrs-mcp-draft-svg-开头的all-mcp.log、related-python.log、all-node.log、components.log、browser.log、existing-e2e.log及final-regression*.log。SVG专项的8张浅深主题390/1440px截图、checks.json、a4.html与a4.pdf在/tmp/omrs-draft-svg-browser-d6txmm3m/，已目视核对桌面深色布局。既有页面前后对比报告在/tmp/omrs-mcp-draft-svg-visual/report.html；新增SVG状态单独留图，不混算为既有页面的零差异。

初轮Node新增用例未设置详情就绪状态导致失败，修正测试夹具后10项通过。旧协议示例验收误把SVG算作来源位图，已更新夹具与断言，53项回归全绿。专项浏览器先遇到同目录mcp.py遮蔽SDK，去除脚本目录后主路径通过；首次导出等待误用展示板专有标记，已改为打印按钮就绪并重跑。初轮失败原因保留在本日志；/tmp同名标准输出文件由重跑覆盖，不将首轮计为全绿。

收尾补跑MCP扩展网页门禁首轮16通过、1失败：基线测试遗漏勾选已有problem:read/problem:write，却断言全部权限。对照HEAD测试及当前权限映射后，只补齐测试操作与默认未勾选检查，权限实现不变；重跑17项全绿，首轮及重跑输出分别保留。此调整属于验证夹具修正，不改变计划契约。

全部门禁完成，以一个功能切片本地提交代码、测试、模块文档、计划与本日志；提交身份以包含本记录的Git提交为准。

## 未执行验证

生产部署、重启及远端推送未执行，本轮授权仅到本地提交；实体手机、Windows/Obsidian客户端、实体打印机和真实付费模型未验证。未跑全仓所有业务回归，本次按受影响模块执行上述门禁。没有读取或写入真实错题；本地无已知功能遗留，生产服务及客户端工具定义须在后续发布和刷新后才具备本次能力。
