# 变更日志

这里索引已保留的任务日志；完整提交历史以 Git 为准。2026-07-24 的校准记录集中说明此前缺失的近期实现与文档漂移。

| 日期 | 类型 | 主题 | 详情 |
|---|---|---|---|
| 2026-09-22 | 完整性修复 | 展示板七项漏洞修复：保存、撤销、预览与导出快照 | [查看](2026-09-22_board-integrity-fixes.md) |
| 2026-09-22 | 功能排查 | 展示板预览、保存、导出与纸面记录的 7 项已复现缺陷 | [查看](2026-09-22_board-functional-audit.md) |
| 2026-09-21 | 前端交互 | 错题调度删除入口、确认与状态刷新 | [查看](2026-09-21_schedule-delete.md) |
| 2026-09-13 | 修复与生产部署 | v1.18.2 锁定续印修复、纸面记录恢复与验证 | [查看](2026-09-13_board-lock-incremental.md) |
| 2026-09-20 | 前端资源 | 本地界面字体与离线字体加载 | [查看](2026-09-20_local-ui-fonts.md) |
| 2026-09-20 | 前端交互 | 复习调度列表/画廊视图与 qview 题面预览 | [查看](2026-09-20_schedule-gallery.md) |
| 2026-09-20 | 前端与调度重做 | 复习调度工作台、推荐筛选与正式单题 Session | [查看](2026-09-20_schedule-workbench.md) |
| 2026-09-20 | 修复与生产校验 | 展示板打印比例快照、锁定纸面续印与 50% 数据修复 | [查看](2026-09-20_board-print-ratio-fix.md) |
| 2026-09-13 | 生产降级替换 | v1.18.1 附件包替换 v1.21.0，保留题库并核验外网监听 | [查看](2026-09-13_deploy-v1.18.1-downgrade-production.md) |
| 2026-09-13 | 架构改造续接 | 第 7–11 期页面 island 入口与生命周期收口 | [查看](2026-09-13_rearch-completion.md) |
| 2026-09-13 | 架构改造续接 | 构建欠账、第 7–11 期与相关技术债；隔离验收后上线（执行中） | [查看](2026-09-13_rearch-completion.md) |
| 2026-09-13 | 生产部署 | v1.21.0 架构改造 P6 未完成状态替换生产，已备份并保留构建前兜底 | [查看](2026-09-13_deploy-v1.21.0-rearch-P6-production.md) |
| 2026-09-13 | 架构改造 | 脱敏源码打包改为遍历文件系统，不再依赖 `git ls-files` | [查看](2026-09-13_source-export-no-git.md) |
| 2026-09-13 | 架构改造 | 架构改造第 6 期：目录页与数据复盘页迁到组件层，新增 `omrs:data` 单向镜像 | [查看](2026-09-13_rearch-P6.md) |
| 2026-09-13 | 架构改造 | 架构改造第 5 期：引入 Vite + Vue 组件层，报告页首迁为 island | [查看](2026-09-13_rearch-P5.md) |
| 2026-09-13 | 架构改造 | 架构改造第 4 期：token 层抽离、断点收敛四档、全局重名修复与扫描 | [查看](2026-09-13_rearch-P4.md) |
| 2026-09-13 | 架构改造 | 架构改造第 3 期：静态资源内容指纹、强缓存 / ETag、字体本地化 | [查看](2026-09-13_rearch-P3.md) |
| 2026-09-13 | 架构改造 | 架构改造第 2 期：PIN 鉴权、会话 Cookie、失败限流、TLS | [查看](2026-09-13_rearch-P2.md) |
| 2026-09-13 | 架构改造 | 架构改造第 1 期：线程化 HTTP 服务 + 全局写锁 + AI 识别转后台任务 | [查看](2026-09-13_rearch-P1.md) |
| 2026-09-12 | 展示板交互与调度页清理 | 统一版式与打印入口，增加版式锁定与纸面重置，题目详情入口直达，移除复习调度页 Session 反馈表 | [查看](2026-09-12_board-layout-lock-and-session-feedback-removal.md) |
| 2026-09-10 | 默认版面调整 | 错题集题栏与右侧留白默认对半 | [查看](2026-09-10_board-default-equal-columns.md) |
| 2026-09-10 | 导出调整 | 错题集移除装订预留 | [查看](2026-09-10_board-remove-binding-margin.md) |
| 2026-09-06 | [展示板：录入交互修复、打印提速与界面紧凑化](2026-09-06_board-compact-print-speed.md) | 修 4 处录入→加板交互 bug；KaTeX 只内联 woff2 + 缓存、排版趟数按需、缩图找缝，导出 2.0MB→0.95MB、就绪 0.4s→0.28s；`.bd-*` 改密度变量，行高 52px→28px；修复并扩充 smoke_board_print |
| 2026-09-06 | [ledger-records-docs-audit](2026-09-06_ledger-records-docs-audit.md) | v1.16.1：练习记录改读 Ledger、全站去原生弹窗、文档整理与写法规则 |
| 2026-09-06 | 生产部署 | v1.16.1 练习记录改读 Ledger 等部署（跳过浏览器验收） | [查看](2026-09-06_deploy-v1.16.1-production.md) |
| 2026-09-06 | 文档治理 | 全量文档事实审计与 v1.16.0 记录源勘误 | [查看](2026-09-06_document-fact-audit.md) |
| 2026-09-06 | 生产部署 | v1.16.0 题库练习记录（战绩带 + 记录模块）部署 | [查看](2026-09-06_deploy-v1.16.0-production.md) |
| 2026-09-06 | UI 改版 | 题库练习记录：战绩带 + 记录模块（v1.16.0） | [查看](2026-09-06_practice-record.md) |
| 2026-09-06 | 生产部署 | v1.15.0 UI 改版（密度层 + 首页重构 + 整屏工作台）部署 | [查看](2026-09-06_deploy-v1.15.0-production.md) |
| 2026-09-06 | UI 改版 | 密度层 + 首页重构 + 整屏工作台（v1.15.0） | [查看](2026-09-06_ui-density-home-workbench.md) |
| 2026-09-05 | 收件箱数据集 | 默认版式改为作业帮并修正现有其他记录 | [查看](2026-09-05_inbox-layout-default.md) |
| 2026-09-05 | AI 录入修复 | AI 识别题目/答案去除开头题号 | [查看](2026-09-05_ai-extract-leading-number.md) |
| 2026-09-05 | 生产部署 | v1.14.2 qb-layout 题库 UI 优化前端增量部署（画廊列数/换行模式/视图菜单） | [查看](2026-09-05_deploy-qb-ui-production.md) |
| 2026-09-05 | 生产部署 | v1.14.2 gallery-lean 题库画廊卡精简前端增量部署 | [查看](2026-09-05_deploy-gallery-lean-production.md) |
| 2026-09-05 | 文档纠偏 | 展示板打印设置契约纠正 | [查看](2026-09-05_functional-bug-fixes-2.md) |
| 2026-09-05 | 修复 | 推荐、Session、AI 标记与展示板边界修复 | [查看](2026-09-05_functional-bug-fixes.md) |
| 2026-09-05 | 生产部署 | v1.14.1 展示板打印预览弹窗修复部署 | [查看](2026-09-05_deploy-v1.14.1-production.md) |
| 2026-09-04 | 生产部署 | v1.14.0 展示板/标记/题库 rework（含仅打印新增）部署 | [查看](2026-09-04_deploy-v1.14.0-board-rework-production.md) |
| 2026-09-04 | 新功能 + 题库重设计 | 展示板、用户标记与题库交互重设计（v1.14.0） | [查看](2026-09-04_board-labels.md) |
| 2026-09-02 | 协议收紧 | OMR 剪贴板仅接受 `/result` 顶层协议 | [查看](2026-09-02_omr-result-protocol-only.md) |
| 2026-09-02 | 生产部署 | v1.11.0 升级包部署（答题卡回填 + 画廊空白修复） | [查看](2026-09-02_deploy-v1.11.0-production.md) |
| 2026-09-02 | 新功能 | 答题卡扫描 JSON 回填 + 画廊预览空白修复（v1.11.0） | [查看](2026-09-02_omr-feedback-import.md) |
| 2026-06-15 | 前端改版 | 深色主题与录入页重设计 | [查看](2026-06-15_dark-theme-and-create-redesign.md) |
| 2026-06-15 | 前端改版 | 全宽自适应布局 | [查看](2026-06-15_full-width-layout.md) |
| 2026-06-15 | 前端改版 | 即时练习页响应式重设计 | [查看](2026-06-15_instant-practice-redesign.md) |
| 2026-06-15 | 结构整理 | 前端 JS 拆分与优化文档 | [查看](2026-06-15_js-split-and-optimization-doc.md) |
| 2026-06-15 | 功能调整 | 设置优化卡与备份流程 | [查看](2026-06-15_settings-optimize-redesign.md) |
| 2026-07-03 | 新功能 | 题目截图文本提取 | [查看](2026-07-03_question-text-ocr.md) |
| 2026-07-16 | 新功能 | AI 报告提示词与可选图片材料导出 | [查看](2026-07-16_ai-report-materials.md) |
| 2026-07-24 | 文档治理 | Git 历史校准与每任务文档准则 | [查看](2026-07-24_git-history-doc-sync.md) |
| 2026-07-24 | 导出修复 | A4 公式续栏与防截断 | [查看](2026-07-24_formula-pagination.md) |
| 2026-07-28 | 前端修复 | Ledger 时间线时区显示 | [查看](2026-07-28_ledger-timezone.md) |
| 2026-07-28 | 版本发布 | v1.6.0 单题删除与 v1.5.0 后变更汇总 | [查看](2026-07-28_question-deletion-release.md) |
| 2026-08-01 | 数据整理 | 数学题目分类纠正 | [查看](2026-08-01-reclassify-quadratic.md) |
| 2026-08-06 | 数据迁移 | 分类标点与知识点清空 | [查看](2026-08-06_category-punctuation-migration.md) |
| 2026-08-07 | 数据纠正 | 分类文件名与编号修复 | [查看](2026-08-07_category-filename-fix.md) |
| 2026-08-14 | 文档治理 | 审计偏差修复（文档-代码同步） | [查看](2026-08-14_doc-code-sync-audit-fixes.md) |
| 2026-08-16 | 新功能 + 前端修复 | 行动推荐、目录页与深色对比度修订（v1.7.0） | [查看](2026-08-16_action-plan-dark-contrast-catalog.md) |
| 2026-08-16 | 前端/导出修复 | 答案跨行 LaTeX 渲染 | [查看](2026-08-16_answer-math-rendering.md) |
| 2026-08-16 | 服务修复 | 设置页重启生命周期 | [查看](2026-08-16_omrs-settings-restart-fix.md) |
| 2026-08-16 | 版本发布 | v1.8.0 跨行公式与 systemd 重启修复 | [查看](2026-08-16_v1.8.0-release.md) |
| 2026-08-28 | 前端优化 | 部分判定提交、序号与吸顶概览（v1.8.2） | [查看](2026-08-28_partial-feedback-ui-followup.md) |
| 2026-08-28 | 前端优化 | 分批反馈 Session 进度与自动续录（v1.8.1） | [查看](2026-08-28_partial-feedback-ui.md) |
| 2026-08-29 | 前端修复 | 分批反馈序号保持 Session 原始顺序 | [查看](2026-08-29_feedback-sequence-numbering.md) |
| 2026-08-30 | 导出修复 | A4 打印题目栏底裁切 | [查看](2026-08-30_a4-print-question-clipping.md) |
| 2026-08-30 | 导出修正 | A4 采用块级防截断，取消整题留白 | [查看](2026-08-30_a4-print-no-waste.md) |
| 2026-08-31 | 新功能 | 题目停用/恢复机制（v1.9.0） | [查看](2026-08-31_question-suspend.md) |
| 2026-08-31 | 后续修复 | 题目停用边界、稳定身份与 Session 过滤 | [查看](2026-08-31_question-suspend-followup.md) |
| 2026-09-01 | 新功能 | 设置页下载脱敏源码 | [查看](2026-09-01_sanitized-source-export.md) |
| 2026-09-02 | 修复 | 打包源码缺 qview.js（git 未跟踪导致） | [查看](2026-09-02_source-export-missing-qview.md) |
| 2026-09-01 | 共享题目视图（qview）+ 反馈录入工作台 | [`2026-09-01_feedback-workbench.md`](2026-09-01_feedback-workbench.md) |
| 2026-09-03 | 收件箱录入流程（上传 → 处理 → 录入）、AI 框选 / 可转性判断、训练数据集 | `2026-09-03_inbox-intake.md` |
| 2026-09-03 | 收件箱 P3：框选提供方（template / local_http）、盲标、自动策略、清理（v1.13.0） | `2026-09-03_inbox-intake-2.md` |
| 2026-09-03 | 生产部署 v1.13.0（omrs2.zip 收件箱 P3 源码导出） | `2026-09-03_deploy-v1.13.0-production.md` |

| 2026-09-09 | 生产部署 | 展示板实时预览 Phase 1–2 合入生产（v1.17.0） | [`2026-09-09_deploy-board-preview-phase1-2-production.md`](2026-09-09_deploy-board-preview-phase1-2-production.md) |
| 2026-09-09 | 交接/未完成任务 | 展示板重设计第 1–2 期生产合入与第 3–4 期欠账清单 | [`2026-09-09_board-preview-remaining.md`](2026-09-09_board-preview-remaining.md) |
| 2026-09-08 | 生产部署 | v1.17.0（展示板文件夹 + 统一选板浮层，跳过浏览器验收） | `2026-09-08_deploy-v1.17.0-production.md` |
| 2026-09-12 | 任务 | 展示板重构：状态条 / 舞台 / 检查器三区（v1.18.0） | [`2026-09-12_board-refactor.md`](2026-09-12_board-refactor.md) |
| 2026-09-12 | 生产部署 | v1.18.0（展示板三区重构 + 等待记录纸面状态，含 TIME-WAIT 重启坑记录） | [`2026-09-12_deploy-v1.18.0-production.md`](2026-09-12_deploy-v1.18.0-production.md) |
| 2026-09-12 | 任务 | 反馈提交结果改弹窗（`#fb-result-modal`，v1.18.1） | [`2026-09-12_feedback-result-modal.md`](2026-09-12_feedback-result-modal.md) |
| 2026-09-12 | 生产部署 | v1.18.1（反馈提交结果改弹窗；TIME-WAIT 序列重启一次成功，零写入验收） | [`2026-09-12_deploy-v1.18.1-production.md`](2026-09-12_deploy-v1.18.1-production.md) |
