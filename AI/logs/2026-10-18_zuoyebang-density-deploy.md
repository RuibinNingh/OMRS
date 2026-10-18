# 2026-10-18 作业帮题图密度调整提交与生产发布

## 背景与授权

用户在题图密度调整交付后要求「提交GitHub,部署生产」。执行者Codex，完整模式。本次发布15px正文、1.5行高、1080px完整PNG及mobile-360-v2排版版本，产品版本保持v2.8.3；实现与上一轮实际验证见AI/logs/2026-10-18_zuoyebang-density.md，不改写其交付时事实。

开工基线e6c8ab9d42c4cf6a3a2240ceb65ee68e9281c0e7；本地main比origin/main领先107989b、e6c8ab9两个已部署的框选服务提交，fetch后远端无新增提交，本次随正常快进同步。原有AI/plans/omrs-maintenance/validation.json的SHA256为3d3cdbd203731931981a4db6d940cae48878e1069d55c1c2008c361aa58be9f9，保持原样，不暂存、不提交、不带入发布归档。

## 发布前已实际核对

生产源码别名当前指向/root/workspace/apps/releases/omrs-107989b，三个服务均active/running、NRestarts=0；端口、unit、网关、模型与私有连接沿用当前配置。恢复／正式写入意图及审核、助手、收件箱、草稿、运行、作业帮、网关扫码和旧受管模型操作预检通过，八类实际在途任务均0，训练锁可获取。

上一轮已实际通过56项相关Python、550项Node、35项组件浏览器、157项作业帮页面、58组对比度与UI零违规，以及4组标准页面视觉对比。本轮另从Git精确归档执行下述发布门禁，并核对生产资源、服务与原业务数据；没有把上一轮结果重复计作归档验证。

## 状态与影响文件

实现提交1740051de79b733e55495b01b9cd6ae5034fa302（调整作业帮题图字号与行高）含题图渲染、排版版本、现有测试及对应模块／README文档、实现任务日志、本日志和自动日志索引共14个路径，已普通快进推送GitHub main，并通过git ls-remote回读确认。生产收尾另更新AI/environment.md与本日志，不改历史实现日志。

## 精确归档与门禁

线上源码为/root/workspace/apps/releases/omrs-1740051，1596份文件与Git归档逐字节一致，.venv仅链接原依赖，未安装或升级包。驱动和私有证据目录为/root/workspace/apps/releases/OMRS-zyb-density-release-wk9zk30q，目录0700、文件0600；包含release.py、verify_production.py、source.tar、old-source.tar、gates.json及各组日志。凭据、原始业务数据与保全均留在仓库外。

从该归档实际运行七组检查，均退出0。Python解释器为归档.venv/bin/python；移除OMRS_SYSTEMD_SERVICE、OMRS_BOXDETECT_CONTROL、OMRS_TEST_CDP_URL等环境，隔离服务使用临时Vault、随机高端口和独立Chromium，不读取生产题库。

| 检查 | 实际命令与结果 |
|---|---|
| 后端专项 | python -B -m unittest tests.test_zuoyebang_render tests.test_zuoyebang_svg tests.test_zuoyebang_geometry tests.test_zuoyebang -q；56通过 |
| Node | node --test tests/app/*.test.mjs；550通过、0失败、0跳过 |
| UI | python -B tests/check_ui.py；全仓零违规 |
| 对比度 | python -B tests/check_contrast.py；58组通过 |
| 组件浏览器 | python -B tests/app/run_browser.py；35通过 |
| 作业帮页面 | python -B -u tests/e2e/zuoyebang.py；157/157通过 |
| 文档 | python -B tests/check_docs.py；150份文档、0问题、3条既有大文件提醒 |

## 首次切换中断与修正

首次停服保全完成后，驱动复用了旧检测服务的匿名/health检查；当前独立框选服务要求该路径携带Key，实际返回401，因此等待超时。原子别名已自动回到omrs-107989b，但回退分支又被同一检查阻断，主站和网关未自动启动。发现后立即逐一启动主站与网关，三个原服务恢复active/running、NRestarts=0；49张原业务表、1084个原文件及网关／框选私有数据核对保持，没有用旧备份覆盖数据。

首轮状态、备份及恢复结果完整保存在attempt-1。只修正仓库外驱动：存活检查使用当前/healthz，模型身份通过主站既有Key的只读/api/boxdetect/status核对；回退分支先尝试恢复全部进程，再统一检查健康，避免单个检查阻断其它服务恢复。修正后在旧生产上实测存活与模型身份，再复核11类在途计数全0及训练锁，继续发布。未改应用源码、鉴权、Key或unit。

## 成功切换与保全

第二次持训练锁停止三个服务后再次预检，保全Vault、maintenance、网关和框选私有数据。vault.tar与gateway-private.tar解包比较1254个文件、8个SQLite库完整性通过；boxdetect-private.tar另比较2个文件、1个SQLite库完整性通过，共1256个文件、9个数据库。

2026-10-18 14:43:39（北京时间）完成切换，release-state.json为deployed。稳定别名omrs-9b29d49原子指向omrs-1740051，三个服务真实cwd分别为归档根及对应services目录，均active/running、NRestarts=0。成功轮停服、保全、启动及主要检查共4.302秒，不代表首轮中断时长或单独测得的HTTP不可用时长。

49张原业务表全部原列原行、1084个原正文／图片／关键配置保持；核验时325题、待审0、冲突0，此数字不是后续业务约束。框选原历史、管理员凭据、调用Key、模型及主站连接保持，网关账号／设备／Key／设置保持，Nginx、隧道、unit与模型控制配置未改。

## 生产验收

用归档解释器执行verify_production.py，41/41通过、production-verification.json的success=true。四份作业帮脚本的线上版本化地址与归档字节一致，immutable及回环304正常，线上排版版本为mobile-360-v2；归档正文15px、1.5行高，富文本正文同为1.5。未登录的业务、题图工作台脚本、MCP、网关与框选调用被拒绝；主站保留原Key并正常连接网关与当前框选模型。

独立Chromium访问公网1440／390px入口，PIN可见、无横溢或未捕获脚本错误；未提交PIN，拦截所有非GET/HEAD/OPTIONS请求，实际写请求0。截图在production-entry-1440.png与production-entry-390.png。浏览器后再次复核原业务表、文件、网关和框选私有数据保持，三个服务发布后错误级journal为空。

## 未执行与收尾

未执行真实官方搜题、扫码、付费模型、实体手机、生产测试入库或与本次无关的全仓测试；业务主路径由归档隔离E2E覆盖，生产只读验收不冒称真实搜题验收。版本保持v2.8.3，刷新页面后新生成题图使用新版密度，未入库旧预览可主动「重新生成手机版」。

AI/environment.md同步当前归档、保全及验收事实，为40333字节、低于40KB。已实际运行python3 tests/check_docs.py --write-log-index及python3 tests/check_docs.py --diff 1740051，150份文档、0问题、3条既有大文件提醒，退出码0；git diff --name-status和git diff --check已复核。原validation.json的SHA256仍与开工一致，保持未暂存。收尾提交只包含环境分册和本日志，线上继续运行已验收的1740051精确归档。
