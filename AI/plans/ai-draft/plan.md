# 主 AI 录题与 AI 草稿区计划

> 本文件是总纲：目标、流程、架构、分期、关键决策。进度只记在同目录 `progress.md`；每一期一份 `exec-*.md` 执行说明。
>
> - 默认执行者：Codex · 完整模式（用户也可指定 Claude Code · 完整模式）；每期一份执行说明，每步一个提交
> - 规划者：Claude Code · 完整模式，2026-09-28，基于本机 HEAD `ae471fc`（v1.28.1）
> - 部署：P2 完成后才有完整的用户价值；部署一律等用户授权

## 0. 用户诉求清单（原话，各节都要能指回这里）

| # | 原话 | 分类 | 处理 |
|---|---|---|---|
| U1 | "似乎不需要 AI 录入页面，反正是录入作业帮的，我原来的似乎就可以满足" / "主要优化主 AI 录入" | 明确要求：作业帮批量录入维持收件箱现状，本计划只做主 AI 录题 | 范围边界（§6） |
| U2 | "如果是聊天中比如在解一道题，然后我发给主 AI 一个截图，它识别到题目后……就可以主 AI 用工具自己创建题目，答案解析，错因（要用户提供）" | 明确要求：聊天贴图 → 主 AI 用工具录题；错因只能来自用户 | P1 |
| U3 | "如果题目不能完全转文本（即附带图片），就把题目图片暂存在一个地方用户有空自己框选（可以录入时候选择是否作为训练数据）" | 明确要求 | P3（待框选、训练开关） |
| U4 | "这种一般就是我搜作业帮，结果这个题目解析不够好，我又去问 ChatGPT，得到解析后截图 ChatGPT 解析一起给主 AI" | 隐含前提：一道题常由多张截图组成 | §3.2 一份草稿引用多张图 |
| U5 | "AI 录入的题目可以选择静默录入，专门弄个地方放 AI 录入的题目，然后审核通过就录入……或者人类自己改，比如手动框选，重新识别" | 明确要求：静默录入 + 草稿审核区 | P2、P3 |
| U6 | "手动框选又要收集数据训 AI" | 明确要求 | P3 训练开关 |
| U7 | "可以在设置选择默认是 AI 自动框还是手动还是每次询问" | 明确要求 | P3（每次询问 / 手动）、P4（AI 自动框） |
| U8 | "设置里面可以选择即使判定题目和答案都是识别文字，也要框选，这样一般是为了训练模型创造更多数据" | 明确要求 | P4 |
| U9 | "设置里面设置AI是否支持图片,如果不支持会走模型转述,DS最新已经能识图了" | 明确要求 | P1（`agent_vision` 两条路） |
| U10 | "2.你的想法"（回应：一份草稿引用多张图，新建 drafts 表） | 明确要求 | §3.2 |
| U11 | "草稿不进Ledger,独立管理" | 明确要求 | §3.1 |
| U12 | "可以接受,但一般不会存在这样的,如果是这样的话就不用调框选AI了"（回应：一次贴的图含多道题时拆成多份草稿、共用图片） | 明确要求 | §3.2、P4 跳过规则 |
| U13 | "2.可以"（回应：侧栏录入入口显示待审核数量） | 明确要求 | P2 |
| U14 | "先不做让ai改功能,默认先自己改" | 明确要求：不做 AI 修改草稿 | §6 范围外；AI 没有改草稿的工具 |
| U15 | "制定计划,不干活" | 本轮只出计划 | — |

## 1. 现状基线（2026-09-28，本机 HEAD `ae471fc`，v1.28.1，读代码）

| # | 事实 | 来源 |
|---|---|---|
| F1 | `POST /api/agent/message` 只收 `{conversation_id, text}`；`post_message` 把 `{"role":"user","content":text}` 存进 `agent.db` | `omrs/agent/runtime.py::post_message` |
| F2 | `model_messages` 重放时去掉 `_` 开头的内部字段，可以用来挂附件引用而不进模型上下文 | `omrs/agent/runtime.py::model_messages` |
| F3 | OpenAI 兼容客户端的 `build_payload` 对 user 消息只发 `msg.get("content") or ""`，内容若是数组会原样发出，但没有任何图片处理 | `omrs/llm/openai_compat.py::build_payload` |
| F4 | `agent_vision` 已是配置键（布尔，校验在 `omrs/agent/config.py`），但没有任何代码使用它，设置页也没有开关 | `omrs/agent/config.py`、`assets/app/features/settings/agent-view.js` |
| F5 | 视觉调用已有现成封装：`_ai_config(vault, "extract")` 选模型，`_call_model` / `_call_model_multi_image` 按 `image_url` data URL 发图 | `omrs/ai_assist.py` |
| F6 | 现有录题工具 `create_text_question`（confirm 级）：难度固定 5，`cause=""` 写死，只有文字 | `omrs/agent/tools/write.py::create_tool` |
| F7 | `creation.create_question` 接受 `question_text / answer_text / cause / question_images / answer_images / related_tags / labels`，图片是 data URL 列表 | `omrs/creation.py` |
| F8 | 权限级别只有 `read / rev / confirm` 三级；写入预算按「产生 commit 的工具调用」计数 | `omrs/agent/policy.py`、`AI/agent.md` §3 |
| F9 | AI 的写入经 `agent_actor` 把 commit 来源记为 `agent`，按运行撤销按 `payload._agent.run_id` 找 commit | `omrs/actor.py`、`omrs/ledger.py`、`omrs/agent/revert.py` |
| F10 | 收件箱：`upload_images(vault, files, source)`，`source` 目前是 `phone / desktop / paste`；框选画布、裁图（`crop.js`）、detect 提供方、训练统计与导出都在收件箱里 | `omrs/inbox.py`、`assets/app/features/create/` |
| F11 | 录入页工作区由 `STAGES` 定义，已有按状态计数的机制（`countKey`） | `assets/app/features/create/state.js` |
| F12 | 备份导出打包整个 `错题/`（含 `.omrs/`），新目录 `错题/.omrs/drafts/` 自动随备份 | `omrs/optimization.py::create_backup_export` |
| F13 | 只写 `agent.db` 的 POST 在写锁豁免清单里，每条写明理由 | `omrs/locking.py` |

## 2. 目标与验收

完成后：用户在助手里贴 1–N 张截图并说「录一下」，主 AI 把题录成草稿，放进录入页的「AI 草稿」工作区；侧栏录入入口显示待审核数量；用户在草稿区看、改、框选，点「通过」才写入题库。用户选择作为训练数据的截图和框进入收件箱数据集。

| 指标 | 验收口径 |
|---|---|
| 两种看图方式 | `agent_vision` 开：图片以 `image_url` 进主模型；关：主模型只看到转述文字，且能调 `describe_image` 追问 |
| 草稿不进 Ledger | 建草稿、改草稿、框选、丢弃，commit 数不变；只有「通过」产生 commit |
| 错因来自用户 | `create_draft` 带了错因却没有 `cause_statement`，或原话在本对话的用户消息里找不到时，工具报错，草稿不建 |
| 可追溯 | 题目入库的 commit payload 带 `_draft: {draft_id, conversation_id}`；草稿记下 `uid` |
| 训练数据可控 | 只有训练开关打开的图进收件箱数据集；关着的图不出现在收件箱任何列表和导出里 |
| 现有功能不变 | 收件箱批量录入、快速录入、AI 助手其余工具、按运行撤销行为不变；门禁全绿 |

## 3. 流程与架构

### 3.1 总流程

```
用户在聊天里贴 1–N 张截图，附一句话
  │  POST /api/agent/message {conversation_id, text, images:[dataURL…]}
  ▼
图片按 sha256 存入 drafts/images/，本对话内编号 IMG-1、IMG-2…
用户消息存为 {"role":"user","content":text,"_images":["IMG-1",…]}
  │
  ▼
◇ agent_vision？
  ├─ 开 → 重放时把 _images 展开成 image_url 内容块（只展开最近 4 张，更早的换成占位文字）
  └─ 关 → 运行开始前逐张调转述模型（ai_model_extract），结果按 sha256+模型缓存
          以「[IMG-1 转述] …」文本块拼进该条用户消息
  │  两种模式都提供只读工具 describe_image(image, question)
  ▼
◇ 用户要求录题？
  ├─ 否 → 普通对话
  └─ 是 → 主 AI 分块判定：题目、答案各自能否完整转成文字
          ◇ 用户说过错因？没说 → AI 追问（用户可答「先不填」）
          ▼
          create_draft（rev 级，自动执行，不写 Ledger）
            · 能转的块写文字；必须留图的块写 kind=image + 来源图
            · 错因必须带 cause_statement（用户原话）
          ▼
          ◇ 有 image 块？
            ├─ 否 → 草稿：待审核
            └─ 是 → 草稿：待框选（P3 起按 draft_crop_mode 决定是否 AI 框，见 3.4）
          ▼
          ◇ draft_mode
            ├─ silent  → 聊天里显示草稿卡片，草稿留在草稿区
            └─ confirm → AI 再调 commit_draft（confirm 级），用户在聊天里点允许即入库
```

### 3.2 草稿与图片

- 一份草稿 = 一道题，可引用多张图（U4、U10）。一次贴的图含多道题时，拆成多份草稿共用同一批图（U12）；**被两份及以上草稿引用的图不跑 AI 框选**，一律手动框。
- 图片属于对话，不属于草稿：同一张图（同 sha256）在库里只存一份，`conv_images` 记它在哪个对话里叫 IMG-几。
- 草稿的块（block）：`section`（题目 / 答案）、`ord`、`kind`（text / image）、`text`、`image_sha`、`box`（归一化 `x y w h`，未框为空）、`box_origin`（manual / ai / ai_edited）、`ai_box`。一个节可以文字块和图片块混排，入库时按 `ord` 拼：文字进正文，图片块裁成 PNG 进 `question_images` / `answer_images`，与收件箱 commit 的拼法一致。

### 3.3 草稿状态

```
[create_draft] ─┬─ 有未框的 image 块 → 待框选(cropping) ── 全部框好 ──→ 待审核(review)
                └─ 没有 ─────────────────────────────────────────────→ 待审核(review)
待审核 ── 用户把某块改成 image 或清空框 ──→ 待框选
待审核 ── 通过 ──→ 已入库(done，只读，记 uid)
待框选 / 待审核 ── 丢弃 ──→ 已丢弃(discarded，保留 draft_discard_keep_days 天后删图片引用)
```

没有「修改中」状态：AI 不能改草稿（U14），只有用户在草稿区改，不存在并发编辑。

### 3.4 框选与训练数据（P3、P4）

```
待框选的草稿
  ◇ draft_crop_mode（图被多份草稿共用时强制按 manual）
    ├─ ask    → 聊天草稿卡片给「AI 框」「我来框」两个按钮（P4 之前只有「我来框」）
    ├─ auto   → 对来源图跑现有 detect（inbox_detect_provider），框写进块，box_origin=ai（P4）
    └─ manual → 等用户去草稿区框
  ▼
草稿区框选（复用收件箱画布 process-canvas.js）
  ▼
◇ 这张图的训练开关（默认取 draft_train_default，默认关）
  ├─ 开 → 通过时把图和框登记为收件箱条目：source=chat、layout=other、status=ready，
  │       regions 带 origin 与 ai_box；不进收件箱待处理队列，计入统计与导出
  └─ 关 → 框只用来裁图
```

`draft_force_crop` 打开时（P4），全文字的草稿也会给每张来源图生成待框任务，框只进训练集，不生成裁图，不阻塞入库。

### 3.5 存储 `错题/.omrs/drafts/`

```
drafts.db          SQLite
images/<sha256>.<ext>
events.jsonl       只追加：image.add / image.transcribe / draft.create / draft.update / draft.crop / draft.commit / draft.discard / image.train
```

| 表 | 列 |
|---|---|
| `images` | `sha256` PK、`file`、`mime`、`width`、`height`、`bytes`、`created_at`、`transcript`（JSON）、`transcript_model`、`train`（0/1，NULL 表示未设置）、`inbox_item_id` |
| `conv_images` | `conversation_id`、`n`（IMG-n 的 n）、`sha256`、`run_id`、`created_at`；主键 `(conversation_id, n)` |
| `drafts` | `id`（`DR-YYYYMMDD-xxxxxx`）、`status`、`conversation_id`、`run_id`、`tool_call_id`、`subject`、`category`、`knowledge_points`（JSON）、`difficulty`（默认 5）、`labels`（JSON）、`cause`、`cause_statement`、`note`、`uid`、`question_id`、`created_at`、`updated_at` |
| `blocks` | `id`、`draft_id`、`section`、`ord`、`kind`、`text`、`image_sha`、`x y w h`、`box_origin`、`ai_box`（JSON） |

### 3.6 设置项（`config.json`，`common.CONFIG_DEFAULTS`）

| 键 | 界面名称 | 取值 | 默认 | 期 |
|---|---|---|---|---|
| `agent_vision` | 主 AI 支持图片 | 布尔 | false | P1（已有键，接上逻辑和开关） |
| `draft_mode` | AI 录题方式 | `silent` / `confirm` | `silent` | P2 |
| `draft_crop_mode` | 留图部分怎么框 | `ask` / `auto` / `manual` | `ask` | P3（`auto` 在 P4 前按 `manual` 处理） |
| `draft_train_default` | 聊天截图默认作为训练数据 | 布尔 | false | P3 |
| `draft_force_crop` | 全是文字也要框（造训练数据） | 布尔 | false | P4 |
| `draft_discard_keep_days` | 丢弃的草稿保留天数 | 整数 ≥1 | 7 | P3 |

### 3.7 工具（`omrs/agent/tools/`）

| 工具 | 级别 | 期 | 说明 |
|---|---|---|---|
| `describe_image` | read | P1 | `{image:"IMG-n", question}` → 视觉模型针对性回答，≤2000 字 |
| `list_drafts` / `get_draft` | read | P1 | 查本库草稿（默认只列未入库的） |
| `create_draft` | rev | P1 | 建草稿；自动执行，计入写入预算，不进按运行撤销 |
| `commit_draft` | confirm | P2 | 只在 `draft_mode=confirm` 时注册；只能提交本对话建的、状态为待审核的草稿 |
| `create_text_question` | — | P1 | 下线，录题只保留草稿一条路径 |

AI **没有** `update_draft`、`discard_draft`（U14）。

### 3.8 HTTP（`/api/drafts/*`，同源校验与写锁规则同其他端点）

| 方法 | 路径 | 期 |
|---|---|---|
| GET | `/api/drafts/list?status=`、`/api/drafts/item?id=`、`/api/drafts/image?sha=`、`/api/drafts/counts` | P1（接口）/ P2（界面） |
| POST | `/api/drafts/update`（字段与块整体覆盖）、`/api/drafts/commit`（带裁图 data URL）、`/api/drafts/discard` | P2 |
| POST | `/api/drafts/boxes`、`/api/drafts/extract`（框后转文字）、`/api/drafts/image/train` | P3 |
| POST | `/api/drafts/detect` | P4 |

## 4. 分期

| 期 | 目标 | 用户能做什么 | 主要内容 |
|---|---|---|---|
| **P1 地基** | 聊天能贴图、AI 能建草稿 | 聊天贴图让 AI 看图 / 转述；AI 建草稿（草稿区界面还没有，只能经接口看到） | `omrs/drafts.py` 存储；消息附图；`agent_vision` 两条路与转述缓存；`describe_image`、`list_drafts`、`get_draft`、`create_draft`；下线 `create_text_question`；助手输入框粘贴 / 拖入图片；设置页「主 AI 支持图片」开关；提示词规则；假模型脚本与测试 |
| **P2 草稿区** | 能审核入库 | 在录入页「AI 草稿」看、改、通过、丢弃；侧栏角标；聊天草稿卡片；确认模式 | 录入页新工作区；草稿表单（复用快速录入的字段组件）；image 块在 P2 只能选「整图」作为框；`/api/drafts/update·commit·discard`；入库 payload 带 `_draft`；侧栏录入入口与工作区计数；`draft_mode` 与 `commit_draft` |
| **P3 框选与训练** | 能框、能攒训练数据 | 在草稿区手动框选；框后转文字；逐图训练开关 | 复用 `process-canvas.js`；`draft_crop_mode` 的 ask / manual；聊天卡片「我来框」；`/api/drafts/boxes·extract·image/train`；通过时登记收件箱条目（`source=chat`）；丢弃清理 |
| **P4 自动化** | 按设置全流程自动 | AI 自动框；全文字也框 | `draft_crop_mode=auto` 与卡片「AI 框」；共用图跳过规则；`draft_force_crop`；训练统计里区分 chat 来源 |

每期单独写执行说明；P1 的见 `exec-2026-09-28-p1.md`。P2–P4 的执行说明在上一期落地后，按当时代码写。

## 5. 关键决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | 草稿存独立的 `drafts.db`，不复用 `inbox.db` | U11；收件箱的 item 是「一张图 N 道题」，草稿是「一道题 N 张图」，模型相反；训练数据只在通过时单向登记到收件箱 |
| D2 | 图片不以 data URL 存进 `agent.db`，消息里只存 `_images` 引用 | `agent.db` 每次打开对话要全量重放，几 MB 的 base64 会拖慢重放和事件接口 |
| D3 | 视觉模式重放只展开最近 4 张图 | 每轮请求都带全部历史图片，token 与延迟随对话线性增长；更早的图换成「[IMG-n 已省略，需要时调 describe_image]」 |
| D4 | 转述在运行开始、进入循环前同步完成，并发 `image.transcribe` 事件 | 主模型第一轮就需要转述文字；事件让界面显示「正在转述 IMG-1」 |
| D5 | `create_draft` 用 `rev` 级，写入预算单独计一次 | 不写 Ledger，不需要确认（静默录入的前提，U5）；仍受单次运行写入上限约束，防止 AI 刷出大量草稿 |
| D6 | 错因的 `cause_statement` 服务端校验：规范化空白后必须是本对话某条用户消息的子串 | U2「要用户提供」；规则写在服务端，不靠提示词 |
| D7 | 用户在草稿区点「通过」产生的 commit 来源是 `api`（用户），payload 带 `_draft`；确认模式下 `commit_draft` 产生的 commit 来源是 `agent` | 用户亲手通过的题不该被「按运行撤销」连带删除；确认模式等同于现有 `create_text_question` 的语义 |
| D8 | 训练开关按图记，不按草稿记 | 训练的是框题模型，样本单位是图 |
| D9 | 聊天截图登记到收件箱时 `layout=other` | ChatGPT 等截图与作业帮版式不同，混进 `zuoyebang` 会污染模板与统计 |
| D10 | 手动框选的画布复用收件箱 `process-canvas.js`，不另写 | 框选交互、遮罩、缩放已成熟 |

## 6. 范围外

- AI 修改或丢弃草稿（`update_draft`、「回到对话」按钮）——U14，推迟。
- 收件箱批量录入流程的任何改动——U1。
- 训练框题模型本身、`local_http` 检测服务——本计划只产出数据。
- MCP、助手其余推迟项（B2 幂等等），见 `AI/plans/ai-agent/progress.md`。

## 7. 风险

- **厂商对 `image_url` 的支持不一致**：DeepSeek、百炼的视觉模型是否接受 OpenAI 格式的 data URL、单图大小上限各不相同。P1 在「测试连接」里加一次带小图的探测，失败时提示改用转述模式；兼容差异按需加进 `omrs/llm/compat.py`。
- **转述质量决定录题质量**：关视觉模式时，公式和图形的转述可能丢信息。缓解：转述要求按块给出可转性判断，主 AI 可用 `describe_image` 追问；无法转的块一律留图。
- **上下文膨胀**：多图对话容易撞上 60 条消息上限与上下文窗口。D3 限制展开张数；转述文本每张截断到 3000 字。
