# 2026-10-03 统一审核中心与 MCP 正式改题

## 背景

用户批准 AI/plans/ai-review-center/plan.md 并要求完整实施。执行者 Codex，完整模式，基线 eda4510；开工工作区干净，版本保持 v2.2.1。生产、推送和版本升级不在范围内。

## 行为变化

已实现统一 MCP/助手业务写记录与审批、独立审核中心及原草稿图文审核迁入。正式计划与高风险业务写须人工决定；MCP 改题允许白名单字段提案、人工修订和正式写入。自动业务写登记真实结果，查询、技术缓存及下载快照不进入中心。聊天与中心共享决定，草稿连续审核保留当前筛选与未保存内容。

## 影响文件

已用 `git diff --name-status` 并结合未跟踪新文件复核，全部改动属于本任务，开工无用户未提交改动。

| 范围 | 文件与目的 |
| --- | --- |
| 统一审核 | `omrs/ai_review.py`、`omrs/http/ai_review.py`、HTTP 注册和服务混入；审批、分页、精确回执与历史证据 |
| MCP 与助手 | `omrs/mcp/`、`mcp_operations.py`、`mcp_board.py`、`agent/`；固定分类、唯一决定及实时执行 |
| 正式题目 | `question_update.py`、`question_update_journal.py`、`common.py`；白名单补丁、YAML/图片保护及文件/Ledger恢复 |
| 原领域 | `drafts.py`、`draft_write.py`、`reports.py`；精确意图回执与首次完整架构 |
| 生命周期 | `backup_store.py`、`cli.py`、`locking.py`、`runtime_records.py`；恢复失效、启动收束与只读查询 |
| 前端 | `features/ai-review/`、`domain/ai-review.js`、`domain/image-crop/`；迁入草稿，抽出收件箱实际共用画布 |
| 兼容入口 | 路由、外壳、助手、录入、历史和MCP权限页；旧链接、导航、角标和新权限 |
| 验证 | 相关 Python、SDK、Node、E2E、视觉夹具；门禁升级基线独立、隔离服务诊断 |
| 文档 | 映射模块、根README/AGENTS、计划/进度、路由和日志索引 |

## 验证

已执行：开工 git status --short、git log；各专项与全仓门禁结果见下文。调查阶段结果不冒充实现验收，全部验证使用合成临时 Vault 与随机端口。

## 实现调整

使用公共 ai_review.db 作为唯一审批权威；自动草稿/报告按工具调用记录，原领域 request_id/回执保持实际幂等。MCP记录查询以精确身份及摘要匹配的原生回执展示真实结果，不改变底层审批或重放业务；记录列表、状态筛选、总数与详情一致。

提交粒度偏差：各切片按计划顺序实现和验证，但审批存储、两个来源适配与草稿页面迁移相互依赖，最终以一个完整集成提交交付，使本地提交快照包含可运行的中心、全部安全回归、文档与进度。目标、范围、审批契约和验收条件未变；不拆出缺少唯一权威服务的中间提交。

## 实施中验证记录

已实际执行：运行历史 E2E 34/34；MCP 扩展网页审核/PIN/重复决定 17/17；录入页 E2E 114/114；仪表盘、数据复盘重跑退出码0。Node 443 项、组件浏览器、打印冒烟、UI 与对比度门禁均通过。并行协作者已提供草稿多块59/59、P4 24/24、助手59/59、MCP设置39/39、P4工具11/11、Session网页17/17及领域安全测试记录，最终统一门禁将复核实际最终源码。

首轮全仓门禁在并行集成中执行，出现旧工具清单计数、旧页面选择器、尚在修订的模块导出与新库失败状态启动收束问题；逐项定位并修复，不将失败或跳过算通过。完整结果与截图路径在最终验收后补齐。新工具的 reason 无旧schema兼容需求，固定为必填非空。

历史扫描用SQLite游标和临时Ledger身份索引，不在Python加载整条历史正文。页级分页采用offset并兼容cursor字符串；不改审批、范围或用户目标。

最新全仓 Python 单测已实际运行 790 项通过，无 SKIP；证据 `/tmp/omrs-review-unit-final.log`。旧 MCP 确认入口无版本参数仅兼容首版，修订后无版本或旧版本返回409；真实SDK与HTTP回归已通过。

门禁原先把本次差异基线同时用于历史升级夹具，但升级夹具固定验证17d6d84的UID-only旧语义，eda4510已经完成该迁移，导致旧阶段断言失败。`run_gates.py` 增加独立 `--upgrade-ref`，默认17d6d84，`--ref eda4510`继续用于文档/视觉。升级六阶段已实跑通过，证据 `/tmp/omrs-ai-review-upgrade-gate/results.json`；没有放宽历史断言。

真实浏览器发现并修复手机列表/详情布尔属性被模板吞掉、同秒草稿排序不一致、空队列维护入口和新版角标隐藏规则。相关检查加到当前测试，不删减原图文/框选/连续入库验收。

旧代码与新代码的恢复安全实证保存在 `/tmp/omrs-review-safety-audit/comparison.json`：旧eda4510在领域写入前故障后的GET会实际写盘一次并删除板，当前GET写盘0次且保留板；旧库恢复成功与恢复失败回退后均可沿用旧批准，当前两种情形均为interrupted/vault_changed且保留板。对应持久回归包含GET、恢复成功和恢复失败三条路径。

全部门禁入口已完整执行：`/tmp/omrs-review-gates-final/results.json` 44个门禁中42个通过，助手/草稿测试遇到首次建库并发503及旧页面定位假设。专项通过后，`/tmp/omrs-review-gates-corrected/results.json` 再次暴露助手初始化竞态与P4测试提前判完成；保留失败证据，不用早先单次通过替代故障定位。全仓视觉48组对比通过、无脚本错误，24组有差异；额外16组已启用助手/设置/历史/录入比较，新中心四组独立审计通过并已实际看图。

审核计数503已硬暂停复现：真实 `executescript` 首次建草稿表后、`ALTER revision` 前抛 `sqlite3.OperationalError: no such column: revision`。新表改为一次声明当前全部列，旧库迁移保持；暂停窗口回归在旧实现失败、当前通过。另覆盖文件已出现但表未建立的窗口，并验证坏架构仍报错。HTTP提示保持脱敏，安全SQLite诊断仅由临时测试入口保存。

P4训练入库的旧浏览器等待条件把详情暂时清空当成完成，随后导航时提交仍忙。等待条件改为真实下一份草稿且提交不忙，不放宽产品行为或延长超时来掩盖错误。

普通页面验收改用共享open_app，PIN路径仍实际填写并解锁。路由/PIN临时fixture使用现有静态入口背景，避免并行WebGL干扰；默认黑洞和自定义背景专项已经独立通过。未运行外部冻结boxdetect模型E2E：没有更改模型，未提供冻结数据，不触碰真实训练材料；SDK与浏览器要求均实际执行。

## 视觉差异解释

全仓48组报告 `/tmp/omrs-review-gates-final/visual/report.html`。每页桌面浅/深两组差异如下；手机浅/深24组全部0。差异均为新增审核中心导航，页面主区域未漂移。

| 页面 | 浅色桌面 | 深色桌面 | 差异原因 |
| --- | --- | --- | --- |
| 仪表盘 | 0.250% | 0.243% | 新导航和下方侧栏项位置 |
| 数据复盘 | 0.092% | 0.090% | 新导航和下方侧栏项位置 |
| 题目库 | 0.387% | 0.378% | 新导航和下方侧栏项位置 |
| 展示板 | 0.108% | 0.099% | 窄导航新增审核中心 |
| 目录 | 0.247% | 0.232% | 新导航和下方侧栏项位置 |
| 复习调度 | 0.113% | 0.111% | 新导航和下方侧栏项位置 |
| 即时练习 | 0.388% | 0.378% | 新导航和下方侧栏项位置 |
| 反馈录入 | 0.386% | 0.375% | 新导航和下方侧栏项位置 |
| 录入题目 | 0.387% | 0.378% | 新导航；草稿入口跳转中心 |
| 历史记录 | 0.357% | 0.351% | 新导航；旧确认入口改跳中心 |
| 报告 | 0.385% | 0.379% | 新导航和下方侧栏项位置 |
| 设置 | 0.307% | 0.298% | 新导航；改题权限默认不授予 |

额外16组报告 `/tmp/omrs-ai-review-visual-final/report.html`：录入/历史/设置各四组与上表同因，手机均0；已启用助手四组为桌面浅0.803%/深0.776%、手机浅1.703%/深1.640%，包含新导航、审批权限欢迎说明及其正常换行。最终新中心单独报告 `/tmp/omrs-ai-review-audit-scoped/report.html`，桌面两栏、手机纵向前后对照，四档无溢出、过小目标、行内样式或脚本错误；最小字号12px。

## 最终验收

首次完整运行后按实际修改影响重跑，原失败结果保留。44类默认门禁已有通过证据，不能表述为一次连续运行全绿；各来源记录见下表，最终文档单独复核。

| 验证 | 最终结果与证据 |
| --- | --- |
| 全仓Python | 798项通过，无跳过；`/tmp/omrs-review-gates-verified/unittest.log` |
| 正式改题真实SDK | 3项完整闭环通过，包含于上述798项；默认权限、提案/人工修订/Web批准/重试、撤权与非法补丁 |
| Node | 449/449，无跳过；`/tmp/omrs-review-gates-corrected/node.log` |
| 中心真实浏览器 | 47/47；`/tmp/omrs-review-gates-corrected/e2e-ai_review.log`，含双标签、脏输入、旧链接及320/390/1024/1440px深浅主题 |
| 助手真实浏览器 | 59/59；`/tmp/omrs-review-gates-verified/e2e-assistant.log`，中心允许后原对话继续，真实文件与提交核验 |
| 完整草稿 | 75/75；`/tmp/omrs-review-drafts-ready.log`，含丢响应、安全重试、触摸、训练与连续审核 |
| 草稿多块/P4 | 59/59与24/24；corrected的`e2e-drafts_blocks.log`及`/tmp/omrs-review-p4-ready.log` |
| 外壳 | 24/24；`/tmp/omrs-review-gates-verified/e2e-shell_router.log` |
| 其余默认门禁 | pytest导出、组件浏览器、打印、UI/对比度、其他E2E、六阶段升级、全仓视觉；`/tmp/omrs-review-gates-final/results.json`中各项退出0 |
| 受影响前端重跑 | Node、UI、对比度、中心、草稿多块退出0；`/tmp/omrs-review-gates-corrected/results.json` |
| 文档与差异 | `python3 tests/check_docs.py --diff eda4510` 检查101文档、0问题；两条既有大型计划体积提醒。`git diff --check` 退出0，路由和日志索引均已生成 |

最终重跑命令：`env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/run_gates.py --ref eda4510 --only unittest,e2e-assistant,e2e-shell_router --out /tmp/omrs-review-gates-verified`，三项全部退出0。草稿等待条件修改后另实跑 `python3 tests/e2e/drafts.py` 与 `python3 tests/e2e/drafts_p4.py`，两项退出0；服务仍临时Vault/随机端口，清除生产控制环境变量。

未执行：外部冻结boxdetect模型E2E缺少冻结模型/数据且本任务未改模型；生产、公网/真实在线模型、Windows平台及ChatGPT账户联调不在本批本地验收范围。没有用跳过代替SDK或浏览器通过。未部署、未推送，未升级版本。

遗留：本批功能与安全验收无已知未解决问题。六阶段历史演练明确旧代码UID-only语义不能用于直接降级；回退沿用仓库前向修复原则。下一步是用户安排后续发布，本任务仅交付本地集成提交。
