# 2026-10-21 审核中心题目与答案自适应双栏

> **任务**
> - 标识：ai-review-columns
> - 状态：已交付

## 背景

用户原话：「审核中心建议改一下」「如果空间足够」「采取双栏布局(题目与答案)」。已确认共用滚动、保留原图并按正文实际空间自适应，补充布局草图后要求实施计划。执行者Codex，完整模式；计划AI/plans/ai-review-columns/plan.md；基线e0ef9ed2084066d98391d8aba7d900fa67ed5b0c。

开工已有AI/plans/omrs-maintenance/validation.json未提交修改，SHA-256为3d3cdbd203731931981a4db6d940cae48878e1069d55c1c2008c361aa58be9f9；保留且不纳入本任务提交。

验证期间工作区新增另一项MCP答案内容边界改动，包含工具说明、模块文档、计划和日志；按路径及README、自动日志索引的具体差异区分，保留且不纳入本任务提交。

该MCP任务随后独立提交为32f3086；提交前重新核对HEAD与差异，本任务仅纳入双栏实现、测试及对应文档，原维护验证记录仍保留在工作区。

## 行为变化

正文实际宽度达到1000px时题目与答案等宽并排、顶部对齐，题目信息仍在上方；窄正文恢复上下排列。两栏共用详情滚动和底部操作，保留来源图，长公式局部滚动，图片限制在栏宽内。

## 影响文件

按git diff --name-status结合未跟踪文件核对，本任务范围如下；README和自动日志索引仅纳入本任务的具体差异。

- assets/app/features/ai-review/drafts.css：具名正文容器、1000px题答双栏、块操作下置、长公式滚动与图片宽度。
- tests/e2e/ai_review_entry.py：真实边界布局、缩放保留编辑、长解析、来源与只读、窄抽屉回归；tests/visual/run.py：增加--draft-sources none，让基线和当前树共用纯文字草稿进行双栏对比，默认带图行为保留。
- AI/frontend/ai-review.md、AI/frontend/architecture.md、AI/environment.md、README.md：更新当前行为、回归覆盖及视觉夹具用法；环境文档保持40926字节，低于40KiB。
- AI/plans/ai-review-columns/plan.md、progress.md与AI/plans/README.md：入库已确认计划、验收和完成进度。
- 本任务日志及AI/logs/log.md：记录真实验证和自动生成索引，不纳入其他任务的改动。

## 已执行验证

已复核Git状态、基线、草稿DOM和样式、隔离测试启动配置。规划阶段24项既有回归和11项草图检查不充当实现后的验证。所有本轮服务使用临时Vault和随机端口，清除OMRS_SYSTEMD_SERVICE与OMRS_BOXDETECT_CONTROL。

- `node --test tests/app/*.test.mjs`：561项通过，无失败或跳过。
- `python3 tests/app/run_browser.py`：35项通过，0失败。
- `python3 tests/check_ui.py`：全仓计数为0、0处问题；`python3 tests/check_contrast.py`：58组全部达标。
- `python3 tests/e2e/ai_review_entry.py`：最终46/46，截图与checks.json位于/tmp/omrs-review-entry-ii_o70ju。首轮在抽屉入场动画期间比较两次几何值，抽屉断言失败；改为同一帧读取两栏并等待实际动画结束，重跑通过。首轮证据保留在/tmp/omrs-review-entry-n52n7p6r。
- `python3 tests/e2e/ai_review_refresh.py`：56/56，覆盖浅深色桌面与手机的慢读取、失败重试、新版本和脏输入保护。
- `python3 tests/e2e/ai_review.py`：48/48；`python3 tests/e2e/assistant_review.py`：28/28；`python3 tests/e2e/drafts.py`：82/82；`python3 tests/e2e/drafts_blocks.py`：59/59；`python3 tests/e2e/drafts_p4.py`：24/24。连同审核录入和刷新共7组343项全部通过。完整命令与原始日志位于/tmp/omrs-review-columns-20261021-26xb5f3g/results.json及对应日志。
- `python3 tests/visual/run.py --ref e0ef9ed2084066d98391d8aba7d900fa67ed5b0c --pages ai-review --review-kind draft --draft-sources none --out /tmp/omrs-review-columns-20261021-26xb5f3g/visual-none`及同参数的--draft-sources image：两组均退出0，共8组前后对比。report.html和audit.json保留在各自目录，已实际查看无图桌面基线与当前截图。

| 夹具 | 主题 | 视口 | 像素差异 | 解释 |
|---|---|---|---|---|
| 无来源图 | 浅色 | 桌面1440 | 2.013% | 题答从上下改为等宽并排，块操作下置并增加中间细线，题目信息和统一底栏保持 |
| 无来源图 | 深色 | 桌面1440 | 2.043% | 同一双栏变化在深色token下的像素差异 |
| 无来源图 | 浅色 | 手机390 | 0% | 正文未达到1000px，保持上下排列 |
| 无来源图 | 深色 | 手机390 | 0% | 正文未达到1000px，保持上下排列 |
| 有来源图 | 浅色 | 桌面1440 | 0% | 扣除原图区后正文不足1000px，保留原有核对布局 |
| 有来源图 | 深色 | 桌面1440 | 0% | 扣除原图区后正文不足1000px，保留原有核对布局 |
| 有来源图 | 浅色 | 手机390 | 0% | 题答和原图继续上下排列 |
| 有来源图 | 深色 | 手机390 | 0% | 题答和原图继续上下排列 |

8组当前审计均无页面横溢、可见内容横溢、过小目标、行内样式或脚本错误；超宽有图双栏、长公式滚动及窄抽屉由审核录入46项另行覆盖。

`python3 tests/check_docs.py --write-log-index`已生成日志索引；另行执行`python3 tests/check_docs.py --diff e0ef9ed2084066d98391d8aba7d900fa67ed5b0c`，检查155个文档、0处问题、3条已有篇幅提醒，退出码0。`git diff --check`通过，原维护验证记录的SHA-256与开工一致。

## 未执行验证

未执行生产、实体手机及全仓后端验证：本次变更集中于草稿CSS和测试工具，已完成计划要求的隔离浏览器及前端门禁。未请求版本升级、推送或部署；版本保持v2.8.4。本任务无已知遗留问题，后续发布按现有流程单独处理。
