# 前端重构：进度

> **状态**
> - 目标：重建前端架构，让 CCW 能安全修改、可维护性提升、UI 精致化（总纲见同目录 `plan.md`）
> - 阶段：**P6 完成（v1.26.6）**，P7 完成（v1.26.5 已与 P6 合并）。P6 最后一段（录入页框选、题卡、AI 训练工作区，删除 `inbox.js`）由 Claude 在对话里按受限模式做完（U19），待 Codex 落地；之后 P8、终检
> - 基线：P6 本机基线提交 `7ebfc6c`（`rearch/base-v1.25.4`），开发 worktree 分支 `frontend-rearch`；P7 补丁基线是导出包 `20260927T013727Z`（v1.25.4）。本次三方合并的祖先由 P7 累计补丁反向应用还原（与该导出包清单逐项一致），P6 一侧是导出包 `20260927T125544Z`（含框选在制代码）
> - 下一步：Codex · 完整：① 先按任务日志 `AI/logs/2026-09-27_frontend-rearch-p6-p7-merge.md`「落地」应用合并补丁并提交（未做的话）；② 再按 `AI/logs/2026-09-27_frontend-rearch-p6-create.md`「合入」应用 `changes-2026-09-27-p6-create.patch`（相对合并完整包 v1.26.5），作为一个提交 `frontend-rearch P6: 录入页框选 / 题卡 / 训练 → features/create（v1.26.6）`；③ 补做本机步骤（`--write-log-index`、本机全量 E2E、真实浏览器走一遍录入页三个工作区）；④ 进 P8（执行说明阶段 4），之后终检；部署另等用户授权
> - 更新：2026-09-27，Claude（对话内，U19）完成 P6 剩余：收件箱前端数据归 `features/create/inbox-store.js`，框选收尾、题卡与 AI 训练工作区原生，删除 `assets/inbox.js`；门禁见 §4

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
| U16 | "直接推进P7,不需要等到P6,隔离完成" | P7 不等 P6 剩余页面，由 CCW · 受限按轮推进；只动展示板自己的文件，与 P6 剩余并行、互不依赖；每轮交补丁由 Codex 合入 |
| U17 | "继续第二轮,最后在合入" | P7 各轮在上一轮完整包上接着做，不逐轮合入；每轮交相对导出包的累计补丁，P7 全部完成后由 Codex 一次合入 |
| U18 | "合并两个分支 我让Codex做的P6,没做完,但是CCW P7做完了 所以请你帮我合并这两个代码"；「执行」「继续」 | P6 在制（Codex）与 P7（CCW）的合并改在对话里由 Claude 完成，交付合并后的完整包、相对 P6 导出包的合并补丁与任务日志；Codex 不再按 P7 日志「合入」自行应用累计补丁，只把合并补丁作为一个提交落地并补做本机验收 |
| U19 | "执行没有完成的P6"；「继续」 | P6 剩余（录入页框选收尾、题卡、AI 训练工作区，删 `inbox.js`）改在对话里由 Claude 按受限模式做完，交付相对合并完整包 v1.26.5 的补丁、完整包与任务日志，由 Codex 作为一个提交落地 |

## 2. 流程与生产现状

| 阶段 | 执行者 / 模式 | 开工基线 | 交付 |
|---|---|---|---|
| P0 → P6 第 5 轮（已完成） | CCW · 受限，每期一到数轮 | 上一轮 CCW 交付的完整包 | 补丁、完整包、UPGRADE、截图包（历史做法） |
| P7（2026-09-27 起，U16、U17） | CCW · 受限，每轮一个补丁 | 上一轮交付的完整包（不等合入） | 每轮：相对导出包 `20260927T013727Z` 的累计补丁、本轮增量补丁、完整包、任务日志；P7 全部完成后 Codex 按日志「合入」一次应用，按轮拆提交 |
| P6 在制 + P7 合并（2026-09-27，U18） | Claude（对话内） | P6 导出包 `20260927T125544Z`；P7 完整包与累计补丁（祖先 = 导出包 `20260927T013727Z`） | 合并后的完整包、相对 P6 导出包的合并补丁、任务日志；Codex 作为一个合并提交应用，P7 不再按轮拆提交（手里只有累计补丁与第 6 轮增量）|
| P6 最后一段（2026-09-27，U19） | Claude（对话内 · 受限） | 合并完整包 v1.26.5 | 相对该包的补丁 `changes-2026-09-27-p6-create.patch`、完整包、任务日志；Codex 作为一个提交落地 |
| P8 → 终检 | Codex · 完整，按 `exec-2026-09-26-codex.md`（阶段 3 由上一行代替） | 本机基线提交（执行说明阶段 0 建立） | 本机分支 `frontend-rearch` 上每页一个提交，含代码、测试、文档、任务日志与本文件的更新；不再出任何包外交接物 |
| 部署 | 用户授权后执行；执行者由用户指定，未指定时按 U13 由 Hermes 执行 | 终检通过的提交 | 按 §8 的部署清单执行 |

**补丁链（历史）。** ① `changes-2026-09-25-p2.patch` → ② `p1` → ③ `p1-fix` → ④ `dp4` → ⑤ `p3` → ⑥ `p4` → ⑦ `p5r1`…`p5r4` → ⑧ `p6r1`…`p6r5`，已在本机工作区合并。

2026-09-26 的导出包核对结果：
- 版本 v1.25.4；
- 与 p6r5 完整包相比，只多出本机浏览器测试的 CDP 适配（`tests/browser_runtime.py` 等）；
- 此后不再出补丁。

**生产现状（2026-09-26 实测）：**
- `omrs.service` 为 active，PID 1936793；`/api/status` 返回 v1.25.4、215 题；12 个页面在真实浏览器里均能打开，页面脚本错误为 0。
- 服务的 `WorkingDirectory` 是 `/root/workspace/apps/OMRS`，属于执行说明阶段 0 的情况 A；后端每次请求都从磁盘读 `/assets/*`，所以开发在独立 worktree `/root/.codex/worktrees/frontend-rearch/OMRS` 中进行。
- 开工时本机 HEAD 为 `4fd4827`（v1.18.2），有 305 条未提交状态；按执行说明的项目路径纳入 300 个文件，建立快照提交 `7ebfc6c`。未纳入的 5 个 `.playwright-mcp/` 临时文件留在生产目录。

**处理工作树的边界：**
- 不得 `reset --hard`、`git clean`、整目录覆盖或做无范围的 `restore`；
- 上线前备份源码和工作树改动；
- 绝不覆盖 `错题/`、Ledger、环境配置和 systemd 文件。

## 3. 分期状态

| 期 | 版本 | 状态 | 要点 |
|---|---|---|---|
| P0 | v1.19.1 | 已完成；生产现运行 v1.25.4 | token、对比度、门禁、fixture、截图对比 |
| P2 | v1.20.0 | 交付；用户验收通过 | 23 个 ui 组件、gallery、统一 toast 与 `<dialog>`、`@layer` 分层 |
| P1 | v1.21.0 | 交付；用户验收通过 | core 底座、hash 路由、外壳重排、`/assets/` 304 |
| DP4 + P3 | v1.22.0 | 交付，未部署 | 顶栏瘦身；即时练习迁到 `features/instant/`；`domain/` 四个适配器 |
| P4 | v1.23.0 | 交付，未部署 | 反馈录入迁到 `features/feedback/`；`domain/sessions.js`；全站 `ui/dialog` 标题栏修复 |
| P5 | v1.24.0 → v1.24.2 | **完成（4 轮）** | 第 1 轮：`domain/question/`、容器查询根治、超宽公式、计划文件夹入库。第 2 轮：题目库迁到 `features/questions/`、`domain/question/ops.js`、全局 Esc 统一进 core/keys、删 `qtable.js` 与约 170 条旧题库 CSS。第 3 轮（v1.24.1）：题目弹窗 `modal.js` 与 Markdown 编辑器 `editor.js` 换 `ui/dialog`、`ui/overlay` 客人浮层、焦点回到行。第 4 轮（v1.24.2）：`domain/labels/`（芯片不写 `style=`、预设色进 tokens、选择器与管理的数据部分）、qview 外观全部搬进 `qview.css` 并 token 化（题面 16px 阅读正文）。日志 `AI/logs/2026-09-25_frontend-rearch-p5.md` |
| P6 | v1.25.0 → v1.25.13、v1.26.6 | **完成** | v1.26.6：收件箱前端数据归 `features/create/inbox-store.js`，框选收尾、题卡、AI 训练工作区原生，删 `inbox.js`、`legacy-inbox.js`、`populateCreateLists` 与 `styles.css` 收件箱整段（U19）。v1.25.13：收件箱网格、手机上传页接入 tokens。v1.25.12：快速录入。v1.25.11：上传入口。v1.25.10：录入页外壳。v1.25.9：补 CCW 差异。v1.25.8：设置。v1.25.7：报告。v1.25.6：目录。v1.25.5：历史记录。v1.25.4：全题库导出。v1.25.3：安排复习。v1.25.2：复习调度。v1.25.1：数据复盘。v1.25.0：`domain/data.js` 与仪表盘。日志 `AI/logs/2026-09-25_frontend-rearch-p6.md`、`AI/logs/2026-09-27_frontend-rearch-p6-create.md` |
| P7 | v1.26.0 → v1.26.5 | **完成（6 轮），已与 P6 合并（v1.26.5）** | 第 6 轮（v1.26.5）：列表 / 画廊、检查器原生（`view.js` / `state.js`，整页 morph，只有舞台 iframe 与画廊题面挂载点 skip）；板详情所有者 `features/board/detail.js`（I/O 注入，真实 I/O 与单例在 `runtime.js`）；domain 经端口 `domain/board/detail-port.js`（删 `legacy.js`）；「添加题目」换 `ui/dialog`（`add.js`，修 Esc）；删 `board.js` 与 `styles.css` 139 行；node +13、`board.py` 22 → 35。第 1–5 轮见 §5c。日志 `AI/logs/2026-09-27_frontend-rearch-p7.md` |
| P8 | v1.26.6 | 已完成 | 旧脚本、过渡桥、旧样式和 UI 基线删除；模块化入口与零容忍门禁 |
| 终检 / 部署 | v1.26.6 | 已完成，生产已重启 | 全量门禁与浏览器主路径通过；部署记录见 `AI/logs/2026-09-28_frontend-rearch-p8-final.md` |

## 4. 门禁计数（v1.26.6，沙箱实测）

2026-09-27 P6 收尾后在对话沙箱里实跑下表（Python 3.12、Node 22、Playwright Chromium 141 独立启动，无 CDP），本机 worktree 待 Codex 复核。与 v1.26.5 合并后的计数相比：node +12（`create-inbox`）、`create.py` 42 → 80、`ui_bridge.py` 15 → 14（删去已不存在的 `ibToast` 一项）、`check_ui` 存量下降；其余不变。

| 命令 | 预期 |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 160 OK |
| `node --test tests/*.js tests/app/*.test.mjs` | 330 / 330 |
| `python3 tests/app/run_browser.py` | 34 / 34 |
| `python3 tests/e2e/shell_router.py` | 20 / 20 |
| `python3 tests/e2e/ui_bridge.py` | 14 / 14 |
| `python3 tests/e2e/instant.py` | 23 / 23（「标记筛选」偶发 22，重跑即过）|
| `python3 tests/e2e/feedback.py` | 31 / 31 |
| `python3 tests/e2e/questions.py` | 92 / 92 |
| `python3 tests/e2e/board_picker.py` | 31 / 31 |
| `python3 tests/e2e/board.py` | 35 / 35（v1.26.5 合并后沙箱里 4 次有 1 次「离开展示板页：待保存的版面改动立即落盘」读到 0.5，重跑即过，见 §8；本轮一次全过）|
| `python3 tests/e2e/dashboard.py` | 26 / 26 |
| `python3 tests/e2e/data.py` | 21 / 21 |
| `python3 tests/e2e/schedule.py` | 45 / 45 |
| `python3 tests/e2e/history.py` | 23 / 23 |
| `python3 tests/e2e/catalog.py` | 26 / 26 |
| `python3 tests/e2e/reports.py` | 24 / 24 |
| `python3 tests/e2e/settings.py` | 50 / 50 |
| `python3 tests/e2e/create.py` | 80 / 80（上传与网格、框选、题卡、AI 训练、快速录入主路径，五个工作区各四种审计）|
| `node --test tests/app/create.test.mjs tests/app/create-process.test.mjs tests/app/create-inbox.test.mjs` | 5 / 5、3 / 3、12 / 12 |
| `python3 -m unittest tests.smoke_schedule_workbench` | OK |
| `python3 -m unittest tests.smoke_board_integrity tests.smoke_board_print tests.smoke_board_print_geometry` | 15 项，1 项失败：`smoke_board_print` 的 `test_full_then_incremental_print`（v1.26.5 合并时实测，本轮未改展示板与导出，未重跑；§8）|
| `python3 -B tests/smoke_board_lock.py` | 退出码 0（v1.26.5 合并时实测，本轮未重跑）|
| `python3 tests/check_ui.py` | 0 处问题；存量 handlers 4、html_assign 11、inline_style 11、color_literals 37、font_size_literals 74（`--update-baseline` 重算，只降不升）|
| `python3 tests/check_contrast.py` | 58 组，0 不达标 |
| `python3 tests/check_docs.py --diff <合并完整包基线>` | 35 个文档，0 处问题、2 条既有篇幅提醒（`AI/api.md`、`exec-2026-09-26-codex.md`）|

## 5. P5 任务书：题库与共享题目视图

原计划 §6 P5：`domain/question/`（Markdown 和 KaTeX 渲染按内容哈希缓存，qview 与记录模块迁入）；`features/questions/`（表格和画廊双视图、筛选抽屉、批量条、列设置、视图预设；窄屏降级为卡片列表 D4）；`domain/labels/`。验收：题库相关 Node 测试迁移后全绿；E2E（筛选 → 切换视图 → 打开详情 → 翻页 → 打标记 → 批量）；过渡桥为 feedback 和 export 保留的 qview 调用逐条登记。

P5 已在 v1.24.0–v1.24.2 四轮完成（第 1 轮 `domain/question/`；第 2 轮题目库迁到 `features/questions/`；第 3 轮题目弹窗与 Markdown 编辑器换 `ui/dialog`、旧浮层进顶层；第 4 轮 `domain/labels/` 与 qview 样式归位）。唯一没做的可选项「标记管理换 `ui/dialog`」移到 P6 或 P8（§8）。各轮开工条目已删去（P7 第 4 轮整理，本文件回到 40KB 以下）；做法与结论在 `AI/changelog.md` v1.24.0–v1.24.2 与本机任务日志 `AI/logs/2026-09-25_frontend-rearch-p5.md`。

## 5b. P6 任务书：其余中小页面 + 数据所有权

第 1–5 轮（v1.25.0–v1.25.4，CCW，补丁 `p6r1`…`p6r5`）已完成：`domain/data.js` 与仪表盘、数据复盘、复习调度（含 `SESSIONS` 所有权）、安排复习、全题库导出。开工条目在 U19 收尾时压成这一段；做法与结论在 `AI/changelog.md` v1.25.0–v1.25.4 与本机任务日志 `AI/logs/2026-09-25_frontend-rearch-p6.md`。

P6 剩余（v1.25.5–v1.25.13 由 Codex · 完整执行；最后一段 v1.26.6 由 Claude 在对话里完成，U19）：

- [x] 历史记录（`history.js` → `features/history/`；`domain/history.js` 的转调换成真实现，仪表盘最近动态仍同步更新）。反馈与 Session 撤销 / 恢复、状态还原、时区和四种视觉审计由 `tests/e2e/history.py` 覆盖；v1.25.5。
- [x] 目录（`catalog.js` → `features/catalog/`）：目录树、搜索、全部文件、开题、复制、后备树与扫描后重读均迁移；v1.25.6。
- [x] 报告（`reports.js` → `features/reports/`）：文件拖入 / 选择、带图材料下载、沙箱预览与删除确认；v1.25.7。
- [x] 设置（`assets/app/main.js` 设置段 → `features/settings/`）；v1.25.8。
- [x] 录入题目外壳与导航（`features/create/`）；本轮先保留旧工作区供分步迁移；v1.25.10。
- [x] 原生上传入口（`features/create/upload.js`）：多图拖放 / 选择 / 粘贴、错误提示与旧列表刷新；v1.25.11。
- [x] 快速录入（`features/create/quick.js`）：分区图片、AI 识别与提取、创建后保留上下文；v1.25.12。
- [x] 收件箱网格（`features/create/grid.js`）：筛选、全选、批量操作、框位预览与关联题目入口；v1.25.13。
- [x] 手机上传页加载 tokens / base 样式，390px 浅 / 深截图与上传主路径在隔离实例验证；v1.25.13。
- [x] 截图脚本的「复习调度 44 处行内样式」已修：`shoot()` 截图后 `<input>` 留下空 `style=""`，现只计非空属性值，并排除 `.katex` 内部。`--audit-only` 对复习调度和题库页各四种主题 / 尺寸组合的行内样式计数均为 0；详见 p6 日志「本机接手」。
- [x] 框选工作区收尾（Codex 在制的 `process*.js` 接上新数据所有者，删 `legacy-inbox.js`）、题卡工作区（`cards*.js`）、AI 训练与策略工作区（`train*.js`）；收件箱前端数据 `inbox-store.js`，删 `assets/inbox.js`；v1.26.6。`create.py` 80、`create-inbox` 12，日志 `AI/logs/2026-09-27_frontend-rearch-p6-create.md`。
- P6 收尾核对（执行说明 §2.8）：每页一个 E2E（dashboard、data、schedule、history、catalog、reports、settings、create 均在）；各页四种审计在各自 E2E 里；`legacy-pages.js` 登记表为空。§2 指标的全站核对留给终检。

## 5c. P7 任务书：展示板（CCW · 受限，按轮推进，U16）

顺序照 `plan.md` §6 P7：先纯函数与测试，再拆五个子模块，最后迁 UI。每轮一个补丁、升一个补丁号，旧代码经 `installBoardBridge` 调新模块，每轮结束页面都能用。预计 6 轮，第 7 步的 UI 量大时再拆一轮（最多 7 轮）。

| 轮 | 步骤 | 版本 | 状态 |
|---|---|---|---|
| 1 | 第 1 步：纯函数与测试（`features/board/model.js`、`domain/board/model.js`，4 份旧 node 测试迁入） | v1.26.0 | 完成 |
| 2 | 第 2 步保存队列 + 第 3 步打印协调（含「仅补印新增」、打印任务与纸面记录、预览控制器进模块） | v1.26.1 | 完成 |
| 3 | 第 4 步拖拽排序（含键盘排序、拖拽中 Esc）+ 第 5 步版面设置（检查器字段写入、锁定确认） | v1.26.2 | 完成 |
| 4 | 第 6 步选板浮层原生（`domain/board/`，叠在对话框上按 `hostGuest` 挂；键盘进 `core/keys.js`） | v1.26.3 | 完成 |
| 5 | 第 7 步前半：页面契约 `features/board/index.js`、从 `legacy-pages.js` 删 board；状态条、板列表、舞台（预览 iframe `data-morph="skip"`，消息带 `previewToken`） | v1.26.4 | 完成 |
| 6 | 第 7 步后半：检查器、列表 / 画廊；删 `board.js` / `board_picker.js` / `board_preview.js` 与 `styles.css` 的 `.bd-*`；`tests/e2e/board.py`（建板 → 加题 → 排序 → 版面设置 → 打印预览 → 仅补印新增，四项审计）；截图对比 | v1.26.5 | 完成 |

第 1–5 轮（v1.26.0–v1.26.4）的已完成清单在 P7 第 6 轮整理时压成这一段：纯函数进 `features/board/model.js` 与 `domain/board/model.js`；保存队列 `save.js`、打印协调 `print.js`、常驻预览 `preview.js`；拖拽 `drag.js`、版面设置 `settings.js`；选板浮层 `domain/board/picker.js`（`core/keys` 浮层键盘层）；页面契约 `features/board/index.js`（状态条、左栏树、舞台头）与板列表数据所有者 `domain/board/boards.js`。做法与验证在任务日志与 `AI/changelog.md` v1.26.0–v1.26.4。

第 6 轮（已完成，v1.26.5，增量补丁 `changes-2026-09-27-p7r6.patch` 与累计 `changes-2026-09-27-p7-r1-r6.patch`）：

- [x] 板详情所有者 `features/board/detail.js`（`createBoardDetail(deps)`，I/O 全部注入）；真实 I/O、单例、窗口级监听在 `runtime.js`；domain 经端口 `domain/board/detail-port.js`（依赖倒置，删 `legacy.js`）
- [x] 列表 / 画廊、检查器原生（`view.js` 模板、`state.js` 视图模型、`board.css`）；整页 morph，删掉为保焦点写的局部刷新，锁定确认被拒时先放焦点；拖拽改为挂载时绑一次（修重复绑定）
- [x] 「添加题目」`ui/dialog`（`add.js`，修 Esc，删 `AI/optimization.md` 那一条）；「按标记同步」token 样式
- [x] 删 `assets/board.js` 与 `<script>`、`styles.css` 139 行；过渡桥只挂旧调用方与冒烟测试要用的入口并逐条登记；冒烟测试改用 `configureBoardDetail` / `boardSetPrintMode`，`BOARD_DETAIL` 只读访问器
- [x] `board-locked.test.mjs` 改测 `createBoardDetail`（+5）、`board-regions` 改查新模板、`board-page` +8、`tests/e2e/board.py` 35；截图对比；版本、文档、日志、本文件

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

- `tests/smoke_board_print.py` 的 `test_full_then_incremental_print` 在 CCW 沙箱里失败（P7 第 1、2 轮都复测过，结果相同）（仅补印新增的第一页不是占位页），导出包基线上同样失败、报错相同，P7 第 1 轮没有改导出模板与后端。Codex 在本机跑一次：本机也失败就在 `AI/optimization.md` 记一条 `[ ]`（导出模板范围，不在 P7 内修）；本机通过就只在此记为沙箱环境差异。2026-09-27 对话内合并后在沙箱复测：合并结果与祖先导出包都失败、断言内容相同（第 3 页 overflow −853），与合并无关，仍待本机复核。
- `tests/e2e/board.py` 的「离开展示板页：待保存的版面改动立即落盘」在合并后的第一次全量运行里失败过 1 次（服务端仍是 0.5），随后单独重跑 3 次、纯 P7 跑 4 次都通过。合并没有改展示板、保存队列与切页卸载的代码（仪表盘只多订阅一个 `history:changed`），按偶发处理；本机再出现就查「拖放进文件夹 → 改版式 → 立即切页」之间板详情是否正在重读。
- 剩余 document 级 keydown（按 `document.addEventListener('keydown'` 计）只剩 `app.js`（closeDrawer）：`inbox.js` 的已在 P6 录入页迁移时并进 `features/create/index.js` 的页面快捷键，展示板的在 P7 第 5 轮迁进 `core/keys`、`board.js` 第 6 轮已删。选板浮层 P7 第 4 轮起走 `core/keys` 浮层层（document 冒泡阶段），所以浮层开着时 `app.js` 的 Esc 仍会关抽屉，影响很小，P8 删 `app.js` 时一并消失。
- 芯片本身的外观（`.lbl` 的形状、淡底、深色，字号 9.6px）仍在旧 `styles.css`，P8 随 styles.css 一起搬（展示板 E2E 审计的字号项因此不计 `.lbl`）；`assets/questions.js` 的 `masteryBarHtml` P7 第 6 轮起无调用方，P8 随文件删除；标记管理仍是旧 `.modal-overlay#label-manager`（叠在对话框上时登记为客人），P6 或 P8 换 `ui/dialog` 后删客人登记里的这一项。

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
| 2026-09-27 | P6 最后一段（录入页框选收尾、题卡、AI 训练）改在对话里由 Claude 按受限模式做完，取代执行说明阶段 2.6 第 2–4 步由 Codex 本机执行；Codex 只把补丁作为一个提交落地并补做本机验收。版本 v1.26.6（在 v1.26.5 上加 0.0.1）| U19 |
| 2026-09-27 | P6 在制与 P7 的合并改在对话里做，取代 P7 日志「合入」一节由 Codex 自行 `git apply --3way` 并按轮拆提交的做法：交付合并后的完整包与相对 P6 导出包的合并补丁，Codex 作为一个合并提交应用、补做本机验收；版本按下面 U16 一行的规则取两者较大的 v1.26.5（工作区 v1.25.13 低于补丁版本，不另加 0.0.1），此后各页从 v1.26.6 起 | U18 |
| 2026-09-27 | P7 各轮不逐轮合入，在上一轮完整包上继续；每轮交相对导出包的累计补丁，P7 完成后 Codex 一次合入、按轮拆提交（版本号规则不变） | U17 |
| 2026-09-27 | P7 不等 P6 剩余，改由 CCW · 受限按轮推进（预计 6 轮，§5c），每轮交补丁、完整包与日志，由 Codex 合入；Codex 继续 P6 剩余、P8、终检，跳过执行说明阶段 3。版本号：P7 各轮用 v1.26.x；合入时若工作区版本已不低于补丁版本，就在当前最大版本上加 0.0.1 并同步 changelog 标题，此后各页一律在当前最大版本上加 0.0.1 | U16 |
| 2026-09-26 | P6 剩余到终检的执行者改为 Codex · 完整：每页一个本机提交，取消补丁、完整包、UPGRADE、交接清单与合并版 UPGRADE；终检由 Codex 做；部署执行者由用户指定（默认 Hermes）；执行说明 `exec-2026-09-26-codex.md`；删除重复的 `AI/rearch-plan.md`，其中仍有效的事实并入 §2 | U15；2026-09-26 导出包核对（本机已合并到 v1.25.4）|
