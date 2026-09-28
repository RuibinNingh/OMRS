# 前端：架构（目录、依赖方向、页面契约、启动顺序、过渡桥）

> **速查**
> - 职责：`assets/app/` 的分层与依赖方向、`core/` 底座（渲染、事件、快捷键、状态、总线、路由、请求、格式化）、页面契约、启动顺序、过渡桥与静态资源缓存
> - 入口：`assets/app/main.js`、`assets/app/shell.js`、页面登记模块、`assets/app/core/router.js`
> - 不变量：`main.js` 装配外壳与领域服务后启动路由；页面之间不互相 import，联动走 bus；`innerHTML` 只在 `core/dom.js`；生产代码不恢复测试专用旧全局
> - 必跑测试：`tests/app/core.test.mjs`、`tests/app/run_browser.py`、`tests/e2e/shell_router.py`、`tests/test_asset_cache.py`
> - 相关：`AI/frontend/components.md`（ui 组件与 gallery）、`AI/frontend/shell.md`（外壳、加载顺序）、`AI/frontend/design-system.md`（token 与门禁）

## 1. 目录与依赖方向

```
assets/app/
├── main.js            启动入口（见 §2）
├── shell.js           外壳：路由生命周期 → 顶栏标题、侧栏高亮、面板显隐、工作台布局；暴露 window.__omrs
├── core/              与业务无关的底座：html、dom、events、keys、store、bus、router、api、format
├── ui/                无业务组件
├── styles/            tokens、index（@layer 总入口）、base、ui、shell、legacy-bridge、gallery
├── domain/            业务领域：question/（共享题目视图，已是真实现）+ 过渡期适配器（新页面只经这里碰旧全局，见 §5）
└── features/          已迁移的页面：dashboard/、data/、schedule/、board/（展示板，整页原生；板详情 detail.js）、questions/、instant/、feedback/、history/、catalog/、reports/、settings/、create/（录入题目：上传、网格、处理、题卡、AI 草稿、AI 训练、快速录入）
```

依赖方向由 `tests/check_ui.py` 的 R7 强制：`core` 只依赖 `core`；`ui` 依赖 `ui`、`core`；`domain` 依赖 `domain`、`ui`、`core`；`features/<页>` 只依赖本页、`domain`、`ui`、`core`，页面之间禁止互相 import，跨页联动走 bus。根目录的 `main.js`、`shell.js` 是装配层，不受 R7 限制，也不放业务逻辑。

## 2. 启动顺序

入口是 HTML 的 `type="module"` 脚本 `main.js`，无需构建。先安装图标、提示、题目 DOM 与展示板入口并启动活动跟踪，再 `startShell(window,pages)` 创建 bus/store/router 与页面契约。

外壳创建后连接统计、Session、历史、标记和草稿领域服务；`connectDrafts` 接入跨页目标、侧栏角标、页面进入与窗口聚焦刷新。初始标记 / 统计 / Session 并行加载后调用 `router.start()`，随后同步助手入口。旧 app.js、init 和过渡桥不在当前启动链中。

## 3. 路由与页面契约

- 地址形如 `#/questions`。`router.go(id)` 无异步守卫时同步切页并 `pushState` 一条历史；未登记的 id 落到仪表盘；地址无效时改写成 `#/dashboard`。
- 地址变成非路由 hash（例如 `href="#"` 的链接）时不切页，并把地址改回当前页，保证刷新仍停在原页。
- 侧栏导航是 `<a class="tab" data-tab="页面" href="#/页面">`：普通点击同步切页；带修饰键时交给浏览器（新标签页打开）。旧 `onclick="switchTab(...)"` 继续可用。
- 新页面契约（`features/<页>/index.js` 导出 `page`）：`{ id, title, workbench, mount(root, ctx) → unmount, actions, keys }`。`root` 是 `#panel-<id>`，`ctx = { bus, store, router }`；离开页面时执行 `mount` 返回的卸载函数。`actions` 与 `keys` 由外壳在登记页面时一次性注册，动作命名空间与快捷键作用域都是页面 id；处理函数只在挂载期间生效。新增一页时在 `main.js` 把页面契约并进登记表（外壳只认 `mount`）。范例：`features/instant/`（见 `AI/frontend/instant.md`）；`features/feedback/`（见 `AI/frontend/feedback.md`）另示范了挂载期的 document 级监听（paste）要在卸载函数里移除。
- 助手页 `features/assistant/` 的输入框图片粘贴、拖入和文件选择都由页面挂载期监听或页面动作处理，卸载时移除监听；事件归约与视图分别由 `tests/app/assistant.test.mjs` 和 `tests/e2e/assistant.py` 验证。
- 跨页共用的按钮走外壳登记的全局动作 `app.*`（目前只有 `app.scan`，见 `AI/frontend/shell.md`）；页面自己的动作用页面 id 作命名空间。
- 外壳在每次进入页面时统一处理：顶栏标题、`document.title`（「页面名 · OMRS」）、侧栏 `.active` 与 `aria-current="page"`、`.panel.active`、`.content.is-workbench`、快捷键作用域、关闭手机抽屉，并在 bus 上发 `page:change`。

路由的 `setLeaveGuard(fn)` 返回注销函数。无守卫保持同步切页；守卫返回 false 或异步未获允许时，页面与地址保持在原处，连续点击合并为同一次确认。AI 草稿页用它保护显式保存前的编辑；浏览器关闭另用原生 beforeunload。

## 4. core 模块

| 模块 | 接口 | 要点 |
|---|---|---|
| `core/html.js` | `html```、`raw()`、`escape()`、`each(list, keyOf, render)`、`cls()` | 插值默认转义；`each` 发现重复 key 直接报错 |
| `core/dom.js` | `render`、`morph`、`toFragment`、`toElement` | 唯一写 innerHTML 处。`morph` 按 `data-key` 对齐可重排，保留聚焦输入框的值与选区，`data-morph="skip"` 整棵不动，`data-hash` 相同跳过 |
| `core/events.js` | `defineActions(ns, handlers)`、`bindEvents(root)` | `data-action`（点击）、`data-change`、`data-input`、`data-submit`；只认带点号的名字；禁用元素不触发 |
| `core/keys.js` | `registerKeys(scope, map)`、`setScope(id)`、`bindKeys()`、`pushKeyLayer(map, {modal})` | 当前页与 `global` 两层；输入框里、弹层打开时默认不触发；`mod+k`、`shift+tab`、`?` 这类键名。浮层键盘层（选板浮层用）：打开时压一层、返回弹出函数，只有最上层生效且先于当前页与 global，在输入框、对话框里都生效；`'any'` 兜底表里没有的键；默认独占（没处理的键不传给页面，也不 `preventDefault`） |
| `core/store.js` | `createStore(initial)` → `get / set / subscribe(fn, selector) / batch` | 选择器订阅只在选中值变化时回调 |
| `core/bus.js` | `createBus()` → `on / once / off / emit` | 单个监听出错不影响其余监听 |
| `core/router.js` | `createRouter({ win, fallback, onEnter })`、`parseHash()` | 见 §3 |
| `core/api.js` | `request(path, o)`、`get`、`post` → `{ ok, status, data, error }` | 永不抛出；错误取服务端 `msg` / `error`；网络失败 `network`、超时 `timeout`；远端 401 跳登录页 |
| `core/format.js` | `formatDate`、`relativeDays`、`formatPercent`、`formatNumber`、`formatDuration` | 空值与非法值显示「—」；`YYYY-MM-DD` 按本地日期解析 |
| `core/download.js` | `downloadResponse(response, fallbackName)`、`fileNameOf` | 把 fetch 响应存成文件；文件名优先取 `Content-Disposition`（含 `filename*=UTF-8''`）；不写页面状态（v1.25.1 起，数据复盘导出用）|

纯逻辑的单测在 `tests/app/core.test.mjs`（node），依赖 DOM 的 morph、事件委托、快捷键在 `tests/app/core_tests.js`（由 `tests/app/run_browser.py` 在浏览器里跑）。浏览器测试（`tests/app/run_browser.py`、`tests/e2e/`）在设了 `OMRS_TEST_CDP_URL` 时连接已开着的 Chromium（本机直接启动会崩溃的环境用），否则自行启动；等待一律等条件成立（`wait_for_function`），不写固定延时。历史、目录、报告的回归脚本覆盖操作区重绘、目录展开状态和删除防重；`tests/e2e/create.py` 覆盖快速录入的图片分区、AI 固定响应和创建后上下文。独立框选标注页不挂在外壳上：纯逻辑与数据所有者在 `tests/app/annotate.test.mjs`，`tests/e2e/annotate.py` 直接打开 `/annotate` 走主路径（沿用 `create.py` 的审计脚本）。

展示板的页面测试分三层：`tests/app/board*.test.mjs` 测视图模型与源码约束（`board-regions.test.mjs` 同时读 `view.js` 与 `view-panel.js`），`tests/app/board-preview.test.mjs` 测预览消息与「适应宽度」公式，`tests/e2e/board.py` 走主路径，含详情层独立滚动、答案折叠、「打开题目」弹窗，以及宽屏收起左栏后纸面自动重算缩放。

## 5. 状态与总线

- `window.__omrs = { bus, store, router, emit }` 给旧代码用。
- **统计数据的所有者是 `domain/data.js`（v1.25.0 起）**：`reloadData()` 拉 `/api/stats` → 设快照 → 写旧 `DATA` 镜像（直接给 `let` 标识符赋值）→ 跑过渡桥登记的旧刷新链 `legacyDataRefresh()` → 经 bus 发 `data`，外壳同步进 `store.data`。旧 `DATA`、`store.data`、`currentData()` 是同一个对象。
- **录入页的状态**：`features/create/quick.js` 持有快速录入表单、两区图片与粘贴目标，调用 `domain/labels` 的录入选择器适配；创建成功后刷新统计、历史与目录。收件箱只在录入页用，数据所有者留在 feature 里：`features/create/inbox-store.js`（I/O 注入的工厂，单例在 `inbox.js`）持有图片列表、勾选、当前图、保存队列与任务轮询，网格、处理区、题卡、训练共用，经 bus 事件 `inbox:changed` 重绘；页面卸载时 flush。旧 `inbox.js`、`CR_*` 全局与 `core.js::populateCreateLists` 已删除。
- **目录的跨页刷新**：`features/catalog/` 订阅 `store.data`，题目统计变化时只重算目录学习状态；外壳的 `app.scan` 成功后发 `catalog:refresh`，目录页收到后强制重读 `/api/tree`。页面卸载时退订，不保留旧全局入口。
- 并发合并：一次加载进行中再调用，只排一次「补拉」，之后的调用共享它；调用方 await 之后拿到的数据不早于调用时刻。加载失败保留上一份快照（首次失败给空快照），`lastError()` 给原因；不再用演示数据顶替。全局 `reloadData` 由过渡桥挂成这个实现，旧调用方不变。`main.js` 在外壳就绪后 `connectData({ emit })` 接上发布通道。
- 题目详情缓存归 `domain/question/mount.js`；旧代码读的 `QUESTION_CACHE` / `QUESTION_PENDING` 是过渡桥挂的只读全局。Session 列表归 `domain/sessions.js`（v1.25.2 起）：`refreshSessions()` 后发先至只认最新、失败保留旧列表，成功失败都经 bus 发 `sessions`；旧 `SESSIONS` 是镜像，全局 `refreshSessions` 由过渡桥挂成它。`main.js` 在外壳就绪后 `connectSessions({ emit })`。
- bus 事件：`data`（载荷统计快照，`domain/data.js` 发）、`questions:preset`（载荷题库预设，仪表盘切页后发）、`ledger:tz`（设置页 `features/settings/appearance.js` 改 Ledger 时区后发，仪表盘重投影最近动态）、`schedule:view`（仪表盘「开始复习」发，打开安排复习）/ `schedule:open-plan`（过渡桥 `schOpenPlan` 发，打开计划）/ `schedule:render`（过渡桥 `renderUnifiedListV2` / `renderExportPicker` 发）、`page:change`（`{ id, prev }`）、`labels`（载荷 LABELS，旧 `renderLabelFilterOptions()` 之后发）、`instant:load`（载荷预设，过渡桥 `instLoadPractice` 发）、`sessions`（`domain/sessions.js` 每次加载开始、结束与删除后发）、`inbox:reload`（录入页上传成功后发，页面重读收件箱）、`inbox:changed`（`features/create/inbox-store.js` 在列表、勾选、当前图或工作区变化时发，录入页各工作区重绘）、`feedback:session`（载荷 session_id，复习调度「录入结果」发）、`feedback:reset` / `feedback:clear-results` / `feedback:render`（过渡桥 `resetFeedbackForm` / `fbClearResults` / `renderFb` 发）。新增事件在这里登记。
- `domain/question/`（P5 起）与 `domain/labels/`（P5 第 4 轮起）是真正落在新代码里的领域模块。`domain/question/`：题面 Markdown / KaTeX 渲染与内容哈希缓存、练习记录、qview、详情缓存与题目弹窗，旧代码经过渡桥用它（见 `AI/frontend/qview.md`）。
- domain 层（`assets/app/domain/`）：`items.js`（全站筛选语义 `filterAll`、全部题目 `allItems`、按 uid 取题 `itemOf`、到期天数、筛选选项）、`labels.js`（标记定义与芯片外观；选择器 / 管理弹层 / 新建 / 批量增删仍有旧入口，`pickerOpen()` 供页面快捷键让位）、`board/`（见下一条）、`data.js`（统计快照的所有者）、`history-model.js`（Ledger 撤销状态、分类、标题和时间的纯投影）、`history.js`（历史读取与修正请求、跨页通知、最近动态投影）、`exporting.js`（导出请求与下载）、`sessions.js`（Session 列表的所有者、详情、删除与进度纯函数）。features 不直接写 `window.xxx`。注意旧 `core.js` 用 `let` 声明的全局（如 `ACTIVE_FB_SESSION`）在全局词法环境里、不是 `window` 属性：适配器要直接给该标识符赋值，写 `globalThis.xxx` 旧代码读不到。
- 展示板 domain（`assets/app/domain/board/`）：`model.js` 是选板分组、行状态、过滤、最近使用、行模型、点击决策与 `boardUniqueUids` 的纯函数，P7 第 1 步起归新代码；选板浮层 `picker.js` 是真实现，经 `source.js` 读 `boards.js` 的板列表、文件夹，加题 / 重读 / 打开经 `detail-port.js`；`boards.js` 是板列表的数据所有者；`detail-port.js` 是板详情端口，由 `features/board/runtime.js` 接上实现（domain 不 import features）；`index.js` 的 `boardQuickAdd` / `boardChooseAndAdd` 直接打开它。

助手页（`features/assistant/`）在启动加载完成后由 `main.js` 调 `syncAssistantNav` 决定侧栏入口显隐；设置页保存助手配置时发总线事件 `agent:config`，`main.js` 收到后再同步一次（功能页之间不互相 import）。助手页的数据走 `/api/agent/*` 长轮询，不经 domain 层；写入完成后调用 `domain/data`、`domain/sessions`、`domain/question` 的刷新入口。

## 6. 过渡桥（P8 全部删除）

| 位置 | 内容 | 删除期 |
|---|---|---|
| `assets/app/` 模块 | 旧 `uiToast` / `uiDialog` / `uiPrompt` / `uiConfirm` 转调新组件 | P8 |
| 页面登记模块 | 旧页面登记表（P6 剩余页面与 P7 展示板合入后为空，所有页面都是页面契约） | P8 删文件（连同 `main.js` 里的 `...LEGACY_PAGES`） |
| `assets/app/` 模块 的 `installScheduleBridge`（v1.25.2 起；v1.25.3 补推荐选题，v1.25.4 补导出）：`refreshSessions` → `domain/sessions.js`；`schOpenPlan(id)` → 复习调度页事件（不在本页时先切页）；`confirmScheduleV2()` / `loadRecommendationsV2()` → 「安排复习」控制器；`renderUnifiedListV2()` / `renderExportPicker()` → 页面重绘；`downloadExportResponse(response, name, statusId)` → `core/download.js`；只读 `SCH_VIEW`、`SCH_EXPORT_RETURN`、`SCH_SESSIONS_LOADING`、`REC_DATA_V2`、`REC_LOADING`、`REC_ERROR` | app.js `init()`、history.js、schedule.js 的 `doScan`、labels.js（标记变化后）、domain/question/ops.js（批量 A4）；tests/e2e 与冒烟测试 | 调用方迁完逐条删，P8 已完成 |
| `assets/app/` 模块 的 `installBoardBridge`（P7 第 6 轮起只剩旧调用方与冒烟测试要用的入口）：板详情单例（`features/board/runtime.js`）的 `boardInit` / `boardReloadData` / `boardLoad` / `boardAddToBoard` / `boardFlushSave` / `boardApplyPrintField` / `boardSetItemGap` / `boardSetView` / `boardSetPrintMode` / `boardPrintPreview` / `boardExportCurrent` / `boardSaveQueue` / `boardPrint` / `boardMarkAwaiting` / `boardClearAwaiting` / `boardRender` / `configureBoardDetail` 与只读访问器 `BOARD_DETAIL`；`features/board/preview.js` 的 `boardPreview*`；`domain/board/` 的 `boardQuickAdd` / `boardChooseAndAdd` / `boardPickerOpen` / `boardPickerClose` / `boardCurrentId`；并调 `installBoardWindow` 装窗口级监听 | `boardInit` / `boardReloadData`：app.js（`init`、`legacyDataRefresh`）、labels.js；选板：inbox.js、`domain/question/mount.js`、`domain/sessions.js`；其余：smoke_board_integrity.py（已删除：调用的旧全局 P7 起已不存在；覆盖由新版展示板 E2E 承接）、`smoke_board_lock.py`、`smoke_board_print_geometry.py`、`tests/e2e/board.py`、`board_picker.py` | P8：旧调用方迁完、冒烟测试改用新入口后清空 |
| `assets/app/` 模块 的 `installDataBridge`（v1.25.0）：全局 `reloadData` → `domain/data.js`；旧刷新链 `legacyDataRefresh()` 登记为钩子；`QUESTION_CACHE` / `QUESTION_PENDING` 只读全局 | `reloadData`：app.js `init()`、labels.js、schedule.js 的写操作之后；目录与历史页通过 store / bus 自行订阅；缓存：旧读者 board.js（P7 删）、export.js（v1.25.4 删）都已不在，只剩 tests/e2e 读取 | 刷新链随各页迁移逐项删，P8 已完成 |
| `assets/app/` 模块 的 `instLoadPractice(preset)`、`INSTANT_QUEUE` | 旧入口带预设进入即时练习（仪表盘已改为直接发 `instant:load`，现仅 `tests/e2e/instant.py` 回归用）；旧冒烟测试读队列 | P8 |
| `assets/app/` 模块 的 `fbSessionProgress`、`renderFb`、`resetFeedbackForm`、`fbClearResults`；`schedule.js` 的 `feedbackSession` / `refreshFbSessionPicker`（改为发 bus） | 复习调度算进度、跳到反馈页、删计划清表单；标记变化重绘 | P8 |
| `assets/app/` 模块 的 `installQuestionBridge`：`renderMdContent`、`ensureQuestionDetail`、`qvHtml` / `qvRender` / `qvInvalidate(Many)` / `qvRerenderAll` / `qvSetContext`、`viewQ` / `closeModal`、`closeMarkdownEditor`（E2E 收尾）、练习记录函数 | 展示板、导出、推荐、数据复盘、历史仍调旧名 | 各调用方迁完逐条删，P8 已完成 |
| `installLabelsBridge`（P5 第 4 轮）：`lblChip` / `lblChips`、`lblColorKey`、`labelHex`、`labelPresetColors`、`nextLabelColor`、`labelSort` / `labelUpsert`、`labelPickerOptions`、`labelRecent` / `labelTouchRecent` / `labelQuickList`、`labelApplyBatch`、`labelFormValues`（实现在 `domain/labels/`） | 芯片：labels.js、board.js、data.js、export.js、inbox.js、recommend_v2.js；其余：labels.js | 各调用方迁完逐条删，P8 已完成 |
| `installQuestionsPageBridge`：`renderQ()` / `filterQ()` → 发 `'questions:render'`；`questionsLoadPreset(preset)` → 题库页先清空条件再套用预设并切页 | app.js（`legacyDataRefresh`）、labels.js（保存标记后）；qview 的「在题目库打开」、`tests/e2e/questions.py`（旧入口回归） | P8 |
| `installEscapeBridge`：`core/keys.js` 全局 `escape`（先关标记选择器，再关标记管理）——取代 labels.js 原来挂在 document 上的 keydown；题目弹窗与 Markdown 编辑器是 `ui/dialog`，Esc 由 `ui/overlay` 处理 | 所有页面 | 选择器与标记管理迁到新组件时删（P5 第 4 轮起，最迟 P8） |
| `__omrsUi.host(node, {close, escape})` / `release(node)`：旧浮层放进最上层模态对话框（`ui/overlay` 的客人） | labels.js（标记选择器、标记管理）；原生的选板浮层直接用 `hostGuest` | 标记选择器与标记管理迁到新组件时删，P8 已完成 |
| `assets/app/main.js` 的 `switchTab` | 一行包装 `router.go` | P8（旧 `onclick` 全部换成链接或 `data-action` 之后） |

E2E 专用适配器 `tests/e2e/p8_test_modules.js`：8 个 E2E 以 init script 注入，把 `SCH_VIEW`、`QUESTION_CACHE` 等旧断言读的名字做成只读 getter（读真实 ES 模块状态），并挂几个调用入口；生产代码不再有这些全局。新写的断言直接用 DOM、`window.__omrs` 或 `import()` 真实模块，不再往适配器里加名字。

## 7. 静态资源缓存

`/assets/` 响应带弱 ETag（文件 mtime + 大小）与 `Last-Modified`，仍是 `Cache-Control: no-cache`：浏览器每次都问，文件没变时只收到空的 304。模块之间的 import 带不上 `?v=`，也不再需要手工维护版本串；只有 `omrs_dashboard.html` 里的两个入口保留 `?v=`。

## 8. 待办

- 其余页面逐页迁到 `features/<页>/`（仪表盘、数据复盘、复习调度、历史记录、目录、报告、设置、展示板、题目库、即时练习、反馈录入已完成；录入题目（含收件箱工作台）已完成），同时把该页的 keydown 监听迁到 `core/keys.js`、`onclick` 换成 `data-action`。
- 筛选语义 `filterItems` / `getDueDays` 仍在旧 `core.js`（node 旧测试直接调它），随调度与导出迁移搬进 `domain/items.js`。

## 草稿跨页状态

`domain/drafts.js` 负责草稿导航目标、sessionStorage 中的已选编号和四态计数，不持有编辑表单。`openDraft(id)` 先保存目标再切 create，挂载方用 consumeDraftTarget 消费；切页成功后发 `drafts:open {id}`。`drafts:changed {ids}` 触发重新取计数，成功发 `drafts:counts`；读取失败保留上次成功数值。首次加载、切页、聚焦重取计数；有活动运行 / 任务时每两秒轮询，隐藏时暂停，销毁后晚到结果不再更新。

`tests/app/draft-navigation.test.mjs` 覆盖目标先于挂载、离页拒绝、计数请求合并、失败保留与晚到响应；`tests/app/core.test.mjs` 覆盖同步路由和异步离页守卫。
