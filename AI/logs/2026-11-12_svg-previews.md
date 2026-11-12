# 2026-11-12 SVG功能页面预览与助手入口修复

> **任务**
> - 标识：svg-previews
> - 状态：已交付

## 背景

用户原话：「给我一些预览图片,看看效果如何 包括大部分可能涉及此功能的页面」。Codex完整模式，基线37f7086，git status --short确认开工干净。本轮采用临时合成题库和随机高端口拍摄实际页面，不访问真实题库或生产服务。

## 行为变化

生成录入、小字拒绝、题库画廊、桌面及手机深色详情、练习翻答案前后、反馈、审核、助手改图、展示板、离线HTML与打印、修改记录共18张截图，以及A4双栏和展示板PDF、Obsidian示例题目ZIP。预览集放在仓库外 `/root/.codex/artifacts/omrs-svg-previews-2026-11-12/`。

真实聊天补拍发现只更新SVG时被工具schema的content非空限制拦截。修复后，仅追加模式且有配图允许空正文；有效补丁只保留diagrams，审批详情不重复显示未改动正文及尚未保存的新附件。分节执行回执仍返回字符串；审批前不写正文与附件。

## 影响文件

- `omrs/agent/tools/write.py`、`omrs/question_update.py`：工具schema、空正文领域校验、纯配图补丁与分节回执。
- `tests/test_question_svg.py`、`tests/test_agent_review.py`：覆盖参数入口、正文保留、无重复正文差异、审批前无写入、批准后一次提交及回执类型。
- 根README、AI/agent.md、AI/ai-review.md、AI/api.md、AI/mcp.md、AI/ledger.md、AI/question-svg.md：同步入口与审批契约。
- SVG计划progress、本次任务日志与生成的日志索引；原SVG交付日志仅追加勘误，说明原测试未覆盖助手循环入口的依据。

## 已执行验证

- 仓库外capture.py使用临时空Vault、随机高端口、真实Chromium及本机合成模型。最终18张截图、0失败、0页面脚本错误；实际PDF与Obsidian示例附件已生成，图片已人工检查。无外部模型调用。
- `PYTHONPATH=tests:. python3 -m unittest tests.test_question_svg tests.test_question_update tests.test_agent_loop tests.test_agent_tools tests.test_agent_review tests.test_agent_permissions -q`：最终88项通过，日志在预览目录backend-tests.log。包含从工具参数校验到真实聊天审批、批准后一次Ledger提交及字符串回执的回归。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/e2e/assistant_review.py`：28/28通过，日志在预览目录assistant-review-tests.log；真实隔离服务与浏览器覆盖聊天抽屉、审批、草稿编辑和不同视口主题。
- `git diff --name-status`复核实际改动；`git diff --check`、`python3 tests/check_docs.py --write-log-index`、`python3 tests/check_docs.py --diff HEAD`均退出0。文档160个、0问题、3条既有文件体积提醒。
- 前期截图脚本的选择器不唯一、测试专用全局和已建Session排除推荐造成自动化失败；修正截图流程后恢复。助手失败另由真实工具schema不一致引起，修复代码后通过。失败日志与最终产物不混为成功验证。

## 未执行验证

Obsidian桌面／手机真机、Windows与实体打印机未运行，当前环境未提供这些设备；示例ZIP供在实际Obsidian中打开。真实模型供应商、生产部署／重启和推送均未执行；本机合成模型只触发真实工具和审批流程。

本轮未改assets或页面样式，不重复全仓UI、对比度、前端单测及页面前后差异门禁；实际页面截图和聊天审批E2E覆盖本次后端入口修复。打印格式沿用已交付实现，本轮实际生成两份PDF，未重复原全量打印门禁。
