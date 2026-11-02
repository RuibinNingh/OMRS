# 2026-11-02 复习算法一次击杀与分档复核

> **任务**
> - 标识：review-algorithm
> - 状态：已交付

## 背景

用户原话：“改革OMRS的复习算法”“取消必须连续两次高分才算击杀的规则”“有方案吗?中途可以询问我”。用户确认一次高分击杀、五档7/21/60/120/180天、低分答对退出击杀并3天巩固、历史统一重算，并明确要求实现已确认计划。执行者Codex，完整模式；基线8e11f4e，计划见AI/plans/review-algorithm/plan.md。交付为本地v2.9.0实现、验证与单一垂直切片提交，不包含生产操作。

开工已有导出CSS、打印测试、README导出说明、模块文档和维护日志的未提交改动，原始diff及文件副本保存在 `/tmp/omrs-review-policy-cjsz5zw5/original.patch` 与同目录original中。独立原有路径逐文件字节核对一致；README与自动生成日志索引按任务内容分开暂存，原有导出改动不纳入本次提交。

## 行为变化

- 一次高分答对立即击杀。默认阈值7可调；非击杀态熟练度最高0.95，避免低分累积绕过判定。
- 复核间隔为7→21→60→120→180天，最高档循环；到期高分只升一级，逾期不跳档。提前及同日高分保留档位、周期起始日、原日期及累计击杀次数，只记录练习。
- 已击杀题低分答对显示磨合中，3天后巩固；答错回待攻克，1天后重练，熟练度惩罚不重复相乘。降级清空周期，重新击杀从第1档起步，累计成绩保留。
- ledger-v4新增复核档位和周期起始日，due_date为实际排期。网页反馈、助手预览、增量与完整重放共用唯一转换。升级按当前参数原子重放有效反馈，保留不可变原记录；失败不发布部分状态。旧击杀快照从第1档迁移，无可靠日期时待复核并立即入队，首次高分从7天起步。
- 设置接收五个严格递增正整数，废弃连对／复燃计算参数兼容读取但无效，保存清理。题库、详情、调度和结果显示档位与实际日期；复燃题纳入今日及逾期，休眠日期纳入预测。

## 影响文件

已使用git diff --name-status与新增文件清单复核实际范围：

- 后端：common、scheduling、ledger、projections、projection_runtime、data_repository、config_repository、feedback、sessions、stats、analytics；新增周期列、统一转换与兼容迁移、原子配置发布及推荐统计。助手预览原已调用transition_review，沿用同一转换，无须另加规则。
- 前端：domain/items、domain/question/view与新增review-cycle；dashboard、feedback、questions、schedule、settings的相关模块；移除按累计次数推测周期，统一复核文案与设置数组校验。
- 回归：test_revive_cycle、test_instant_feedback、test_config_publication、test_data_runtime与bench_data_runtime；arrange/dashboard/items/questions/settings-tuning的Node测试；dashboard/instant/settings的E2E及新增review_policy闭环。
- 文档：算法、数据、Ledger、API索引与查询/写入分册、受影响前端分册；本计划、进度、日志及自动索引。版本位置为omrs/version.py、omrs_dashboard.html、README和AI/README，变更摘要加入AI/changelog。
- AI/board.md、AI/export.md、原有导出日志、维护validation.json、导出CSS及smoke_a4_print.py均为原有改动，保留但不提交。没有改动生产配置、真实题库、路由或外部服务。

## 已执行验证

证据目录为 `/tmp/omrs-review-policy-cjsz5zw5`。全部服务测试移除OMRS_SYSTEMD_SERVICE与OMRS_BOXDETECT_CONTROL；浏览器用临时Vault与随机高端口。

| 验证 | 实际结果 | 证据 |
|---|---|---|
| 后端全量：python3 -m unittest discover -s tests -p 'test_*.py' -q | 1135项通过，175.908秒 | backend-full-final.log |
| 强化升级失败原子性后：python3 -m unittest tests.test_revive_cycle -q | 24项通过；失败时保留合成旧熟练度0.4、档位0和旧日期，再次启动成功重算为新规则 | review-atomic-final.log |
| node --test tests/app/*.test.mjs | 568项通过，0失败 | node-final.log |
| python3 tests/app/run_browser.py | 35项通过，0失败 | components.log |
| 页面E2E：feedback / instant / schedule / settings | 43 / 27 / 46 / 79项通过 | feedback-e2e.log、instant-e2e-final.log、schedule-e2e.log、settings-e2e.log |
| 页面E2E：dashboard / questions / data / history | 26 / 104 / 21 / 29项通过 | dashboard-e2e-final.log、questions-e2e.log、data-e2e.log、history-e2e.log |
| python3 tests/e2e/review_policy.py | 22项通过；真实反馈→击杀→到期推荐→复核→提前练习→降级→重新击杀，检查题库/详情/复盘/设置及手机宽度 | review-policy-e2e-third.log |
| python3 tests/check_ui.py | 五类违例计数均0，0问题 | ui-final.log |
| python3 tests/check_contrast.py | 58组，0不达标 | contrast-final.log |
| python3 tests/check_docs.py --write-log-index及--diff HEAD | 自动索引已生成，157份文档0问题；3条既有篇幅提醒 | docs-final.log |
| git diff --check | 通过 | 本地终端结果 |

后端全量使用 `PYTHONPATH=/tmp/omrs-review-policy-cjsz5zw5/test-deps:.`；原环境缺少可选segno，按requirements-zuoyebang.txt指定版本1.6.6安装到临时test-deps，未改仓库依赖。针对性重跑94项通过后，再完成全量。测试覆盖阈值边界、五档与最高档、提前/同日不延期、逾期只升一级、降级重练、重启/撤销/替换/恢复/完整重放、旧配置/快照/缺日期/日期上限及原始记录完整性。

首次后端全量1133项有2失败1错误：统计循环误覆盖总击杀数、即时练习旧预期仍为0.4及缺segno。已修复变量覆盖、更新幂等测试为一次击杀且不重复升档、补临时依赖。早期核心测试的旧连对与同日拉长周期预期已替换；旧结构模拟测试修正为新进程初始化。Node首次564项有2个旧字段计数/错误文案预期，修正后通过，再补4项达到568。E2E首次instant/dashboard各1失败已修复并通过；新增闭环前两次分别因测试读取不存在category及同路由未重拉Session而失败，修正测试导航后22项全通过。原始失败日志保留，未掩盖失败。

视觉命令：`python3 tests/visual/run.py --ref 8e11f4e --pages dashboard,data,questions,schedule,instant,feedback,settings --settings-section data --out /tmp/omrs-review-policy-cjsz5zw5/visual-final`。7页×浅深色×桌面手机共28档，脚本错误0；当前审计字号种类不超6、过小目标0、行内样式0、横向溢出0。报告为visual-final/report.html，数据为visual-final/audit.json；已检查主要页面前后截图。

| 页面 | 四档差异范围 | 解释 |
|---|---|---|
| dashboard | 0.337%–0.662% | 重放后击杀与待攻克计数变化，状态提示与版本页脚同步 |
| data | 0.247%–0.254% | 新算法重放后的熟练度/击杀及预测数据变化 |
| questions | 0.961%–2.747% | 一次击杀改变状态数量及排序，新增周期文案 |
| schedule | 15.548%–16.886% | 新击杀题进入休眠后候选从38减为31，后续列表顺序与整体高度改变 |
| instant、feedback | 0%–0.003% | 未选题首屏保持原布局，桌面仅版本页脚；提交结果另由闭环实际验收 |
| settings | 7.374%–16.105% | 连对输入改为五档间隔和说明，高级参数15减为13，卡片高度与后续区块位移 |

## 未执行验证

未进行生产部署、systemd/Nginx变更、推送、生产端口验证或真实题库重算，均不在本次授权范围。真实设备触控未测，手机验证使用Chromium视口。未另跑全仓无关页面E2E或大规模性能基准；已跑后端全量和受影响页面全路径。没有遗留的本地功能失败；后续上线须单独授权并在部署前备份、上线后核验重算回执及真实排期。
