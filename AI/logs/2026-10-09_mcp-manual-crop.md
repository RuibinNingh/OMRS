# 2026-10-09 MCP 草稿人工裁框保存修复

## 背景

用户原话：「什么情况,我自己框的不能用?」；截图显示审核中心保存正文失败：「第 2 块 original 框必须是无 AI 框的全幅」。本轮为独立缺陷修复，执行者 Codex，完整模式；基线 `b7a3f98`，开工 `git status --short` 为空。生产进程使用独立 release，本轮只修改开发工作区，验证使用临时 Vault 与随机高端口并移除生产控制环境变量。

实测：MCP 图片初始为 `original` 全幅框，共享画布在人工缩放结束后只转换 AI 来源，没有转换原图来源。正文局部坐标仍携带 `original`，被既有后端全幅校验拒绝。新增浏览器场景在修复前经真实拖动复现 HTTP 400 与截图同类错误。

## 行为变化

MCP 全幅正文框经人工缩放为局部范围后改为 `manual`，暂存、刷新和入库使用人工范围；仅选中全幅框不产生修改并保持 `original`。来源图片字节和关联保持，人工正文编辑不隐式建立训练任务。后端原图全幅校验及 AI 原框、人工调整来源规则保持。

## 影响文件

- `assets/app/features/ai-review/drafts-canvas.js`：在草稿画布手势完成、同步正文前转换局部原图框来源。
- `tests/e2e/drafts.py`：增加 MCP 合成图的真实选择、缩放、移动、暂存重读、裁图入库、附件尺寸与原件保留回归。
- `AI/frontend/ai-review.md`、`AI/drafts.md`、`AI/frontend/architecture.md`、根 `README.md`：同步人工裁框行为与验证入口，并纠正草稿文档遗漏 `original` 合法值的事实错误。
- 本任务日志及脚本生成的 `AI/logs/log.md`：记录修复与实际验收。

## 验证

已实际执行：

- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 -m unittest tests.test_mcp_draft_atomic tests.test_draft_write tests.test_draft_p3_http tests.test_draft_training -q`：48 项通过，无跳过。
- `node --test tests/app/*.test.mjs`：455 项通过，无跳过。
- `python3 tests/app/run_browser.py`：34 项通过。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/e2e/drafts.py`：正式重跑 82/82 通过，新增 MCP 人工裁图 7 项，既有审核、手动画框、触摸与四档审计全部通过。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/e2e/drafts_p4.py`：24/24 通过，覆盖既有 AI 框人工调整与独立训练任务。
- 仓库外 `/tmp/omrs-mcp-crop-check.py` 复用正式新增场景并自建隔离服务：修复前复现 `original` 校验 HTTP 400；修复后 7/7 通过，包含浏览器裁图正式入库及附件尺寸核对。
- `python3 tests/check_ui.py`：0 问题；`python3 tests/check_contrast.py`：58 组全部通过。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/visual/run.py --ref b7a3f98 --pages ai-review --out /tmp/omrs-mcp-crop-visual`：浅/深色、桌面/手机共 4 对截图，0 差异、0 页面脚本错误。修复仅改变手势完成后的来源标记，静态页面无变化；交互范围另由新增裁框场景验证。
- `git diff --name-status` 已复核实际变化；`git diff --check` 通过。
- `python3 tests/check_docs.py --write-log-index` 生成索引；`python3 tests/check_docs.py --diff HEAD`：105 份文档，0 问题，2 条既有计划文件超 40KB 提醒。

首次回归编写时发现两个测试前提不成立：单纯选中不产生脏状态，不能要求点击禁用的暂存按钮；全幅角柄中心位于 SVG 裁切边界，须从可见内侧实际命中。修正测试后成功复现业务报错。修复后首次重读验证错误等待了已收起的正文；按实际保存的来源模式调整等待条件。失败证据保留于 `/tmp/omrs-mcp-crop-before.log`、`/tmp/omrs-mcp-crop-repro.log`、`/tmp/omrs-mcp-crop-drafts-first.log`；最终正式脚本结果在 `/tmp/omrs-mcp-crop-drafts.log`，不将测试等待失败当作产品缺陷。

未执行：生产部署、生产业务写入、远端推送、真实模型识别、全仓 Python 门禁。本轮只修复人工画布状态，专项后端与真实浏览器覆盖相关路径。

## 遗留与下一步

修复尚未部署到生产，用户当前页面仍使用已发布版本。生产切换需单独授权；本轮不修改真实草稿或运行中的服务。
