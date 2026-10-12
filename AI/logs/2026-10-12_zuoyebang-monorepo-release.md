# 2026-10-12 作业帮同仓合入与生产发布

## 背景

用户原话：“部署在生产,提交GitHub”“服务器和OMRS时一体的,在一个仓库就行”。Codex完整模式，主仓基线e614f3a6f625f8385714aac4171870459a537c15；开工git status干净，main比origin/main领先11个既有提交。上轮隔离交付已完成，本次独立日志记录同仓与发布。

## 行为变化与影响范围

应用已验收OMRS补丁，按源码白名单纳入services/zuoyebang。网关保持独立进程／管理员／私有数据，同仓提交和发布。复用HTTPS8472的/zuoyebang/路径，面板采用相对资源／管理URL，OMRS客户端保留安全路径前缀，拒绝穿越／编码／查询。脱敏源码导出和Windows打包包含服务源码及依赖，排除私有运行目录和管理员秘密。版本同步为v2.5.0。

实际范围含原服务接入代码／测试、omrs/source_export.py与导出回归、同仓网关、deploy模板、pack_for_ai.bat、保留CRLF的.gitattributes、版本及受影响AI文档。按git diff --name-status和未跟踪清单复核，不纳入运行数据或凭据。执行说明见AI/plans/zuoyebang-service/exec-2026-10-12-release.md。

## 验证与发布状态

同仓门禁实际通过：全量Python961项（309.200秒，无失败／错误／跳过）、Node491项、网关52项及1真实Chromium面板、组件34项、设置75项、前缀双进程联调17项。UI全仓0问题，对比度58组全部通过，文档112份0问题、2条既有大计划提醒，git diff --check通过。全部使用临时Vault与随机高端口，移除生产控制环境，不接真实官方账号或付费模型。证据在 `/root/.hermes/cache/scratch/omrs-zyb-deploy-20261012/`。

首次前缀浏览器运行未通过，原因是生产Playwright1.62与候选浏览器1228路径不匹配；改用实际生产缓存/root/.cache/ms-playwright后完整通过，没有修改渲染实现。网关原静态测试仍断言绝对资源路径，按前缀契约改成相对路径，保留资源HTTP／安全断言；最终52项全部通过。Windows脚本保留CRLF，通过限定文件的Git空白属性校验。

生产准备复核：当前v2.4.1、300题、0冲突，后台／恢复／作业帮任务均为空；新网关unit与数据目录尚不存在。最终保全基线在停服后重新采集，不采用上一轮299题的历史值。功能提交后继续精确release门禁及生产切换。

## 视觉差异

settings/create浅／深×桌面／手机8组前后比较，无页面脚本错误。设置浅桌面0.245%、深桌面0.263%、手机各0.012%；录入桌面各0.004%、手机0%。变化为新增服务导航和侧栏v2.5.0版本标识；前缀联调另外验证管理弹窗、资源与Cookie路径，未改变控件布局。

## 未验证项

未导入或迁移真实设备凭据，未验证真实官方登录、签名期限、搜题及付费模型。Windows打包只能检查脚本，本机没有Windows执行环境。

## 提交与精确发布

功能提交08dce8bf8d306b97a3cf7159705b3e04321223b5（v2.5.0）已推送RuibinNingh/OMRS的main，包含本次110个代码／测试／文档文件。既有11个未推送提交随main快进发布，没有强推或另建仓库。运行源码为/root/workspace/apps/releases/omrs-08dce8b的Git归档，1434个文件逐字节一致，生产依赖复用omrs-zyb-deps-20261011。

精确release隔离门禁12/12组全通过：后端64、Node491、网关52及1真实面板、前缀双进程17、设置75、原录入124、服务26、作业帮49、组件34、UI0问题及58组对比度通过，无跳过。命令与stdout在本轮证据目录release-gates.json、release-validation/，未把工作区全量961冒充精确release全量。发布记录另行提交，不改变运行源码pin。

## 生产部署与保全

2026-10-12 12:41:43至12:41:49 CST切换，约5.596秒。停服前再次确认无任务／恢复意图，停服后备份Vault及maintenance，tar比较、解包文件字节和SQLite完整性通过。保全目录/root/workspace/apps/releases/OMRS-v250-zyb-release-85epz6pq，目录0700／文件0600。失败路径预设恢复源码别名与新增控制配置，保留最新Vault；本次没有触发回退。

持久源码别名omrs-9b29d49原子指向omrs-08dce8b；主unit/drop-in保持。安装omrs-zuoyebang.service，共用源码／依赖并监听127.0.0.1:8745，私有数据/var/lib/omrs-zuoyebang。在既有HTTPS8472入口增加/zuoyebang/，覆盖XFF并将Secure管理Cookie限制到服务路径；Nginx语法与unit校验通过，仅reload授权Nginx。Tunnel／检测服务与模型控制配置保持。

在服务器内使用初始管理员秘密登录HTTPS面板，生成OMRS生产调用Key，通过主服务真实Web接口保存连接并测试；秘密仅在内存传递，没有输出或提交。OMRS配置为external，地址https://home.ruibin-ningh.top:8472/zuoyebang，明确不信任私网目标；同仓同机仍走鉴权。网关未导入设备或账号，无真实官方调用。允许外部访问只在初始化设置，unit不强制每次重启重新开启，后续面板关闭会保留。

生产读回：49张业务表、937个正文／图片／关键配置文件保持，300题、0冲突、待审0；PIN、原MCP Key与模型保持。两服务active/running、NRestarts=0，实际cwd为同一release的主目录／services/zuoyebang。真实生产27/27检查通过，含资源字节、匿名鉴权、私有文件拒绝、伪造XFF拒绝、HTTPS连接、390px面板登录／Key元数据／来源IP／登出、Cookie属性、OMRS PIN入口与无横溢／脚本错误，两个unit启动后无错误级journal。记录在production-checks.json与read-live.log。

## 下一步

用户在管理面板导入已登记设备凭据，再核对真实账号及搜题。运维保留受限发布保全与源码回退指针；初始管理员密码由服务器所有者读取/var/lib/omrs-zuoyebang/admin-secret.txt，不写聊天或GitHub。
