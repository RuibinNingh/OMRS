# 2026-10-18 AI 框选同端口部署与实测

## 背景与授权

用户原话：“部署一下实测”，沿用“记得不要再分端口了”。执行者Codex · 完整模式；所属计划AI/plans/boxdetect-panel。源码基线107989b70a7cf2ebcc4a83c6c46da1f996b6c15e，v2.8.3，原生产为baae15f精确归档。本次授权包含生产配置、必要重启和真实链路验证，不包含推送。

开工只有AI/plans/omrs-maintenance/validation.json已有未提交改动，SHA256为3d3cdbd203731931981a4db6d940cae48878e1069d55c1c2008c361aa58be9f9；未修改、归档或提交该改动。上一实现任务日志保持其交付时事实，本次单独记部署结果。

## 行为与部署

线上源码固定为/root/workspace/apps/releases/omrs-107989b，1593份文件与Git归档逐字节一致；稳定别名omrs-9b29d49原子指向该目录。三个服务真实cwd均位于该归档，主站8471／MCP18472、HTTPS8472、网关回环8745、检测回环18766保持，没有修改Nginx或新增监听。

检测unit保留解释器、managed/active和全部资源限额，新增显式私有状态/var/lib/omrs-boxdetect、候选managed/snapshots及StateDirectory/ReadWritePaths。目录0700，SQLite与初始管理员密码0600；OMRS新增独立连接0600，保存主站专用调用Key。外部调用开关持久化开启，只通过现有HTTPS入口接入且仍须Key；未启用legacy-loopback，旧匿名检测返回401。

同源入口为https://home.ruibin-ningh.top:8472/boxdetect/。远端管理先走现有主站PIN，再使用独立管理员密码；未输出或提交密码、调用Key。提供方保持local_http，当前模型仍为v2-20260929-b、640、conf0.1、SHA256 f62581b7c28353d5d7799973018a6986e706cd7dcf4fb43ccd10972be4a4c7c3。原managed指针、state.json及revision保持，旧模型控制器因独立连接启用而停用。

## 保全与切换

发布驱动和证据在/root/workspace/apps/releases/OMRS-boxdetect-deploy-3ub051ln，私有目录0700。切换前八类在途任务计数均0，未发现恢复/正式写入意图，训练锁可获取；实际切换持训练锁，停主站、网关和检测后重新预检，保全Vault、maintenance、网关私有数据、新旧源码、unit和managed模型/控制历史。

首次部署的检查脚本误要求主站精简状态响应含protocol和完整model字段，实际连接测试已200但驱动KeyError触发自动回退。原服务恢复就绪，保留新生成的私有连接和Key，未用旧备份覆盖数据；第一次1250文件/8库保全及失败状态保存于attempt-1。随后按client.status的真实白名单契约修正驱动，复用原Key，不重复创建。

第二次停服保全实际解包比对1251个文件，8个SQLite integrity_check均ok，另校验model-control.tar与原目录。切换、启动和驱动主要检查共4.301秒，此数不等同HTTP不可用时长。主站/网关/检测均active/running、NRestarts=0；49张原业务表全部原列/原行、1081个原正文/图片/关键配置及网关凭据保持。新框选私有库用SQLite备份API另存boxdetect-private-after并检查完整性，密码和连接副本哈希一致。

## 已实际执行的验证

从发布归档执行以下四组，均退出0；隔离实例使用临时Vault和随机高端口，移除生产控制环境变量，不读取真实题库。浏览器使用可信本机CDP的独立context，未关闭共享浏览器。

| 检查 | 命令与结果 |
|---|---|
| 主程序相关 | 归档.venv/bin/python -B -m unittest tests.test_boxdetect_panel tests.test_traincontrol tests.test_draft_detect tests.test_inbox tests.test_trainpanel -q；83通过 |
| 独立服务 | PYTHONPATH=services/boxdetect /root/omrs-train/.venv/bin/python -B -m unittest discover -s services/boxdetect/tests -p 'test_*.py' -q；21通过 |
| 隔离浏览器 | 归档.venv/bin/python -B tests/e2e/boxdetect_panel.py --out 发布证据/isolated-browser；111通过 |
| 真实模型预检 | systemd-run临时受限单元，从归档执行训练解释器 -B -m boxdetect_service probe --model-dir 发布证据/model-snapshot；通过，单元已回收 |

生产驱动omrs-boxdetect-production-check.py及其finish续验合并81项通过，production-verification.json的success=true。主站设置使用真实本机API验证脱敏连接、已保存Key测试和固定unit重启；没有猜测/重设PIN或注入主站会话。独立面板真开浏览器完成管理员登录、创建临时Key、真实推理、历史原图叠框、刷新、吊销及退出。公开HTTPS验证带Key状态和检测、同编号复用回执与吊销立即拒绝；调用Key不能管理服务或访问主站。

使用同一张768×3840合成题图，面板和公网各执行一次真实ONNX，分别286ms/172ms，均3条带、2个返回框、每次一条历史；重复公网编号不增加记录。该图不是真实题图，数字只记录本次链路结果，不代表内容准确率或性能基准。固定unit重启后两条历史、原图、管理会话、主站Key和当前模型保持，重启控制有完成回执；临时Key已吊销，只有主站Key有效。

面板3份资产及主站设置/训练3份脚本与归档逐字节一致；1440/390px、浅深色的概览/历史/模型/设置16组无横溢，无未捕获脚本错误，已查看概览桌面/手机和历史详情截图。初次业务浏览器40项通过后，另开训练页导致后台概览截图超时；保留原结果，新建前台context只补截图与余下核验，未重复推理或重启。无泄露Key/密码的截图。

验收脚本初期还修正两处预期：未登录管理路径先302到PIN，自动跟随后是200入口HTML；普通OMRS接口收到Bearer按既有MCP边界返回403。原错误结果保留为production-check-first/second记录。修正只在仓库外验证脚本，不改变生产鉴权代码。最终三服务无发布后错误级journal，原业务表/文件、模型和控制登记再次核对保持，实际监听与原端口逐一匹配。

## 仓库影响与收尾

deploy/boxdetect.service补显式data-dir、models-dir和唯一可写状态目录，避免在ProtectHome/ProtectSystem下尝试写默认家目录；README同步模板安装说明。AI/environment.md更新真实归档、私有目录、端口与验收事实；AI/plans/boxdetect-panel/plan.md先登记部署切片，progress.md同步完成状态、门禁和变更依据。本日志新建，索引由check_docs生成，不改历史日志。

文档提交不改变当前在线归档，后端和前端源码仍固定107989b；模板只供后续安装使用，线上unit已按同样目录权限配置。模板按本机用户、解释器和安装路径归一后通过systemd-analyze verify，退出0；同时核对原端口、私有目录、候选路径和资源限制，没有启动额外单元。

单独执行python3 tests/check_docs.py --write-log-index生成索引。首次--diff HEAD为150文档/0问题，环境文档新增至41KB触发新体积提醒；删去其重复产品操作说明（对应页面分册已有权威说明），保持环境模块在40KB内。最终文档检查、diff与用户改动哈希复核后按本任务路径提交；不重启当前精确归档。

最终python3 tests/check_docs.py --diff HEAD退出0，150份文档、0问题、3条既有体积提醒；AI/environment.md为40953字节，无新增提醒。git diff --name-status、git diff --check及用户validation.json哈希已核对；提交仅含本任务7个路径，原用户改动保留未暂存。生产后端和前端没有额外改动，版本保持v2.8.3。

## 未执行与下一步

本轮未重复上轮已通过的全仓1083项Python、550项Node和全部UI视觉门禁，因为发布的是同一已验收源码，归档已重跑相关检查；本轮仓库只变部署模板和文档。未做实体手机、生产真实题图准确率、付费调用、训练、模型切换或测试入库；主站设置页面的PIN后浏览器流程沿用上轮隔离验收，生产通过本机API验证。未推送GitHub。用户可登录主站后打开独立管理面板，后续模型内容验收独立安排。
