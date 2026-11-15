# 2026-11-15 调度统一导出与提醒素材库

> **任务**
> - 标识：schedule-reminders
> - 状态：已交付

## 背景

用户原话：「首先把\"导出打印版\"和\"导出屏幕版\"合并」「标记没有错因的题目」「允许创建提醒svg」「调度页面新增一个标签页,允许用户删除新增svg」「打开一个svg面板,画廊式选择」「先设计ui 给我草稿」。用户接受可点击草稿后授权：「可以 执行下去 完成后版本号+0.1 提交GitHub部署生产」。执行者Codex，完整模式。基线b056e4a，开工工作区干净；本次按次版本递增为v2.12.0，明确授权提交、推送与生产部署。

用户随后要求「先快速切换生产,我急用,后面的慢慢来」。据此从精确归档完成快速门禁后优先上线，相关完整归档回归及生产只读页面验收随后补齐；没有以加急为由跳过停服备份、活动任务预检或原数据校验。本任务不属于进行中的计划。

## 行为变化

合并导出入口；导出可选动态「待补错因」标记；调度页新增提醒素材库，支持AI生成、导入、删除、新计划默认和本次导出画廊选择。旧计划保留快照。内置助手与外部MCP只可新增素材，不改变默认或删除素材。

首页提醒指导出文件第一页横幅。v2.12.0已于2026-11-15上海时间17:38切换生产，地址https://home.ruibin-ningh.top:8472。功能提交68fdbe75a77b18d685f80c34c993617fcca8138c已推送GitHub main并核实远端；发布记录另作纯文档提交，生产继续使用该功能归档。

## 影响文件

`git diff --name-status b056e4a`与未跟踪清单逐项核对，本轮改动仅属于此任务：

- `assets/app/features/schedule/`：统一导出、缺错因参数、提醒库／新增／画廊和手机标签布局；设置页提供管理直达和MCP独立权限。
- `omrs/schedule_reminders.py`、`schedule_banner.py`、HTTP注册／处理与锁边界：私有素材、AI预览、幂等回执和默认CAS；旧模板只读兼容，不迁移真实题目。
- `omrs/exporting.py`、导出模板／字体：动态题号标记及素材快照选用；AI工具、MCP与运行记录同步新增提醒能力。
- `tests/test_schedule_reminders.py`及相关MCP／Node测试、调度与导出E2E、新提醒专项：覆盖真实业务链路。
- 根README、版本、AI索引／变更记录、模块文档、路由和日志索引同步；没有修改生产unit或Nginx配置。

## 已执行验证

- 定向后端147项、导出／写锁等37项通过；有交集，不合并为不重复总数。最新素材及横幅12项通过。最初MCP新增未列为技术准备、撤回夹具误用RF身份均已修复；首次直接导入MCP测试缺PYTHONPATH，按仓库配方重跑通过。
- `node --test tests/app/*.test.mjs`601项通过；`python3 tests/app/run_browser.py`35项通过；UI全仓0问题，对比度58组全部通过。
- `tests/e2e/schedule.py`54项通过；初跑手机三标签挤压导致6项审计失败，修复顶部标签／全库导出分行后全部通过。`tests/e2e/schedule_export.py`22项通过，含离线A4、PDF页数、屏幕版、取消／重试和参数记忆。
- 提醒专项28项通过，覆盖设置直达、安全SVG拒绝与文件导入、真实兼容客户端连接合成模型HTTP服务、保存、默认、删除、旧计划快照、画廊取消／选中素材被删、缺错因标记与320／390／1440px浅深主题。首次暴露未知图标sparkles，改用既有sparkle；新建测试计划需刷新列表并等待详情后断言，已修正测试等待。证据`/tmp/omrs-reminder-shots-xw6b8yyz`；后续增加真实画廊下载与重新打开快照检查，最终30项全部通过，证据`/tmp/omrs-reminder-shots-552g2mnn`；发布归档再跑同一最终专项。
- `python3 tests/visual/run.py --ref b056e4a --pages schedule,settings --out /tmp/omrs-reminders-visual`8组对比完成，脚本错误0、审计均无溢出／过小控件／行内样式。调度桌面浅深0.014%为新增标签及版本号；调度手机15.351%／16.918%为顶部标签与全库导出分行；设置桌面21.512%／21.548%、手机16.928%／16.954%为旧SVG编辑卡收为素材库直达入口、页面缩短和版本号。已实际查看前后截图及新素材页、手机新增面板、离线A4。
- 文档门禁检查167份0问题；发布前v2.11.4、407题、三服务active/running，切换前重新读取活动任务与快照。功能提交后以Git精确归档发布，1726个源码文件逐字节校验；稳定别名指向`/root/workspace/apps/releases/omrs-68fdbe7`。发布证据目录`/root/workspace/apps/releases/OMRS-reminders-v2120-0rnkn0bl`为0700，不入Git。

### 生产切换与原数据核验

首次切换触发保护回退：本次发布包含此前未上线的b056e4a，启动给`drafts.db/blocks`新增可空列`svg_data BLOB`、`svg_hash TEXT`，发布保护脚本的完全相同列断言因此失败。回退保留最新数据；旧源码为723acc1e9b1dfa54251a8ed1d96b5497737160e7。逐列核实唯一变化为这两列、切换时新列均为NULL，259条既有blocks的所有原字段哈希完全一致，其它业务表也完全一致。

只修正仓库外发布保护脚本，明确允许上述两列，同时按全部原列和原行严格比较。首次备份与失败证据保留在`attempt-1/`，未覆盖或恢复旧业务数据。再次切换及检查耗时5.664秒，状态为deployed；Vault／维护目录／网关1533文件、10库和框选2文件、1库通过备份与SQLite完整性检查，57张业务表原数据及1332个正文／图片／SVG／配置文件保持一致。验收时407题、0冲突。

三服务均active/running、NRestarts0，真实cwd分别为新归档根、`services/zuoyebang`及`services/boxdetect`，上线后优先级err日志0。unit、Nginx和既有依赖未修改。原数据核验是切换时快照，不对用户随后正常业务写入要求新列保持NULL。状态、备份与比较证据见私有目录的`release-state.json`、`release.py`和`original-block-columns.json`。

### 上线后补齐的精确归档门禁

下列10组均从实际生产归档运行且退出码0，测试实例使用临时Vault和随机端口，清除`OMRS_SYSTEMD_SERVICE`与`OMRS_BOXDETECT_CONTROL`：

- 后端：`python -B -m unittest`执行素材、横幅、导出、写锁、MCP、权限、运行记录、错因及资源缓存相关22个测试模块，209项通过；准确模块清单见`gates.json`。
- 前端：`node --test tests/app/*.test.mjs`601项，`python -B tests/app/run_browser.py`35项全部通过。
- 业务浏览器：`python -B tests/e2e/schedule.py`54项、`schedule_export.py`22项、`schedule_reminders.py`30项全部通过。
- 打印：`python -B -m unittest tests.smoke_a4_print tests.smoke_board_print -q`15项通过。
- 静态与文档：`python -B tests/check_ui.py`全仓0问题，`check_contrast.py`58组通过，`check_docs.py --diff b056e4a`167份0问题，3条已有体积提醒。

命令、计数及输出见私有目录的`gates.json`、`archive-*.log`和`post-release-validation.log`。AI仅替换网络模型边界，真实兼容客户端连接合成本地HTTP模型；业务HTTP、素材保存／默认／删除、快照、画廊下载和打印均实际运行。收尾更新生产事实与同一任务日志，执行`python3 tests/check_docs.py --write-log-index`生成索引（内容未变）；文档`--diff HEAD`与`--diff b056e4a`均167份0问题、3条已有体积提醒。

### 生产只读页面与公网验收

使用已校验归档HTML、真实生产静态资源与业务GET，拦截所有业务写请求，浏览器实际检查浅深主题×1440／1024／390／320px共8档。素材页、单一导出入口、默认关闭的缺错因开关、嵌套画廊、取消、版本、重复ID与溢出均通过，脚本错误0、业务写请求0、横向溢出0；14份静态资源哈希、immutable缓存和ETag304通过。该验收没有实际PIN登录，不能视为真实登录流程验证。

公网8项均符合预期：入口与网关health200，未登录业务状态、提醒列表／新增／生成、MCP及检测查询401。证据为`live-check.json`、`live-browser.json`、`production-*.png`、`public-http.json`与空的`production-errors.jsonl`。生产已切换完成，所有补充回归已完成，无待执行发布步骤。

## 未执行验证

未做付费真实模型、实体手机／打印机、Windows实机、无关全仓Python测试或主动生产故障演练。AI网络使用真实兼容客户端与合成HTTP响应，打印使用Chromium离线HTML/PDF；生产浏览器没有实际PIN登录，功能写路径已在隔离实例验证。首次自动保护回退为发布中真实发生，不计作主动故障演练。无已知阻断交付的问题，无待执行功能或生产切换；后续只需正常使用。
