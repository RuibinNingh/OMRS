# 2026-11-22 开放 AI 正式题目位图编辑

> **任务**
> - 标识：ai-formal-question-image-edits
> - 状态：进行中

## 背景

用户原话：「当前OMRS AI不能修改题目的图片,存在这个问题吗」「开放一些,允许AI进行修改」「可以做到吗」「部署生产,提交GitHub」。执行者 Codex，完整模式。功能改动先在旧工作区按 55afe35 开发；发布前 GitHub `main` 已推进到 v2.12.3 提交 `f99ab2c`，本次将功能补丁迁入基于该提交的隔离 worktree，生产主站当时运行 v2.12.3。旧工作区已有的其它未提交内容保持不变。

## 行为变化

内置助手可使用当前对话上传图替换已有题目或答案中的 PNG/JPEG/GIF，也可裁剪静态图或移除图片引用；MCP 可在正式改题提案里提交相同操作。审核详情显示新旧预览，批准后更新正文引用并保留旧附件，沿用既有权限、审批、Ledger 历史和按运行撤销。该功能处理图片引用及裁剪，不包含已有图片的生成式重绘；需要生成替换图时先上传到助手对话。

## 影响文件

- `omrs/`：新增 `question_image_edits.py`，扩展图片安全发布、正式题目修改、journal、助手与 MCP 提案。
- `assets/app/`：助手工具说明及审核详情展示位图修改预览。
- `tests/`：覆盖安全校验、图片提案与审核执行的 Python 和 Chromium 回归。
- `README.md`、`AI/`：同步工具范围、权限、存储、历史、审核页面及版本 v2.13.0。

## 已执行验证

- 首轮基于旧工作区提交 `55afe35`：MCP 测试 150 项、助手测试 92 项、题目测试 76 项通过；`tests/e2e/assistant_review.py` 为 34/34，`tests/e2e/ai_review.py` 为 48/48。
- 在最新 `f99ab2c` 基线复跑：MCP 150、助手 92、题目 76、统一审核 29 项通过；Node 606 项通过且无跳过；组件浏览器 35 项通过；UI 0 问题、对比度 58 组均达标。
- `tests/e2e/assistant_review.py` 34/34，实际上传替换图、核对审核预览、批准后检查新附件与旧图保留；`tests/e2e/ai_review.py` 48/48。两者均使用临时 Vault、随机端口和真实 Chromium，脚本错误为 0。
- `tests/visual/run.py --ref f99ab2c --pages assistant,ai-review`：8 档脚本错误 0；手机 4 档无差异，桌面 4 档差异各 0.004%，仅侧栏版本号变化，报告在 `/tmp/omrs-question-image-release-visual/report.html`。
- `python3 tests/check_docs.py --write-log-index` 后以 `--diff f99ab2c` 检查 173 份文档，0 问题、0 提醒；`git diff --check` 通过。

## 未执行验证

尚未在精确发布归档上复跑发布门禁，也未推送 GitHub 或部署生产；尚待重新执行生产任务／恢复意图预检、保全、切换与上线后验收。未调用真实付费模型，也未验证客户端自动选择该工具参数；像素生成式重绘不属于本次实现范围。

## 发布与 GitHub

目标版本 v2.13.0。发布前需在当前隔离 worktree 复验相关测试和 `python3 tests/check_docs.py --diff f99ab2c`，更新本任务日志与 `AI/environment.md`；提交代码并推送 GitHub `main`，从推送提交创建精确发布归档。生产切换前重新核对运行任务、恢复意图、训练锁并保全 Vault；上线后核对主站真实目录、版本、资源、就绪与数据完整性。生产结果、提交号、门禁及保全路径在完成后补记。
