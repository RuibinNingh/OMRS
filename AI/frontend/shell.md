# 前端：外壳、布局与主题

> **速查**
> - 职责：页面外壳：`assets/` 文件划分与加载顺序、侧栏与顶栏、hash 路由的外壳一侧、整屏工作台布局、主题 token 与深色对比度
> - 入口：`omrs_dashboard.html`、`assets/app/domain/items.js`、`assets/app/main.js`、`assets/app/main.js`、`assets/app/shell.js`、`assets/app/styles/shell.css`、`assets/app/styles/tokens.css`、`assets/app/styles/index.css`、`assets/app/styles/index.css`
> - 不变量：`core.js` 最先加载、`app.js` 是最后一个经典脚本，模块入口 `assets/app/main.js` 排在它之后并负责调用 `init()`；`switchTab` 只是路由的一行包装；样式只有 `tokens.css` 与 `index.css` 两个 `<link>`；颜色一律走 token，不在规则里写死浅色值
> - 必跑测试：`tests/e2e/shell_router.py`、`tests/e2e/catalog.py`、`tests/app/settings.test.mjs`、`tests/e2e/settings.py`
> - 相关：`AI/frontend.md`（索引）

## 文件组织（assets/）
```
omrs_dashboard.html   ← 仅 HTML 结构，<link> 引样式 + 多个 <script> 引脚本
assets/
├── app/              ← 新前端（ES Module）：main.js、shell.js、legacy-pages.js、legacy-bridge.js、core/、ui/、domain/、features/（仪表盘、数据复盘、复习调度、展示板、题目库、即时练习、反馈录入、历史记录、目录、报告、设置，以及录入题目的外壳、上传、快速录入与收件箱网格）、styles/（见 AI/frontend/architecture.md）
├── styles.css        ← 旧页面样式，经 app/styles/index.css 以 @layer legacy 引入（颜色一律引用 token）
├── vendor/fonts/     ← 本地 Noto Sans SC / JetBrains Mono 字体分片、许可与来源清单
├── core.js           ← 全局状态、api()、通用工具/筛选/Markdown 渲染 + 做题记录解析
├── labels.js         ← 用户标记芯片、LabelPicker、标记管理与筛选状态
├── questions.js      ← 题库页迁走后的残留：masteryBarHtml（P7 第 6 轮起已无调用方，P8 随本文件删）；题库页在 assets/app/features/questions/，Markdown 编辑器在 assets/app/domain/question/editor.js
├── schedule.js       ← 全局扫描 doScan 与两个旧入口；复习调度页在 assets/app/features/schedule/
└── app.js            ← switchTab（路由包装）/旧页面刷新链 legacyDataRefresh/init()（由 app/main.js 调用）
```

**加载约定（重要）：**
- 除 `assets/app/main.js`（`<script type="module">`，排在 `app.js` 之后，浏览器在全部经典脚本之后才执行）外，脚本均为普通 `<script>`，共享同一全局作用域；顶层 `let`/`const` 跨文件可见，行内 `onclick` 仍可直接调用各函数。旧代码调用 `uiToast` 等过渡桥函数不必关心模块是否就绪：桥装好之前的调用会排队补发。
- 样式只有两个 `<link>`：`assets/app/styles/tokens.css` 与 `assets/app/styles/index.css`。KaTeX 与 `styles.css` 由 `index.css` 分层引入，不要再单独 `<link>`（未分层的样式会压过全部分层样式）。
- **加载顺序**：`labels.js` 在 `questions.js` 之前。当前 HTML 的完整顺序为
  `core → labels → questions → schedule → inbox → app`。展示板整页是模块（`assets/app/features/board/`，v1.26.5 起旧 `board.js` 已删），
  板详情在第一次真正同步预览时才 `boardPreviewOn(...)` 注册回调（`detail.js` 的惰性注册）。
- 共享题目视图（`renderMdContent`、`ensureQuestionDetail`、`qvHtml`、`qvRender`、`viewQ` 等）已是模块 `assets/app/domain/question/`，由过渡桥在 `init()` 之前挂成同名全局；经典脚本只能在函数体里调用它们，不能在文件顶层直接调用（顶层执行时模块还没运行）。
- **不再新增经典脚本**：新代码一律进 `assets/app/`（见 `AI/frontend/architecture.md`）；仪表盘、数据复盘、复习调度（含推荐选题）的旧脚本已删，其余旧页面迁走时逐个删。
- **加载顺序固定**：`core.js` 最先（定义全部全局变量，只能声明一次，不可在其他文件重复 `let`）；`app.js` 是最后一个经典脚本，但不再自调用 `init()`：模块入口 `assets/app/main.js` 装好过渡桥与路由后调用它（启动顺序见 `AI/frontend/architecture.md` §2）。
- 后端由 `/assets/<file>` 通用静态路由提供（`server.py` → `_serve_asset()`，含路径穿越防护与按扩展名的 content-type）。原 `/omrs_dashboard.js` 路由已移除。
- 修改旧页面样式 → 改 `assets/app/styles/index.css`（它在 `legacy` 层，同名外观会被 `ui` 与 `legacy-bridge` 层压过，旧 `.btn` / `.input` 的外观改在 `assets/app/styles/controls.css`）；改某模块行为 → 改对应 `assets/*.js`；新增全局工具 → 放 `core.js`。
- **拆分**：原 `schedule.js` 的导出、反馈页、复习调度部分都已迁到 `assets/app/`（`features/schedule/`、`features/feedback/`、`domain/exporting.js`），旧 `schedule.js` 只剩扫描与两个旧入口。

## 侧栏、顶栏与路由（`assets/app/styles/shell.css`、`assets/app/shell.js`）

- 地址形如 `#/questions`：刷新停在原页，浏览器前进后退可用，页面可以直接用链接打开。路由与页面契约见 `AI/frontend/architecture.md` §3。
- 页面 `<head>` 注册 `assets/app/omrs-favicon.svg` 作为 16–32px 标签页图标，注册 `assets/app/omrs-icon.svg` 作为 48px 以上与触控主屏图标；侧栏左上角 32px 品牌位使用小尺寸图标，旁边保留 OMRS 名称与中文副标题。
- 侧栏宽 232px，导航项是 `<a class="tab" href="#/页面">`（键盘可达）。当前页：强调浅底、半粗、左侧 3px 指示条，并带 `aria-current="page"`。
- 侧栏、折叠按钮和手机汉堡按钮的图标都引用页面内的 `#i-*` SVG sprite；`.nav-ico` 统一设置 `currentColor` 描边、无填充、圆角线帽和 18px 盒子，避免 symbol 缺少外观规则时退回浏览器默认填充。
- 折叠：`toggleSidebar()` 在 `<html>` 上切 `data-sidebar="collapsed"`（存 localStorage），侧栏收成 58px 图标栏，宽度与文字淡出有过渡；折叠时外壳给导航项挂 `data-tooltip`，悬停显示页面名。
- 顶栏：标题是 `<h1 id="topbar-title">`，由外壳按页面登记写入，同时写 `document.title`。顶栏只有一个全局按钮「录入题目」（`.ui-btn` 带图标，不是旧 `.btn`：旧 `.btn` 被最高的 legacy-bridge 层接管，外壳改不动它）。「重新扫描」不在顶栏，放在仪表盘概览条、题库工具栏、目录工具栏三处，统一写 `data-action="app.scan"`，由外壳登记的全局动作处理：调旧 `doScan()`，期间三处按钮都置忙（`disabled` + `aria-busy`）防重复扫描；在目录页扫描成功时发 `catalog:refresh`，目录控制器重读磁盘树。
- 手机（≤760px）：侧栏变左侧抽屉（汉堡按钮打开，遮罩或 Esc 关闭，切页后自动关闭）；顶栏的「录入题目」只留 40×40 图标（文字对读屏保留），标题占满剩余宽度、过长时省略，不再被按钮挤压。

## 整屏工作台布局（`.is-workbench`）

功能复杂的多栏页原先各自为战：收件箱处理页写死 `height:calc(100vh - 200px)`，反馈工作台和题库则靠
`position:sticky` 让侧栏跟随、整页一起滚。前者的 `200` 是数出来的，页头一旦加减工具栏就算错；
后者在长列表下会把工具条、表头和「提交反馈」按钮一起滚出视口。

统一为一条链路：

1. 外壳（`assets/app/shell.js`）按页面登记表的 `workbench` 字段给 `.content` 切 `.is-workbench` 类，命中五页：
   `questions` / `feedback` / `create` / `board` / `instant`。
2. `assets/app/styles/shell.css` 在大于 1160px 时让 `.content.is-workbench` 变成
   `height:100vh; overflow:hidden` 的 flex 列，`.topbar` 不收缩，`.panel.active` 拿走剩余高度。
3. 各页把自己的滚动容器标成 `flex:1; min-height:0; overflow-y:auto`。

因此高度是从 `.content` 一路分下去的，**不再出现 `calc(100vh - 魔数)`**；页头加减工具栏无需重算。

| 页面 | 撑高的容器 | 各自滚动的区域 |
|---|---|---|
| 题目库 | `.qlb` → `.qlb-card` → `.qlb-body`（`features/questions/questions.css`） | `.qlb-main` 里的表格 / 画廊、`.qlb-drawer` |
| 反馈录入 | `.fb-work`（`grid-template-rows:minmax(0,1fr)`） | `.fb-rail` / `.fb-stage` / `.fb-panel` 三栏独立 |
| 录入题目 | `#create-app` → `.ib-stage.on`；处理页额外 `#ib-stage-process.on` → `.ib-proc` | 新页面契约渲染导航和上传网格；旧处理工作区仍承载三栏，上传 / 录入 / AI 训练三个 stage 整体滚 |
| 展示板 | `.bd-layout` | `.bd-layout > .card` 三张 |
| 即时练习 | `.inst-work`（`features/instant/instant.css`） | `.inst-main` / `.inst-queue__list` |

配套：题库表头 `position:sticky; top:0`，列表再长表头也在；抽屉不 sticky（父级已经限高，自己滚）。

**只在 ≥1161px 生效**。窄屏沿用原有响应式：反馈工作台仍走 1160 / 820 两档重排，
题库抽屉 ≤1160 落到列表上方，都不受影响。

改这几页时的注意点：
- 新增的滚动容器必须同时写 `min-height:0`，否则 flex 子项按内容撑开，`overflow` 不生效。
- 往工作台页面加新的顶部工具栏，记得给它 `flex-shrink:0`，否则会被压扁。
- 新增工作台型页面时，在它的页面登记（页面登记模块 或页面契约）里写 `workbench: true`，不需要动 CSS 结构。

## 主题与对比度（`tokens.css` + `styles.css`）

主题切换机制见 `AI/frontend/settings.md`「外观与显示」：`<head>` 内联脚本 + `localStorage('omrs-theme')` + `<html data-theme>`。全部 token 定义在 `assets/app/styles/tokens.css`，浅色与深色的对比度由 `tests/check_contrast.py` 统一校验，规则见 `AI/frontend/design-system.md`。

浅色主题当前值：辅助文字 `--fg-3` 为 `#6b7178`；状态色 `--danger` `#d02020`、`--success` `#15803d`、`--warning` `#a16207`、`--info` `#2563eb`；芯片字 `--success-fg` `#166534`、`--warning-fg` `#854d0e`、`--danger-fg` `#b91c1c`。以上对 `surface-0/1` 或各自的 `-soft` 底均 ≥4.5:1。

### 深色 token 层（`[data-theme="dark"]`，下表用旧名，今为语义 token 的别名）

| 变量 | 修订前 | 当前值 | 原因 |
|---|---|---|---|
| `--bg` | `#1a1916` | `#141311` | 页面底压暗一档，给卡片让出层次 |
| `--bg2` / `--bg3` / `--bg4` | `#211f1c` / `#2b2925` / `#3a3732` | `#211f1d` / `#2e2b27` / `#433f38` | 内层面依次拉开 |
| `--fg` / `--fg2` / `--fg3` | `#ece7df` / `#a39c91` / `#6f685e` | `#f0ebe3` / `#b3aa9e` / `#8f887c` | `--fg3` 原本对 `--bg2` 只有约 3:1，抬到约 4.7:1 |
| `--red` / `--green` / `--yellow` / `--blue` | `#d98a7e` / `#82ab8b` / `#cda35f` / `#7e9bbf` | `#e59a8c` / `#8fbf9a` / `#dcb06a` / `#8fb0d8` | 语义四色整体提亮一档，对 `--bg2` 均 ≥7:1；`--*-rgb` 同步 |
| `--kill/attack/trap-bg` | `.16` | `.20` | 状态 chip 底色需要看得出 |
| `--border` / `--border2` | `.10` / `.17` | `.13` / `.23` | 深色下卡片主要靠描边区分，不能太淡 |
| `--chart-surface` / `--chart-line` | `.035` / `.11` | `.055` / `.17` | 空热力格与坐标网格原本近乎不可见 |
| `--accent-fg` | `#1a1916` | `#17150f` | 跟随新底色 |

`.stat-card` / `.card` 的深色规则由半透明白渐变（`rgba(255,255,255,.045→.024)`）改为**实色 `var(--bg2)` + `--border` 描边 + 更实的投影**；深色侧栏用 `--surface-0`（与页面同色，靠右侧描边分隔）。

答案块只有一条规则 `.qv .q-answer-md`，走 `rgba(var(--green-rgb),α)`，深色不需要单独补丁。深色「反转题图」的选择器是 `.q-md img` / `.qv .q-md img` / `.gallery-preview img`。

### 规则层：写死浅色的几处

根因是这些规则写死了浅色时代的颜色，token 切深色后它们不跟着走。全部新增为 `[data-theme="dark"]` 覆盖，集中在 `styles.css` 末尾「v1.7.0 深色对比度修订」注释段：

- `.modal .q-answer .q-md`：原 `rgba(39,134,74,.04)` 深绿底，深色下等于没有 → 改 `rgba(var(--green-rgb),.10)`，边框 `.30`。
- `.timeline-head .tag.fam-review` / `.fam-session`：原写死 `rgba(47,125,79,.1)` / `rgba(53,106,156,.1)` → 改走 `--green-rgb` / `--blue-rgb` 的 `.18`；`.fam-question` / `.fam-system` 一并改用 token 前景色。
- `.heat-0`～`.heat-4`：空档 `.07` 看不出网格 → `.14`；中间档同步抬；`.heat-3` / `.heat-4` 的白字压浅绿底 → 改深墨 `#17150f`；`.heat-cell` 文字改 `--fg2`。
- `.level-fill` 与 `.bar-fill` / `.chart-fill` 的渐变低位：原停在 `.42` / `.72`，深色下淡进背景让柱子像被截断 → 抬到 `.58` / `.82`（accent 抬到 `.70`）；`.bar-track` / `.m-bar` 轨道改 `rgba(236,231,223,.10)`。
- `.btn.danger:hover`：`color:#fff` 压在浅色语义红上 → 深色下改 `#17150f`。
- 卡中卡（`.rec-item` / `.sched-item` / `.picker-row` 等）由 `.04` 抬到 `.07` 并补描边；`.btn` 底 `.05→.07`、hover `.10→.14` 并明确前景色；`.input` 深色底改 `--bg3`；`.img-thumb` 角标底改 `.70`。

**维护约定**：新写深色规则一律走 `var(--*)` 或 `rgba(var(--*-rgb), α)`，不要再写死十六进制或裸 `rgba(r,g,b,a)`；确需固定的深墨字用 `#17150f`（与 `--accent-fg` 同值）。
