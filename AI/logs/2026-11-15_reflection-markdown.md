# 2026-11-15 统一 Markdown 错因记录

> **任务**
> - 标识：reflection-markdown
> - 状态：已交付

## 背景

用户原话：「做成统一的吧」「留在md文件」「然后允许特定格式比如日期」「错因只显示在错因记录 的页面」「然后错因记录默认先显示历史而不是新增」「备注 / 错因 字段删去错因」「如何?」。导出范围选择：「仅调整页面，导出保留错因（推荐）」。执行者为 Codex，完整模式；基线 2fe4fae，开始时工作区干净。承接问题中心 U5 的新需求，替代旧版的双源保存及默认新增；不沿用旧任务的生产发布授权。

## 行为变化

错因以原题 Markdown 为唯一当前正文来源，支持三级日期标题、日期未知和任意 Markdown 正文。应用使用引用块及隐藏元数据保留稳定身份、来源、问题关联、修订与撤回；旧裸文本作为日期未知记录，只读不改文件。旧数据库记录在正常 serve 启动时幂等转入原题，保留原编号、原文和旧证据；归档且无工作文件的旧记录仍可只读查询。

页面只在「错因记录」中显示错因，默认选中历史页签；顶部新增仍可直达编辑器，草稿保护保留。原「备注 / 错因」改为「备注」，保留其它备注与关联。直接保存 Markdown 后历史即时刷新；正文与校验哈希来自同一次读取，旧表单及审批不能覆盖外部改动。打印和导出保留有效错因，排除撤回、隐藏元数据和旧版本。

文件、问题回执和 Ledger 正文事实由恢复意图收束，进程中断后按提交状态回滚或补齐；不改变学习状态。旧整段 cause 写入口继续兼容纯旧文本，但不能覆盖结构化历史。本次保持 v2.11.1，不创建提交、推送或生产变更。

## 影响文件

已用 git diff --name-status 和未跟踪文件清单复核，开始时无用户未提交改动，全部变更属于本任务。

- 存储与恢复：新增 omrs/reflection_markdown.py、omrs/reflection_journal.py；修改 omrs/problems.py、omrs/cli.py、omrs/backup_store.py，统一正文、旧库归并和中断恢复。
- 兼容与审核：omrs/question_update.py、omrs/question_ops.py、omrs/problem_review.py、omrs/agent/tools/{common,problems,write}.py、omrs/mcp/tool_docs.py、omrs/exporting.py，补齐原文哈希、防止旧工具整段覆盖，并让导出读取有效记录。
- 页面：新增 assets/app/domain/question/notes.js；修改同目录 view.js、editor.js、reflections.js、reflections-view.js，统一历史、备注去重、日期显示、原位刷新和迟到读取保护。
- 测试：新增 tests/test_reflection_markdown.py；修改 tests/app/{question,reflections}.test.mjs、tests/e2e/{notes_markdown,reflection_layout}.py，覆盖真实文件、异常事务、四处子进程退出和页面主路径。
- 文档：AGENTS.md、AI/README.md、根 README.md；AI/problems.md、data.md、data/storage.md、ledger.md、api.md、api/mutations.md、agent.md、mcp.md、ai-review.md、security.md、backup.md、export.md、environment.md、frontend/{qview,problems,architecture}.md；同步问题中心 plan/progress、本日志及自动生成 routes.md、logs/log.md。

## 已执行验证

以下均实际执行，服务测试使用临时 Vault、随机端口；去掉 OMRS_SYSTEMD_SERVICE 和 OMRS_BOXDETECT_CONTROL。完整 Python 使用 /root/workspace/apps/releases/omrs-zyb-deps-20261011/.venv/bin/python；未联网安装依赖。持久证据在 /root/workspace/artifacts/omrs-reflection-markdown-20261115/。

| 验证 | 命令与结果 |
|---|---|
| 完整后端 | python -m unittest discover -s tests -p 'test_*.py' -q：最终 1197 项全部通过，181.142 秒，退出 0；含新增 13 项 Markdown/恢复测试 |
| 并发与兼容 | python -m unittest tests.test_reflection_markdown tests.test_problems tests.test_mcp_problems tests.test_question_update tests.test_math_delimiters -q：64 项通过；随后完整套件覆盖相同最终后端 |
| 前端模块 | node --test tests/app/*.test.mjs：595 项通过，0 失败、0 跳过 |
| 组件浏览器 | python3 tests/app/run_browser.py：35 项通过 |
| 页面主路径 | python3 tests/e2e/notes_markdown.py --out /tmp/omrs-reflection-unified/notes-complete：34 项通过；默认历史、日期、编辑刷新、导出及学习状态不变 |
| 布局与草稿 | OMRS_REFLECTION_EVIDENCE=/tmp/omrs-reflection-unified/layout-complete python3 tests/e2e/reflection_layout.py：44 项通过，双主题 1440/1160/1024/760/390/320px 无页面横向溢出 |
| 关联页面回归 | tests/e2e/problems.py 32 项、problems_http.py 14 项、questions.py 106 项、instant.py 27 项、feedback.py 43 项，全部退出 0 |
| 打印 | python3 -m unittest tests.smoke_a4_print tests.smoke_board_print -q：15 项通过 |
| 前后视觉 | python3 tests/visual/run.py --ref HEAD --pages questions --out /tmp/omrs-reflection-unified/visual：四组像素差异均为 0，无脚本错误或页面横向溢出 |
| 前端纪律 | python3 tests/check_ui.py：全仓 0 违规；python3 tests/check_contrast.py：58 组全部达标 |
| 文档与补丁 | python3 tests/check_docs.py --diff HEAD：165 份、0 问题；git diff --check：退出 0。路由及日志索引分别由 --write-routes、--write-log-index 生成 |

另用 git archive HEAD 基线及当前源码各启动真实 serve，以相同合成旧题、旧数据库记录拍摄浅深主题 × 1440/390px 前后共 8 张弹窗截图。启动后验证旧字段加旧库合计两条、旧 entry 转身份索引、学习状态不变、无页面横向溢出或脚本错误；已查看最终桌面截图。差异逐项为：错因从备注移到历史区、默认历史选中且新增表单隐藏、日期或未知日期明确显示、原备注保留关联。题库列表页没有预期视觉变化，故四组列表比较为零；弹窗变化见 modal-compare/。

失败与修正：初次完整 1195 项中有 1 项公式分隔符回归，修正错因摘要的导出规范化后先 1195 项全过，最终增加两项并发/日期覆盖后 1197 项全过。初次 Node 为 594/595，通过更新不再成立的「备注展示错因」断言后 595 全过。浏览器补充用例曾因备注定位命中「创建信息」和重开后未等待异步历史而失败，改用精确定位和自动重试等待后最终 34 项通过。布局重跑曾误用不支持的 --out 参数，改为环境变量后 44 项通过。原始失败日志保留，不用后续成功覆盖。

证据目录含最终及失败日志、notes-complete/、layout-complete/、regressions/、modal-compare/ 和 visual/report.html。文档门禁另有三条既存体积提醒，未将无关计划和根 README 拆分；本次受影响模块均不超过 40KB。

## 未执行验证

未执行生产部署、真实 Vault 迁移和远端推送，本次授权只涵盖本地实现与验证。未做实体手机、实体打印机或真实付费模型调用；页面及打印使用真实 Chromium，AI/MCP 权限和审批使用合成内容与临时实例。没有其它待完成的本地功能项。
