# 2026-10-03 OMRS v2.2.0 生产部署与 GitHub 推送

## 背景与授权

用户原话：「完成后部署生产,提交GitHub」。执行者 Codex，完整模式。修复及完整验收已独立完成，工作区干净，基线719db03；实现757e1ed，v2.2.0。本任务只实施发布、上线核验、文档与正常推送，不改写开发日志。

## 发布准备

只读开工实测生产为omrs-97e0927/v2.1.0，主服务PID2579856，Tunnel及检测服务active/running、NRestarts=0。262活动题、扫描零冲突；助手67运行、收件箱169任务、草稿3任务均结束，MCP无running记录。七个.db路径中六个为实际SQLite，顶层旧inbox.db为空历史文件；全部quick_check为ok。磁盘约40GiB空闲。

已fetch远端，origin/main是本机main的祖先，修复分支与远端无分叉。最初准备源码从精确719db03归档，补修后的最终源码为ec12293，共享既有venv，不升级依赖或模型。升级后的存储不允许仅回退v2.1代码，故障需保全新事实并保持v2.2契约前向恢复。

## 发布前已实际执行的验证

已完成git状态/远端、systemd及监听、HTTP状态、纯SQLite只读盘点、任务与模型操作探测。首次停服一致文件归档在/root/workspace/apps/releases/OMRS-v220-preflight-20261002T180201Z/，tar比较及五项SHA全部通过，归档300431360字节；从停服到旧服务恢复约1.086秒，生产仍为旧版。真实副本的纯字节摘要验证720提交/269blob、六库integrity_check全部通过；新版scan后262活动题与1归档身份，当前正文无缺blob或冲突，既有历史缺口63项待原始副本对照。

复用生产Python3.13.5、MCP1.28.1、Pillow12.3.0与既有依赖，清除两个生产控制变量。全量unittest651项，110.678秒，退出0，无ResourceWarning或Traceback；系统Python的pytest报告7项通过（生产venv不含pytest，未安装依赖）。五个原始E2E：audit_identity15、instant23、MCP39、MCP扩展17、shell_router24，全部通过；六阶段升级/再升级/前向恢复再次通过。生产切换和推送待真实副本最终核验后执行。

门禁命令为env清除OMRS_SYSTEMD_SERVICE/OMRS_BOXDETECT_CONTROL后调用生产venv的python -W error::ResourceWarning -m unittest discover -s tests -p test_*.py -q，以及tests/run_gates.py --ref 17d6d84 --groups e2e,release --only e2e-mcp,e2e-mcp_expansion,e2e-shell_router,e2e-instant,e2e-audit_identity,upgrade-compat。原始日志保存在/tmp/omrs-v220-deploy-umcty7w1/。一次门禁命令误填不存在的e2e-audit_regressions，参数验证退出2且未运行测试；改成仓库真实audit_identity入口后全部直接通过。

## 未执行与下一步

未重复全量Node/组件/打印/UI/对比度/视觉/32E2E与万题十万反馈规模测量：开发轮已有完整结果，发布轮两项补修不改页面、算法或正常非空库路径，已运行风险相关验证、全后端及5关键原始E2E。Windows实机/目录刷盘、外部冻结检测模型和ChatGPT账户联调未执行；生产PIN不可取得，实际仅验证公开入口及MCP/本机授权读取，完整PIN主路径用隔离合成代理验证。生产不造业务测试对象。

部署与源码GitHub推送已完成，发布文档随后同步。没有剩余实施工作；生产出现问题保全最新事实，保持v2.2存储契约前向修复，不直接降级旧代码或覆盖上线新数据。

## 正文盘点发布前修复

部署契约审查发现，正文盘点后半段通过普通Ledger连接读取历史，旧库会被自动迁移。现改为单一SQLite只读事务覆盖投影、blob和全部历史引用，缺库时不创建错题目录；存在待恢复journal时领域入口及CLI均拒绝盘点。生命周期租约仍可建立独立维护锁文件，不修改业务数据。影响omrs/content_history.py、tests/test_content_integrity.py与AI/ledger.md。

实际验证：正文模块22项通过；正文加备份恢复关联36项通过。新增原生旧Schema夹具同时走领域入口及真实CLI子进程，逐项断言Schema、完整commits、全部文件SHA256和mtime不变，并覆盖缺库及待journal边界。使用719db03旧实现运行该回归时，领域与CLI两路均复现不变断言失败。全部使用临时合成Vault，未运行真实源初始化，源保全归档不变。

本修复收尾：已生成日志索引；`python3 tests/check_docs.py --diff HEAD` 检查94份文档、0处问题（2条既有大文件提醒），`git diff --check` 通过。未修改计划或维护环境文件，未提交，由发布主执行者集成。

## 影响文件（发布前切片）

已用git diff复核：正文盘点代码及三个回归、AI/ledger.md；计划总纲/进度登记追加授权，本独立日志与自动日志索引。没有修改页面、版本、生产配置、密钥权限或模型。后续生产环境及发布证据文档在上线验收后单独提交。

## 真实副本与备份兼容补修

真实副本正常启动后，默认严格差异检查只拒绝两项预期变化：首次配置发布追加的config.tuning_update事实及config.json补齐默认项。显式许可这两项后，原720提交/269blob逐项不变、39个原配置键SHA不变、六库全部旧业务列/行保持；助手1,203条旧事件转入run_events后语义逐条相同。恢复了1个被旧唯一约束挤掉的归档身份，历史投影235反馈。旧归档里的纯SQLite正文盘点确认63个历史缺blob全在首次snapshot之前，升级未增加缺口，当前262题正文完整。摘要工具首次直接只读SQLite时技术SHM/WAL变化导致严格stat拒绝；改为只打开外部字节副本，源stat前后相同。合成自检9项通过，覆盖业务改写/丢行/丢事件/外部编辑拒绝。

实际HTTP备份导出在真实副本返回400：旧顶层.omrs/inbox.db为零字节占位文件。该路径当前无消费者，实际收件箱在.omrs/inbox/inbox.db。现仅对这个旧零字节占位按普通文件保留；非空损坏文件及空的活动收件箱库仍拒绝，不删除或初始化旧占位。影响omrs/backup_store.py、tests/test_backup_recovery.py、AI/backup.md。新增完整备份/可信预检/恢复后原字节保留及实际收件箱数据保留回归，并证明异常库没有被例外放行。正文与备份关联38项通过，生产Python全量653项、111.048秒通过，无ResourceWarning/Traceback。

真实副本可信备份有876文件、282Markdown、541图片，254265617字节；冻结0.725秒，总备份/预检/恢复/盘点9.654秒。另一独立Vault恢复721提交、262活动/1归档、当前无缺口冲突，旧历史缺口仍63；原ZIP与恢复目录的全部业务行、列、事件、正文及不可变事实对照通过。材料在/tmp/omrs-v220-deploy-umcty7w1/real-backup-restore.json和real-restore-comparison.json。容量大规模数值仍采用此前实测；本次只读与旧占位兼容补修不宣称新的规模性能数字。

新公网验收脚本没有旧部署/回滚依赖，失败只留报告并吊销Key。合成远端代理真实PIN登录和页面/SDK/静态验证707检查通过，288静态hash；代理因浏览器取消页面请求出现BrokenPipe，业务服务无脚本错误。临时脚本初轮将JSON整数键与Python整数键直接比较、代理改Host导致Origin拒绝，分别规范JSON和保留Web原Host后通过；均未改业务代码。真实副本预跑695检查通过，287静态文件hash，46次技术调用、临时Key吊销、业务文件/SQL变化0。四项明示未跑：无现有报告源码、不提供真实PIN的授权登录、工作台HTML及浏览器登录主路径；完整路径由合成验证承担。一次副本只读核验与备份复现并发，备份按契约写入三份CSV导致差异检查拒绝；串行独立重跑后业务变化0，原失败报告保留。

## 最终生产切换与数据核验

从精确ec12293创建/root/workspace/apps/releases/omrs-ec12293，1,080归档文件SHA逐项一致，既有venv复用。归档目录实际执行正文/恢复38项、1.452秒通过。最后停服前复核所有任务及模型操作结束，保存完整原始Vault、旧源码与unit/drop-in；tar比较通过。停服期间再次复制最新数据，仅对最终副本初始化新版并逐字段比较，通过后原子替换三个release路径并daemon-reload/start；进入新版初始化后脚本明确禁止旧码自动回滚。停服到新服务就绪2.947804秒，2026-10-03北京时间08:33，PID217166；262题/零冲突/v2.2.0。

最终保全目录/root/workspace/apps/releases/OMRS-v220-upgrade-20261003T003307Z/为0700，18项材料文件0600、SHA全部核验；含原库主文件与WAL/SHM、旧源/unit/drop-in、before/after、部署及只读摘要脚本和实际检查JSON。不可变720事实/269blob逐项保持，新增721为脱敏配置原子发布审计；39原配置键保持，六实库旧业务行/列、1,203助手事件语义、普通内容文件全部保持。仅许可46条runtime只读验收追加、临时Key/最近使用元数据及配置默认镜像变化；旧零字节占位仍0字节。生产正文盘点262活动/1归档、当前缺blob0、冲突0、旧历史缺口63；不填造缺失历史。

生产公网SDK＋本机静态＋桌面手机PIN入口695检查通过（14.816秒），4项条件验证明示未执行；287本机静态hash一致，公网原生PNG351546字节与附件一致。22读工具精确发现、16隐藏写工具拒绝，实际调用46次均有终态脱敏记录；临时Key mcp_bbea816cc0b74932已吊销并401，既有Key权限/生命周期保持。没有生产题目、反馈、草稿、报告、展示板或确认写操作。主服务/Tunnel/检测服务active/running、NRestarts=0，检测PID1532134、模型指针及状态SHA一致；journal错误/警告级条目0，Traceback/BrokenPipe/ERROR/CRITICAL标记0。初次上线观测VmHWM/VmRSS71968KiB（本数据规模的时点观测，不当作规模峰值结论）。

GitHub常规快进已推ec12293，git ls-remote核实ec1229385e1b03cd7c43ca85228ae6b50da5b9b9；没有强推。上线产生的Vault根维护目录包含恢复暂存个人数据，补入.gitignore并用git check-ignore验证，不纳入提交。当前环境、数据目录、计划索引/进度、最终报告与发布材料同步，真实数据摘要和脚本仅存外部保全，仓库deployment.json仅留无秘密的发布摘要。本次最终文档提交随后快进合入本机main并正常推送；远端最终HEAD由收尾比对确认。

## 发布文档门禁

最终git diff --name-status与未跟踪清单逐项复核：九个路径，只有Git忽略、当前数据/环境、计划索引/进度/发布/报告、无秘密deployment.json及本任务日志；没有个人Vault或维护暂存数据被Git跟踪。日志索引已由脚本生成，本次已有索引项无需额外变化。python3 tests/check_docs.py --diff 17d6d84检查94份文档、0问题、两条保留历史计划尺寸提醒；git diff --check通过。生产和18项永久保全SHA再次核验通过。本次最终文档提交的业务源码与已上线ec12293相同，无额外部署或重启。
