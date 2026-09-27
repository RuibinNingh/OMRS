# 2026-09-25 前端重构 P3：DP4 顶栏瘦身 + 即时练习迁到 features/instant

---

## 项目基本信息

| 项 | 值 |
|---|---|
| 项目名 | OMRS（Obsidian Mistake Reconstruction System）|
| 当前版本 | v1.21.0（本任务交付后为 v1.22.0）|
| 类型 | 个人错题本，Markdown + 本地 HTTP 服务 |
| 后端入口 | `omrs_engine.py` |
| 前端文件 | `omrs_dashboard.html`（结构）+ `assets/`（旧脚本与 `styles.css`）+ `assets/app/`（ES Module：core、ui、domain、features、外壳、过渡桥）|
| 数据目录 | 结构化数据在 `错题/.omrs/`；生成的 AI 报告在 `错题/report/` |
| 依赖边界 | 核心 Python 运行路径无强制第三方库；前端无构建依赖；浏览器单测、E2E 与截图需要 playwright + Chromium（可选，缺失时跳过）|

---

## 执行者与模式

- 执行者：Claude（claude.ai 沙箱，等同 CCW）。**受限模式**：源码来自上一轮交付的完整包 `OMRS-v1.21.0-2026-09-25.zip`（导出清单时间仍为 P0 的 `20260925T014232Z`，不是生产重新导出的包），无网络、无 systemd、碰不到生产与 Git 远端。
- 基线：解压后 `git init` 提交为本沙箱基线（v1.21.0）；开工门禁与交接基线逐项一致：unittest 156、node 155、浏览器 30、shell_router 18、ui_bridge 15、check_ui 0（存量 265 / 196 / 263 / 189 / 397）、对比度 54 / 0、文档 0 + 1 提醒。
- 前置：用户 2026-09-25 答复「验收通过」（P2 + P1）、「DP4 允许」，并要求先做 DP4 再推进 P3。

## DP4：顶栏只留「录入题目」，「重新扫描」挪进三页

### 行为变化（用户可见）

1. 顶栏只剩「录入题目」一个全局按钮；手机顶栏只剩一个 40×40 图标。
2. 「重新扫描」出现在三处：仪表盘概览条末尾一格（窄屏落进 3 列 / 2 列网格的最后一格）、题库工具栏（仅图标，悬停提示说明用途）、目录工具栏（「重新读取」旁）。
3. 三处统一走外壳登记的全局动作 `app.scan`：调用旧 `doScan()`，期间三处按钮都置忙（`disabled` + `aria-busy`），防止重复扫描；在目录页扫描完顺带重读目录树，「N 个题目文件还没进题库」的提示随之更新。
4. 扫描成功的提示由 warn（黄色）改为 ok（绿色）；目录页提示文案改为「点工具栏的『重新扫描』」。

### 影响文件

- `omrs_dashboard.html`（删顶栏按钮、三处新按钮）、`assets/app/shell.js`（`app.scan`）、`assets/app/styles/index.css`（概览条加一列自适应宽度的动作格）、`assets/catalog.js`（提示文案）、`assets/schedule.js`（成功提示类型）。
- 测试：`tests/e2e/shell_router.py` 18 → 20（顶栏与三页按钮、扫描主路径；手机顶栏断言改为一个按钮）。
- 文档：`AI/frontend/shell.md`、`AI/frontend/dashboard.md`、`AI/frontend/library.md`、`AI/frontend/architecture.md`。

### 验证（本轮实际执行）

- `shell_router.py` 20 / 20；`ui_bridge.py` 15 / 15；`node --test` 155 / 155；`check_ui.py` 0 处问题，handlers 265 → 264（删掉顶栏按钮的 `onclick`，新按钮用 `data-action`）；`check_docs.py` 0 处问题。
- 截图人工核对：桌面 1440、1000 与手机 390，浅 / 深色；概览条 5 格 + 动作格，3 列、2 列时动作格落在最后一格，无溢出。

## P3：即时练习迁到 `assets/app/features/instant/`（v1.22.0）

### 行为变化（用户可见）

1. 判定不再重建题卡：判对错、打分、切队列时题面节点与 KaTeX 公式原样保留，聚焦的按钮与滑杆不丢焦点，题卡滚动位置不变。改前每次判定整卡 innerHTML 重建（6 个公式全部重新渲染，焦点落回 body）。
2. 界面按新规范重做：筛选条（ui 选择框、题数字段、标记筛选按钮）、对 / 错分段按钮、空 / 加载 / 出错状态、进度与提交、队列（到期提示、状态标记）、提交结果。>1160 整屏工作台（题卡 | 右栏各自滚动），≤1160 单栏、队列变横条，≤760 手机布局；题面双栏在挂载点 ≤680px 时改单栏。
3. 快捷键与反馈工作台一致：J / K、↓ / ↑、空格显示答案、1 / 2 判对错、0 与 3–9 打分（需已判定）、Enter 下一道未判定、E 编辑、⌘ / Ctrl + Enter 提交；桌面题卡底部一行键帽提示。
4. 已提交的题锁定（不能改判、不会被重复提交）；有未提交判定时重新取题先确认。改前提交后清空全部判定，同一题可以再判再交；重新取题直接丢弃判定。
5. 与计划的差异：计划写 761–1160 两栏，实际单栏——761px 宽时去掉侧栏内容区只有约 500px。空状态里的主按钮叫「开始练习」，全页只保留一个「加载推荐」（旧冒烟测试按按钮名严格匹配）。

### 架构

- 外壳补全页面契约：登记页面时注册 `actions` / `keys`（命名空间与作用域都是页面 id）。改前契约里写了但外壳只调用 `mount`。
- 新增 `assets/app/domain/`：`questions.js`、`items.js`、`labels.js`、`data.js`，是新代码碰旧全局的唯一出口。
- `features/instant/`：`index.js`（契约与控制器，202 行）、`state.js`（模块单例状态与纯逻辑）、`view.js`（模板）、`instant.css`（features 层）。
- 旧代码：删 `assets/instant.js` 与它的 `<script>`、面板旧 HTML、`core.js` 的 `INSTANT_*`、`styles.css` 72 条规则（另从 2 组深色选择器里摘掉即时练习部分）、`legacy-bridge.css`「题数」段；`actions.js::actionGoInstant` 改为交给过渡桥；`core.js::populateFilterOptions`、`labels.js` 去掉 `inst` 前缀；`labels.js::renderLabelFilterOptions()` 末尾经 bus 发 `labels`；`app.js::reloadData()` 不再调 `instRenderSide`（新页面从 store 重绘）。
- 过渡桥：`instLoadPractice(preset)`（仪表盘预设，键沿用旧元素 id）、只读 `INSTANT_QUEUE`（给未改动的 `tests/smoke_schedule_workbench.py`）。`tests/visual/run.py` 与旧冒烟测试未改动。
- 发现并登记：qview 的窄屏单栏容器查询写在容器自身上，从不生效（`AI/optimization.md`）；即时练习在挂载点上补了容器，其余页面留给迁 qview 的那一期。

### 改前 / 改后实测（full fixture 40 题，真实浏览器）

| 项 | 改前（v1.21.0） | 改后 |
|---|---|---|
| 页面字号（不含题面 qview） | 最多 12 种，最小 9.6px | 3–4 种（紧凑档 11 / 12 / 15，空状态多 13），桌面 / 平板 / 手机相同 |
| 小于 28px 的可点目标 | 3（标记筛选芯片 20px） | 0（桌面 / 手机 × 浅 / 深 × 四种状态） |
| 判一次对错 | 题面节点换新，6 个 KaTeX 全部重渲染，焦点落回 body | 挂载点与 6 个 KaTeX 节点复用，焦点留在按钮，滚动不变 |
| 对 / 错控件 | `<span onclick>`，Tab 够不到，无快捷键 | 按钮（`aria-pressed`）+ 快捷键 |
| 页面脚本错误 | 0 | 0 |

### 验证（本轮实际执行）

| 门禁 | 结果 |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 156 个，OK（本机有 playwright，`test_app_browser` 真跑）|
| `node --test tests/*.js tests/app/*.test.mjs` | 162 / 162（155 + `instant.test.mjs` 7）|
| `python3 tests/app/run_browser.py` | 31 / 31（+ 外壳页面契约生命周期 1 项）|
| `python3 tests/e2e/shell_router.py` | 20 / 20（+ DP4 两项；手机顶栏断言改为一个按钮）|
| `python3 tests/e2e/ui_bridge.py` | 15 / 15（样式分层断言加入 `features`；D3 选择器改指新设置条）|
| `python3 tests/e2e/instant.py`（新） | 23 / 23 |
| `python3 tests/check_ui.py` | 0 处问题；存量 handlers 265 → 254、html_assign 196 → 183、inline_style 263 → 251、color_literals 189、font_size_literals 397 → 383，已 `--update-baseline` |
| `python3 tests/check_contrast.py` | 54 组，0 不达标 |
| `python3 tests/check_docs.py --diff <v1.21.0 基线>` | 0 处问题，1 条提醒（`AI/api.md` 53KB，非本期引入）|
| `python3 tests/visual/run.py --ref <DP4 提交>` | 48 张中 23 张有差异，页面脚本错误无；解释见下 |

### 截图差异逐项解释（相对 DP4 提交，visual/run.py）

- 即时练习 4 张：桌面浅 / 深 2.0% / 2.4%、手机浅 / 深 14.3% / 15.1%。这是本期的改动本身：设置条去掉重复标题、标记筛选改按钮、空状态换成 `ui/empty`；手机端设置条改两列网格。
- 其余 19 张全在桌面端、各 0.002%（约 26 像素）：像素差分定位在侧栏底部版本号（x 49–53、y 873–880），即 v1.21.0 → v1.22.0。手机端侧栏收起，没有这项差异；其余页面内容无变化。
- 截图只覆盖各页初始状态；即时练习加载、翻答案、判定后的改前 / 改后对照另拍在截图包里（改前实例由 `git worktree` 检出 DP4 提交启动）。

## 交付与交接

- 补丁链：④ `changes-2026-09-25-dp4.patch`（v1.21.0 → DP4）→ ⑤ `changes-2026-09-25-p3.patch`（→ v1.22.0），接在 ①②③ 之后；两者都已在 v1.21.0 完整包的干净解压上依次 `git apply --check`、应用，并与完整包逐字节比对。
- 完整包 `OMRS-v1.22.0-2026-09-25.zip`、`UPGRADE-2026-09-25-p3.md`、截图包 `P3-screenshots-2026-09-25.zip`、交接文档 `HANDOFF-frontend-rearch-2026-09-25-p4.md`。
- 协作流程按用户 2026-09-25 的新要求改变：P4 → P8 都由 CCW 在上一期交付的完整包上继续，各期之间不经过 Hermes；P8 之后由一个 CCW 做整体检查并写合并版 UPGRADE；最后由 Hermes 一次性部署（生产重启需用户授权）。
- 未执行 / 不能执行的验证：生产重启、远端（Nginx）与真实手机、平板走查（受限模式做不到，留给最终部署）；旧版 Safari 未实机验证；`AI/logs/log.md` 未生成（由部署时的完整模式运行 `--write-log-index`）。
