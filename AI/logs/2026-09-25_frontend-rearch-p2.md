# 2026-09-25 前端重构 P2：ui 组件库 v1、gallery 与统一 toast / Dialog

---

## 项目基本信息

| 项 | 值 |
|---|---|
| 项目名 | OMRS（Obsidian Mistake Reconstruction System）|
| 当前版本 | v1.20.0 |
| 类型 | 个人错题本，Markdown + 本地 HTTP 服务 |
| 后端入口 | `omrs_engine.py` |
| 前端文件 | `omrs_dashboard.html`（结构）+ `assets/`（旧 `styles.css` 与拆分的 JS）+ `assets/app/`（ES Module：token、ui 组件、过渡桥）|
| 数据目录 | 结构化数据在 `错题/.omrs/`；生成的 AI 报告在 `错题/report/` |
| 依赖边界 | 核心 Python 运行路径无强制第三方库；前端无构建依赖；浏览器单测与截图需要 playwright + Chromium（可选，缺失时跳过）|

---

## 执行者与模式

- 执行者：Claude（claude.ai 沙箱，等同 CCW）。**受限模式**：工作目录不是 git 仓库，源码来自上传的 `OMRS-source-sanitized-20260925T014232Z.zip`；无网络，不能访问 systemd、生产服务与 Git 远端。受限不等于只读：本轮实际改代码、跑门禁、在隔离实例里做了 E2E 与截图。
- 基线：把导出包解压后 `git init` 并提交为 `ba43d45`（仅本机沙箱里的基线，补丁以它为准）。
- 前置：用户确认 P0（v1.19.1）已在生产验收。
- 依据：`HANDOFF-frontend-rearch-2026-09-25.md` 与原计划 `frontend-rearch-plan-2026-09-24.md` 的 §3.2、§4.5、§4.6、§6 P2。

## 关键决定：P1 未执行，P2 先带入它的必需部分

上传的包是 P0 包（`assets/app/` 只有 `styles/tokens.css`），P1 没有做，而 P2 依赖 P1 的 ES 模块、`html```、样式分层与过渡桥。本轮按 P1 的规格只带入 P2 必需的部分：`assets/app/package.json`、`core/html.js`、`core/dom.js`（只有 render / toFragment / toElement，`morph` 仍归 P1）、`main.js`（只装过渡桥）、`legacy-bridge.js`、`styles/index.css` 分层、`tests/app/` 运行器。hash 路由、`init()` 接管、`_serve_asset` 的 ETag、外壳打磨与 DP4 仍归 P1。若另有人并行执行 P1，这几份文件会冲突，合并时以本期实现为底再补 P1 的部分。版本：P2 用 v1.20.0，之后的 P1 顺延为 v1.21.0。

## 行为变化（用户可见）

1. 全站只剩一套 toast、一套对话框。旧 `uiToast` / `uiDialog` / `uiPrompt` / `uiConfirm` 与收件箱 `ibToast` 转调新组件，签名与返回值不变；模块就绪前的调用排队补发。新 toast 右下角堆叠（窄屏底部通栏），最多 3 条、同文同类合并、悬停暂停；对话框用 `<dialog>.showModal()`，自带焦点陷阱、Esc / 遮罩关闭、关闭后焦点回到触发元素、锁定背景滚动，并能叠在旧 `.modal-overlay` 弹层之上（按 Esc 只关上层）；危险确认默认聚焦「取消」。
2. 旧按钮、输入框、下拉统一高度与外观（修 D2、D3）：桌面 32（紧凑 30）/ 小号 28；窄屏（≤760px）三档统一 40，满足移动端可点目标不小于 40px（D9）。题库工具栏同一行由 21 / 28 / 38 / 41 / 43 五种高度变为一档；即时练习页移动端筛选 select 文字不再被裁切；「题数」组合框与同行 select 同高。控件文字由 12.3px 变为 13px。
3. 旧 `.modal` 弹层外壳换成新的遮罩色、圆角、阴影，关闭按钮热区 28px（手机 40px）；层级与尺寸不变。
4. 新增组件陈列页 `/assets/app/gallery.html`（23 个组件 × 全部状态，浅 / 深、舒适 / 紧凑可切换）。
5. 样式入口改为 `tokens.css` + `assets/app/styles/index.css`（`@layer`：vendor < legacy < base < ui < domain < features < utilities < legacy-bridge）。浏览器下限随之为 Chrome 99 / Safari 15.4 / Firefox 97。

## 影响文件

- 新增 `assets/app/`：`package.json`、`main.js`、`legacy-bridge.js`、`core/html.js`、`core/dom.js`、`ui/` 下 24 个 JS（23 个组件 + `overlay.js`）与 23 个 CSS、`styles/index.css`、`styles/ui.css`、`styles/legacy-bridge.css`、`styles/gallery.css`、`gallery.html`、`gallery.js`、`gallery-sections.js`、`gallery-sections-2.js`、`gallery-demos.js`；`styles/tokens.css` 增加窄屏控件高度规则。
- 旧前端：`omrs_dashboard.html`（样式入口、模块脚本、删 `#ib-toast`、侧栏版本）、`assets/app/domain/items.js`（四个 ui 函数改为转调）、`assets/inbox.js`（`ibToast` 转调）、`assets/board.js` / `assets/board_picker.js` / `assets/qtable.js`（「有弹层时不响应」守卫加 `dialog[open]`）、`assets/app/styles/index.css`（删除被接管的 37 行：`.btn` / `.input` 基础规则、`.ui-toast*`、`.ui-dialog*`、`.ib-toast*`、死样式 `.bd-toast`）。
- 后端：`omrs/server.py`（`_ASSET_TYPES` 增 `.html` / `.mjs`）、`omrs/source_export.py`（收录 `assets/app/package.json`）。
- 测试：新增 `tests/app/html.test.mjs`、`tests/app/browser.html`、`tests/app/browser_tests.js`、`tests/app/run_browser.py`、`tests/test_app_browser.py`、`tests/e2e/ui_bridge.py`；改 `tests/check_contrast.py`（+3 组）、`tests/test_ui_gates.py`（fixture 补 token）、`tests/test_source_export.py`、UI 基线文件（棘轮下调）。
- 文档：新增 `AI/frontend/components.md`；改 `AI/frontend.md`、`AI/frontend/design-system.md`、`AI/frontend/shell.md`、`AI/frontend/library.md`、`AI/environment.md`、`AI/api.md`、`AI/README.md`、`AI/changelog.md`、`AGENTS.md`、`README.md`、`omrs/version.py`。

## 验证结果（本轮实际执行）

| 门禁 | 结果 |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 150 个，OK（基线 149 + `test_app_browser`，本机有 playwright 故真跑）|
| `node --test tests/*.js tests/app/*.test.mjs` | 146 / 146（基线 140 + `html.test.mjs` 6）|
| `python3 tests/app/run_browser.py` | 24 / 24；`--shots` 另存 gallery 5 张，无页面错误 |
| `python3 tests/e2e/ui_bridge.py` | 15 / 15（fixture Vault + 隔离实例）|
| `python3 tests/check_ui.py` | 0 处问题；存量 handlers 277、innerHTML 198→196、行内样式 263、颜色字面量 195→191、字号字面量 418→407，已 `--update-baseline` |
| `python3 tests/check_contrast.py` | 54 组，0 不达标 |
| `python3 tests/check_docs.py --diff ba43d45` | 0 处问题，1 条提醒（`AI/api.md` 53KB，建议拆分，非本期引入）|
| `python3 tests/visual/run.py --ref ba43d45` | 48 / 48 有差异，页面脚本错误无；逐项解释见下 |

- 变异检查：临时去掉 `.qb-bar` 桥接规则、去掉对话框 Esc 的 `stopPropagation`，对应两个浏览器用例都失败；恢复后 24 / 24。
- gallery 审阅：浅 / 深 × 舒适 / 紧凑 4 张整页图逐节看过，另看 390 宽手机与真实打开的对话框、抽屉、连发 toast。修了 4 处：陈列格里控件没撑满、抽屉预览铺满看不到遮罩、提示预览被拉成整行、表格选中行与悬停行分不清（加左侧强调条，卡片模式同样处理）。
- 本轮途中修掉的缺陷：`toElement()` 返回的节点属于 template 的惰性文档（`ownerDocument.body` 为 null，对话框打开即报错），改为 `importNode`；`.html` 的 content-type 写了两遍 charset。

## 截图差异逐项解释（visual/run.py，浅色）

差异主要来自控件高度变化带来的纵向位移：旧 `.btn` 各宽度下约 38px，现在桌面为 30 / 32、手机为 40，下面的内容整体上移或下移，像素差异因此遍布整页（手机端最高 25.7%，展示板深色）。逐页对照截图，布局没有错位、重叠或新增横向溢出。运行时审计（小目标指小于 28px 的可点元素）：

| 页面 | 控件高度（前 → 后） | 小目标 桌面 / 手机 |
|---|---|---|
| 题库 | 21/25/28/38/43 → 桌面 28/30、手机 40 | 43→0 / 43→0 |
| 仪表盘 | 21/30/38 → 桌面 21/28/30、手机 21/40 | 4→4 / 4→4 |
| 即时练习 | 20/34/38 → 桌面 20/30、手机 20/40 | 3→3 / 3→3 |
| 复习调度 | 20/30/38/43/48 → 桌面 20/28/30/48、手机 20/40/47 | 41→41 / 41→41 |
| 展示板 | 20/22/24/26/30/38 → 桌面 22/24/26/28/30、手机 22/24/26/40 | 13→12 / 13→12 |
| 目录 | 16/30/36 → 桌面 16/28/36、手机 16/36/40 | 25→25 / 26→26 |
| 其余 6 页 | 旧 30/38/43 → 桌面 28/30、手机 40 | 0→0 |

全站小目标合计：桌面 129→85，手机 130→86。剩余的小目标来自尚未迁移页面的非 `.btn` 控件（标记筛选 chip、调度页选择框、目录树节点等），随 P3–P7 各页迁移处理。字号种数多数页下降 1–2 种（控件文字统一为 13px）。

## 未执行 / 不能执行的验证

- 生产重启、远端设备与真实手机（iOS Safari / Android Chrome）走查：受限模式做不到，列入交接清单。
- 旧浏览器降级：Safari 15.4 以下不支持 `@layer`（整页无样式），Safari 17 以下没有 popover（菜单、提示、toast 退回 z-index）——只按规范推断，未实机验证。
- 读屏软件实测：只做了 aria 属性的自动化断言。
- 完整模式主机若没有 playwright，`tests/test_app_browser.py` 会跳过，届时 unittest 显示 1 个 skipped。
- `AI/logs/log.md` 不在包内，按 AGENTS 规定未生成，由完整模式运行 `--write-log-index`。

## 遗留与交接

- P1 仍待执行（见上「关键决定」）；P1 合入时注意本期已有的 `main.js`、`legacy-bridge.js`、`core/`、`styles/index.css`。
- 过渡桥删除期：题库工具栏段 P5，展示板小按钮段 P7，旧弹层外壳 P5–P7，「题数」组合框段 P3，其余 P8。
- 已知遗留：即时练习页的标记筛选 chip 约 20px 高（P3）；各页 emoji 图标（D7）、原生文件选择（D6）、零散空状态（D5）随页面迁移替换。
