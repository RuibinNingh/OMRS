# 2026-10-02 MCP 全量扩展生产部署

## 背景与授权

用户原话：「部署生产」。执行者 Codex，完整模式；开工 main 为 97e09275ef1e3b93b2f9d4d821bb20236ae07ad8，工作区干净。开发 P0–P7 已独立交付，本次是新的部署任务，不改写开发日志的历史结果。版本保持 v2.1.0，不包含 GitHub 推送、密钥扩权、版本升级或 ChatGPT 账户联调。

## 发布准备

实测旧生产 omrs-ba6501b 的主服务与 OMRS Tunnel 均 active/running、NRestarts=0；262 题、0 冲突。助手、收件箱和草稿后台任务均无未结束项；七个现有 SQLite 的 quick_check 均为 ok，Vault 约 284.86 MiB，可用磁盘 40.27 GiB。

从精确 Git 提交归档创建 /root/workspace/apps/releases/omrs-97e0927，1012 个归档文件逐字节校验。.venv 复用 ../omrs-bbf3757/.venv；生产环境实测 Python 3.13.5、mcp 1.28.1、Pillow 12.3.0、jsonschema 4.26.0、pydantic 2.13.5，未安装或升级依赖。工作目录为 /tmp/omrs-expansion-deploy-hpl9r16t/，摘要与隔离门禁日志存于其中。

本次切换新增 --web-public-url https://home.ruibin-ningh.top:8472，使网页确认和下载链接使用主 Web 公网地址。完整 38 工具的查询、受保护草稿修订、报告、展示板管理、网页确认与快照导出已上线；现有密钥权限保持，新增写权限需在设置页显式启用，再刷新外部客户端工具清单。

## 发布、备份与回滚

切换前复核无活动助手、收件箱、草稿或MCP调用，受管模型操作为已结束。停服备份完整错题/、原unit/drop-in、旧release源码，记录只含计数/哈希的文件与数据库摘要；GNU tar -d校验归档内容、sha256sum清单均通过。最终备份目录 /root/workspace/apps/releases/OMRS-mcp-expansion-rollback-20261002T135921Z/ 为0700，文件为0600；Vault归档285.58 MiB，最终8项清单均通过。

仅原子替换 /etc/systemd/system/omrs.service.d/10-release.conf 中三个release路径，增加公网Web参数后 daemon-reload、start。最终停服、备份、切换和启动核验耗时2.374秒，完成时间北京时间2026-10-02 21:59:23。有效WorkingDirectory为omrs-97e0927、PID2579856、NRestarts=0；真实Vault、端口、PIN、Nginx、检测配置与模型指针保持。

回滚只恢复上述目录的10-release.conf.before到原drop-in，再执行systemctl daemon-reload、systemctl restart omrs.service并检查/api/status。旧omrs-ba6501b及共享依赖目录保留；不要用Vault归档覆盖上线后数据。

首次尝试完成切换后，公网临时核验脚本误从get_question结果顶层读取subject，触发KeyError和自动旧代码回滚；耗时2.398秒的首次切换与回滚快照135455Z均保留。临时Key mcp_fa4a53e728c1458c已吊销，回滚后再次核验业务数据一致，没有恢复Vault。修正脚本为从stats取得科目；隔离预跑另发现小时桶整数键需按JSON字符串键规范化，只修临时脚本，随后65/65通过。第二次切换和公网核验全部通过，业务源码未修改。

## 已实际执行的验证

在新release执行下列命令，复用生产Python、临时Vault和随机高端口，清除生产重启与检测控制环境变量：

```bash
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL .venv/bin/python -m unittest discover -s tests -p 'test_mcp*.py' -q
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL .venv/bin/python tests/e2e/mcp.py
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL .venv/bin/python tests/e2e/mcp_expansion.py
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL .venv/bin/python tests/e2e/board.py
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL .venv/bin/python tests/e2e/board_picker.py
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL .venv/bin/python tests/e2e/runtime_history.py
```

| 验证 | 结果 |
| --- | --- |
| MCP全专项，含真实SDK | 105/105，7.817秒，无SKIP |
| SDK / 原图 / 草稿与Key浏览器 | 39/39 |
| 扩展权限 / 确认 / PIN回跳 / 下载 / 重启 | 17/17 |
| 展示板并发保存 / 选板 | 30/30、31/31 |
| 系统运行页与中断恢复 | 34/34 |
| 临时部署核验脚本隔离预跑 | 65/65，含报告源码和展示板分支 |
| 最终公网SDK / Web入口 / 数据核验 | 99/99 |

部署与公网命令为上述工作目录的deploy.py、verify_public.py，用新release的.venv/bin/python运行；首次失败状态和日志另保留attempt-1文件。全部最终门禁退出码0，浏览器没有页面脚本错误。开发轮全量计数不重复计入部署验收。

公网真实SDK初始化并精确发现22个只读工具；批量读题含不存在编号、正文两页及错误哈希拒绝、两种单题历史、Ledger时间线、六种同科目分析和未知科目空范围、草稿及原图、板目录及详情均与共享读取一致。原生image/png为351546字节，与正式附件原件一致；草稿原图保持登记SHA。报告列表为现有空库，生产未创建测试报告，实际报告源码分页在临时预跑验证。

只读密钥逐个点名16个隐藏写工具全部返回forbidden；普通Web API、密钥和确认详情接口拒绝MCP凭据403，未登录的新确认与下载接口及受保护静态资源401。验收Key mcp_002c561466584750已吊销，公网401；明文只存内存，既有密钥凭据、权限及生命周期保持，允许最近使用时间更新。没有创建或修改生产题目、草稿、报告、板或确认操作。

本轮最终Key的39次工具调用均有中文脱敏终态，原图结果不进入运行摘要，不保存明文Key或Base64。18个变更静态资源与release哈希一致；公网首页200，真实Chromium看到PIN输入，页面错误0，截图在工作目录public-entry.png。主服务与Tunnel均active/running、NRestarts=0，262题、0冲突；上线后journal错误级条目0，Traceback/BrokenPipe/ERROR/CRITICAL标记0。受管检测服务PID、状态文件哈希和模型指针一致。

868个内容文件（含282Markdown）哈希不变，七个现有SQLite库业务表行数、内容和schema保持，quick_check均ok；草稿无落盘迁移，旧展示板读取无写入。仅Ledger扫描元数据、临时Key/最近使用时间和runtime追加记录属于技术变化，原运行记录未改写；密钥、runtime和草稿库均0600。

## 影响文件与文档收尾

git diff --name-status连同未跟踪日志复核，更新AI/environment.md当前release、公共地址与回滚位置，AI/mcp.md当前线上能力与显式扩权入口，计划总纲/进度和AI/plans/README.md登记独立部署授权与完成结果。新建本任务日志，AI/logs/log.md由脚本生成；本轮七个文档路径，未修改业务源码、版本号或原执行说明。

实际运行python3 tests/check_docs.py --write-log-index，索引仅新增本任务；python3 tests/check_docs.py --diff HEAD检查83个文档、0问题，退出码0，3条既有大文件提醒保持。git diff --check通过。文档采用独立本地提交，生产源码仍为已验收的97e0927；不推送GitHub。

## 未执行与下一步

未重复Python/Node全量、组件、UI/对比度及视觉门禁：业务源码来自已验收提交，本轮无源码或页面改动，改动集中在发布配置和文档，已针对生产依赖环境与相关网页复跑。没有可用PIN会话进入生产主工作台，完整管理/确认/导出闭环使用隔离真实浏览器验收。

ChatGPT账户联调、Windows实机、生产业务写入测试、GitHub推送和版本升级均未执行。生产部署完成，后续使用新写能力须用户在设置页给所需Key启用相应权限并刷新客户端工具；不需要再次重建服务端。
