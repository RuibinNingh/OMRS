# 前端：架构（目录、依赖方向、页面契约、启动顺序）

> **速查**
> - 职责：`assets/app/` 的分层与依赖方向、`core/` 底座（渲染、事件、快捷键、状态、总线、路由、请求、格式化）、页面契约、启动顺序与静态资源缓存
> - 入口：`assets/app/main.js`、`assets/app/shell.js`、各页 `features/<页>/index.js`、`assets/app/core/router.js`
> - 不变量：`main.js` 装配外壳与领域服务后启动路由；页面之间不互相 import，联动走 bus；`innerHTML` 只在 `core/dom.js`；旧全局只由 E2E 适配器注入
> - 必跑测试：`tests/app/core.test.mjs`、`tests/app/run_browser.py`、`tests/e2e/shell_router.py`、`tests/test_asset_cache.py`
> - 相关：`AI/frontend/components.md`（ui 组件与 gallery）、`AI/frontend/shell.md`（外壳、加载顺序）、`AI/frontend/design-system.md`（token 与门禁）

## 1. 目录与依赖方向

```
assets/app/
├── main.js            启动入口（见 §2）
├── shell.js           外壳：路由生命周期 → 顶栏标题、侧栏高亮、面板显隐、工作台布局；暴露 window.__omrs
├── core/              与业务无关的底座：html、dom、events、keys、store、bus、router、api、format
├── ui/                无业务组件
├── styles/            tokens、index（@layer 总入口）、base、ui、shell、gallery
├── domain/            跨页业务模块：data、sessions、drafts、taxonomy、history、items、exporting、scan、question/、labels/、board/
└── features/          主外壳页面：dashboard/、data/、schedule/、board/、questions/、instant/、feedback/、history/、catalog/、reports/、settings/、create/、assistant/；独立页面：annotate/、trainpanel/
```

依赖方向由 `tests/check_ui.py` 的 R7 强制：`core` 只依赖 `core`；`ui` 依赖 `ui`、`core`；`domain` 依赖 `domain`、`ui`、`core`；`features/<页>` 只依赖本页、`domain`、`ui`、`core`，页面之间禁止互相 import，跨页联动走 bus。根目录的 `main.js`、`shell.js` 是装配层，不受 R7 限制，也不放业务逻辑。

## 2. 启动顺序

主页面入口是 HTML 的 `type="module"` 脚本 `main.js`，无需构建。先安装图标、提示、题目 DOM 与展示板窗口监听并启动活动跟踪，再 `startShell(window,pages)` 创建 bus/store/router、登记页面契约。

外壳创建后连接草稿、统计、Session、历史和标记领域服务，绑定标记选择器事件与全局 Esc。先调用 `router.start()` 安装 hash 监听并稳定当前页面，再并行加载初始标记 / 统计 / Session，随后同步助手入口；设置变更通过 `agent:config` 再同步。独立的 `/annotate`、`/train` 使用各自入口，不在主外壳的页面登记表中。

## 3. 路由与页面契约

- 地址形如 `#/questions`，也支持 `#/instant?practice=<card_id>&attempt=<attempt_id>`。路由用问号前的页面 ID 匹配页面，并保留查询串供页面挂载时读取；同一页面的查询串改变也重新挂载。`router.go(id)` 无异步守卫时同步切页并 `pushState` 一条历史；未登记的 id 落到仪表盘；地址无效时改写成 `#/dashboard`。
- 地址变成非路由 hash（例如 `href="#"` 的链接）时不切页，并把地址改回当前页，保证刷新仍停在原页。
- 侧栏导航是 `<a class="tab" data-tab="页面" href="#/页面">`：普通点击同步切页；带修饰键时交给浏览器（新标签页打开）。
- 新页面契约（`features/<页>/index.js` 导出 `page`）：`{ id, title, workbench, mount(root, ctx) → unmount, actions, keys }`。`root` 是 `#panel-<id>`，`ctx = { bus, store, router }`；离开页面时执行 `mount` 返回的卸载函数。`actions` 与 `keys` 由外壳在登记页面时一次性注册，动作命名空间与快捷键作用域都是页面 id；处理函数只在挂载期间生效。新增一页时在 `main.js` 把页面契约并进登记表（外壳只认 `mount`）。范例：`features/instant/`（见 `AI/frontend/instant.md`）；`features/feedback/`（见 `AI/frontend/feedback.md`）另示范了挂载期的 document 级监听（paste）要在卸载函数里移除。
- 助手页 `features/assistant/` 的图片粘贴、聊天主面板文件拖入和文件选择都由页面挂载期监听或页面动作处理，卸载时移除监听；会话切换使附件读取 generation 失效。事件归约与视图由 `tests/app/assistant.test.mjs`、`tests/e2e/assistant.py` 和 `tests/e2e/assistant_p3.py` 验证，含 JPEG 字节保持、拖放、预览、输入法与可见视口路径。共享图片预览在 `tests/app/browser_tests.js` 验证焦点和模态行为；草稿来源图在 `tests/e2e/drafts.py` 验证。
- 助手用量归约仍是页面自身的纯逻辑，`tests/app/assistant.test.mjs` 验证请求去重、重放与缺失字段；`tests/e2e/assistant_usage.py` 用隔离 Vault 和假模型验证圆环切换、持久偏好与检查器。
- 录入页的可搜索建议由 `ui/combobox` 绑定到原生输入框，卸载时释放 body 浮层和窗口监听；`tests/e2e/create.py` 验证建议框键盘退出、AI 结果与人工编辑及图片版本之间的隔离。
- 历史页通过 `domain/history.js` 分批读取 Ledger 摘要与独立 MCP 运行记录，按需读取各区详情；`tests/e2e/history.py` 覆盖 240 条以上跨页加载、撤销状态与读取失败保留列表，`tests/e2e/runtime_history.py` 在临时 Web + MCP 服务上覆盖真实调用、筛选竞争、人工入库双向关联、轮询与手机返回。调用详情通过 `domain/drafts.js` 的 `openDraft` 复用草稿导航，页面之间不直接依赖。
- 跨页共用的按钮走外壳登记的全局动作 `app.*`（创建、侧栏折叠、手机抽屉、重新扫描，见 `AI/frontend/shell.md`）；页面自己的动作用页面 id 作命名空间。
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
| `core/download.js` | `downloadResponse(response, fallbackName)`、`fileNameOf` | 把 fetch 响应存成文件；文件名优先取 `Content-Disposition`（含 `filename*=UTF-8''`）；不写页面状态 |

纯逻辑的单测在 `tests/app/core.test.mjs`（node），依赖 DOM 的 morph、事件委托、快捷键在 `tests/app/core_tests.js`（由 `tests/app/run_browser.py` 在浏览器里跑）。浏览器测试（`tests/app/run_browser.py`、`tests/e2e/`）在设了 `OMRS_TEST_CDP_URL` 时连接已开着的 Chromium（本机直接启动会崩溃的环境用），否则自行启动；等待一律等条件成立（`wait_for_function`），不写固定延时。历史、目录、报告的回归脚本覆盖操作区重绘、目录展开状态和删除防重；`tests/e2e/create.py` 覆盖快速录入的图片分区、AI 固定响应、创建后上下文，并在 360px 触摸浏览器核对主按钮尺寸和横向布局。独立框选标注页不挂在外壳上：纯逻辑与数据所有者在 `tests/app/annotate.test.mjs`，`tests/e2e/annotate.py` 直接打开 `/annotate` 走主路径（沿用 `create.py` 的审计脚本）。

录入页的数据所有者在 `tests/app/create-inbox.test.mjs` 用替身接口验证保存队列、字段补丁、revision 冲突、load 与保存交错、旧模板配置兼容及截图重置时旧请求的处理；`tests/app/create-process.test.mjs` 检查框选和批量栏不出现模板与沿用框位入口，并固定录入成功状态块；`tests/e2e/create.py` 用隔离服务和真实浏览器验证提取中重置、旧任务结束后进度保持清空、保存失败不入库、继续画框，以及标记就绪成功反馈留在工作区内而不再弹同文 toast。`tests/app/annotate.test.mjs`、`board-locked.test.mjs` 与 `tests/e2e/assistant_race.py` 分别固定标注版本冲突、换板读取失败和迟到对话响应不覆盖当前状态。

设置页的配置读写在 `tests/app/settings.test.mjs` 用替身接口验证；MCP 密钥元数据投影同时覆盖到期边界、吊销优先、本地时间与名称转义。`tests/e2e/settings.py` 用隔离服务和真实浏览器验证「AI 识别」思考开关、助手最大输出 Token 的默认状态、保存与回读，并复核四档页面布局。

`tests/e2e/mcp.py` 在临时 Vault 的同进程 Web + MCP 服务上验证真实密钥创建、一次性明文、复制反馈、窗口关闭及页面卸载清理、吊销确认与取消、到期自动分组、刷新保留展开和读取失败保留列表；创建及吊销失败可原地重试。权限仅有 `omrs:read` / `draft:create`，完整密钥不写浏览器存储。脚本先通过官方 SDK 核对题目图片列表及按下标返回的原生图片、MIME 与原字节，再创建草稿、由浏览器查看来源和完整原图，并检查浅深色桌面/手机创建窗口。

展示板的页面测试分三层：`tests/app/board*.test.mjs` 测视图模型与源码约束（`board-regions.test.mjs` 同时读 `view.js` 与 `view-panel.js`），`tests/app/board-preview.test.mjs` 测预览消息与「适应宽度」公式，`tests/e2e/board.py` 走主路径，含详情层独立滚动、答案折叠、「打开题目」弹窗、宽屏收起左栏后纸面自动重算缩放，以及翻页动效结束后无残留动画和位移。

## 5. 跨页状态与总线

外壳把 `{ bus, store, router, emit }` 作为只读的 `window.__omrs` 暴露，供领域模块跳页、少数页面动作和浏览器测试使用；页面挂载时直接接收 `ctx = { bus, store, router }`。生产代码不注入 `DATA`、`SESSIONS`、`QUESTION_CACHE` 或 `switchTab` 等旧全局。

- `domain/data.js` 是 `/api/stats` 快照的所有者。`reloadData()` 成功后发布 `data`，外壳同步到 `store.data`；失败保留上次快照，首次失败给空快照。并发调用合并为当前请求和至多一次补拉，调用方可从返回值与 `lastError()` 读取结果。
- `domain/sessions.js` 持有 Session 列表、当前反馈 Session、详情与删除入口。`refreshSessions()` 只接受最新请求的结果，加载开始和结束时发布 `sessions`；删除成功后移除本地记录并使在途旧响应失效。
- `domain/labels/` 持有标记定义、芯片、选择器和管理弹层；写入后通过 `labels`、`questions:render`、`schedule:render`、`feedback:render`、`board:reload` 通知已挂载页面。`domain/items.js` 集中题库、练习和导出的筛选语义与到期天数。
- `domain/question/` 提供 Markdown / KaTeX 渲染、题目详情缓存、共享题目视图、弹窗和编辑器。渲染默认保留普通换行、空行仍按 Markdown 分段，显式「简略」偏好才合并单个换行；题库、录入预览、反馈、即时练习和展示板详情共用这条路径。题目内容或练习记录变化后，由调用方让缓存失效并重绘挂载视图。`domain/board/` 持有板列表与选板浮层，板详情经 `detail-port.js` 连接到 `features/board/runtime.js`，domain 不反向 import feature。
- `features/create/inbox-store.js` 持有收件箱图片列表、当前图、勾选、保存队列和任务轮询；录入页的网格、处理、题卡与训练工作区共用该状态，变化时发 `inbox:changed`。`domain/drafts.js` 持有跨页草稿导航目标与角标计数，不持有草稿编辑表单。

其他跨页入口包括 `domain/history.js`（学习与运行记录读取、修正与通知）、`domain/exporting.js`（导出请求和下载）、`domain/scan.js`（扫描后刷新统计与 Session）。页面之间的导航与刷新由路由和 bus 协调：外壳发 `page:change`，仪表盘可发 `questions:preset`、`instant:load`、`schedule:view` 或 `feedback:session`，设置页发 `agent:config` 后由入口同步助手导航。新增跨页事件时在这里登记其来源与接收方。

## 6. E2E 旧断言适配

`tests/e2e/p8_test_modules.js` 只在浏览器测试中注入：它 import 当前 ES Module，把旧测试读的 `DATA`、`SESSIONS`、`QUESTION_CACHE` 等名字映射成只读 getter，并提供少量旧调用入口。主页面不加载该文件；新增断言应直接检查 DOM、`window.__omrs` 或 import 实际模块。

## 7. 静态资源缓存

`/assets/` 响应带弱 ETag（文件 mtime + 大小）与 `Last-Modified`，使用 `Cache-Control: no-cache`：浏览器每次会重新验证，文件没变时收到空的 304。模块间的 import 不带 `?v=`，由资源校验处理更新；`omrs_dashboard.html` 直接引用的样式、主模块和图标仍带各自的 `?v=`。锁屏入口的 WebGL 场景实现、公式 atlas 和降级主视觉放在 `assets/vendor/entry-*`，由入口页按需加载，不进入应用层依赖检查。

## 8. 草稿与录入页状态

`domain/drafts.js` 负责草稿导航目标、sessionStorage 中的已选编号和四态计数，不持有编辑表单。`openDraft(id)` 先保存目标再切 create，挂载方用 consumeDraftTarget 消费；切页成功后发 `drafts:open {id}`。`drafts:changed {ids}` 触发重新取计数，成功发 `drafts:counts`；读取失败保留上次成功数值。首次加载、切页、聚焦重取计数；有活动运行 / 任务时每两秒轮询，隐藏时暂停，销毁后晚到结果不再更新。

`tests/app/draft-navigation.test.mjs` 覆盖目标先于挂载、离页拒绝、计数请求合并、失败保留与晚到响应；`tests/app/core.test.mjs` 覆盖同步路由和异步离页守卫。

草稿后台作业由页面 `drafts-job.js` 管理轮询和卸载，活动标记交给 `domain/drafts.js` 统一维护角标轮询；页面内容以服务端 revision 为边界，后台结果不能覆盖未保存表单。真实 HTTP 进程重启回归见 `tests/test_draft_p3_http.py`；画布复用与收件箱行为由草稿/录入 E2E 联合验证。

草稿审核页把队列展开、单块编辑、字段表单与来源模式状态留在挂载控制器；跨页领域层仍只保存导航目标与计数。正文视图在 `drafts-review.js`，局部块操作在 `drafts-block-actions.js`，复用共享菜单和确认对话框。插入与跨组移动保留对象身份，暂存响应后把本地块键映射为服务端 id；取消状态下拉切换恢复原筛选值。格式提示与提交预检共用 `draftIssue`。

入库动作先复核服务端 revision，保存后用相同 revision 串行提交；网络响应丢失时重试同一入库身份。`tests/app/create-drafts.test.mjs` 验证阅读结构与块身份，`tests/e2e/drafts_blocks.py` 用真实隔离服务验证逐块焦点、插入、调序、跨组移动、删除确认、保存重读、图文入库和 320 / 390 / 1024 / 1440px 布局。`tests/e2e/drafts.py` 与 `tests/e2e/drafts_p4.py` 验证冲突、响应丢失、移动端队列、框选及独立训练。

丢弃成功后与入库共用待审核队列推进，详情清空时同步移除会话选中记录；画布兼容空草稿与空检测结果。`tests/e2e/drafts.py` 在真实浏览器中覆盖中间项继续下一份、末项回到上一份、连续丢弃、空队列返回与刷新、取消和请求失败保护、成功后列表读取失败重试，以及手动查看已丢弃正文。

`tests/e2e/p4_tools.py` 使用假模型和临时 Vault 从助手确认分类、修订草稿，再进入快速录入与审核页；助手的无 Ledger 写入活动归约由 `tests/app/assistant.test.mjs` 固定。

自动检测与提取共用草稿作业轮询，按 type 区分进度和错误。助手卡片独立读取当前作业并在活动时轮询，结束运行的缓存由 draftVer 失效；隐藏与卸载停止轮询。录入页顶部与草稿列表都复用当前计数快照，接收 counts 事件时同步更新，避免首次挂载或入库后保留旧值。Node 测试覆盖设置、卡片作业状态、候选展示与独立训练框；HTTP 回归验证检测并发和服务重启。

录入页端到端测试 `tests/e2e/create.py` 使用临时 Vault、随机高端口和真实后台提取任务，只替换外部模型调用；覆盖一键提取、部分失败重试、结果后改存图片／切回文本、人工审核及提取结果四档审计。

## 9. 独立训练面板

独立训练面板 `/train` 由 `features/trainpanel/store.js` 持有实验快照、选择状态与指标；按块 morph 保留实时测试原图和滚动。纯模型与增量读取测试见 `tests/app/trainpanel.test.mjs`；`tests/e2e/trainpanel.py` 用假实验目录审计四档状态，`tests/e2e/boxdetect.py` 使用外部真实模型和临时 Vault 复核收件箱及面板。

训练评测的audits.js独立持有筛选、分页、选中案例与复核表单；列表轮询不重绘详情。异步详情和历史都校验请求序号；卸载后拒绝更新。Node验证提交绑定案例/revision，trainpanel E2E验证真实HTTP保存与刷新历史，不调用外部模型。

训练服务控制由 `features/trainpanel/control.js` 独立持有请求身份、服务 revision、选择模型与轮询状态；模型选择不改变实验 store 或在线服务。完成操作后通知父入口刷新 health 顶栏。`tests/app/traincontrol.test.mjs` 验证请求绑定与评测分母文案，`tests/e2e/traincontrol.py` 验证真实 HTTP 异步操作与刷新持久性。


助手页面的 Node 与浏览器回归位于 `tests/app/assistant.test.mjs`、`tests/e2e/assistant.py`、`tests/e2e/assistant_p3.py` 与 `tests/e2e/assistant_usage.py`；这些测试覆盖运行过程折叠、移动输入和用量显示。

路由单测的窗口替身按 URL 解析历史地址并保留 pathname/search/hash，覆盖锁屏入口查询串与当前页恢复；MCP 草稿/设置浏览器验收使用实际页面导航。
