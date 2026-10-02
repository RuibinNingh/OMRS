# 2026-10-02 MCP 全量扩展

## 背景

用户批准完整 38 工具扩展，要求 Codex 完整模式连续完成 P0–P7。本批基线 d716157，开工工作区干净。执行说明在 AI/plans/mcp-integration/exec-2026-10-02-expansion.md。生产变更、推送、版本升级不在授权范围。

## 行为变化

P0 只固定规范，无业务代码变化。扩大原计划范围但保留历史执行与发布事实。

## 影响文件

AI/plans/mcp-integration 的总纲、进度、扩展执行说明和本日志；日志索引由检查脚本生成。

## 验证

本批开工只读复核 Git 状态和现有代码。规划基线历史通过 527 Python 和 39 SDK/浏览器，不计入新增功能验收。P0 实跑 docs --diff HEAD：82 文档、0 问题、3 条既有大文件提醒；git diff --check 通过。

## P1 查询

实现 5 个查询工具及共同分页/稳定错误契约；当前正文后续页必查哈希，历史版本只读已登记 blob，草稿图验证来源 SHA 和普通路径。时间线先按题/科目/日期筛选、显示当前修正状态；测试发现 Session 投影 UIDs 实际为对象数组，已按代码修正解析。

影响 omrs/mcp/server.py、queries.py、common.py、question_images.py、runtime_records.py，相关 MCP/查询回归及模块文档。实跑 MCP 专项 73/73（含 5 项新增、真实 SDK，无 SKIP）；MCP SDK/浏览器 39/39；docs 82 文档、0 问题；git diff --check 通过。未运行全量 Python，留 P7。

## P2 分析与报告

新增 4 工具；共享 analytics 在科目/分类筛选后聚合，同名分类拆桶，日期仅筛选练习行为，当前薄弱项和预测保留完整有效反馈口径。报告使用独立 SQLite 预留稳定编号，原子 HTML 和可恢复索引；已删除报告不因技术重试复活。Key 可用权限扩展，但默认保持原两项。

影响 analytics.py、reports.py、mcp/analysis_reports.py、keys.py、server.py、runtime_records.py 及相关回归/文档。实跑 MCP 专项 78/78，无 SKIP。报告文件使用 pytest 函数，unittest 专项收集为 0 后改跑 pytest：7/7；报告浏览器 24/24；docs 0 问题及 git diff --check 通过。全量门禁留 P7。

## P3 草稿修订

共享补丁校验，MCP 单独授权各来源待审核草稿、保留原来源和训练，人工保护整次不写；原助手继续限制本对话。补丁与回执同事务，错因 client_asserted，编辑身份单独记录。影响 draft_write.py/drafts.py、MCP 注册和修订模块、运行错误及测试/文档。

实跑 MCP 82/82、助手草稿 16/16、草稿写入 14/14，无 SKIP；既有 SQLite ResourceWarning 不影响通过。草稿浏览器 75/75；docs 82 文档、0 问题、4 条大文件提醒（data 本批达到 40KB）；git diff --check 通过。

## P4 展示板并发

v4 保留修订/目录版本与 MCP 回执；旧文件读取不迁移，实际写入原子替换。领域锁包住检查和读改写，暂存预览不写纸面历史，回执与变更同次保存。Web 全部写操作携带读取版本，409 保留本地字段并停止重试/关页写入，主动读取需确认丢弃。新增分页板查询。

影响 boards.py/server.py、MCP board_read、板 domain/页面保存/版式载荷/读写适配、板 E2E 和夹具。旧夹具无版本导致准备失败，已按新公开契约更新；新增冲突用例保留旧版本，不能用 helper 掩盖。实跑板 Python 48/48、MCP 84/84、Node 全仓 411/411、组件浏览器 34/34、UI 0、对比度 58/58；板视觉相对 d716157 四对零差异、无脚本错误。板/选板浏览器仍验收中。

选板浏览器发现直接进入题库 hash 时 DATA 有 39 题但页面仍空：题库未订阅初始 data 事件。为恢复本批选板主路径，补一条现有事件订阅，无其它题库重构；记录为直接相关低风险修复。板浏览器并发/主动重读路径 30/30 已通过；首次冲突断言时的延时竞争已用实跑详情核对并重跑通过，业务检查未删减。

选板重复加题发现撤回后详情版本旧于已读取目录；加题在先冲刷本地队列后使用选板列表读到的版本，详情编辑仍使用原详情版本。选板读取采纳完整目录元数据。验收改在完成 toast 后检查服务端，不在浮层关闭时抢读。最终选板浏览器 31/31、Node 411/411；板浏览器 30/30，其余 P4 门禁见上。

## P5 展示板管理与确认

新增13个局部管理工具和本人操作查询，共37工具；独立确认库10分钟期限。严格预览与实际应用共用领域事务，解除锁定不能绕过纸面保护，删除/清空/纸面重置由网页确认。应用前重查Key与板/目录版本和完整影响，领域回执恢复已确认中断操作。有效Key可从网页/CLI编辑六项权限，新增权限默认关闭。Web主来源单独配置，PIN登录保留确认hash，历史页区分预览与完成。

影响 mcp_board.py/mcp_operations.py、MCP board_write/server/keys、boards/server/cli/runtime_records、设置/历史/core API、路由生成器和相关模块文档。测试扩展测试库与真实SDK/网页闭环；完整参数只在确认库，不进入脱敏运行摘要。实跑管理专项12/12（含SDK）及MCP全专项96/96，无SKIP；运行记录14/14、既有SDK/浏览器39/39、运行记录浏览器34/34；新增权限/确认/PIN手机回跳浏览器10/10，Node411/411。UI0、对比度58/58。

P5 组件浏览器34/34；相对d716157视觉8对，历史4对无差异。设置桌面浅/深0.103%/0.100%，手机浅/深4.337%/4.470%：MCP介绍文字扩展导致手机换行和后续卡片下移；视觉检查未发现脚本错误、溢出或过小目标，已查看深色手机截图。首次视觉命令误用空格列表，退出2未执行截图；改用逗号后完成。docs82文档0问题4条现有大文件提醒；git diff --check通过。

## P6 安全导出与关联

最后一个工具export_board使全量达到38；安全附件回调取原字节，拒绝旧路径回退。64MiB/24小时的自包含HTML，工具只返回登录下载地址；独立SQLite完整字节与编号先原子提交，HTML再原子落盘，崩溃可恢复原快照；到期删除HTML/恢复副本保留墓碑。去除已打印按钮，不写纸面/Ledger。运行详情增加板、报告、导出关联入口。

影响exporting/mcp_exports/board_export、MCP注册、Web下载、runtime及历史关联，新增安全导出测试与SDK工作流/浏览器下载验收。实跑MCP104/104（导出7项、真实SDK全链路及22/1/38实时发现，无SKIP）、板48/48，Node411/411；扩展SDK/网页15/15含离线HTML真实浏览器排版、未登录401、MCP凭据403、PIN会话下载。首次导出专项定位SQLite插入占位符数量错误，已修复并全部复跑通过。

P6组件浏览器34/34，UI0与对比度58/58。相对d716157历史/板视觉8对零差异、无脚本错误。docs82文档0问题4条现有大文件提醒；git diff --check通过。新增文件名控制字符过滤在P7全量再验证。

## P7 终检修复

初次全量 Python 563 项有 1 项失败：普通 CLI 顶层导入相对 mcp.common，被无可选依赖回归拦截。稳定 RequestError 移入核心 errors.py，协议模块重新导出同一类，Web/运行模块不再顶层依赖 MCP 模块；既有无 SDK/Pillow 导入回归 17/17 通过。

初次展示板浏览器为29/30，本地留白被晚到详情读取覆盖。新增受控 Node 交错先在旧代码实跑失败（null 不等于6），再以本地编辑使在途读取失效修复；确认期间详情已更换时不写旧对象。E2E 等真实页面挂载与预览就绪后操作，保留全部业务断言；修复后板30/30，选板31/31。

复核契约补齐：MCP 请求触及人工保护目标，即使值相同也整次不写，纯无变化请求仍返回保护建议；清空错因也要求 cause_statement，实际修改标 client_asserted。新增回归覆盖字段/块保护、混合补丁与各来源错因清空。网页改名同时检查目录版本；真实 SDK 对网页写后持旧版本和目录变化后网页持旧目录版本均验证409。

SDK 工作流覆盖全部板管理工具，包含推荐、建目录/板、批量加题、完整排序、留白/置顶、版式、导出、改名、移板、复制、移出引用、申请删目录及网页删除确认。板操作前后 Ledger 与完整 mastery_data.csv 字节保持；已导出快照不因板之后变化而改变。真实服务重启后待确认不应用；缺失导出文件按 SQLite 原字节恢复，再经 PIN 网页确认与下载。

文档集中更新38工具及6权限清单，修正残留v3与旧状态筛选描述。data.md 的本批MCP技术存储拆至 mcp-storage.md，索引与引用同步，使data.md低于40KB；未做业务范围外重构。影响文件为核心错误、草稿补丁、板读取/设置/目录载荷、相关SDK/Node/浏览器回归与模块文档、README、进度和本日志。

## P7 已实际执行验证

全部服务为临时Vault、随机高端口，命令清除 OMRS_SYSTEMD_SERVICE 与 OMRS_BOXDETECT_CONTROL。以下计数为本批最终代码实跑结果，无SDK跳过项：

| 验证 | 命令 | 结果 |
| --- | --- | --- |
| Python 全量 | `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 564/564，无SKIP |
| MCP 专项含真实SDK | `python3 -m unittest discover -s tests -p 'test_mcp*.py' -q` | 105/105，无SKIP |
| Node 全仓 | `node --test tests/app/*.test.mjs` | 412/412，无SKIP |
| 组件浏览器 | `python3 tests/app/run_browser.py` | 34/34 |
| 既有SDK/网页 | `python3 tests/e2e/mcp.py` | 39/39 |
| 扩展SDK/网页 | `python3 tests/e2e/mcp_expansion.py` | 17/17，含实际重启、离线排版、权限/确认/PIN/下载 |
| 板/选板浏览器 | `python3 tests/e2e/board.py`、`python3 tests/e2e/board_picker.py` | 30/30、31/31 |
| 草稿浏览器 | `python3 tests/e2e/drafts.py`、`python3 tests/e2e/drafts_p4.py`、`python3 tests/e2e/drafts_blocks.py` | 75/75、24/24、59/59 |
| 报告专项/浏览器 | `python3 -m pytest tests/test_report_export.py -q`、`python3 tests/e2e/reports.py` | 7/7、24/24 |
| 系统运行/设置浏览器 | `python3 tests/e2e/runtime_history.py`、`python3 tests/e2e/settings.py` | 34/34、62/62 |
| UI/对比度 | `python3 tests/check_ui.py`、`python3 tests/check_contrast.py` | 0问题、58/58 |

视觉实际命令：`python3 tests/visual/run.py --ref d716157 --pages board,history,settings,create,reports,questions --settings-section access --create-stage drafts --out /tmp/omrs-p7-visual`。24对中20对零差异；设置桌面浅/深0.103%/0.100%，手机浅/深4.337%/4.470%。MCP能力说明新增草稿修订、报告和板管理使手机换行、后续卡片下移；四组差异均在该区，查看了深色手机前后截图，24场景均无脚本错误、横向溢出、小目标及行内样式。报告在 /tmp/omrs-p7-visual/report.html。

Python仍输出既有SQLite ResourceWarning、Pillow getdata弃用提示及客户端断连的BrokenPipeError；最终结果OK，不把这些输出计为失败或已修复。首次docs检查有3项问题（缺架构文档同步和本阶段日志），已按实际改动补齐；路由/日志索引已生成。最终 `python3 tests/check_docs.py --diff HEAD` 与 `--diff d716157` 均83文档、0问题、3条既有大文件提醒；`git diff --check` 通过。已按当前与累计 `git diff --name-status` 复核变化，不纳入其它任务路径。

未执行ChatGPT账户联调与Windows实机验收；本批按授权以真实SDK/Linux隔离浏览器为终点。版本仍v2.1.0，未推送或部署。功能范围无剩余待办，外部发布须单独授权。

## 本地提交

| 阶段 | 提交 | 内容 |
| --- | --- | --- |
| P0 | 625102c | 固定全量契约、执行说明与连续进度 |
| P1 | 54123ac | 批量/完整正文/原图/历史查询 |
| P2 | d821a45 | 同范围分析与可恢复报告保存 |
| P3 | 8595d64 | 跨来源受保护草稿修订 |
| P4 | 8e5404b | 展示板v4版本、回执与网页保存冲突 |
| P5 | 3767ec2 | 管理工具、网页确认与权限编辑 |
| P6 | b289f1e | 安全不可变快照、下载与运行关联 |
| P7 | 本日志所在收尾提交 | 终检边界修复、完整工具清单及全部验收收尾 |

所有提交版本均保持v2.1.0。P0–P7全部完成；工作区提交终点之外的推送、发布和账户验证未执行。
