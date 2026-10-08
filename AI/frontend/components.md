# 前端：ui 组件库与 gallery

> **速查**
> - 职责：`assets/app/ui/` 的无业务组件与自绘 SVG 图标、`assets/app/core/` 的渲染底座（`html```、`render`）、入口 `assets/app/main.js`、组件陈列页 gallery
> - 入口：`assets/app/main.js`（`type="module"`）、`assets/app/styles/index.css`、`assets/app/gallery.html`
> - 不变量：全站共用 `assets/app/ui/` 的 toast 与对话框；`innerHTML` 只出现在 `assets/app/core/dom.js`；页面直接导入组件，样式经 `styles/ui.css` 进入 `ui` 层
> - 必跑测试：`tests/app/run_browser.py`、`tests/app/html.test.mjs`、`tests/e2e/ui_bridge.py`、`tests/test_app_browser.py`、`tests/check_ui.py`
> - 相关：`AI/frontend/design-system.md`（token 与门禁）、`AI/frontend/shell.md`（加载顺序）

## 1. 文件与加载

```
assets/app/
├── package.json          {"type":"module"}：使本目录的 JS 按 ES Module 解析
├── main.js               模块入口：安装共用组件、装配页面并启动路由（见 AI/frontend/architecture.md）
├── core/html.js          html`` 标签模板（默认转义）、raw()、escape()、cls()
├── core/dom.js           render / morph / toFragment / toElement：唯一写 innerHTML 的文件
├── ui/<组件>.js + .css   每个组件一对文件；overlay.js 是 dialog / drawer 共用的模态底座
├── styles/index.css      样式总入口（@layer 分层）
├── styles/ui.css         汇总 ui/*.css 与共享动效关键帧
├── styles/gallery.css    陈列页版式
└── gallery.html、gallery*.js  组件陈列页
```

- `omrs_dashboard.html` 加载本地字体、`tokens.css` 和 `index.css`；`index.css` 的层级是 `vendor`（KaTeX）< `base` < `ui` < `shell` < `domain` < `features` < `utilities`。`styles/ui.css` 汇总组件样式并进入 `ui` 层。
- `main.js` 是页面底部唯一的模块入口：先安装图标和提示，再建立外壳、连接领域服务、加载初始数据并启动路由。业务页面直接导入所需组件，不经过全局桥。
- 浏览器下限：Chrome 99、Safari 15.4、Firefox 97（`@layer` 与 `<dialog>`）。popover 顶层需要 Safari 17；更旧的浏览器里菜单、提示、toast 退回 `--z-*` 层级。

## 2. 渲染约定

- 组件函数返回 `html``` 的结果（HtmlResult），插值默认转义；确需原样输出时显式写 `raw()`。
- 只能经 `core/dom.js` 写进文档：`render(el, result)` 整体替换，`toElement(result)` 解析出节点（已导入当前文档）。传普通字符串会抛 TypeError。
- 需要反复重绘的视图用 `morph(root, result)` 做差量更新；事件用 `data-action` 委托。二者与快捷键、store、路由的约定见 `AI/frontend/architecture.md` §4。

## 3. 组件清单

| 组件 | 调用 | 要点 |
|---|---|---|
| 按钮 | `button({label, variant, size, icon, iconOnly, loading, pressed})` | `.ui-btn`；variant：default / primary / ghost / danger；size：sm 28 / md 32 / lg 40；仅图标时 label 作 aria-label |
| 图标 | `icon(name, {label, size})`、`installIcons()` | 自绘 61 个，24 网格、1.5 描边；sprite `#ui-icon-sprite`，symbol 名 `ic-<name>`；未知名字抛错 |
| 字段 / 输入 | `field({label, id, hint, error, required, control})`、`input()`、`textarea()` | 统一 label、提示、错误的位置；错误 role=alert |
| 选择框 | `select({id, options, value, size})` | 原生 select 统一外观；上下内边距为 0，文字不裁切（D3） |
| 可搜索建议 | `createCombobox(host, {options,onSelect})` | 原生 input + body 浮层；分类按科目给候选，输入法组合期间不选，方向键 / Enter / Esc / Tab 可用；手机建议层贴实际可视区域底部 |
| 折叠区域 | 原生 `<details class="ui-disclosure">` | 统一摘要箭头、悬停、聚焦与展开状态；保留原生键盘语义 |
| 开关 | `switchControl({id, label, checked})` | 原生 checkbox + role=switch |
| 分段 | `segmented({name, label, options, value, size})` | 原生 radio 组 |
| 标签页 | `tabs({...})` + `bindTabs(list)` | ←/→/Home/End 自动激活，按 aria-controls 切面板，派发 `ui-tabs:change` |
| 标签 / 徽标 | `tag({label, tone, removable})`、`badge(n, {tone, max, dot})` | 六种色调；徽标超过上限显示 99+ |
| 卡片 / 统计 | `card({title, subtitle, actions, body, footer, interactive})`、`stat({label, value, unit, delta, trend, size})` | stat 的 lg（40px display）全站只给仪表盘首屏 |
| 表格 | `table({columns, rows, rowKey, selected, empty, stack})` | 表头固定；悬停 / 选中 / 行内操作三态；stack 在 ≤760px 变卡片列表（D4），表头只留给读屏（1px 裁剪、表头行无内边距，不算作溢出） |
| 对话框 | `dialog(spec)`、`confirm(title, o)`、`prompt(title, value, o)` | 见 §4 |
| 图片预览 | `openImageViewer(images, initial)` | 站内模态预览、缩放、切图、下载、新标签次级操作；Esc / 浏览器返回键关闭并恢复焦点 |
| 抽屉 | `openDrawer({title, body, content, footer, side, dismissible, returnFocus, onClose})` | 与对话框共用模态底座；窄屏变底部面板 |
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

图标表（`ui/icon.js`）另有 `stop`、`arrow-up`、`arrow-down`、`undo`、`message`、`paperclip`，供助手页使用；侧栏入口的 `#i-sparkle` 在 `omrs_dashboard.html` 的内联雪碧图里。

## 4. 弹层与通知

- `dialog` / `drawer` 用 `<dialog>.showModal()` 进入浏览器顶层，背景自动 inert。`dialog` 面板是可收缩的 flex 列，受限高度时由正文区承担滚动；`overlay.js` 管理 Esc 与遮罩关闭（按下和松开都落在遮罩上才算）、Enter 确认（textarea、按钮、链接里的 Enter 除外）、关闭动画、焦点还给触发元素、`html.ui-scroll-lock` 锁定背景滚动、嵌套时只关闭最上层。
- Esc 在 document 捕获阶段拦下并 `stopPropagation`，避免同一次按键继续作用到下层弹层。危险确认默认聚焦「取消」。
- `dialog(spec)` 返回 `{ok, values}`，values 按 id 收集对话框内的 input / select / textarea（复选与单选取 checked）。`body` 可以是 `html``` 结果；传字符串时会原样插入，调用方必须先转义不可信内容；`content` 可以是 DOM 节点。
- `dialog(spec)` 另收（P5 第 3 轮起）：`size:'xl'`（1180，题目弹窗与 Markdown 编辑器）、`id`、`onOpen(el)`、`onOk(values, el)`（异步；等待时确定按钮 `aria-busy` 并禁用，返回 false 或抛错则留在对话框，用于保存失败）、`dismissible` 为函数（每次 Esc / 点遮罩时再问，如「有未保存修改」）、`returnFocus()`（关闭后优先把焦点交给它返回的元素）；`closeDialog(el)` 按元素关闭。多行文本里的 Enter 不确认，Ctrl / ⌘ + Enter 在任何位置都确认。
- **客人浮层**：标记选择器和选板浮层通过 `overlay.js` 的 `hostGuest(node, {close, escape})` / `releaseGuest(node)` 挂到最上层模态对话框中；没有对话框时放进 body。登记后 Esc 与 Enter 先让给客人（`escape:true` 的由 overlay 代为关闭），宿主关闭时先关客人；客人自行关闭时调用 `releaseGuest`，必要时把焦点还给触发元素。`topModal()`、`guestOpen()` 供快捷键判断。
- 关闭中的对话框带 `.is-closing`，退场动画期间仍是 `[open]`：「有对话框打开」的守卫写成 `dialog[open]:not(.is-closing)`（`core/keys.js`、反馈页 paste 守卫）。
- toast 容器是 aria-live 区域。支持 popover 的浏览器把 toast 容器、菜单、提示放进顶层，每来一条 toast 重新置顶；模态对话框开着时，它外面的 toast 只能看、不能点。

## 5. 组件接入

页面直接从 `assets/app/ui/` 导入组件和弹层函数，视图用 `html``` 构建，通过 `render()` 或 `morph()` 写入 DOM。按钮、输入框和选择框使用 `ui-btn`、`ui-input`、`ui-select`、`ui-textarea`；全站组件样式在 `styles/ui.css` 汇总。主站没有旧类名样式层或运行时过渡桥。

## 6. gallery 与测试

- 陈列页：服务运行时打开 `/assets/app/gallery.html`，地址参数 `theme=light|dark`、`density=comfortable|compact`，页头也能切换。组件示例覆盖默认、悬停、按下、焦点、禁用、加载中、空、错误、骨架、长文本溢出；浮层有静态预览加可点的真实演示。当前陈列页仍含一节旧类名静态示例，不属于主站组件契约。
- `python3 tests/app/run_browser.py`：自带静态服务器，用 playwright 跑 `tests/app/browser_tests.js` 的组件单测（对话框焦点与 Esc、toast 队列、菜单键盘、拖放、D2 / D3 高度等）；`--shots DIR` 另存 gallery 五张整页截图（浅 / 深 × 舒适 / 紧凑，外加 390 宽手机）。没有 playwright 时退出码 2，`tests/test_app_browser.py` 据此跳过。
- `node --test tests/app/html.test.mjs`：覆盖 `html``` 的转义规则。
- `python3 tests/e2e/ui_bridge.py`：用隔离 Vault 和真实浏览器验证样式层、原生提示与对话框、控件高度及 13 页切换无脚本错误。

抽屉的 dismissible 可为每次关闭时求值的函数，关闭按钮、Esc 与遮罩均检查它；returnFocus 返回关闭后应聚焦的现存元素，用于宿主内容刷新后的入口恢复。调用 close() 用于已通过宿主守卫的关闭及卸载清理。
