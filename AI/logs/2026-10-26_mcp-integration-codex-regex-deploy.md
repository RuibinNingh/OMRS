# 2026-10-26 MCP 编号正则兼容修复生产发布

> **任务**
> - 标识：mcp-integration-codex-regex-deploy
> - 状态：已交付

## 背景

用户原话：「上线一下生产」「然后我尝试刷新工具」。本地修复已在 a7b9a1b 交付，原实现日志保持已交付原文，本日志单独记录新增生产授权。执行者 Codex，完整模式，所属 AI/plans/mcp-integration/plan.md「Codex 参数校验兼容生产发布」。

上线前实际生产为 6a6c744 / v2.8.5，本轮已发布 a7b9a1bf8fcdf629a4d7eddbdc240f2cca55cf77 精确归档，运行代码差异仅三个 MCP 文件。已有 AI/plans/omrs-maintenance/validation.json 未提交改动已保存原字节、补丁及哈希，不纳入提交或归档。本轮授权不包含 GitHub 推送或密钥扩权。

## 行为变化

上线题图 UID、Session ID、复习计划请求编号与稳定题目 ID 的统一非空白正则，兼容搜索和整串匹配；既有长度、空白处理、权限与审核保持。版本保持 v2.8.5，客户端需在上线后刷新工具定义。

## 影响文件

- 生产源码：a7b9a1b 精确 Git 归档，运行变化为 omrs/mcp/common.py、omrs/mcp/server.py、omrs/mcp/session_write.py。
- 本轮仓库文档：AI/plans/mcp-integration/plan.md、progress.md 记录生产授权及结果；AI/environment.md 同步生产事实，本日志及脚本生成的 AI/logs/log.md 留痕。已用 git diff --name-status 复核范围，原有 validation.json 保留。
- 发布证据与备份：/root/workspace/apps/releases/OMRS-mcp-codex-regex-release-4z9qqbpv，目录 0700、私有文件 0600。

## 已执行验证

- git status --short、git log、生产服务真实 cwd 与版本核对：三服务 active/running、NRestarts=0，源码均来自 omrs-6a6c744；运行差异严格限定为三个 MCP 文件。
- 初始预检：11 类活动任务均为 0，无未完成恢复或业务写入意图，训练锁可取得；发布目录可用空间 12.5 GiB。保留原有 validation.json 的原字节、补丁及哈希。
- 从保全目录复用上一轮发布脚本的归档、备份、切换和源码回退逻辑，按本次授权去掉推送前置条件，限定三个运行文件与允许的发布文档改动。执行清除 OMRS_SYSTEMD_SERVICE、OMRS_BOXDETECT_CONTROL 后的生产解释器 `-B release.py stage`、`validate`、`deploy`，均退出0；保全目录的 task.json、release-state.json、gates.json 记录精确候选、基线与状态。
- 候选 /root/workspace/apps/releases/omrs-a7b9a1b 的1612个文件与Git归档逐字节一致，复用既有依赖。候选执行 `-m unittest discover -s tests -p 'test_mcp*.py' -q`：133/133，15.499秒，无跳过；门禁进程16.298秒。临时Vault／随机端口SDK检查四处schema的完整匹配，中文UID取PNG原字节、Session查询及复习计划送审均通过，1.367秒。归档文档 `--diff 87f813e`：155份、0问题、3条大小提醒，4.525秒；详情在 mcp.log、sdk-schema.json、docs.log。
- 停服前再次预检，持训练锁停止三个服务，备份Vault、maintenance、网关及框选私有数据并实际解包比较。主备份1318文件、9库，框选备份2文件、1库，总1320文件、10库完整性通过。原子切换别名后按框选、网关、主站顺序启动，三服务真实cwd均为新归档，active/running、NRestarts=0；切换及首轮核验6.113秒，未触发源码回退。原unit、Nginx、Tunnel、端口、模型及控制配置保持。
- 生产使用既有Tunnel凭据执行 `-B live-discovery.py`：只initialize/tools/list，回环和公网各42工具，四处编号规则各4/4，instructions与归档完全一致，原长度边界保持；无业务工具调用、新增Key或扩权，仅更新既有Key最后使用时间。公网首页200，主站状态／MCP／网关业务接口无凭据均401，网关healthz与Tunnel /readyz为200；发布后错误级服务日志0条，见 live-mcp-discovery.json。
- 停服快照与上线后51张原业务表全部原列原行完全一致，无业务表新增行或启动历史补录；1134个原正文、图片及关键配置仅.omrs/mcp_keys.json最后使用时间变化，Key数量、身份及scope保持。主站341题、0冲突；网关与框选私有数据保持。发布证据目录0700、私有备份0600；原有validation.json哈希保持。
- 收尾执行 `python3 tests/check_docs.py --write-log-index`、`python3 tests/check_docs.py --diff HEAD`：155份文档、0问题、3条既有大小提醒，退出0；git diff --name-status与git diff --check通过。收尾文档提交仅记录发布结果，不再次切换源码。

## 未执行验证

实际Codex／Chat账户刷新由用户在上线后进行，不将隔离SDK或工具发现当作账户实际读图通过。未在生产创建合成题、提交复习计划或调用模型；写路径验证仅在临时Vault执行。本批未修改页面，不重复浏览器与视觉门禁；未执行GitHub推送，未触发实际回退。
