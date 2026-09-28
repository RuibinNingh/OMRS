# 2026-09-28 展示板 UI 打磨：详情可滚动、打开题目入口、左栏对齐、纸面自动适配

## 背景

用户原话：「Plan 里面有关于展示板 UI 重构的，但是 Codex 完成度不高，UI 很粗糙；列表左侧留了一堆空不知道干啥；点击题目后右侧的设计不好，太大了，也不能滚动；还有，如果可以加一个打开题目功能，在右侧，直接能看到面板；按照原本的目标 html 创新设计。」追问后确认：「打开题目」就是弹窗。

所属计划：`AI/plans/board-redesign/`（目标稿 `target.html`）。运行模式：CCW 受限模式——源码来自上传的 `OMRS-source-sanitized-20260928T061213Z.zip`，不是 Git 仓库；解压后 `git init` 建基线提交 `be7f208`。环境：Python 3.12、Node 22、Chromium 141 可用，`rg` 不可用。

## 行为变化

- **详情层能滚动了。** 旧 `board.css` 里 `.content.is-workbench .brd-ins { position: static }` 的优先级高于新样式的 `position:absolute; inset:0`，详情层撑满内容高度又被外层 `overflow:hidden` 裁掉，底部按钮也看不见。现在两层都是「固定头 + 独立滚动的正文 + 固定脚」。
- **详情收紧一档。** 标题 `--text-lg`；元信息一行（分类 / 难度 / 熟练度）；留白步进与 0/2/4/6/8 预设同一行；题面用 qview 窄栏档（界面字号、不重复「题目」标签），答案与错因先折叠在「显示答案与错因」后，展开按题记在 `state.revealUid`，切题即收起，展开后标题旁有「收起答案」；练习记录改为战绩带 + 一句话摘要（`recordSummaryView`），完整记录留给弹窗。
- **「打开题目」放到详情导航条上**（带文字的按钮，进详情即可见），打开共享题目弹窗 `viewQ`；Enter 与双击题目行同效。详情脚改为「在纸上找到」「移出」。
- **左栏去掉缩进与竖线。** 最左 20px 结构列放文件夹折叠箭头和当前板指示条；文件夹图标、「未归档」、板名从同一条线起排。空文件夹显示可放置的虚线提示；板行第二行只留题数 / 已印页数 / 未印等状态，更新时间移进悬停提示，不再把「5 题未印」截成省略号。宽屏可收起左栏，板头出现打开按钮；窄屏抽屉加了遮罩，点遮罩可关。
- **「适应宽度」真正生效并跟随容器。** 原先默认显示「适应宽度」但缩放一直是 1，纸面右侧被切。现在 `ResizeObserver` 观察舞台，首次挂载、改窗口、收起左栏时自动重算（一帧一次），两侧各留约 32px 桌面，上限 1.25。
- **窄于 A4 时纸面居中。** 模板缩放改为以左上角为原点、舞台宽度放到 `100% / scale`；原来以中心缩放，视口比纸窄时整体偏右约 (793.7 − 视口宽) / 2。内嵌预览上边距改为 24px 的桌面留白。独立导出件与打印不受影响（它们不发缩放）。
- 同步条、列表脚提示文案缩短，不再折成两行；工具条页码框收窄，只在悬停 / 聚焦时显示边框。

## 影响文件

- `assets/app/features/board/view.js`（M）：只保留工作台——左栏树、板头、确认条、纸面工具条与浮层；浮层宿主移进纸面列，版式浮层贴右、纸面记录浮层贴左。
- `assets/app/features/board/view-panel.js`（A）：题目列表、详情层、留白卡、记录摘要从 `view.js` 拆出（两文件都在 400 行内）。
- `assets/app/features/board/index.js`（M）：详情水合改为按「题 + 是否显示答案」挂载，另挂记录摘要；`reveal` 动作；宽窄屏区分的 `toggleBoards`；`ResizeObserver` 自动适配；删去视图里已不存在的 `focusGap` / `inspectLocate` / `gapLive` / `gapSet` 及其辅助函数。
- `assets/app/features/board/state.js`（M）：`listHidden`、`revealUid` 状态；板行状态去掉时间、`treeView` 另给 `time`；`gapReadout` 给 `cm`；详情 `metaBits`、已印说明带页码；新增 `recordSummaryView`。
- `assets/app/features/board/preview.js`（M）：适配公式改为 `(宽 − 64) / 793.7`，上限 1.25。
- 样式：`board.css`（M，重写为外框 / 板头 / 纸面列 / 共享小件 / 响应式）、`board-tree.css`（A）、`board-panel.css`（A，接替 `board-list.css` 并重写）、`board-popovers.css`（M）、`board-dialogs.css`（A，加题 / 同步 / 删文件夹，规则原样从旧 `board.css` 搬出）、`board-layout.css`、`board-list.css`（D）；`assets/app/styles/index.css`（M）更新引入。旧文件里互相覆盖的画廊、旧检查器、`.brd-layout` 等死规则一并删除。
- `omrs/export_templates/board.js`、`omrs/export_templates/board.css`（M）：缩放原点与内嵌上边距，见上。
- 测试：`tests/app/board-regions.test.mjs`（M，源码断言读 `view.js + view-panel.js`）、`tests/app/board-preview.test.mjs`（M，适配公式期望值 1.23 → 1.18）、`tests/e2e/board.py`（M，新增两项：详情滚动 / 脚常驻 / 答案折叠 / 打开弹窗；宽屏收起左栏后缩放变大并能展开）。
- 文档：`AI/frontend/board-ui.md`、`AI/board.md`、`AI/export.md`、`AI/frontend/design-system.md`、`AI/frontend/architecture.md`（展示板测试分层）、`AI/plans/board-redesign/plan.md`、`AI/plans/board-redesign/progress.md`（M）。

## 验证

已实际执行（隔离实例，fixture Vault `/tmp/fx/full`，端口 18471，另建 1 个文件夹 + 2 块板 + 1 个空文件夹看树形）：

- `node --test tests/app/*.test.mjs`：326/326（全部改动完成后重跑；其中展示板子集 `tests/app/board*.test.mjs` 120/120）。
- `python3 -m unittest discover -s tests -p 'test_*.py' -q`：182/182。
- `python3 tests/app/run_browser.py`：32/32。
- `python3 tests/e2e/board.py`：25/25（原 23 项 + 新增 2 项）；`python3 tests/e2e/board_picker.py`：31/31。
- `python3 tests/check_ui.py`：0 处问题；`python3 tests/check_contrast.py`：58/58。
- `python3 tests/visual/run.py --ref be7f208`：48 张中仅展示板四档有预期差异（桌面 14.1% / 16.6%，手机 22.0% / 24.5%）；页面脚本错误 0；展示板小目标 0、行内样式 0、整页横向溢出 0，手机档局部横向溢出由 1 降为 0。
- 手工截图：1440 深 / 浅、1280×700（长题目详情 scrollHeight 739 > clientHeight 531，可滚到底）、390 手机与抽屉；「打开题目」弹出题目弹窗、Esc 关闭。

未执行：`tests/smoke_board_print.py`（真实打印对话框，无头环境不适用）；物理打印机实物验收。

## 合入（仅受限模式交付）

- 补丁基线：导出包 `OMRS-source-sanitized-20260928T061213Z`。
- 应用：在仓库根执行 `git apply --3way changes-2026-09-28-board-ui-polish.patch`（补丁删除 `board-layout.css`、`board-list.css`，新增 `board-panel.css`、`board-tree.css`、`board-dialogs.css`、`view-panel.js`）。
- 门禁与预期计数：`node --test tests/app/*.test.mjs` 326/326；unittest 182/182；`tests/app/run_browser.py` 32/32；`tests/e2e/board.py` 25/25；`tests/e2e/board_picker.py` 31/31；`check_ui` 0；`check_contrast` 58/58；`check_docs.py --diff <合入前 HEAD>` 退出码 0。
- 完整模式补做：
  1. 运行 `python3 tests/check_docs.py --write-log-index`，验收：`AI/logs/log.md` 收录本日志且 `check_docs.py` 无「索引不同步」。
  2. 用真实 Vault 打开展示板页各点一遍：长题目详情能滚到底；「打开题目」弹出题目弹窗；窗口从宽拖窄时纸面始终居中且不被切。

## 完整模式合入（2026-09-28）

用户要求将展示板 UI 重构合并到当前工作区，同时另一智能体正在处理 AI 功能，因此只合入本日志列出的展示板页面、导出模板、测试与对应文档。收到的是完整源码 zip，没有独立补丁；以合入前 Git `HEAD` 和工作区为基线，逐项对比后生成限定 26 条路径的补丁，`git apply --check` 通过再应用。包内的 AI 计划、`AI/plans/README.md` 和导出清单未合入；已有未跟踪的 `.playwright-mcp/` 保留。

已实际执行：展示板 Node 120/120、全仓 Node 326/326、Python unittest 182/182、组件浏览器 32/32、展示板 E2E 25/25、选板 E2E 复跑 31/31、UI 纪律 0 处问题、对比度 58/58。选板 E2E 首次为 30/31：Enter 加入后服务端断言未即时观察到题目，复跑为 31/31；未修改选板代码。`tests/visual/run.py --ref ae471fc --pages board` 的四档截图均有预期 UI 差异（浅/深桌面 13.234% / 15.786%，浅/深手机 20.962% / 23.437%），页面脚本错误 0，小目标 0，行内样式 0，整页横向溢出 0，手机档局部横向溢出由 1 降为 0。

文档收尾：`python3 tests/check_docs.py --write-log-index` 已生成索引；`python3 tests/check_docs.py --diff HEAD` 检查 45 个文档、0 处问题，另有 2 条原有文件体积提醒。

未执行：物理打印机实物验收；真实 Vault 手工走查（按仓库测试实例规则，只使用临时 Vault）。
