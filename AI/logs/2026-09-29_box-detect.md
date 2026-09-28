# 2026-09-29 本地框选训练与训练面板

## 背景

执行者：Codex，完整模式。用户要求按 box-detect 计划从阶段 0 到 C7，顺序 C1 → C5 → C6 → C2 → C3 → C4 → C7，仅在 §10 停止条件处停下，并避免 OOM。隔离工作树 `codex/box-detect`，开工 fetch origin/main 后以本地 main `2bb401c` 为基线；本地 main 领先远端，无远端新提交。原工作区既有改动保留，用户明确授权本任务一并提交现有 `AI/training/`。原计划复制到工作树保留；未纳入 ai-draft 的未提交改动。

## 阶段 0 与 C1 行为变化

新增只读数据构建：严格校验人工框、图片哈希／尺寸／解码，dHash 分组，固定测试集，OMRS 同款条带与残框过滤。快照、图片、标签均在仓库外。冻结图或标签变化拒绝重建，新增近似测试图隔离。实际有效数据仅 62 张；65 张候选 JPEG 截断，另缺类 4、未编辑 AI 框 1，按计划排除。详细统计见 `AI/training/records/2026-09-29_dataset.md`。

环境：Python 3.13.5，CPU torch 2.14.0+cpu；精确依赖在 requirements。开工可用内存约 9.6 GiB、swap 已用 9.5 GiB，装依赖后可用内存约 18 GiB。未启动训练，未改 systemd／生产配置。生产只读首页检查 HTTP 200。

## 影响文件

新增 `tools/boxdetect/` 数据工具与依赖、`tests/test_boxdetect.py`、训练记录目录、原 box-detect 执行计划；更新训练入口、AGENTS 映射、AI 入口、环境文档、计划进度和本日志。提交前用 `git diff --name-status` 与 untracked 清单复核。

## 验证

基线已实际执行：Python unittest 226 通过，Node 339 通过。新增数据单测 7 通过（裁框、残框、分组传递、切分复现、冻结隔离、缺失冻结图、只读筛选）。构建输出 39/8/15 张、47/11/20 条带，真实 `.omrs` 前后文件 mtime_ns 与大小无变化。

未执行：训练、模型评估、服务、页面与端到端，属于后续 C2–C7。C1 提交门禁已实际执行：Python 233 通过、Node 339 通过、文档 0 问题（2 条既有体积提醒）。提交前再次同步 main，仍为 2bb401c。
