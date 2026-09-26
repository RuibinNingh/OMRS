# 前端：ui 组件库、过渡桥与 gallery

> **速查**
> - 职责：`assets/app/ui/` 的无业务组件（23 个 + 自绘 SVG 图标）、`assets/app/core/` 的渲染底座（`html```、`render`）、旧入口过渡桥（`assets/app/legacy-bridge.js`、`assets/app/styles/legacy-bridge.css`）、组件陈列页 gallery
> - 入口：`assets/app/main.js`（`type="module"`）、`assets/app/styles/index.css`、`assets/app/gallery.html`
> - 不变量：全站只有一套 toast、一套对话框；旧 `uiToast` / `uiDialog` / `uiPrompt` / `uiConfirm` 签名不变、只转调；`innerHTML` 只出现在 `assets/app/core/dom.js`；过渡桥每条注明旧调用方与删除期，P8 清空
> - 必跑测试：`tests/app/run_browser.py`、`tests/app/html.test.mjs`、`tests/e2e/ui_bridge.py`、`tests/test_app_browser.py`、`tests/check_ui.py`
> - 相关：`AI/frontend/design-system.md`（token 与门禁）、`AI/frontend/shell.md`（加载顺序）

## 1. 文件与加载

```
assets/app/
├── package.json          {"type":"module"}：只作用于本目录，旧脚本与 node 测试的 require 不受影响
├── main.js               模块入口：装过渡桥、启动外壳与路由、调用 init()（见 AI/frontend/architecture.md）
├── legacy-bridge.js      过渡桥（JS）：把新组件挂到旧入口
├── core/html.js          html`` 标签模板（默认转义）、raw()、escape()、cls()
├── core/dom.js           render / morph / toFragment / toElement：唯一写 innerHTML 的文件
├── ui/<组件>.js + .css   每个组件一对文件；overlay.js 是 dialog / drawer 共用的模态底座
├── styles/index.css      样式总入口（@layer 分层）
├── styles/ui.css         汇总 ui/*.css 与共享动效关键帧
├── styles/legacy-bridge.css  过渡层：旧类名套新外观
├── styles/gallery.css    陈列页版式
└── gallery.html、gallery*.js  组件陈列页
```

- `omrs_dashboard.html` 只引 `tokens.css` 与 `index.css`。层级从低到高：`vendor`（KaTeX）< `legacy`（旧 `assets/styles.css`）< `base` < `ui` < `shell`（侧栏、顶栏、工作台）< `domain` < `features` < `utilities` < `legacy-bridge`。未分层的规则总压过分层规则，所以新旧样式都必须进层。
- `main.js` 以 `<script type="module">` 挂在 `app.js` 之后，浏览器在全部经典脚本之后才执行它。桥装好前，旧代码的调用先进 `window.__omrsUiPending` 队列，装好后按顺序补发。
- 浏览器下限：Chrome 99、Safari 15.4、Firefox 97（`@layer` 与 `<dialog>`）。popover 顶层需要 Safari 17；更旧的浏览器里菜单、提示、toast 退回 `--z-*` 层级。

## 2. 渲染约定

- 组件函数返回 `html``` 的结果（HtmlResult），插值默认转义；确需原样输出时显式写 `raw()`。
- 只能经 `core/dom.js` 写进文档：`render(el, result)` 整体替换，`toElement(result)` 解析出节点（已导入当前文档）。传普通字符串会抛 TypeError。
- 需要反复重绘的视图用 `morph(root, result)` 做差量更新；事件用 `data-action` 委托。二者与快捷键、store、路由的约定见 `AI/frontend/architecture.md` §4。

## 3. 组件清单

| 组件 | 调用 | 要点 |
|---|---|---|
| 按钮 | `button({label, variant, size, icon, iconOnly, loading, pressed})` | `.ui-btn`；variant：default / primary / ghost / danger；size：sm 28 / md 32 / lg 40；仅图标时 label 作 aria-label |
| 图标 | `icon(name, {label, size})`、`installIcons()` | 自绘 55 个，24 网格、1.5 描边；sprite `#ui-icon-sprite`，symbol 名 `ic-<name>`；未知名字抛错 |
| 字段 / 输入 | `field({label, id, hint, error, required, control})`、`input()`、`textarea()` | 统一 label、提示、错误的位置；错误 role=alert |
| 选择框 | `select({id, options, value, size})` | 原生 select 统一外观；上下内边距为 0，文字不裁切（D3） |
| 开关 | `switchControl({id, label, checked})` | 原生 checkbox + role=switch |
| 分段 | `segmented({name, label, options, value, size})` | 原生 radio 组 |
| 标签页 | `tabs({...})` + `bindTabs(list)` | ←/→/Home/End 自动激活，按 aria-controls 切面板，派发 `ui-tabs:change` |
| 标签 / 徽标 | `tag({label, tone, removable})`、`badge(n, {tone, max, dot})` | 六种色调；徽标超过上限显示 99+ |
| 卡片 / 统计 | `card({title, subtitle, actions, body, footer, interactive})`、`stat({label, value, unit, delta, trend, size})` | stat 的 lg（40px display）全站只给仪表盘首屏 |
| 表格 | `table({columns, rows, rowKey, selected, empty, stack})` | 表头固定；悬停 / 选中 / 行内操作三态；stack 在 ≤760px 变卡片列表（D4），表头只留给读屏（1px 裁剪、表头行无内边距，不算作溢出） |
| 对话框 | `dialog(spec)`、`confirm(title, o)`、`prompt(title, value, o)` | 见 §4 |
| 抽屉 | `openDrawer({title, body, content, footer, side, onClose})` | 与对话框共用模态底座；窄屏变底部面板 |
| 菜单 | `openMenu(anchor, items)` → value 或 null | ↑/↓ 跳过禁用项、Esc 还焦点、点外面关闭；锚点在对话框里时挂进对话框 |
| 通知 | `toast(text, {kind, actions, duration})` | kind：info / ok / warn / error；最多 3 条、同文同类合并、悬停或聚焦时暂停 |
| 空状态 | `empty({icon, title, hint, action, compact, bordered})` | 说明为什么是空的、下一步做什么，并给一个主操作（D5） |
| 骨架屏 | `skeleton({lines, avatar, block})`、`showAfter(el, 300)` | 超过 300ms 才出现 |
| 局部状态 | `status({tone, text, block})`、`dot(tone)` | 错误写在出错位置；danger 用 role=alert（D11） |
| 进度 | `progress({value, max, label, tone, size, meta})`、`spinner()` | 原生 progress；不传 value 为不定进度 |
| 提示 | 元素写 `data-tooltip`，页面调一次 `bindTooltips(document)` | 悬停 500ms 或键盘聚焦时出现，Esc 隐藏 |
| 快捷键 | `kbd('Ctrl', 'K')` | 键帽与组合键 |
| 文件拖放 | `filedrop({id, title, hint, accept, multiple})` + `bindFileDrop(zone, onFiles, onReject)` | 取代原生「Choose File」（D6）；不符合 accept 的文件滤掉并标 is-error，可由 onReject 给出就地原因 |

状态类 `is-hover` / `is-active` / `is-focus` 只供 gallery 固定展示交互态；业务代码用真实伪类与 `aria-pressed`、`aria-selected`、`aria-invalid`、`aria-busy`。

## 4. 弹层与通知

- `dialog` / `drawer` 用 `<dialog>.showModal()` 进浏览器顶层，天然盖过旧代码 z-index 999 的 `.modal-overlay`；背景自动 inert，即焦点陷阱。`overlay.js` 另补：Esc 与遮罩关闭（按下和松开都落在遮罩上才算）、Enter 确认（textarea、按钮、链接里的 Enter 除外）、关闭动画、焦点还给触发元素、`html.ui-scroll-lock` 锁定背景滚动、嵌套时 Esc 只关最上层。
- Esc 在 document 捕获阶段拦下并 `stopPropagation`，旧代码挂在 document 上的 Esc 监听不会顺带关掉下层弹层。危险确认默认聚焦「取消」。
- `dialog(spec)` 返回 `{ok, values}`，values 按 id 收集对话框内的 input / select / textarea（复选与单选取 checked）。`body` 可以是 `html``` 结果，也可以是旧代码传入、已由调用方转义的 HTML 字符串；`content` 可以是 DOM 节点。
- `dialog(spec)` 另收（P5 第 3 轮起）：`size:'xl'`（1180，题目弹窗与 Markdown 编辑器）、`id`、`onOpen(el)`、`onOk(values, el)`（异步；等待时确定按钮 `aria-busy` 并禁用，返回 false 或抛错则留在对话框，用于保存失败）、`dismissible` 为函数（每次 Esc / 点遮罩时再问，如「有未保存修改」）、`returnFocus()`（关闭后优先把焦点交给它返回的元素）；`closeDialog(el)` 按元素关闭。多行文本里的 Enter 不确认，Ctrl / ⌘ + Enter 在任何位置都确认。
- **客人浮层**（`overlay.js` 的 `hostGuest(node, {close, escape})` / `releaseGuest(node)`，旧代码经过渡桥 `__omrsUi.host` / `release`）：旧浮层叠在模态对话框上时放进最上层对话框，否则被 inert；没有对话框时放进 body。登记后 Esc 与 Enter 先让给客人（`escape:true` 的由 overlay 代为关闭），点遮罩只关客人（客人自己处理点外面），宿主关闭时先关客人；客人自行关闭时 `releaseGuest`，焦点随节点丢失时还给打开它的元素。`topModal()`、`guestOpen()` 供快捷键让位判断。
- 关闭中的对话框带 `.is-closing`，退场动画期间仍是 `[open]`：「有对话框打开」的守卫写成 `dialog[open]:not(.is-closing)`（`core/keys.js`、反馈页 paste 守卫）。
- toast 容器是 aria-live 区域。支持 popover 的浏览器把 toast 容器、菜单、提示放进顶层，每来一条 toast 重新置顶；模态对话框开着时，它外面的 toast 只能看、不能点。

## 5. 过渡桥

- JS：`assets/core.js` 的 `uiToast` / `uiDialog` / `uiPrompt` / `uiConfirm` 只剩转调（经 `window.__omrsUi`），签名与返回值不变；收件箱 `ibToast` 转调 `uiToast`。旧 `uiToast` 不传 kind 时按旧语义映射为 ok（成功样式）；新组件自身的默认是 info。
- 「有弹层打开时不响应」的守卫写成 `document.querySelector('.modal-overlay.open, dialog[open]')`（`assets/board.js`）；新增守卫写 `dialog[open]:not(.is-closing)`。选板浮层的「点外面关闭」只让「不包含浮层」的弹层挡住（宿主对话框不算）；已迁到新页面的快捷键走 `core/keys.js`，它自带「有弹层时不响应」（`inDialog`）。
- CSS：`styles/legacy-bridge.css` 给旧 `.btn` 系列、`.input` / `select.input` / `textarea.input`、旧 `.modal` 外壳套新外观；旧 `styles.css` 里被接管的基础规则已删除。桥只写外观，不写 z-index 与布局尺寸。
- 旧代码调用的题目视图全局（`renderMdContent`、`ensureQuestionDetail`、`qvHtml`、`qvRender`、`viewQ`、`closeModal`、练习记录函数等）由 `legacy-bridge.js` 的 `installQuestionBridge` 从 `assets/app/domain/question/` 挂上，逐条注明调用方；它同时调 `bindQuestionDom()` 绑定 qview 的按钮委托、题图降级与弹窗 ←/→。
- 统计数据的全局入口（`reloadData`、只读 `QUESTION_CACHE` / `QUESTION_PENDING`）与旧刷新链钩子（`legacyDataRefresh()`，v1.25.1 起不再包含数据复盘的图）由 `installDataBridge` 挂上（v1.25.0 起，实现在 `assets/app/domain/data.js` 与 `domain/question/mount.js`），调用方见 `AI/frontend/architecture.md` §6。
- 复习调度与 Session 的旧入口（`refreshSessions`、`schOpenPlan`、`confirmScheduleV2`、`loadRecommendationsV2`、`renderUnifiedListV2`、`renderExportPicker`、`downloadExportResponse` 与只读 `SCH_VIEW`、`REC_DATA_V2` 等）由 `installScheduleBridge` 挂上（v1.25.2 起），调用方见 `AI/frontend/architecture.md` §6。
- 旧代码调用的标记全局（`lblChip` / `lblChips`、`labelHex`、`nextLabelColor`、选择器与管理的数据函数）由 `installLabelsBridge` 从 `assets/app/domain/labels/` 挂出（P5 第 4 轮起），逐条的调用方见 `AI/frontend/architecture.md` §6。
- 删除期：题库工具栏一段已随题库页迁走删除（P5 第 2 轮）；展示板小按钮一段 P7；旧弹层外壳随各弹层迁到 Dialog / Drawer（P5–P7）；其余 P8 整个文件删除，届时 `legacy-bridge.js` 也必须为空。

## 6. gallery 与测试

- 陈列页：服务运行时打开 `/assets/app/gallery.html`，地址参数 `theme=light|dark`、`density=comfortable|compact`，页头也能切换。每个组件一节，覆盖默认、悬停、按下、焦点、禁用、加载中、空、错误、骨架、长文本溢出；浮层有静态预览加可点的真实演示；最后一节是旧类名桥接。
- `python3 tests/app/run_browser.py`：自带静态服务器，用 playwright 跑 `tests/app/browser_tests.js` 的组件单测（对话框焦点与 Esc、toast 队列、菜单键盘、拖放、D2 / D3 高度等）；`--shots DIR` 另存 gallery 五张整页截图（浅 / 深 × 舒适 / 紧凑，外加 390 宽手机）。没有 playwright 时退出码 2，`tests/test_app_browser.py` 据此跳过。
- `node --test tests/*.js tests/app/*.test.mjs`：覆盖 `html``` 的转义规则。
- `python3 tests/e2e/ui_bridge.py`：生成 fixture Vault、起隔离实例，在真实页面里验过渡桥、旧弹层之上叠新对话框、D2 / D3 与 12 页无报错。

## 7. 待办

- 随页面迁移：emoji 图标换 `icon()`（D7）、原生文件选择换 FileDrop（D6）、零散 empty 类换 `empty()`（D5）、旧 `.modal-overlay` 弹层迁到 Dialog / Drawer，并删掉 legacy-bridge 对应段落。
- 旧 `styles.css` 的全局元素规则仍在 legacy 层生效。其中 `header{padding;border-bottom;margin-bottom}` 会漏进用 `<header>` 的组件：P4 起 `.ui-dialog__head`、`.ui-card__head` 显式清零 margin / padding / border，`.ui-drawer__head` 清零 margin（P2 起所有对话框标题下那条粗线与空白即此）。gallery 不加载旧样式，这类问题只在真实页面里看得到；新组件用 `<header>` / `<footer>` 等元素时同样要清。
- 已知遗留：展示板列表里的小按钮只统一了外观（P7）。即时练习迁到新架构后留给旧代码的入口（`instLoadPractice`、只读 `INSTANT_QUEUE`）、反馈录入留给旧代码的入口（`fbSessionProgress` 再导出，`renderFb` / `resetFeedbackForm` / `fbClearResults` 改发 bus 事件）也在 `legacy-bridge.js`，见 `AI/frontend/architecture.md` §6。
