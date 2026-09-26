# 2026-09-25 前端重构 P4：反馈录入迁到 features/feedback

---

## 项目基本信息

| 项 | 值 |
|---|---|
| 项目名 | OMRS（Obsidian Mistake Reconstruction System）|
| 当前版本 | v1.22.0（本任务交付后为 v1.23.0）|
| 类型 | 个人错题本，Markdown + 本地 HTTP 服务 |
| 后端入口 | `omrs_engine.py` |
| 前端文件 | `omrs_dashboard.html`（结构）+ `assets/`（旧脚本与 `styles.css`）+ `assets/app/`（ES Module：core、ui、domain、features、外壳、过渡桥）|
| 数据目录 | 结构化数据在 `错题/.omrs/`；生成的 AI 报告在 `错题/report/` |
| 依赖边界 | 核心 Python 运行路径无强制第三方库；前端无构建依赖；浏览器单测、E2E 与截图需要 playwright + Chromium（可选，缺失时跳过）|

---

## 执行者与模式

- 执行者：Claude（claude.ai 沙箱，等同 CCW）。**受限模式**：源码来自 P3 交付的完整包 `OMRS-v1.22.0-2026-09-25.zip`，无网络、无 systemd、碰不到生产与 Git 远端。
- 基线：解压后 `git init` 提交 `d42adec`（v1.22.0）。开工门禁与交接文档 §3.2 逐项一致：unittest 156、node 162、浏览器 31、shell_router 20、ui_bridge 15、instant 23（首跑 22，重跑 23，计时抖动）、check_ui 0（存量 254 / 183 / 251 / 189 / 383）、对比度 54 / 0、文档 0 + 1 提醒。
- 后端零改动；`/api/feedback` 提交体 `{uid, sub_score, is_correct, note}` 不变。

## 行为变化（用户可见）

- 提交结果改在 `ui/dialog` 弹窗里显示（原 `#fb-result-modal` 删除），状态行留「查看本次结果」可重开。改前空页面上就有一个「查看本次结果」按钮（`hidden` 被 `.btn` 的 display 盖掉），现在只在有结果时出现。
- 三栏在未选 Session 时各给 `ui/empty` 空状态（改前是三块空白卡片，手机上是两条空白横条）；Session 列表读取失败时顶栏给原因。
- 题面按挂载点宽度决定单 / 双栏：桌面三栏里题面约 510px 宽，改前是挤着的双栏，现在单栏；手机同理。整行超宽的公式只在所在段落内横滚。
- 判定后焦点留在按钮上（改前判定面板整块重绘，焦点丢失）；快捷键与即时练习一致。
- 导入报告里的 ⚠ 行单独着警示色；注意事项块正常换行。
- ≤1160 单栏时判定面板排在题面之前（改前也是面板在前；本期初版一度排在题面之后，看改前 / 改后对照图时发现手机上每题都要滚过整个题面才能判定，已改回并在 E2E 里断言）。
- 有意差异：导入反馈 JSON 失败（如全部已录入）时不再顺手切换当前 Session。

## 架构

| 文件 | 说明 |
|---|---|
| `features/feedback/index.js` | 页面契约 + 控制器；动作命名空间与快捷键作用域 `feedback`；挂载期 document `paste` 监听（卸载移除）；进入即刷新 Session 进度，并发刷新共用一个 promise |
| `features/feedback/state.js` | 模块单例 + 纯函数：Session 进度、rail 条目、光标、判定默认分、提交体；OMR / 反馈 JSON 解析器逐字迁移 |
| `features/feedback/importer.js` | 新增：文本 → 导入计划（纯函数），三个导入入口共用，使原冒烟测试的全部断言能在 node 里跑 |
| `features/feedback/view.js` | `html``` 模板；rail key =「行下标 \| 只读题 uid」保证唯一；题面挂载点 `data-morph="skip"`、key `qv:<uid>` |
| `features/feedback/feedback.css` | features 层，类名前缀 `fbw-`；断点 760 / 1160；挂载点作容器查询容器 |
| `domain/sessions.js` | 新适配器：`SESSIONS` / `ACTIVE_FB_SESSION`、`refreshSessions`、题目查找、标记、展示板、剪贴板 |
| `domain/questions.js` | 加 `mountQuestionStage()`（完整题头，工具多「停用」「打开」）|
| `legacy-bridge.js` | `fbSessionProgress` 再导出；`renderFb` / `resetFeedbackForm` / `fbClearResults` 改发 bus |
| `schedule.js` | `feedbackSession` → `router.go` + bus `feedback:session`；`refreshFbSessionPicker` → bus `sessions` |

删除：旧 feedback.js（616 行）、面板旧 HTML 与结果弹窗、`styles.css` 105 条 `.fb-*` / `.result-row` 规则与 3 个随之清空的 `@media` 块（删前确认 39 个类名别处均未使用；唯一的混合选择器只摘本页部分）、`core.js` 里已无人用的 `fbRows`。

## 本期发现并修掉的问题

- `ACTIVE_FB_SESSION` 是 `core.js` 的 `let`，在全局词法环境里而不是 `window` 属性：适配器最初写 `globalThis.ACTIVE_FB_SESSION`，选中 Session 后下拉跳回「手动录入」。改为直接给标识符赋值（已写进 `architecture.md` §5）。
- 旧 `styles.css` 的全局 `header{padding;border-bottom;margin-bottom}` 漏进 `<header>`：本页判定面板标题下多出粗线与空白；**所有 `ui/dialog` 的标题栏自 P2 起都有同样问题**（gallery 不加载旧样式所以没暴露）。`.ui-dialog__head`、`.ui-card__head` 清零 margin / padding / border，`.ui-drawer__head` 清零 margin。影响全站对话框外观（变好），已记入 `components.md` §5。
- `tests/e2e/ui_bridge.py` 的样式分层断言按 `@import` 逐条列层名，第二条 `layer(features)` 使其失败；改为去重后比顺序（每迁一页都会多一条）。
- `tests/smoke_schedule_workbench.py`：基线上就用 `[data-ui-ok]` 找对话框按钮（P2 后是 `data-dialog-ok`），反馈段落从未执行过。更正后部分录入、连续 9 批提交、完成态首次跑通；现停在复习调度页「空推荐提示查看已有计划」，基线打同样补丁后失败在同一处，与本期无关（已记入 `optimization.md`）。
- `assets/board.js:1061` 的 `focus: '[data-ui-ok]'` 同样过时，本期未改（记录）。
- 删旧 CSS 后留下两个只剩注释的 `@media` 块（造成补丁行尾空白告警），已按精确字符串删除。过程中一次用正则批量删「只含注释的块」误删了 `@media(min-width:1161px)` 里的真实规则，未提交即发现并 `git checkout` 还原，重跑全部门禁确认。`styles.css` 里另有一个只剩注释的 `@media(max-width:900px)` 块是 P3 即时练习的遗留，本期未动。

## 改前 / 改后实测（full fixture，同一 Session、同一题、真实浏览器）

| 项 | P3（v1.22.0） | P4（v1.23.0） |
|---|---|---|
| 判错后 KaTeX 节点保留 | 6 / 6 | 6 / 6（v1.10.0 起已做到，本期保持）|
| 判错后按钮仍有焦点 | 否 | 是 |
| 桌面 1440 题面栏数（挂载点约 510px） | 2 | 1 |
| 手机 390 题面栏数 | 2 | 1 |
| 页面自身字号种类（桌面 / 手机） | 7 / 7 | 4 / 3 |
| 最小字号 | 9.72px | 11px / 12px |
| 行内样式元素 | 8 | 0 |

## 验证（本轮实际执行）

| 命令 | 结果 |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 156 OK |
| `node --test tests/*.js tests/app/*.test.mjs` | 171 / 171（删旧 15 个单元，新增 `tests/app/feedback.test.mjs` 24 个）|
| `python3 tests/app/run_browser.py` | 31 / 31 |
| `python3 tests/e2e/shell_router.py` | 20 / 20 |
| `python3 tests/e2e/ui_bridge.py` | 15 / 15（分层断言改为去重比顺序；`ui/dialog` 标题栏修复后重跑）|
| `python3 tests/e2e/instant.py` | 23 / 23（本轮一次 22，「标记筛选」同基线计时抖动；连续重跑两次 23）|
| `python3 tests/e2e/feedback.py`（新） | 31 / 31，连跑 3 次稳定 |
| `python3 tests/check_ui.py` | 0 处问题；存量 handlers 254 → 244、html_assign 183 → 161、inline_style 251 → 215、color_literals 189 → 185、font_size_literals 383 → 355，已 `--update-baseline` |
| `python3 tests/check_contrast.py` | 54 组，0 不达标 |
| `python3 tests/check_docs.py --diff d42adec` | 0 处问题，1 条提醒（`AI/api.md` 53KB，非本期引入）|
| `PYTHONPATH=. python3 tests/smoke_schedule_workbench.py` | 失败于第 235 行（与基线同处，见上）；反馈段落通过 |
| `python3 tests/visual/run.py --ref HEAD` | 48 张中 26 张有差异，页面脚本错误无；解释见下 |

## 截图差异逐项解释（相对 v1.22.0 基线，visual/run.py）

- 反馈录入 4 张：桌面浅 / 深 3.8% / 4.1%、手机浅 / 深 31.9% / 33.3%。即本期改动：三栏空状态、顶栏按钮换 ui 组件（手机上「读剪贴板填写」不再折成两行）、导入面板折叠按钮、判定面板与提交按钮、去掉空页面上多余的「查看本次结果」。手机页面由 844px 变高到 1088px（三块空状态卡）。
- 其余 22 张全在桌面端、各 0.001%–0.003%：像素差分定位在侧栏底部版本号（x 49–54、y 873–881），即 v1.22.0 → v1.23.0。手机端侧栏收起，无此差异。
- 截图只覆盖各页初始状态；导入答题卡、判定、提交结果弹窗的改前 / 改后对照另拍在截图包（改前实例由 `git worktree` 检出基线启动，提交接口用 route 拦截，不写数据）。`ui/dialog` 标题栏修复影响全站对话框，初始状态截图里看不到。

## 交付与交接

- 补丁链：⑥ `changes-2026-09-25-p4.patch`（v1.22.0 → v1.23.0），接在 ①–⑤ 之后。
- 完整包 `OMRS-v1.23.0-2026-09-25.zip`、`UPGRADE-2026-09-25-p4.md`、截图包 `P4-screenshots-2026-09-25.zip`、交接文档 `HANDOFF-frontend-rearch-2026-09-25-p5.md`。
- **部署注意**：本期改了 `tests/smoke_schedule_workbench.py`（反馈段选择器与 `data-dialog-*`），交接文档说 Hermes 本机对旧冒烟测试有未提交的 CDP 适配，合入时可能冲突，两边改动都要保留。
- 未执行 / 不能执行的验证：生产重启、远端与真实手机走查；旧版 Safari；`AI/logs/log.md` 未生成（部署时完整模式运行 `--write-log-index`）。
