# OMRS 全面修复验收报告

执行者：Codex，完整模式。基线17d6d84/v2.1.0，工作区版本v2.2.0；本地修复和验收，未部署或推送。验证来自真实模块与原始浏览器入口，不使用原审计计数代替修复结果。

## 1. 十九项缺陷证据

表内测试直接调用真实模块；浏览器使用临时Vault及随机端口。全部原始E2E保持其入口直接运行，登录/导航/就绪等待和保存回执已改成真实行为等待，未放宽业务断言。

| 编号 | 缺陷与修复行为 | 可重复验证入口 |
|---|---|---|
| A01 | Session以entries绑定创建时question_id；详情预览与下一题也使用ID，UID移动/复用后不串题，旧无法证明条目人工绑定 | test_data_runtime的archive_and_uid_reuse、move_old_uid_feedback、unproven_bootstrap；e2e/audit_identity |
| A02 | 展示板有ID时只查原身份，删除后显示缺失，不回退同UID新题 | test_board_identity的archived_reference；e2e/audit_identity同UID板行 |
| A03 | 活动题partial UNIQUE，归档完整保留；取消题目INSERT OR REPLACE并从Ledger重建 | test_data_runtime的archive_and_uid_reuse；升级演练 |
| A04 | 逐卡预留身份/摘要；创建事实与回执同Ledger事务，跨库失败只补状态 | test_inbox_atomic_commit：8并发、各持久化步骤故障、Ledger后kill、冲突/reset |
| A05 | 各独立SQLite用backup()捕获WAL，不直接复制热库文件；staging后锁外压缩 | test_backup_recovery的online_snapshot、barrier_coordinates；bench_backup_runtime |
| A06 | 同文件系统恢复journal；提交标记前回旧库、后保新库，启动先恢复 | test_backup_recovery的journal_failure、subprocess_interruption、rename/fsync、rename与journal间kill |
| A07 | PIN按Vault/IP串行计算失败窗口，五次失败触发限流 | test_http_boundaries的parallel_wrong_pin |
| A08 | 加载推荐先退出卡片上下文，每次操作只请求一次 | app/audit-controllers的练习卡加载推荐；原e2e/instant及practice |
| A09 | mount/read/round请求身份校验，离页与新轮次废止旧结果 | app/audit-controllers的旧挂载/补拉/旧轮次；e2e/audit_identity的同UID qview迟到读取 |
| A10 | 混合反馈只移除明确成功行，失败/缺回执保留判定分数备注及顺序；刷新失败不报完成 | app/audit-controllers的手工反馈、Session刷新；原e2e/feedback |
| A11 | cards所有省略字段保留，labels省略不变、[]清空，最终Markdown一致 | test_inbox_atomic_commit的omitted_labels；原e2e/create |
| A12 | 元数据对前后Markdown版本做差量，不用旧YAML覆盖当前学习状态 | test_data_runtime的metadata_does_not_restore_stale_markdown_learning_tag |
| A13 | 同一纯transition_review用于投影及助手预测；反馈转换、事实与增量投影同事务，响应取实际入账结果 | test_data_runtime的batch_response_matches_sequential_persisted_transition；反馈与复燃回归 |
| A14 | 展示板删题、留白、详情、补印按稳定ID；纸面允许当前移动UID且不改归属 | test_board_identity的current_uid_remove；原e2e/board、board_picker；audit_identity双身份留白 |
| A15 | 保留UTC时区和原recorded_at；新记录/可靠带时区记录取Asia/Shanghai业务日，旧无时区保留原时间与精度 | test_data_runtime的timezone_business_date；原统计、排期及真实浏览器 |
| A16 | sort:none仅筛选且保留后端推荐序 | app/audit-controllers的推荐筛选；原e2e/instant、schedule |
| A17 | 鉴权/读取/校验在写锁外，统一限额及超时；旧世代正文拒绝分派 | test_http_boundaries的slow_body、body_from_previous_generation；真实HTTP |
| A18 | 图片统一受限路径解析，拒绝绝对/遍历/双编码/符号链接越界 | test_http_boundaries的image_absolute_traversal；导出与题图回归 |
| A19 | HEAD使用GET的同一授权、资源白名单及路由，仅不发送正文 | test_http_boundaries的head_uses_get_auth_and_resource_allowlist |

完整文件位置：Python入口均位于tests/，Node入口位于tests/app/，浏览器入口位于tests/e2e/。全部十九修复及治理代码对应本地提交757e1ed（v2.2.0），最终文档提交与状态见progress.md。

## 2. 完整维护性治理

内部读取SQL；普通反馈禁止full_project及整表删除的测试通过。流式全量重放、SQL修正索引、有界快照与按需CSV均有容量验证。固定种子20261002随机事件逐字段比较增量/完整投影；参数变化与投影发布同事务，失败回旧状态，mirror_pending与第三方冲突有故障回归。

助手事件落run_events，1000完成运行移出内存；1300事件验证缓存淘汰、稳定游标、完成和重启。71对话分页与旧events_json迁移有真实模块测试；浏览器验证66对话、45运行和411事件全部可访问。默认分页与上限按计划合同。

生命周期屏障覆盖Web/MCP/CLI与后台磁盘入口；跨进程锁及世代使恢复后的旧任务无法写新库。模型网络、复盘ZIP、上传读取和备份压缩/下载位于锁段外。备份预检检查路径、大小、hash、SQL和Ledger；stage修改、磁盘失败和不确定journal拒绝执行/启动。

HTTP注册表与领域mixins、前端身份/date/upload工具替代重复实现。启动、手工/后台扫描不生成或轮转CSV；显式export-csv命令与备份才流式导出当前SQL。删除无消费者旧评分函数、旧CSV导入、废弃恢复变量和依赖已删全局的旧调度冒烟；新调度E2E及Node仍纳入门禁。API/data文档分册与README事实同步，原已完成计划保留。

## 3. 容量实测

设备：Intel Core i5-12400，Linux 6.12.86 amd64，Python3.13.5。固定随机种子，10000实际Markdown及正文blob、100000有效反馈，未使用真实题库。RSS取独立进程VmHWM，不能据此保证其它硬件同延迟。除普通反馈50次外，每条路径5个独立样本、复制同一基线；P95为最近秩，5样本即最大值。容量原始样本与元数据已入库capacity.json。

| 路径 | P50 | P95 | 峰值RSS |
|---|---|---|---|
| 普通反馈，50次且禁止全重放 | 1.545ms | 2.499ms | 74.45MiB |
| 冷投影读取 | 0.086s | 0.092s | 75.35MiB |
| 磁盘启动/扫描/正文盘点 | 3.666s | 3.721s | 115.24MiB |
| 完整重算 | 2.647s | 2.757s | 107.85MiB |
| 调参即时重算 | 2.645s | 2.665s | 111.38MiB |
| 单历史修正 | 2.842s | 2.897s | 119.09MiB |
| 十万历史修正 | 6.477s | 6.722s | 118.34MiB |
| state.restore | 2.758s | 2.786s | 119.51MiB |
| SQL stats+analytics | 1.661s | 2.191s | 191.28MiB |
| CSV流式导出 | 0.948s | 1.015s | 75.42MiB |
| 全库备份 | 2.779s | 2.794s | 77.26MiB |
| 备份冻结 | 1.617s | 1.632s | 同上 |
| 恢复含捕获/预检/交换全流程 | 11.222s | 11.353s | 186.51MiB |
| 冷服务启动及一次全库stats | 5.326s | 5.392s | 275.58MiB |

最终源码冻结后在无浏览器/单测负载窗口复测调参、数据启动、普通反馈和全部备份/恢复/服务路径；五条路径各5个独立样本，加一个连续50次反馈进程，16份相关源码起止哈希一致。其它七条未改变的路径保留既有五样本测量，来源分别登记capacity.json，不把保留样本说成此次重跑。恢复总流程包含创建备份、预检与交换/初始化；预检P50/P95为5.653/5.684s，实际交换/初始化为2.748/2.829s。HTTP就绪为3.781/3.831s，万题统计请求为1.545/1.601s，表中总流程包含两者。CSV样本独立复制基线，不受十万修正额外历史影响。所有已测路径低于768MiB，最大275.58MiB，不声明未经测量的提速倍数。

## 4. 已实际执行的验证

最终源码冻结后的整仓648项unittest、7项pytest、436项Node、34项组件浏览器、7项打印全部通过；unittest无ResourceWarning。UI零违规、58组对比度通过。48组默认视觉及新增设置数据分区4组均无脚本错误，差异逐项解释见visual.md。

32个原始E2E在冻结代码上全部直接通过，共1089断言；实际命令、耗时、日志及计数登记validation.json。外壳在并行运行时PIN解锁点击的隐式导航等待8秒超时一次，未改变脚本/断言/时限，单独原入口重跑24/24通过；失败轮同样留在validation.json。没有用临时适配结果替代正式验收。

统一入口tests/run_gates.py同时登记unit、pytest、Node、组件、打印、E2E、release、visual及docs。AST核对只有test_report_export.py使用模块级pytest风格，7项显式执行，没有依靠unittest漏掉它们。最终路由/日志索引分别生成，文档门禁和diff检查结果登记validation.json。

## 5. 未执行验证与限制

未实际执行Windows LockFileEx环境、外部冻结boxdetect模型/数据与ChatGPT账户联调。运行受管服务控制E2E使用假的控制端，未控制真实systemd。Windows持久目录刷盘的语义需在目标平台验收，Linux故障/中断结果不冒称跨平台保证。

v2.1代码回退兼容性与重新升级实测见release.md；禁止直接用升级前备份覆盖上线后新增。其它可选优化仅在AI/optimization.md登记，不重复挂缺陷。用户追加授权后的实际生产部署与GitHub推送见§7；未更改Nginx或独立模型。

## 6. 实施中另外发现的缺陷

长期连续高分曾使SM-2/复燃日期突破date.max，已限制到可表示日期并补长序列回归。旧代码只重写SQL而不追加提交曾使新检查点误判有效，现投影表DELETE在同事务废止元数据，重新升级验证SQL与状态一致。批量标记回包曾按旧UID乐观更新，现只更新冻结的question_id，有迟到/UID复用回归。备份目标连接创建失败时关闭已打开源连接；目录ZIP数量、数据库护栏集合和上传空间/长度检查均已补回归。这些附加修复不挪用A01–A19编号。

跨进程配置发布补齐三种竞态：迟到发布者不能覆盖较新镜像；配置字段/版本/重算摘要在同一读事务返回；投影在取得SQL写事务后读取有效参数。反馈同样在写事务内校验链头和policy，不符时先重建再重试；事实、学习状态与响应同一事务，投影失败整体回滚并废止内存状态。第三方无效JSON也保留两份配置并报镜像冲突；撤销Session不再接受无效反馈。

恢复严格要求JSON布尔true确认，暂存备份在锁外流式校验哈希/长度并重查世代，同长度篡改与增长均拒绝。JSON引用使用普通限额，任意声明multipart不能绕过限额；MIME主类型大小写不影响类型判断。设置页新增19项学习参数（4常用、15高级）及重算进度/回执，断连后核验实际版本和完整有效参数。缺IANA数据库时1992年后的上海日期可使用UTC+08回退，更早历史与未知时区保留原信息。

## 7. 生产发布补充（2026-10-03）

用户追加授权后，发布前复核补修正文盘点只读迁移漏洞（d524c91）和旧零字节inbox.db的备份阻断（ec12293）。生产Python完整653项与精确release关联38项通过；当前生产为ec12293/v2.2.0，停服2.948秒。真实副本严格升级、可信备份恢复和生产数据对照通过，原720事实/269blob及全部独立业务行保留，归档身份恢复1项；当前262题正文完整，63项旧历史正文缺口不变。合成完整PIN707检查、真实副本与生产各695检查通过；生产实际PIN未提供，工作台登录在隔离环境验证。

GitHub main已正常快进推送并核实源码SHA ec12293，后续发布文档同步；主服务/Tunnel/检测服务均正常，原模型保持，无错误日志。18项保全材料位于/root/workspace/apps/releases/OMRS-v220-upgrade-20261003T003307Z/，权限0700/0600。不能只回退v2.1代码，保留新事实按当前存储契约前向修复。详细发布、实际未验证项与计数见release.md、deployment.json及独立生产日志；原容量数据未因这两处兼容补修重新测量。
