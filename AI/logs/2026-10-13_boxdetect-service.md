# 2026-10-13 框选检测服务源码迁移

## 背景

用户原话：“执行”。执行者 Codex · 完整模式，按 `AI/plans/boxdetect-service/plan.md` 连续执行源码阶段 0–2。执行基线 `09fb0bc9e85409df4e43dd75c98e19f731ab702f`，版本保持 v2.6.0。规划交付日志保持原事实，本日志独立记录实施。

工作区已有本任务规划文档和并行作业帮改动。作业帮源码／页面、相关测试及模块文档全部保留；共享 README／文档只提交本任务 hunk。未继承旧任务的生产或推送授权。

## 行为变化

### 阶段 1：独立服务及兼容层

新增同仓 services/boxdetect，提供独立 boxdetect_service 的 serve／probe 模块入口、固定三项推理依赖和可安装包。HTTP、推理算法及原模型校验保持；服务不再导入 omrs 或 tools。旧 serve.py、inference.py、probe.py 委托同一实现，训练工具仍位于原目录。生产服务入口、模型、端口和控制状态未改变。

独立几何函数与现有收件箱 IoU 在空／退化框及固定随机样例上等价。真实模型冒烟只操作临时模型副本和随机端口；在线模型与训练 current 分别冻结，不重训或改指针。

## 影响文件

阶段 1：新增 services/boxdetect 项目、独立服务协议／独立性／安装包测试，tests/test_boxdetect_service.py 和真实新旧对照脚本 tests/boxdetect_compare.py；旧三个入口及服务依赖清单改为兼容委托。同步训练、环境、根 README、AI 索引、AGENTS 映射、progress 与日志索引。本轮只按所属路径／hunk 提交，不包含并行作业帮变更。

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
