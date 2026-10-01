# v2.1.0（2026-10-01）

- 新增可选外部 MCP 接入，与 Web 同进程运行官方 Streamable HTTP SDK，固定九个查询工具与一个待审核草稿创建工具。API Key 独立于 Web PIN 和模型密钥，按查询/建草稿权限授权；MCP 不修改正式题库，图片保持完整原字节，入库仍由人工审核。
- 补齐 MCP 并发初始化、原子创建与幂等重试边界；请求和实际写入复查密钥吊销、到期及权限，工具发现按实时权限过滤。助手与 MCP 的科目概况统一按所选科目汇总。
- MCP 设置改为能力说明与密钥管理面板，创建权限和到期时间放进共享弹窗，成功后展示一次性明文并提供复制反馈；可用与失效记录分组，失效记录折叠，时间本地化，关闭或离页清空明文。失败可重试并保留现有输入和列表。
- AI 草稿审核采用窄队列与连续正文，信息先显示摘要，题目和答案按块阅读，每次展开一个编辑框。块菜单支持调序、插入、跨部分移动和确认删除；手机队列默认折叠，缺项可定位，「入库并下一题」连续审核。修正自动框选坐标列绑定，人工编辑和版本冲突保护保持。
- 新增独立锁屏入口与黑洞 WebGL 场景，支持 PIN 解锁和免 PIN 进入；入口背景可切换为当前 Vault 的共享图片/视频，支持 0–32px 模糊、200MB 文件和动态效果降级。修复解锁后仪表盘首屏空白。
- AI 助手打磨手机聊天、图片预览、输入区和处理轨迹；上下文与缓存用量同时可见，处理状态使用紧凑文字行，完成后保留可展开的过程。
- 题目详情显示录入日期与 Ledger 精确创建时间，题库支持创建日期排序，助手检索支持创建日期范围与多级排序；旧题缺少精确时间时明确显示缺失。题目正文与导出保留普通换行，答案图文块保持阅读顺序，修复手机详情滚动。
- 展示板增加渐隐、滑页、抽纸及关闭动效选项和时长设置，快速连续操作执行最新目标，系统减少动态效果时直接切换；修复翻页后残留变换，保持预览、打印与纸面记录边界。

# v2.0.0（2026-09-30）

- AI 草稿改成逐题审核工作台，默认先看题目与答案，来源和框选按需展开；手机队列与题目、答案、信息切换减少来回滚动，保存入库仍遵守草稿 revision 与恢复身份。
- 快速录入截图区居中并压缩空态；AI 可补科目、分类、难度和知识点，错因只给有题图文字依据的待采纳候选。模型契约、服务端字段和前端合并共同禁止 AI 修改人工标记；人工字段与迟到请求受到保护。
- AI 助手主聊天区支持拖图，附件和草稿来源图站内预览；手机输入区、消息与工具轨迹收紧。助手可经确认创建零题分类，按版本修订本对话待审草稿，人工修改与入库边界保持保护。
- 聊天中的临时练习卡复用即时练习页面，不创建正式 Session；真实反馈写 Ledger，稳定提交身份防止双击与丢响应重试重复计分，部分失败可续交。
- 笔记本页码退出新题、题卡和快速录入活动路径；旧正文与 Ledger 证据保留，旧库迁移不向无页码题补空字段。反馈、草稿和图片的不同备注继续保留。
- 高频科目、分类、知识点选择器和折叠区域使用共享控件视觉与键盘交互；快速录入手机主按钮的触摸目标至少 44px 高。
- 历史时间线改为分批摘要与按需详情，默认展示题目、动作和结果；缺历史快照明确说明，不用当前题面冒充旧状态。跨页撤销/恢复依赖完整链状态。
- 助手用量圆环可切换缓存占比；详情区分主模型与辅助调用、完整总量与已知总量，缓存和推理 token 不重复计算，供应商缺失数据不显示为零。

# v1.35.0（2026-09-29）

- 新增只读正文覆盖率盘点；创建、移动、外部扫描与正文修改把对应 Markdown blob 随 Ledger 提交入账，启动前只对身份及哈希一致的当前缺口做增量回填。删除前验证正文可取回，正文还原核对题目身份与历史哈希；AI 助手按运行撤销可在部分完成后续做。
- 收件箱图片增加持久修订号，更新、重置、丢弃与录入按修订号及重置代次检查；前端字段补丁、后台任务写回和加载保留未保存的人工编辑。标注集保存与删除也按修订号防止旧页面覆盖。
- 受管检测服务在主站监听前恢复中断操作，检测请求核对实际在线模型身份；训练页分开显示在线模型与训练目录当前模型。未过独立内容验收的候选需明确确认应用，操作记录保存验收状态与服务端认证来源。
- AI 助手对话加载、运行结束和展示板切换丢弃迟到结果；目标板读取失败时保留原板选择与内容。

# v1.34.0（2026-09-29）

- AI 助手设置增加每轮最大输出 Token，默认 10240；可按模型服务商限制调整，减少长思考时工具参数被截断的情况。

# v1.33.1（2026-09-29）

- 收件箱处理区可重置当前截图：保留原图，清空框选、提取结果和题卡进度；旧保存与后台结果不能写回，已有题卡入库时拒绝重置。
- 移除收件箱「模板框选」与「沿用上一张框位」的单图和批量入口、在线实现及配置选项；旧 template 配置转为多模态框选。离线训练评估保留历史模板基线。

# v1.33.0（2026-09-29）

- 收件箱框选改为「一键提取」：默认由 AI 一次返回完整文本或不可提取原因，无法完整转写时保留裁图。
- 取消提取前的保存方式选择；结果出来后可人工编辑文本、改存图片或切回文本，已有文字保留。
- 自动提取不再自动标记就绪，仍须人工审核；失败可重试，过期结果不覆盖已修改的区域。

# v1.32.0（2026-09-29）

- 训练面板增加受管检测服务启停、重启、在线模型身份与操作历史；查看实验和实际应用模型明确分开。
- 模型应用先做限时限内存预检，再核验实际在线SHA；失败回退上一模型，版本冲突、重复请求和中断恢复均有保护。
- 管理权限由部署者按Vault显式登记，网页不能传入任意服务名或命令；现有训练及DeepSeek评测仍由CLI启动。

# v1.31.0（2026-09-29）

- 新增独立训练面板、实时框选测试与可选标注积累，模型服务使用固定ONNX并与主程序隔离。
- 内容评测记录支持原图/裁图对照、筛选、缩放与人工纠正；保留DeepSeek原判、调用失败和复核历史，版本冲突不覆盖。
- 框选验收按内容完整性统计，IoU仅作诊断；离线评测带缓存和调用预算，冻结数据划分，评测不自动发布模型。

# v1.30.0（2026-09-29）

- AI 草稿支持编辑、审核入库、丢弃与聊天卡片联动；确认入库绑定草稿版本，重复提交及中断恢复不会重复建题。
- 来源图可手动框选、转文字或保留裁图；训练按图选择，登记与录入队列隔离，共用图合并标注并安全清理。
- 框选支持询问、自动、手动，自动检测保护人工框和共享图片；全文字草稿可先入库后完成独立训练任务，训练统计包含聊天来源。

# v1.29.0（2026-09-28）

- AI 助手现在可在对话中粘贴、拖入或选择最多 6 张截图；大图缩放后发送，消息里显示 IMG 编号与可打开的缩略图。设置页「主 AI 支持图片」决定主模型直接看图或先读「AI 识别」模型的转述，运行轨迹显示转述状态，连接测试显示图片直传探测结果。
- 助手新增 `create_draft`、`describe_image`、`list_drafts`、`get_draft`，录题进入独立的 `错题/.omrs/drafts/` 草稿存储，不写 Ledger；草稿卡片显示编号、内容摘要、块类型与待审核 / 待框选状态。`create_text_question` 不再注册。草稿审核、编辑与入库界面由后续阶段提供。

# v1.28.1（2026-09-28）

- 合并用户工作区的两处修复（侧栏图标描边、`dueDays` 作 `map` 回调），v1.28.0 AI 助手无冲突合入。
- 补完前端重构 P8：删除 `assets/` 下 23 个旧脚本与旧 `styles.css`（约 780KB，页面早已不加载）和测它们的 16 个旧 node 测试（均已迁到 `tests/app/`）；按钮与输入框统一为 `ui-btn` / `ui-input` / `ui-select` / `ui-textarea`，删除 `styles/controls.css`；外壳去掉旧页面 `enter(win)` 分支；百分比格式统一用 `core/format.js`；删除 3 个调用已不存在全局的展示板冒烟脚本。
- 修复：题库、复习调度、即时练习、反馈录入、外壳的 E2E 改为读真实模块、DOM 与 `window.__omrs`，不再调用已删除的旧全局；外壳 E2E 计入 AI 助手页。`check_docs.py` 的路由提取同时读 `omrs/agent/http.py`。

# v1.28.0（2026-09-28）

- 内置 AI 助手：侧栏「AI 助手」页（对话列表、运行轨迹、内联确认卡与确认对话框、检查器、上下文用量、按运行撤销），设置页新增「AI 助手」分区。后端是自写 Harness（`omrs/agent/`）与 OpenAI 兼容客户端（`omrs/llm/`），16 个工具分只读 / 可撤销 / 需确认三级，权限在服务端；对话存 `agent.db`。
- 并发地基：服务器改为每连接一线程；进程级写锁串行全部持久化写入，等锁超时返回 503；Ledger 追加与计数用 `BEGIN IMMEDIATE` + `busy_timeout`；设置文件原子写入；删除 `Skills/mistake-card-creator`。
- 写入来源新增 `agent`（payload 带运行身份）；题目正文入账：`blobs` 表、`question.content_update`、首次启动回填 `question.content_snapshot`、删除前保存最后一版，新增正文历史 / 取回 / 还原接口，编辑接口支持 `expected_content_hash`（不符 409）。

# v1.27.0（2026-09-28）

- P8：删除旧前端脚本、过渡桥与旧样式，筛选与标记管理迁入 ES Module；全仓 UI 门禁改为零容忍。

# 前端版本变更摘要（changelog）

> 从 `frontend.md` 顶部搬出来的「每版改了什么」叙述，按版本**倒序**排列；`frontend.md` 只保留当前行为。
> 这里每段都是当时写下的原文（未改写），所以段里的「现在 / 原先」以该版本为准；具体文件级变更看 `logs/`。
> 新版本的摘要请追加在最上面；同一版本多次改动时合并进同一段。

## v1.26.6（2026-09-27）前端重构 P6 收尾：录入页框选、题卡、AI 训练工作区原生，删除 inbox.js

- **收件箱前端数据归 `assets/app/features/create/inbox-store.js`**（原经典脚本 inbox.js 的 `IB` 全局、保存队列与任务轮询；旧文件、它的 `<script>`、分步迁移用的 `legacy-inbox.js` 全部删除）：I/O 注入的工厂，单例在 `inbox.js`；网格、处理区、题卡、训练共用一份图片列表与勾选，变化时发 `inbox:changed`。保存沿用 `ibSaveSoon` 语义（防抖合并、`cards` 按题卡合并、同图串行、修订号防覆盖），离开处理区、离开本页、创建题目前 flush；拖框期间收到保存响应只同步状态，不再替换正在拖的对象。
- **框选工作区（Codex 在制的部分）完成**：本张图的编辑全部在 `process.js`，AI / 模板框选、沿用框位、整图、提取与分类在 `inbox-ops.js`，裁图在 `crop.js`；队列与区域面板的旧 `data-ib-*` 点击换成 `data-action` / `data-change` / `data-input`。多题卡时「在此题卡画框」由链接改为按钮。保留图片的裁图预览只在框位变化时重画。
- **题卡工作区原生**（`cards-state.js` / `cards-view.js` / `cards.js`、`cards.css`）：模板不写 `style=` 与 `on*=`，emoji 按钮换成图标；标记走 `domain/labels`，科目、分类、知识点的 datalist 由页面渲染（`core.js` 的 `populateCreateLists` 与三个全局 datalist 删除）；没有就绪题卡时给空态和「去处理」；批量按钮在没勾选时禁用。创建前先写出待存改动，成功后同时刷新统计、历史与目录；批量创建仍只弹一条汇总。
- **AI 训练工作区原生**（`train-state.js` / `train-view.js` / `train.js`、`train.css`）：指标卡用 `ui/stat`，版式与转换决策条用原生 `<progress>`（原为行内 `style="width:…"`），导出改为随格式变化的下载链接，策略表单用 `ui/field` / `ui/select` / `ui/switch`，本地检测地址按提供方显隐（原为行内 `display`），保存结果与读取失败就地显示并可重试；清空裁图缓存的确认改为危险样式。
- **样式**：`.ib-flow*`、工作区显隐与整屏工作台规则从 `styles.css` 搬进 `create.css`（token 化；导航副标题 11.2px → 12px）；`styles.css` 删去收件箱整段、`.lbl-form-add` 与工作台媒体块（含一条空注释）。
- **测试**：新增 `tests/app/create-inbox.test.mjs`（12：保存队列、修订号、轮询、切工作区、题卡、训练模型、裁图参数、框选汇总）；`tests/e2e/create.py` 42 → 80（题卡：必填预检、字段去抖、分类任务、退回处理、单张与批量创建；训练：统计、导出格式、策略显隐与保存、清理确认、读取失败重试；题卡与训练工作区各四种审计）；`tests/e2e/ui_bridge.py` 删去已不存在的 `ibToast` 一项（15 → 14），组件画廊的 toast 说明同步。

## v1.26.5（2026-09-27）前端重构 P7 第 6 轮：展示板整页原生，删除 board.js

- **与 P6 剩余合并（2026-09-27）**：P7 六轮基于 v1.25.4 开发，与 Codex 的 P6 剩余（下文 v1.25.5–v1.25.13，另有录入页框选工作区的在制代码）并行；两条线在此版合并，按 progress §9 取较大的版本号 v1.26.5，此后各页在 v1.26.5 上加 0.0.1。合并时另改：`features/create/quick.js` 的 `import` 从已删除的 `domain/board.js` 改到 `domain/board/index.js`（不改会让整个模块图加载失败）；`legacy-pages.js` 的登记表清空（P6 删完其余五页、P7 删掉 board）；`omrs_dashboard.html` 同时去掉 `board*.js` 与 `history` / `catalog` / `reports` 的 `<script>`；UI 基线文件 按合并后的实测重算（只降不升）。
- **板详情的所有者是 `assets/app/features/board/detail.js`**（原经典脚本 assets/board.js 的 `BOARD_DETAIL` / `BOARD_PRINT_MODE` / `BOARD_SELECTED_UID`、数据加载与详情上的全部操作；旧文件与它的 `<script>` 删除）：控制器只经注入的 I/O 碰外界，缺省 I/O、单例与窗口级监听在 `runtime.js`；保存队列、打印协调、版面设置照旧由它懒创建。板列表（`domain/board/boards.js`）与选板浮层经新端口 `domain/board/detail-port.js` 冲刷、重读、加题（依赖倒置，取代第 5 轮的过渡适配器 `legacy.js`）。
- **列表 / 画廊与检查器原生**：模板在 `view.js`、视图模型在 `state.js`（`contentView`、`inspectorView`、`itemFlags`、`gapReadout`、`dueView`），样式进 `board.css`（类名 `brd-`，只用 token）；整页一次 `morph`，只有舞台 iframe 与画廊题面挂载点是 skip。聚焦中的输入框与滑杆 morph 不改值，所以原来为了不丢焦点而写的「只刷新读数」一套函数全部删去；锁定确认被拒时先放掉焦点再重绘。`styles.css` 删 139 行（`.bd-*`、`.board-add-*`、`.bdadd-*`、`.board-sync-options`、`.qb-search`）。
- **「添加题目」换 `ui/dialog`（`features/board/add.js`）**：Esc、点遮罩关闭，焦点陷阱与归还（原 `.modal-overlay` 弹层 Esc 关不掉，`AI/optimization.md` 那一条随之删去）；勾选跨列表 / 画廊保持；一题都没勾时「加入展示板」留在对话框里。「按标记同步」的单选改用 token 样式。
- **用户可见的变化**：列表行与画廊卡用 `aria-current` 标选中；行上的次要动作（留白、详情）悬停 / 选中 / 键盘聚焦时出现，手机常显；检查器「跳到这道题」在列表 / 画廊视图下先切回纸面再翻页（原来不在纸面时点了没反应）；停用但已打印的题在列表行上只标「停用」（与画廊、检查器一致；原来还标「已印」）；列表行的熟练度从小进度条改为「熟练 N%」文字；纸面记录改成定义列表。
- **过渡桥**：`installBoardBridge` 只挂旧调用方（`app.js`、`labels.js`）与冒烟测试要用的入口，逐条登记；只供旧 `board.js` 用的模型 / 保存 / 打印 / 设置 / 拖拽全局与 `boardPageRepaint`、`adoptBoards` 等不再挂。冒烟测试里的 `window.uiConfirm = …` 改为 `configureBoardDetail({ confirm })`，`BOARD_PRINT_MODE='new'; boardRender()` 改为 `boardSetPrintMode('new')`；`BOARD_DETAIL` 是只读访问器。
- **测试**：`board-locked.test.mjs` 从 vm 跑旧脚本改为注入 `createBoardDetail`（20 → 25）；`board-regions.test.mjs` 的静态检查改查 `view.js` / `state.js` / `detail.js`（条数不变）；`board-page.test.mjs` 12 → 20；`tests/e2e/board.py` 22 → 35（加题 → 排序 → 版面设置 → 打印预览 → 仅补印新增，另有列表视图的审计）。

## v1.26.4（2026-09-27）前端重构 P7 第 5 轮：展示板页外壳原生、板列表数据所有权

- **展示板页成为页面契约 `assets/app/features/board/index.js`**（从 `legacy-pages.js` 删去）：状态条、左栏板列表（文件夹 → 板两级树）、舞台头（视图、内容操作、翻页条、缺失 / 停用警告）用 `html` + `morph` 渲染（`view.js`、视图模型 `state.js`、样式 `board.css`，只用 token）；`#panel-board` 在 HTML 里是空壳，挂载时渲染。常驻预览的舞台、列表 / 画廊、检查器是 `data-morph="skip"`，每层子节点固定，morph 不会挪动 iframe（切视图、折叠、重绘都不重载预览）。
- **板列表的数据所有权归 `assets/app/domain/board/boards.js`**：板列表、文件夹、当前板、上次用的板、折叠状态，以及板 / 文件夹的全部写操作（原 `board.js` 的 `BOARD_DATA` / `BOARD_FOLDERS` / `BOARD_CURRENT`、`boardCreate` 等 13 个函数删除）；选板浮层的 `source.js` 改读它，展示板页与浮层共用一份并随之重绘。板详情、打印范围、列表 / 画廊、检查器与加题对话框仍在 `board.js`（经 `boardPageSnapshot()` 交给新页面，经 `domain/board/legacy.js` 被调用），第 6 轮迁。
- **快捷键进 `core/keys.js` 页面作用域**：`board.js` 的 document keydown 删除（N / A / P、←→ 翻页、↑↓ 选行、Ctrl+↑↓ 换位、Enter 打开、Delete 移除）；对话框、输入框、选板浮层由 core/keys 挡住，标记选择器打开时让位。离开页面前的落盘从侧栏点击捕获阶段改到页面卸载（浏览器后退离开也会落盘）。
- **用户可见的变化**：板 / 文件夹 / 新建 / 排序四个下拉换成 `ui/menu`（键盘可用、进顶层）；板行的主体是按钮（Tab 可达、`aria-current` 标当前板），折叠按钮带 `aria-expanded`；状态条标题旁加「重命名」按钮（双击仍可就地改名）；Enter 在按钮上时不再同时打开题目；板 ⋯ 菜单总有「移到新文件夹…」（原来没有文件夹时整段不出现）；预览生成失败的原因经状态保留，重绘后不丢。
- **测试**：新增 `tests/app/board-page.test.mjs`（12）、`tests/e2e/board.py`（22）；`board-regions.test.mjs` 的状态条 / 舞台 / 骨架三条不变量改查新模板；`board-locked.test.mjs` 注入 `boards.js`；`board_picker.py` 改读 `boardCurrentId()`。

## v1.26.3（2026-09-27）前端重构 P7 第 4 轮：选板浮层原生

- **选板浮层搬进 `assets/app/domain/board/picker.js`**（原 assets/board_picker.js，已删）：内容用 `html` + `morph` 渲染（模板 `picker-view.js`），样式进 `picker.css`（`@layer domain`，只用 token；原 `styles.css` 的 `.bd-picker-*` 55 行删除）；挂载走 `ui/overlay` 的 `hostGuest`（`escape:true`），再进浏览器顶层（popover）。行模型、默认高亮、折叠目标、点击决策、锚定位置都成了 `domain/board/model.js` 的纯函数；过渡期经 `source.js` 读旧 `board.js` 的板列表、文件夹与加题函数。`boardQuickAdd` / `boardChooseAndAdd` 直接打开新浮层，旧代码经过渡桥 `installBoardBridge` 挂回的同名全局调用。
- **键盘进 `core/keys.js`**：新增浮层键盘层 `pushKeyLayer`（最上层优先于页面与全局、在输入框里生效、默认独占）；选板浮层原来挂在 document 捕获阶段的 keydown 删除，旧 `board.js` 的页面快捷键在浮层开着时让位（`boardPickerIsOpen()`）。
- **用户可见的变化**：`Ctrl/⌘ + Enter` 连加（与底栏提示「⌘ 连加」对上，原来 Enter 带不带修饰键都一样）；浮层开着时背后页面的快捷键不再触发（原来焦点不在搜索框时按 V 会切题库视图）；`←` 折叠后紧接 `→` 能展开同一个组（原来折叠后高亮跳到最前面，`→` 找不到组）；`aria-activedescendant` 指向真实的行 id（原来写的是板 id）；「换个板…」的提示写「已从《原板》移到《新板》」（原来原板名总是空）；不在对话框里时关闭后焦点回到触发元素；「已全部在板中」的行用前景色退一档，不再用透明度；可点目标桌面 ≥28、手机 40，手机隐藏底栏键盘提示。其余行为与文案不变；侧栏版本号变为 v1.26.3。
- **测试**：新增 `tests/app/board-picker.test.mjs`（11）、`tests/e2e/board_picker.py`（31）；`core.test.mjs` 加浮层键盘层 3 条；`board.test.mjs` 的模块契约含选板浮层；`questions.py` 两处改查 `.bpicker`。


## v1.26.2（2026-09-27）前端重构 P7 第 3 轮：拖拽排序与版面设置搬进新代码

- **用户可见的只有一处：**「按标记同步」对话框打开时，焦点落在「同步到展示板」按钮上（原来写的是 P2 之前的选择器 `[data-ui-ok]`，找不到按钮，焦点落在默认位置）。其余行为、文案、确认时机都不变；侧栏版本号变为 v1.26.2。
- **拖拽排序进 `assets/app/features/board/drag.js`**：列表行与左栏树的拖拽绑定（`bindBoardRowDrag` / `bindBoardTreeDrag`），落点改成纯函数 `boardRowDropPlan` / `boardTreeDropPlan`，键盘 Ctrl/⌘+↑↓ 与 ↑↓ 的目标位置 `boardKeyReorderTarget` / `boardKeySelectTarget`。拖拽中按 Esc 由浏览器取消，不会误移（新增用例覆盖）。
- **版面设置进 `features/board/settings.js`**：`createBoardSettings` 负责版式字段规范化（`boardNormalizePrint`）、写入与记脏、答案与标记开关立即保存、单题留白、锁定保护（同一轮输入共用一个确认框，确认后本轮去抖保存前不再问）。旧 `BOARD_LAYOUT_CONFIRM` / `BOARD_LAYOUT_GRANTED` 删除，换成 `boardSettings().granted()` / `.revoke()`；`boardApplyPrintField`、`boardSetItemGap`、`boardAllowLayoutChange` 名字不变。
- **测试**：新增 `tests/app/board-settings.test.mjs`（6）、`board-drag.test.mjs`（5）；`board-locked.test.mjs` 注入新模块、改读 `boardSettings().granted()`，`board-regions.test.mjs` 的「改板级字段后刷新读数」改查 `boardSettings()` 注入的钩子，用例不减。

## v1.26.1（2026-09-27）前端重构 P7 第 2 轮：保存队列、打印协调与常驻预览搬进新代码

- **无用户可见变化。** 保存时机（去抖 500ms、答案与标记开关立即保存、切 Tab 前与关页 sendBeacon）、打印预览窗口与下载、「记录纸面」、仅补印新增、重置纸面、常驻预览的消息协议与文案都不变；侧栏版本号变为 v1.26.1。打印预览窗口的占位页不再写行内样式与颜色字面量，改用系统字体与系统色（外观几乎一样）。
- **保存队列进 `assets/app/features/board/save.js`**（`createBoardSaveQueue`、`boardAdoptSaved`）：旧 `BOARD_DIRTY` / `BOARD_SAVE_TIMER` / `BOARD_SAVE_IN_FLIGHT` 删除，`board.js` 的 `boardSaveQueue()` 懒创建唯一实例，当前板、请求、定时器与「采纳服务端返回的板」都由它注入；`boardMarkDirty` / `boardFlushSave` 名字不变。
- **打印协调进 `features/board/print.js`**（`createBoardPrint`、`fetchBoardExport`、`measureBoardLayout`）：旧 `BOARD_PRINT_JOBS` / `BOARD_WINDOWS` 换成 `boardPrint().jobs` / `.windows`；`boardExportCurrent`、`boardMarkPrinted`、`boardResetPrinted`、`boardRecordPrinted`、`boardMarkAwaiting` 等旧名是一行包装。window 的 message 监听仍由 `board.js` 注册，转给 `handleMessage`。
- **常驻预览进 `features/board/preview.js`**：assets/board_preview.js 删除（HTML 少一个 `<script>`），导出请求与打印共用 `fetchBoardExport`；外部读 iframe 改用 `boardPreviewFrame()`。
- **测试**：新增 `tests/app/board-save.test.mjs`（8）、`board-print.test.mjs`（7），`board.test.mjs` 加一条五个模块导出不重名；`board-preview.test.mjs` 改测模块、`board-locked.test.mjs` 注入保存与打印模块，用例不减；smoke_board_integrity.py（v1.28.0 删除：调用的旧全局 P7 起已不存在；覆盖由新版展示板 E2E 承接） 的 `BOARD_DIRTY` / `BOARD_WINDOWS` / `BP_FRAME` 改用新访问器。

## v1.26.0（2026-09-27）前端重构 P7 第 1 轮：展示板纯函数与测试搬进新代码

- **无用户可见变化。** 展示板页、选板浮层、常驻预览、打印与纸面记录的行为、文案、请求体不变；侧栏版本号变为 v1.26.0。
- **页面纯函数进 `assets/app/features/board/model.js`**：打印状态机 `boardStatusModel`、题后留白 `boardEffectiveGap` / `boardItemsPayload`、排序 `boardMoveItems`、保存载荷 `boardDirtyMerge` / `boardSavePayload`、锁定边界 `boardPaperLayoutChanged`、估算文案 `boardEstimateText`、`boardFormatTime`、纸面几何 `boardGapCm` / `boardColumnWidth` 与常量 `CUT_LINES` / `BOARD_LINE_PX` / `BOARD_MM_PX`；另把旧 `boardContentSignature()` / `boardPreviewGaps()` 的计算拆成纯函数 `boardItemsSignature` / `boardGapMap`（旧函数变成一行包装）。
- **选板纯函数进 `assets/app/domain/board/model.js`**：`boardFolderTree`、`boardPickerRowState`、`boardPickerFilter`、`boardPickerRecent`、`boardUniqueUids`。原 `domain/board.js` 改为 `domain/board/index.js`（再导出纯函数，保留 `boardQuickAdd` / `boardChooseAndAdd` 适配器），题目库与数据复盘的 import 随之改路径。
- **过渡桥 `installBoardBridge`** 把两个模块的导出按原名挂回全局，旧 assets/board.js、assets/board_picker.js 删掉对应定义后照常调用。
- **测试**：tests/test_board_ui.js、test_board_regions.js、test_board_preview.js、test_board_locked_incremental.js 迁为 `tests/app/board.test.mjs`、`board-regions.test.mjs`、`board-preview.test.mjs`、`board-locked.test.mjs`，61 个用例原样保留，另加 6 个（签名、留白表、锁定边界、时间格式、几何常量、两模块导出不重名）。

## v1.25.13（2026-09-27）前端重构 P6：收件箱网格与手机上传页

- 收件箱网格迁入 `features/create/`：原图卡片、框位缩略预览、状态筛选、全选与批量操作由页面模块渲染。网格与尚未迁移的处理工作区暂时共用图片列表和选择状态；已录入卡片打开关联题目，批量丢弃失败时保留选择并就地显示原因。
- 手机上传页接入 `tokens.css` 和 `base.css`，颜色改用语义 token，读取与主站相同的浅色 / 深色设置；上传和重复图片合并流程保持不变。

## v1.25.12（2026-09-27）前端重构 P6：快速录入

- 快速录入表单迁入 `features/create/`：题目与答案图片区分别支持选择、拖入、粘贴和显式读取剪贴板，AI 分类与文本提取保留原接口。提交后保留科目、分类、难度、知识点、标记和页码，只清空题目内容与图片；旧全局图片数组、录入函数、内联事件和专属样式已删除。

## v1.25.11（2026-09-27）前端重构 P6：收件箱上传入口

- 录入页上传区改用统一 `ui/filedrop` 控件，支持多张图片选择、拖入和粘贴；非图片与上传失败在控件旁显示原因，上传期间阻止重复提交。成功后通知旧收件箱列表刷新，重复图片仍按原接口合并。旧上传函数、内联事件和专用 dropzone 样式已删除。

## v1.25.10（2026-09-27）前端重构 P6：录入题目工作区外壳

- 录入题目页登记为 `features/create/` 页面契约，工作区导航改为可键盘操作的按钮，训练和快速录入入口使用统一 SVG 图标；切页返回后保留当前工作区。上传、框选、题卡、训练与快速录入内容暂由原控制器承载，按 P6 计划继续逐块迁移。

## v1.25.9（2026-09-27）前端重构 P6：合入 CCW 三轮的差异

- 历史记录修正期间禁用全部写按钮，页面重绘后保留已展开的详情与操作面板。目录恢复默认展开根与一级目录、切页保留展开状态，并修正展开按钮的 `aria-expanded`。
- 报告页删除期间防止重复请求；列表失败时就地提供「重试」，首次加载超过 300ms 才显示骨架。保留现有的页内 sandbox iframe 预览。

## v1.25.8（2026-09-27）前端重构 P6：设置页迁入 features/settings

- 设置页五个分区由 `features/settings/` 管理，访问与 PIN、AI 配置、外观、本地存储、备份与服务状态沿用现有接口和浏览器键名。重启仅在出现新的 `instance_id` 后刷新；只改免 PIN 网段时立即生效，不重启。
- 图片扫描与压缩轮询、备份导入双重确认及脱敏源码下载迁入新模块。删除 `app.js` 的旧设置逻辑、两份旧抽函数测试和只服务设置页的旧 CSS；纯规则测试与隔离实例 E2E 覆盖五分区和四种视觉组合。

## v1.25.7（2026-09-27）前端重构 P6：报告页迁入 features/reports

- 报告页由 `features/reports/` 渲染，上传区使用 `ui/filedrop`，支持拖入和点击选择；非 HTML、空文件、读取失败就地提示，上传期间防重复提交。
- 浏览报告时在页面内打开无 `allow-same-origin` 权限的 sandbox iframe，仍可选择在新标签打开。删除前用统一对话框确认；分析材料的带图 ZIP、纯 Markdown 下载与提示词切换保留。
- 旧报告脚本和专用旧 CSS 已删除；新增 Node 纯规则测试与隔离实例 E2E，覆盖上传、下载、沙箱、删除及四种视觉审计。

## v1.25.6（2026-09-27）前端重构 P6：目录页迁入 features/catalog

- 目录树改由 `features/catalog/` 渲染；结构仍取 `/api/tree`，接口不可用时按题目路径构建后备树。题目状态按文件夹前缀叠加，搜索、展开折叠、显示全部文件、开题目详情和复制路径保留。
- 默认只展开根目录；大量文件夹时可自行展开，桌面与手机均使用原生按钮、图标和语义 token。重新扫描成功后经页面事件重读目录，扫描失败保留原树；复制被拒绝时提示手动复制路径。
- 旧目录脚本和专用旧 CSS 已删除；目录场景迁到 `tests/app/catalog.test.mjs`，隔离实例的 `tests/e2e/catalog.py` 覆盖主路径与四种视觉审计。

## v1.25.5（2026-09-26）前端重构 P6：历史记录页迁入 features/history

- Ledger 时间线、排序、修正模式、修正记录与载荷预览由 `features/history/` 渲染；反馈、Session 和结构化状态的修正仍调用原有 API，成功后刷新题目缓存、统计和 Session，并通知仪表盘最近动态。
- 撤销状态、节点标题、分类、时间格式和排序归 `domain/history-model.js`；仪表盘最近动态直接复用这些函数，不再读取旧全局。旧历史脚本及专用的旧 CSS 已删除。
- 历史页使用语义 token、统一按钮与对话框，空态和错误态给出原因与重试；桌面、手机、浅色、深色的字号、可点目标、行内样式与溢出审计通过。

## v1.25.4（2026-09-25）前端重构 P6 第 5 轮：「全题库导出」迁进复习调度页，复习调度三块全部原生

- **「全题库导出」原生实现**（`features/schedule/exporter*.js`）：筛选、标记、平铺式 / 画廊式、选择当前筛选 / 移除当前筛选 / 清空、A4 打印版与屏幕版、附带答案、题间留白、导出；规则、文件名与请求体不变，旧 id（`#export-panel`、`#pick-*`、`#export-*`）保留。屏幕版时「附带答案」显示为已勾选且不可改、留白不可改（原来可以勾但不生效）；没选题、导出成功与失败都显示在导出栏。已选区超过约 22em 时内部滚动，选题区不再被挤到很远。
- **导出统一走 `domain/exporting.js`**（`POST /api/export` + `core/download.js` 下载）。「已有计划」的导出打印版 / 屏幕版也改走它：结果显示在详情里，按钮进行中置忙。
- **删除** assets/export.js、`domain/schedule.js`、`core.js` 的 `EXPORT_SELECTION` / `EXPORT_VIEW`、旧刷新链里的 `syncExportSelection` / `renderExportPicker`、过渡桥的 `schShow` / `showRecommendPanel`（仪表盘「开始复习」改为发页面事件），以及 `styles.css` 里只服务旧导出面板的规则（22 条）。旧的 `downloadExportResponse` 全局保留给备份导出、报告与题库批量 A4，实现换成 `core/download.js`。

## v1.25.3（2026-09-25）前端重构 P6 第 4 轮：「安排复习」迁进复习调度页

- **「安排复习」原生实现**（`features/schedule/arrange*.js`）：筛选、推荐方式、标记筛选、按建议选择、列表 / 画廊、选择栏、生成计划，规则与文案不变；旧 id（`#rec-*`、`#recommend-panel-v2`）保留。
- **画廊题面恢复显示。** P5 之后旧推荐画廊引用的 `QV_CARD_OPTS` 没有被过渡桥挂出，题面一直停在「正在加载题面…」；新实现直接从 `domain/question` 取，挂载点 `data-morph="skip"`，重绘不重挂。
- **手机列表每行两行**（勾选与题目一行，理由、熟练度与「预览」一行），UID 不再是第二个预览按钮；可点目标桌面 ≥28、手机 ≥40；分段切换改为 28 / 40 高。
- **删除调度后**详情区显示「调度已删除」（原生「已有计划」上一版显示的是「选择一个计划」）。
- **`tests/smoke_schedule_workbench.py` 全部通过**（P4 之后第一次）：选择器改到新标记；删除确认框之间等退场动画结束（ui/dialog 另有标题栏关闭按钮，旧写法点到两个）。
- **删除** assets/recommend_v2.js、tests/test_recommend_v2_filters.js（用例迁到 `tests/app/arrange.test.mjs`）、questions.js 里只给推荐用的 `reviveChipHtml`、旧数据刷新链里的 `initRecommendV2`，以及 `styles.css` 里只服务旧推荐区的规则（约 170 行）。

## v1.25.2（2026-09-25）前端重构 P6 第 3 轮：复习调度迁到 features/schedule，Session 列表归 domain/sessions

- **复习调度成为 features 页面。** 顶部标签栏与「已有计划」由 `features/schedule/` 渲染；「安排复习」「全题库导出」两块仍是旧 DOM，作为页面挂载点里的兄弟节点，由页面切显隐（下一轮迁）。标签栏吸顶，手机上列表与详情分两屏。
- **「已有计划」重做**：列表、筛选、详情、删除、导出、录入结果全部原生；打印选项的展开状态与勾选在重绘后保留；刷新 Session 列表时当前详情保留内容不闪骨架（原来整块换成「正在读取计划详情…」）；删掉的计划不会被随后的刷新重新打开。
- **Session 列表归新代码所有。** `domain/sessions.js` 负责加载、快照与发布（后发先至只认最新、失败保留旧列表、删除后让进行中的旧加载作废）；旧 `SESSIONS` 是镜像，全局 `refreshSessions` 由过渡桥挂成新实现。进度计算 `sessionProgress` 从反馈页 state 搬进 domain，两页共用。
- **从别的工作区切回「安排复习」会重拉推荐**（原来只重绘旧数据；P1 起点侧栏当前页不再重新进入，冒烟测试因此停在「空推荐提示」一步）。
- **删除** schedule.js 里复习调度页的全部代码（文件只剩录入题目、全局扫描与两个旧入口）、旧 node 测试 tests/test_schedule_sessions.js（用例迁到 `tests/app/schedule.test.mjs` 与 `tests/e2e/schedule.py`）、`styles.css` 里只服务旧标签栏与计划列表的规则（34 条）。

## v1.25.1（2026-09-25）前端重构 P6 第 2 轮：数据复盘迁到 features/data

- **数据复盘页重做版式。** 八格概览放进一张卡；20 张图表卡自动成两栏（按标记正确率、复习预警、顽固题、屡练不熟整行），标题去掉 emoji（D7）。表格换成 `ui/table`（手机降级为卡片，原来横向截断）；横条换原生 `<progress>`；颜色一律经 `data-tone` 走状态 token（原来是 `style="color:var(--red)"` 这类行内样式，D11）。统计口径、分档配色、区块顺序与表格列不变。
- **运行时审计**（`tests/visual/run.py`）：本页字号 14 → 3 种、最小字号 8.7 → 12px，行内样式 177 → 0，手机上的可见溢出 1 → 0。
- **数据何时更新**：进入页面、点「刷新」、以及写操作后统计快照变化时都会重拉 `/api/analytics`（原来只在进入与刷新时拉）。首次加载失败给原因与「重试」；已有数据时刷新失败保留旧数据、只在页首报错。
- **导出**改经新的 `core/download.js`：文件名取服务端 `Content-Disposition`；成功弹 toast，失败原因写在页首。
- **删除** assets/data.js 与 `styles.css` 里只服务它的规则（74 行）；旧数据刷新链不再画数据复盘的两张图（页面自己订阅统计快照）。
- 测试：新增 `tests/app/analytics.test.mjs`、`tests/e2e/data.py`。

## v1.25.0（2026-09-25）前端重构 P6 第 1 轮：统计数据所有权反转到 domain/data.js，仪表盘迁到 features/dashboard

- **统计数据归新代码所有。** `assets/app/domain/data.js` 负责拉 `/api/stats`、持有快照并经 bus 发 `data`；旧 `DATA` 是它写好的镜像（与 `store.data` 同一对象），旧页面的刷新链改名 `legacyDataRefresh()`（`app.js`），由过渡桥登记为钩子。全局 `reloadData()` 由过渡桥挂成新实现，调用方不变。
- **并发合并与失败处理。** 一次加载进行中再调用只排一次补拉，之后的调用共享它（原来每次调用各发一次请求，先发后到时旧数据会覆盖新数据）。加载失败保留上一份快照；原来会换成 `core.js` 里的演示数据（6 道假题），服务重启的几秒里首页会闪出假数字。`demo()` 已删。
- **题目详情缓存归 `domain/question/mount.js`。** 旧代码读的 `QUESTION_CACHE` / `QUESTION_PENDING` 改为过渡桥挂的只读全局；`core.js` 删掉这两个 `let`。
- **仪表盘迁到 `features/dashboard/`（D8）。** 「今天」放进独立卡片（原来数字直接压在页面背景上），「开始复习」不再是紧贴行动推荐卡的通栏黑条，各块之间统一 16px；行动推荐的字符图标（◷ ○ ↓ ◆）换成 SVG；全页字号收到 6 档，可点目标桌面 ≥28、手机 ≥40，没有行内样式与 `onclick`。热力格不再在格子里写日期（两行各 15 格，首尾标日期，悬停看当天次数）；最薄弱科目的条改用原生 `<progress>`。规则与文案不变，行动推荐的跳转从闭包改成描述对象，题库预设经 bus `questions:preset` 交给题库页。
- **删除**旧仪表盘的两个脚本 assets/dashboard.js 与 assets/actions.js，以及 `styles.css` 里只服务旧仪表盘的规则（223 行，含 P3 遗留的一个只剩注释的 `@media(max-width:900px)` 块）。数据复盘页的「每日练习趋势」「标记分布」两张图搬进 assets/data.js（v1.25.1 删除，见 features/data）（`renderDataCharts()`）；标记分布的条改用原生 `<progress>`，其余不变。
- 测试：新增 `tests/app/dashboard.test.mjs`（行动推荐、今天、概览、热力、最薄弱科目）、`tests/app/data.test.mjs`（所有权、合并、失败）与 `tests/e2e/dashboard.py`；`smoke_frontend_actions_catalog.js` 与 `test_question_suspend_frontend.js` 里行动推荐的断言迁入新单测。

## v1.24.2（2026-09-25）前端重构 P5 第 4 轮：标记迁到 domain/labels，qview 外观归位（P5 完成）

- **标记芯片不再写行内样式。** 芯片、色板、颜色圆点只写 `data-lbl-c="rrggbb"`；每种颜色由运行时样式表（`<style id="omrs-label-colors">` 的 `@layer domain` 块）登记一条规则给出 `--lbl-c` 等变量。颜色算法（浅 / 深主题下的 AA 文字色钳制、solid 前景）原样迁移，芯片外观不变。预设色移到 `tokens.css` 的 `--lbl-preset-1…10`，`domain/labels/` 的 JS 里没有颜色字面量。
- **`domain/labels.js` 扩成 `domain/labels/`：** `color.js`（颜色）、`sheet.js`（运行时样式表）、`chips.js`（芯片）、`model.js`（排序、增改、选择器候选、最近使用、快速区、下一个颜色、批量增删、管理表单规范化，全部纯函数）。旧 labels.js 里这些函数删除，经过渡桥 `installLabelsBridge` 挂成同名全局；选择器浮层与标记管理的 DOM 仍在旧 labels.js。
- **qview 的全部外观搬进 `domain/question/qview.css` 并换成 token**（连同导出选题、展示板画廊、复习调度预览对它的覆盖），旧 `styles.css` 净删 100 行。可见变化：题面 / 答案按设计系统的阅读正文显示（16px、行高 1.75，原 12.9px / 1.8），缩略卡 13px；题头去掉旧全局 `header` 规则带来的 16px 顶部空白；题头与记录模块字重 600，小字统一到 11 / 12px；深色主题下答案块恢复浅绿底（原被深色覆盖规则盖掉）。题目弹窗的字号种数 6 → 5。
- **测试：** 原 test_labels_ui.js（已删除）迁到 `tests/app/labels.test.mjs`（原 5 个用例保留，新增 5 个），node 192 → 197；E2E 的「不写行内样式」审计去掉对芯片的排除，另加一项检查芯片颜色走运行时样式表；`check_contrast.py` 加「正文 / 次文字压在题面块上」两组。

## v1.24.1（2026-09-25）前端重构 P5 第 3 轮：题目弹窗与 Markdown 编辑器换成 ui/dialog

- **题目弹窗是 `ui/dialog`（`domain/question/modal.js`）。** 进浏览器顶层、焦点陷阱（背景拿不到焦点）、Esc 与点遮罩关闭、背景滚动锁定；关闭后焦点回到触发它的元素——从题库打开时回到那一行，翻过页则游标与焦点落在最后看的那一题。翻页条与关闭按钮换成 `ui-btn`，手机上翻页按钮只留图标、可点区域 40×40，题面区单独滚动、头部不动。
- **Markdown 编辑器是叠在题目弹窗上的第二个 `ui/dialog`（`domain/question/editor.js`）。** 有未保存修改时 Esc / 点遮罩不关并在状态行提示；Ctrl / ⌘ + Enter 保存；保存失败留在编辑器里写出原因；内容没改时「保存」直接关闭、不写文件；关闭后焦点回到「编辑」按钮。旧 `questions.js` 的编辑器与 `omrs_dashboard.html` 里两个旧弹窗外壳删除。
- **叠在对话框上的旧浮层可以用了。** 标记选择器、选板浮层、标记管理打开时放进最上层对话框（`ui/overlay` 的「客人」，旧代码经 `__omrsUi.host`），不再被模态对话框 inert；Esc 与点外面先关浮层、对话框留着，对话框关闭时一并关掉浮层。标记管理可以按 Esc 关闭。
- **`ui/dialog` 扩展：** `--xl`（1180）尺寸、`id`、异步 `onOk`（返回 false 留在对话框，确定按钮忙碌态）、`dismissible` 可为函数、`returnFocus()`、`onOpen(el)`、`closeDialog(el)`；多行文本里 Ctrl / ⌘ + Enter 也能确认。退场动画中的对话框不再挡快捷键。
- **修正：** 在题目弹窗里打标记后，弹窗里的标记芯片不再停在保存前（qview 的标记改以题目列表为准）。Esc 关题目弹窗改由 `ui/overlay` 处理，过渡桥 `installEscapeBridge` 删去关弹窗那一条。
- **测试：** 浏览器单测 31 → 34（客人浮层；onOk / dismissible / Ctrl+Enter；returnFocus）；`tests/e2e/questions.py` 70 → 91（焦点陷阱与回到行、浮层在弹窗里真实可操作、编辑器写回文件、弹窗打开状态审计）。

## v1.24.0（2026-09-25）前端重构 P5：共享题目视图与题目库迁到新架构

- **第 1 轮：共享题目视图 `domain/question/`。** Markdown / KaTeX 渲染按内容哈希缓存、练习记录、qview、详情缓存与题目弹窗收进一个领域模块，旧代码经过渡桥 `installQuestionBridge` 用同名全局；qview 以挂载点为容器（窄挂载点题面单栏），超宽公式只在自己的块里横滚；弹窗 ←/→ 接入 `core/keys.js`。
- **第 2 轮：题目库是第三个迁到 `assets/app/features/` 的页面。** `features/questions/`（`index.js` / `state.js` / `view.js` / `list.js` / `dialogs.js` / `questions.css`）按页面契约挂载；旧 `qtable.js`（全部）、`questions.js` 的表格 / 画廊 / 操作部分、面板里的旧 HTML、`styles.css` 里约 170 条 `.qb-*` / `.question-gallery-*` / `.q-edit-*` 规则与 `legacy-bridge.css` 的「题库工具栏」段一并删除。题目操作（迁移、停用 / 恢复、删除、批量停用、导出 A4）迁到 `domain/question/ops.js`，题库页、弹窗与各处 qview 按钮共用。
- **勾选、筛选、切视图不再重建列表。** morph 差量更新，画廊题面挂载点只在换题或换密度时重挂；双滑块拖动中只预览命中数，松手才重排。
- **窄屏。** ≤760 表格降级为卡片列表（每格带小标题），全部可点目标 ≥40px，搜索框占满一行、提示文字不截断；≤1160 筛选抽屉折到列表上方；>1160 整屏工作台，表头吸顶，列表与抽屉各自滚动。
- **对话框与菜单换成 ui 组件。** 行内「⋯」用 `ui/menu`；停用 / 删除 / 迁移 / 批量打标记 / 存为视图 / 管理视图用 `ui/dialog`（批量打标记可当场新建标记并添加，不再二次弹框）。
- **快捷键接入 `core/keys.js`**（`/`、F、V、`[` `]`、↑↓、Space、Enter、B、L、Esc）。旧 `qtable.js`、`labels.js`、`app.js` 各自挂在 document 上的 Esc 监听收进过渡桥 `installEscapeBridge`：标记选择器开着先关它，再关题目弹窗——修正了「按 Esc 关弹窗时顺手清空了题库勾选」这类同一次按键被两处处理的问题。
- **偏好、视图预设与旧入口兼容。** localStorage 键名与视图预设格式沿用旧版，旧版存下的视图照样能用；仪表盘行动建议、「在题目库打开」经过渡桥 `questionsLoadPreset()` 先清空全部条件再套用（停用筛选不会残留）。题面换行偏好归 `domain/question/markdown.js`。
- **一处有意差异：** 画廊卡「未练习」只在从未作答时显示；作答过但熟练度为 0 的题显示 0% 进度条（改前两者都显示「未练习」，与旁边的「1 次」矛盾）。
- **测试。** 原 qtable 单测文件（3 个用例，已删除）与旧画廊脚注用例并入新增的 `tests/app/questions.test.mjs`（20 个用例，state 纯函数全覆盖）；`tests/e2e/questions.py` 扩成题库主路径 + 弹窗 + D4 + 桌面 / 手机 × 浅 / 深审计（23 → 70 项）。

## v1.23.0（2026-09-25）前端重构 P4：反馈录入迁到新架构

- **反馈录入是第二个迁到 `assets/app/features/` 的页面。** `features/feedback/` 按页面契约挂载；旧的 feedback.js（616 行）、面板里的旧 HTML 与提交结果弹窗 `#fb-result-modal`、`styles.css` 里 105 条 `.fb-*` / `.result-row` 规则一并删除。新增适配器 `domain/sessions.js`（Session 列表与当前选中、题目查找、标记、展示板、剪贴板），页面只经 `domain/` 碰旧全局。
- **判定、打分、写备注不再重建题面。** morph 差量更新，题面挂载点只在换题时更换：KaTeX 节点、图片与滚动原样保留，聚焦的按钮与滑杆不丢焦点。
- **提交结果改用 `ui/dialog` 弹窗**，状态行留「查看本次结果」可重开；空状态统一用 `ui/empty`；Session 列表读取失败时顶栏给出原因。
- **窄屏题面单栏。** ≤1160 单栏竖排、题目列表变横条；题面双栏在挂载点 ≤680px 时改单栏（以挂载点为容器补上 qview 自身容器查询不生效的问题）；整行超宽的公式只在所在段落内横滚，手机上不再撑出整页横向滚动。
- **快捷键接入 `core/keys.js`**（J / K、↓ / ↑、1 / 2、0 与 3–9、Enter、E、⌘ / Ctrl + Enter，与即时练习一致）；在本页空白处 ⌘ / Ctrl + V 读答题卡改为挂载期间的 paste 监听，卸载即移除。三个导入入口共用纯函数 `importer.js::planImportText()`，答题卡与反馈 JSON 的解析规则、报告措辞逐字迁移。
- **测试。** `test_feedback_ui.js`、`test_omr_import.js`、`smoke_feedback_omr_import.js` 的断言全部并入 `tests/app/feedback.test.mjs`（15 → 24 个用例）；新增浏览器 E2E `tests/e2e/feedback.py`（31 项）。`smoke_schedule_workbench.py` 的对话框选择器已随 P2 更正，反馈部分首次实际跑通。
- **与旧页面的一处有意差异：** 导入反馈 JSON 失败（如题目已全部录入）时不再顺手切换当前 Session。

## v1.22.0（2026-09-25）前端重构 P3：即时练习迁到新架构；DP4 顶栏瘦身

- **即时练习是第一个迁到 `assets/app/features/` 的页面。** `features/instant/` 按页面契约挂载，旧的 instant.js（177 行）、面板里的旧 HTML、`styles.css` 里约 80 行即时练习规则与 `legacy-bridge.css` 的「题数」段一并删除。新代码只经 `assets/app/domain/` 的四个适配器碰旧全局（题目详情与 qview、全站筛选语义、标记、reloadData）。
- **判定不再重建题卡。** 用 morph 差量更新，题面挂载点只在换题、翻答案时更换：判对错、打分、切队列时题面节点与 KaTeX 公式原样保留（改前每次判定 6 个公式全部重新渲染），聚焦的按钮与滑杆不丢焦点。
- **界面按新规范重做。** 筛选条、对 / 错分段按钮、空 / 加载 / 出错状态、进度与提交、队列、提交结果全部换成 ui 组件与 token；页面自身字号由 12 种（最小 9.6px）收到 3–4 种，小于 28px 的可点目标由 3 个降到 0（标记筛选芯片由 20px 改为正常按钮）。>1160 为整屏工作台，≤1160 单栏、队列变横条，≤760 手机布局；题面双栏在窄容器里改单栏。
- **快捷键。** 与反馈工作台一致：J / K、↓ / ↑ 切题，空格显示答案，1 / 2 判对错，0、3–9 打分，Enter 下一道未判定，E 编辑，⌘ / Ctrl + Enter 提交。
- **行为修正。** 已提交的题锁定，不能改判、不会被重复提交（改前提交后清空全部判定，同一题可再判再交）；有未提交判定时重新取题先确认（改前直接丢弃）。
- **页面契约补全。** 外壳在登记页面时注册契约里的 `actions` / `keys`（改前只调用 `mount`）。bus 新增 `labels`、`instant:load` 事件；过渡桥新增 `instLoadPractice(preset)` 与只读 `INSTANT_QUEUE`。
- **DP4：顶栏只留「录入题目」。** 「重新扫描」移到仪表盘概览条、题库工具栏、目录工具栏，三处共用 `app.scan`：扫描期间按钮置忙，目录页扫完重读目录树；扫描成功提示改为成功色。
- 测试：新增 `tests/app/instant.test.mjs`（7 项）、`tests/e2e/instant.py`（23 项）、core 浏览器单测 1 项；`tests/e2e/shell_router.py` 18 → 20。


## v1.21.0

- **前端重构 P1：hash 路由与启动接管。** 地址形如 `#/questions`：刷新停在原页，浏览器前进后退可用，页面能直接用链接打开；未知地址回到仪表盘，`href="#"` 这类非路由 hash 不再把页面带跑。`app.js` 不再自调用 `init()`，改由模块入口 `assets/app/main.js` 依次安装过渡桥、启动外壳、调用 `init()`、启动路由。`switchTab` 缩成 `router.go` 的一行包装（旧 `onclick` 不用改），原来的标题表、工作台列表与进入各页的 if 链搬进 页面登记模块。
- **core 底座补齐。** `assets/app/core/` 新增 `morph`（带 `data-key` 的差量更新，保留聚焦输入框的值与选区，支持 `data-morph="skip"` 与 `data-hash`）、`events.js`（`data-action` 委托）、`keys.js`（按页快捷键）、`store.js`、`bus.js`、`router.js`、`api.js`（统一 `{ok, data, error}`）、`format.js`，以及 `html.js` 的 `each()`。旧 `reloadData()` 之后经 `window.__omrs.emit('data', DATA)` 同步到新 store。
- **外壳打磨。** 侧栏、顶栏与工作台整屏布局迁到 `assets/app/styles/shell.css`（新增 `shell` 层）与 `base.css`，按尺度 token 重排：导航项 40px（紧凑 36px）、当前页强调浅底 + 左侧指示条 + `aria-current`，导航改成可用键盘访问的 `<a href="#/页面">`；折叠为 58px 图标栏时有过渡并用提示显示页面名；顶栏标题 20px 半粗、全局按钮带图标。手机（≤760px）抽屉切页后自动关闭，顶栏按钮只留 40×40 图标，标题不再被挤压。原 860px 的抽屉断点改为设计系统的 760px。旧 `styles.css` 里对应的外壳规则删除。
- **静态资源 304。** `/assets/` 响应带弱 ETag 与 `Last-Modified`，文件没变时回空的 304，远端经 Nginx 访问不再每次整包重下。
- **门禁。** 新增 `tests/app/core.test.mjs`（node 9 项）、`tests/app/core_tests.js`（浏览器 6 项，并入 `run_browser.py`）、`tests/e2e/shell_router.py`（18 项）、`tests/test_asset_cache.py`（6 项）。DP4（顶栏只留「录入题目」）等用户确认，未执行。

## v1.20.0

- **前端重构 P2：ui 组件库 v1 与组件陈列页。** `assets/app/ui/` 新增 23 个无业务组件（按钮、图标、字段、选择框、开关、分段、标签页、标签、徽标、卡片、统计、表格、对话框、抽屉、菜单、通知、空状态、骨架屏、局部状态、进度、提示、快捷键、文件拖放）和 55 个自绘 SVG 图标；`assets/app/gallery.html` 按状态矩阵陈列全部组件（浅 / 深 × 舒适 / 紧凑）。P1 尚未执行，本期先带入 P2 必需的底座：`assets/app/package.json`、`core/html.js`（`html``` 默认转义）、`core/dom.js`（唯一写 innerHTML 处）、模块入口 `main.js` 与过渡桥 `legacy-bridge.js`；路由、ETag、`init()` 接管与外壳打磨仍归 P1。
- **全站只剩一套 toast、一套对话框。** 旧 `uiToast` / `uiDialog` / `uiPrompt` / `uiConfirm` 与收件箱 `ibToast` 改为转调新组件（签名不变，模块就绪前的调用排队补发）。对话框改用 `<dialog>.showModal()`：焦点陷阱、Esc / 遮罩关闭、关闭后焦点回到触发元素、锁定背景滚动，能叠在旧弹层之上；危险确认默认聚焦「取消」。旧 `.ui-toast`、`.ib-toast`、`.ui-dialog` 样式与死样式 `.bd-toast` 删除，`#ib-toast` 元素删除。
- **样式分层。** `omrs_dashboard.html` 只引 `tokens.css` 与新的 `assets/app/styles/index.css`：KaTeX、旧 `styles.css`、组件、过渡层按 `@layer` 排序，新样式不再靠提高选择器权重压旧规则。浏览器下限随之为 Chrome 99 / Safari 15.4 / Firefox 97。
- **旧按钮、输入框、下拉统一高度与外观（修 D2、D3）。** `styles/legacy-bridge.css` 给旧 `.btn` / `.input` / `select.input` / `textarea.input` 套新外观，旧 `styles.css` 里被接管的基础规则删除：题库工具栏同一行原有 21 / 28 / 38 / 41 / 43 五种高度，现在统一为一档；窄屏（≤760px）三档控件统一为 40px，满足移动端可点目标（D9）；即时练习页移动端筛选 select 文字不再被裁切。旧 `.modal` 弹层外壳同步换成新的圆角、阴影与关闭按钮。
- **后端小改。** `/assets/` 增加 `.html`、`.mjs` 的 content-type（组件陈列页）；脱敏源码导出收录 `assets/app/package.json`。
- **门禁。** 新增 `tests/app/run_browser.py`（组件浏览器单测 24 项，可另存 gallery 截图）、`tests/app/html.test.mjs`、`tests/e2e/ui_bridge.py`（过渡桥主路径 E2E）、`tests/test_app_browser.py`；`tests/check_contrast.py` 增加主按钮悬停、危险按钮悬停、选中行三组，浅 / 深共 54 组。

## v1.19.1

- **前端重构 P0：设计 token 与门禁。** 全部 token 移到 `assets/app/styles/tokens.css`，改为「语义 token + 旧名别名」两层，旧样式不改即跟随。新增 `tests/check_ui.py`（新代码零容忍规则 R1–R9 + 旧代码按文件计数的棘轮基线 UI 基线文件）、`tests/check_contrast.py`（浅/深 48 组 WCAG 对比度）、`tests/fixtures/make_vault.py`（演示 Vault）、`tests/visual/run.py`（前后截图对比与运行时审计）。
- **浅色主题对比度修正。** 辅助文字 `#8b9198`→`#6b7178`（3.2→4.9:1）、绿色 `#16a34a`→`#15803d`（3.3→5.0:1）、黄色 `#ca8a04`→`#a16207`（2.9→4.9:1）、红色 `#dc2626`→`#d02020`（在页面底上 4.50→5.0:1）；击杀 / 顽固芯片字加深到 `#166534` / `#854d0e`（4.4→6.1:1 以上）。深色主题原本全部达标，未改。
- **删除死代码 recommend.js。** 31 个函数中 28 个无外部引用、所操作的 DOM 已不存在；仍在用的 `showRecommendPanel()` / `showExportPanel()` 并入 `schedule.js`，`core.js` 里配套的 `REC_*` 全局一并删除。
- **脱敏源码导出收录 `tests/` 下的 JSON。** 否则棘轮基线不随包导出，下一轮受限模式的 `check_ui.py` 会直接失败；其它目录的 JSON 仍不导出。

## v1.19.0

> **v1.19.0 错因迁出题面区 + 已击杀题复燃周期**：两件事，一件版式、一件算法。① **错因泄漏答案**：`## 错因` 一直被排进**题面区**，复习时题目下面直接写着「为什么错」，等于把解法提示给正在作答的人；错因和答案同属「做完才能看」的信息。同时 A4 导出的「二、反馈勾选表」（纸面手填的遗留物，反馈早已改在反馈页录入）也不再需要。改法：`_build_export_data()` 把 notes 拆开——`questions[i].notes` 只带 `关联`（关联是线索不是答案，留在题面区），`answers[i].notes` 只带 `错因`；`data["feedback"]` 键整套删除。A4 `buildBlocks()` 正文重排为「一、题目 / 二、反馈区」：反馈区里每题一块，「第 N 题 [UID]」标题行下面直接跟答案正文，**紧接着**同题错因块（`noteBlock`），同属一块不另起标题，即「答案和错因不分开」；该题既没答案也没错因时不占位，整节无内容连标题都不输出。**未勾选导出答案时反馈区仍然出现**，只是只剩错因，导语改为「本次未导出答案，只列错因」——反馈区是常设区域，不是答案的附属。屏幕版错因移进「显示答案」折叠区之后，展示板补上答案附页的错因块（`answers:"none"` 时整份不给错因，作答纸不给提示）。`.fb-row` 样式与那张表一并删除。② **击杀即永久消失**：`is_killed_state()` 原先在 `schedule_questions()` / `generate_recommendations()` 里直接 `continue`，而投影只在答错时把标签降回待攻克、熟练度留在 1.0——结果是「击杀 = 从系统里删掉」，与记忆规律相反。改法：新增 `revive_dormant_days()` / `is_revive_eligible()`（`common.py` 新增 `revive_decay_threshold` / `revive_tier_multiplier` / `revive_priority_bonus` / `kill_demote_factor` 四个 tuning 键），休眠时长按现有衰减式反解 `(mastery×30+5)×ln(1/threshold)×multiplier^(kill_count-1)`，第 1/2/3/4 次击杀后约 **56 / 101 / 182 / 327 天**，即「周期较长 + 越熟练越长」。`mastery_projection` 新增 `kill_count` 列（只在击杀时累加、降级不重置，老库 `PRAGMA table_info` 探到缺列后 `ALTER TABLE` 补齐），复燃题的旧 `Due_Date` 早已逾期，自然落入到期列表并因 `revive_priority_bonus` 靠前。复燃后答错：标签回 `#状态/待攻克`，熟练度 `× kill_demote_factor`（0.3）、`repetition = 0`、`interval = 1`，配合既有 `attack_bonus` 立刻回到推荐前面；`kill_count` 保留，下次周期自动更长。界面在题库状态列、画廊异常标记、推荐列表选题行与题目详情四处显示「复燃」chip（`title` 写明第 N 次击杀、休眠天数与原定日期）——「这题不是已经击杀了吗，怎么又回来了」必须在列表上直接读到。停用题不参与调度，故不出复燃 chip；画廊里「停用 / 复燃」二选一，且复燃优先于「逾期 N 天」（复燃题的 `Due_Date` 是击杀时的旧值，说「逾期 90 天」会读成没做完的旧账）。`omrs/version.py`、侧栏与根 `README.md` 提到 **v1.19.0**。

## v1.18.2

- 修复展示板锁定后追加新题会清空纸面记录、被迫全部重印的问题：增删引用、排序与调整未打印题留白保留已印题目、页数及续排位置；仅新增导出继续沿用旧纸面。
- 锁定保护只针对会影响已打印区域的版式修改，保留明确确认流程；前端提示与后端判定保持一致。补充后端与前端回归测试。

## v1.18.1

> **v1.18.1 反馈提交结果改弹窗**：起因是「反馈录入后的结果显示占用屏幕空间还关不掉」。原先 `submitFb()` 把「本次处理结果」直接 `innerHTML` 进页内 `#fb-results`；宽屏 `.content.is-workbench` 下 `.panel.active` 是整屏 flex 列且 `overflow:hidden`，这块没有 `flex-shrink:0`，明细一多就把 `.fb-work` 三栏挤矮、超出部分被裁到屏幕外，而它只有换 Session 或重新导入才会消失，没有任何关闭入口。改法：新增 `#fb-result-modal`（`.modal-overlay` + `.modal.fb-result-modal`，与 `#modal` / `#md-editor` 同骨架），`#fb-results` 搬进弹窗当滚动区 `.fb-result-list`，页内只留 `.fb-statusbar` 一行（`#fb-status` 小结 + `#fb-result-reopen`「查看本次结果」）。`feedback.js` 新增 `FB_LAST_RESULT` 与 `fbResultRowsHtml` / `fbResultMetaText` / `fbOpenResults` / `fbCloseResults` / `fbClearResults` / `fbSyncResultReopen`；原先三处「清空 `#fb-results`」（`onFbSessionChange(true)`、`fbImportOmrScan`、`fbImportFeedbackPayload`）统一改调 `fbClearResults()`，关闭与清空分成两件事——关掉只是收起来，结果留着可重开。关闭入口四个：`✕` / 「知道了」/ 点遮罩 / `Escape`；弹窗开着时 `fbHandleKey` 只认 `Escape`，`J`/`K`/`1`/`2`/`⌘`+`Enter` 不再穿透到判定面板，`fbHandlePaste` 同样让路。明细行 `.result-row.ok/.err` 与掌握度、SM-2、来源标记的渲染内容不变，`/api/feedback` 与提交体 `{uid, sub_score, is_correct, note}` 零改动。新增反馈结果弹窗回归用例（20 项），守弹窗开关、快捷键不穿透、换 Session 清结果。`styles.css` 与 `feedback.js` 的 `?v=` 刷成 `20260912-fb-result-modal`。

## v1.18.0

> **v1.18.0 展示板重构：状态条 / 舞台 / 检查器三区**：起因是「展示板的 UI 操作有点太怪」，拆出来是四条职责放错位置——能做什么随视图变（纸面有检视条、列表是行内控件、画廊两样都没有）、打印范围藏在会遮住纸面的浮层里、题后留白有三个彼此不可见的入口、打印状态机没有落脚点（未打印 / 已印 N 页 / 新增 M 题 / K 题已改动散在副标题、警告条、行内徽章和浮层里，没有一处说下一步做什么，所以最容易漏掉「标记为已打印」）。改法：新增纯函数 `boardStatusModel(board, mode, awaiting)` 一处算出状态 chips、打印范围、唯一主行动与一句「为什么」；`#bd-statusbar` 承载它，打印范围分段 `[data-board-modes]` 从浮层提到这里，主按钮 `[data-board-primary]` 全页唯一；触发打印预览 / 下载 HTML 后主按钮翻成「✓ 记录纸面」（`BOARD_AWAITING_RECORD`），记录成功、重置纸面或改范围才复位。新增常驻检查器 `#bd-inspector`，三段 `[data-sec="item|layout|paper"]`；`boardSettingsPopHtml` / `boardPopOpen` / `boardPopClose` / `boardPopPlace` / `boardPopRefresh` / `BOARD_POP` 与 `.bd-pop*` 样式整套删除，旧检视条 `#bd-inspect` 一并移除。题后留白写入口收敛到检查器一个（`[data-board-inspect-gap]`），列表行与画廊卡改 `[data-board-gap-view]` 只读回显，点它 = 选中并把焦点送进检查器；新增 `boardRefreshLiveReadouts()` 让板级 `gap_lines` 一改，继承它的单题读数与两处回显一起刷新。舞台栏 `.bd-stagebar` 只留视图分段与内容操作，翻页条另占一行；缩放档状态化为 `BOARD_ZOOM`（此前初始态两个按钮都不高亮）。常驻预览在 `omrs-board-view` 里带 `embedded:true`，导出模板据此收起顶栏 `#bar`，舞台里不再出现第二套打印与记录入口。`.bd-layout` 改 `200px / 1fr / 268px` 三列，≤1180px 检查器折到底部通栏。顺手修掉一个既有缺陷：`boardEffectiveMode()` 原先不看新增数，「补印新增 → 记录纸面」之后模式仍是 `new` 而新增已归零，下一次导出会报「没有新增题目需要打印」；现在它直接返回 `boardStatusModel().scope`，与状态条同源。新增 tests/test_board_regions.js（17 项，v1.26.0 起迁为 `tests/app/board-regions.test.mjs`）守三条不变量与状态机五态。

## v1.17.0

> **v1.17.0 展示板文件夹与统一选板浮层**：八处「加入展示板」入口统一走 `boardPickerOpen(uids, {anchor, exclude, moveFrom, direct, onDone})`——锚定触发元素下方弹浮层、单击板行即加入、无「确定」按钮；`boardQuickAdd` / `boardChooseAndAdd` 保留为薄封装。键盘两键直达（`Enter` 进上次的板，默认高亮跳过「全部已在板中」行）；`Shift`+点击跳过浮层直加；`⌘` 点已加行撤回本次加的题；搜不到时底部变「＋ 新建并加入」。`boards.json` 升 v2：新增单层 `folders`，板新增 `folder_id` / `order`，v1 文件读时自动迁移、悬空 `folder_id` 静默归未归档；左栏板列表改「文件夹 → 板」两级树（折叠、拖拽归类、文件夹排序）。`/api/boards` 响应从 `{boards}` 变 `{boards, folders}`，每板多返回 `uids`；新增 `/api/board/folder/{create,update,delete}` 与 `/api/board/move` 4 条路由。折叠状态存 localStorage 不进 `boards.json`；删除文件夹默认保板可改连删。toast 调整：「换个板…」只保留在 `Shift` 直加路径。

## v1.16.1

> **v1.16.1 练习记录改读 Ledger + 文档整理**：`GET /api/question` 新增 `records[]`（`stats.get_question_records()`，由 Ledger 投影 `history_log.csv` 派生，按 `Question_ID` 优先、`UID` 兜底匹配）；前端 `core.js::qRecordsFromDetail()` 统一取记录，画廊战绩带（`galleryStreakBodyHtml`）与题目详情记录模块（`qvRecordHtml`）都改读它，Markdown `# 历史` 降为老后端兜底，空记录只显示「还没练过。」。反馈提交 / 历史修正后 `qvInvalidateMany()` 清 `QUESTION_CACHE`。设置页「外观」文案改为「首次打开默认深色」。全站 35 处原生 `alert / prompt / confirm` 换成 `uiToast / uiPrompt / uiConfirm`（涉及 app / export / feedback / history / inbox / instant / questions / recommend / recommend_v2 / reports / schedule），长确认改成标题 + hint + 动词按钮；13 个 JS 的 `?v=` 统一刷成 `20260906-v1161`。文档：`frontend.md` 顶部 16 段版本引用搬到本文件并按版本倒序，正文里 3 段「原来 / 现在」叙述改写成当前状态；章节重新编号（设置页 §7、历史页 §8、录入页 §9、收件箱 §9.1、数据页 §10、报告页 §11、主题 §12）；§5.1.1 答题卡导入拆成 `omr-import.md`；`optimization.md` 测试清单改成按主题分组的列表；新增 `tests/check_docs.py` 文档形式体检，三条写法规则与体检门槛写进根 `AGENTS.md` 与 `AI/README.md`。

## 未标版本

> **设置页源码协助**：服务设置新增「下载脱敏源码」按钮，调用 `GET /api/source/export` 下载仅含 Git 已跟踪源码、测试和项目文档的 ZIP；不读取未跟踪文件，并排除个人题库、附件、运行数据、日志和生成导出文件。包内 `SOURCE_EXPORT_MANIFEST.txt` 记录导出范围。

## v1.16.0

> **v1.16.0 题库练习记录：战绩带 + 记录模块**：把「练了几次、对错、分数」做进题库，但按**三层披露**分配，同一份数据只出现在一个层级。① **第一层（画廊卡脚注）**：原来的「N 次」升级成**战绩带**——一根竖条一次练习，绿对红错，高度是主观分（0–10 映射到 3–12px），左→右是时间，更早的几次 `opacity:.45` 淡出；连错 ≥2 时才在带子后补一句「连错 N」，顺利的题不加字。开关在「列 / 密度」菜单的画廊段（`QB_STREAK`，`localStorage('omrs-qb-streak')`，**默认开**，缺省值即开），关掉即回到 v1.15.0 的纯「N 次」，见「画廊式（Gallery View）」与 §3.2。② **第二层（题目详情最下面）**：`qvHtml()` 里原先塞在右栏 `.qv-a` 的 `<details class="qv-hist">` + `<pre>` 原文**整块下线**，改为通栏 `<section class="qv-rec">`，排在 `.qv-q` / `.qv-a` 之后（`.qv-split>.qv-rec{grid-column:1/-1}`）：四个派生数（练习次数 / 正确率 / 平均主观分 / 平均间隔）+ 主观分走势 sparkline（对错用点的颜色叠在同一张图上，不为对错单画第二张）+ 明细行，首屏 3 条、其余进 `<details>`，见 §2.2。③ **第三层不做**：全库聚合仍只在数据复盘页，题库页不重复。**当前实现存在数据源错配**（→ v1.16.1 已修，见上）：`DATA.items[].attempts` 来自 Ledger 重建的 `history_log.csv` 兼容投影，但 `GET /api/question` 的 `history` 仍是题目 Markdown 遗留 `# 历史` 原文；战绩带和记录模块只解析后者。因此正式反馈已记录、但题目文件没有旧历史行时，界面仍可能显示「还没练过」或空记录。Markdown 历史不再由反馈流程写入，也不是正式记录来源；修复记录模块前不应据此判断练习次数。前端正则与后端解析格式相近但并非字面完全一致：前端要求整行匹配并把分数钳到 0–10，后端使用 `re.match` 且未锚定行尾。**表格视图不加战绩带**：表格不拉题目详情，加了会让一屏几十行各发一次 `/api/question`，故 `attempts`（次数）列保持原样。版本号提到 **v1.16.0**（`omrs/version.py` + HTML 侧栏 + 根 `README.md`）。

## v1.15.0

> **v1.15.0 UI 改版：密度层 + 首页重构 + 整屏工作台**：分三块。① **密度层**：`styles.css` 的 `:root` 新增 `--pad / --pad-sm / --gap / --row / --ctl / --fs / --fs-sm / --fs-xs` 一组间距变量，舒适档取值即改版前原值；`html[data-density="compact"]` 额外覆盖 `--radius / -sm / -lg`，因此所有引用这三个圆角变量的既有规则自动跟随，无需逐条改。`.card` / `.stat-card` / `.cols` / `.card-title` / `.btn` / `.btn.sm` / `.input` / `thead th` / `tbody td` / `.content` / `.topbar` / `.sched-item` 等 15 处写死 px 换成变量。注意 `.input` 用 `padding:var(--ctl) 12px` 而非固定高度——录入页的 Markdown 编辑器是 `textarea.input`，设死高度会坏。开关在设置页「外观」（`setDensity()`，`localStorage('omrs-density')`，默认 `compact`），`<head>` 内联脚本与 theme / invert-img / sidebar 同批应用防闪。② **首页重构**：顺序改为「今天 → 行动推荐 → 概览条 → 近 30 天活动 + 最薄弱科目 → 最近动态」，见 §1。③ **整屏工作台**：`switchTab()` 给 `.content` 加 `.is-workbench`（题库 / 反馈录入 / 录入题目 / 展示板 / 即时练习五页），高度自 `.content` 一路 flex 分下去，取代原先 `calc(100vh - 魔数)` 的写法，见 §1.2。

## v1.14.1

> **v1.14.1 题库画廊卡精简**：画廊卡从「8 条等权横带」改为「标识 / 题面 / 脚注」三层，题面成为唯一主角。① 去重：UID 按 `category` 前缀拆成「分类 + 序号」，`knowledge_tags` 过滤掉与 `category` 同名的一条，同一字符串不再一卡三现；② 去卡中卡：`.gallery-preview` 移除 `background` / `border` / `min-height:140px`，画廊内 `.qv-label`（「题目」二字）隐藏，`.qv .q-md` 强制透明无边框；③ 只报异常：`statusTagHtml` 不再逐卡渲染全库同值的「待攻克」，改为 `galleryFlagsHtml()` 仅在逾期 / 今日到期 / 顽固 / 停用时亮标；熟练度为 0 时显示「未练习」而不画空进度条；④ 悬停收纳：复选框、「⋯」菜单、「＋标记」入口 hover / 选中才显形（`@media (hover:none)` 下常显），底部「查看详情」按钮删除——整卡（含题面）点击即开 Modal，`questions.js` 行点击选择器移除 `.gallery-preview` 排除项；⑤ 网格 `minmax(320px)→minmax(260px)`、`gap 16→12`、卡片 `padding 16→12/14`，`.question-gallery-wrap` 限宽 1440px；⑥ 截断改渐隐：`hydrateQuestionGalleryPreviews()` 渲染后量 `scrollHeight` 差值，真被截的卡才加 `.is-clipped`（`mask-image` 底部渐隐），短题不糊。元数据（科目 / 上次复习 / 衰减后 / 知识点）收进「列 / 密度」菜单的**画廊 → 显示元数据**开关（`QB_GALLERY_DETAIL`，`localStorage('omrs-qb-gallery-detail')`，**默认关 = 精简**）。同时 `qbRenderChips()` 在无激活条件时输出空串，配合 `.qb-chips:empty{display:none}` 收起常驻的「未设置筛选条件」提示行。表格视图、`getFilterState('q')`、`renderQ` / `filterQ` / `setQView` 签名与全部接口不变。

## v1.14.0

> **v1.14.0 展示板 + 用户标记 + 题库交互重设计**：题库新增筛选抽屉、激活条件 chips、列/密度设置、视图预设、批量操作和键盘导航；用户标记以 `<=>` 芯片显示，名称写入题目 YAML，支持单题/批量编辑、改名、删除、合并、按标记筛选与可选调度加成；展示板保存题目引用，支持排序、左题右空打印、「仅打印新增」+ 纸面记录与绝对页码。页面与导出统一采用 18% 淡底 + 彩色字标记样式。

## v1.11.0

> **v1.11.0 答题卡扫描回填 + 画廊预览修复**：反馈录入页接上答题卡扫描项目（OMR）的正式 `/api/v1/recognitions/{id}/result` 结果 JSON——扫完卡在识别详情页点「复制结果 JSON」，回本页点「📋 读剪贴板填写」或直接 `⌘`/`Ctrl`+`V`，按题号自动填对错与主观分，见 §5.1.1。OMR 导入只接受顶层 `recognition_id/template_id/mode/status/questions/unresolved`，明确拒绝旧 raw/items、裸数组和包装层。全部在前端完成，`/api/feedback` 零改动。同时修掉画廊缩略预览顶部凭空多出约 220px 空白的问题：`.gallery-preview` 上给旧版纯文本预览留的 `white-space:pre-wrap`，把 v1.10.0 起装进去的 qview 结构化 HTML 里标签之间的换行也渲染成了空行，见 §2.2 末尾。版本号提到 **v1.11.0**（`omrs/version.py` + HTML 侧栏 + 根 `README.md`）。

## v1.10.0

> **v1.10.0 共享题目视图（qview）+ 反馈工作台**：新增 assets/qview.js（P5 起迁为 `assets/app/domain/question/`），把原来分散在 `viewQ()`、画廊卡 `.gallery-preview` 和 `instRender()` 的三份题目渲染副本收敛成一个组件，见 §2.2。基于它做了两件用户可见的事：① 题目 Modal 改双栏（题面 | 答案+备注+历史）、加宽到 1180px、支持 `←/→` 在当前列表上下文内翻页；② 反馈录入页从「一列表单」改成三栏工作台（题目列表 / 题目视图 / 判定面板），录反馈时能直接看题和就地编辑，见 §5.1。即时练习的题面/答案块也换成 qview。版本号提到 **v1.10.0**（`omrs/version.py` + HTML 侧栏）。

## v1.9.0

> **v1.9.0 题目停用机制**：题目库支持停用/恢复。停用题目保留 Markdown、题目库管理入口和 Ledger 历史，但不参与复习调度、行动推荐、统计、数据分析、反馈和复习导出；题目库筛选提供活动/仅停用/全部三种口径，仪表盘显示停用数。

## v1.8.2

> **v1.8.2 部分判定提交 + 吸顶概览**：反馈页不再要求本批所有题都先判定；点击「提交反馈」时只提交已经选择「对 / 错」的题，未判定题自动保留到下一批。`fb-tally` 以吸顶“灵动岛”样式显示总数、对/错/未判和进度条，滚动题目时持续可见；每道反馈题增加序号徽标，选择已部分录入的 Session 时仍显示该题在 Session 原始题目列表中的序号，不会因过滤已录入题而从 1 重新编号。HTML 的 `styles.css`、`schedule.js`、`feedback.js` 资源查询参数同步更新，避免浏览器缓存旧交互。

## v1.8.1

> **v1.8.1 分批反馈交互优化**：`GET /api/sessions` 与 `GET /api/session` 的每个 Session 现在附带 `feedback_uids`、`pending_uids`、`feedback_count`、`pending_count`、`feedback_complete`，按 Session 原始题目顺序去重。反馈页选择 Session 时调用 `fbRowsForSession()` 自动只载入 `pending_uids`，已录入题目不再进入编辑行；顶部显示 `已录入 / 总数` 与剩余题数，Session 列表按钮改为「继续录入」。一次提交成功后保留当前 Session，刷新数据并自动载入剩余题目；全部完成时显示无需重复提交。反馈 JSON 导入同样自动跳过该 Session 已录入 UID，并在状态栏报告跳过数量；手动反馈仍可通过「添加行」使用。

## v1.7.0

> **v1.7.0 行动推荐 + 目录页 + 深色对比度修订**：① 仪表盘顶部新增「行动推荐」卡（`#action-plan`，在「最近动态」上方），脚本 assets/actions.js（v1.25.0 删除，规则迁到 features/dashboard/plan.js），见 §1.1；② 侧栏在「题目库」和「复习调度」之间新增「目录」页（`#panel-catalog`，图标 `#i-tree`），脚本 assets/catalog.js（v1.25.6 删除），数据来自新接口 `GET /api/tree`，见 §2.1；③ `styles.css` 的 `[data-theme="dark"]` token 与若干写死浅色的规则按对比度重配，见 §12。版本号提到 **v1.7.0**（`omrs/version.py` + HTML 侧栏 `v1.7.0 · 本地服务`）。

## v1.5.0

> **v1.5.0 深色主题：暖石墨 Warm Graphite**：早期 v1.5.0 的「玻璃拟态」深色（半透明卡片 + `backdrop-filter` 模糊 + body 四道极光径向渐变 + 紫青 `--grad`/`--glow` 辉光 + 渐变裁切文字）整段下线，改为与浅色同源的「暖石墨」——浅色用近黑墨、深色用骨白墨，互为镜像。`[data-theme="dark"]` token 改为实色暖面（`--bg:#1a1916` 等暖中性梯度）、发丝描边、单色骨白墨：`--accent` 由紫 `#b794f6` 改骨白 `#ece7df`、`--accent-fg` 深墨，故 `.btn.primary` 成「浅底深字」与浅色「深底白字」镜像；语义色由霓虹 400 收成大地色（黏土红 / 鼠尾草绿 / 赭黄 / 灰灰蓝）。删除 `--grad`/`--glow` 与 body 极光、玻璃卡片 / 玻璃侧栏 / 渐变按钮 / 紫色激活态 / 渐变 `.stat-value` 等深色特例，卡片 / 数值 / 进度条 / 品牌块 / 激活态全部回退到 token 驱动（深色覆盖块由约 53 行瘦到 ~16 行）。图表内联色仍走 `var()`，自动跟随。版本号不变（仍 v1.5.0）。

## v1.4.2

> **v1.4.2 页面内部现代化（首批两页）**：即时练习 `instRender` 题头改「题 N/M + chip + 进度条」、`instRenderSide` 队列项右侧改状态圆点（对/错/当前/未答）；反馈录入 `renderFb` 改卡片行（对/错分段 + 分数滑杆 + 备注 + 按 UID 反查科目分类）并在顶部加实时对错统计条。字段与 `/api/feedback`、`/api/recommend` 接口不变。**侧边栏应用式 shell 为下一独立改动**。

## v1.4.0

> **v1.4.0 应用骨架（侧边栏 shell）**：顶部 `<header>` + `.tabs` 横条 → 左侧 `<aside class="sidebar">`（`.sidebar-brand` 品牌 + `.sidebar-nav`）+ `<main class="content">`（`.topbar` 页面标题 + 动作按钮）。导航项**仍是 `.tab[data-tab]` + `onclick="switchTab()"`**，`switchTab` 逻辑不变，只新增：按 `name→中文` 映射更新 `#topbar-title`。图标为 `<body>` 顶部一段隐藏 `<svg><symbol id="i-*">` 雪碧图，导航用 `<svg class="nav-ico"><use href="#i-*"/></svg>`（描边走 `currentColor`，无外部图标依赖）。`modal-overlay` 与 `datalist` 仍是 `.shell` 外的兄弟节点。响应式：≤860px 侧栏转为顶部横向滚动条。

## v1.3.0

> **v1.3.0 深色模式 + 现代化**：首次打开且本地没有主题设置时，`<head>` 启动脚本当前选择**深色**；之后由设置页「外观」切换并存 `localStorage('omrs-theme')`。内联脚本在首帧前给 `<html>` 打 `data-theme` / `data-invert-img` 防闪。`:root` 圆角加大（`--radius:14 / -sm:10 / -lg:20`）、恢复柔和阴影 `--card-shadow`、新增 `--accent-rgb`；`[data-theme="dark"]` 为完整深色 token。`dashboard.js`/`data.js` 图表颜色已**全部 token 化**（含 SVG fill/gradient 改 `var()`+opacity），深色可正确显示。深色 + 「反转题图」开启时，`.q-md / .q-body / .gallery-preview / .instant-md / .instant-notes` 内 `img` 套 `filter:invert(1)`（简易白↔黑，彩色一并反相，保色版待后续）。

## v1.2.0

> **v1.2.0 视觉刷新（精修暖色）**：`styles.css` 的 `:root` 收敛为「编辑式暖色」——卡片去阴影/去 stat-card 顶部彩条、发丝级分隔线。图表条 `.bar-fill.*`/`.chart-fill.*` 以 `rgba(var(--accent-rgb),…)` 淡入主色的渐变填充（见 L500–505 的 `linear-gradient` 段，后者覆盖早期纯色定义）。新增语义族变量 `--fam-review`（复习/绿）、`--fam-session`（Session/蓝）、`--fam-question`（题目/棕）、`--fam-system`（系统/灰），用于时间线圆点、commit 类型标签和仪表盘「最近动态」圆点。`:root` 下方保留一段注释版「夜间账本」深色 token，整段替换即切深色；但仪表盘雷达/热力/趋势图与散点仍有内联浅色需先改用 `var()` 才能正确切到深色。图表内联色尽量走 `var()`（散点已改）。

## 早期版本摘要（自根 README 版本表迁入）

- **v1.13.0**：收件箱：框选提供方（多模态模型 / 版式模板零联网 / 本地检测服务 `local_http`）、盲标评估集、置信度自动就绪与上传即自动处理、超期丢弃图与裁图缓存清理、大裁图改 JPEG、拒绝计数增量化
- **v1.12.0**：收件箱录入流程：上传 → 处理（框选 / 转文本 / 留图）→ 录入；手机上传页；AI 框选与可转性判断走后台 job；训练数据集统计与导出
- **v1.8.0**：跨行块级 LaTeX 在题目页/A4/屏幕版完整渲染；设置页重启交给 systemd，避免服务停机
- **v1.6.0**：单题删除（Ledger 归档）与可配置 Ledger 时间线时区；汇总 v1.5.0 后的导出、AI 录入、仪表盘和报告托管改进
- **v1.1.1**：历史修正体验修复（撤销/恢复真正生效）；历史页只读浏览需显式开启修正模式；时间线改为题目优先
- **v1.1.0**：数据格式大变动：改用链式存储（Ledger），数据可回溯可复原，一切操作记录在链上
- **v1.0.x**：初版
