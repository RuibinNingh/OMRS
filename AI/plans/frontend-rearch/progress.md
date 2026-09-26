# 前端重构：进度

> **状态**
> - 目标：重建前端架构，让 CCW 能安全修改、可维护性提升、UI 精致化（总纲见同目录 `plan.md`）
> - 阶段：**P6 第 5 轮完成**（v1.25.4：「全题库导出」迁进复习调度页，复习调度三块全部原生）；第 1–4 轮已交付（v1.25.0 仪表盘与统计数据所有权、v1.25.1 数据复盘、v1.25.2 复习调度外壳与已有计划、v1.25.3 安排复习）
> - 基线：p6r5 及之前的补丁链已在本机工作区合并为 v1.25.4（2026-09-26 导出包 `20260926T140037Z` 核对）；基线提交由 Codex 按执行说明阶段 0 建立，建好后在此填入哈希
> - 下一步：Codex · 完整，按同目录 `exec-2026-09-26-codex.md` 从阶段 0 起执行（本机基线 → P6 剩余页面 → P7 → P8 → 终检，部署另等用户授权）
> - 更新：2026-09-26，CCW 规划：执行者改为 Codex，写入执行说明（§9）

## 1. 用户诉求原话（每期都要能对应回这里）

| # | 原话 | 含义 |
|---|---|---|
| U1 | "目前的前端架构我觉得还是很粗糙，很多时候打磨不够细致" | UI 精致度 |
| U2 | "并且设计上不合理" | 交互和信息架构 |
| U3 | "维护更麻烦" | 可维护性 |
| U4 | "重设计一个前端架构，让 CCW 能进行修改的同时，提升可维护性，还有实现 UI 的精致化打磨" | **总目标** |
| U5 | "受限模式不是只能只读出方案……依旧可以执行你最大范围的能力" | 要动手，不要只出方案 |
| U6 | "继续，到时候生成的文档记得是交接的" | 文档写成交接式 |
| U8 | "那P1也完成吧，到时候统一发我文件" | 可以连做几期，最后统一交付 |
| U11 | "我不打算让Hermes验收了,执行完p3的交接执行者改为CCW" | 各期之间不再交给 Hermes |
| U12 | "直到全部执行完毕,最后让一个CCW检查项目文件,确认项目没有问题" | P8 之后加一次 CCW 终检 |
| U13 | "总任务完成后让Hermes部署" | Hermes 只在最后部署一次 |
| U14 | "建议在文档里面放计划文件,每个计划可以是一个文件夹表示总计划,然后里面任务进度维护" | 本文件夹；进度只维护在这里 |
| U15 | "剩下的交给Codex执行,去掉交接文档环节" | P6 剩余到终检由 Codex · 完整执行，每页一个本机提交；不再出补丁、完整包、UPGRADE、交接清单；终检由 Codex 做（取代 U12 的执行者） |

## 2. 流程与生产现状

| 阶段 | 执行者 / 模式 | 开工基线 | 交付 |
|---|---|---|---|
| P0 → P6 第 5 轮（已完成） | CCW · 受限，每期一到数轮 | 上一轮 CCW 交付的完整包 | 补丁、完整包、UPGRADE、截图包（历史做法） |
| P6 剩余 → P7 → P8 → 终检 | Codex · 完整，按 `exec-2026-09-26-codex.md` | 本机基线提交（执行说明阶段 0 建立） | 本机分支 `frontend-rearch` 上每页一个提交，含代码、测试、文档、任务日志与本文件的更新；不再出任何包外交接物 |
| 部署 | 用户授权后执行；执行者由用户指定，未指定时按 U13 由 Hermes 执行 | 终检通过的提交 | 按 §8 的部署清单执行 |

**补丁链（历史）。** ① `changes-2026-09-25-p2.patch` → ② `p1` → ③ `p1-fix` → ④ `dp4` → ⑤ `p3` → ⑥ `p4` → ⑦ `p5r1`…`p5r4` → ⑧ `p6r1`…`p6r5`，已在本机工作区合并。

2026-09-26 的导出包核对结果：
- 版本 v1.25.4；
- 与 p6r5 完整包相比，只多出本机浏览器测试的 CDP 适配（`tests/browser_runtime.py` 等）；
- 此后不再出补丁。

**生产现状（2026-09-25 实测，执行说明阶段 0 复核后在此改正）：**
- `omrs.service` 为 active，`/api/status` 返回 v1.19.1、208 题；
- 本机 HEAD 是 `4fd4827`（v1.18.2），工作树有大量未提交和未跟踪的改动；
- 生产服务是否运行在这个工作区，待阶段 0 用 `systemctl cat omrs.service` 确认。后端每次请求都从磁盘读 `/assets/*`，所以如果服务就在工作区里运行，改文件等于直接上线。

**处理工作树的边界：**
- 不得 `reset --hard`、`git clean`、整目录覆盖或做无范围的 `restore`；
- 上线前备份源码和工作树改动；
- 绝不覆盖 `错题/`、Ledger、环境配置和 systemd 文件。

## 3. 分期状态

| 期 | 版本 | 状态 | 要点 |
|---|---|---|---|
| P0 | v1.19.1 | 生产在线 | token、对比度、门禁、fixture、截图对比 |
| P2 | v1.20.0 | 交付；用户验收通过 | 23 个 ui 组件、gallery、统一 toast 与 `<dialog>`、`@layer` 分层 |
| P1 | v1.21.0 | 交付；用户验收通过 | core 底座、hash 路由、外壳重排、`/assets/` 304 |
| DP4 + P3 | v1.22.0 | 交付，未部署 | 顶栏瘦身；即时练习迁到 `features/instant/`；`domain/` 四个适配器 |
| P4 | v1.23.0 | 交付，未部署 | 反馈录入迁到 `features/feedback/`；`domain/sessions.js`；全站 `ui/dialog` 标题栏修复 |
| P5 | v1.24.0 → v1.24.2 | **完成（4 轮）** | 第 1 轮：`domain/question/`、容器查询根治、超宽公式、计划文件夹入库。第 2 轮：题目库迁到 `features/questions/`、`domain/question/ops.js`、全局 Esc 统一进 core/keys、删 `qtable.js` 与约 170 条旧题库 CSS。第 3 轮（v1.24.1）：题目弹窗 `modal.js` 与 Markdown 编辑器 `editor.js` 换 `ui/dialog`、`ui/overlay` 客人浮层、焦点回到行。第 4 轮（v1.24.2）：`domain/labels/`（芯片不写 `style=`、预设色进 tokens、选择器与管理的数据部分）、qview 外观全部搬进 `qview.css` 并 token 化（题面 16px 阅读正文）。日志 `AI/logs/2026-09-25_frontend-rearch-p5.md` |
| P6 | v1.25.0 → v1.25.4 → | **进行中（第 5 轮完成）** | 第 5 轮（v1.25.4）：「全题库导出」原生（`exporter*.js`、`domain/exporting.js`），删 `export.js` 与 `domain/schedule.js`。第 4 轮（v1.25.3）：「安排复习」原生（`arrange*.js`），删 `recommend_v2.js`，冒烟测试全过。第 3 轮（v1.25.2）：复习调度迁到 `features/schedule/`（标签栏与已有计划原生，安排复习 / 全题库导出仍是旧 DOM 由页面切换），`SESSIONS` 归 `domain/sessions.js`，删 `test_schedule_sessions.js`。第 2 轮（v1.25.1）：数据复盘迁到 `features/data/`（字号 14→3 种、行内样式 177→0、表格手机降级为卡片），删 `data.js`。第 1 轮（v1.25.0）：`domain/data.js` 成为统计数据所有者（并发合并、失败保留快照、旧 `DATA` 镜像、旧刷新链钩子）、`QUESTION_CACHE` 归 `domain/question`、仪表盘迁到 `features/dashboard/`（D8）、删 `dashboard.js` / `actions.js`。日志 `AI/logs/2026-09-25_frontend-rearch-p6.md` |
| P7 | — | 未开始 | 见 §8 |
| P8 | — | 未开始 | 见 §8 |
| 终检 / 部署 | — | 未开始 | 见 §8 |

## 4. 门禁基线（本机合并后的 v1.25.4 上应得到的数）

| 命令 | 预期 |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 159 OK（2026-09-26 起含本机新增的 `test_browser_runtime.py`、`test_visual_diff.py`）|
| `node --test tests/*.js tests/app/*.test.mjs` | 220 / 220 |
| `python3 tests/app/run_browser.py` | 34 / 34 |
| `python3 tests/e2e/shell_router.py` | 20 / 20 |
| `python3 tests/e2e/ui_bridge.py` | 15 / 15 |
| `python3 tests/e2e/instant.py` | 23 / 23（「标记筛选」偶发 22，重跑即过）|
| `python3 tests/e2e/feedback.py` | 31 / 31 |
| `python3 tests/e2e/questions.py` | 92 / 92 |
| `python3 tests/e2e/dashboard.py` | 26 / 26 |
| `python3 tests/e2e/data.py` | 21 / 21 |
| `python3 tests/e2e/schedule.py` | 45 / 45 |
| `python3 -m unittest tests.smoke_schedule_workbench` | OK（P6 第 4 轮起全过）|
| `python3 tests/check_ui.py` | 0 处问题；存量 handlers 127、html_assign 84、inline_style 126、color_literals 103、font_size_literals 227 |
| `python3 tests/check_contrast.py` | 58 组，0 不达标 |
| `python3 tests/check_docs.py --diff <基线>` | 0 处问题，1 条提醒（`AI/api.md` 53KB）|

## 5. P5 任务书：题库与共享题目视图

原计划 §6 P5：`domain/question/`（Markdown 和 KaTeX 渲染按内容哈希缓存，qview 与记录模块迁入）；`features/questions/`（表格和画廊双视图、筛选抽屉、批量条、列设置、视图预设；窄屏降级为卡片列表 D4）；`domain/labels/`。验收：题库相关 Node 测试迁移后全绿；E2E（筛选 → 切换视图 → 打开详情 → 翻页 → 打标记 → 批量）；过渡桥为 feedback 和 export 保留的 qview 调用逐条登记。

第 1 轮（已完成）：

- [x] `domain/question/`：`markdown.js`（内容哈希缓存）、`records.js`、`view.js`、`mount.js`、`index.js`、`qview.css`；旧 `qview.js`、`domain/questions.js` 删除
- [x] qview 容器查询根治（挂载点是容器）、超宽公式统一处理；删掉 `instant.css` / `feedback.css` 的挂载点补丁；题目弹窗窄屏单栏
- [x] 过渡桥 `installQuestionBridge` 逐条登记旧调用方
- [x] 弹窗 `←/→` 接入 `core/keys.js`（原 `qvHandleKey`）
- [x] 三份旧 node 测试并入 `tests/app/question.test.mjs`（26 → 34）；新增 `tests/e2e/questions.py`（弹窗与挂载点部分）
- [x] 计划文件夹 `AI/plans/` 与 `check_docs.py` 规则 9

第 2 轮（已完成）：

- [x] 题库页迁到 `features/questions/`：`index.js`（309 行）、`state.js`（291，纯函数全覆盖）、`view.js`、`list.js`、`dialogs.js`、`questions.css`（242）；题目操作迁到 `domain/question/ops.js`；删 `qtable.js`，`questions.js` 缩到 21 行
- [x] 窄屏（≤760）表格降级为卡片列表（D4），搜索框 placeholder 不截断；可点目标桌面 ≥28、手机 ≥40（E2E 断言）
- [x] `qbHandleKey`（`qtable.js`）与 `labels.js` 的 keydown 迁到 `core/keys.js`；`app.js` 关弹窗的 Esc 一并收进过渡桥 `installEscapeBridge`（它先于 core/keys 执行，会让页面 Esc 误清勾选）
- [x] 删 `styles/legacy-bridge.css` 的「题库工具栏」段；`styles.css` 删 166 条旧题库规则
- [x] `tests/test_qtable_ui.js` 迁到 `tests/app/questions.test.mjs`（用例只增不减，共 20）；`tests/e2e/questions.py` 补题库主路径与本页审计（23 → 70）
- [x] 截图：`tests/visual/run.py --ref fd41951`（p5r1）与题库主路径 4 个状态 × 桌面 / 手机 × 浅 / 深的改前 / 改后对照，差异逐项写在日志
- [x] 版本 v1.24.0、changelog、补丁 `p5r2`（相对 p5r1）、完整包、UPGRADE、本文件

第 3 轮（已完成，v1.24.1，补丁 `p5r3`）：

- [x] 题目弹窗换成 `ui/dialog`（`domain/question/modal.js`）：焦点陷阱、Esc、关闭后焦点回到触发元素；题库传 `returnFocus`，关闭后游标与焦点落在最后看的那题
- [x] 叠在上面的旧浮层进顶层：`ui/overlay` 客人机制（`hostGuest`，旧代码经 `__omrsUi.host`）——标记选择器、选板浮层、标记管理
- [x] Markdown 编辑器换成 `ui/dialog`（`domain/question/editor.js`）；`ui/dialog` 加 `xl`、`onOk`、`dismissible` 函数、`returnFocus`
- [x] 删 `installEscapeBridge` 关弹窗那一条、`omrs_dashboard.html` 两个旧外壳、`questions.js` 编辑器、`styles.css` 只服务它们的规则
- [x] E2E：`questions.py` 70 → 91（焦点回到行、编辑器保存写回、浮层在弹窗里可操作、弹窗打开状态审计）；浏览器单测 31 → 34
- [x] 截图、版本 v1.24.1、补丁 `p5r3`、完整包、UPGRADE、本文件

第 4 轮（已完成，v1.24.2，补丁 `p5r4`；P5 到此结束）：

- [x] `domain/labels.js` 扩成 `domain/labels/`：`color.js`、`sheet.js`（运行时样式表，`@layer domain`）、`chips.js`、`model.js`（纯函数）、`index.js`、`labels.css`；芯片、色板、颜色圆点写 `data-lbl-c`，不写 `style=`；预设色 `--lbl-preset-1…10` 与 solid 前景 `--lbl-fg-*` 进 tokens，本目录 JS 无颜色字面量
- [x] 旧 labels.js 删颜色工具、芯片与最近使用；排序、增改、候选、批量、管理表单改调过渡桥 `installLabelsBridge` 挂的纯函数；`test_labels_ui.js` 迁到 `tests/app/labels.test.mjs`（5 → 10）
- [x] qview 全部外观搬进 `qview.css` 并 token 化（连同 `.gallery-card .qv …`、深色 `.qv .q-md`、`.sch-gallery-preview .qv`、`.md-p` / `.md-table*` 等），`styles.css` 净删 100 行；截图差异逐项写在日志
- [x] E2E：弹窗与画廊审计去掉对 `.lbl` 的排除，新增芯片颜色走运行时样式表的检查（91 → 92）
- [ ] 标记管理换 `ui/dialog`（可选项，未做）：移到 P6 或 P8，见 §8
- [x] 截图、版本 v1.24.2、补丁 `p5r4`、完整包、UPGRADE、本文件

## 5b. P6 任务书：其余中小页面 + 数据所有权

第 1 轮（已完成，v1.25.0，补丁 `p6r1`）：

- [x] `domain/data.js` 成为 `/api/stats` 的所有者：快照、旧 `DATA` 镜像、旧刷新链 `legacyDataRefresh()` 钩子、并发合并、失败保留快照（删 `demo()`）；`tests/app/data.test.mjs`
- [x] 详情缓存 `QUESTION_CACHE` / `QUESTION_PENDING` 归 `domain/question/mount.js`，旧代码读只读全局
- [x] 仪表盘迁到 `features/dashboard/`（`plan.js` 纯规则、`state.js` 派生、`view.js`、`index.js`、`dashboard.css`）；D8；字号 16→5 种、小目标 4→0、行内样式 8→0；`domain/history.js`、`domain/schedule.js` 两个过渡适配器
- [x] 删 `dashboard.js`、`actions.js`、`styles.css` 223 行；数据复盘的两张图搬进 `data.js`
- [x] `tests/app/dashboard.test.mjs`（旧 node 测试里的行动推荐断言迁入）、`tests/e2e/dashboard.py`（26）
- [x] 截图、版本 v1.25.0、补丁 `p6r1`、完整包、UPGRADE、本文件

第 2 轮（已完成，v1.25.1，补丁 `p6r2`；按 §9 只做数据复盘）：

- [x] 数据复盘迁到 `features/data/`（`state.js` 纯函数、`charts.js` 三张 SVG、`view.js`、`index.js`、`data.css`）；`core/download.js`
- [x] 字号 14→3 种、最小 8.7→12px、行内样式 177→0；表格用 `ui/table`（手机卡片）、横条用原生 `<progress>`、颜色走 `data-tone`
- [x] 统计快照变化时重拉 analytics；首次失败给重试；导出失败原因写页首
- [x] 删 `data.js`、`styles.css` 74 行；旧刷新链去掉 `renderDataCharts`
- [x] `tests/app/analytics.test.mjs`（5）、`tests/e2e/data.py`（21）；截图、版本、补丁、完整包、UPGRADE、本文件

第 3 轮（已完成，v1.25.2，补丁 `p6r3`；按 §9 只做复习调度的外壳、已有计划与 `SESSIONS`）：

- [x] `domain/sessions.js` 成为 Session 列表所有者（只认最新、失败保留、删除作废旧加载），`sessionProgress` 两页共用；`installScheduleBridge`
- [x] `features/schedule/`：标签栏（←/→/Home/End）、已有计划（筛选、详情、删除、导出、录入结果、预览）原生；安排复习 / 全题库导出是挂载点里的旧 DOM，经 `domain/schedule.js` 切换
- [x] 切回「安排复习」重拉推荐（冒烟测试原先停在「空推荐提示」的原因）
- [x] `schedule.js` 184→10 行；删 `test_schedule_sessions.js`（用例迁到 node 与 E2E）；`styles.css` 34 条
- [x] `tests/app/schedule.test.mjs`（5）、`tests/e2e/schedule.py`（25）；截图、版本、补丁、完整包、UPGRADE、本文件

第 4 轮（已完成，v1.25.3，补丁 `p6r4`）：

- [x] 「安排复习」原生：`arrange.js`（纯函数）、`arrange-ctl.js`、`arrange-view.js`；画廊题面懒加载恢复（`QV_CARD_OPTS` 缺全局导致的旧失败）
- [x] 删 `recommend_v2.js`、`test_recommend_v2_filters.js`（迁到 `tests/app/arrange.test.mjs`）、`reviveChipHtml`、`initRecommendV2`、`styles.css` 约 170 行
- [x] `smoke_schedule_workbench.py` 全过；`tests/e2e/schedule.py` 33（含「安排复习」审计）
- [x] 截图、版本、补丁、完整包、UPGRADE、本文件

第 5 轮（已完成，v1.25.4，补丁 `p6r5`）：

- [x] 「全题库导出」原生：`exporter.js`（纯函数）、`exporter-ctl.js`、`exporter-view.js`；导出统一走 `domain/exporting.js`（「已有计划」的导出也改走它）
- [x] 删 `export.js`、`domain/schedule.js`、`EXPORT_SELECTION` / `EXPORT_VIEW`、过渡桥 `schShow` / `showRecommendPanel`、`styles.css` 22 条；`downloadExportResponse` 全局改由 `core/download.js` 实现
- [x] `tests/app/exporter.test.mjs`（4）、`tests/e2e/schedule.py` 45（含导出段与审计）；冒烟测试仍全过
- [x] 截图、版本、补丁、完整包、UPGRADE、本文件

P6 剩余（Codex · 完整，细节以 `exec-2026-09-26-codex.md` 阶段 2 为准；以下为原第 6 轮开工条目，截图脚本一项已定位）：

- 范围：历史记录（`history.js` → `features/history/`；`domain/history.js` 的转调换成真实现，仪表盘最近动态不动）、目录（`catalog.js` → `features/catalog/`）。量大时先做历史记录（有修正、撤销、还原等写操作，E2E 要覆盖）。
- 截图脚本的「复习调度 44 处行内样式」：2026-09-26 已定位为脚本问题。`shoot()` 先整页截图、后跑审计，截图后页面里所有 `<input>` 都带上空的 `style=""`，审计用 `hasAttribute('style')` 把它们计了进去（复习调度 44 个、题库 41 个，全是 input）；截图前数是 0。修法：只计非空 `style`，并排除 `.katex` 内部。执行说明 2.1 负责修。
- 其后：报告、设置、录入题目与收件箱入口、`inbox_mobile.html` 接 tokens（§9）；P6 全部完成后进 P7 展示板。

以下是原「第 5 轮开工」条目（留作记录）：

- 范围：「全题库导出」（`export.js` 的选题器，DOM `#export-panel`）迁进复习调度页，之后删 `domain/schedule.js` 与 `installScheduleBridge` 的 `schShow`；历史记录（`domain/history.js` 的转调换成真实现）。量大时先做全题库导出。
- `export.js` 里的 `exportSession` / `requestExport` / `downloadExportResponse` 还被已有计划的导出、展示板与题库批量导出使用，迁时先搬进 domain（或 `core/download.js`），再删旧文件。
- 目录、报告、设置、录入题目与收件箱入口、`inbox_mobile.html` 在后面几轮（§9）。

以下是原「第 4 轮开工」条目（留作记录）：

- 范围：「安排复习」（`recommend_v2.js`）迁进 `features/schedule/`（仍是同一页，新增子视图模块，注意单文件 ≤400 行）；「全题库导出」（`export.js` 的选题器）视预算同轮或下一轮。`smoke_schedule_workbench.py` 现在停在第 79 行（画廊题面预览找不到 `.sch-gallery-preview .q-md`，见日志第 3 轮），随「安排复习」一起修。
- 迁完后删 `domain/schedule.js` 的对应转调、`installScheduleBridge` 的 `schShow`、`legacyDataRefresh()` 里的 `initRecommendV2`。
- 历史记录、目录顺延到第 5 轮；报告、设置、录入题目与收件箱入口、`inbox_mobile.html` 再往后（§9）。

以下是原「第 3 轮开工」条目（留作记录）：

- 范围：复习调度（`SESSIONS` 所有权反转到 `domain/sessions.js`，`refreshSessions` 的计划列表加载态留给页面；`smoke_schedule_workbench.py` 余下失败）、历史记录（`domain/history.js` 的转调换成真实现，仪表盘不动）。量大时先做复习调度（用户每天从仪表盘「开始复习」进它）。
- 复习调度迁完后：`domain/schedule.js` 的 `showArrange()` 换成页面事件；`legacyDataRefresh()` 里 `initRecommendV2` 删掉。
- 以下是原「第 2 轮开工」条目，仍然适用：

- 范围：复习调度（`SESSIONS` 所有权反转到 `domain/sessions.js`，`refreshSessions` 的计划列表加载态留给页面；`smoke_schedule_workbench.py` 余下失败）、数据复盘（清行内样式；`data.js` 里 `renderDataCharts` 等搬进 feature）、历史记录（`domain/history.js` 的转调换成真实现，仪表盘不动）。
- 复习调度迁完后：`domain/schedule.js` 的 `showArrange()` 换成页面事件；`legacyDataRefresh()` 里 `initRecommendV2`、`renderDataCharts` 两项删掉。
- 筛选语义 `filterItems` / `getDueDays` 搬进 `domain/items.js` 时，同步改 `tests/test_question_suspend_frontend.js`、`tests/test_recommend_v2_filters.js`（它们在 node 沙箱里直接调旧全局）。
- 每轮第一步把 WIP 补丁写进下载目录（§7）。

P6 开工（CCW · 受限；第 1 轮用，留作记录）：

- 先读 `plan.md` §6 P6 与本文件 §8；每轮第一步把 WIP 补丁写进下载目录（§7）。
- 范围大（8 个页面 + `DATA` / `SESSIONS` 所有权反转 + `inbox_mobile.html` 接 tokens），原计划两轮，开工时按用户可见度排轮次并登记在 §9；建议第 1 轮先做 `DATA` 所有权反转与仪表盘（D8）——其余页面都依赖 `DATA`，仪表盘是每天第一眼看的页。
- 迁一页照 §6 的四到五个文件写法；每页一个 `tests/e2e/<页>.py`，照 `questions.py` 的段落与审计。
- `smoke_schedule_workbench.py` 的剩余失败属于复习调度页，随该页修掉。

## 6. 已立下的写法（后续各期照抄）

- **页面 = 四到五个文件**：`index.js`（页面契约 + 控制器）、`state.js`（模块单例 + 纯函数，node 单测全覆盖）、`view.js`（只产出 `html```）、`<页>.css`（`layer(features)`，类名用页面前缀避免与待删旧类冲突，如 `fbw-`）。逻辑能写成纯函数的再拆一个文件，让原来要靠 DOM 桩的断言能在 node 里跑。
- **渲染**：`morph(root, view(state))`；可有可无的块带 `data-key`；`each()` 的 key 必须唯一且与模板里 `data-key` 一致；第三方渲染挂载点 `data-morph="skip"`，key 编码「何时必须换新」，`hydrate()` 交给 domain。
- **领域模块**：真实现放 `domain/<领域>/`，输出字符串的函数供旧代码拼接、新代码经 `raw()` 嵌入；旧代码仍调的同名全局在 `legacy-bridge.js` 用一个 `install<领域>Bridge` 集中挂，逐条注明调用方（先例：`domain/question/`）。
- **旧全局**：features 不写 `window.xxx`，一律经 `domain/`。读：`typeof X !== 'undefined'` 守卫后按名读。写：旧 `core.js` 的 `let` 全局不是 `window` 属性，要直接给标识符赋值。经典脚本只能在函数体里调用过渡桥挂的全局（文件顶层执行时模块还没运行）。
- **document 级监听**：keydown 一律走 `core/keys.js`；弹层里要响应的键登记为 `{ handler, inDialog: true }`，处理函数返回 false 表示不处理。`paste` 等非 keydown 事件在 `mount` 里加、在卸载函数里移除。
- **事件委托**：`data-change` 挂在 `ui/select` 外层时，处理函数里要从 `event.target.value` 读值。
- **菜单 / 浮层里触发旧浮层**：`ui/menu` 选中后要 `setTimeout(0)` 再打开旧浮层（标记选择器、选板），否则同一次点击冒泡到 document 被旧的「点外面关闭」立刻关掉。页面自己的「点外面关闭」用 `event.composedPath()` 判断，重绘后目标脱离 DOM 也判得准。
- **Esc**：`core/keys.js` 同一作用域同一键只有一个处理函数；全局 Esc 集中在过渡桥 `installEscapeBridge`，新增旧浮层的 Esc 加进它，不要另挂 document 监听。页面作用域的 Esc 在旧浮层开着时返回 false 让位。`ui/dialog` 的 Esc 由 `ui/overlay` 在捕获阶段处理，到不了 core/keys。
- **标记芯片**：新代码用 `domain/labels` 的 `labelChip(s)`（经 `raw()` 嵌入），旧代码用全局 `lblChip(s)`；要按标记色上色的元素写 `data-lbl-c="${ensureColor(color)}"`，CSS 里用 `var(--lbl-c)`，不写 `style=`。
- **旧浮层叠在模态对话框上**：用 `__omrsUi.host(node, {close, escape})` 挂（有对话框时进对话框，否则进 body），自行关闭时 `__omrsUi.release(node)`；自己处理 Esc 的浮层 `escape:false`，否则 `escape:true` 交给 overlay 代关。直接 `document.body.appendChild` 会被模态对话框 inert。
- **关对话框后焦点交给别处**：`dialog({returnFocus})` / `openModal(el, {returnFocus})` / `viewQ(uid, ctx, {returnFocus})`；被交焦点的元素要可聚焦（列表行用 `tabindex=-1`）。
- **旧全局元素样式**：`styles.css` 里的 `header{…}` 等全局元素规则仍在 legacy 层生效，页面或组件用这些元素时要显式清零。
- **样式层**：domain / features 层高于 legacy，不看特异度；把一组规则搬出 `styles.css` 时，旧文件里覆盖它们的规则要一起搬，否则新层会反压。
- **模板不写 `style=`**：动态尺寸用 `data-*` 档位 + 样式表（先例：`data-clamp`、战绩带 `data-h`）或 HTML 属性（题图 `width`）。
- **加载态 / 空态 / 错态**：按钮立即 loading，超过 300ms 才骨架屏；空与错用 `ui/empty` 或 `ui/status`，出错写原因并给「重试」。
- **测试**：`tests/app/<页>.test.mjs` 测 state；`tests/e2e/<页>.py` 照 `feedback.py`（自建 fixture、隔离实例、认 `OMRS_TEST_CDP_URL`、只用条件等待、每段 `guarded()`、末尾桌面 / 手机 × 浅 / 深审计）。E2E 需要 Session 时用 `/api/confirm-schedule` 建。
- **截图证据**：`tests/visual/run.py --ref <上一期提交>`；另拍本页主路径各状态的改前 / 改后对照（改前用 `git worktree` 起旧实例、Vault 用副本；写接口用 `page.route` 拦截）。

## 7. 坑与经验

- （仅 CCW）**工具预算**：合并命令；长任务 `setsid … &` 放后台轮询；先做用户看得见的部分；每轮开头先提交一个 WIP 快照并把补丁放进 `/mnt/user-data/outputs/`，工作区即使被清也能从补丁恢复。
- **进程**：`pkill -f` 的模式别出现在同一条命令里；停和起分两次调用。用 Python 扫 `/proc/*/cmdline` 找 PID 会匹配到执行它的 shell，排除 `os.getpid()` 及其父进程，或按端口找，或记下启动时的 PID。后台服务在两轮对话之间会被清掉，每轮开头先 `curl` 确认。
- **服务版本**：改了 `omrs/version.py` 要重启实例再截图。
- **playwright**：`get_by_role(..., exact=True)` 严格模式；`ui/dialog` 的按钮是 `[data-dialog-ok]` / `[data-dialog-cancel]`；需要干净页面状态时用带查询参数的地址整页重载；粘贴用 `DataTransfer` + `ClipboardEvent('paste')` 派发到 `document.body`；键盘事件后读异步渲染的结果要等条件，不要立刻读。
- **E2E 里的 LaTeX**：Python 源码里写 `"\\frac"`（值是 `\frac`）；多转义一层变成 `\\frac`，KaTeX 当成换行。
- **CSS**：层内不看特异度只看层序；删旧 CSS 只按精确字符串删，并用 `git diff` 核对；不要用正则批量删「只含注释的块」。删完跑 `git diff --check`。容器查询只作用于后代。断点只许 760 / 1160 / 1500。
- **morph**：`<select>` 的选中项要写进模板的 `selected`；未聚焦的 textarea 会被同步回模板值——草稿要存进状态。
- （仅 CCW）**中文输出**：不要用 `cut -c` / `head -c` / `sed -n` 截中文长行；`grep` 输出里的中文长行同样会让整条工具输出失败，改用 Python 按字符截。
- （仅 CCW）**受限模式不要运行 `--write-log-index`**。
- **E2E 按快捷键前先点中性区**（如 `.qlb-total`）：点到 label 会把焦点给复选框，之后的字母键被当成输入；点到按钮上 Space / Enter 会被按钮吃掉。
- **删旧 CSS 的做法（P5 第 2 轮）**：按「选择器引用的类 / id 在 JS 与 HTML 里已无人使用」逐条删，部分失效的只去掉那几个选择器，再人工清孤立注释、`git diff` 逐段核对。KaTeX 输出自带行内样式，审计「不写 style=」时排除 `.katex *`。
- **补丁**：`git diff --binary <上一期提交>`；在上一期完整包的干净解压上 `git apply --check`、应用，再与工作区 `diff -rq`。
- **对话框动画**：入场 `scale(.98)` 期间量尺寸会小 2%（40 量成 39），E2E 量前等 400ms；退场动画期间仍是 `[open]`，守卫写 `dialog[open]:not(.is-closing)`。
- **乐观更新 + 立即重绘**：打标记先改题目列表再重绘，重绘时拉的详情可能早于保存请求到达服务端——展示以题目列表为准（qview 的标记已改）。
- **搬 CSS 时用到的元素要看全局规则**：qview 的题头是 `<header>`，旧全局 `header{}` 给它加了 16px 顶部内边距与 space-between；搬进新层后内外边距、边框、对齐全部显式写（详见日志第 4 轮）。
- **删旧 CSS 用脚本时**，判断「只含注释」不能用 `/\*.*?\*/` 加 fullmatch：懒惰匹配会越过规则连到后面的注释，把整块误判为纯注释（P6 第 1 轮误删过一个在用的 `@media(min-width:1161px)` 块，靠 `git diff` 发现）。写成 `/\*(?:(?!\*/).)*\*/`，删完逐个核对被删的 `@media` 块。
- **`pkill -f` 的坑 P6 第 1 轮又踩了一次**：`pkill -f "serve -p 18471"` 与启动门禁写在同一条命令里，杀掉了自己，门禁没启动。停服务单独一次调用。
- （仅 CCW）**沙箱 shell 是 dash**：`<(...)` 进程替换报错，需要时 `bash -c`。
- （仅 CCW）**P5 第 3 轮第一次会话**没在开头存 WIP 补丁，预算用完时改动只在沙箱里；每轮第一步必须先写 WIP 补丁到下载目录。

## 8. 已知遗留与后续路线

- `assets/board.js` 的 `focus: '[data-ui-ok]'` 过时（对话框按钮是 `data-dialog-ok`），P7 顺手改。
- 剩余 document 级 keydown（按 `document.addEventListener('keydown'` 计）：`app.js`（closeDrawer）、`board.js`、`board_picker.js`、`inbox.js`、`schedule.js`——都属于未迁页面、与弹窗无关，随各自页面迁（P6 / P7）；选板浮层的捕获阶段 keydown 已与 `ui/overlay` 客人机制协调。
- 芯片本身的外观（`.lbl` 的形状、淡底、深色）仍在旧 `styles.css`，P8 随 styles.css 一起搬；标记管理仍是旧 `.modal-overlay#label-manager`（叠在对话框上时登记为客人），P6 或 P8 换 `ui/dialog` 后删客人登记里的这一项。

| 期 | 要点 |
|---|---|
| P6 | 仪表盘（D8）、数据复盘、目录、历史、报告（FileDrop 修 D6）、设置、复习调度（含 `smoke_schedule_workbench.py` 余下失败）、录入题目与收件箱入口；`DATA` 与 `SESSIONS` 所有权反转到 `domain/` |
| P7 | 展示板：先搬纯函数与测试，再拆保存队列、打印协调、拖拽排序、版面设置、选板浮层，最后迁 UI |
| P8 | 删 `styles.css`、旧 token 别名、`legacy-bridge.js` / `legacy-pages.js` / `switchTab` 包装；`ui_baseline.json` 归零后删除 |
| 终检 | Codex · 完整：在新 worktree 里从零跑全部门禁与 E2E、12 页 × 浅深 × 桌面手机人工审阅、Firefox / WebKit 主路径、§2 指标表；部署与回滚清单写进本节 |
| 部署 | 用户授权后执行；执行者由用户指定，未指定时按 U13 由 Hermes 执行 |

## 9. 计划变更

| 日期 | 改动 | 依据 |
|---|---|---|
| 2026-09-25 | P3 之后各期的接力执行者改为 CCW；P8 后加 CCW 终检；Hermes 只在最后部署一次 | U11、U12、U13 |
| 2026-09-25 | 计划与进度入库到 `AI/plans/frontend-rearch/`；包外交接文档只列交付物并指向本文件 | U14 |
| 2026-09-25 | P5 拆成三轮：题目弹窗与 Markdown 编辑器换 `ui/dialog`、`domain/labels/`、qview 样式归位移到第 3 轮（弹窗换 `ui/dialog` 前要先让叠在上面的旧浮层能进顶层，工作量与风险都够单独一轮） | 第 2 轮工具预算；先交付用户看得见的题库页 |
| 2026-09-25 | 补丁 ⑦ 由「一份相对 v1.23.0 的补丁」改为 p5r1 → p5r2 → p5r3 按序应用 | 用户：「我给你的就是最新的包了」 |
| 2026-09-25 | P5 第 3 轮再拆：第 3 轮只做题目弹窗与 Markdown 编辑器换 `ui/dialog`、旧浮层进顶层（v1.24.1，补丁 p5r3）；`domain/labels/`、qview 样式归位移到第 4 轮（补丁 p5r4）；剩余 keydown 与弹窗无关，归各自页面（P6 / P7） | 第 3 轮第一次会话工具预算用完、未交付；按回复里提出的拆分方案，用户：「继续」 |
| 2026-09-25 | P6 排轮次（按用户可见度）：第 1 轮 `DATA` 加载与快照所有权反转到 `domain/data.js`、详情缓存 `QUESTION_CACHE` 进 `domain/question`、仪表盘迁到 `features/dashboard/`（D8）；第 2 轮复习调度（含 `SESSIONS` 所有权与 `smoke_schedule_workbench.py` 余下失败）、数据复盘、历史记录；第 3 轮目录、报告（FileDrop，D6）、设置、录入题目与收件箱入口、`inbox_mobile.html` 接 tokens。`SESSIONS` 的加载与复习调度页的计划列表绑在一起（`refreshSessions` 同时驱动计划列表的加载态），随该页一起反转 | 用户：「执行P6」；progress §5「P6 开工」建议第 1 轮先做数据所有权反转与仪表盘 |
| 2026-09-25 | P6 第 2 轮再拆：本轮只做数据复盘（只读页、旧行内样式最多、不涉及写操作，能在一次会话内收口，并顺带删掉旧数据刷新链里的 `renderDataCharts`）；复习调度（含 `SESSIONS` 所有权与 `smoke_schedule_workbench.py`）、历史记录顺延到第 3 轮，目录、报告、设置、录入题目与收件箱入口顺延到第 4 轮 | 第 1 轮一页加所有权用了三次会话；用户：「执行」 |
| 2026-09-25 | P6 第 3 轮只做复习调度（含 `SESSIONS` 所有权与 `smoke_schedule_workbench.py`）；历史记录顺延到第 4 轮（与目录同轮），报告、设置、录入题目与收件箱入口、`inbox_mobile.html` 顺延到第 5 轮 | 复习调度连同推荐、导出选题共三个旧脚本约 40KB，是 P6 最大的一页；一轮一页才能在一次会话内收口。用户：「继续」 |
| 2026-09-26 | P6 剩余到终检的执行者改为 Codex · 完整：每页一个本机提交，取消补丁、完整包、UPGRADE、交接清单与合并版 UPGRADE；终检由 Codex 做；部署执行者由用户指定（默认 Hermes）；执行说明 `exec-2026-09-26-codex.md`；删除重复的 `AI/rearch-plan.md`，其中仍有效的事实并入 §2 | U15；2026-09-26 导出包核对（本机已合并到 v1.25.4）|
