# 2026-09-27 前端重构 P6 收尾：录入页框选、题卡、AI 训练工作区原生（v1.26.6）

## 背景

- 用户原话：「执行没有完成的P6」；随后两次「继续」。记为 progress §1 的 U19。
- 所属计划：`AI/plans/frontend-rearch/`，对应执行说明 `exec-2026-09-26-codex.md` 阶段 2.6 的第 2–4 步（框选、卡片、训练与策略）与 2.8（P6 收尾）。
- 执行者与环境：Claude（claude.ai 对话沙箱），按受限模式执行（源码来自上传包、工作目录不是 Git 仓库，`AGENTS.md`「模式判定」）。Python 3.12.3、Node 22.22.2、git 2.43.0、Playwright Chromium 141（独立启动，无 CDP）；无网络；没有 `AI/logs/log.md`。
- 基线：合并完整包 `OMRS-source-merged-p6wip-p7r6-v1_26_5.zip`（v1.26.5，即任务日志 `2026-09-27_frontend-rearch-p6-p7-merge.md` 的产物），解压后 `git init` 原样提交。开工前在基线上实跑 `tests/e2e/create.py`：42 / 42。

## 盘点（旧 `assets/inbox.js`，539 行）

- 全局状态 `IB`（图片列表、勾选、题卡勾选、当前图、画框角色与题卡、选中框、上一张、图片缓存、保存计时器 / 补丁 / 串行链 / 修订号、轮询）。
- 函数分四组：入口与阶段（`inboxInit`、`ibLoad`、`ibGo`、`ibCounts`、`ibToast`）；处理区（`ibOpen`、`ibStep`、`ibSetDrawRole`、`ibAfterEdit`、`ibSaveSoon` / `ibSave` / `ibFlushSaves`、`ibSetLayout`、区域增删与保存方式、`ibApplyLast` / `ibTransferBoxes`、`ibWholeImage`、`ibAddCard`、`ibDiscardCurrent`、`ibMarkReady`）；AI 任务（`ibJob`、`ibStrips`、`ibDetect*`、`ibExtractRegions` / `ibExtractAll`、`ibClassify*`、`ibCrop`）；题卡与训练（`ibReadyCards`、`ibRenderCards`、`ibCardField`、`ibOpenCardLabels`、`ibCommit` / `ibCommitSelected`、`ibBackToProcess`、`ibLoadStats`、`ibExportDataset`、`ibLoadPolicy` / `ibSavePolicy` / `ibPolicyToggle`、`ibCleanup`）。
- 事件：`#panel-create` 上的 click / change / input 委托（`data-ib-*`）、`window` resize、`MutationObserver` 补画裁图、`inbox:reload` 订阅；HTML 里题卡与训练两块有 `onclick` / `onchange` 与行内样式。适配器 `window.__omrsInbox` 供 `features/create/legacy-inbox.js` 使用。
- 外部引用（`grep assets/ omrs_dashboard.html tests/`）：只有 `features/create/index.js`（`inboxInit`、`__omrsInbox.flush`）与 `legacy-inbox.js`；`core.js` 的 `populateCreateLists` 只为题卡的三个 datalist 服务（`app.js` 的 `legacyDataRefresh` 调用它）。没有测试载入 `inbox.js`。
- 在制代码（Codex 未提交、随 v1.26.5 合并保留）：`process-view.js`、`process-canvas.js`、`process-content.js`、`process-state.js`、`process.css` 已是新写法，但数据、保存、AI 任务与区域面板的点击仍经 `legacy-inbox.js` 调旧函数。

## 行为变化

- 录入页五个工作区全部运行在 `assets/app/features/create/`；旧 `inbox.js`、`legacy-inbox.js`、`populateCreateLists` 与三个全局 datalist 删除。功能与文案保持不变，以下是可见差异：
- 题卡：模板不写行内样式与行内事件，🤖 换成图标；没有就绪题卡时给空态与「去处理」；两个批量按钮在没有勾选时禁用，勾选数显示在「AI 识别」按钮上；创建期间按钮置忙；创建成功后除统计外也刷新历史与目录（与快速录入一致）；创建前先写出未到防抖时间的题卡字段，避免提交后迟到的保存去改已录入的图片（服务端会拒绝并弹「保存失败」）。
- AI 训练：条形改为原生 `<progress>`；导出改为随格式变化的下载链接；策略表单换 `ui/field` / `ui/select` / `ui/switch`，本地检测地址按提供方显隐；保存结果就地显示；统计或策略读取失败时在原位给原因与「重试」（原来只弹提示）；清空裁图缓存的确认改为危险样式。
- 处理：多题卡时「在此题卡画框」由链接改为按钮；保留图片的裁图预览只在框位变化时重画；拖框期间收到保存响应不再替换正在拖的图片对象（原来会让手势改到脱离列表的旧区域上）；重读收件箱时清掉已不存在的勾选与当前图。
- 导航：选中态由内阴影改为 outline（`check_ui` R4）；副标题 11.2px → 12px（token 化）。

## 新结构

| 文件 | 职责 |
|---|---|
| `inbox-store.js` | `createInboxStore({ api, emit, notify, timers })`：状态、读取、保存队列、任务轮询、切工作区、切图；node 可测 |
| `inbox.js` | 单例（`core/api`、`ui/toast`），`connectInbox(bus)`；`notify` 保持旧 `ibToast` 的停留时长 |
| `inbox-ops.js` | AI / 模板框选、沿用框位、整图、文本提取、题卡分类识别、框选汇总文案 |
| `crop.js` | 原图缓存、裁图（大 PNG 改 JPEG）、预览尺寸、框位键、`paintCrops` |
| `process.js` | 处理区控制器：本张图的全部编辑、快捷键 |
| `cards-state.js` / `cards-view.js` / `cards.js` / `cards.css` | 题卡工作区 |
| `train-state.js` / `train-view.js` / `train.js` / `train.css` | AI 训练工作区 |
| `index.js` | 页面契约：挂载、工作区显隐、计数、全部 `create.*` 动作与快捷键 |

## 影响文件

- 新增：上表中的 `inbox-store.js`、`inbox.js`、`inbox-ops.js`、`crop.js`、`cards-*`、`train-*`、`tests/app/create-inbox.test.mjs`、本日志。
- 删除：`assets/inbox.js`、`assets/app/features/create/legacy-inbox.js`。
- 修改：`AI/routes.md`（`--write-routes` 生成）、`AI/frontend/design-system.md`（features 层样式清单）、`assets/app/gallery-sections-2.js`（toast 说明）、`tests/e2e/ui_bridge.py`；`features/create/` 的 `index.js`、`process.js`、`process-content.js`、`grid.js`、`quick.js`（datalist 选项改用 `cards-state.js` 的 `suggestions`）、`state.js`、`view.js`、`create.css`；`assets/app/styles/index.css`；`assets/app/main.js`（调用方注释）；`assets/app/domain/items.js`、`assets/app/main.js`、`assets/app/styles/index.css`；`omrs_dashboard.html`（挂载点、去掉 `<script>` 与 datalist、缓存参数 `20260927-p6-create-cards`、侧栏版本）；`omrs/version.py`、`README.md`、`AI/README.md`、`AI/changelog.md`；`AI/frontend/create.md`、`AI/inbox.md`、`AI/frontend/architecture.md`、`AI/frontend/components.md`；`AI/plans/frontend-rearch/progress.md`；`tests/e2e/create.py`、UI 基线文件。
- `styles.css` 删除内容：收件箱整段（`--ib-role-*`、`.ib-*` 共 70 行，其中导航与显隐规则 token 化后搬进 `create.css`）、`.lbl-form-add` 两行、`@media(min-width:1161px)` 工作台块（4 条收件箱规则搬进 `create.css`，另有一条前期迁移留下的空注释）。按精确行号删除，删前逐段断言内容，删后 `git diff` 核对。

## 测试迁移

没有旧测试载入 `inbox.js`，没有需要迁移的用例。新增：`tests/app/create-inbox.test.mjs` 12 例；`tests/e2e/create.py` 42 → 80（题卡 18 项：整图、保留图片的裁图、就绪计数、题卡列表与裁图、无行内样式 / 事件、必填预检、字段即时更新与去抖写回、classify 任务载荷、退回处理与字段保留、单张创建与「加入展示板」、图片转已录入、批量就绪与 KaTeX 预览、全选、批量汇总、入库；训练 12 项：统计、无行内样式 / 事件、导出格式、提供方显隐、保存与夹取、返回重读、清理确认、读取失败与重试；审计另加题卡与训练两个工作区各四种组合）。E2E 里需要 AI 的 classify 用 `page.route` 返回固定任务结果；批量就绪的测试数据经 `/api/inbox/item/update` 构造。

## 验证

均在沙箱里对最终改动实跑（数字见下；「偶发」一栏按实际记录）：

- `python3 -m unittest discover -s tests -p 'test_*.py' -q`：160 OK。
- `node --test tests/*.js tests/app/*.test.mjs`：330 / 330（318 + `create-inbox` 12）。
- `python3 tests/check_ui.py`：0 处问题；`--update-baseline` 后存量 handlers 13→4、html_assign 21→11、inline_style 39→11、color_literals 44→37、font_size_literals 96→74。
- `python3 tests/check_contrast.py`：58 组，0 不达标。
- `python3 tests/app/run_browser.py`：34 / 34。
- E2E（全量各跑一次，均通过）：shell_router 20、ui_bridge 14、instant 23、feedback 31、questions 92、board_picker 31、board 35、dashboard 26、data 21、schedule 45、history 23、catalog 26、reports 24、settings 50、create 80。`ui_bridge.py` 原有一项调用旧全局 `ibToast`（随 `inbox.js` 删除），改为只检查排队的早期提示已补发，15 → 14；组件画廊 toast 说明里的 `ibToast` 一并删去。
- 冒烟：`smoke_schedule_workbench` OK。展示板冒烟（`smoke_board_*`）本轮没有重跑：本轮未改展示板、导出与后端，结果沿用 v1.26.5 合并日志。
- `python3 tests/check_docs.py --diff <基线>`：35 个文档，0 处问题，2 条既有篇幅提醒；`--write-routes` 重新生成了 `AI/routes.md`（`/api/inbox/*` 的文档引用随 `AI/frontend/create.md` 变化）。
- `git diff --check` 无空白错误。
- 调试中修掉的问题：题卡难度滑杆被旧全局 `input[type=range]{height:6px}` 压扁（审计报小于可点尺寸）；E2E 构造数据时两张图的区域 id 撞在一起（区域 id 全局唯一，接口返回 400）；Playwright 点击后鼠标停在提示条上，提示条暂停计时一直挡住题卡底部按钮（测试里先把鼠标移开）。
- 未执行：`tests/visual/run.py --ref`（沙箱预算；改动集中在录入页三个工作区，E2E 审计已覆盖字号、目标尺寸、行内样式与溢出），留给本机。

## 合入

- 补丁基线：合并完整包 `OMRS-source-merged-p6wip-p7r6-v1_26_5.zip`（v1.26.5）；该包相对 P6 导出包 `20260927T125544Z` 的差异就是合并补丁 `changes-2026-09-27-p6wip-p7-merge.patch`。
- 应用：先按 `2026-09-27_frontend-rearch-p6-p7-merge.md`「落地」把合并补丁作为一个提交（若已提交则跳过），再 `git apply --check changes-2026-09-27-p6-create.patch`，通过后 `git apply --3way`。补丁是 `git diff --binary`，含新增、删除，不含 `SOURCE_EXPORT_MANIFEST.txt`。
- 提交：一个提交 `frontend-rearch P6: 录入页框选 / 题卡 / 训练 → features/create（v1.26.6）`，哈希填进 progress 状态块。
- 门禁与预期计数：unittest 160 OK；node 330 / 330；`check_ui` 0 处问题；`check_contrast` 58 组 0 不达标；`run_browser` 34 / 34；E2E 计数同 progress §4（`create.py` 80 / 80）。
- 完整模式补做：`python3 tests/check_docs.py --write-log-index`；`python3 tests/visual/run.py --ref <合并提交>`，录入页的差异按本日志「行为变化」逐项解释；真实浏览器手工走一遍：上传 → 网格整图 → 处理区画框、改保存方式、标记就绪 → 题卡填表、加标记、创建 → 批量创建与「加入展示板」→ AI 训练改策略并保存；有可用模型时各跑一次 AI 框选、提取与题卡识别。验收：页面脚本错误为零，行为与本日志一致。
- 不部署，不重启生产。
