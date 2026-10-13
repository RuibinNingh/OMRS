# 2026-10-13 框选检测服务迁移方案

## 背景

用户原话：“OMRS的AI训练服务是不是也应该放services?检查一下”“制定迁移方案”。执行者 Codex · 完整模式，基线 `09fb0bc9e85409df4e43dd75c98e19f731ab702f`，v2.6.0，开工工作区干净。第一次只读调查未制造仓库日志；本次形成持久化方案，另建任务日志。

## 行为变化

无业务、服务或数据行为变化。本轮新增迁移方案：同仓独立服务、旧工具兼容、主程序接入、精确源码导出和隔离验收；生产发布、模型保持和回退单列授权边界。尚未实现、提交、推送、重启或部署。

方案明确服务实际承担 ONNX 框选推理，训练／评测仍留 CLI；生产保留 managed/active，不能以训练 models/current 替代。模块职责、关键决策、两个源码提交、验收、停止与恢复规则均在计划内。

## 影响文件

- 新增 `AI/plans/boxdetect-service/plan.md` 与 progress.md，作为可直接执行的迁移说明和进度。
- 更新 `AI/plans/README.md` 与 `AI/README.md` 的任务索引；据现有 progress 和存储分册，订正旧框选计划已交付服务管理的状态及训练存储章节号。
- 新增本日志；`AI/logs/log.md` 由门禁脚本生成。

收尾 git diff --name-status 还显示 services/zuoyebang/zyb_gateway 下的 __main__.py、config.py、search.py、server.py、storage.py 五个并行改动；均不是本轮修改，未覆盖、还原或整理，也不属于本方案交付。未跟踪的本计划两文件及本日志由 git status 单独复核。

## 验证

已实际执行：

```bash
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 -m unittest tests.test_boxdetect tests.test_boxdetect_inference tests.test_boxdetect_training tests.test_boxdetect_decision tests.test_traincontrol tests.test_trainpanel tests.test_trainaudit tests.test_source_export -q
```

结果 70 项通过、0 失败；运行耗时 5.691 秒。Pillow 的既有 getdata 弃用提示不影响结果，本轮不修改训练算法或数据构建。

只读 systemctl show 和 /proc 核对独立检测进程仍运行于 omrs-6437525；四个服务相关脚本与当前仓库一致。在线 GET /health 与 managed/active 元数据一致：v2-20260929-b、640、conf=0.1、SHA-256=f62581b7c28353d5d7799973018a6986e706cd7dcf4fb43ccd10972be4a4c7c3。训练 current 为另一模型及 conf=0.55，迁移方案分别约束两者。

将当前 serve／inference／common 复制到自动清理的临时目录，以隔离 Python 执行 --help，实测退出 1、缺少 omrs，确认独立性缺口。读取服务解释器包元数据确认 Python3.13.5 和三项推理版本。调用源码文件扫描器（未读取业务数据）得到 services/zuoyebang 46 个、tools/boxdetect 0 个导出文件，确认白名单缺口。

已执行 `python3 tests/check_docs.py --write-log-index` 生成索引，`python3 tests/check_docs.py --diff HEAD` 检查 117 份文档、0 问题，退出 0；两条提醒来自既有 frontend-rearch 与 v2.0.0 大计划，本轮计划为约 24KB。交付前已用 git diff --name-status 与未跟踪文件列表复核实际范围。

未执行：全仓门禁、迁移后浏览器／视觉、新包构建、旧／新推理对照、生产切换及回退。本轮仅文档方案，无实现和页面改动；对应验收留给源码执行及另行授权发布，不使用历史数字充当本轮结果。
