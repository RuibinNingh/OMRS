# 2026-10-13 框选检测服务源码迁移

## 背景

用户原话：“执行”。执行者 Codex · 完整模式，按 `AI/plans/boxdetect-service/plan.md` 连续执行源码阶段 0–2。执行基线 `09fb0bc9e85409df4e43dd75c98e19f731ab702f`，版本保持 v2.6.0。规划交付日志保持原事实，本日志独立记录实施。

工作区已有本任务规划文档和并行作业帮改动。作业帮源码／页面、相关测试及模块文档全部保留；共享 README／文档只提交本任务 hunk。未继承旧任务的生产或推送授权。

最终提交前另有并行任务修改 omrs/agent/loop.py、policy.py、store.py 与 omrs/ai_review.py，均不属于本迁移，保留在工作区且不纳入提交。发布归档只从本迁移验收提交生成，避免混入这些未提交改动。

## 行为变化

### 阶段 1：独立服务及兼容层

新增同仓 services/boxdetect，提供独立 boxdetect_service 的 serve／probe 模块入口、固定三项推理依赖和可安装包。HTTP、推理算法及原模型校验保持；服务不再导入 omrs 或 tools。旧 serve.py、inference.py、probe.py 委托同一实现，训练工具仍位于原目录。生产服务入口、模型、端口和控制状态未改变。

独立几何函数与现有收件箱 IoU 在空／退化框及固定随机样例上等价。真实模型冒烟只操作临时模型副本和随机端口；在线模型与训练 current 分别冻结，不重训或改指针。

阶段 1 提交 `00b44d8`，v2.6.0，独立服务、兼容层、测试、当前行为文档及计划／日志一起入库；未纳入并行作业帮 hunk。

### 阶段 2：接入与源码导出

控制器用登记解释器在独立服务 WorkingDirectory 启动限额 probe；原内存检查提取到 omrs/system_resources.py，训练脚本保留旧函数导入，主程序不加载 tools 或 ONNX／torch。未受管启动提示给出 cd 与新模块入口，保留本机端口和路径引用；受管／远程模式语义保持。

精确扩展源码导出：服务公开包／测试／安装文件，以及登记的平铺训练工具、依赖和提示词。未知服务／工具、生成子目录、模型／状态／秘密与符号链接仍排除。真实导出包解压后的服务、旧推理、评估与内存保护导入闭环已验证。

增加 deploy/boxdetect.service 示范同仓源码入口及原限额；生产配置不变。真实模型浏览器脚本改为新服务，并沿用当前 open_app 工作台进入方式，避免旧锁屏入口的测试准备失效；没有改变业务页面或减掉原断言。

## 影响文件

阶段 1：新增 services/boxdetect 项目、独立服务协议／独立性／安装包测试，tests/test_boxdetect_service.py 和真实新旧对照脚本 tests/boxdetect_compare.py；旧三个入口及服务依赖清单改为兼容委托。同步训练、环境、根 README、AI 索引、AGENTS 映射、progress 与日志索引。本轮只按所属路径／hunk 提交，不包含并行作业帮变更。

阶段 2：omrs/traincontrol.py、trainpanel.py、system_resources.py 与 tools/boxdetect/train.py 整理主程序依赖、限额预检和启动提示；omrs/source_export.py 及定向测试验证精确导出、私人路径与导入闭环；deploy/boxdetect.service 提供沿用原限额与隔离设置的示例。调整两份训练相关 E2E，同步受影响 API／数据／训练／前端架构／环境文档、AGENTS、根 README、计划索引及进度。无 assets、样式、模型、生产配置或业务数据改动。

## 验证

执行前重新运行计划指定的八组基线：70 项通过，0 失败。通过只读 health 核对生产仍为 v2-20260929-b、SHA=f62581b7…、640、conf=0.1；服务仍运行旧固定源码。原模型与训练 current 都只读复制到 `/tmp/omrs-boxdetect-migration-_itycugr/`，迁移前 Git 源码在同目录 before/，无真实 Vault 副本或业务写入。

阶段 1 已实际执行：

- 相关九组 unittest：72 项通过，0 失败（原八组加 tests.test_boxdetect_service）。
- 服务目录 unittest：10 项通过，包含真实 HTTP 的身份、边界／错误与复制项目独立导入，不加载真实推理框架。
- 安装包冒烟：构建 wheel，在全新最小环境安装；删除源码副本后使用 -I 从外部目录运行，真实 ONNX／预检／health／白图 POST 通过，禁止的 omrs/tools/torch/ultralytics 均不存在且未加载；七项检查通过。
- 新旧推理对照：迁移前、新服务、旧兼容入口三条路径，短图／长图／白图三组完整预测及 health 逐字段完全相同；框数为 2／0／0。只证明行为保持，不作为内容准确率验收。

最小环境初次离线缓存安装缺少锁定 numpy，因此只读复制现有推理解释器的七个依赖／构建包并重打包 wheel，在临时 wheelhouse 离线安装；所有二进制源自现有锁定安装，未修改生产解释器或升级依赖。这属于验证环境调整，迁移目标与契约保持。

执行命令和 JSON 证据位于上述临时目录：package.json、compare.json。代码中的 package_smoke.py 支持 --wheelhouse，以便无网络复验；比较脚本由执行者显式传入旧源码／解释器／快照，不访问生产端口。

阶段 1 文档索引已生成；差异门禁检查 117 份文档、0 问题，退出 0，两条既有大计划提醒；git diff --check 通过。提交哈希随下一切片记录。阶段 2 接入、导出、真实浏览器与最终门禁尚待执行；生产切换、回退与推送未执行（本轮未授权）。

阶段 2 定向九组 unittest 已执行 78 项通过，新增限额／工作目录／字面路径、内存不足不启动单元、无推理／工具依赖的主程序导入、明确启动命令和实际源码导出闭环。后续统一门禁、浏览器、视觉及发布准备在收尾补记。

### 阶段 2 最终门禁

最终实际结果：全仓 Python 973 项通过，0 失败、0 跳过；Node 496 项通过；组件浏览器 34 项通过；全仓 UI 0 问题；58 组对比度全部达标。训练面板 32／32、受管控制 32／32、真实 ONNX 浏览器 7／7 通过，无页面脚本错误。服务级测试再次通过 10 项；实际脱敏包 1207 个源码文件中包含服务 15 个、工具 17 个，解压后以最小环境运行真实 probe／health／白图 POST 均通过，health 与冻结生产身份逐字段相同。

真实模型浏览器用训练 current，三张 2376／3072／3723px 图片显示两类框；6209px 长图切为 3 条带，关闭积累时 Vault 所有文件字节不变。积累开启、去重、刷新保持、服务离线及固定 unit 启停／应用／回退由面板和受管控制门禁覆盖，不操作生产 unit。

统一门禁首次失败两项：系统 Python 缺少可选 Segno，使作业帮二维码测试失败；真实模型 E2E 切换实验后误读取仍在显示的旧图表。前者使用已有完整依赖解释器重跑全仓，未安装或升级任何生产依赖；后者先等待所选实验名称，再精确核对答案图中模型评分，断言保持。初次与复验日志分别保留，validation-final.json 汇总最后结果，九个门禁全部退出 0。

实际命令（在根目录执行，基线固定为 09fb0bc9e85409df4e43dd75c98e19f731ab702f）：

```bash
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL OMRS_TEST_CDP_URL=http://127.0.0.1:9222 python3 tests/run_gates.py --ref 09fb0bc9e85409df4e43dd75c98e19f731ab702f --dataset /root/omrs-train/datasets/20260929-1 --only unittest,node,components,discipline,contrast,e2e-trainpanel,e2e-traincontrol,e2e-boxdetect,docs --out /tmp/omrs-boxdetect-migration-_itycugr/gates
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL OMRS_TEST_CDP_URL=http://127.0.0.1:9222 /root/workspace/apps/releases/omrs-zyb-deps-20261011/.venv/bin/python tests/run_gates.py --ref 09fb0bc9e85409df4e43dd75c98e19f731ab702f --dataset /root/omrs-train/datasets/20260929-1 --only unittest --out /tmp/omrs-boxdetect-migration-_itycugr/retry-gates
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL OMRS_TEST_CDP_URL=http://127.0.0.1:9222 python3 tests/run_gates.py --ref 09fb0bc9e85409df4e43dd75c98e19f731ab702f --dataset /root/omrs-train/datasets/20260929-1 --only e2e-boxdetect,e2e-trainpanel --out /tmp/omrs-boxdetect-migration-_itycugr/retry-browser
```

### 视觉差异

按计划运行 tests/visual/run.py 比较 trainpanel 的浅／深主题与桌面／手机四组：均无脚本错误、横向溢出或尺寸变化，三组零差异；浅色桌面 0.513% 差异仅在 12 个叠加缩略图，位于 y=2586–2913，命令与服务区域零差异。加长 settle 复验仍相同，不能将等待时间当作修复。

临时诊断副本实测：基线图像 naturalWidth 均有效，当前 12 张处于 loading=lazy 且尚未加载；等待同组图像全部真实加载后，浅色桌面比较为 0%，无脚本错误。训练面板 view／store／index 与基线字节一致；不修改页面或仓库视觉脚本。报告分别在证据目录 visual/、visual-retry/、visual-loaded/。录入页 AI 训练工作区不显示本次改动的服务命令，因此无需另加该页命令视觉比较；入口已由真实浏览器覆盖。

### 发布准备与未执行项

只读复制实际 unit 后生成候选 /tmp/omrs-boxdetect-migration-_itycugr/omrs-boxdetect.service 与 production-unit.diff；systemd-analyze verify 退出 0。候选只变更 WorkingDirectory 为 /root/workspace/apps/releases/omrs-9b29d49/services/boxdetect，以及 ExecStart 为原解释器执行 -m boxdetect_service serve；保持 /root/omrs-train/managed/active、18766、Restart、原 CPU／内存／线程／TasksMax 和全部隔离设置。该发布指针须在后续授权阶段先切到源码验收提交的精确归档；当前旧归档中没有新模块，不能提前应用候选 unit。

精确 Git 发布归档以本次第二个源码提交为准，交付证据路径为 /tmp/omrs-boxdetect-migration-_itycugr/release.tar.gz，并以 release.json 记录提交及归档哈希。回退步骤采用 plan.md §4 阶段 3：恢复本次 unit／源码指针及原服务状态，核验旧 health，保留最新 Vault、managed 历史、revision 与锁，不以旧备份覆盖新业务事实。

未执行生产发布、systemd 变更／重启、生产切换后的身份验收与实际回退、Nginx 和 Git 推送：本轮只获源码阶段授权。源码阶段 0–2 已完成，无未完成源码验收。并行作业帮修改在 4413aec 独立提交，本任务继续保留；版本仍为 v2.6.0。

收尾已生成日志索引，固定执行基线与当前 HEAD 的文档差异门禁均检查 117 份、0 问题，git diff --check 通过；两个既有大计划提醒不在本任务范围。只读核验生产检测 PID 仍为 1532134、cwd 仍为旧 omrs-6437525，unit 字节与保全相同，health 与执行前完全相同。生产状态核验保存在 online-after.json。
