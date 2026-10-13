# 框选检测服务迁移到 services

执行者：Codex · 完整模式；生产切换由获得单独授权的 Codex 或 Hermes Agent · 完整模式执行。本文件是一次完整源码迁移的执行说明，不另拆执行批次。当前用户只要求制定方案，尚未授权实现、生产变更或远端推送。

## 1. 任务目标

将常驻 ONNX 框选检测服务整理为同仓 `services/boxdetect/` 独立项目，解除其对 OMRS 业务模块和训练工具的运行依赖，保持现有检测结果、训练流程与面板管理契约。

必须同时满足：旧工具入口可继续使用；主程序不加载推理或训练框架；模型与数据继续存于仓库外；源码导出包含全部必要服务代码和兼容入口；生产切换有独立授权边界、验收与回退步骤。

用户原话及归类：

| 原话 | 归类与本方案采用的理解 |
|---|---|
| “OMRS的AI训练服务是不是也应该放services?检查一下” | 明确要求检查；放进 services 是当时提出的可能方式。本方案依据源码及独立进程现状，选定同仓 services/boxdetect 路线。 |
| “制定迁移方案” | 明确要求本轮制定可执行方案；不表示本轮实施或操作生产。 |

隐含前提：迁移服务源码不等于重训、换模型或搬运私人数据。训练面板继续由 OMRS 提供；常驻进程承担框选推理，训练和付费内容评测仍由维护者 CLI 启动。依据为现有代码、`AI/training/README.md` 与 `AGENTS.md`。

## 2. 当前背景与约束

### 2.1 规范来源

先读 `AGENTS.md`「完整模式」「按执行说明执行」「每次任务的强制文档收尾」，以及 `AI/README.md`「按任务找文档」、`AI/plans/README.md`。领域契约读 `AI/training/README.md`、`tools/boxdetect/README.md`、`AI/api/extensions.md`「训练面板」「受管检测服务」、`AI/data/storage.md` §8、`AI/frontend/trainpanel.md`、`AI/environment.md` 的本机检测服务与安装验证章节。旧训练计划只作历史背景，不继承其生产授权。

### 2.2 实测事实（2026-10-13）

基线为 `09fb0bc9e85409df4e43dd75c98e19f731ab702f`，版本 v2.6.0，调查开始时 Git 工作区干净。执行前必须复核，不能将本表当作永久生产配置。

| 实测事实 | 来源及迁移影响 |
|---|---|
| `serve.py`、`inference.py`、`probe.py` 位于 tools/boxdetect；服务入口通过 sys.path 定位整个仓库。 | 读取三个脚本；仅将当前服务及其公共模块复制到临时目录执行 --help，退出 1，错误为缺少 omrs。当前服务不能作为独立项目运行。 |
| 推理模块引用 omrs.inbox.iou；预检引用 omrs.traincontrol.model_info。 | `tools/boxdetect/inference.py`、`probe.py`。拆分时解除这两条反向业务依赖。 |
| 主控制器从训练脚本取得内存检查，并固定调用 tools/boxdetect/probe.py；面板生成旧 serve.py 命令。 | `omrs/traincontrol.py`、`omrs/trainpanel.py`。调用路径与内存检查需要同步整理。 |
| 检测服务独立运行，当前 active/running，回环端口 18766；实际进程目录为 /root/workspace/releases/omrs-6437525。 | systemctl show 及 /proc 的 cwd、cmdline；读取核对的四个服务相关脚本与当前仓库字节一致。 |
| 实际在线模型为 v2-20260929-b，640、conf=0.1、SHA-256=f62581b7c28353d5d7799973018a6986e706cd7dcf4fb43ccd10972be4a4c7c3。 | 只读 GET /health，与 managed/active/model.json 一致。迁移验收比较切换当时的身份，不写死本次调查值。 |
| 训练 models/current 是另一模型：20260929-yolov8n-640，conf=0.55、SHA 前缀 894cb458。 | 只读模型元数据；生产切换必须沿用 managed/active，不能使用 CLI 默认的 models/current。 |
| Python 3.13.5；推理依赖 onnxruntime 1.30.0、numpy 2.5.2、Pillow 12.3.0。 | 实际服务解释器的包元数据，与 requirements-serve.txt 一致；本次不升级依赖。 |
| 源码导出只允许 services/zuoyebang，tools/boxdetect 当前导出文件数为 0。 | `omrs/source_export.py` 与 _source_files 实测；新项目、必要安装文件及离线入口都须纳入精确白名单。 |
| 八组相关 unittest 共 70 项通过。 | 完整命令见 §9；不代表新服务、浏览器或生产迁移已验证。 |

资源限制实测为 Restart=on-failure、3 秒重启、CPUQuota=200%、MemoryHigh=512MiB、MemoryMax=1GiB、Nice=10。ONNX Runtime 内部线程为 3/1。数据、训练环境及受管指针均在 `/root/omrs-train/`，本次不搬目录、不重建历史。

### 2.3 硬约束

本轮方案只改文档。未来源码执行也不得自动改 systemd、Nginx、真实 Vault、生产控制登记或 Git 远端。测试使用临时 Vault、随机高端口，并同时移除 `OMRS_SYSTEMD_SERVICE` 与 `OMRS_BOXDETECT_CONTROL`；真实模型只能取只读快照用于隔离实例。付费评测与新训练不在范围内。

## 3. 最终预期行为

| 位置 | 迁移完成后的职责 |
|---|---|
| services/boxdetect/ | 独立包 boxdetect_service、HTTP 服务、ONNX 推理及预检、最小依赖、安装说明、独立测试。可从该目录启动，也可构建安装包在仓库外运行。 |
| tools/boxdetect/ | 数据构建、训练、评测、导出／发布、困难采样和控制登记工具；serve.py、inference.py、probe.py 留作兼容入口。 |
| omrs/ | 训练面板、配置、标注积累、候选与受管操作、审核、权限、幂等、恢复与原子模型指针。 |
| 仓库外训练目录 | datasets、runs、models、managed、audits 及锁、历史；位置和持久化格式保持。 |

新标准入口为在 `services/boxdetect/` 执行 `python -m boxdetect_service serve --model-dir <目录> --port <端口>` 与 `python -m boxdetect_service probe --model-dir <目录>`。旧三个工具路径保留兼容；旧 serve CLI 的参数、默认模型目录和默认端口继续有效。训练与评测命令保持原路径。

检测仍只监听 127.0.0.1，以原 `GET /health` 和 `POST /detect` 协议服务 OMRS。health 身份字段及 boxes/label/bbox_2d/confidence 返回保持；预处理、坐标恢复、按类 NMS、置信度、结果排序及 CPU 推理参数保持。模型仍启动时加载一次。长图切片和合并留在 OMRS，离线评估继续使用既有整图口径。

`/train` 的查看、实时测试、可选 todo 积累、启停／重启、显式应用／回退与并发恢复行为保持。新命令可复制运行；本地受管模式仍优先显示固定 unit 的启动命令。独立包不能读取 Vault、写受管指针、调用训练或导入 omrs/tools；训练工具可以复用服务包的推理实现。

## 4. 实施计划

### 阶段 0：复核与冻结

先读本计划 progress 与 Git 状态，复核 §2 的源码、运行目录、模型身份和可用材料。运行 §9 的相关基线；记录当前检测协议、推理参数、旧导入接口及输出。只读取得固定模型和冻结数据快照，后续对照使用相同 SHA、conf、imgsz 与图片字节。阶段 0 不产生生产变更，也不以检查点为终点。

### 阶段 1：独立服务及兼容入口（提交一）

新增 `services/boxdetect/` 项目和 `boxdetect_service` 包，迁入服务与推理、预检所需的纯函数。解除 inference 对 inbox 以及 probe 对 traincontrol 的依赖；保持已有校验和计算规则。新包提供 serve/probe CLI、最小依赖与可构建安装包。现有工具导入和脚本转为薄兼容层，不保留两份推理实现。

以仅有新服务项目的临时副本及最小推理环境证明独立性：清除仓库 PYTHONPATH、从副本外运行安装后的包，实际加载固定模型，完成 health 和合成图 POST。新旧入口在同模型同图片下比较 health 与完整预测。提交包含独立服务、兼容层、有效的边界／协议测试、模块文档、任务日志和 progress；现有面板与旧控制路径仍须正常。

### 阶段 2：OMRS 接入及交付闭环（提交二）

将控制器的限额预检改为新服务 CLI，并以服务子目录作为明确工作目录；在 systemd-run 使用相应 WorkingDirectory，不依赖调用者 cwd。将既有内存检查提取到标准库模块 `omrs/system_resources.py`，由控制器与训练脚本复用，消除主程序 import tools.boxdetect.train。继续使用登记解释器、固定 unit、原限额和参数数组。

面板的未受管启动提示改为可直接复制的新入口及明确 cwd；保留原本机端口、远程地址提示和受管 unit 提示。更新真实模型 E2E 的服务启动路径，保留旧入口的专项兼容验收。补 `deploy/boxdetect.service`，使用与 OMRS 同一发布归档内的服务 cwd，显式指定 managed/active 和生产端口；根依赖不增加 ONNX 或训练框架。

源码导出仅增加 `services/boxdetect/` 与 `tools/boxdetect/` 的公开源码和必要安装／提示文件白名单，不能开放任意 services 或 tools。合成私人目录、权重、数据集、控制状态与符号链接应继续被排除。检查 pack_for_ai.bat 已能收集新源码；仅在确有遗漏或新运行目录排除需求时改它。补脱敏包解压后的服务启动及工具导入验收。

提交包含接入、导出、部署模板、测试、当前行为文档、日志及 progress；统一运行 §9 的最终门禁。源码阶段到此完成，连续执行，不在提交一后询问是否继续。版本保持执行开始时的版本；生产版本变更随另行授权的发布任务决定。

### 阶段 3：生产切换（需后续单独授权）

源码阶段先产出可审阅的 unit 差异、精确 Git 发布归档、实际验证结果和本节回退步骤。当前“制定迁移方案”及以后单纯“执行源码迁移”均不自动授权本阶段；未获授权时在 progress 登记待生产切换，交付已完成的源码。

获得覆盖发布、unit 更新和服务重启的生产授权后：

1. 复核无活动训练、未终结服务操作及未完成恢复，确认旧源码和解释器可回退；记录真实在线身份、指针目标、原服务状态、unit/drop-in、登记与主服务发布指针。保全控制文件，记录哈希，不在日志输出私有内容。
2. 使用验收提交的精确发布归档，服务源码与 OMRS 共用该归档。用现有检测解释器在隔离端口加载模型快照预检；保留依赖版本及既有解释器，禁止在生产训练环境中升级包。
3. 将检测 unit 的 WorkingDirectory 指向该归档的 services/boxdetect，ExecStart 改为登记解释器执行新 serve CLI；模型参数继续是原 managed/active，端口及全部资源限制保持。按当前发布机制切换主服务源码，再按需 daemon-reload 与重启相关服务；作业帮和 Nginx 无本任务配置变更。
4. 核验实际 cwd／cmdline、服务状态、health 的 SHA／conf／imgsz／classes／name 与切换前一致，且主服务只读 manager 与 /train 能正常展示。记录恢复后的控制状态；迁移不调用 activate、rollback 或 bootstrap，不改业务数据。原本停止的检测服务保持停止，模型加载验收在隔离进程完成。
5. 健康不一致、启动或控制恢复失败时，恢复本次改变的 unit/drop-in 与源码指针，重新加载并恢复原服务状态，核验原 health。保留最新 Vault、managed 历史、revision 与锁状态，不能以旧目录或旧备份覆盖新业务事实。失败原因及回退验收写入单独发布任务日志。

Git 推送仍须本会话后续明确授权；不继承旧训练或作业帮任务的推送授权。

## 5. 关键技术决策

- **组织与依赖方向：** 采用同仓独立包 boxdetect_service，与现有作业帮项目的组织方式一致。选择模块 CLI 作为标准入口；不为主应用安装该包或修改其全局 PYTHONPATH。主程序只通过 HTTP 与限额子进程使用它。
- **兼容：** 保留 serve.py、inference.py、probe.py 的现有公开接口和退出语义。兼容层仅在工具进程定位同仓服务包；后续删除兼容层须另立任务，本次不设置自动失效期限。
- **纯函数边界：** 服务拥有推理所需的几何、类别、哈希与模型读取逻辑，不引用业务模块。IoU 按现有算法做轻量实现并验证等价；不为数行纯函数引入跨项目公共包。OMRS 候选／受管状态校验留在控制器，预检的模型校验由服务实现，保持既有规则与错误语义。
- **内存检查：** 原函数移入 OMRS 标准库模块，继续检查宿主机及 cgroup 祖先额度、读取失败拒绝操作。训练脚本复用；独立服务无需导入此模块，正式限制由部署与原 ORT 参数保持。
- **依赖：** 新服务 requirements.txt 固定现有三项版本；旧 requirements-serve.txt 转为引用该清单。pyproject 声明同一依赖集合，精确安装清单是版本锁；构建工具只属于构建环境。独立包最低 Python 3.11，当前验收解释器为 3.13.5，其他版本不宣称已验收。
- **部署模式：** 同仓生产从固定发布目录的服务子目录启动模块；独立安装包是源码独立性的验收方式。当前生产解释器和配置登记 schema 保持，切换时只改变源码入口及工作目录。
- **数据和生命周期：** 不迁移模型文件、数据表、锁、revision、request_id、操作历史或 managed 指针格式；不重跑 bootstrap。models/current 只用于原有手动工具默认值，生产显式使用 managed/active。
- **接口与权限：** 不新增外部监听、服务鉴权、网页训练或远程控制能力；HTTP 限额、登录／来源校验、白名单 unit、候选确认、原子切换和失败恢复沿用现状。本次不修与迁移无关的协议或算法问题。
- **导出：** 白名单按服务与具体公开文件扩展；不扫描训练产物，不跟随符号链接。脱敏源码包继续排除 AI/logs；pack_for_ai.bat 的维护者包继续保留 AI/logs，两种包的原语义各自保持。

## 6. 边界情况

| 情况 | 必须表现 |
|---|---|
| 只复制 services/boxdetect，或安装后从仓库外启动 | 不需要 omrs、tools、真实 Vault 或根目录 sys.path；CLI、预检与实际 HTTP 可用。 |
| 根 Python 未安装 ONNX、numpy 或 torch | 主程序、面板只读及控制器导入正常；推理在登记解释器运行。依赖缺失时服务明确失败，不能误报健康。 |
| 错误 cwd、路径含空格、旧工具导入 | 标准入口明确工作目录，兼容入口基于自身路径定位；调用使用参数数组，不将路径拼为 shell 命令。 |
| 模型缺失、SHA／类别／尺寸不符、预检失败 | 按原契约失败，候选预检不改变受管指针；无自动替代模型。 |
| 无登记、无 systemd、外部检测地址或服务离线 | 保留当前说明与启动提示，不创建孤儿进程，也不将远程服务变成本机受管服务。 |
| 训练占锁、重复 request_id、revision 冲突、中断恢复 | 保持原拒绝、幂等和恢复路径；测试不操作真实 unit。 |
| 导出中存在伪装源码、私人目录或指向仓库外的符号链接 | 不纳入权重、数据、秘密或运行状态；未知服务和未知 tools 子目录仍不导出。 |
| 生产模型与训练 current 不同，切换时服务原本停止 | 保留生产原指针和原在线／离线状态，不能因默认 CLI 参数而换模型或开启服务。 |

## 7. 修改范围

- **预计涉及：** 新增 services/boxdetect 项目与 deploy/boxdetect.service；tools/boxdetect 的三个兼容入口和推理依赖清单；omrs/traincontrol.py、trainpanel.py、source_export.py、system_resources.py、训练脚本的内存检查导入；相关 Python／E2E、打包冒烟测试及文档映射。
- **明确不要修改：** 真实错题目录、训练产物、生产 unit／登记／Nginx（源码阶段）、作业帮服务、模型权重与默认提供方；不搬训练面板前端、不改页面样式和审核流程。
- **本次源码必须完成：** 独立服务、兼容入口、主程序依赖整理、命令与限额预检接入、精确导出白名单、部署模板、隔离验证、中文文档／日志／progress。计划交付本轮只包含方案及调查验证记录。
- **可以顺手处理：** 迁移涉及的错误引用、导出说明和必要测试夹具；仅修影响本计划验收的低风险问题，并记日志。
- **本次不要处理：** 重训、付费评测、模型选择、推理加速、批处理、异步 HTTP 改造、新前端控制面板、外网访问／鉴权方案、统一全部 services 框架、清理历史发布目录或兼容入口、自行升版本与远端推送。

实现时同步 `AI/training/README.md`、`tools/boxdetect/README.md`、服务 README、`AI/environment.md`、`AI/api.md` 及相关分册、`AI/data.md`／storage、`AI/frontend/trainpanel.md`、`AI/inbox.md`、根 README 和 `AI/README.md` 索引。在 AGENTS 的映射表补新服务及相关标准库资源模块归属；不复制协作规则。前端代码预计不改，页面行为仍须真实浏览器验收。

## 8. 验收标准

1. 单独复制服务目录、清除 OMRS 路径后，新 CLI 与安装包均能从项目外加载固定 ONNX，返回正确 health，并处理实际图片 HTTP 请求；加载模块列表中没有 omrs/tools/torch/ultralytics。
2. 同一模型 SHA、conf、imgsz 和同一组短／长／无目标图片，新旧服务 health 身份、预测类别／排序／数量一致，坐标与置信度使用相同运行时应一致；如底层存在已证明的浮点非确定性，最大绝对误差不超过 1e-6 并记录证据。不能只比较状态码或框数。
3. 旧 serve CLI、Detector／几何函数导入及 probe CLI 仍可用，离线数据、评估、发布与既有内存保护测试通过；服务不再反向导入 OMRS 或 tools。
4. 控制器不再导入 tools.boxdetect.train；预检工作目录和入口指向新服务。缺模型、预检失败、身份冲突、重复请求与中断恢复仍按原契约处理，登记字段和受管历史格式保持。
5. 实际浏览器走收件箱框选、/train 实时测试与积累开／关，并在测试后端走启停／应用／回退主路径。当前确认、失败恢复、两窗口冲突、离线提示与候选评分均正常；无真实 Vault 或 unit 写入。
6. 源码导出 ZIP 包含新服务、安装清单、兼容入口及所需离线公开源码；解压后不靠原工作区也能运行服务与导入工具。合成权重／图片／数据集／状态／秘密和符号链接全部排除，作业帮导出回归通过。
7. 对应单元、Node、组件、UI／对比度、专项浏览器、真实模型链路、视觉与文档门禁通过，报告实际计数；缺少真实材料必须记未完成验收，不能标为全部完成。
8. 源码交付提供新 unit 与旧配置的明确差异和回退步骤，未授权时生产状态不变。生产授权后，实际运行入口归到同一发布归档的 services/boxdetect，在线模型、端口、资源限制及原业务配置保持；失败可恢复旧入口和原服务状态。

## 9. 验证步骤

以下命令在仓库根目录执行；Python 选择已具备当前门禁依赖的解释器。所有测试移除两项生产控制环境，浏览器按 `AI/environment.md` 使用本次独立 context，不能关闭共享浏览器。模型材料只读复制到临时位置；不直接向生产检测端口发测试图片。

阶段 0 在根目录执行下面第一行，记录哈希到 progress；提交过程中保持该变量，会话恢复时从已记录的执行基线还原，不以新的 HEAD 替换。相关基线及每个源码提交的定向验证：

```bash
OMRS_BOXDETECT_MIGRATION_BASE="$(git rev-parse HEAD)"
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 -m unittest tests.test_boxdetect tests.test_boxdetect_inference tests.test_boxdetect_training tests.test_boxdetect_decision tests.test_traincontrol tests.test_trainpanel tests.test_trainaudit tests.test_source_export -q
```

每个源码提交前另执行服务级测试及文档索引／差异检查。变量赋值只在阶段 0 执行；定向测试失败不得提交。

服务级命令在阶段 1 创建对应文件后执行。工作目录为服务副本，解释器位于仅安装服务三项运行依赖的独立环境；包冒烟脚本负责构建 wheel、在源码副本外安装运行、真实模型与 HTTP 检查，不使用根仓库 PYTHONPATH。新增测试入口采用下列名称，便于执行者直接复验：

```bash
cd services/boxdetect
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python -m unittest discover -s tests -t . -q
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python tests/package_smoke.py --model-dir /root/omrs-train/managed/active
```

最终在根目录运行已有相关门禁；dataset 默认沿用现有冻结快照，若阶段 0 发现该模型／样本不兼容，先记录并选择已经冻结且完整的快照，不重建测试集凑数：

```bash
python3 tests/check_docs.py --write-log-index
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/run_gates.py --ref "$OMRS_BOXDETECT_MIGRATION_BASE" --dataset /root/omrs-train/datasets/20260929-1 --only unittest,node,components,discipline,contrast,e2e-trainpanel,e2e-traincontrol,e2e-boxdetect,docs --out /tmp/omrs-boxdetect-service-gates
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/visual/run.py --ref "$OMRS_BOXDETECT_MIGRATION_BASE" --pages trainpanel --out /tmp/omrs-boxdetect-service-visual
python3 tests/check_docs.py --diff "$OMRS_BOXDETECT_MIGRATION_BASE"
```

视觉只比较受影响的训练面板；若改变录入页命令展示，另加 create 的 train 工作区。若实际修改 assets/app，再完整执行仓库规定的 Node、组件浏览器和 UI／对比度门禁；没有前端改动也不省去面板主路径浏览器验证。根 unittest 必须覆盖新增导出与依赖边界测试；服务项目测试由前述独立命令执行。

真实模型 E2E 使用训练 models/current 验证原接入路径，与生产 managed/active 身份对照各自记录，不能混称同一模型。安装包冒烟及新旧入口对照另使用 managed/active 的只读快照，保证生产所选模型也能加载。缺少冻结数据时仍完成合成图协议与其余源码工作，最终将真实模型浏览器验收登记为待补，不能将源码迁移标为完全验收。

手工浏览器路径：录入题目 → AI 训练 → 打开训练面板，检查可复制命令；在临时 Vault 上传图实时测试，分别关闭／开启积累，校验 todo 与去重；测试控制后端上检查启停、应用确认、失败回退及恢复。生产阶段浏览器只读展示，不能用真实控制按钮验收切换其他模型。

## 10. 执行原则

先读后改，以当前代码为准；实现可以调整，目标、兼容契约和验收不能自行改。优先复用既有服务／控制抽象，不引入通用服务平台或无关重构。两个源码提交都包含对应代码、有效测试、当前行为文档、同一源码任务日志与 progress，门禁通过后提交；本轮方案任务日志与后续实现日志分别建立，不将实现补写成今天已发生。

只有下列情况停止受影响步骤：已有改动冲突且无法判断原意；事实差异改变目标、兼容契约或范围；必须改真实数据／模型或使用未授权生产与远端操作；资源保护失败或不能可靠回退。环境／测试故障、实现细节和常规路径问题自行连续解决。缺少外部材料时继续独立源码工作，最后明确未通过验收及需要的材料，不伪造通过或擅自重训。

中断后先读 git status、git log --oneline -15 与本计划 progress，核对已提交切片和验证结果，再从未完成项继续；不要覆盖用户改动、reset、clean 或整目录还原。会话结束时在状态块记录停在哪、剩余验证和下一步。

最终用中文报告：提交哈希／版本／内容；实际验证与计数；未执行验证及原因；遗留与不确定项；下一步。源码完成而生产未授权时，明确“源码迁移已完成，生产切换待单独授权”，附具体 unit 差异与回退步骤，不以旧日志的授权越界执行。
