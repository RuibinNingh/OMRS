# 2026-09-25 前端重构 P1：core 底座、hash 路由、启动接管、外壳打磨与静态资源 304

---

## 项目基本信息

| 项 | 值 |
|---|---|
| 项目名 | OMRS（Obsidian Mistake Reconstruction System）|
| 当前版本 | v1.21.0 |
| 类型 | 个人错题本，Markdown + 本地 HTTP 服务 |
| 后端入口 | `omrs_engine.py` |
| 前端文件 | `omrs_dashboard.html`（结构）+ `assets/`（旧 `styles.css` 与拆分的 JS）+ `assets/app/`（ES Module：core、ui、外壳、过渡桥）|
| 数据目录 | 结构化数据在 `错题/.omrs/`；生成的 AI 报告在 `错题/report/` |
| 依赖边界 | 核心 Python 运行路径无强制第三方库；前端无构建依赖；浏览器单测、E2E 与截图需要 playwright + Chromium（可选，缺失时跳过）|

---

## 执行者与模式

- 执行者：Claude（claude.ai 沙箱，等同 CCW）。**受限模式**：源码来自 `OMRS-source-sanitized-20260925T014232Z.zip`，无 git 仓库、无网络、不能访问 systemd 与生产服务。实际改代码、跑门禁、在 fixture 隔离实例里做 E2E 与截图。
- 基线：导出包 `git init` 后的 `ba43d45`（v1.19.1）→ P2 提交 `ed74b46`（v1.20.0，见 P2 任务日志）→ 本期在 P2 之上。用户 2026-09-25 要求 P1 也完成、与 P2 统一交付。
- 顺序说明：原计划 P1 在 P2 之前；实际 P2 先做，并已按 P1 规格带入了 `package.json`、`html.js`、`dom.js`（render）、最小 `main.js`、过渡桥、分层入口与浏览器测试运行器。本期补齐 P1 其余部分，版本 v1.21.0。
- DP4（顶栏只留「录入题目」，「重新扫描」移到仪表盘 / 题库 / 目录）：交接清单第 3 条要求先得到用户同意，未得到答复时不动。本期**未执行**；手机标题被挤压的问题改用「顶栏按钮只留图标」解决，与 DP4 无关。

## 行为变化（用户可见）

1. hash 路由：地址形如 `#/questions`，刷新停在原页，浏览器前进后退可用，页面可以直接用链接打开；未知地址回到仪表盘；`href="#"` 之类的非路由 hash 不再把页面带跑（地址自动改回当前页）。
2. 外壳打磨（`assets/app/styles/shell.css`）：侧栏 232px、导航项 40px（紧凑 36px）、字号 13px；当前页强调浅底 + 左侧 3px 指示条 + `aria-current`；导航改为 `<a href="#/页面">`，可用键盘访问；折叠为 58px 图标栏时宽度与文字有过渡，页面名由提示显示；深色侧栏改用 `--surface-0`（与页面同色、靠描边分隔），深色顶栏去掉底边线。
3. 顶栏：标题改为 20px 半粗的 `<h1>`，并同步写 `document.title`（「页面名 · OMRS」）；两个全局按钮换成带图标的新按钮组件，位置与功能不变。
4. 手机（≤760px）：侧栏抽屉切页后自动关闭；顶栏按钮只留 40×40 图标（文字对读屏保留），标题不再被挤压。抽屉断点由旧的 860px 改为设计系统的 760px（761–860px 宽度改为显示常规侧栏）。
5. 内容区留白按 4px 尺度重排（舒适 20 / 24 / 40，紧凑 16 / 20 / 32，手机 12 / 16 / 32）；工作台页（>1160px）底部留白由约 58px 收到 16px，列表多显示一行左右。
6. 静态资源 304：`/assets/` 带弱 ETag 与 `Last-Modified`，文件没变时回空的 304。

## 影响文件

- 新增：`assets/app/core/{events,keys,store,bus,router,api,format}.js`、`assets/app/shell.js`、`assets/app/legacy-pages.js`、`assets/app/styles/{base,shell}.css`、`tests/app/core.test.mjs`、`tests/app/core_tests.js`、`tests/e2e/shell_router.py`、`tests/test_asset_cache.py`、`AI/frontend/architecture.md`。
- 修改：`assets/app/core/html.js`（`each`）、`assets/app/core/dom.js`（`morph`）、`assets/app/main.js`（启动顺序）、`assets/app/styles/index.css`（加 base、shell 层）、`assets/app.js`（`switchTab` 包装、不再自调用 `init()`、`reloadData` 发 `data`）、`omrs_dashboard.html`（导航改链接、遮罩挪到侧栏前、品牌与顶栏标记、顶栏按钮、版本）、`assets/styles.css`（删除迁走的外壳规则与死规则 `.tabs` / `.tab`）、`omrs/server.py`（ETag / 304）、`tests/app/browser_tests.js`（并入 core 用例）、`tests/e2e/ui_bridge.py`（层级列表与导航选择器随本期更新）、`tests/ui_baseline.json`。
- 文档：`AI/frontend/architecture.md`（新）、`AI/frontend/shell.md`、`AI/frontend/components.md`、`AI/frontend/design-system.md`、`AI/frontend.md`、`AI/api.md`、`AI/environment.md`、`AI/README.md`、`AI/changelog.md`、`AGENTS.md`、`README.md`、`omrs/version.py`。

## 验证结果（本轮实际执行）

| 门禁 | 结果 |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 156 个，OK（P2 的 150 + `test_asset_cache` 6）|
| `node --test tests/*.js tests/app/*.test.mjs` | 155 / 155（140 + `html.test.mjs` 6 + `core.test.mjs` 9）|
| `python3 tests/app/run_browser.py` | 30 / 30（组件 24 + core 6）；`--shots` 另存 gallery 5 张 |
| `python3 tests/e2e/shell_router.py` | 18 / 18：12 页按地址直进、侧栏同步切页、后退前进、刷新停留、旧 `switchTab` 与旧 onclick、未知地址、非路由 hash、折叠、手机抽屉与标题、304 |
| `python3 tests/e2e/ui_bridge.py` | 15 / 15（P2 的过渡桥用例在 P1 之上仍全过）|
| `python3 tests/check_ui.py` | 0 处问题；存量 handlers 277→265、html_assign 196、inline_style 263、color_literals 191→189、font_size_literals 407→397，已 `--update-baseline` |
| `python3 tests/check_contrast.py` | 54 组，0 不达标 |
| `python3 tests/check_docs.py --diff ba43d45` | 0 处问题，1 条提醒（`AI/api.md` 53KB，非本期引入）|
| `python3 tests/visual/run.py --ref ed74b46` | 48 / 48 有差异，页面脚本错误无；解释见下 |

- 顺带修掉：`@media not all and (max-width: 1160px)` 取代旧的 `min-width:1161px`，工作台断点与 R5 白名单一致且无 1px 重叠。

## 截图差异逐项解释（相对 P2，visual/run.py）

差异来自外壳本身和它带来的内容位移，内容区没有变化：

- 外壳区域：侧栏宽 236→232、导航项 36→40、字号 12.75→13、激活样式；深色侧栏颜色；顶栏标题 22.5px / 900 → 20px / 600、按钮加图标；手机顶栏按钮变图标。
- 位移：内容区左移约 4px（侧栏变窄、内边距改为 4px 尺度），下移约 13px（顶栏最小高度与间距）。按位移对齐后再比，内容区残余差异桌面 1–3%、手机 5–6%，来自内容区宽度多出几个像素后的细微换行。
- 运行时审计（控件高度、横向溢出、小于 28px 的可点目标）12 页与 P2 **完全相同**（小目标仍为桌面 85、手机 86），说明页面内容与控件没有被外壳改动波及。

## 未执行 / 不能执行的验证

- 生产重启、远端（Nginx）下 304 的实际命中、真实手机与平板（761–860px 宽度现在显示常规侧栏）：受限模式做不到，列入交接清单。
- 旧版 Safari：模块顶层 `await` 需 Safari 15+，与 `@layer` 的 15.4 下限一致，未实机验证。
- DP4 未执行（等用户答复）。
- `AI/logs/log.md` 未生成，由完整模式运行 `--write-log-index`。

## 遗留与交接

- `legacy-pages.js`、`app.js` 的 `switchTab` 包装、`legacy-bridge.js`、`legacy-bridge.css` 都是过渡物，P8 清空；每迁一页删对应一项。
- 12 个分散的 keydown 监听仍在旧代码里，随各页迁移改用 `core/keys.js`。
- DP4 若用户同意：把 `omrs_dashboard.html` 顶栏的「重新扫描」按钮移进仪表盘、题库、目录三页的工具栏，并更新 `AI/frontend/shell.md`，约半小时。

## 交付后修正（2026-09-25，Hermes 隔离验收反馈）

- 反馈：隔离副本验收基本通过（Python 159、Node 155、浏览器 30、UI Bridge 15、UI 门禁 0、对比度 54、文档 0、视觉 48/48 且无新增溢出）；两处测试脚本问题：`tests/e2e/shell_router.py` 固定等待 400ms，偶发读到侧栏过渡中间态；新浏览器测试直接启动 Chromium、不认 `OMRS_TEST_CDP_URL`，在 Hermes 主机上报 `Page crashed`。
- 修正（只动测试脚本与文档，产品代码不变，版本仍为 v1.21.0）：`tests/app/run_browser.py`、`tests/e2e/shell_router.py`、`tests/e2e/ui_bridge.py` 设了 `OMRS_TEST_CDP_URL` 时 `connect_over_cdp`，否则照旧启动；`shell_router.py` 的五处固定等待改成等条件成立（侧栏宽度到 58 / 232、抽屉可见与关闭、地址改回）。`tests/visual/run.py` 与旧 smoke 测试未改，避免与 Hermes 本机未提交的适配冲突。
- 验证：CDP 路径（另起带 `--remote-debugging-port` 的 Chromium）`shell_router` 18/18、`run_browser` 30/30、`ui_bridge` 15/15；自行启动路径 `shell_router` 18/18。
- 交付：`changes-2026-09-25-p1-fix.patch`，在 P1 补丁之后应用。
