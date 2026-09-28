# OMRS 内置 AI 助手计划（自研 Harness + 权限系统 + 正文入账）

> 本文件是总纲：目标、架构、分期、关键决策与风险。进度只记在同目录 `progress.md`；每一期由规划者单独写一份 `exec-*.md` 执行说明，执行者按执行说明干活。
>
> - 默认执行者：Codex · 完整模式（每期一份执行说明，每步一个提交）
> - 规划者：CCW · 规划模式（每期开工前按当时的导出包写该期执行说明）
> - 部署：用户授权后执行，未指定执行者时由 Hermes Agent 执行

## 0. 用户诉求清单（原话，计划各节都要能指回这里）

| # | 原话 | 分类 | 本计划的处理 |
|---|---|---|---|
| U1 | "我想给OMRS嵌入AI功能 核心是Pi Agent AI通过调用MCP直接管理OMRS" | 明确要求：嵌入 AI、AI 能管理 OMRS。「Pi Agent」「MCP」是实现方式，已被 U2、U9 取代 | 总目标；MCP 列为范围外的可选后续（§3.9） |
| U2 | "能不能参照PI的核心逻辑用Python实现? 因为有历史记录回溯可以实现控制" | 明确要求：用 Python 参照 Pi 的核心逻辑实现；隐含前提：AI 的改动可以通过历史回溯来控制 | 阶段 E（Harness）；阶段 G1（按运行撤销） |
| U3 | "我会改设计,到时候用多线程" | 明确要求 | 阶段 A |
| U4 | "让自己维护的Agent有权限系统吧" | 明确要求 | §3.4、阶段 E3 |
| U5 | "这是个问题,或许Ledger应该记录正文数据" | 明确要求（方向）：正文进 Ledger；具体存法是实现方式 | §3.5、阶段 C |
| U6 | "到时候区分,新增一个类别" | 明确要求：AI 的写入在 Ledger 里单独一类来源 | 阶段 B1 |
| U7 | "可以"（回应：写接口加幂等键；反馈只记录用户明说的对错和分数） | 明确要求 | 阶段 B2、G5 |
| U8 | "那个skills已经过时了,后面计划删掉" | 明确要求 | 阶段 A4 |
| U9 | "同样的,自己写Harness"（回应：Pi 作为编程 Agent 默认形态不适合嵌入） | 明确要求 | 阶段 E |
| U10 | "不升级平时,以后有时间维护就看看Pi有没有更新" | 隐含前提：Pi 只作参考，不作运行依赖 | §3.1；不引入 Node 依赖 |
| U11 | "实现OpenAI兼容协议" | 明确要求 | 阶段 D |
| U12 | "一般来说让AI用关键词啥的搜比较好吧" | 明确要求（方向）：AI 用关键词找题 | §3.8、阶段 F2 |
| U13 | "可以,写成计划 不过要分很多步骤 逐步进行修改" | 明确要求：细粒度分步、逐步修改 | §4：9 期 30 余步，每步一个提交、门禁全绿；每期单独出执行说明 |

## 1. 现状基线（2026-09-27 实测，导出包 `20260926T231101Z`，v1.25.4）

### 1.1 环境与门禁

CCW 受限环境：Python 3.12.3、Node 22.22.2、git 2.43.0，出站网络被拒（pypi 返回 403），1 核 CPU。基线门禁：

| 命令 | 结果 |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 159 OK（46 秒） |
| `node --test tests/*.js tests/app/*.test.mjs` | 220 / 220 |
| `python3 tests/check_docs.py` | 0 处问题，2 条提醒（均为已有文档超 40KB） |

浏览器 E2E 本轮未跑（本计划未改页面）。

### 1.2 实测与读代码得到的事实

| # | 事实 | 性质 | 来源 |
|---|---|---|---|
| F1 | 服务单线程：一个未发完请求头的连接挂着时，`GET /api/status` 4 秒超时；该连接关闭后 0.00 秒返回 | 实测 | 隔离实例（fixture full，端口 18731）；`omrs/cli.py` 的 `OMRSTCPServer` 直接继承 `socketserver.TCPServer` |
| F2 | 并发追加 Ledger 会**静默**分叉哈希链：4 线程各追加 60 条，无任何异常，`verify_ledger` 返回 `valid: False`，首个错误「CMT-000075 prev_hash 不匹配」 | 实测 | `omrs/ledger.py::append_commit_in_db` 先 `SELECT` 链头、后 `INSERT`，读写不在同一个写事务里 |
| F16 | 并发申请题目身份会重号：4 线程各调 50 次 `reserve_operation_id`，200 个号里只有 150–178 个不同（3 次运行），无任何异常。线程化后两道新题可能拿到同一个 `_omrs_id` | 实测 | `omrs/ledger.py::_next_counter` 先读后写，不在写事务里 |
| F3 | 今天就存在并发写入者：工作区扫描线程每 600 秒追加 commit 并重建投影，与请求线程没有共同的锁；`_SCAN_LOCK` 只防扫描重入 | 读代码 | `omrs/workspace_sync.py` |
| F4 | 只改正文不写 commit：经 `/api/question/markdown` 只改正文，commit 数 58 → 58 | 实测 | `save_question_markdown`；扫描器发现 `content_only` 也只记在 changes 里 |
| F5 | 删除题目会 `os.remove` Markdown 文件，只写 `question.archive`（不含正文），正文不可恢复；附件图片不删除 | 读代码 | `omrs/question_ops.py::delete_question` |
| F6 | commit 已记录 `content_hash`（创建、迁移、元数据更新），但正文本身不在任何地方留存 | 读代码 | `creation.py`、`question_ops.py`、`workspace_sync.py` |
| F7 | 所有 API 写入的 `source` 都写死为 `"api"`；fixture 58 条 commit 的来源：api 44、self_check 12、system 1、migration 1 | 读代码 + 实测 | 各 `append_commit(vault, "api", ...)` 调用点 |
| F8 | 全量重放耗时：fixture（58 条）0.007 秒；合成 1558 条（约 15000 次反馈）1.6–1.7 秒 | 实测（1 核） | `rebuild_projection`；每次写入都会调用 |
| F9 | 未知 commit 类型在重放时被跳过，不报错 | 实测 | 追加自定义类型后 `rebuild_projection` 正常；新类型对旧代码回滚是安全的 |
| F10 | `/api/stats` 在 40 题时响应 28,050 字节（每题约 700 字节），208 题约 145KB | 实测 + 推断 | 不能原样交给模型 |
| F11 | SQLite FTS5 trigram 分词搜不到两字中文词：「最小正」命中，「周期」不命中 | 实测 | SQLite 3.45.1 |
| F12 | 原子写都用固定的 `<文件>.tmp` 临时名，两个线程同时写同一文件会互相踩临时文件 | 读代码 | `common.save_csv`、`labels.py`、`boards.py`、`question_ops.py`、`creation.py` |
| F13 | 模块级可变状态：`security`、`inbox`、`optimization` 各有自己的锁；`_TUNING_CACHE`、`_KATEX_BUNDLE_CACHE`、`log_utils._LOG_DIRS` 是无锁缓存 | 读代码 | 需在线程化时逐个复核 |
| F14 | `Skills/mistake-card-creator` 在进程内 import omrs 直接写文件，服务运行时是第二个写入者；仓库内除 README 结构图外无引用 | 读代码 | `Skills/`、`README.md` |
| F15 | Pi 参考：`packages/agent/src/agent-loop.ts` 的 `runLoop` 约 150 行；`packages/ai/src/api/openai-completions.ts` 1726 行，处理约 27 个兼容开关 | 读代码 | pi-main 0.87.1（MIT） |

### 1.3 与进行中计划的关系

`AI/plans/frontend-rearch/` 进行中：P6 剩余页面、P7、P8、终检由 Codex 执行，每页一个提交并升版本。本计划阶段 A–G 只改后端（`omrs/`）、测试与文档，和前端重构的冲突集中在版本号、`AI/changelog.md`、根 `README.md`、`AI/README.md`；阶段 H 要在前端外壳里加新页面，必须等 P8 之后。先后顺序见 §7 待确认项 Q1。

## 2. 目标与验收指标

完成后的状态：用户在 OMRS 网页里用中文和内置 AI 助手对话，助手能找题、看统计、给推荐、安排复习、改标记、改题目内容、录入文字题、按用户明说的结果记录反馈。同时满足：

| 指标 | 验收口径 |
|---|---|
| 不阻塞 | 任一慢请求（含 AI 运行、慢上游）期间，`GET /api/status` 在 1 秒内返回 |
| 并发安全 | 20 个并发写请求加一次工作区扫描后，`/api/ledger/verify` 为 valid，CSV 可解析 |
| 可审计 | 每条 AI 写入的 commit：`source` 为 `agent`，payload 带 run_id、tool_call_id |
| 可回溯 | 任一题的正文可列出历史版本并还原；删除的题正文仍可取回；一次 AI 运行可整体撤销，与之后用户改动冲突时拒绝并列出冲突 |
| 权限在服务端 | 设置、PIN、备份恢复、重启、源码导出、历史整体还原不可经 AI 触达（工具不存在）；需确认级写入未经用户点击确认不会执行 |
| 零依赖 | 核心运行时仍只用标准库；未启用助手时，其余功能行为与门禁不变 |
| 协议 | 兼容 OpenAI Chat Completions（流式与非流式、工具调用），各厂商差异由兼容配置描述 |

## 3. 目标架构

### 3.1 为什么不用 Pi 运行时和 MCP

U2、U9、U10、U11 已定：Harness 用 Python 自写，Pi 只作设计参考。好处是不引入 Node，核心零依赖原则不变；工具在进程内直接调用领域函数，不经 HTTP 回环，也就不存在「本机免 PIN 等于最高权限」的问题；权限与审计完全由 OMRS 控制。MCP 不在本计划内，以后若要让外部客户端复用工具，再在工具注册表上加一层外壳（§3.9）。

### 3.2 模块与存储

| 位置 | 职责 | 引入期 |
|---|---|---|
| `omrs/locking.py` | 进程级可重入写锁 `write_lock()` 与 POST 加锁豁免清单 | A2 |
| `omrs/actor.py` | 当前写入者上下文（`contextvars`）：用户或某次 AI 运行 | B1 |
| `ledger.db` 新表 `op_results` | 幂等键 → 首次结果 | B2 |
| `ledger.db` 新表 `blobs` | 正文内容寻址存储（sha256 → 正文） | C1 |
| `omrs/llm/` | OpenAI 兼容客户端、兼容配置、测试用假模型 | D |
| `omrs/agent/loop.py` | 与 OMRS 无关的通用循环（参照 Pi `runLoop`） | E1 |
| `omrs/agent/store.py`，`错题/.omrs/agent.db` | 对话、运行、工具调用记录 | E2 |
| `omrs/agent/policy.py` | 权限级别、确认令牌、预算 | E3 |
| `omrs/agent/runtime.py` | 后台运行线程、事件缓冲、`/api/agent/*` 接口 | E4 |
| `omrs/agent/tools/` | OMRS 工具（只读、写入、撤销） | F、G |
| `omrs/agent/prompts/system.md` | 中文系统提示 | E5 |
| `assets/app/features/assistant/` | 聊天面板 | H |
| `AI/agent.md` | 新模块文档；AGENTS.md 映射表登记 `omrs/agent/`、`omrs/llm/` → `AI/agent.md` | E1 |

对话数据放独立的 `agent.db`，不进 Ledger：对话不是学习状态的事实源，也不应拖慢全量重放。它在 `错题/.omrs/` 下，随备份导出（Q3），不进源码包。

### 3.3 一条消息的数据流

```
浏览器 POST /api/agent/message ──► runtime 建 run，起后台线程，立即返回 run_id
                                   │
      GET /api/agent/events?after=N ◄── 事件缓冲（文本增量、工具开始/结束、确认请求、结束原因）
                                   │
后台线程：loop ──► llm 客户端（不持写锁）──► 模型
            │
            └─► 工具分发器 ─► policy 判级 ─► [需确认] 发确认事件并等待 POST /api/agent/confirm
                          └─► actor 上下文 + write_lock() ─► 领域函数 ─► append_commit(source=agent)
```

写锁只在单次工具执行期间持有；模型思考和网络等待期间不持锁，用户在界面上的操作不被卡住。

### 3.4 权限模型（U4）

| 级别 | 例子 | 执行策略 |
|---|---|---|
| read | 查词表、搜题、看题、统计、推荐、查复习计划 | 自动执行 |
| reversible | 改题目标记、建复习 Session | 自动执行；计入每次运行的写入预算；可被 G1 撤销 |
| confirm | 改正文某一节、改知识点、移动/停用/恢复题目、录入文字题、记录反馈 | 发确认事件，用户在界面上点「允许」才执行；拒绝或超时即返回「用户未允许」 |
| 不注册 | 删除题目、设置、PIN 与认证、备份导入/恢复、重启、源码导出、历史整体还原/替换/撤回、展示板、标记定义、收件箱、导出、报告 | 工具不存在，模型无从调用 |

规则写死在服务端分发器里，不写在提示词里：

- **确认是带外的**：只认界面按钮发来的 `POST /api/agent/confirm`，聊天里的「好的」不算。
- **确认绑定参数**：确认令牌 = run_id + 工具名 + 规范化参数的 sha256；参数变了就是新请求；令牌 10 分钟过期。
- **预算**：每次运行最多 40 次工具调用、20 次写入、25 轮模型请求（可在配置里调小）；超出即结束运行并告知原因。
- **远端登录用户**与本机用户使用同一套级别（Q4）；未登录请求连 `/api/agent/*` 都到不了（沿用现有认证）。

### 3.5 正文入账模型（U5）

- **文件仍是当前版本，Ledger 存历史**：Obsidian 照常编辑 Markdown 文件；`ledger.db` 的 `blobs(hash, content)` 存每个出现过的正文版本，commit 只引用哈希。重放不读 blobs，全量重放的耗时不变（F8）；哈希链覆盖 `content_hash`，正文可校验。
- **正文变化都要入账**：新 commit 类型 `question.content_update`（payload：question_id、uid_at_that_time、before_hash、after_hash）。经 API 改正文写 `source=api` 或 `agent`；扫描器发现的 `content_only` 写 `source=self_check`。
- **写前对齐**：任何写正文的操作先重读文件，哈希与最近记录不同时先把这个未入账的版本记一笔（`self_check`），再执行写入；写入方可带 `expected_content_hash`，对不上就放弃（HTTP 409）。
- **删除可取回**：删除前保证当前正文已入账；正文历史接口能按 question_id 取回已删除题目的最后版本。
- **附件只增不改**：本计划新增的写路径一律不覆盖、不删除 `错题/附件/` 下已有文件（图片压缩是无损原位重写，不改引用，保持现状）。
- **回填**：首次启用时写一条 `question.content_snapshot`（`source=migration`），把现有全部题目的正文放进 blobs；幂等，只执行一次。

### 3.6 Harness 行为（参照 Pi `runLoop`，U2、U9）

要照搬的行为：

1. 外层循环处理「运行结束后排队的追问」（follow-up），内层循环处理「工具调用」和「运行中插话」（steering）；插话在下一次模型请求前注入。
2. 模型因长度上限截断（`finish_reason: length`）时，这一轮的全部工具调用一律判失败、不执行，因为参数可能残缺。
3. 工具执行出错时，错误作为工具结果交还模型，循环继续；工具不存在、参数不合 schema 同样处理。
4. 中止时，未完成的工具调用补「已中止」结果，保证会话记录前后一致；中止在工具执行之间生效，不打断正在持锁的写入。
5. 工具串行执行；执行前后各有钩子（`before_tool_call` 做权限判定，`after_tool_call` 做审计与结果截断）。
6. 结束原因明确：完成、中止、出错、预算耗尽、轮数上限。

不做：多厂商适配、OAuth、会话分支、并行工具、扩展/技能加载、上下文压缩（先用「单个对话最多 60 条消息，超出请新开对话」代替，压缩列为后续）。

### 3.7 模型协议与兼容配置（U11）

`omrs/llm/openai_compat.py` 只用标准库实现 `POST {base}/chat/completions` 的流式（SSE）与非流式调用。流式时按 `index` 累积工具调用参数片段，结束后一次性 `json.loads`，不做残缺 JSON 解析。兼容差异写成数据（`omrs/llm/compat.py` 的命名配置 + 用户覆写），只收与国内外常用厂商有关的几项：

| 开关 | 含义 |
|---|---|
| `reasoning_fields` | 从哪些字段读思考内容（`reasoning_content`、`reasoning`、`reasoning_text`） |
| `send_reasoning_back` | 带工具调用的 assistant 消息是否回传思考内容 |
| `tool_result_name` | 工具结果消息是否必须带 `name` |
| `max_tokens_field` | `max_tokens` 或 `max_completion_tokens` |
| `system_role` | `system` 或 `developer` |
| `stream_usage` | 是否发送 `stream_options.include_usage` |
| `strict_tools` | 工具 schema 是否带 `strict` |

内置配置：`openai`、`dashscope`、`deepseek`，其余用 `custom` 加覆写。每次请求与响应原文（去掉密钥）可按开关写入调试日志。测试用假模型按脚本回放，另用本地假 HTTP 服务回放手写的 SSE 样本；真实厂商联调是可选验证。

### 3.8 搜题（U12）

关键词找题是主路径，但要避开四个坑：

- **不用 FTS5 trigram**（F11），直接在内存里做子串匹配：题库几百道，逐题扫描是毫秒级。
- **文本先规范化**：NFKC、转小写、去空白、去 LaTeX 反斜杠与花括号，让 `\sin 2x` 能被「sin2x」命中；索引按 `content_hash` 缓存。
- **纯图片题搜不到正文**：结果里单独给出「在筛选范围内、正文无文字的题」数量，并支持按科目、分类、知识点、标记、状态（到期、逾期、顽固、已击杀、停用）、熟练度区间筛选。
- **统计不是搜索**：「哪块最弱」用聚合工具回答；搜索前先给模型现有词表（`ai_assist.collect_taxonomy` 的数据加上标记），让关键词和库里的叫法对齐。

搜索结果带总数、分页、每题一行摘要（UID、科目/分类、正文前 80 字、熟练度、到期日、命中字段），单次最多 30 条。

### 3.9 范围外（不在本计划主线）

MCP 外壳；上下文压缩；向浏览器推 SSE（先用轮询）；截图录题（收件箱与 Agent 打通）；Ledger 增量快照（只在生产实测重放超过 0.5 秒时升级为高优先级，见阶段 I）；`ai_assist.py` 改用共享客户端；WAL 模式（备份只拷 `ledger.db` 会漏掉 WAL 内容，要改备份后才能开）。

## 4. 分期与步骤

规则：每一步一个提交，提交前门禁全绿，提交里含代码、测试、文档、任务日志与 `progress.md` 更新。只有带用户可见变化的步骤升版本（按当时 HEAD 顺延）；不升版本的步骤写进下一个升版本步骤的 changelog 段。每期开工前由规划者按当时的导出包写该期执行说明。

### 阶段 A：并发地基（U3、U8）— 执行说明 `exec-2026-09-27-a.md`

| 步 | 做什么 | 验收要点 | 版本 |
|---|---|---|---|
| A1 | Ledger 追加与计数器原子化：读链头与插入、计数器的读与写各自放进 `BEGIN IMMEDIATE` 写事务，设 `busy_timeout` | 多线程与多进程并发后 `verify_ledger` 为 valid（F2 基线为 False）、申请的题目身份无重号（F16 基线有重号） | 不升 |
| A2 | 进程级写锁：POST 默认加锁（豁免清单逐条举证），后台线程的写入段加锁，锁顺序与超时写死 | 仍单线程时全部门禁不变 | 不升 |
| A3 | 服务线程化：`ThreadingMixIn` + `daemon_threads`；复核模块级状态 | F1 场景 1 秒内返回；慢上游期间其他请求正常；并发写后链与 CSV 完好 | 升次版本 |
| A4 | 删除过时的 `Skills/mistake-card-creator/` | 仓库内外无引用；源码导出测试通过 | 不升 |

### 阶段 B：写入来源与幂等（U6、U7）

| 步 | 做什么 | 验收要点 | 版本 |
|---|---|---|---|
| B1 | `omrs/actor.py`：写入者上下文。上下文为 AI 运行时，`append_commit` 把 `source` 由 `api` 改为 `agent`，payload 加 `_agent: {conversation_id, run_id, tool_call_id}`（参与哈希，投影忽略）；`AI/ledger.md` 登记来源取值 | 单测：同一领域函数在两种上下文下产生两种来源；旧链重放结果不变 | 不升 |
| B2 | 幂等：`op_results(op_id, result_json, created_at)`；领域写函数经统一包装接受 `op_id`，重复调用直接返回首次结果；HTTP 写接口可选接受 `client_op_id`；已知窗口（提交后、记录前崩溃）写进文档 | 同一 op_id 连调两次只产生一条 commit | 升修订号 |

### 阶段 C：正文入账（U5、U2）

| 步 | 做什么 | 验收要点 | 版本 |
|---|---|---|---|
| C1 | `blobs` 表：带 `content_hash` 的 commit 在同一事务里存正文；`verify_ledger` 增加 blob 校验 | 新建、迁移后的题都能按哈希取回正文 | 不升 |
| C2 | `question.content_update`：API 只改正文时入账；扫描器的 `content_only` 入账（`self_check`）；投影更新 `content_hash` | F4 场景 commit 数 +1；扫描后 +1 | 不升 |
| C3 | 回填 `question.content_snapshot`，幂等只执行一次 | fixture 上每题都有 blob；重复启动不再写 | 不升 |
| C4 | 写前对齐 `ensure_content_recorded` 与 `expected_content_hash`（409）；删除、移动、保存正文都先对齐 | Obsidian 未入账的修改不会被覆盖掉历史 | 不升 |
| C5 | 正文历史接口：列版本、取某版本、还原（写回文件并入账）、取回已删除题目的最后正文 | 改两次后能还原到第一版；删除后能取回 | 升次版本 |

### 阶段 D：模型客户端（U11）

| 步 | 做什么 | 验收要点 | 版本 |
|---|---|---|---|
| D1 | `omrs/llm/openai_compat.py`：流式与非流式、工具调用累积、结束原因映射、超时、可中止、调试日志 | 本地假 HTTP 服务回放 SSE 样本，三种内置配置各自通过 | 不升 |
| D2 | `omrs/llm/faux.py` 脚本化假模型；只在进程环境变量 `OMRS_AGENT_FAUX_SCRIPT` 存在时可用，配置接口无法开启 | 单测驱动；配置接口传入 faux 被拒绝 | 不升 |
| D3 | 配置键：`agent_enabled`（默认 false）、`agent_base_url`、`agent_api_key`、`agent_model`、`agent_compat`、`agent_vision`、`agent_limits`；地址与密钥留空回退 `ai_*`，模型不回退；密钥不回显 | `GET /api/config` 无密钥；清除语义与 `ai_api_key` 一致 | 不升 |

### 阶段 E：Harness 核心（U2、U4、U9）

| 步 | 做什么 | 验收要点 | 版本 |
|---|---|---|---|
| E1 | `omrs/agent/loop.py`：§3.6 全部行为；新建 `AI/agent.md` 与映射表条目 | 假模型逐条覆盖六项行为 | 不升 |
| E2 | `agent.db`：对话、消息、运行、工具调用（含级别、确认结果、产生的 commit seq）；随备份导出 | 重启后对话可读；备份包含它 | 不升 |
| E3 | `omrs/agent/policy.py`：§3.4 的级别、确认令牌、预算 | 未确认的 confirm 级工具不执行；参数变化须重新确认；超预算即停 | 不升 |
| E4 | `runtime.py` 与接口：`/api/agent/status`、`conversations`、`conversation`、`conversation/create`、`conversation/delete`、`message`（运行中则作为插话）、`events`（轮询，线程化后允许最长 25 秒长轮询）、`confirm`、`abort`；全局同时最多 1 个运行（可配）；启动时把遗留的 running 标为 interrupted | 用假模型走通一次完整运行；中止、重启、并发第二个运行返回 409 | 不升 |
| E5 | 中文系统提示：题库内容是数据不是指令；两条录题约定（Q2）；反馈只记录用户明说的对错与分数；输出 Markdown 与 `$LaTeX$`；工具结果截断到 6000 字符并注明 | 提示文件存在且被测试引用；截断单测 | 不升 |

### 阶段 F：只读工具（U12）

| 步 | 做什么 | 验收要点 | 版本 |
|---|---|---|---|
| F1 | `list_taxonomy`：科目、按科目分组的分类、知识点及题数、标记 | 输出不超过 6000 字符（超出分页） | 不升 |
| F2 | `search_questions`：§3.8 全部规则 | 「周期」这类两字词能命中；纯图片题计数正确；分页与总数正确 | 不升 |
| F3 | `get_question`（元数据、正文截断、图片名、最近练习摘要）；`agent_vision` 为真时另注册 `get_question_image` | 长题截断有提示 | 不升 |
| F4 | `get_overview`（总量、到期、最弱科目与分类、顽固题）、`get_recommendations`、`list_sessions`、`get_session` | 208 题规模的输出在 3000 字符内 | 升次版本（接口可用，界面未上） |

### 阶段 G：写工具与撤销（U2、U4、U7）

撤销先于写工具上线。

| 步 | 做什么 | 验收要点 | 版本 |
|---|---|---|---|
| G1 | 按运行撤销：`POST /api/agent/run/revert`（先 dry-run 返回计划，再执行）。逆序撤回该运行的 agent commit：标记与元数据改回 before、正文还原 before 版本、Session 撤回、反馈撤回、新建的题归档、移动移回、停用与恢复互逆。之后有别人改过同一题或同一 Session 就整体拒绝并列出冲突，不做部分撤销 | 每类逆操作单测；冲突时一条都不撤 | 不升 |
| G2 | reversible 级：`set_question_labels`（批量，单次最多 50 题）、`create_review_session` | 结果带 commit seq；预算生效 | 不升 |
| G3 | confirm 级正文：`update_question_section`（题目、答案、错因，替换或追加）、`set_knowledge_points`；确认事件带前后对比；写前对齐 | 未确认不写；对齐与 409 生效 | 不升 |
| G4 | confirm 级结构：`move_question`、`suspend_question`、`resume_question`、`create_text_question`（不暴露难度，默认 5；不暴露错因，Q2） | 各工具可被 G1 撤销 | 不升 |
| G5 | confirm 级反馈：`record_feedback`，必填 `user_statement`（用户原话），确认框展示原话、题目与分数 | 缺原话被拒；可撤销 | 升次版本 |

### 阶段 H：聊天面板（等前端重构 P8 之后）

| 步 | 做什么 | 验收要点 | 版本 |
|---|---|---|---|
| H1 | `features/assistant/` 页面：对话列表、消息流（轮询事件）、Markdown 与 KaTeX 复用 `domain/question/markdown.js`、工具调用卡片、中止、新对话；遵守 `check_ui.py` | E2E（假模型）主路径；手机 390 宽可用 | 升 |
| H2 | 确认对话框（`ui/dialog`）：前后对比、允许/拒绝、倒计时 | E2E：拒绝后无 commit | 升 |
| H3 | 运行结束有写入时经 bus 让统计、题目缓存、Session 列表刷新 | E2E：AI 改标记后题库页立即可见 | 升 |
| H4 | 运行记录与「撤销这次运行」；历史时间线把 `agent` 来源显示为「AI」 | E2E：撤销后题库恢复 | 升 |
| H5 | 设置页「AI 助手」：开关、模型、兼容配置、预算、测试连接 | 密钥不回显；未启用时侧栏无入口 | 升 |

### 阶段 I：收尾与部署

| 步 | 做什么 | 验收要点 |
|---|---|---|
| I1 | 文档收口：根 `README.md` 特性表与技术债表、`AI/agent.md`、`AI/security.md`（AI 权限边界）、`AI/data.md`（`agent.db`、`blobs`、`op_results`）、`AI/optimization.md` | `check_docs.py` 0 问题 |
| I2 | 部署（须用户授权）：先备份；部署前后各跑一次生产 `/api/ledger/verify`（部署前若已 invalid，停下报告，可能是 F3 的历史遗留）；记录生产重放耗时，超过 0.5 秒把增量快照升为高优先级；部署后助手默认关闭，由用户在设置页开启 | 部署清单逐项打勾 |

## 5. 关键技术决策（按推荐项执行，除非用户另行指定）

| # | 决策 | 默认 | 理由 |
|---|---|---|---|
| D1 | 写锁粒度 | 单个进程级可重入锁，按单次写操作持有 | 数据层是文件 + 单个 SQLite，细粒度锁收益小、风险大 |
| D2 | POST 加锁方式 | 默认全部加锁，豁免清单逐条举证 | 漏锁比多锁危险 |
| D3 | 跨进程安全 | 靠 SQLite `BEGIN IMMEDIATE` + `busy_timeout`；不做文件锁 | A4 删掉第二写入者后，只剩 CLI 偶发写入 |
| D4 | AI 来源标记 | `source=agent` + payload `_agent`（参与哈希） | 放在额外列里不受哈希链保护 |
| D5 | 正文存储 | `ledger.db` 内 `blobs` 表，commit 只存哈希 | 与 commit 同事务；重放不读正文 |
| D6 | 对话存储 | 独立 `agent.db` | 不污染事实源、不拖慢重放 |
| D7 | 浏览器取事件 | 轮询（线程化后可长轮询） | SSE 长连接占线程，收益不大 |
| D8 | 同时运行数 | 全局 1 个 | 多端同时发起时串行更安全；可配 |
| D9 | 工具执行 | 串行 | 有写锁，并行无收益 |
| D10 | 上下文 | 单对话 60 条消息上限，不做压缩 | 先保证正确，压缩列为后续 |
| D11 | 搜索实现 | 内存子串匹配 + 规范化，不用 FTS | F11；规模小 |
| D12 | 真实厂商联调 | 可选；用户提供测试密钥时才做 | 受限模式无网络，且会产生费用 |

## 6. 风险与对策

| 风险 | 对策 |
|---|---|
| 线程化暴露隐藏的共享状态问题 | A3 逐个复核模块级状态；并发压测放进单测；E2E 连跑两遍 |
| 写锁造成死锁 | 锁顺序固定：写锁在外、模块锁在内；持模块锁时禁止取写锁；取锁超时 60 秒返回 503 并记日志 |
| 重放随历史变慢，AI 连续写入被放大 | 工具优先批量（标记一次最多 50 题）；预算限制写入次数；I2 实测后决定是否上增量快照 |
| 提示注入（OCR 文本、题目正文） | 权限在服务端；危险能力不注册；确认带外且绑定参数 |
| 模型编造反馈分数 | `record_feedback` 必须附用户原话并经确认 |
| 与前端重构的版本号、changelog 冲突 | 默认串行（Q1）；若并行，版本号在合入时顺延，changelog 按合入顺序排 |
| 厂商兼容差异导致工具调用失败 | 兼容配置做成数据；调试日志存原文；假服务回放样本 |
| 生产 Ledger 已因 F3 分叉 | I2 部署前先校验；A1 只防新增分叉，不自动修复旧链 |

## 7. 需用户确认（未确认前按默认执行）

| # | 问题 | 默认 |
|---|---|---|
| Q1 | 与前端重构的先后 | 串行：frontend-rearch 终检完成后再开始阶段 A；阶段 H 必然在 P8 之后 |
| Q2 | 两条录题约定（难度默认 5、AI 不代写错因）在删除旧 Skill 后是否保留 | 保留：录题工具不暴露难度与错因参数；错因只能经 `update_question_section`（需确认）写入 |
| Q3 | 对话记录是否进备份 | 进（`agent.db` 在 `错题/.omrs/` 下） |
| Q4 | 远端登录用户能否使用助手 | 能，权限与本机相同 |
