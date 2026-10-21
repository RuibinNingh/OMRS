# 2026-10-21 MCP 答案规范生产发布

> **任务**
> - 标识：mcp-answer-scope-deploy
> - 状态：已交付

## 背景

用户原话：「上线一下」。这是答案内容边界本地交付后的独立生产发布授权，执行者 Codex，完整模式，所属 AI/plans/mcp-integration/「答案内容边界生产发布」。本地实现为 32f3086；本次开工开发分支还包含其它任务提交 da42533，未提交 AI/plans/omrs-maintenance/validation.json 保留，不纳入发布。

实际线上为 1740051 / v2.8.3，不能把开发分支的其它改动一并上线。以线上提交为父，仅移植 32f3086 的 MCP 规则与对应文档，通过私有 Git 索引生成独立候选 f56c21d314ff8810b7d5691d40c568904004dc79，分支 codex/mcp-answer-scope-release-20261021。既有已交付开发日志保持原文，发布结果单独记录。

## 行为变化

发布新 MCP instructions、创建草稿、草稿修订、正式改题的工具及文字字段说明：答案默认仅保存本题结论及必要解析，不主动追加练习、独立概念讲解、重复提醒或其它教学内容。规则内容及例外沿用本地实现，版本保持 v2.8.3。

部署使用精确归档和既有依赖；先预检、停服一致备份并校验，再切换稳定源码别名。上线验证仅 initialize/tools/list，不新建生产 Key、业务对象或修改题目；客户端刷新及模型遵守程度另验。

## 影响文件

- 生产候选相对 1740051：运行代码仅 omrs/mcp/tool_docs.py，另外同步本次实现的模块文档、README、计划及任务日志；代码与 32f3086 字节完全一致。
- 本轮开发工作区：AI/plans/mcp-integration/plan.md、progress.md 追加上线授权、范围和结果；AI/environment.md 更新当前生产事实，本日志及自动生成索引记录发布。
- 发布保全及脚本位于 /root/workspace/apps/releases/OMRS-mcp-answer-scope-release-dtupj55u，候选源码归档位于 /root/workspace/apps/releases/omrs-f56c21d。

## 已执行验证

- git status --short、实际服务目录和版本复核：其它任务施工期间存在独立暂存并随后提交，本次私有索引不修改共享暂存区或 checkout。
- 候选与父提交路径差异复核：运行代码仅工具说明，版本文件与生产相同，工具说明与实现提交相同；源码归档 1597 个文件逐字节一致。
- 发布初始及停服预检：11 项活动任务计数均为 0，无待审提案，训练锁可取得；三服务和相邻 Tunnel、Nginx 均在运行。stage、validate、deploy 均成功，命令为清除两个生产控制环境变量后，在候选 .venv/bin/python -B 执行保全目录的 release.py 对应子命令。
- 精确归档生产解释器执行 unittest discover -s tests -p 'test_mcp*.py' -q：132/132，15.675秒，无跳过；门禁进程16.443秒。临时合成Vault与随机端口SDK：44工具、7/7新规则，1.317秒。候选 tests/check_docs.py --diff 1740051：150文档、0问题、3条非阻断大小提醒，4.422秒。详见保全目录 mcp.log、sdk-discovery.json、docs.log、gates.json。
- 持训练锁停服备份Vault、maintenance及网关：1263文件、8库解包比较与完整性通过；框选私有备份另2文件、1库通过，总1265文件、9库。源码别名原子切换、三服务启动及数据核验5.423秒；失败回退仅恢复源码的路径已备妥，本轮未触发回退。备份和实际状态见release-state.json、vault.tar、gateway-private.tar、boxdetect-private.tar。
- 系统 /usr/bin/python3 -B live-discovery.py：仅initialize/tools/list，回环与公网各发现42工具，按既有权限匹配，instructions及三工具、三字段分别7/7通过。生产虚拟环境不含PyYAML，首轮客户端脚本导入失败后改用已有系统SDK环境，不安装或修改生产依赖。
- 原49张业务表逐列原行全部保持。严格总行数比较发现启动新增一条只读失败历史，operation_id为op_589198cf4d92ea9924cedae9cdd1dbb9；与停服快照原runtime记录的身份、参数、结果、时间及全部目标列一致，其余业务表完全一致。审计脚本先假定世代文件存在、再误用Tunnel的/ready；分别按源码缺省世代0和实际/readyz修正后最终通过。失败尝试、差异及证据保留在verification-attempts.json、post-deploy-profile-diff.json、new-review-rows.json，不删除补录历史、不重放业务。
- 1093个原内容和关键配置检查，仅.omrs/mcp_keys.json最后使用时间变化，Key数量、身份、scope保持。网关及框选私有数据、模型、unit、Nginx、Tunnel控制配置保持；无生产业务工具调用或新建Key。
- 三服务真实cwd均指向新归档且active/running、NRestarts=0，330题、0冲突；公网首页200、Web/MCP/网关业务接口未授权401，网关healthz与Tunnel readyz为200。发布后错误级journal为0；最终报告live-mcp-discovery.json。
- 已运行python3 tests/check_docs.py --write-log-index、git diff --name-status和git diff --check；主工作区diff HEAD最终155文档、0问题、3条既有非阻断大小提醒，暂存差异检查通过。环境文档触及40KB提醒后已精简本次生产事实至40902字节，保留其它任务内容。

## 未执行验证

- ChatGPT 账户刷新与实际生成效果未执行；服务端 SDK 验收不等于账户已更新。页面行为未改，不重复页面与视觉门禁；不做推送。
