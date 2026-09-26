# OMRS 前端重构计划（架构 + 设计系统 + UI 精致化）

> **速查**
> - 目标：重建前端架构，同时满足三点：CCW 能在受限模式下安全修改、可维护性提升、UI 精致化打磨
> - 路线：无构建、零依赖的原生 ES Module；`assets/app/` 与旧代码物理隔离，逐页替换；每期都能上线
> - 门禁：原有 Python 137 / Node 140 / check_docs 0 继续全绿，另加 `check_ui.py` 棘轮和前后截图对比
> - 分期：P0 基建 → P1 底座 → P2 组件库 → P3–P7 逐页迁移 → P8 收尾，约 10–12 轮 CCW 会话
> - 编写：Claude Code Web（受限模式），2026-09-24，基线为导出包 `20260924T154156Z`
> - 执行：P0 到 P6 第 5 轮由 CCW 在受限模式下执行；2026-09-26 起，剩余部分由 Codex 在完整模式下按 `exec-2026-09-26-codex.md` 执行（progress §9）
> - 进度：见同目录 `progress.md`。本文件是总纲，只在计划本身变更时修改，并在 progress.md「计划变更」登记

---

## 0. 用户诉求清单（原话，计划各节都要能指回这里）

| # | 用户原话 | 对应章节 |
|---|---|---|
| U1 | "目前的前端架构我觉得还是很粗糙，很多时候打磨不够细致" | §1.3 视觉缺陷、§4 设计系统、P2–P7 |
| U2 | "并且设计上不合理" | §1.3、§4.6 交互模式、DP4 |
| U3 | "维护更麻烦" | §1.2、§3 架构、§5 门禁 |
| U4 | "重设计一个前端架构，让 CCW 能进行修改的同时，提升可维护性，还有实现 UI 的精致化打磨" | 全文；CCW 适配见 §3.1、§5 |
| U5 | "受限模式……依旧可以执行你最大范围的能力……制定一个详细的计划" | 本文件；分期里的执行者标注 |

主诉求是 U4 中"UI 精致化"和"可维护"两件事同时落地。按 AGENTS.md 防漂移规则，每一期都必须交付一个肉眼可见的改进，不允许只交地基。

---

## 1. 现状基线（2026-09-24 实测，不是估计）

### 1.1 环境与门禁

- CCW 环境：Python 3.12.3、Node 22.22.2、git 2.43.0、Chromium 141（playwright 可以无头运行）。网络 403，不能装依赖。1 核 CPU，4GB 内存。
- 基线门禁：`unittest` 137 个用例 OK；`node --test` 140/140 通过；`check_docs.py` 0 处问题、1 条提醒（`AI/api.md` 52KB，超过 40KB）。
- 隔离实例：临时 Vault 放了 8 道题（数学/物理/化学/英语，含 LaTeX 和长题面），端口 18471。12 个页面各截一遍，浅色、深色各一轮，另加 390px 移动视口 4 页。浏览器控制台 0 个错误。

### 1.2 代码结构

| 指标 | 数值 | 说明 |
|---|---|---|
| 前端体积 | JS 约 570KB / 20 个文件，CSS 191KB 单文件，HTML 98KB | 最大的三个是 `board.js` 106KB、`inbox.js` 54KB、`app.js` 46KB |
| 共享全局作用域 | 约 740 个顶层声明 | 靠 `<script>` 顺序维持，`shell.md` 要用一大段专门讲加载顺序 |
| 行内事件 | HTML 227 处，JS 模板 74 处 | 这是阻碍 ES Module 化的主要障碍 |
| `innerHTML=` | 209 处 | 整块重建 DOM，焦点、滚动、KaTeX 都会丢 |
| 行内 `style=` | HTML 85 处，JS 模板 185 处 | 数据复盘页运行时有 145 个元素带行内样式 |
| CSS 组织 | 按版本往后追加（v1.2 refresh / v1.4.1 现代化 / v1.5.0 暖石墨……） | 顶层有 73 个选择器被重复定义 |
| 设计尺度 | 只有 21 个 token | 但有 62 种字号、24 种圆角、38 种阴影、38 种 transition、15 种 z-index、十几种断点 |
| 字号 token 使用率 | `--fs*` 只被引用约 76 次 | 其余全是硬编码的 `.62–.82rem` |
| 重复组件 | 3 套 toast、6 类弹层、15 种 empty 类、约 30 种 chip/tag/badge 类 | `uiToast` / `showBoardToast` / `ibToast` 三套并存 |
| 原生控件 | 33 个 `<select>`，报告页用原生文件选择 | 外观没有统一 |
| 疑似死代码 | `recommend.js` 的 31 个函数中 28 个没有外部引用 | 页面已改用 `recommend_v2.js`，P0 核实后处理 |
| 页面注册 | `switchTab()` 写死页面表，外加一串 `typeof x==='function'` 判断 | 新增页面要改好几处 |

### 1.3 视觉缺陷清单（截图与运行时测量）

| 编号 | 缺陷 | 证据 |
|---|---|---|
| D1 | 正文字号偏小，而且档位过多 | 运行时文本集中在 9.3–12.3px；仪表盘一页渲染出 18 种字号，数据复盘 14 种 |
| D2 | 控件高度没有尺度 | 题库工具栏同一行里，搜索框、筛选、排序 select、表格/画廊切换、列/密度、状态 chip 高度各不相同 |
| D3 | 移动端即时练习页的筛选 select 文字上下被裁切 | 390px 截图中"全部科目"等只露出半行，**这是 bug** |
| D4 | 移动端题库表格横向被截断，没有滚动提示；搜索框 placeholder 被截断 | 390px 截图 |
| D5 | 空状态不统一且很简陋 | 反馈录入空态是两个空白框；即时练习空态是一大块空卡 |
| D6 | 原生控件没有统一外观 | 33 个原生 select；报告页原生 "Choose File" |
| D7 | 图标体系混用 | emoji（📥📑🔄📋）与线性 SVG 并存 |
| D8 | 仪表盘首屏节奏断裂 | 大数字区直接放在背景上；"开始复习"按钮与"行动推荐"卡几乎没有间距 |
| D9 | 可点击目标过小 | 高度小于 28px 的可点元素：题库 12 个、目录 13 个、复习调度 8 个 |
| D10 | 全局动作放置不合理 | "重新扫描 / 录入题目"出现在包括设置、报告在内的所有页面，移动端还会挤压标题 |
| D11 | 行内样式直接承担语义 | 例如 `style="color:var(--yellow)"` 充当状态提示，同类信息每处样子都不一样 |

这些缺陷的共同根源是：没有尺度、没有组件、没有边界。本计划先解决根源，再逐页消除这些缺陷。

---

## 2. 目标与验收指标

| 维度 | 指标 | 何时达成 |
|---|---|---|
| 字号 | 每页渲染字号不超过 6 种；正文不小于 13px，辅助文字不小于 11px | 每页迁移完成时 |
| 控件 | 控件高度只允许 28 / 32 / 40px 三档 | P2 起的新代码；旧页随迁移完成 |
| 可点目标 | 桌面不小于 28px，移动端不小于 40px | 每页迁移完成时 |
| 对比度 | token 组合中，正文不低于 4.5:1，大字和图形不低于 3:1（浅色、深色都要满足），由脚本计算 | P0 |
| 组件唯一 | toast、弹层、空状态、tag 各只剩一套 | P8 |
| 旧债归零 | `on*=`、`innerHTML=`、`style=` 存量归零；`styles.css` 删除 | P8 |
| 可维护 | `assets/app/` 下单个 JS 文件不超过 400 行、CSS 不超过 300 行；feature 之间没有互相 import | 持续，由 `check_ui.py` 强制 |
| 回归 | 每期 Python / Node / check_docs 全绿；前后截图差异全部解释过 | 每期 |

---

## 3. 目标架构

### 3.1 为什么无构建、零依赖

- CCW 不能联网，没法 `npm install`；受限模式只能靠仓库里已有的东西工作。
- 维护者之间用补丁加 `git apply --3way` 协作，构建产物会产生大块冲突，也无法人工审阅。
- 后端是标准库 HTTP 服务，`/assets/*` 按原样提供文件；`.js` 的 MIME 已经满足 ES Module 要求。
- 现有代码本来就是字符串模板，换成"自动转义的标签模板 + 差量 DOM 更新"几乎是机械迁移，能按页渐进，不需要一次性重写。

### 3.2 目录结构

新代码全部放在 `assets/app/`。旧的 `assets/*.js` 和 `styles.css` 原地保留，迁完一页删一页。

```
assets/app/
├── package.json          {"type":"module"}：只作用于本目录，旧脚本的 require 测试不受影响
├── main.js               唯一启动入口：安装过渡桥 → 调旧 init() → 注册页面 → 启动路由
├── core/                 与业务无关的底座（不 import ui/domain/features）
│   ├── html.js           html`` 标签模板（默认转义）、raw()、each(list, key, fn)
│   ├── dom.js            morph(root, htmlResult)：带 key 的差量更新，唯一允许写 innerHTML 的地方
│   ├── events.js         data-action 全局委托和动作注册表
│   ├── keys.js           快捷键注册表，按当前页面生效，替代分散的 16 个 keydown 监听
│   ├── store.js          createStore / subscribe(selector) / batch
│   ├── bus.js            轻量事件总线（data:reloaded、question:changed……）
│   ├── router.js         hash 路由 #/questions，负责页面生命周期
│   ├── api.js            fetch 封装，统一错误结构 {ok, data, error}
│   └── format.js         日期、百分比、数字（tabular）
├── styles/
│   ├── index.css         @layer reset, tokens, base, ui, domain, features, utilities, legacy-bridge;
│   ├── tokens.css        原始色板 → 语义 token；浅色/深色；[data-density] 两套密度
│   ├── base.css          排版、焦点环、滚动条、中文与数学混排、打印隔离
│   └── shell.css         侧栏、顶栏、工作台布局（取代 .is-workbench 那一段）
├── ui/                   无业务语义的组件：每个组件一个 x.js 加一个 x.css
│   └── button/ icon/ field/ select/ switch/ segmented/ tabs/ tag/ badge/ card/ stat/
│       table/ dialog/ drawer/ menu/ toast/ empty/ skeleton/ status/ progress/
│       tooltip/ kbd/ filedrop/
├── domain/               有业务语义、跨页面共享
│   ├── question/         题面/答案渲染（Markdown + KaTeX 按内容哈希缓存）、qview、记录模块
│   ├── labels/           标记芯片、LabelPicker
│   └── session/          Session 选择器和数据同步
├── features/             一个页面一个目录；feature 之间禁止互相 import
│   └── dashboard/ data/ questions/ board/ catalog/ schedule/ instant/
│       feedback/ create/ history/ reports/ settings/
│       └── index.js（页面契约）  view.js  state.js  actions.js  *.css
└── gallery.html          组件陈列页：每个组件的全部状态 × 浅色/深色 × 两种密度
```

### 3.3 依赖方向（由 `check_ui.py` 强制）

```
features → domain → ui → core
    └────────→ ui ─────→ core
styles/tokens 被所有 CSS 引用；JS 不直接读取颜色值
```

违反依赖方向会让门禁失败。跨页面的联动一律走 `bus`，不允许直接调用别的页面的函数。

### 3.4 页面契约与路由

```js
// features/instant/index.js
export const page = {
  id: 'instant', title: '即时练习', workbench: true,
  actions,                                  // 本页的 data-action 处理器
  keys: { j: next, k: prev, ' ': reveal },  // 本页快捷键，离开页面自动失效
  mount(root, ctx) {                        // ctx = { store, bus, api, router }
    const s = createInstantState(ctx);
    const off = s.subscribe(st => morph(root, view(st)));
    return () => { off(); s.dispose(); };   // unmount
  },
};
```

- `router.js` 负责 hash 路由：刷新后停留在原页，也可以直接用链接打开某一页。旧的 `switchTab(name)` 保留为一行包装 `router.go(name)`，旧的 `onclick="switchTab(...)"` 不用改。
- 顶栏标题、`.is-workbench` 状态、侧栏高亮都从页面契约里读取，`switchTab` 里的硬编码表和 `typeof` 判断链一并删除。
- 过渡期内，还没迁移的页面由 `legacyPages` 适配器登记：把现在 `switchTab` 里那串 `if(name===...)` 原样搬过去。

### 3.5 渲染：`html``` + `morph`

- `html``` 对插值默认转义；需要原样输出的 HTML 必须显式写 `raw()`，`check_ui` 会统计 `raw(` 的数量。
- `morph(root, next)` 规则：
  - 用 `data-key` 对齐列表项。
  - 当前聚焦的输入框保留 value 和选区。
  - 带 `data-morph="skip"` 的子树不参与比对（iframe、第三方渲染）。
  - 带 `data-hash` 的节点哈希相同就跳过（题面 KaTeX 靠这一条避免重算）。
- 事件委托写法：`<button data-action="instant.verdict" data-arg="true">`，`events.js` 在 `document` 上只绑一次。
- 实现规模约 200 行，核心单测放在浏览器里跑（见 §5.4）。

### 3.6 状态

- 全局 `appStore`：stats（原 `DATA`）、sessions、labels、配置。每个页面有自己的 `state.js`，页面内部的临时状态不进全局。
- 过渡期由旧代码持有 `DATA`：`reloadData()` 末尾加一行 `window.__omrs?.emit('data', DATA)`，新 store 通过这个通知同步。等依赖它的页面全部迁完（P6），再把数据加载逻辑搬进 `domain/` 并反转所有权。

### 3.7 启动顺序与过渡桥（关键风险点）

模块脚本是延迟执行的，会在所有经典脚本之后才运行。因此：

1. `app.js` 末尾的 `init()` 自调用移到 `main.js` 里执行，否则旧代码可能在模块就绪前调用新函数。这正是 AGENTS.md 复盘里"回调注册时机"那类事故。
2. `main.js` 的执行顺序：安装过渡桥（把新模块中仍被旧 `onclick` 或旧脚本调用的函数挂到 `window`，列表集中在 `legacy-bridge.js`）→ `init()` → 注册页面 → `router.start()`。
3. 过渡桥里每一条都注明"哪个旧调用方、哪一期删除"。P8 时过渡桥必须为空。

### 3.8 缓存

现在 `_serve_asset` 只返回 `Cache-Control: no-cache`，没有 ETag，浏览器每次都要重新下载全部文件。模块化以后文件数会超过 60 个，远端经 Nginx 访问时会明显变慢。P1 给 `_serve_asset` 加上 `ETag`/`Last-Modified` 和 304 响应（后端小改动，同步 `AI/api.md`）。模块内部 import 带不上 `?v=` 参数，不需要再手工维护版本串。

### 3.9 范围外

- 不改业务行为和后端 API。唯一例外是 §3.8 的缓存头。
- 不改导出和打印模板 `omrs/export_templates/*`：展示板预览 iframe 的消息协议保持不变。
- `inbox_mobile.html` 只接入 tokens 和 base 样式（P6），不重写。

---

## 4. 设计系统规范（UI 精致化的"尺度"）

### 4.1 字体与字号

| token | 值 | 用途 |
|---|---|---|
| `--text-2xs` | 11px | 元信息、等宽 ID、图例 |
| `--text-xs` | 12px | 标签、次要说明、表头 |
| `--text-sm` | 13px | 表格、紧凑正文、控件文字 |
| `--text-md` | 14px | 默认正文 |
| `--text-lg` | 16px | 卡片标题、题面（阅读） |
| `--text-xl` | 20px | 页面标题 |
| `--text-2xl` | 28px | 统计数字 |
| `--text-display` | 40px | 仪表盘首屏大数字（全站唯一） |

- 行高：界面文字 1.45；阅读正文（题面、答案）1.75；数字 1.15。
- 字重只用 400、500、600；700 只给 display。
- 数字列和统计值用 `font-variant-numeric: tabular-nums`。等宽字体只用于 UID、时间戳、代码。
- KaTeX：行内公式 `font-size:1.02em`，基线对齐；块级公式允许横向滚动，并加渐隐提示。
- 紧凑密度 `[data-density=compact]` 整体下调一档（14→13），对接设置页已有的"舒适 / 紧凑"开关。

### 4.2 间距、尺寸、形状

- 间距以 4px 为基准：`--sp-0_5`=2、`--sp-1`=4、`--sp-1_5`=6、`--sp-2`=8、`--sp-3`=12、`--sp-4`=16、`--sp-5`=20、`--sp-6`=24、`--sp-8`=32、`--sp-10`=40、`--sp-12`=48。
- 控件高度：`--ctl-sm`=28、`--ctl-md`=32、`--ctl-lg`=40。同一行的控件必须同一档，这条直接解决 D2。
- 圆角：`--r-xs`=4（tag）、`--r-sm`=6（控件）、`--r-md`=10（卡片）、`--r-lg`=14（弹层）、`--r-pill`。
- 阴影（elevation）：`--elev-0` 无阴影、只靠描边；`--elev-1` 卡片；`--elev-2` 下拉和浮层；`--elev-3` 弹窗。深色主题主要靠描边加表面层级区分，阴影减弱。
- 层级：`--z-sticky` 10 < `--z-sidebar` 20 < `--z-dropdown` 100 < `--z-drawer` 200 < `--z-modal` 300 < `--z-toast` 400 < `--z-tooltip` 500。
- 断点只允许三个：760（移动）、1160（工作台）、1500（宽屏）。CSS 的媒体查询不能用变量，由 `check_ui` 白名单约束。

### 4.3 颜色

- 两层结构：原始色板（暖中性色 0–950，加红、绿、黄、蓝四个语义色系各 5 级）映射到语义 token。
- 语义 token：
  - 表面：`--surface-0/1/2/3`
  - 文字：`--text-1/2/3`、`--text-on-accent`
  - 描边：`--border-1/2`
  - 强调：`--accent`、`--accent-hover`
  - 状态：`--success-*`、`--danger-*`、`--warning-*`、`--info-*`（各含 `fg`、`bg`、`border`）
  - 焦点：`--focus-ring`
- 旧 token（`--bg`、`--fg2`、`--red` 等）在 `tokens.css` 里保留为新 token 的别名。调色板只改一处，新旧页面同时生效。P8 删除别名。
- `tests/check_contrast.py` 从 `tokens.css` 解析出所有前景/背景组合，按 §2 的阈值检查。

### 4.4 动效

- 时长：`--dur-1` 120ms（悬停、按下）、`--dur-2` 180ms（切换、浮层）、`--dur-3` 260ms（抽屉、弹窗）。
- 缓动：`--ease-out: cubic-bezier(.2,.8,.2,1)`、`--ease-in-out: cubic-bezier(.4,0,.2,1)`。
- 只对 `opacity`、`transform`、`background-color`、`border-color` 做动画。
- `prefers-reduced-motion` 下所有时长置 0。

### 4.5 组件状态矩阵

每个 ui 组件都必须在 `gallery.html` 里展示以下状态，缺一项视为未完成：

默认、悬停、按下、`:focus-visible`、禁用、加载中、空、错误、骨架屏（适用时）、长文本溢出、浅色/深色、舒适/紧凑。

### 4.6 交互模式（对应 U2"设计不合理"）

- **空状态**：统一用 `EmptyState(icon, title, hint, action)`。必须说明"为什么是空的"和"下一步做什么"，并提供一个主操作。取代 15 种 empty 类（D5）。
- **加载**：超过 300ms 才显示骨架屏；不允许出现"加载中..."纯文字闪烁。
- **错误**：局部错误显示在出错位置（`Status` 组件），全局错误用 toast，toast 只保留一套（D11）。
- **弹层**：只保留 `Dialog` 和 `Drawer`：带焦点陷阱，Esc 关闭，锁定背景滚动，关闭后焦点回到触发元素。
- **全局动作**（D10）：顶栏只保留"录入题目"；"重新扫描"移到仪表盘、题库、目录三个页面的本页工具栏里。见决策点 DP4。
- **表格**：表头固定；三种行态（悬停、选中、行内操作显示）；窄屏时降级为卡片列表，而不是横向截断（D4）。
- **图标**：统一使用 `ui/icon` 的 SVG sprite（1.5px 描边、24 网格，内部自绘约 40 个），全部去掉 emoji（D7）。
- **表单**：`Field` 统一 label、提示、错误的位置；原生 `select` 保留（可访问性最好），但统一外观和高度，这同时修掉 D3 的文字裁切；文件上传统一用 `FileDrop`（D6）。

---

## 5. 工具与门禁（让 CCW 靠脚本守规则，而不是靠记忆）

### 5.1 `tests/check_ui.py`（P0 新增）

对 `assets/app/**` 零容忍：

| 规则 | 内容 |
|---|---|
| R1 | 颜色字面量（hex、rgb/rgba/hsl）只允许出现在 `styles/tokens.css` |
| R2 | `font-size`、`line-height`、`font-weight` 必须用 token |
| R3 | `margin`、`padding`、`gap` 只能用 `var(--sp-*)`、`0` 或 `auto` |
| R4 | `border-radius`、`box-shadow`、`z-index`、`transition` 的时长和缓动只能用 token |
| R5 | `@media` 宽度只允许 760 / 1160 / 1500 |
| R6 | 模板里禁止 `style=` 和 `on[a-z]+=`；`innerHTML` 只允许出现在 `core/dom.js` |
| R7 | 遵守依赖方向（§3.3），feature 之间不得互相 import |
| R8 | 单个 JS 文件不超过 400 行，CSS 不超过 300 行 |
| R9 | 每个 `features/<x>/` 在 `AI/frontend/` 下都有对应分册，并在 `AGENTS.md` 映射表里 |

对旧文件采用棘轮机制：`tests/ui_baseline.json` 按文件记录 `on*=`、`innerHTML=`、`style=`、颜色字面量、硬编码字号的计数。计数只许减少，不许增加；减少后用 `--update-baseline` 下调。按文件分行存储，其他维护者并行修改时冲突最小。

### 5.2 Fixture Vault（P0 新增 `tests/fixtures/make_vault.py`）

- 生成两份数据：`full`（约 40 题，覆盖 4 科、LaTeX、长题面、图片、标记、若干 Session 和反馈历史，让图表和时间线有内容）和 `empty`（0 题，专门用于检查空状态）。
- 题目用 `Skills/mistake-card-creator/scripts/add_card.py` 创建（本轮已验证可用）；Session 和反馈通过本地 HTTP API 写入。
- 固定随机种子。截图时在页面里冻结 `Date`，保证两次截图结果一致。

### 5.3 前后截图对比（P0 新增 `tests/visual/run.py`）

- `run.py --ref <基线提交>`：用 `git worktree` 把基线检出到临时目录，基线和工作区各起一个实例、各用一份 fixture 副本。
- 截图矩阵：12 个页面加 gallery × 浅色/深色 × {1440×900, 390×844}。
- 用 Pillow 和 numpy 做像素差分，输出 `report.html`：左右对照、差异热区、每页差异比例。
- 不在仓库里存金标图，基线每次现拍，补丁里没有二进制文件。
- 同一脚本再附带运行时审计：每页字号种数、控件高度、小目标数量、带行内样式的元素数。§1.3 的数字就是这样测出来的，作为 §2 指标的自动检查。

### 5.4 测试分层

- 纯逻辑（html 转义、store、router 解析、format、页面 state 的 reducer）写成 `tests/app/*.test.mjs`，用 `node --test` 跑。
- 依赖 DOM 的（morph、事件委托、dialog 焦点陷阱）放在 `tests/app/browser.html`，由 playwright 打开并收集结果：`tests/app/run_browser.py`。
- 每个迁移页面都有一个主路径 E2E 脚本 `tests/e2e/<page>.py`（真实浏览器、隔离实例），满足 AGENTS.md"验证要打到用户能看见的那一层"。
- 门禁命令更新为：

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -q
node --test tests/*.js tests/app/*.test.mjs
python3 tests/app/run_browser.py
python3 tests/check_ui.py
python3 tests/check_contrast.py
python3 tests/check_docs.py --diff <基线>
python3 tests/visual/run.py --ref <基线>      # 报告人工审阅；差异必须逐项解释
```

### 5.5 文档与 AGENTS.md 同步

- 新增 `AI/frontend/architecture.md`：目录、依赖方向、页面契约、启动顺序、过渡桥。
- 新增 `AI/frontend/design-system.md`：§4 的内容加组件清单。
- `AI/frontend/shell.md` 的加载顺序章节随迁移逐步缩短，P8 时删除。
- `AGENTS.md` 映射表新增：`assets/app/core|styles|ui` 对应 architecture.md 和 design-system.md；`assets/app/features/<x>` 对应 `AI/frontend/<x>.md`；`tests/check_ui.py`、`tests/visual/` 对应 `AI/environment.md` 和 `AI/README.md`。
- `AI/optimization.md`：在对应期里把"CSS 重复定义""innerHTML + 行内 onclick""board.js 多职责"三条改为进行中或已完成，不要在多处重复挂同一条缺陷。

---

## 6. 分期执行

通用约定：

- P0 到 P6 第 5 轮：每期是一到数轮 CCW 会话，每期交付 zip、`changes-<日期>.patch`、`UPGRADE-<日期>.md`、任务日志和交接清单，在前一期合入后的新导出包上开工。
- 2026-09-26 起（U15）：
  - Codex 在本机分支上每页（展示板按子步骤）一个提交，回滚单位就是一个提交；
  - 每个提交都包含代码、测试、文档、任务日志和 progress 的更新；
  - 不再产出补丁、完整包、UPGRADE 和交接清单。
- 旧代码只能和它的替代品在同一期删除，而且要有截图对比作证。

### P0 基建与设计基线（执行者：CCW · 受限模式）

- 任务：
  - `check_ui.py` 加棘轮基线；`check_contrast.py`。
  - fixture 生成器；`visual/run.py`；运行时审计。
  - 核实 `recommend.js` 是否为死代码：先用 E2E 点遍复习调度页，确认后删除，否则保留并登记。
  - 起草 `design-system.md`。
- 用户可见交付：`tokens.css` 接入全站。语义 token 通过旧 token 别名驱动现有页面，并修正 §4.3 对比度检查不达标的组合。第一件交付物是审计报告：12 页的问题截图清单，作为后续各期的验收底稿。
- 验收：原门禁全绿；新增脚本自身有单测；截图差异只出现在修正过对比度的地方。

### P1 底座与外壳（执行者：CCW · 受限模式）

- 任务：
  - 实现 `core/` 全部模块和单测；`main.js`；过渡桥。
  - `init()` 移交给 `main.js`；hash 路由；`switchTab` 改为包装。
  - `_serve_asset` 加 ETag 和 304。
- 用户可见交付：外壳（侧栏、顶栏、工作台布局）迁到 `styles/shell.css`，按新尺度打磨：侧栏节奏、激活态、折叠动效；顶栏全局动作按 DP4 调整；移动端标题不再被挤压。刷新后停留在当前页。
- 验收：12 个页面都能通过路由进入；旧 `onclick` 全部正常；E2E 覆盖路由、刷新保持和浏览器后退；截图差异只出现在外壳区域。

### P2 组件库 v1 与 gallery（执行者：CCW · 受限模式）

- 任务：实现 §3.2 `ui/` 下的全部组件和 SVG 图标 sprite；`gallery.html` 按 §4.5 全覆盖；统一 toast，旧的三套先改为转调新实现。
- 用户可见交付：gallery 页本身；全站 toast、Dialog 统一，旧弹层通过转调接入；全站原生 select 和按钮统一高度与外观（通过 legacy-bridge 层给旧类名套上新样式）。修掉 D2、D3。
- 验收：gallery 截图浅色/深色 × 两种密度全部审阅；每个组件的浏览器单测通过。

### P3 试点：即时练习（执行者：CCW · 受限模式）

- 为什么选它：规模小（177 行），但每次判定都整卡重建，重构效果最明显，也最能验证 morph 和 KaTeX 缓存。
- 任务：`features/instant/` 完整实现；快捷键接入 `keys.js`；删除 `instant.js` 以及 `styles.css` 里即时练习相关的规则。
- 用户可见交付：判定时题面不再闪烁、焦点不丢；空状态、加载状态和队列按新规范重做；移动端单栏布局。
- 验收：E2E 主路径（加载推荐 → 翻答案 → 判定 → 提交）；本页字号不超过 6 种、没有小目标；`ui_baseline` 计数下降。

### P4 反馈录入（执行者：CCW · 受限模式）

- 已有 `fbRender*` 拆分和事件委托，迁移成本低。三栏工作台和提交结果弹窗改用 Dialog；空状态修掉 D5。
- 验收：E2E（选 Session → 判定 → 导入 JSON → 提交）；`tests/test_feedback_ui.js` 迁到新模块后仍然通过。

### P5 题库与共享题目视图（执行者：CCW · 受限模式，原计划两轮，实际分四轮，轮次与内容见 progress.md §5）

- `domain/question/`：Markdown 和 KaTeX 渲染按内容哈希缓存，`qview` 与记录模块从 `questions.js`、`qview.js` 迁入。
- `features/questions/`：表格和画廊双视图、筛选抽屉、批量条、列设置、视图预设；窄屏降级为卡片列表（D4）；`domain/labels/`。
- 验收：题库相关 Node 测试迁移后全绿；E2E（筛选 → 切换视图 → 打开详情 → 翻页 → 打标记 → 批量）；过渡桥为 feedback 和 export 保留的 qview 调用逐条登记。

### P6 其余中小页面（执行者：第 1–5 轮 CCW · 受限模式；其余 Codex · 完整模式）

- 迁移仪表盘（修掉 D8）、数据复盘（清掉 145 处行内样式）、目录、历史记录、报告（用 FileDrop 修掉 D6）、设置、复习调度、录入题目和收件箱入口。
- `DATA` 的所有权反转到 `domain/`（§3.6）。`inbox_mobile.html` 接入 tokens 和 base。
- 验收：每页一个 E2E；每页都达到 §2 的指标。

### P7 展示板（执行者：Codex · 完整模式，按子步骤提交）

- 最大的一块（106KB）。先搬纯函数和测试，再拆成保存队列、打印协调、拖拽排序、版面设置、选板浮层五个子模块，最后迁 UI。预览 iframe 的协议不变，iframe 节点标 `data-morph="skip"`。
- 验收：`test_board_*.js`、`smoke_board_*.py` 全绿；E2E（建板 → 加题 → 排序 → 版面设置 → 打印预览 → 仅补印新增）。

### P8 收尾（执行者：Codex · 完整模式；部署另行授权）

- Codex：
  - 删除 `styles.css`、旧 token 别名、`legacy-bridge.js`；`omrs_dashboard.html` 只保留外壳骨架。
  - `ui_baseline.json` 归零后删除，棘轮改为全局零容忍。
  - 文档定稿：`shell.md` 加载顺序章节删除，`optimization.md` 三条关闭。
- 部署（用户授权后执行，执行者由用户指定）：生产重启、远端设备和手机端验收。
- 验收：§2 全部指标达成。

---

## 7. 风险与对策

| 风险 | 对策 |
|---|---|
| 模块执行时机导致旧代码调用落空 | §3.7：`init()` 移到 `main.js`；过渡桥集中登记；P1 的 E2E 覆盖全部页面入口 |
| morph 与 KaTeX、iframe、第三方 DOM 冲突 | `data-hash` 跳过、`data-morph="skip"`；P3 试点专门验证 |
| 迁移期间其他维护者修改同一页面，补丁冲突 | 每期开工时在交接清单里声明"迁移中页面冻结表"。冻结期内对该页的功能需求改在新结构上实现，或者等本期合入后再做 |
| `ui_baseline.json` 被并行改动打乱 | 按文件分行存储；冲突时用 `check_ui.py --update-baseline` 重算，只允许数值下降 |
| 截图对比受时间和随机因素干扰 | 固定 fixture 种子、冻结 `Date`、关闭动效再截图 |
| 单轮 CCW 预算不够 | 每期拆成"用户可见主体"和"收尾"两部分，先交主体；超预算按 AGENTS 第 5 条提前收口，并说明进度 |
| 打印和导出链路受影响 | 范围外（§3.9）；P7 跑完整套 board 冒烟测试 |
| 节点测试无法覆盖 DOM | §5.4：浏览器单测加 E2E |

---

## 8. 决策点（按推荐项执行，除非用户另行指定）

| 编号 | 问题 | 推荐（默认执行） | 备选及影响 |
|---|---|---|---|
| DP1 | 渲染层 | 零依赖 `html``` + `morph`（§3.5） | Preact + htm（约 5KB）：需 Hermes 联网放进 `vendor/`；P1 的 `core/dom.js` 换成适配层，页面写法改为组件，P3 起迁移成本增加约 30% |
| DP2 | 正文字号 | 正文 14px，紧凑模式 13px；html 根字号保持 15px，新 token 用 px，避免影响旧页面 | 正文 13px：更密，但 D1 只能部分解决 |
| DP3 | 路由 | hash 路由 `#/page`，后端不用改 | History API：需要后端为所有页面路径回退到 HTML |
| DP4 | 顶栏全局动作 | 只保留"录入题目"；"重新扫描"放进仪表盘、题库、目录三页 | 保持现状：D10 不修 |

---

## 9. 交接清单模板（2026-09-26 起停用）

2026-09-26 起不再写交接清单（U15），部署与回滚清单见 progress §8。下表留作记录。

| 步骤 | 执行者 / 模式 | 验收标准 |
|---|---|---|
| 备份工作区，`git status --short` 记录现状 | Hermes 或 Codex / 完整 | 记录已写入 |
| `git apply --3way changes-<日期>.patch` | Hermes 或 Codex / 完整 | 没有冲突；有冲突就逐个 hunk 合并 |
| 跑 §5.4 全部门禁 | Hermes 或 Codex / 完整 | 计数与 UPGRADE 文档一致 |
| `check_docs.py --write-log-index` | Hermes 或 Codex / 完整 | `log.md` 包含本期日志 |
| 生产重启（需用户授权） | Hermes 或 Codex / 完整 | `/api/auth/session` 正常；12 个页面能打开 |
| 远端设备和手机端走一遍主路径 | Hermes 或 Codex / 完整 | 与 CCW 截图报告一致 |

---

## 附：本轮实际执行与未执行

- **已执行**：
  - 环境探测；把导出包提交为基线；三项门禁（137 / 140 / 0）。
  - 临时 Vault 放 8 题，隔离实例运行在 18471 端口。
  - 12 页 × 浅色/深色截图，4 页移动端截图；运行时审计（字号、圆角、行内样式、小目标、控制台错误）。
  - 静态统计（§1.2）。
- **未执行**：没有修改仓库；没有写任务日志（只读规划，符合 AGENTS.md）；fixture、截图脚本、`check_ui.py` 都还没有落地（属于 P0）；没有做生产验证。
