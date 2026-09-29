# 2026-09-28 框选模型训练计划

## 背景

用户原话：「我的错题本准备进行AI训练了,我需要你帮我制定计划,开始吧」。Claude Code · 完整模式，基线 `2bb401c`（v1.29.0）。开工时工作区已有他人未提交改动（`AI/training/`、`AI/plans/ai-draft/` 等），均未动，只在 `AI/plans/README.md` 表格追加一行。本任务只写计划，不训练、不装依赖。

## 第二轮：训练面板

用户追加：「记得还有弄一个新的AI训练面板,独立于现在的面板,入口同样是录入题目-AI训练-打开训练面板.里面展示一些可视化数据,如果可以的话展示进度啥的也不错,还有就是模型训练完应该是固定文件吧,我倒挺期待上传一个图片看看它的效果,也就是实时测试,顺便也可以积累数据*(可选择是否积累)」。同一任务续写：`plan.md` 加 T7–T12、§3.2 面板、§3.3 实时测试、C5–C7、D9–D13、验收 8–13；`progress.md` 分期表与需确认项同步。补充实测：生产 `omrs.service` 以 root 用 `/usr/bin/python3`（Pillow 12.3）运行；`/train` 与 `/api/trainpanel/*` 未占用；前端无图表库；并行的 `ai-draft` 工作树也改 `features/create/`、`server.py`、`common.py`，计划要求执行前同步 `main`。

## 行为变化

无。新增计划 `AI/plans/box-detect/`（`plan.md` 按执行说明模板写、`progress.md` 带状态块）。

## 影响文件

- 新增 `AI/plans/box-detect/plan.md`、`AI/plans/box-detect/progress.md`。
- 修改 `AI/plans/README.md`：现有计划表加一行。
- 新增本日志。

## 验证

已实际执行（真实数据全部 `sqlite3 -readonly` 或临时副本，未写 `错题/`）：

- 数据盘点：标注集 69 张 done、每张 1 题目框 + 1 答案框，宽 1080、高 2376–6752；收件箱 63 张 done、两库 sha256 无重复。
- 模板基线：临时副本上以 `omrs.inbox.template_boxes` 对 69 张标注集逐张「沿用上一张」预测，题目 平均 IoU 0.627（IoU≥0.75 23/68），答案 0.272（5/68）；默认模板题目 0/69、答案 1/69 达 0.75。
- 硬件与依赖：12 线程、31 GiB（可用 10 GiB、swap 已用 9 GiB）、无 GPU；本机无 torch／ultralytics／onnxruntime；PyPI 上有 cp313 x86_64 的 onnxruntime 1.30.0，torch 最新 2.14.0，ultralytics 8.4.164（AGPL-3.0）；yolov8n.pt 下载地址可达。
- `python3 tests/check_docs.py --write-log-index` 后 `--diff HEAD`：50 个文档、0 处问题、2 条已有体积提醒，退出码 0。

未执行：训练、依赖安装、业务单测与 E2E（未改代码）；未提交。
