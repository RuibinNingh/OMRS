# 2026-10-03 审核中心 v2.3.0 本地发布

## 背景与授权

审核中心功能已本地交付9da7e83，版本v2.2.1；用户追加「部署本地和推送GitHub」「版本更新v2.3.0」。执行者Codex，完整模式，开工工作区干净。当前主服务精确b41a65a/v2.2.1，origin/main为eda4510；功能实现与发布验证分开记录，不改写旧任务日志。

## 行为与范围

将统一MCP/助手业务写审核、原草稿图文工作区及安全改题发布为v2.3.0。既有Key不自动增加question:propose；正式复习计划先返回pending_confirmation，批准后查询实际Session。新版本沿用现有端口、Vault、MCP/Web公网参数及依赖。

## 影响文件

版本源、工作台侧栏、根README、AI摘要/changelog、外壳文档、环境当前发布事实、计划追加授权/发布说明与进度、新发布日志及生成索引。无业务逻辑改动，私人归档、数据库、凭据与部署脚本均在仓库外。

## 发布前核对

已实际核对Git状态/HEAD/远端main、有效主服务代码路径、磁盘空间和三个服务状态；无未完成整库恢复、题目写入journal或queued/running/pending任务。原主服务PID491135、Tunnel PID875442、检测PID1532134，三者active/running、NRestarts=0。

## 验证与发布

### 版本与精确源码

已实际验证版本源、侧栏、README与AI摘要同步；临时Vault/随机端口 `/api/status` 返回v2.3.0；UI检查0问题、58组对比度全部达标。`python3 tests/visual/run.py --ref 9da7e83 --pages dashboard --out /tmp/omrs-v230-version-visual` 四档无脚本错误，浅/深桌面各0.003%差异仅为页脚版本字符，范围(41,871,61,880)，两手机完全一致。

发布源码提交de100220ba4f15af757236cd80d440442974235f（`release: 准备审核中心 v2.3.0 本地发布`），从Git归档生成 `/root/workspace/apps/releases/omrs-de10022`；1,134个文件逐字节校验通过。复用既有venv，核对Python3.13.5、MCP SDK1.28.1、Pillow12.3.0，未安装或升级依赖。

使用该精确release与既有venv运行ai_review、HTTP、MCP自动意图、question_update、MCP改题SDK、agent_review、MCP审批与backup_recovery八个模块，共94项通过、无跳过，4.222秒。所有测试使用临时Vault与随机端口，移除OMRS_SYSTEMD_SERVICE与OMRS_BOXDETECT_CONTROL；日志 `/tmp/omrs-v230-prod-venv-tests.log`。注入记录终态失败的诊断属于实际故障回归，无测试失败。

### 原始保全与私人副本

保全位于 `/root/workspace/apps/releases/OMRS-v230-release-20261003T092803Z-6u51wcwh`，目录0700、文件0600，不进入Git。保存旧unit/drop-in、源码归档与SHA，以及首次停服和最终切换前最新的完整 `错题/`、`.omrs-maintenance/` 原样归档；tar比较通过。首次保全停服1.757秒，恢复旧主服务后继续隔离验证，最终发布再取最新原始基线。

私人一致副本迁移保持45张原业务表全部原行与原列、827个原Markdown/原图/报告/配置文件SHA和731条Ledger事实，提交链合法；262个活动题当前正文缺blob为0、文件冲突0。48个历史正文缺口为既有缺口，未增加。审核历史导入80项操作，重复初始化不重复；ai_review.db权限0600，GET数量/列表/详情不改变审批表。

副本完整CLI与真实PIN登录浏览器通过：桌面1440浅色、手机390深色，2幅真实截图，无脚本错误或横向溢出。已知测试PIN只用于私人副本，停止后还原该副本原auth字节；生产PIN未修改。截图与完整私人对照只保存在保全目录。

验证过程的失败与修正：初始对照把正常技术缓存变化当成业务变化，核实只有snapshots、workspace_fingerprint、workspace_scan_status变化，原业务均保持；第一次浏览器继承真实PIN而停在锁屏，改用副本已知测试PIN；手机导航等待抽屉visibility过渡后通过。这些修正仅在仓库外验证脚本中完成，没有产品源码变更。

### 实际切换与只读核验

只原子替换 `/etc/systemd/system/omrs.service.d/10-release.conf` 三处release路径，daemon-reload后启动主服务。2026-10-03 17:41:09 CST停止旧主服务，17:41:10 CST启动新服务，最终切换约1秒。新主PID1977331，active/running、NRestarts=0；Tunnel PID875442与检测PID1532134均保持、未重启。Vault、端口、公网URL、Nginx、PIN、Key权限和模型指针保持。

本机 `/api/status` 返回v2.3.0；生产只读核验保持最新停服基线的45张原业务表和827个原文件。中心可读取108条记录，由80项操作和28份原生草稿组成，待审0；GET数量/列表/详情不改变审批表。3个中心JS/CSS资源hash与精确release一致，本机MCP匿名401。

公网实际响应：入口 `/` 与 `/api/auth/session` 为200；匿名 `/api/status`、`/api/ai-review/counts` 与 `/mcp` 为401。首次发布检查误将文档中的“非秘密元数据”理解为status可匿名读取，遇401报告异常；服务切换实际成功，没有回退或再次重启。按服务器授权代码修正预期并完成只读核验，deployment.json状态为deployed，首次证据另存deployment-first-check.json。同步订正security与queries的授权描述，没有更改业务安全代码或访问权限。

### GitHub与文档收尾

本地main从eda4510正常快进到de10022，`git push origin main` 成功；`git ls-remote --heads origin main` 核对精确de100220ba4f15af757236cd80d440442974235f。没有强推、新建标签或GitHub Release。本记录和当前环境/进度订正随独立文档收尾提交推送；业务源码仍与线上de10022一致。

文档复核同时纠正MCP说明中的旧history确认链接、独立确认库描述及运行详情生命周期来源，均以当前代码为准。发布前文档检查102份、0问题，2条既有大型计划体积提醒。收尾运行 `python3 tests/check_docs.py --write-log-index`，再运行 `python3 tests/check_docs.py --diff de10022`：102份、0问题、2条相同提醒，退出0；`git diff --check`退出0，复核7个文档路径，没有业务源码或私人材料。

本批继承实现轮798项Python、449项Node及真实SDK/浏览器通过证据，不重复计为本轮执行。

### 未执行的验证

没有在生产执行测试业务写、创建验收Key/题目/反馈/报告/板或调用真实付费模型。真实PIN未提供，完整PIN/工作台路径在私人副本已知测试PIN验证；公网匿名授权实际核对。外部冻结boxdetect模型、Windows实机与ChatGPT账户联调未运行，均不属于本批发布范围。仅文档收尾不重复全仓功能门禁，也不再次部署或重启。

## 恢复边界

先取得完整原始错题目录及维护目录归档，不以会触发初始化的新版应用备份代替第一份基线。待处理题目journal绑定原路径与inode，不迁移或删除后启动副本。新权限scope、JSON/YAML编码、统一审批与题目恢复协议启用后，直接旧码回退可能损坏语义或重新暴露旧审批；保留最新数据并以前向修复处理，禁止旧归档覆盖上线新增事实。

## 遗留与下一步

本批功能、发布与验证无已知新增遗留问题。48个历史正文缺口已明确保留，当前正文完整。用户刷新工作台即可使用审核中心；MCP改题需按实际需要人工授予默认关闭的question:propose，既有Key未扩权。
