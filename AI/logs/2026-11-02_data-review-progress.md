# 2026-11-02 数据复盘击杀进度与题目明细

> **任务**
> - 标识：data-review-progress
> - 状态：已交付

## 背景

用户原话：「数据复盘页改进一下」「还看不了已击杀等数据」「看看还有啥能补充」。执行者 Codex，完整模式，独立页面改进，不属于既有执行计划。基线 HEAD `667603a` 加开工工作区；已有导出排版、相关文档及计划验证清单的修改保留，不纳入本次实现。

现有分析接口已经提供当前击杀状态、逐题累计成绩和实际复核字段；缺口在页面概览与明细展示。因此复用既有只读接口，未改变算法、存储或 HTTP 契约。

## 行为变化

概览新增参与复盘题数、已击杀及击杀率、待攻克、练习覆盖率，另列停用数量。新增题目状态明细，默认已击杀，支持全部、休眠、复燃待复核、待攻克、未复习和顽固题；科目和关键词交叉过滤、完整匹配分页、真实详情及加入展示板。

新增休眠、复燃、累计击杀次数、曾击杀题数和五档复核分布；累计成绩包含后来降级的题目，不以当前状态推断成绩。到期预测补上已逾期。每日趋势与标记分布改为同一分析响应，避免与统计快照刷新时差。修正概览的 CSS 优先级，防止通用 dl 重置规则吃掉卡片内边距。

## 影响文件

- `assets/app/features/data/`：概览、状态与累计成绩纯函数、明细视图、控制器和页面样式。
- `tests/app/analytics.test.mjs`、`tests/app/data-progress.test.mjs`、`tests/e2e/data.py`：比例、停用排除、降级历史、筛选、完整分页、真实浏览器和错误状态回归。
- `AI/frontend/records.md`、`AI/frontend/architecture.md`、根 `README.md`：同步页面行为和验证入口；本日志及自动生成索引留痕。

已用 `git diff --name-status` 与未跟踪清单复核实际范围；开工原有的六条独立源码／文档改动与保存的基线补丁逐项完全一致。根 README 与自动日志索引在原有修改上追加本次内容，原导出任务的未跟踪日志保持。

## 已执行验证

- `node --test tests/app/*.test.mjs` 最终 573 / 573 通过，零跳过，见 `node-final.log`。初次全量 572 / 573：新增视图测试的合成数据缺少共享复核组件使用的 mastery 字段，已补齐。更早的 5 项定向检查有两处旧断言不符合新概览数量／逾期行，已更新。
- `env -u OMRS_SYSTEMD_SERVICE OMRS_DATA_SHOTS=/tmp/omrs-data-review-evidence/shots python3 -u tests/e2e/data.py` 最终退出码 0，32 / 32 通过，见 `data-e2e-verified.log`。包含真实反馈构造的跨页击杀、升档、复燃、降级成绩、过滤交叉、详情下一题、刷新与导出错误、空库及浅深色手机／桌面审计。
- E2E 前两轮均 28 / 29：空结果场景在题目弹窗仍处于退出动画时填写背景输入；仅等待文本无效，改为等待真实 dialog 关闭后通过。第一次扩展后 32 / 32 的工具会话退出 143，未以此当作成功进程；最终独立重跑明确退出 0。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/app/run_browser.py` 35 / 35 通过；`python3 tests/check_ui.py` 全仓零违规；`python3 tests/check_contrast.py` 58 组全部通过；`git diff --check` 通过。
- `env -u OMRS_SYSTEMD_SERVICE python3 -u tests/visual/run.py --ref HEAD --pages data --out /tmp/omrs-data-review-evidence/visual-final` 退出 0，浅深色 × 桌面手机共 4 对截图。脚本错误、横向溢出、行内样式与过小目标均为零，最小字号 12px；截图已肉眼复核。首次视觉在内边距修正前也通过，最终报告取 `visual-final/`。
- 最终截图差异：浅色桌面 30.672%、深色桌面 32.461%、浅色手机 28.252%、深色手机 28.279%。共同原因是新增四个概览、整行状态明细、击杀复核卡与逾期横条导致后续图表下移；概览恢复内边距。两种主题使用既有状态色，手机明细按共享表格堆叠，未产生横向滚动。
- `python3 tests/check_docs.py --write-log-index` 已生成索引；`python3 tests/check_docs.py --diff HEAD` 检查 157 份文档、零问题，3 条既有大文件提醒。首轮在生成索引前报索引不同步，生成后通过。全部证据在 `/tmp/omrs-data-review-evidence/`，未使用真实题库或生产端口。

## 未执行验证

后端全集未执行：只修改只读前端与其测试，已通过页面真实接口、反馈构造及下载链路。实体设备、真实题库和生产环境未验收；全部浏览器验证为 Linux Chromium 合成题库。未改版本号、提交、推送或部署，下一步可按独立发布授权上线。
