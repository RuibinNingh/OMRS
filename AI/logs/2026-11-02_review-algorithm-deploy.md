# 2026-11-02 复习算法生产部署与推送

> **任务**
> - 标识：review-algorithm-deploy
> - 状态：已交付

## 背景

用户追加明确授权：“部署并且推送吧”。执行者Codex，完整模式；本地实现84c7efa、v2.9.0已完成，见同日review-algorithm任务日志。本任务仅发布已验收代码、真实历史重算、核验和推送，未改业务代码。生产原为0ed224d精确归档；开发工作区原有导出相关改动继续保留，未打包进发布或纳入提交。

## 行为变化

生产使用一次高分击杀、五档复核及ledger-v4历史重放。默认间隔7/21/60/120/180天，提前练习不延期、低分正确3天巩固、错误1天重练；前端设置、题库、仪表盘、调度和复盘随同上线。活动配置只规范清理废弃参数，没有更改凭据、PIN、模型、Nginx、Tunnel、unit或依赖。

源码通过git archive 84c7efa提取到/root/workspace/apps/releases/omrs-84c7efa，1621文件逐字节核验；稳定别名omrs-9b29d49原子切换。三服务真实cwd核对新归档及各自服务子目录，active/running、NRestarts0，相邻服务进程与控制配置保持。首次因发布校验脚本要求离线与线上独立审计提交的链头哈希相等，触发保留数据的源码回退；差异只在commits、projection_meta和重算回执，题目及复习投影一致。修正校验脚本，比较原始提交、投影及元数据序号/策略/版本，第二次发布成功。

## 影响文件

仓库仅更新AI/environment.md当前生产事实、AI/plans/review-algorithm/progress.md、计划目录索引、本日志及自动日志索引。部署脚本与私有证据不提交：最终/root/workspace/apps/releases/OMRS-review-policy-release-9hree7k4，首次尝试/root/workspace/apps/releases/OMRS-review-policy-release-uxj8c3qd；两目录0700，私有文件0600，保留独立备份和状态，不覆盖前次证据。

已有AI/board.md、AI/export.md、README导出说明、维护validation.json、两份导出CSS、smoke_a4_print.py及2026-10-29导出日志均未改动或纳入本次提交。日志索引只暂存本任务生成的增量。实现代码84c7efa已快进推送GitHub main；部署记录另作中文文档提交并推送。

## 已执行验证

发布前git fetch核对main为8e11f4e且为HEAD祖先，git push origin HEAD:main成功，无强推。预检运行任务、恢复意图、框选操作、训练锁均通过，所有有效运行任务计数0。候选从精确归档使用生产现有Python依赖补验，测试均清理生产控制环境变量并使用临时Vault/随机端口。

| 检查 | 实际结果 |
|---|---|
| 归档前端node --test tests/app/*.test.mjs | 568项通过 |
| 归档组件tests/app/run_browser.py | 35项通过 |
| 归档feedback / review_policy / settings E2E | 43 / 22 / 79项通过 |
| 归档unittest：test_revive_cycle、test_config_publication、test_instant_feedback、test_data_runtime、test_asset_cache、test_web_assets | 83项通过 |
| 归档UI / 对比度 / 文档 | 零违例 / 58组通过 / 157份零问题 |
| 停服备份 | Vault及网关1402文件、9库，框选2文件、1库，全部解包逐字节及SQLite完整性通过 |
| 离线重算与真实重算 | 题目身份/正文引用保持；题目、熟练度、历史、档位和排期投影逐表一致，元数据序号/策略/版本一致 |
| 原始数据保全 | 45张非算法变更业务表原列原行保持；1211个正文/图片/关键配置哈希一致；网关和框选私有历史/凭据不变 |
| Ledger | 原始888条提交逐列完整保留；两次尝试各追加1条config.tuning_update，最终890条哈希链有效 |
| 重算回执 | complete，ledger-v4，revision6，374题目投影（含归档）、371条有效反馈；第1档67、第2档40、档位0共267 |
| 线上统计/推荐 | 371道可见题、106已击杀，其中75到期、31休眠；默认推荐11题含6道到期复核，31道休眠题排除 |
| 线上资源 | 5个版本化模块与归档逐字节一致，immutable及ETag304通过 |
| 线上只读浏览器 | dashboard/questions/schedule/data/settings，桌面/手机、浅深色共20档通过；设置五档值正确且旧连对项消失，题库档位可见，溢出/脚本错误/写请求0 |
| 公网及就绪 | 首页200，状态/MCP/网关业务/框选业务401，网关healthz200，Tunnel readyz200，本机MCP无Key401，共8项通过 |
| 生产服务 | 三项active/running，真实cwd正确，NRestarts0，错误级日志0，最终切换及核验5.143秒 |

主要证据：release-state.json、gates.json及各门禁log、private-profile系列、shadow-recalculation.log、live-check.json、recommendation-check.json、production-*.png和production-errors.jsonl。收尾python3 tests/check_docs.py --diff HEAD检查157份文档0问题，仅3条既有篇幅提醒；git diff --check通过。自动索引使用check_docs.py --write-log-index生成，任务行单独暂存；其余8个原有文件逐字节一致，原有索引行保留为未暂存改动。归档检查结果与本地实施全量回归分开记录，本轮未把之前的1135项后端全量冒充重新执行。

## 未执行验证

真实PIN登录、实体手机触控、模型推理业务调用未执行。生产浏览器仅替换本地文档响应为已校验归档HTML，资源和只读业务GET使用生产，不改鉴权配置；不能等同完整真实登录验收。未在生产创建模拟反馈或改复核日期，反馈写入闭环已在隔离临时Vault验证。没有遗留发布失败；首次校验脚本失配、源码回退与第二次成功证据均保留。
