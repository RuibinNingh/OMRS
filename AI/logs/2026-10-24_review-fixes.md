# 2026-10-24 全面审查问题修复与发布

> **任务**
> - 标识：review-fixes
> - 状态：已交付

## 背景

用户原话：「执行一下修复」「提交GitHub部署生产」「版本+0.0.1」。承接本聊天确认的六个问题，执行者Codex，完整模式，全程不委派子代理。本任务独立于已交付的旧审计与维护计划。开发基线162532f，版本v2.8.4；目标v2.8.5。生产实际基线另行预检，不以开发版本推定线上状态。

开工已有AI/plans/omrs-maintenance/validation.json改动，保留且不纳入提交或发布；原SHA-256和补丁存于/tmp/omrs-fixes-20261024-0xxk0wzu/baseline.json及preserved.patch。用户已明确授权GitHub推送和生产部署，验证仍只使用临时Vault与随机高端口，并清除生产控制环境变量。

## 行为变化

1. 普通即时练习首次提交生成安全随机practice_round_id，以轮次／question_id将完整回执和反馈、投影同事务保存。同轮批内重复、并发和丢响应重试只计分一次，失败项可重试，新轮允许再次作答。回执同步首次接纳的判定与分数，避免断网后改判被误显示为成功。旧客户端省略字段时保留原重复作答语义。
2. 推荐接口接收label_mode=any/all，在排序和题数截断前筛选；即时练习同步「全部命中」选项，非法匹配方式返回400。
3. 标记与知识点列表用JSON字符串编码生成YAML双引号值，完整转义引号、反斜杠与控制字符，创建、保存及扫描保留原名称。
4. 无候选的调度返回HTTP200及完整empty结果，不创建Session或反馈。
5. Chat Completions流提前EOF、坏JSON或未知结束原因均返回error，AgentLoop不执行该轮工具；length继续走原截断流程。显式finish_reason或[DONE]可正常结束。
6. Chat与Responses中止已建立响应时shutdown底层socket，由请求线程关闭响应，避免停止接口争用缓冲读取锁。连接建立和响应头到达之前的取消时机不在本修复范围。

版本v2.8.4升至v2.8.5。实现提交6a6c7445e9eb8a934c93d75bf1d4c9ec896eeb2e已推送GitHub的main并部署生产。生产从v2.8.3、omrs-f56c21d切至omrs-6a6c744；包含此前已提交但尚未上线的v2.8.4展示板空态、审核中心自适应双栏及诊断维护改动，不把发布范围误记成只有六个补丁。后续收尾提交只更新发布文档，不另切换源码。

## 影响文件

已按git diff --name-status复核：omrs/feedback.py、http/learning.py、http/core.py、scheduling.py、sessions.py、question_ops.py、creation.py、llm/openai_compat.py实现六项修复；assets/app/features/instant/index.js与state.js同步轮次身份、回执和筛选。

tests/test_instant_feedback.py、test_llm_chat.py新增事务／并发／慢SSE故障回归；test_labels.py、test_http_boundaries.py与tests/app/instant*.test.mjs、tests/e2e/instant.py扩充真实接口及浏览器路径。omrs/version.py、omrs_dashboard.html、README.md、AI/README.md同步版本，AI/changelog.md记录行为；AI/agent.md、algorithm.md、api.md、api/mutations.md、api/queries.md、data.md、ledger.md、labels.md、frontend/instant.md、frontend/architecture.md同步当前契约；AI/environment.md同步实际生产目录、版本、归档和验收事实，本日志与脚本生成的AI/logs/log.md留痕。

## 已执行验证

证据目录：/tmp/omrs-fixes-20261024-0xxk0wzu。Python使用/root/workspace/apps/releases/omrs-zyb-deps-20261011/.venv/bin/python；所有回归清除OMRS_SYSTEMD_SERVICE、OMRS_BOXDETECT_CONTROL、OMRS_TEST_CDP_URL，使用临时Vault、随机高端口和独立Chromium。

- 后端：-m unittest discover -s tests -p 'test_*.py' -q，1122项全部通过，175.831秒，无跳过，见backend.log。此前定向tests.test_instant_feedback、test_llm_chat、test_labels、test_recommendations、test_http_boundaries、test_maintenance_backend共60项通过，见targeted.log。
- 前端：node --test tests/app/*.test.mjs，562项通过、0失败，见frontend.log；此前即时练习13项定向通过，见instant-node.log。
- 组件：tests/app/run_browser.py，35项通过、0失败，见components.log。
- 真实浏览器：tests/e2e/instant.py 27/27、practice.py 17/17、feedback.py 31/31、assistant.py 59/59通过，见对应*-e2e.log。即时练习实际在服务端接纳反馈后丢弃响应，再改判重试并核对原回执；all匹配用真实创建的A与A+B两题验证截断前筛选。
- 界面：tests/check_ui.py零问题，tests/check_contrast.py 58组全部达标。tests/check_docs.py --diff HEAD退出0，155文档、零问题、3项既有体积提醒；git diff --check通过。
- 视觉：tests/visual/run.py --ref 162532f --pages instant --out /tmp/omrs-fixes-20261024-0xxk0wzu/visual退出0。浅色桌面与深色桌面均0.002%差异，均为侧栏版本4→5；浅色手机、深色手机均0%。已查看桌面差异图，四档脚本错误、小目标、行内样式、横向溢出均为0，字号均3种；report.html与audit.json留存。
- 发布预检：git fetch origin成功，main领先origin/main五个提交且没有远端独有提交；原有validation.json哈希与补丁已留存。生产三服务active，十一类活动任务计数为0，无恢复或未完成写入意图，训练锁可取得；未在生产创建测试题或调用模型。

生产发布证据：/root/workspace/apps/releases/OMRS-v285-release-e0kga9tj，开发证据另保全在其development-validation目录。执行完整模式、用户已授权发布；新旧源码、原unit、停服备份、业务哈希与只读验收脚本均留存，目录0700、私有文件0600。未修改systemd、Nginx、Tunnel、端口、训练模型或生产凭据。

- Git：git push origin main成功，远端从94fa3b2推进至6a6c744，随后git ls-remote精确核对源码提交。只暂存本任务34个文件；validation.json保留开工哈希，不进提交或归档。
- 归档：release.py stage生成/root/workspace/apps/releases/omrs-6a6c744，1611个文件逐字节匹配Git archive。release.py validate从候选归档跑十一道门禁，全部退出0：定向后端60、前端562、组件35、即时练习27、展示板73、审核录入46、网关64、框选21；另界面零问题、对比度58组达标，文档155份零问题。docs使用独立Git索引，测试仍使用临时Vault及随机端口，未加载生产控制环境。
- 停服保全：release.py deploy再次核对活动任务、恢复意图、训练锁、控制配置与归档。停三个服务后备份Vault、maintenance、网关及框选私有目录，tar compare、解包字节及9库SQLite完整性通过；主备份1276文件／8库，框选备份2文件／1库。
- 切换：源码别名原子切至omrs-6a6c744，框选、网关、主站依次启动；v2.8.5就绪，三个真实cwd均在新归档，active/running、NRestarts=0。相邻Nginx/Tunnel、unit、模型、受管状态及控制配置全部不变。切换与首轮核验6.215秒；四份版本化前端资源与归档字节一致、缓存304通过。
- 数据：49张原业务表全部原列原行、1101个原正文／图片／关键配置保全；主站331题、0冲突，审核中心的2条既有待处理草稿保留，活动操作与审批提案均为0。启动新增1条只读MCP失败历史，已逐列核对为停服快照中的旧运行记录，稳定身份一致，无业务重放，详见live-mcp-discovery.json。
- 公网与MCP：live-discovery.py首次在导入阶段因共用依赖没有PyYAML退出，尚未请求MCP；随后用标准库读取唯一认证标量重跑通过，不安装依赖或修改配置。回环、公网各initialize/tools/list发现42个既有授权工具，说明规则各7/7通过；无业务工具调用、无新增Key，仅既有Key的last_used_at更新，身份、权限及其余配置不变。公网首页200，主站状态／MCP／网关受保护API均401，网关healthz与Tunnel /readyz为200，发布后错误级服务日志0条。失败与重跑保留在verification-attempts.json。

## 未执行验证

真实供应商、付费模型、ChatGPT端刷新与生成效果、实体手机和Windows Edge未验证；本机合成SSE、浏览器与生产SDK发现不代表这些外部环境。未在生产创建合成题、运行练习提交或调用业务工具，故障写路径仅在隔离实例验证。实际发布未触发回退；源码回退程序保留当前数据、不用备份覆盖Vault，旧源码归档保留。后续仅在用户要求这些外部验收时开展，无未完成修复或发布步骤。
