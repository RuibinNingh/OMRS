# 前端：架构（目录、依赖方向、页面契约、启动顺序、过渡桥）

> **速查**
> - 职责：`assets/app/` 的分层与依赖方向、`core/` 底座（渲染、事件、快捷键、状态、总线、路由、请求、格式化）、页面契约、启动顺序、过渡桥与静态资源缓存
> - 入口：`assets/app/main.js`、`assets/app/shell.js`、`assets/app/legacy-pages.js`、`assets/app/core/router.js`
> - 不变量：模块入口晚于全部经典脚本执行，`init()` 只由 `main.js` 调用；`switchTab` 只是 `router.go` 的一行包装；页面之间不互相 import，联动走 bus；`innerHTML` 只在 `core/dom.js`；过渡桥与旧页面登记表到 P8 必须清空
> - 必跑测试：`tests/app/core.test.mjs`、`tests/app/run_browser.py`、`tests/e2e/shell_router.py`、`tests/test_asset_cache.py`
> - 相关：`AI/frontend/components.md`（ui 组件与 gallery）、`AI/frontend/shell.md`（外壳、加载顺序）、`AI/frontend/design-system.md`（token 与门禁）

## 1. 目录与依赖方向

```
assets/app/
├── main.js            启动入口（见 §2）
├── shell.js           外壳：路由生命周期 → 顶栏标题、侧栏高亮、面板显隐、工作台布局；暴露 window.__omrs
├── legacy-pages.js    旧页面登记表（过渡）：原 switchTab 的标题表、工作台列表、进入钩子
├── legacy-bridge.js   过渡桥：旧 uiToast / uiDialog 等转调新组件（见 AI/frontend/components.md）
├── core/              与业务无关的底座：html、dom、events、keys、store、bus、router、api、format
├── ui/                无业务组件
├── styles/            tokens、index（@layer 总入口）、base、ui、shell、legacy-bridge、gallery
├── domain/            业务领域：question/（共享题目视图，已是真实现）+ 过渡期适配器（新页面只经这里碰旧全局，见 §5）
└── features/          已迁移的页面：questions/、instant/、feedback/、dashboard/、data/、schedule/、history/、catalog/、reports/、settings/
```

依赖方向由 `tests/check_ui.py` 的 R7 强制：`core` 只依赖 `core`；`ui` 依赖 `ui`、`core`；`domain` 依赖 `domain`、`ui`、`core`；`features/<页>` 只依赖本页、`domain`、`ui`、`core`，页面之间禁止互相 import，跨页联动走 bus。根目录的 `main.js`、`shell.js`、`legacy-pages.js`、`legacy-bridge.js` 是装配层，不受 R7 限制，也不放业务逻辑。

## 2. 启动顺序

模块脚本在全部经典脚本之后才执行，所以启动权交给 `main.js`，`app.js` 不再自调用 `init()`：

1. `installLegacyBridge(window)`：注入图标 sprite、绑定提示；旧 `uiToast` 等转调新组件，桥装好之前排队的调用按顺序补发。
2. `startShell(window, LEGACY_PAGES)`：建 bus、store、router，登记页面，绑定事件委托与快捷键；随即按当前地址显示对应页面的外壳（刷新时不先闪一下仪表盘）。
3. `await window.init()`：旧启动流程（读标记、`reloadData()`、历史、Session、展示板、行动推荐）。出错只记日志，不阻断路由。
4. `router.start()`：进入当前页（执行它的进入钩子），开始响应前进 / 后退。

## 3. 路由与页面契约

- 地址形如 `#/questions`。`router.go(id)` 同步切页并 `pushState` 一条历史（旧代码与冒烟测试都假定 `switchTab` 之后页面立即可见）；未登记的 id 落到仪表盘；地址无效时改写成 `#/dashboard`。
- 地址变成非路由 hash（例如 `href="#"` 的链接）时不切页，并把地址改回当前页，保证刷新仍停在原页。
- 侧栏导航是 `<a class="tab" data-tab="页面" href="#/页面">`：普通点击同步切页；带修饰键时交给浏览器（新标签页打开）。旧 `onclick="switchTab(...)"` 继续可用。
- 旧页面登记项：`{ id, title, workbench, enter(win) }`。`enter` 每次进入该页时调用，与原 `switchTab` 的 if 链相同，不等待其完成。
- 新页面契约（`features/<页>/index.js` 导出 `page`）：`{ id, title, workbench, mount(root, ctx) → unmount, actions, keys }`。`root` 是 `#panel-<id>`，`ctx = { bus, store, router }`；离开页面时执行 `mount` 返回的卸载函数。`actions` 与 `keys` 由外壳在登记页面时一次性注册，动作命名空间与快捷键作用域都是页面 id；处理函数只在挂载期间生效。迁移一页时，从 `legacy-pages.js` 删掉对应一项，在 `main.js` 把页面契约并进登记表。范例：`features/instant/`（见 `AI/frontend/instant.md`）；`features/feedback/`（见 `AI/frontend/feedback.md`）另示范了挂载期的 document 级监听（paste）要在卸载函数里移除。
- 跨页共用的按钮走外壳登记的全局动作 `app.*`（目前只有 `app.scan`，见 `AI/frontend/shell.md`）；页面自己的动作用页面 id 作命名空间。
- 外壳在每次进入页面时统一处理：顶栏标题、`document.title`（「页面名 · OMRS」）、侧栏 `.active` 与 `aria-current="page"`、`.panel.active`、`.content.is-workbench`、快捷键作用域、关闭手机抽屉，并在 bus 上发 `page:change`。

## 4. core 模块

| 模块 | 接口 | 要点 |
|---|---|---|
| `core/html.js` | `html```、`raw()`、`escape()`、`each(list, keyOf, render)`、`cls()` | 插值默认转义；`each` 发现重复 key 直接报错 |
| `core/dom.js` | `render`、`morph`、`toFragment`、`toElement` | 唯一写 innerHTML 处。`morph` 按 `data-key` 对齐可重排，保留聚焦输入框的值与选区，`data-morph="skip"` 整棵不动，`data-hash` 相同跳过 |
| `core/events.js` | `defineActions(ns, handlers)`、`bindEvents(root)` | `data-action`（点击）、`data-change`、`data-input`、`data-submit`；只认带点号的名字；禁用元素不触发 |
| `core/keys.js` | `registerKeys(scope, map)`、`setScope(id)`、`bindKeys()` | 当前页与 `global` 两层；输入框里、弹层打开时默认不触发；`mod+k`、`shift+tab`、`?` 这类键名 |
| `core/store.js` | `createStore(initial)` → `get / set / subscribe(fn, selector) / batch` | 选择器订阅只在选中值变化时回调 |
| `core/bus.js` | `createBus()` → `on / once / off / emit` | 单个监听出错不影响其余监听 |
| `core/router.js` | `createRouter({ win, fallback, onEnter })`、`parseHash()` | 见 §3 |
| `core/api.js` | `request(path, o)`、`get`、`post` → `{ ok, status, data, error }` | 永不抛出；错误取服务端 `msg` / `error`；网络失败 `network`、超时 `timeout`；远端 401 跳登录页 |
| `core/format.js` | `formatDate`、`relativeDays`、`formatPercent`、`formatNumber`、`formatDuration` | 空值与非法值显示「—」；`YYYY-MM-DD` 按本地日期解析 |
| `core/download.js` | `downloadResponse(response, fallbackName)`、`fileNameOf` | 把 fetch 响应存成文件；文件名优先取 `Content-Disposition`（含 `filename*=UTF-8''`）；不写页面状态（v1.25.1 起，数据复盘导出用）|

纯逻辑的单测在 `tests/app/core.test.mjs`（node），依赖 DOM 的 morph、事件委托、快捷键在 `tests/app/core_tests.js`（由 `tests/app/run_browser.py` 在浏览器里跑）。浏览器测试（`tests/app/run_browser.py`、`tests/e2e/`）在设了 `OMRS_TEST_CDP_URL` 时连接已开着的 Chromium（本机直接启动会崩溃的环境用），否则自行启动；等待一律等条件成立（`wait_for_function`），不写固定延时。历史、目录、报告的回归脚本覆盖操作区重绘、目录展开状态和删除防重；`tests/e2e/create.py` 覆盖快速录入的图片分区、AI 固定响应和创建后上下文。

## 5. 状态与总线

- `window.__omrs = { bus, store, router, emit }` 给旧代码用。
- **统计数据的所有者是 `domain/data.js`（v1.25.0 起）**：`reloadData()` 拉 `/api/stats` → 设快照 → 写旧 `DATA` 镜像（直接给 `let` 标识符赋值）→ 跑过渡桥登记的旧刷新链 `legacyDataRefresh()` → 经 bus 发 `data`，外壳同步进 `store.data`。旧 `DATA`、`store.data`、`currentData()` 是同一个对象。
- **录入页的状态**：`features/create/quick.js` 持有快速录入表单、两区图片与粘贴目标，调用 `domain/labels` 的录入选择器适配；创建成功后刷新统计、历史与目录。`features/create/grid.js` 持有网格筛选与请求状态，迁移期间经 `legacy-inbox.js` 与旧 `inbox.js` 共享图片列表、选择和处理入口。旧 `CR_*` 全局图片数组和 `app.js` 的 `cr*` 函数已删除；旧收件箱题卡仍使用 `core.js::populateCreateLists`。
- **目录的跨页刷新**：`features/catalog/` 订阅 `store.data`，题目统计变化时只重算目录学习状态；外壳的 `app.scan` 成功后发 `catalog:refresh`，目录页收到后强制重读 `/api/tree`。页面卸载时退订，不保留旧全局入口。
- 并发合并：一次加载进行中再调用，只排一次「补拉」，之后的调用共享它；调用方 await 之后拿到的数据不早于调用时刻。加载失败保留上一份快照（首次失败给空快照），`lastError()` 给原因；不再用演示数据顶替。全局 `reloadData` 由过渡桥挂成这个实现，旧调用方不变。`main.js` 在外壳就绪后 `connectData({ emit })` 接上发布通道。
- 题目详情缓存归 `domain/question/mount.js`；旧代码读的 `QUESTION_CACHE` / `QUESTION_PENDING` 是过渡桥挂的只读全局。Session 列表归 `domain/sessions.js`（v1.25.2 起）：`refreshSessions()` 后发先至只认最新、失败保留旧列表，成功失败都经 bus 发 `sessions`；旧 `SESSIONS` 是镜像，全局 `refreshSessions` 由过渡桥挂成它。`main.js` 在外壳就绪后 `connectSessions({ emit })`。
- bus 事件：`data`（载荷统计快照，`domain/data.js` 发）、`questions:preset`（载荷题库预设，仪表盘切页后发）、`ledger:tz`（设置页 `features/settings/appearance.js` 改 Ledger 时区后发，仪表盘重投影最近动态）、`schedule:view`（仪表盘「开始复习」发，打开安排复习）/ `schedule:open-plan`（过渡桥 `schOpenPlan` 发，打开计划）/ `schedule:render`（过渡桥 `renderUnifiedListV2` / `renderExportPicker` 发）、`page:change`（`{ id, prev }`）、`labels`（载荷 LABELS，旧 `renderLabelFilterOptions()` 之后发）、`instant:load`（载荷预设，过渡桥 `instLoadPractice` 发）、`sessions`（`domain/sessions.js` 每次加载开始、结束与删除后发）、`inbox:reload`（录入页上传成功后发，旧 `inbox.js` 重读列表）、`inbox:grid`（旧控制器的列表或选择变化时发，`features/create/grid.js` 重绘）、`feedback:session`（载荷 session_id，复习调度「录入结果」发）、`feedback:reset` / `feedback:clear-results` / `feedback:render`（过渡桥 `resetFeedbackForm` / `fbClearResults` / `renderFb` 发）。新增事件在这里登记。
- `domain/question/`（P5 起）与 `domain/labels/`（P5 第 4 轮起）是真正落在新代码里的领域模块。`domain/question/`：题面 Markdown / KaTeX 渲染与内容哈希缓存、练习记录、qview、详情缓存与题目弹窗，旧代码经过渡桥用它（见 `AI/frontend/qview.md`）。
- domain 层（`assets/app/domain/`）：`items.js`（全站筛选语义 `filterAll`、全部题目 `allItems`、按 uid 取题 `itemOf`、到期天数、筛选选项）、`labels.js`（标记定义与芯片外观；选择器 / 管理弹层 / 新建 / 批量增删仍有旧入口，`pickerOpen()` 供页面快捷键让位）、`board.js`（加入展示板的选板浮层）、`data.js`（统计快照的所有者）、`history-model.js`（Ledger 撤销状态、分类、标题和时间的纯投影）、`history.js`（历史读取与修正请求、跨页通知、最近动态投影）、`exporting.js`（导出请求与下载）、`sessions.js`（Session 列表的所有者、详情、删除与进度纯函数）。features 不直接写 `window.xxx`。注意旧 `core.js` 用 `let` 声明的全局（如 `ACTIVE_FB_SESSION`）在全局词法环境里、不是 `window` 属性：适配器要直接给该标识符赋值，写 `globalThis.xxx` 旧代码读不到。

## 6. 过渡桥（P8 全部删除）

| 位置 | 内容 | 删除期 |
|---|---|---|
| `assets/app/legacy-bridge.js` | 旧 `uiToast` / `uiDialog` / `uiPrompt` / `uiConfirm` 转调新组件 | P8 |
| `assets/app/legacy-pages.js` | 旧页面登记表（当前只登记 board） | 每页迁移时删一项，P8 删文件 |
| `assets/app/legacy-bridge.js` 的 `installScheduleBridge`（v1.25.2 起；v1.25.3 补推荐选题，v1.25.4 补导出）：`refreshSessions` → `domain/sessions.js`；`schOpenPlan(id)` → 复习调度页事件（不在本页时先切页）；`confirmScheduleV2()` / `loadRecommendationsV2()` → 「安排复习」控制器；`renderUnifiedListV2()` / `renderExportPicker()` → 页面重绘；`downloadExportResponse(response, name, statusId)` → `core/download.js`；只读 `SCH_VIEW`、`SCH_EXPORT_RETURN`、`SCH_SESSIONS_LOADING`、`REC_DATA_V2`、`REC_LOADING`、`REC_ERROR` | app.js `init()`、history.js、schedule.js 的 `doScan`、labels.js（标记变化后）、domain/question/ops.js（批量 A4）；tests/e2e 与冒烟测试 | 调用方迁完逐条删，P8 清空 |
| `assets/app/legacy-bridge.js` 的 `installDataBridge`（v1.25.0）：全局 `reloadData` → `domain/data.js`；旧刷新链 `legacyDataRefresh()` 登记为钩子；`QUESTION_CACHE` / `QUESTION_PENDING` 只读全局 | `reloadData`：app.js `init()`、inbox.js、labels.js、schedule.js 的写操作之后；目录与历史页通过 store / bus 自行订阅；缓存：board.js | 刷新链随各页迁移逐项删，P8 清空 |
| `assets/app/legacy-bridge.js` 的 `instLoadPractice(preset)`、`INSTANT_QUEUE` | 旧入口带预设进入即时练习（仪表盘已改为直接发 `instant:load`，现仅 `tests/e2e/instant.py` 回归用）；旧冒烟测试读队列 | P8 |
| `assets/app/legacy-bridge.js` 的 `fbSessionProgress`、`renderFb`、`resetFeedbackForm`、`fbClearResults`；`schedule.js` 的 `feedbackSession` / `refreshFbSessionPicker`（改为发 bus） | 复习调度算进度、跳到反馈页、删计划清表单；标记变化重绘 | P8 |
| `assets/app/legacy-bridge.js` 的 `installQuestionBridge`：`renderMdContent`、`ensureQuestionDetail`、`qvHtml` / `qvRender` / `qvInvalidate(Many)` / `qvRerenderAll` / `qvSetContext`、`viewQ` / `closeModal`、`closeMarkdownEditor`（E2E 收尾）、练习记录函数 | 展示板、导出、推荐、数据复盘、收件箱、历史仍调旧名 | 各调用方迁完逐条删，P8 清空 |
| `installLabelsBridge`（P5 第 4 轮）：`lblChip` / `lblChips`、`lblColorKey`、`labelHex`、`labelPresetColors`、`nextLabelColor`、`labelSort` / `labelUpsert`、`labelPickerOptions`、`labelRecent` / `labelTouchRecent` / `labelQuickList`、`labelApplyBatch`、`labelFormValues`（实现在 `domain/labels/`） | 芯片：labels.js、board.js、data.js、export.js、inbox.js、recommend_v2.js；其余：labels.js | 各调用方迁完逐条删，P8 清空 |
| `installQuestionsPageBridge`：`renderQ()` / `filterQ()` → 发 `'questions:render'`；`questionsLoadPreset(preset)` → 题库页先清空条件再套用预设并切页 | app.js（`legacyDataRefresh`）、labels.js（保存标记后）；qview 的「在题目库打开」、`tests/e2e/questions.py`（旧入口回归） | P8 |
| `installEscapeBridge`：`core/keys.js` 全局 `escape`（先关标记选择器，再关标记管理）——取代 labels.js 原来挂在 document 上的 keydown；题目弹窗与 Markdown 编辑器是 `ui/dialog`，Esc 由 `ui/overlay` 处理 | 所有页面 | 选择器与标记管理迁到新组件时删（P5 第 4 轮起，最迟 P8） |
| `__omrsUi.host(node, {close, escape})` / `release(node)`：旧浮层放进最上层模态对话框（`ui/overlay` 的客人） | labels.js（标记选择器、标记管理）、board_picker.js（选板浮层） | 各自迁到新组件时删（标记 P5 第 4 轮起、选板 P7），P8 清空 |
| `assets/app.js` 的 `switchTab` | 一行包装 `router.go` | P8（旧 `onclick` 全部换成链接或 `data-action` 之后） |
| `assets/app/styles/legacy-bridge.css` | 旧类名套新外观 | 分段删除，见 `AI/frontend/components.md` §5 |

## 7. 静态资源缓存

`/assets/` 响应带弱 ETag（文件 mtime + 大小）与 `Last-Modified`，仍是 `Cache-Control: no-cache`：浏览器每次都问，文件没变时只收到空的 304。模块之间的 import 带不上 `?v=`，也不再需要手工维护版本串；只有 `omrs_dashboard.html` 里的两个入口保留 `?v=`。

## 8. 待办

- 其余页面逐页迁到 `features/<页>/`（题目库、即时练习、反馈录入已完成），同时把该页的 keydown 监听迁到 `core/keys.js`、`onclick` 换成 `data-action`。
- 筛选语义 `filterItems` / `getDueDays` 仍在旧 `core.js`（node 旧测试直接调它），随调度与导出迁移搬进 `domain/items.js`。
