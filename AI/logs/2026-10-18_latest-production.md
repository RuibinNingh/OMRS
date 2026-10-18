# 2026-10-18 最新提交合并与生产发布

## 背景与授权

用户原话：「合并最新的提交,部署生产」。执行者Codex，完整模式。本轮开工分支codex/ai-review-entry为447ea2a，远端main为98fdeba；生产仍为c312872精确归档、v2.8.2。合并设置日志导出、识别中提示和静态SVG附图修复，沿用版本号、依赖及现有部署方式。

开工已有AI/plans/omrs-maintenance/validation.json未提交修改，SHA256为3d3cdbd203731931981a4db6d940cae48878e1069d55c1c2008c361aa58be9f9。已将原文件和补丁保存在仓库外，本轮不覆盖、暂存或归档该工作区修改。

## 合并范围

git fetch origin后核对两侧提交。远端5d2abb8是本地447ea2a识别提示的独立发布副本，业务文件逐字节相同；本地另有cfd2727日志导出，远端另有98fdeba附图修复。三方合并自动成功，无代码冲突，双方文档、测试和历史日志均保留。

已用git diff --cached --stat、git diff --cached --check及识别提示业务文件对比复核实际变化。发布源码固定为合并后的Git提交，不使用带未提交修改的开发目录运行生产。

## 已实际执行的验证

验证使用既有完整依赖解释器omrs-zyb-deps-20261011/.venv/bin/python；启动前清除生产控制及共享CDP变量，所有功能服务均使用临时Vault、随机端口和独立Chromium。原生产题库只用于部署前只读预检，不作为测试数据。

- node --test tests/app/*.test.mjs：542项通过，0失败或跳过。
- python -m unittest tests.test_log_export tests.test_http_boundaries tests.test_security tests.test_source_export tests.test_write_lock tests.test_web_assets tests.test_asset_cache tests.test_zuoyebang_svg tests.test_zuoyebang tests.test_zuoyebang_render tests.test_zuoyebang_geometry -q：128项通过。写锁回归中的预期503与Pillow弃用提醒不代表失败。
- python tests/app/run_browser.py：35项通过，0失败或脚本错误。
- python tests/e2e/settings_logs.py：29/29通过，包含真实ZIP、筛选、重试、生命周期与浅深主题320／390／1440px。
- python tests/e2e/settings.py：75/75通过，原设置分区路径保持。
- python tests/e2e/zuoyebang.py：157/157通过，包含SVG着色路径绘入PNG、识别提示、失败重试、人工核对、幂等入库和刷新恢复，无脚本错误。
- python tests/check_ui.py：全仓0问题；python tests/check_contrast.py：58组通过。
- python tests/visual/run.py --ref c3128729dc523b964fbaf45030904f5f332bd6d8 --pages settings,zuoyebang --settings-section service：8组前后截图完成，无脚本错误、横溢、行内样式和过小目标。

python3 tests/check_docs.py --write-log-index已生成索引；--diff HEAD与--diff c312872均检查146份文档、0问题、3条既有体积提醒。git diff --check通过。精确归档核对和生产切换结果在完成后追加到本日志，不把尚未完成的步骤记为通过。

## 视觉差异

设置页浅／深桌面分别为1.040%／1.027%，浅／深手机为4.254%／4.194%；新增日志导出说明、卡片与按钮使源码协助区域下移，临时Vault路径不同亦影响路径行。作业帮四组静态页面均0差异；识别期间提示由真实流程回归覆盖。已查看深色手机设置页及320px日志窗口截图，日期、长文件名和固定页脚完整。

## 发布保护与未执行边界

生产预检未发现有效在途任务、恢复journal、正式写入意图、扫码或检测受管操作，训练锁可获取。正式切换前再次复核，持锁停服后保全Vault、maintenance和网关私有数据，校验解包与SQLite完整性，再原子切换源码别名；异常只回退源码并保留最新业务数据。

不执行真实官方搜题、付费模型调用或生产测试入库；实体手机、Safari与Windows浏览器未验收。原有计划的真实环境验收取舍与R14来源限制不属于本次发布范围。

验证日志、截图、已验证源码哈希与发布驱动位于/root/workspace/apps/releases/OMRS-latest-release-dbypl3ni，权限受限；不提交私有备份或凭据。

## 实际合并与生产切换

合并提交为e400742d874ccbb3c2ca8ba3cad14d42e3b295f3，包含本地447ea2a与远端98fdeba两侧历史。main从既有d1a7169快进到合并提交，再以普通推送从远端98fdeba前进至e400742；git ls-remote回读一致，未改写远端历史。

生产精确归档/root/workspace/apps/releases/omrs-e400742的1557个源码文件与Git归档逐字节一致；另将1148个已运行门禁的源码／测试文件与归档逐一核对SHA256，未重复计数原验证。归档内文档差异门禁检查146份、0问题、3条既有提醒，全部10组发布门禁通过。

2026-10-18 09:36:27（北京时间）完成原子切换与主要检查，共4.579秒。原稳定别名omrs-9b29d49从omrs-c312872切至omrs-e400742，主服务、作业帮网关和检测真实cwd均位于新归档的相应目录，active/running且NRestarts=0。版本v2.8.2、unit/drop-in、依赖、Nginx、隧道、模型身份及revision保持；未执行回退。

停服前与持训练锁停服后两次核对任务、恢复及写入意图。私有保全/root/workspace/apps/releases/OMRS-latest-backup-qva2ytue包含新旧源码、unit、Vault/maintenance和网关数据，两份tar实际比较并解包验证1248个文件和8个SQLite库。49张原业务表的全部原列／原行、1079个原正文／图片／关键配置文件及网关账号／设备／凭据保持；核对时322题、0冲突和0待审，题数只作当时观察值。

10份线上版本化资源覆盖作业帮工作窗、页面及共享组件，另含日志控制器／视图／样式、服务分区与dialog；均与归档逐字节一致，immutable和条件请求304通过。公网入口200，主数据／MCP／网关业务匿名401，网关健康200。

## 生产浏览器与收尾

独立Chromium实际访问1920／390px公网PIN入口与受保护的作业帮直达，两档均无页面横溢。在线真实模块在浏览器内合成状态下生成双预览、单确认按钮和双正文工作窗；识别中提示实际出现并在结束后移除，模拟识别回调一次，提交回调0次。在线设置模块的日志导出入口、四项筛选与合成文件勾选正常；全程无脚本错误或生产写请求。

实际本机GET /api/logs返回200、有效清单和no-store，公网匿名同路径401；回环MCP无Key401，10份版本化资源公网匿名均401。未下载真实AI日志或调用日志导出POST。浏览器后再次核对49张原业务表、1079个原文件、网关凭据与控制配置保持，三个服务发布后错误级journal为空。

部署证据保存于本轮发布目录，验证驱动与结果复制到私有保全。收尾仅更新AI/environment.md和同一任务日志，日志索引由脚本生成；生产源码继续固定e400742，文档提交另行同步main。未改变既有计划状态或原有未提交验证JSON，真实账号／模型和实体设备的未验证边界保持。
