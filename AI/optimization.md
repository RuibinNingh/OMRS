# 优化空间 / 技术债清单

> **速查**
> - 职责：技术债、风险边界与已完成优化
> - 入口：—（跨模块清单）
> - 不变量：已知缺陷只在这里记一条 `[ ]`，其他文档最多一句话指过来
> - 必跑测试：—
> - 相关：`AGENTS.md`「文档写法」

> 初次整体代码与架构走查完成于 2026-06-15，2026-07-24 又按 Git 历史与当前工作区校正文档状态。覆盖：架构文档、后端请求/数据层（`server.py`、`cli.py`、`projections.py`、`ledger.py`、`ai_assist.py`）、前端 JS/CSS 的模式层面。**未**逐行审计算法模块（`optimization.py` / `scheduling.py` / `analytics.py`），故不含算法正确性结论。
>
> 标注:影响 / 工作量 / 状态。勾掉时把 `[ ]` 改成 `[x]`。

---

## 展示板完整性保障

- [x] **导出归属固定。** 导出在请求前捕获板 ID、名称与模式；独立窗口只回写自己的导出任务。前后端均核验版面归属、模式、题目身份和页码范围；旧窗口、未知/别板题目、无纸面续印和越界布局不能写入纸面。
- [x] **保存串行且保留新编辑。** 保存队列（`assets/app/features/board/save.js`）协调在途请求；响应合并时保留发送后产生的脏字段并继续保存。切板、导出、重载等待队列，保存失败时保留编辑并中止依赖动作。
- [x] **撤销只移除实际新增引用。** 加题接口返回 `added_uids`；普通 toast、Shift 快捷加入和连续选板的撤销使用该清单。「换个板」只处理本次新增引用，并在加入目标成功后移除来源引用。
- [x] **内容设置重新导出。** 答案与标记开关进入内容指纹，保存后更新导出内容；纯几何调整仍用实时 relayout。
- [x] **立即打印等待保存。** 打印窗口先同步打开，再等待去抖和在途保存完成；保存失败不生成旧版式的导出。
- [x] **纸面记录绑定导出快照。** 每板保存待记录任务，使用独立窗口的实测 layout，或以已下载的同份 HTML 测量；当前预览的后续编辑不替换快照。正文指纹从导出数据传回，旧导出件缺字段时保留兼容回退。
- [x] **预览消息隔离。** 每份 srcdoc 带独立 `previewToken`，与板 ID、模式、来源窗口一起核验；旧响应或旧消息不能使新文档提前就绪。内嵌 HTML 从加载开始收起独立打印工具栏。

保障范围由 `tests/test_board_integrity.py`、`tests/app/board-preview.test.mjs`、`tests/app/board-locked.test.mjs`、smoke_board_integrity.py（已删除：调用的旧全局 P7 起已不存在；覆盖由新版展示板 E2E 承接） 和既有展示板测试覆盖。排查与修复记录见本机任务日志（2026-09-22 的 board-functional-audit 与 board-integrity-fixes）。

## 最值得动的

- [x] **服务重启时 TCP 端口短暂占用** — `omrs/cli.py::OMRSTCPServer` 启用 `SO_REUSEADDR`（不启用 `SO_REUSEPORT`、不改线程模型与 systemd 重试策略），旧连接处于 `TIME-WAIT` 时可立即重绑。设置页改为比较重启前后 `instance_id`，确认新实例就绪才刷新，90 秒无结果则停在页面提示。回归：`tests/test_restart_lifecycle.py`、`tests/app/settings.test.mjs`、`tests/e2e/settings.py`。

- [ ] **`AI/api.md` 超过 40KB** — 影响:低 / 工作量:小。`check_docs.py` 对它给出拆分提醒。可按领域拆成 `AI/api/` 分册（题目与调度、反馈与历史、展示板与导出、系统与认证），路由到文档的定位由 `AI/routes.md` 自动更新。

- [ ] **服务器单线程,AI 识别时整界面卡死** — 影响:高 / 工作量:中
  `cli.py` 用 `socketserver.TCPServer`(非 Threading),一次只处理一个请求。而 `ai-recognize` 同步调外部大模型(`ai_assist.py`,带 timeout,可能十几秒),期间任何请求都被阻塞;局域网多设备也排队。
  改法:换 `ThreadingHTTPServer` / `ThreadingTCPServer` + `daemon_threads=True`。**v1.12.0 部分缓解**：收件箱的 detect / extract / classify 已改成后台线程 job + 轮询（`omrs/inbox.py`），批量识别不再卡界面；旧 `/api/ai-recognize` 仍同步。**代价**:并发后文件型数据层(CSV / Markdown / ledger)写入需加锁——给改动型端点 + `append_commit` / `rebuild_projection` 套一把全局 `threading.Lock`。

- [ ] **投影是全量重放整条 ledger** — 影响:中(随时间恶化)/ 工作量:中高
  `projections.py` 的 `rebuild_projection` / `_project_state` 都 `read_commits(ascending=True)` 后从头 `for commit in commits` 算到尾。提交链只增,成本随历史线性增长——题做多了(几千 commit)每次重建肉眼变慢。
  改法:定期落投影快照(snapshot at seq N),之后只重放增量。`ledger_history` 已分页,这点很好。

## 可维护性(「臃肿 / 草率」的根)

- [x] **前端 JS 杂烩文件已按职责拆分(v1.5.0 完成)**
  原 `schedule.js`(约 100 行)混了导出 / Session / 反馈页 / 录入提交 / 历史时间线 / 扫描六件事。已拆出 `export.js`、`feedback.js`、`history.js`,`schedule.js` 仅留 Session + 扫描 + 录入提交。因共享全局作用域,拆分零行为改动(函数名/签名/调用全不变,72 个函数原样,`node --check` 通过)。 P6 起导出与复习调度迁到 `assets/app/features/schedule/`，`export.js` 已删。
  **后续**:`app.js`(26KB,含录入页图片/AI 逻辑 + init)也偏大,可在需要时再拆(旧 `recommend.js` 已确认为死代码并删除,两个仍在用的入口并入 `schedule.js`);前端整体可考虑迁移原生 ES Module(浏览器免构建),但**前提是先把行内 `onclick` 换成 `addEventListener`**(模块作用域下行内 handler 失效)。

- [ ] **CSS 一层层叠,有真实重复定义** — 影响:中 / 工作量:中 / 风险:低
  **进行中(前端重构 P0)**:token 已集中到 `assets/app/styles/tokens.css`(旧名保留为别名),`tests/check_ui.py` 对旧代码的颜色字面量、硬编码字号等按文件计数只减不增,`tests/visual/run.py` 提供前后截图对比。重复定义随各页迁入 `assets/app/` 时整段删除,不再单独清理;规范见 `AI/frontend/design-system.md`。
  `styles.css` 里 `.form-group`、`.fb-toggle` 等被定义两遍(历次「现代化」往后追加却没删旧的)。注意约 30 个「重复」里不少是合理的响应式 / 深色 `@media` 覆盖,不算债;上面这几个是真叠加债。建议按组件集中收拢(配合截图回归)。即时练习页已清理了一批孤立规则,重复的 `.shell` 也已删除(全宽改造时)；2026-08-13 已收拢 `.instant-queue` 的重复定义(删除 v1.4.2 遗留的 55vh 段,保留 v1.5.0 的 62vh 段)。
  另有一类相关但不同的债在 v1.7.0 清掉:**规则里写死浅色时代的颜色**(`.q-answer .q-md` 的深绿底、时间线 `.fam-review/.fam-session` 标签、`.heat-*` 的白字与 7% 空档、柱状渐变的低位停点、`.btn.danger:hover` 的白字)。这些不是重复定义,而是 token 切深色后它们不跟着走,表现为「深色下看不清」。已统一改为 `var(--*)` / `rgba(var(--*-rgb), α)` 并集中在文件末尾的深色修订段。**新增规则不要再写裸十六进制或裸 `rgba(r,g,b,a)`。**

- [x] **qview 的「窄了就单栏」容器查询永远不生效（P5 已修）** — 影响:中(手机上题目弹窗、反馈工作台的题面仍是挤在一起的双栏) / 工作量:小。`styles.css` 把 `container-type` 设在 `.qv` 自身，而 `@container qv (max-width:680px)` 要改的正是 `.qv-split` 这个容器本身；容器查询只作用于后代，所以从不命中。现改为以挂载点为容器（`assets/app/domain/question/qview.css`），即时练习与反馈录入的页面补丁已删除，题目弹窗在窄屏单栏。

- [ ] **`tests/smoke_schedule_workbench.py` 在导出基线上即失败** — 影响:低(测试本身) / 工作量:小
  2026-09-24 受限模式实测:基线提交与当前工作区都在第 138 行失败,筛选「到期=今天」后期望 14 题、实得 0。原因待确认(疑与运行时刻或时区有关)。2026-09-25 P4 复测:第 138 行已通过(印证与运行时刻有关);随后卡在导出打印版的 `[data-ui-ok]`——P2 后对话框按钮是 `data-dialog-ok` / `data-dialog-cancel`,测试选择器已更正,反馈部分(部分录入、连续 9 批提交、完成态)现已实际跑通;现在停在「空推荐时提示查看已有计划」(基线同样失败,属复习调度页,待查)。另:旧经典脚本 assets/board.js 的 `focus: '[data-ui-ok]'` 同样过时。运行方式:`PYTHONPATH=. python3 tests/smoke_schedule_workbench.py`(不设 `PYTHONPATH` 会因找不到 `omrs` 包而无法启动)。

- [ ] **后端路由是超长 if/elif** — 影响:中 / 工作量:中
  `server.py` 的 `do_GET`(~150 行)/ `do_POST`(~280 行)是手写分支链,`json.loads(body)` 重复十几次。可收成 `{(method, path): handler}` 派发表 + 统一 body 解析。纯整理,降认知负担。

- [ ] **前端整块 innerHTML 重渲染 + 行内 onclick** — 影响:中 / 工作量:高
  存量由 `tests/check_ui.py` 的棘轮基线 UI 基线文件 跟踪(只减不增);新代码在 `assets/app/` 下零容忍。
  项目仍广泛使用 `innerHTML=` 和模板内 `onclick=`；具体数量会随功能变化，不在此硬编码。它们会导致高频交互重建整块 DOM、标记与逻辑混在字符串中，并阻碍 ES Module 化。务实改法：先把队列、反馈行等高频区域改为局部更新和事件委托。
  **v1.10.0 已完成反馈页部分**：`renderFb()` 拆成 `fbRenderRail` / `fbRenderPanel` / `fbRenderStage`，点「对 / 错」只就地改一行 class（`fbPatchRailRow`）并重绘判定面板，题目 DOM 与 KaTeX 不再整块重建，滑杆焦点与滚动位置不丢；rail 与判定面板的控件改走 `data-fb-go` / `data-fb-act` 事件委托，qview 的工具按钮走 `data-qv-act` 委托。**仍未处理**：题目库表格与画廊、导出选题器、推荐面板、历史时间线、数据复盘表格等仍是整块 `innerHTML` + 行内 `onclick`；（即时练习、反馈录入已随前端重构 P3 / P4 迁到 `assets/app/features/instant/`、`assets/app/features/feedback/`，改用 morph 差量更新，上述 `fbRender*` / `data-fb-*` 随旧 `feedback.js` 一并删除。）
  **v1.14.0 新增的 `qtable.js` / `board.js` 也保留了整块渲染**：两者都已迁走（题库 P5、展示板 P7），新页面用 `morph` 差量更新。

- [x] **旧经典脚本 assets/board.js 承载多种职责（P7 完成拆分并删除）** — 影响:中 / 工作量:中 / 风险:中
  原文件包含板 CRUD、文件夹操作、条目增删排序、版面设置、保存队列、打印与纸面记录、拖拽、预览协调和事件委托。
  前端重构 P7 分六轮拆完：纯函数在 `assets/app/features/board/model.js` 与 `assets/app/domain/board/model.js`；保存队列、打印协调、
  常驻预览、版面设置、拖拽排序在同目录的 `save.js`、`print.js`、`preview.js`、`settings.js`、`drag.js`；选板浮层与板列表在
  `assets/app/domain/board/`；板详情在 `detail.js`（真实 I/O 与单例在 `runtime.js`）；页面在 `index.js` / `view.js` / `state.js`，
  「添加题目」在 `add.js`。旧调用方与冒烟测试要用的全局经过渡桥 `installBoardBridge` 挂回，P8 清空。

- [x] **展示板预览的内容签名不覆盖题目正文** — 已按「自动 + 人工兜底」两条一起解决
  `boardContentSignature()` 只算题目集合、顺序、停用 / 缺失状态，加上纸面记录时间。
  自动一侧：题目 Modal 保存与反馈提交都会走 `reloadData()` → `boardReloadData()` →
  `boardPreviewInvalidate()`，预览下一次同步就重新导出（已实测确认）。
  人工一侧：检视条上的「↻ 重新生成」（`boardRegenPreview()`）用于应用外改文件这类
  没有重载信号的情况。仍未覆盖的是「别的标签页改了同一份数据」，那需要服务端推送才谈得上。

- [x] **展示板纸面历史选了「追加 jsonl」而不是进 Ledger** — 决策记录
  展示板是呈现层数据，进 Ledger 会把打印这种「呈现动作」混进复习事实链，
  也会让每次打印都产生不可回收的提交。因此 `record_printed` / `reset_printed` 只把
  **被替换掉**的那份纸面追加进 `错题/.omrs/boards_printed_history.jsonl`（只增不改），
  写失败仅记运行日志、绝不打断打印记录本身。代价：这份历史不参与校验、没有回滚能力，
  且**目前没有 UI 也没有 HTTP 端点**读它。文件只增不删，长期需要一个轮转或归档策略。

- [ ] **预览 HTML 缓存只留最近一份** — 影响:低 / 工作量:小
  `BP_HTML_CACHE` 是一个只装一条的 `Map`：导出 HTML 内联 KaTeX 字体后接近 1MB，
  攒几份很快就是几十 MB。代价是「A 板 → B 板 → A 板」这种来回切要重新拉两次导出。
  几何改动走 relayout 已经消化掉绝大多数刷新，所以暂时不做 LRU；真要做的话
  上限按条数而不是按字节，避免为了算字节把整份 HTML 再遍历一遍。

- [ ] **标记批量级联写入可能阻塞单线程服务** — 影响:中 / 工作量:中
  标记名称存进题目 YAML，因此 `labels.py` 的改名、删除（解除引用）和合并会逐题
  原子写 Markdown，并为结构化元数据产生提交，最后统一扫描投影。几十题通常可接受，
  但数百题会在当前单线程 HTTP 服务中占住请求；未来可将批量操作改成后台 job 或
  在统一写锁下合并提交，同时保留失败题清单和幂等重试。

## 健壮性

- [ ] **AI 写入的 op_id 幂等未做** — 影响:低 / 工作量:小
  `ledger.db` 已有 `op_results` 表，但工具调用还没有按 `op_id` 记录结果；目前靠「一次运行一个线程、工具串行、写锁内执行」避免重复写入，浏览器重发 `/api/agent/confirm` 只会得到 409。需要跨进程重放时再补。
- [ ] **助手不能看题图** — 影响:中 / 工作量:中
  配置里预留了 `agent_vision`，但还没有把图片交给模型的工具；纯图片题只能靠分类筛选和用户描述。
- [ ] **`AI/api.md` 超过 40KB** — 影响:低 / 工作量:小
  按 GET / POST 或按模块拆成分册，参照 `AI/frontend/`。

- [ ] **测试覆盖仍偏低** — 影响:中高 / 工作量:中
  现有测试按主题分（全部在 `tests/`）：
  - Ledger / 历史：`test_history_projection.py`（撤销 / 恢复 / 替换）、`test_question_records.py`（`/api/question` 的 `records[]` 匹配与日期拆分，v1.16.1）
  - AI 与报告：`test_ai_assist_taxonomy.py`（分类约束、答案提示词）、`test_report_export.py`（报告材料与部分 HTML 导出契约，pytest 风格）
  - 目录树与行动推荐：`test_catalog_tree.py`、`tests/app/catalog.test.mjs`、`tests/e2e/catalog.py`、`tests/app/dashboard.test.mjs`
  - 反馈录入与答题卡导入：`tests/app/feedback.test.mjs`（P4 起；合并了原 `test_feedback_ui.js`、`test_omr_import.js`、`smoke_feedback_omr_import.js` 的全部断言）、`tests/e2e/feedback.py`（浏览器接线）
  - 标记与展示板：`test_labels.py`、`test_boards.py`、`test_board_export.py`、`tests/app/labels.test.mjs`、`tests/app/board.test.mjs`、`smoke_board_print.py`
  - 题库界面：`test_qtable_ui.js`、`tests/app/question.test.mjs`（渲染缓存、记录统计、战绩带、Ledger 记录优先于 Markdown 旧行、画廊卡骨架）、`test_question_suspend*.{py,js}`、`test_question_delete.py`、`test_recommend_v2_filters.js`
  - 其它：`test_inbox.py`（14 例）、`test_sessions_feedback.py`、`test_recommendations.py`、`test_source_export.py`
  - 文档形式体检：`check_docs.py`（不是测试用例，交付前跑一次）
  核心缺口仍是 `compute_mastery_update` / `compute_priority` / SM-2 的边界、Ledger append→projection 集成、CSV/Markdown 异常输入和浏览器端 A4/屏幕/展示板真实打印回归。
  **当前测试数量与运行方式**：`tests/test_inbox.py` 有 14 个 `test_*` 方法；`test_report_export.py` 有 6 个 pytest 风格用例，其余 Python 测试文件使用 `unittest`。`python3 -m unittest discover -s tests -p "test_*.py"` 会运行 unittest 用例但静默跳过 `test_report_export.py`；无 pytest 的环境需单独安排。JS 用例逐文件跑：`for f in tests/test_*.js; do node --test "$f"; done`（`node --test tests/` 目录形式在 Node 22 下不可用）。

- [x] **展示板打印链路的三处浪费（2026-09-06 已修）** — 导出把 KaTeX 的 woff2/woff/ttf 三份字体全内联且每次重新读盘编码，浏览器模板固定排版两遍，长图在原始分辨率上逐像素找白缝。现在只内联 woff2 并按文件时间缓存（导出 2.0MB→0.95MB）、按是否真的多加载了字体决定第二遍（30 题板就绪 0.4s→0.28s）、白缝分析在 ≤600px 缩图上做。前端页数估算改成可取消，并复用打印预览窗口回传的版面。回归：`tests/test_board_export.py`、`tests/smoke_board_print.py`（3 例）、`tests/app/board.test.mjs`（原 test_board_ui.js）。
  当前预览使用单例 iframe 与最近一份 HTML 缓存；几何改动通过 120ms 去抖发送 `relayout`，页数直接读取预览版面，不再另外排版估算。

- [x] **`smoke_board_print.py` 失败（2026-09-06 已修）** — `test_full_then_incremental_print` 硬断言补印首页是占位页（`partial && ghost`），但夹具在某些字体下最后一页恰好排满，占位页按设计被丢弃，于是断言失败。现改为按 `cursor.y` 与栏高的关系分支断言，并新增两例：短板强制走占位页续排、宽长图走缩图切片。

- [x] **首次主题与页面提示不一致（v1.16.1 已修）** — 设置页「外观」帮助文案改为「首次打开默认深色（暖石墨）」，与 `<head>` 首帧脚本一致。

- [x] **题库练习记录的数据源错配（v1.16.1 已修）** — `GET /api/question` 新增 `records[]`（`stats.get_question_records()`，由 Ledger 投影 `history_log.csv` 派生，按 `Question_ID` 优先、`UID` 兜底匹配）；前端 `core.js::qRecordsFromDetail()` 统一取记录，画廊战绩带与详情记录模块都改读它，Markdown `# 历史` 降为老后端兜底。反馈提交 / 历史修正后 `qvInvalidateMany()` 清详情缓存。回归：`tests/test_question_records.py`、`tests/app/question.test.mjs`。
  **剩余小债**：`parseQHistory` / `parse_history_lines` 这套 Markdown 解析现在只为兼容老后端，等确认没有旧手工 `# 历史` 需要展示后可整体删除；`history_log.csv` 每次 `get_question_records()` 都全量读一遍（单题请求、文件小，暂可接受，量大时改查投影表）。

## 锦上添花

- [ ] `reloadData()` 每次改动全量刷新(~10 处调用):小数据无感,量大偏重,可改局部更新。
- [ ] **运行时外链 Google Fonts**:离线/弱网首屏阻塞 + 每次访问请求 Google。既然 KaTeX 已本地化,把字体也 vendoring 进 `assets/vendor/` 更彻底(离线 + 隐私 + 首屏)。工作量低。
- [x] **局域网模式访问控制。** 远端页面和 API 经 PIN 会话保护；本机及显式豁免网段直连免 PIN。配置与代理边界见 `AI/security.md`。

## 已经做得好的(不要动)

- `_serve_asset`(`server.py`)路径穿越防护扎实(`normpath` + 限定 `assets/` 内);assets 一律 `Cache-Control: no-cache`。
- ledger 不可变链 + 投影的设计有想法;`ledger_history` 分页合理。
- 核心运行时只依赖 Python 标准库；Pillow、jpegtran 只用于可选图片优化，不影响基础服务和导出。
- 根 `AGENTS.md` + `AI/README.md` 已把“每次持久化任务同步模块文档、任务日志和索引”设为完成条件。
