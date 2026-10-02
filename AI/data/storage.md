# 独立存储结构

> **速查**
> - 职责：报告、收件箱、标记定义、展示板、助手、标注、草稿、训练与系统运行记录
> - 入口：`omrs/reports.py`、`omrs/inbox.py`、`omrs/boards.py`、`omrs/agent/store.py`
> - 不变量：独立存储不由学习 Ledger 重放；备份屏障覆盖全部数据库与工作文件
> - 必跑测试：`tests/test_inbox.py`、`tests/test_practice_card.py`、`tests/test_runtime_records.py`、`tests/test_migration_compat.py`
> - 相关：`AI/data.md`、`AI/ledger.md`、`AI/mcp-storage.md`、`AI/agent.md`

## 1. report/（AI 分析报告托管）

> 对应源文件：`omrs/reports.py`

| 路径 | 说明 |
|---|---|
| `错题/report/<id>.html` | 单份报告的纯 HTML 文件 |
| `错题/report/index.json` | 报告索引数组：`[{id, name, filename, created_at, size}]` |

- `id` 形如 `RPT-YYYYMMDDHHMMSS`（同秒冲突加 `-N`）。`created_at` 由后端在创建时记录。
- 报告由 `GET /api/report/view?id=` 以 `text/html` 提供，响应使用独立来源的 CSP 沙箱。报告内仍用 `<img src="/api/image?name=<URL编码文件名>">` 引用题目图片；浏览时服务端只为附件目录中的静态图片 URL 加当前会话的单图签名。磁盘上的报告 HTML 保持原样。
- 题目图片文件名可从 `/api/question?uid=` 的 `images`、`/api/analytics` 的 `items[].images`，或导出复盘报告 JSON 中获得（均由 `extract_images()` 从题面 `![[名]]`/`![](路径)` 解析，取 basename）；`/api/stats` 的 `items` 不含 `images`。
- 报告页下载 AI 分析材料时，可选择不带图片的单个 Markdown，或包含 Markdown + `images/` 的 ZIP。ZIP 只收录 `items[].images` 引用且仍存在的题面图片，不包含未引用附件；其中图片只供 AI 阅读，生成的托管 HTML 仍按上一条 `/api/image?name=` 规则引用。

---

## 2. 收件箱 `错题/.omrs/inbox/`

`inbox.db`（SQLite：items / regions / cards / jobs / meta / chat_training_boxes；items 扩展列含 `blind`、`blind_boxes`、`reset_epoch`、`revision`，`connect()` 对旧库 ALTER 补齐）、`raw/<sha256>.<ext>`（上传原件）、`crops/`（裁剪缓存，可重建）、`annotations.jsonl`（append-only 标注事件）。区域坐标归一化 0–1。items.training_only 隔离聊天训练图，chat_training_boxes 独立保存训练标注并按图合并导出。`reset_epoch` 是当前图处理代次，重置递增以阻止旧保存和后台任务写回；`revision` 是当前图写入版本，更新、重置、丢弃和录入成功后递增，HTTP 写入必须附预期版本。重置删除当前区域、题卡和对应裁图缓存，保留原图及历史事件。字段与状态机见 `AI/inbox.md` §2、§9；`items.layout` 的新上传默认值为 `zuoyebang`（作业帮截图），已有记录可在处理页改选。不参与备份导出以外的任何投影；`item.commit` 事件里记录了创建出的 `uid` / `question_id` 便于回溯。

活动配置支持：`ai_model_detect`、`ai_model_extract`、`ai_model_classify`（string，留空回退 `ai_model`；`CONFIG_DEFAULTS` 均为空串）。同时支持 `inbox_detect_provider`（`vlm`）、`inbox_local_detect_url`（`""`）、`inbox_blind_every`（0）、`inbox_auto_ready_conf`（0.0）、`inbox_auto_on_upload`（false）、`inbox_discard_keep_days`（7），含义见 `AI/inbox.md` §8。丢弃项超期清理后 `items.file` 为 NULL、原图文件删除，行与 `annotations.jsonl` 事件保留。

---

## 3. 用户标记 `labels.json`

路径：`错题/.omrs/labels.json`。这是标记定义表，不是题目归属的第二份事实源：
题目真正保存的是 Markdown YAML 中可读的 `标记:` 名称。文件格式如下：

```json
{
  "version": 1,
  "labels": [{
    "id": "LB-20260904-a1b2c3",
    "name": "考前必看",
    "color": "#dc2626",
    "order": 1,
    "priority_bonus": 0.0,
    "archived": false,
    "created_at": "2026-09-04T12:00:00+00:00"
  }]
}
```

- `id` 只用于标记定义管理；题目 YAML 不引用它，方便在 Obsidian 中直接读写。
- `name` 必须唯一，不能包含换行或 `|`；`color` 规范化为 `#rrggbb`。
- `order` 控制选择器顺序；`priority_bonus` 是可选的调度加成，默认 `0.0`。
- 当前定义文件使用临时文件 + `fsync` + `os.replace` 原子写，尚未滚动 `.bak`。
- 题目标记进入 Ledger 的方式是 `question.metadata_update_external`，投影器同时
 维护 `question_labels(question_id, label)` 和 CSV 的 `Labels` 列。

---

## 4. 展示板 `boards.json`

路径：`错题/.omrs/boards.json`，当前 `version: 4`。展示板是呈现层引用集合，不进入 Ledger，也不
复制题目正文。文件写入会滚动 `.bak.1/2/3`，再使用临时文件、`fsync` 和
`os.replace` 原子替换。

文件顶层是 `{version, folders, boards, catalog_revision, mcp_receipts}`，当前为 v4；每板另有单调 `revision`。旧文件读取不落盘，实际写入才迁移，版本/回执的原子性见 `AI/mcp-storage.md`。`folders[]` 是单层（不嵌套）的展示板文件夹，每项为
`{id, name, order, created_at, updated_at}`，id 形如 `BF-20260907-a1b2c3`。板用 `folder_id`
指向所属文件夹，空串表示未归档；`order` 是它在组内的位置。读写时都会重新编号：文件夹按 `order`
排 0..n-1，板在组内排 0..n-1，因此顺序字段始终连续且无重复。

`folder_id` 指向不存在的文件夹时静默归入未归档，不报错也不丢板——文件夹是分类，坏掉的分类不该
连累数据。折叠状态属于 UI 状态，存在 `localStorage['omrs-board-folders-collapsed']`，不写进本文件。

板记录包含板元数据、打印设置和 `items[]`。每个条目同时保存
`question_id` 与 `uid`；读取优先稳定的 `question_id`，UID 只做显示和降级兜底。
停用题继续保留在板内但导出跳过；题目删除或无法按稳定身份解析时显示
`missing`，不会自动从板文件中删除。

### 4.1 版面设置 `print`

`normalize_print()` 的当前字段与取值范围：

| 字段 | 范围 | 说明 |
|---|---|---|
| `note_ratio` | 0.30–0.55 | 右侧留白占可分配宽度的比例，默认 0.50 |
| `gap_lines` | 0–24 | 板的**全局**题间留白行数（每行 18px） |
| `answers` | `none` \| `append` | 是否在末页附答案 |
| `show_labels` / `show_meta` | bool | 题头是否显示标记 / 科目·难度 |
| `cut_line` | `none` \| `dash` \| `solid` | 每题留白末尾的裁切提示线，默认 `dash` |
| `cut_label` | bool | 切割线右端是否标「第 N 题止」，默认关 |
| `locked` | bool | 保护纸面版式；真实影响已印区域的版式/有效留白变更才重置，引用增删排序不重置，见 `board.md` §4.6 |

未知键忽略，缺失键回默认；旧的 `note_align`、`note_min_lines`、`note_pattern`、
`last_printed_page` 读取时直接丢弃。

### 4.2 每题留白：v2 `extra_gap_lines` → v3 `gap_lines`

v2 的语义是「全局 + 每题额外」，v3 改成**每题绝对行数**：

- `items[].gap_lines = null` → 继承板的全局 `print.gap_lines`；
- `items[].gap_lines = 数字` → 这道题之后固定留这么多行，上限 `MAX_GAP_LINES = 48`。

迁移在 `_normalize_item()` 里就地完成，不需要单独的迁移脚本：读到 v2 的
`extra_gap_lines`（先夹到 0–24）时折算成 `全局 + 额外`，因此**迁移前后每题的有效留白逐题等值，
纸面像素不变**。折算后 `extra_gap_lines` 恒为 0，只读不写，所以重复归一化是空操作——
`load → save → load` 的结果与一次 `load` 完全相同（`tests/test_boards.py`
的 `BoardGapMigrationTests` 逐条锁住这两点）。

`extra_gap_lines == 0` 的条目不折算，保持 `gap_lines = null`（继承），避免把「没设过」
写死成一个具体数字。读不懂的 `gap_lines`（`"x"`、NaN）同样按「没设」处理而不是折成 0：
0 是「这题后面不留白」的真实选择，把坏数据折成 0 会静默改掉纸面。

`update_board(items=…, print=…)` 同一请求里同时提交两者时，`print` 先生效，
`items` 的 v2 折算用的是**本次请求之后**的全局留白，不会用旧值折算出错值。

`effective_gap_lines(item, print)` 是「这道题实际留几行」的唯一算式，服务端与前端
（`boardEffectiveGap`）必须同解；导出时由 `_board_gap_lines()` 落成绝对值交给浏览器模板，
导出数据里**不再出现** `extra_gap_lines`。

### 4.3 纸面记录 `printed`

`printed` 描述**纸上现在有什么**：`pages`（已打印总页数）、`cursor{page,y}`
（下一道新题的续排位置）、打印时的 `print` 几何、`items[]`（每题 `question_id / uid /
hash`（正文指纹）/ `segments[{page,top,height}]`）和 `answer_pages`。`print` 是实际排版时的
几何快照，其中 `note_ratio / gap_lines` 是仅新增续排的权威比例与留白；它不因板当前设置变化而
被覆盖。`pages == 0` 表示没有记录；由 `POST /api/board/printed` 在用户「标记为已打印」时写入，
`mode:"all"` 优先采用导出模板回传的 `layout.print`，缺失时兼容回退当前板 `print`；`mode:"new"`
追加题目但保留原 `printed.print` 快照。`hash` 优先沿用导出时回传的 `layout.items[].hash`，旧导出件缺失时才读取记录时的正文指纹。设计见 `board.md` §4。

纸面记录独立于板的引用集合：追加、去重、移出、清空引用、排序和未打印题留白更新都保留完整记录。已印题从板移除仍保留旧占位；重新加入同一稳定 `question_id` 不重复打印，后续新增题号仍按纸面记录中的题数续接，不按当前板内题数计算。

记录入口会拒绝无法解析或与板内 / 既有纸面不一致的题目身份，且所有段页码、答案页码和续排页码都必须不超过 `pages`；`mode:"new"` 不能在空纸面上建立伪基线。

### 4.4 纸面历史 `boards_printed_history.jsonl`

路径：`错题/.omrs/boards_printed_history.jsonl`，一行一条 JSON，**只增不改**。
记录纸面（`record_printed`）与重置纸面（`reset_printed`，包括锁定版式真实变更触发的重置）会在覆盖之前，追加旧纸面的**摘要**：页数、题数、cursor 和设置。没有逐题 `items/segments/hash`，不能据此直接恢复完整纸面；完整占位必须从 `boards.json` 或其备份核验，恢复时还需保留后续新增引用。

```json
{"at":"2026-09-09T04:00:00+00:00","board_id":"BD-…","board_name":"考前速览",
 "event":"record","mode":"all","pages":3,"count":12,
 "cursor":{"page":3,"y":493.56},"print":{"note_ratio":0.50,"…":"当时的版面"}}
```

- `event ∈ {record, reset}`；`mode` 只在 `record` 时有值（`all` / `new`）。
- 旧纸面为空（`pages <= 0`）时没有可留存的历史，跳过——所以**第一次**「标记为已打印」
  不会产生任何一行。
- 展示板不进 Ledger，这份 jsonl 是审计辅助而不是事实链；写失败只记运行日志
  （`board_printed_history_failed`），绝不打断打印记录本身。
- `read_printed_history(vault, board_id="", limit=20)` 按时间**倒序**读回，可按板过滤；
  文件不存在返回空列表，坏行跳过不报错。**目前没有 UI 也没有 HTTP 端点**读它，
  只能直接读文件或在 Python 里调用。

备份整个 `错题/` 目录时，`labels.json`、`boards.json` 和 `boards_printed_history.jsonl`
都随 `.omrs/` 一起进入备份。

## 5. 对话库 `agent.db`

路径：`错题/.omrs/agent.db`（SQLite，随备份导出，不进 Ledger）。表：`conversations`（对话，软删除）、`messages`（按 OpenAI 格式存的会话消息，用于重放模型上下文）、`runs`（每次运行的状态、结束原因、统计、合并后的事件、撤销信息）、`tool_calls`（参数、用户决定、结果、产生的 commit）、`practice_cards`（按工具调用保存结构化卡片和稳定题序）、`practice_attempts`（签发的 attempt、唯一重练请求标识及界面进度）。后两表不保存正式 Session 或反馈事实，反馈仍在 Ledger；字段与读写规则见 `AI/agent.md` §8。模型请求日志（开关打开时）在 `错题/.omrs/logs/agent-llm.jsonl`，含题目内容，不含密钥。

`run_events(run_id, seq, event_type, event_json)` 按运行与序号持久保存事件，分页读取保持跨完成与重启稳定。旧 `runs.events_json` 在迁移到事件表后置为 `[]`；活动尾缓存有界，完成运行落盘后移出内存。`round.end` 和 `usage.aux` 保留原归属及归一化用量，新增用量字段保留 `null` 表示供应商未返回；页面以事件按请求重放为准。

## 6. 框选标注集 `错题/.omrs/annotate/`

独立于收件箱的训练数据，由 `omrs/annotate.py` 读写，不进 Ledger、不参与任何投影。`annotate.db` 只有一张 `images` 表：`id (AN-YYYYMMDD-xxxxxx)、sha256（唯一）、file（上传时的文件名）、mime、width、height、bytes、status (todo|done)、boxes（JSON 数组 [{role, x, y, w, h}]，role 为 question / answer，坐标归一化 0–1）、revision、uploaded_at、updated_at`。旧库缺 `revision` 时幂等补列，保存与删除按预期版本检查，保存成功递增。原图在 `images/<sha256>.<ext>`，删除记录时一并删除。整个目录随设置页「备份导出」打包（备份遍历整个 `错题/`），图片压缩优化只处理附件目录，不碰这里。

## 7. AI 草稿存储

`draft_manual_edits` 表按 `(draft_id,target)` 记录人工编辑过的字段或块，供 AI 修订工具在同一版本内保护人工内容；`events.jsonl` 的 `draft.ai_update` 记录 AI 修改的运行来源、旧新 revision 和实际变化。草稿存储不进入题目 Ledger。

`错题/.omrs/drafts/` 的 drafts.db 独立于 Ledger，包含 images、conv_images、drafts、blocks、draft_images、commit_operations、training_tasks、training_boxes、draft_jobs 与 cleanup_candidates；图片按 hash 保存，事件追加到 events.jsonl。JPEG 在计算 hash 前清除主图结束标记后的相册数据，缺尾时补标记，保留编码像素；旧文件只在读取为 data URL 时临时整理，不改写。revision、来源完整性、清理状态与训练任务 manual_override / force_crop 通过增量迁移添加。字段、来源恢复和入库恢复以 `AI/drafts.md` 为准；只有通过产生带 `_draft` 追溯信息的题目创建提交。


## 8. 外部训练目录与面板配置

`config.json` 的 `train_dir` 默认空串（读取 `~/omrs-train`）；`train_try_collect` 默认 false（实时测试成功后是否积累到标注集）。训练数据、权重和运行日志放在 Vault 外，不随题库备份，不进 Git。主程序仅以标准库读文件，不导入训练框架。

- datasets/版本/manifest.json：classes、counts（train/val/test/quarantine）、strip_counts、samples、excluded、groups、splits；图片 ID 带 annotate/inbox 前缀，samples 保存 SHA-256、原始框与条带信息。测试图清单冻结到 test_ids.txt，重建沿用。
- runs/实验/status.json：state（running/done/failed）、epoch、epochs、started_at、updated_at、epoch_seconds、pid、dataset、可选 error；训练每轮临时文件加 os.replace 原子写入。进程消失或更新超时由面板派生 interrupted。
- runs/实验/metrics.jsonl：每轮一行，epoch、epoch_seconds、train/box_loss、train/cls_loss、val/box_loss、val/cls_loss、metrics/mAP50(B)、metrics/mAP50-95(B)；忽略最后未写完的一行，按轮次去重排序。
- runs/实验/eval.json：dataset、split、manifest_sha256、template/model 汇总、逐图 rows/template_rows、overlays（name/id）；overlays/ 下 JPEG 叠加图必须在清单中登记才可经接口读取。
- models/current/model.onnx 与 model.json：固定模型与 name、run、created_at、sha256、bytes、classes、imgsz、conf、dataset 元数据；训练不会隐式修改已发布模型。

面板只读目录为空时返回空状态，各文件解析错误各自报告。配置保存继续使用 `/api/config`；不提供网页训练控制。续训命令从原实验 identity.json 取参数，恢复前训练脚本检查数据清单和参数指纹。

实时测试默认只在内存中运行。积累开启后调用现有 annotate 模块写原图与模型框，status 保持 todo；重复 SHA 只提示已有，不更新框。完成标注前不进入默认导出和训练数据集，不增加任何数据表或来源字段。单图 15 MB／4000 万像素与每进程单并发限制用于约束内存。

面板生成的构建与开始训练命令采用未占用的新版本／实验目录；续训沿用旧目录和 identity 参数。评估命令只评估，导出与发布各自显式执行，网页只展示训练命令；受管服务切换使用下述独立映射。

### 内容评测产物与复核存储

外部训练根目录的 audits/评测/audit.json 保存数据集和manifest哈希、样本/分组/用途、检测模型与权重哈希、阈值、提示词版本/哈希、参数、原图/裁图资源ID及坐标。images/仅保存登记图片；案例JSON与attempts/每次响应只允许首次写入，不覆盖原判；progress.json为可恢复的进度快照。缺框也有案例，不从指标分母排除。历史校准导入保留原响应和各轮参数，不作为独立验收。

reviews.sqlite3 的 reviews 表以(audit,case_id,revision)为主键，追加action/verdict/note/source/created_at；source为user或executor。用户结论优先于执行者，未复核项仍沿用原判。该库与训练产物不进入题库备份、不修改标注框。audit-cache/按图/提示/模型/请求参数及渠道指纹保存成功调用；content-round-1.json记录整个实验轮次的实际请求次数、参考费用和未知usage次数，请求前持久计数。

内容数据快照保留全部旧train/val/test归属；test用途标为historical_regression，全新分组才可进入independent。相近验证/测试新图隔离，桥接不同冻结集合拒绝构建。草稿框只读chat_training_boxes，接受人工或人工编辑来源；同SHA相同标签去重，冲突标签排除。困难加权快照只从同manifest的train评测读取已复核错误，记录复核证据；不修改旧数据版本。

### 受管服务目录

`<训练根>/managed/snapshots/<元数据哈希>/` 保存经过 SHA 验证的 model.onnx/model.json 副本；active 为原子替换的相对符号链接。state.json 保存 revision、current、previous、operation；operations/请求ID.json 保存幂等请求、前后模型 SHA、服务端认证方式/会话 ID/可信来源 IP、候选的独立验收状态与人工确认、时刻、运行状态、错误和回退错误，不记录 PIN/Cookie，也不把共享 PIN 会话认定为具体人。events.jsonl 追加完成或恢复事件。状态与请求快照用临时文件加原子替换写入，operation.lock 用 flock 串行化，预检/重启还与 training.lock 互斥。运行中的请求记录允许更新到终态，追加事件不会改写。

受管映射不跟随models/current；初始化只由部署者执行bootstrap_control.py且拒绝覆盖已有state。只发现有export.json、identity.json、eval.json及匹配权重/ONNX哈希的实验。删除或修改实验不会改变已复制的在线模型。独立训练目录仍需单独备份，不随题库备份。

## 9. 系统运行记录 `runtime.db`

`错题/.omrs/runtime.db` 独立保存 MCP 工具调用，首次调用才建库；读接口只读，学习修正与状态还原不影响调用事实。存储字段、白名单摘要、生命周期、启动中断恢复与草稿关联统一见 `AI/runtime.md`。

## 10. MCP 技术存储

报告/草稿/展示板幂等回执、独立确认库与限时导出快照的字段、权限和恢复统一见 `AI/mcp-storage.md`；它们不进入学习 Ledger。
