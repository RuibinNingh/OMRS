# 2026-10-20 诊断日志与协作门禁优化

> **任务**
> - 标识：logging-governance
> - 状态：已交付

## 背景

用户先问「OMRS的日志功能和AGENT.md够成熟吗」，在只读评估后授权「可以,执行优化」。执行者Codex，完整模式；本任务独立于已结束的维护计划，不修改其历史记录。基线为89b90eac89f95eb80bdd7a063196a6a82187af67；开工已有AI/plans/omrs-maintenance/validation.json未提交改动，以SHA256保全，按原样保留。工作证据目录为/tmp/omrs-logging-governance-uiyxefhe。

## 行为变化

- 反馈事务提交后追加FEEDBACK诊断，包含稳定question_id、实际Session和Ledger commit_id；无效、回滚及幂等复用不记成功。正式数据与回执仍由Ledger决定。
- 运行及AI请求日志单文件8MiB、3份轮换备份，完整记录写入；运行日志仅清理受管日期命名普通文件，保留含当天30天、合计64MiB。旧超限文件在下一次写入清理；自定义日志、链接、任务日志和数据库不参与容量清理。
- 日志写入使用线程及跨进程目录锁，新文件0600；存储／锁／清理故障只发每60秒至多一次的固定警告，不回显异常内容，不改变已完成业务结果。超限AI单条以可解析JSON标明省略，不修改模型请求。
- 根AGENTS.md纳入文档形式检查，规划工作流原文移至AI/plans/README.md，入口按需指向；保留运行模式、授权、隔离实例、防漂移和交付底线。文件从26654降至21662字节，减少18.7%；移出的规则逐字校验一致。纳入检查后发现其中已不存在的UI基线路径，按当前全仓零基线规则删除该过时引用。
- 文档映射第一分句中的必更文档逐一检查，条件项仍人工复核；删除文档不算同步。变更任务日志须有状态块及五个非空章节，进行中的任务可跨提交续作；已交付及无状态旧日志只保留原文后追加日期勘误，另有本次任务日志，不能用改写历史代替留痕。

## 影响文件

- omrs/log_utils.py、omrs/feedback.py、omrs/llm/openai_compat.py：提交后反馈诊断、有界轮换与固定故障提示。
- tests/test_logging.py、tests/check_docs.py、tests/test_docs_gate.py：日志故障／并发／容量及真实临时Git门禁回归。
- AGENTS.md、AI/README.md、AI/plans/README.md、AI/environment.md：精简入口、集中规划流程和可检查的任务日志契约。
- AI/data.md、AI/ledger.md、AI/agent.md、AI/security.md、README.md及日志索引：同步当前行为、权限边界、容量与协作使用方式。

## 已执行验证

- 第一轮定向：`python3 -m unittest tests.test_logging tests.test_maintenance_backend tests.test_llm_responses tests.test_log_export -q`，66项通过；文档门禁测试13项通过，但观察到映射表读取未及时关闭的ResourceWarning，已补with关闭。
- 最终定向：`python3 -m unittest tests.test_logging tests.test_docs_gate tests.test_maintenance_backend tests.test_llm_responses tests.test_log_export tests.test_runtime_records tests.test_gate_execution -q`，100项全部通过，无上述警告。
- 全仓首轮：`python3 -m unittest discover -s tests -p 'test_*.py' -q`，执行1105项，唯一错误是作业帮二维码可选依赖segno未安装，日志为`/tmp/omrs-logging-governance-uiyxefhe/python-suite.log`，没有隐去失败或用跳过替代。
- 将已有依赖环境中真实segno包复制到仓库外`/tmp/omrs-logging-governance-uiyxefhe/test-deps/`，不修改全局Python或生产依赖，不使用替身。用`PYTHONPATH=/tmp/omrs-logging-governance-uiyxefhe/test-deps`先单独补验二维码失败项，1项通过；随后以同一PYTHONPATH完整重跑上述discover命令，1105项全部通过、0跳过，耗时173.247秒，日志为同目录`python-suite-with-deps.log`。
- `node --test tests/app/settings-logs.test.mjs tests/app/runtime-history.test.mjs`：7项全部通过，日志为同目录`node-logs.log`。
- `python3 tests/e2e/settings_logs.py`：真实Chromium、临时Vault、随机端口，29/29通过；覆盖筛选、选择、实际ZIP、失败重试、卸载与六档主题／视口。日志为同目录`settings-logs-e2e.log`，截图在`/tmp/omrs-log-shots-w6zxqani`。
- `python3 tests/e2e/feedback.py`：真实反馈页面31通过、0失败，含提交、只读回显、失败保留、键盘和手机／桌面／主题主路径；日志为同目录`feedback-e2e.log`。两项浏览器任务均清除共享CDP变量，使用独立浏览器。
- 另用合成临时Vault执行真实创建与反馈、读取日志清单并生成／解包ZIP，确认FEEDBACK里的question_id和commit_id与已提交Ledger一致，且不含题面正文；临时ZIP在完成后删除。
- 所有服务测试均从环境去掉`OMRS_SYSTEMD_SERVICE`与`OMRS_BOXDETECT_CONTROL`，未连接生产端口或真实题库。用户原有validation.json的SHA256与开工记录一致。
- `python3 tests/check_docs.py --write-log-index`已生成索引；`python3 tests/check_docs.py --diff HEAD`检查153份文档，0问题、3条既有体积提醒。首次检查发现AGENTS旧UI基线路径及环境文档体积超限，已修正引用并缩短新增环境说明，未新增体积提醒。
- 已以`git diff --name-status`、`git status --short`及`git diff --check`复核范围和空白，新增日志与测试另外核对；本任务17个路径，不包含原有validation.json改动。

## 未执行验证

- 未做生产部署、推送、重启或生产数据验证；版本保持v2.8.4。实现作为一个本地提交交付，生产发布仍须用户单独授权。
- 未使用Windows或实体手机；Windows文件锁分支只做代码复核，手机使用真实Chromium视口模拟。
- 未运行其它页面E2E、服务独立全套、付费模型或实际官方搜题；本次按日志、反馈和协作门禁风险验证。未改前端资源或页面结构，因此未运行视觉前后比较、全量Node及组件浏览器门禁。

## 遗留与下一步

本次已完成。诊断写入仍为尽力留痕，不能替代Ledger或提供崩溃时恰好一次保证；日志正文／状态门禁只验证结构与生命周期，不能证明命令实际执行。后续任务使用新模板，旧日志不批量迁移或回写。
