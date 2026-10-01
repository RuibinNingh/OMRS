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

## 训练面板服务管理

- [x] **离线启动命令未匹配实际配置（已修）。** 已登记服务显示固定systemctl命令，手动本机地址读取实际端口；远端地址提示在服务所在机器启动。/train提供受管服务操作与显式模型应用。

## 最值得动的

### MCP 修复

- [x] **科目概况统一范围。** 共享 `get_stats` 在原始行与稳定身份历史上限定科目，助手/MCP 的全部指标及摘要同范围；保留原始熟练度精度与投影停用状态。回归覆盖多科目、未知科目、空库、仅停用科目和真实协议，执行说明 F1。

- [ ] **草稿库首次并发迁移竞争。** 影响：中 / 工作量：小。`omrs/drafts.py:mcp_request` 的无锁连接会运行列检查与迁移，新临时库自然并发已出现 `duplicate column name`，完整 MCP 工具调用也返回内部错误。集中串行化初始化/迁移并维持既有锁顺序；执行说明 F2。

- [ ] **幂等复用遗漏处理中 Key 失效。** 影响：中 / 工作量：小。`omrs/mcp/server.py:create_draft` 的复用分支提前返回，跳过处理后的权限复查；真实草稿/Key 与图片校验期间吊销注入已复现 `reused=true`。覆盖快速复用、图片处理、等锁和到期窗口，不改变幂等身份；执行说明 F3。

- [ ] **工具发现未应用实时 scope。** 影响：中 / 工作量：小。只读/仅建草稿 Key 的真实 SDK 都发现全部十个工具，直接越权调用仍被拒绝。发现与调用共用固定能力映射，过滤请求级描述，不修改全局注册表；执行说明 F4。

- [x] **服务重启时 TCP 端口短暂占用** — `omrs/cli.py::OMRSTCPServer` 启用 `SO_REUSEADDR`（不启用 `SO_REUSEPORT`、不改线程模型与 systemd 重试策略），旧连接处于 `TIME-WAIT` 时可立即重绑。设置页改为比较重启前后 `instance_id`，确认新实例就绪才刷新，90 秒无结果则停在页面提示。回归：`tests/test_restart_lifecycle.py`、`tests/app/settings.test.mjs`、`tests/e2e/settings.py`。

- [ ] **`AI/api.md` 超过 40KB** — 影响:低 / 工作量:小。`check_docs.py` 对它给出拆分提醒。可按领域拆成 `AI/api/` 分册（题目与调度、反馈与历史、展示板与导出、系统与认证），路由到文档的定位由 `AI/routes.md` 自动更新。

- [x] **慢请求阻塞整个服务（已修）。** `omrs/cli.py::OMRSTCPServer` 使用 `ThreadingMixIn`，每连接一个守护线程；`/api/ai-recognize` 调外部模型时不占进程写锁，其他请求可继续处理。持久化写入由 `omrs/locking.py` 的可重入写锁串行，等锁超时返回 503；契约见 `AI/api.md`「并发与写锁」，回归见 `tests/test_write_lock.py`、`tests/test_ledger_concurrency.py`。

- [ ] **投影是全量重放整条 ledger** — 影响:中(随时间恶化)/ 工作量:中高
  `projections.py` 的 `rebuild_projection` / `_project_state` 都 `read_commits(ascending=True)` 后从头 `for commit in commits` 算到尾。提交链只增,成本随历史线性增长——题做多了(几千 commit)每次重建肉眼变慢。
  改法:定期落投影快照(snapshot at seq N),之后只重放增量。`ledger_history` 已分页,这点很好。

## 可维护性(「臃肿 / 草率」的根)

- [x] **旧全局 JS 按职责拆分。** P8 后入口为 `assets/app/main.js` / `shell.js`，各页面在 `features/` 下以原生 ES Module 挂载；旧 `app.js`、`schedule.js`、`feedback.js`、`board.js` 和过渡桥已删除，依赖方向由 `tests/check_ui.py` 约束。

- [x] **旧 CSS 叠加与存量违规（已清理）。** P8 删除旧样式文件，页面样式由 `assets/app/styles/index.css` 分层引入，颜色和尺度由 `tokens.css` 管理。`tests/check_ui.py` 对全仓行内事件、HTML 赋值、行内样式、颜色字面量和硬编码字号零容忍；规范见 `AI/frontend/design-system.md`。

- [x] **qview 的「窄了就单栏」容器查询永远不生效（P5 已修）** — 影响:中(手机上题目弹窗、反馈工作台的题面仍是挤在一起的双栏) / 工作量:小。`styles.css` 把 `container-type` 设在 `.qv` 自身，而 `@container qv (max-width:680px)` 要改的正是 `.qv-split` 这个容器本身；容器查询只作用于后代，所以从不命中。现改为以挂载点为容器（`assets/app/domain/question/qview.css`），即时练习与反馈录入的页面补丁已删除，题目弹窗在窄屏单栏。

- [ ] **`tests/smoke_schedule_workbench.py` 在导出基线上即失败** — 影响:低(测试本身) / 工作量:小
  2026-09-24 受限模式实测:基线提交与当前工作区都在第 138 行失败,筛选「到期=今天」后期望 14 题、实得 0。原因待确认(疑与运行时刻或时区有关)。2026-09-25 P4 复测:第 138 行已通过(印证与运行时刻有关);随后卡在导出打印版的 `[data-ui-ok]`——P2 后对话框按钮是 `data-dialog-ok` / `data-dialog-cancel`,测试选择器已更正,反馈部分(部分录入、连续 9 批提交、完成态)现已实际跑通;现在停在「空推荐时提示查看已有计划」(基线同样失败,属复习调度页,待查)。另:旧经典脚本 assets/board.js 的 `focus: '[data-ui-ok]'` 同样过时。运行方式:`PYTHONPATH=. python3 tests/smoke_schedule_workbench.py`(不设 `PYTHONPATH` 会因找不到 `omrs` 包而无法启动)。

- [ ] **后端路由是超长 if/elif** — 影响:中 / 工作量:中
  `server.py` 的 `do_GET`(~150 行)/ `do_POST`(~280 行)是手写分支链,`json.loads(body)` 重复十几次。可收成 `{(method, path): handler}` 派发表 + 统一 body 解析。纯整理,降认知负担。

- [x] **旧脚本的整块 HTML 赋值和行内事件（已清理）。** P8 后生产代码仅 `assets/app/core/dom.js` 可写 `innerHTML`，由 `render` 或 `morph` 更新 DOM；页面模板不含行内 `onclick`。`tests/check_ui.py` 当前五项计数均为 0。

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

- [ ] **标记批量级联写入可能长时间占用进程写锁** — 影响:中 / 工作量:中
  标记名称存进题目 YAML，因此 `labels.py` 的改名、删除（解除引用）和合并会逐题
  原子写 Markdown，并为结构化元数据产生提交，最后统一扫描投影。几十题通常可接受，
  但数百题会使其他持久化写入排队，等锁超过 60 秒返回 503；未来可将批量操作改成后台 job 或
  在统一写锁下合并提交，同时保留失败题清单和幂等重试。

## 健壮性

- [ ] **备份导出在内存里拼整个 zip** — 影响:中(随框选标注集增长恶化) / 工作量:小。`optimization.create_backup_export` 遍历整个 `错题/` 写 `BytesIO`，框选标注集（`错题/.omrs/annotate/images/`）大批量采集后可达数 GB。可仿照 `/api/annotate/export` 先写临时文件再分块发送。

- [ ] **AI 写入的 op_id 幂等未做** — 影响:低 / 工作量:小
  `ledger.db` 已有 `op_results` 表，但工具调用还没有按 `op_id` 记录结果；目前靠「一次运行一个线程、工具串行、写锁内执行」避免重复写入，浏览器重发 `/api/agent/confirm` 只会得到 409。需要跨进程重放时再补。
- [ ] **助手检索不了题库里的纯图片题** — 影响:中 / 工作量:中
  主 AI 能接收对话附图并使用 `describe_image` 追问；题库中已有的纯图片题仍只能按分类筛选或由用户描述来找。
- [ ] **`AI/api.md` 超过 40KB** — 影响:低 / 工作量:小
  按 GET / POST 或按模块拆成分册，参照 `AI/frontend/`。

- [ ] **测试覆盖仍偏低** — 影响:中高 / 工作量:中
  现有测试按主题分（全部在 `tests/`）：
  - Ledger / 历史：`test_history_projection.py`（撤销 / 恢复 / 替换）、`test_question_records.py`（`/api/question` 的 `records[]` 匹配与日期拆分，v1.16.1）
  - AI 与报告：`test_ai_assist_taxonomy.py`（分类约束、答案提示词）、`test_report_export.py`（报告材料与部分 HTML 导出契约，pytest 风格）
  - 目录树与行动推荐：`test_catalog_tree.py`、`tests/app/catalog.test.mjs`、`tests/e2e/catalog.py`、`tests/app/dashboard.test.mjs`
  - 反馈录入与答题卡导入：`tests/app/feedback.test.mjs`（P4 起；合并了原 `test_feedback_ui.js`、`test_omr_import.js`、`smoke_feedback_omr_import.js` 的全部断言）、`tests/e2e/feedback.py`（浏览器接线）
  - 标记与展示板：`test_labels.py`、`test_boards.py`、`test_board_export.py`、`tests/app/labels.test.mjs`、`tests/app/board.test.mjs`、`smoke_board_print.py`
  - 题库界面：`tests/app/questions.test.mjs`、`tests/app/question.test.mjs`（渲染缓存、记录统计、战绩带）、`test_question_suspend.py`、`test_question_delete.py`、`tests/e2e/questions.py`
  - 其它：`test_inbox.py`、`test_sessions_feedback.py`、`test_recommendations.py`、`test_source_export.py`
  - 文档形式体检：`check_docs.py`（不是测试用例，交付前跑一次）
  核心缺口仍是 `compute_mastery_update` / `compute_priority` / SM-2 的边界、Ledger append→projection 集成、CSV/Markdown 异常输入和浏览器端 A4/屏幕/展示板真实打印回归。
  **当前运行方式**：`python3 -m unittest discover -s tests -p 'test_*.py' -q` 运行 `unittest` 用例，但会静默跳过 `tests/test_report_export.py` 中的 pytest 风格函数；该文件需要单独用 pytest 跑。前端模块用 `node --test tests/app/*.test.mjs`，真实浏览器路径见 `tests/e2e/` 与 `tests/app/run_browser.py`。

- [x] **展示板打印链路的三处浪费（2026-09-06 已修）** — 导出把 KaTeX 的 woff2/woff/ttf 三份字体全内联且每次重新读盘编码，浏览器模板固定排版两遍，长图在原始分辨率上逐像素找白缝。现在只内联 woff2 并按文件时间缓存（导出 2.0MB→0.95MB）、按是否真的多加载了字体决定第二遍（30 题板就绪 0.4s→0.28s）、白缝分析在 ≤600px 缩图上做。前端页数估算改成可取消，并复用打印预览窗口回传的版面。回归：`tests/test_board_export.py`、`tests/smoke_board_print.py`（3 例）、`tests/app/board.test.mjs`（原 test_board_ui.js）。
  当前预览使用单例 iframe 与最近一份 HTML 缓存；几何改动通过 120ms 去抖发送 `relayout`，页数直接读取预览版面，不再另外排版估算。

- [x] **`smoke_board_print.py` 失败（2026-09-06 已修）** — `test_full_then_incremental_print` 硬断言补印首页是占位页（`partial && ghost`），但夹具在某些字体下最后一页恰好排满，占位页按设计被丢弃，于是断言失败。现改为按 `cursor.y` 与栏高的关系分支断言，并新增两例：短板强制走占位页续排、宽长图走缩图切片。

- [x] **首次主题与页面提示不一致（v1.16.1 已修）** — 设置页「外观」帮助文案改为「首次打开默认深色（暖石墨）」，与 `<head>` 首帧脚本一致。

- [x] **题库练习记录的数据源错配（v1.16.1 已修）** — `GET /api/question` 新增 `records[]`（`stats.get_question_records()`，由 Ledger 投影 `history_log.csv` 派生，按 `Question_ID` 优先、`UID` 兜底匹配）；前端 `core.js::qRecordsFromDetail()` 统一取记录，画廊战绩带与详情记录模块都改读它，Markdown `# 历史` 降为老后端兜底。反馈提交 / 历史修正后 `qvInvalidateMany()` 清详情缓存。回归：`tests/test_question_records.py`、`tests/app/question.test.mjs`。
  **剩余小债**：`parseQHistory` / `parse_history_lines` 这套 Markdown 解析现在只为兼容老后端，等确认没有旧手工 `# 历史` 需要展示后可整体删除；`history_log.csv` 每次 `get_question_records()` 都全量读一遍（单题请求、文件小，暂可接受，量大时改查投影表）。

## 锦上添花

- [ ] `reloadData()` 在多个写入点重拉完整统计快照；小数据无感，量大时可评估局部更新。
- [x] **界面字体本地化。** `omrs_dashboard.html` 加载 `assets/vendor/fonts/fonts.css`，Noto Sans SC 和 JetBrains Mono 均从本地 WOFF2 提供，运行时无 Google Fonts 外链。
- [x] **局域网模式访问控制。** 远端页面和 API 经 PIN 会话保护；本机及显式豁免网段直连免 PIN。配置与代理边界见 `AI/security.md`。

## 已经做得好的(不要动)

- `_serve_asset`(`server.py`)路径穿越防护扎实(`normpath` + 限定 `assets/` 内);assets 一律 `Cache-Control: no-cache`。
- ledger 不可变链 + 投影的设计有想法;`ledger_history` 分页合理。
- 核心运行时只依赖 Python 标准库；Pillow、jpegtran 只用于可选图片优化，不影响基础服务和导出。
- 根 `AGENTS.md` + `AI/README.md` 已把“每次持久化任务同步模块文档、任务日志和索引”设为完成条件。
