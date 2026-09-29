# 2026-09-28 初始化框选模型训练记录

## 背景

用户要求：「那么AI文件夹里面先初始化一个用于记录训练的文件夹吧,在里面沉淀经验」。Codex · 完整模式，基线 `2bb401c`。开工时只有已有未跟踪目录 `.playwright-mcp/`，保持不动。本任务建立记录目录，不执行训练，不改变 `ai-draft` 计划范围。

## 行为变化

应用行为无变化。新增训练记录入口、数据与硬件盘点、实验模板和经验库；明确标签只含题目／答案范围，实测、建议和待验证假设分开。可视化仅登记候选方向，不将对话草图写成已实现功能。

## 影响文件

- 新增 `AI/training/README.md`、`template.md`、`lessons.md` 和 `records/2026-09-28-baseline.md`。
- 修改 `AI/README.md`，增加按任务找文档和文件索引入口。
- 新增本任务日志；通过脚本生成 `AI/logs/log.md`。

## 验证

已实际执行：本会话前序通过 SQLite `mode=ro` 查询两份数据库并核对旧原图路径，读取代码导出契约，探测当前仓库主机 CPU、内存与系统；结果保存在基线记录，未改真实数据。

- `git diff --name-status` 配合 `git ls-files --others --exclude-standard AI`：复核范围仅上述文档与日志；`git diff --check` 通过。
- `python3 tests/check_docs.py --write-log-index`：已生成索引。
- `python3 tests/check_docs.py --diff HEAD`：47 个文档、0 处问题、2 条已有体积提醒（API 文档与前端重构执行说明）。
- 当前文档脚本不会自动遍历 `AI/training/`，另通过 `runpy.run_path('tests/check_docs.py')` 加载现有 `check_file`，递归检查新增目录：4 个文档、0 处问题；未为文档初始化扩大修改检查脚本。

未执行：训练、模型评估、依赖安装、权重下载、补标和产品页面实现；本次范围仅为文档初始化。未运行业务单元测试、页面 E2E 和视觉对比，原因是未改代码、配置或页面。未提交、推送或部署。
