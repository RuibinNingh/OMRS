# AI 录题与草稿区：P2–P4 多智能体执行说明

> 执行者：Codex 主控 + 3 个执行智能体，全部为完整模式。执行智能体统一使用 **GPT‑6 Sol / xhigh**（工具参数 `model="gpt-6-sol"`、`reasoning_effort="xhigh"`）。主控也采用同一模型与强度；当前会话不能自行切换主控模型时，开工前如实报告。
>
> 规划基线：`2bb401c`，v1.29.0。本文只制定执行计划，尚未启动智能体、实现功能或部署。执行入口是本文件；P1 执行说明保留作历史依据。

## 1. 任务目标

把已经完成的 P1 接成完整流程：聊天截图建草稿 → 用户审核、编辑、入库 → 手动框选与可控的训练数据登记 → 按设置自动框选。先完成 P2 的用户主路径，再连续完成 P3、P4；每期是集成检查点，不是默认停止点。生产部署另行授权。

用户本次原话：

| 编号 | 原话 | 分类与落实 |
|---|---|---|
| U16 | “AI 录题与草稿区  我要推进,你做一个计划,这个计划的目的是为了等会执行委派几个智能体一起干活,模型是GPT 6 Sol Xhigh” | 明确要求：本轮只写计划；后续多智能体执行，指定模型与强度 |

历史原话逐条保留在 `plan.md` §0 的 U1–U15，不用技术分解替换原话。本文 §2、§5、§6 是落实 U2–U14 的依赖与边界；§3、§8 对应用户可见结果；§4、§9、§10 对应 U16 的协作与交付。P1 已完成部分只回归，不重做。没有额外的可选功能混入主线。

## 2. 当前背景与约束

### 2.1 必读规范

- `AGENTS.md`：完整模式、按执行说明执行、防漂移、文档收尾与源码到文档映射。
- `AI/README.md`：按任务找文档、维护规则；`AI/plans/README.md`：状态与执行说明维护约定。
- `progress.md`、`plan.md` §0、§2–§7。
- 后端：`AI/drafts.md` 全文、`AI/agent.md` §1–§4、`AI/api.md` 草稿及并发写锁部分、`AI/data.md` 配置与存储、`AI/ledger.md` 写入来源、`AI/security.md` 请求与工具权限。
- 页面：`AI/frontend/create.md`、`AI/frontend/assistant.md`、`AI/frontend/settings.md` 相关分区；`AI/frontend/architecture.md` 页面生命周期、路由与 bus；`AI/frontend/design-system.md` 门禁。
- 框选：`AI/inbox.md` §3–§8、`AI/environment.md` 隔离实例与浏览器配方。

### 2.2 已核对事实

以下“代码核对”表示已经读到实现，“实测”表示本轮实际执行；不把推断当作完成状态。

| 事实 | 证据与影响 |
|---|---|
| P1 已在本机提交，HEAD 为 `2bb401c`；工作区原有未跟踪 `.playwright-mcp/` | Git 实测；保留该目录，不提交或清理它 |
| 当前只有草稿四个 GET，没有 update / commit / discard 写路由 | 代码核对：`omrs/server.py::_drafts_get`，`omrs/drafts.py`；P2 需要完整写闭环 |
| 全文字草稿传入 `images` 后，草稿本身未保存来源图集合 | 临时 Vault 实测 `create_draft_tool`：文本块 `image_sha=None`，只有 images / conv_images / drafts / blocks 四表；P3/P4 的全文字训练和共用图判断不能只查 blocks |
| 草稿块已有归一化 box、box_origin、ai_box，但建草稿不会填框 | 代码核对：`_row_block`、`create_draft`；P2 整图框可复用字段 |
| `create_question` 无 `_draft` 来源参数，按“全部文字、全部图片”组装每节 | 代码核对及 `_section_body` 实测；必须增加向后兼容的内部入口来保留图文块顺序 |
| 创建题目会写 Markdown、附件、Ledger，再重建投影；异常分支会删文件 | 代码核对：`omrs/creation.py`；跨存储恢复必须区分 Ledger 提交前后，不能承诺天然原子 |
| `build_registry(settings)` 尚未使用 settings；确认只绑定工具参数 | 代码核对：工具注册表、policy、runtime.Hooks；草稿版本必须进入确认参数，执行时复验 |
| 画布写死收件箱原图 URL 和若干 DOM id | 代码核对：`process-canvas.js`；复用需要可选参数，不能直接给草稿传一个收件箱 id |
| 收件箱所有 `ready` 题卡都会进入待录入队列；上传还可能自动 detect | 代码核对：`cards-state.js::readyCards`、`inbox.upload_images`；训练登记必须单独入口、显式隔离 |
| 助手已有 create_draft 卡片，但状态来自历史工具结果，结束的运行按 data-hash 跳过渲染 | 代码核对：助手 view / tools-view；需叠加当前草稿状态与版本失效 |
| 路由接受 query 的解析形式，但 go/start 会规范化为纯页面 hash | 代码核对：`core/router.js`；不把 `#/create?draft=...` 当作已可用的跳转协议 |

规划期基线测试的实际结果见本次任务日志与 progress；执行期仍须复核，因为后续代码可能变化。生产仍运行哪个 release、真实视觉模型是否可用，本轮没有验证；不把旧进度里的部署记录当成本轮实测。

### 2.3 硬约束

草稿不进 Ledger；仅入库产生题目提交。AI 不获得修改 / 丢弃草稿工具，错因原话校验继续保留。作业帮收件箱、快速录入与独立标注页的用户流程保持。只复用已有原生模块、UI 组件和框选逻辑，不换框架、不增加必装 Pillow。

测试只用临时 Vault 与随机高端口，移除 `OMRS_SYSTEMD_SERVICE`。不读取真实 `错题/` 或其中密钥。推送、生产重启、systemd/Nginx 变更不在本次执行授权中。

## 3. 最终预期行为

### 3.1 P2：审核入库先可用

录入页增加「AI 草稿」工作区。默认展示 cropping / review，切换可看 done / discarded；显示科目、分类、摘要、状态。草稿详情可以编辑科目、分类、难度、知识点、标记、错因、备注，以及按题目 / 答案分组的有序文字或图片块；来源截图可预览。复用现有字段和 Markdown 预览能力，不创建第二套组件。

编辑采用显式「保存」。切换草稿、工作区或页面前，对未保存内容提供保存 / 放弃 / 留在当前的选择；浏览器关闭用原生离开保护。「通过」先保存，再提交已保存的版本。网络失败保留表单；409 不覆盖用户本地编辑，提示重新读取后核对。done / discarded 内容只读，done 显示题目入口。

P2 的图片块提供「使用整图」，显式写入 `{x:0,y:0,w:1,h:1}` 后才可入库；有未框的图片块禁用通过并说明原因。P3 再加入精细框选。草稿区通过只写一次题目，点丢弃不写 Ledger、不立即删原图。

侧栏录入入口与工作区的待审核数量统一为 cropping + review，0 时隐藏侧栏角标。助手卡片有「查看草稿」，跳到该草稿；入库、丢弃后卡片更新，不继续显示历史待审核状态。助手关闭也能从录入页审核已有草稿。

设置「AI 录题方式」默认 silent。silent 只建草稿；confirm 才向主 AI 注册 `commit_draft`，只可申请提交本对话的 review 草稿，用户明确点允许后才入库；拒绝、过期、中止保留草稿。

### 3.2 P3：框选与训练数据

同一份草稿可逐张查看来源截图，用现有画布手动画框、移动、缩放、删框，选择题目 / 答案与留图 / 转文字。转换失败保持原图块与框，不破坏已有文字；成功后替换对应块，保留来源与训练框。按块顺序生成题目 Markdown。

框选方式提供 ask / manual；ask 在卡片显示「我来框」，manual 等用户去草稿区处理。训练开关按来源图设置，初始使用 `draft_train_default=false`。只有用户开启且完成有效框的图才可登记数据集；训练关闭的聊天图不新增收件箱记录。入库不以训练登记成功为前提，失败可重试且不重复建题。

训练图以 `source=chat`、`layout=other` 登记，进入统计与导出，不能出现在上传 / 处理 / 待录入队列，不能再次生成题卡。清理超期丢弃草稿时保护其他草稿、聊天与训练数据仍在使用的原图。

### 3.3 P4：自动框选

设置支持 ask / auto / manual；ask 增加「AI 框」按钮，auto 对新建草稿的可处理来源图自动调当前 detect 提供方，manual 不调用。每次检测都检查共用图与人工框：两份及以上未丢弃草稿共用的图直接转人工，已有人工作框的图不自动覆盖。检测失败或结果有歧义时显示原因，保留草稿供手工处理。

开启 `draft_force_crop` 后，全文字草稿也有独立的训练框选任务；不把文字块改成图片，不因训练任务未完成阻止入库。已入库后仍能完成这些训练任务，题目正文保持只读。AI 训练统计增加 chat 来源信息。这里不训练模型，也不开发检测服务。

## 4. 实施计划与委派

### 4.1 角色与文件所有权

同时最多 4 个智能体：主控 + A/B/C。三名执行者各保留一个角色，分期复用，不再向下递归开智能体。用户说开始执行后才创建；本轮规划不创建。

| 角色 | 职责与独占范围 | 验证责任 |
|---|---|---|
| 主控 | 契约复核、任务分派、集成与最终审查；`omrs_dashboard.html`、`assets/app/main.js`、`shell.js`、`styles/index.css`、必要的 core/domain 共享接线；全部 `AI/` 文档、根 README、版本文件、路由及日志生成器 | 综合门禁、视觉对比、提交；复查权限、失败恢复与实际浏览器主路径 |
| A 后端 | `omrs/drafts.py`、拟新增 `omrs/draft_*.py` 辅助模块、`omrs/creation.py`、`omrs/inbox.py`、`omrs/server.py`、`omrs/common.py`；仅必要时改 locking / ai_assist；`tests/test_drafts.py`、拟新增草稿写入 / 框选测试、相关 creation/inbox 回归 | 存储迁移、HTTP、来源、重复提交、失败注入、训练登记与清理 |
| B 草稿工作区 | `assets/app/features/create/` 内的草稿功能及画布适配，拟新增 `drafts*.js/css`；原有工作区入口 state/view/index；草稿相关 Node 测试、`tests/e2e/create.py`、拟新增 `tests/e2e/drafts.py` | 审核、编辑、整图 / 手动画框、转文字、训练开关、移动端与旧收件箱回归 |
| C 助手与设置 | `omrs/agent/` 内草稿工具、注册、配置投影、提示词及自动检测调度；`assets/app/features/assistant/`、`features/settings/`；相关 agent/assistant/settings 测试；`tests/fixtures/agent_faux.json`、`tests/e2e/assistant.py`、`settings.py` | 确认边界、动态工具、旧卡片刷新、模式设置、自动框选触发 |

`draft_*` 配置默认值与通用校验由 A 提供，`agent/config.py` 的 settings 投影由 C 接。`tests/check_docs.py` 的路由发现登记由主控做。B/C 均不得直接写 main/shell 或共同文档；先发接线需求与已核实的文档事实，主控统一落盘。新文件必须在派发消息里列为“拟新增”，不能误报为现成抽象。

同一文件一时只有一个写入者；需要越界修改时先交给所有者，或由主控显式转移所有权后再动。共用同一个开发工作区，不让多个智能体并行 git add/commit、切分支或生成文档索引。A/B/C 只实现与做各自验证，提交由主控串行完成。不同测试进程各用自己的临时 Vault、端口、输出目录；共享 Chrome 的测试串行安排。

### 4.2 阶段 0：开工复核与契约冻结

主控读 progress、Git 状态和最近 15 个提交，记录本轮实际基线。只读核对生产代码目录是否就是当前开发目录；如果是，先用应用 worktree 工具建立隔离 checkout。先检查已有任务附件，复用合适的活跃 worktree。不得在生产 Vault 中执行探测写入。

复核 §2 的事实、P1 回归和 §5 的字段 / 服务接口。API 的新增字段、状态、错误码、bus 事件与服务函数签名以本说明为约束；函数名可在派发前由主控一次确定并发给三方，不反复口头漂移。发现实现上的不同只记日志；影响目标或权限契约才停止报告。

派发时使用 `fork_turns="none"`，显式指定 `model="gpt-6-sol"`、`reasoning_effort="xhigh"`，带绝对工作目录、文件白名单、基线、本文路径和当前期验收。若工具不接受指定模型 / 强度，报告实际阻碍，不悄悄换模型。

### 4.3 P2：第一轮并行，端到端集成

1. A 实现草稿来源关联、revision、更新 / 丢弃 / 一次性入库及恢复；复用 create_question 并加入 `_draft` 与有序内容入口。先把服务签名与响应样例交给 B/C。
2. B 同时按冻结响应开发草稿列表、详情、表单、整图框、保存与通过。开发期可用测试替身，验收必须切真实 API。
3. C 同时实现 draft_mode、commit_draft 的确认预览 / 执行校验、卡片当前状态、查看草稿动作；提供主控需要的角标和跨页接线接口。
4. 三方进入集成后停止交叉编辑。主控接入口 / CSS / bus，跑审核与确认两条真实浏览器路径，审查重复提交和确认期间被编辑的用例。A/B/C 分别修自己范围的问题。
5. 主控同步文档、日志、progress，门禁全绿后提交一个完整 P2 垂直切片；版本按本计划统一在最终 P4 收尾更新。P2 完成即继续 P3。

### 4.4 P3：第二轮并行，框选与训练

依赖 P2 已集成的 revision、来源表和入库恢复协议。A 实现 boxes/extract/train、幂等数据集登记与引用安全清理；B 对画布做有默认值的适配、草稿框选 / 转文字和逐图开关；C 接 ask/manual、训练默认设置、卡片「我来框」。

主控审查“训练登记失败但题目已入库”“同图多个草稿”“丢弃后聊天仍能看图”三条跨模块路径。B 回归旧收件箱整套画布流程，A 验证 chat 图不会生成待录入题卡。同步文档与门禁后提交完整 P3 切片，继续 P4。

### 4.5 P4：第三轮并行，自动化与终检

A 实现 detect 服务、共用图判断、候选映射、全文字训练任务与来源统计；B 接检测结果、失败 / 歧义提示和已入库草稿的独立训练任务视图；C 接 auto 触发、ask 的「AI 框」、force_crop 设置与任务恢复触发。

慢模型调用放在草稿后台任务中，持锁只读快照与回写；服务重启后的未完成任务标为 interrupted，用户可重试，自动入库绝不绕过确认。主控验证全流程与终检，更新到 v1.30.0（若执行时此版本已被其他任务占用，则选下一个未占用 minor，并记日志），提交 P4 完整切片。执行终点是 P2–P4 验收通过、本地提交与文档齐全；推送 / 部署列为未执行。

### 4.6 单次派发模板

> 你是 AI 草稿计划的【A/B/C】，执行者为 Codex · 完整模式，模型 GPT‑6 Sol / xhigh。工作目录【绝对路径】，基线【哈希】。先读 AGENTS.md、AI/README.md、AI/plans/ai-draft/progress.md 与 exec-2026-09-28-parallel.md 的相关章节。本次只执行【P2/P3/P4】的【职责】，可写文件【白名单】，其余文件只读。遵守本文 §5 契约，不改执行说明、不部署、不 git commit、不自行启动下级智能体。报告修改文件、行为、实际测试结果、未验证项，以及需要主控 / 其他角色接线的内容。发现跨文件边界的需求先发消息，不能抢改。用户已有改动必须保留。

## 5. 关键技术决策

### 5.1 数据、迁移与并发

为 drafts 增加整数 `revision`，老草稿初始化为 1。所有内容 / 框 / 状态修改均在草稿事务内比较预期 revision 并加 1，秒级 updated_at 只用于展示，不当并发令牌。公开状态仍是 cropping / review / done / discarded；cropping 由是否存在缺框的 image 块推导。done / discarded 内容不可再改；训练任务有自己的生命周期，不改变已入库正文。

新增草稿—来源图关联（建议 `draft_images`：draft_id + image_sha 唯一，带来源顺序），保存 create_draft 的完整 images 参数，text 块也保留来源。新入参的所有图必须属于该对话。老草稿先从 image 块回填，再从匹配 conversation/run/tool_call 的已存工具参数精确恢复；找不到证据时只标“来源未完整恢复”，不把对话全部图猜成这道题的来源，不阻止纯文字入库。界面可让用户从该对话的已存截图明确补关联。

共用图判断使用关联表中状态非 discarded 的草稿，包含 done；旧数据来源不确定的图片不自动框。编辑块时保持稳定 block id，新块由服务端生成；ord 由提交数组顺序决定。框坐标只接受有限数值，`0≤x,y<1`、`w,h>0`、`x+w≤1`、`y+h≤1`。所有校验先完成再替换整份字段 / 块，失败不部分保存。

后台提取 / 检测按草稿 revision 与图 / 框快照回写；请求期间用户编辑或丢弃，旧结果标为 conflict，不覆盖新内容。HTTP、工具与后台任务使用同一领域层，锁顺序为全局写锁 → drafts 锁 → 必要的 inbox 锁；模型请求、确认等待和图片网络处理期间不持有这些锁。create_draft 工具只登记自动检测任务，不能在现有 Hooks.execute 的全局写锁内直接调识图模型。

### 5.2 HTTP 契约

保持 P1 GET 包装：list 返回 `{status:"ok",drafts:[...]}`，item 返回 `{status:"ok",draft:{...}}`，counts 返回四态计数。草稿详情增加 revision、source_images、训练任务摘要；列表字段保留，不能把原来的 draft(s) 键改成 items。图片 URL 仍用受保护的 `/api/drafts/image?sha=`。

下表为新增协议，字段名在三方开工前固定。所有写接口沿用登录 / 同源检查；没有单独放宽本机或 agent 权限。

| 接口 | 请求 | 成功响应与约束 |
|---|---|---|
| POST `/api/drafts/update` | `{id,revision,fields,blocks,source_images?}` | `{status:"ok",draft}`；fields 白名单为 subject/category/difficulty/knowledge_points/labels/cause/note；blocks 整体覆盖，保留稳定 id；不接受客户端 status/uid/origin |
| POST `/api/drafts/discard` | `{id,revision}` | `{status:"ok",draft}`；仅 cropping/review 可丢弃；已 discarded 重试返回现状，done 返回 409 |
| POST `/api/drafts/commit` | `{id,revision,crops?:{block_id:dataURL}}` | `{status:"ok",draft,result,reused,training}`；result 含 uid/question_id/file_path；done 重试返回原结果，不再次写题；只有 review 可首次提交 |
| POST `/api/drafts/boxes` | `{id,revision,blocks?,training_boxes?}` | `{status:"ok",draft}`；正文块项为 `{id,box,box_origin,ai_box?}`；训练框项为 `{id?,task_id,section,box,box_origin,ai_box?}`；training_boxes 整体替换所指定任务的框，done 只允许训练框，不接受正文块 |
| POST `/api/drafts/extract` | `{id,revision,block_ids,crops?}` | `{status:"ok",job}`；异步，成功只替换快照匹配的目标块，失败保留原块 |
| POST `/api/drafts/image/train` | `{id,revision,sha,enabled}` | `{status:"ok",draft,image}`；sha 必须是该草稿来源图，enabled 必须布尔，图级共享设置的变化使相关活动草稿失效 |
| POST `/api/drafts/detect` | `{id,revision,sha?}` | `{status:"ok",job}`；强制复核来源、共享与人工框，不因手动点击就绕过共享跳过规则 |
| GET `/api/drafts/job?id=` | — | `{status:"ok",job}`；草稿任务独立于 agent run，状态 queued/running/done/error/conflict/interrupted，含逐图结果与错误 |
| POST `/api/drafts/cleanup` | `{}` | `{status:"ok",cleaned,retained}`；使用配置保留天数，仅清理已过期且无引用的临时产物；不接受任意路径 |

训练登记重试复用 commit：done 不建题，只重试尚未登记的已选训练图。详情的 `training_tasks` 每项至少含 `{id,image_sha,status,boxes,error}`，状态 pending/ready/registered/error；每图每草稿一个任务，框独立于正文 block。后台 job 是一次操作，训练 task 是持久工作项，不能混用 id。A 在 P3 开工前提供与这些字段一致的响应样例给 B/C。

新增写接口：非法字段 / 坐标 / 裁图 400，不存在 404，revision / 状态冲突 409，全局写锁忙 503；错误沿用 `{status:"error",msg,...}`，不让前端解析中文判断类型。冲突附当前 revision；不把失败回成 200。GET 的既有错误行为不作无关改造。新路由同步路由生成器的识别清单。

### 5.3 入库的一次性与内容顺序

手工提交来源 api；工具提交仍经 `agent_actor` 记 agent。创建提交的 payload 顶层增加 `_draft:{draft_id,conversation_id}`，在 append_commit 之前加入并参与哈希，不能事后改 Ledger。只使用草稿库里的字段，不接受 commit 请求覆盖科目、错因或来源。

向 creation 增加内部可选的有序节块 / 来源参数：草稿按 section 内的 ord 插入文字与保存后的图片引用；现有快速录入与收件箱不传新参数时输出不变。附图需完整预校验，不能沿用“坏 base64 静默跳过”导致用户丢图。整图直接复用原件；局部框优先服务端 Pillow，缺 Pillow 时页面提交 canvas 裁图。服务端核验类型、大小、block id、所用框版本；确认工具没有可用裁图条件时报“请先在草稿区通过”，不得把原图假装裁图。

不能用“SQLite 事务包住 create_question”冒充跨库原子。草稿入库保留持久操作记录，绑定 draft_id、revision、预留 question_id 与阶段；重试先检查已有 `_draft` 创建提交。Ledger 已追加但草稿没标 done 时，恢复原 uid 并补回草稿 / 投影，不能再次创建，也不能在投影失败时删掉已被 Ledger 引用的 Markdown 与附件。Ledger 之前失败只清理由该操作明确拥有的暂存产物，重试沿用操作身份。保持改动限于草稿创建所需的向后兼容入口，不重构全部 Ledger。

至少对“提交后响应丢失”“Ledger 后草稿更新失败”“投影失败”“进程重启后重试”做故障注入。若题目之后被撤销或归档，done 草稿显示题目当前不可用，不自动再建一题；恢复题目使用现有入口。

### 5.4 确认与配置

`draft_mode` 从持久配置投影到 agent settings，缺省 silent；仅 confirm 注册 commit_draft。工具参数至少为 `{draft_id,revision}`，get_draft 返回 revision。预览展示这版的文字、图片、错因、元数据；预览和执行各校验当前 mode、对话归属、review 状态与 revision。等待确认期间发生保存、框选或模式切换，旧允许不能提交新内容，工具返回失败，重新 get_draft 后重新申请确认。

人类在草稿表单填写错因不需要伪造历史聊天原话；保留 AI 建草稿时的原始 cause_statement 作为来源证据，人类编辑记录为人类操作。绝不放宽 create_draft 的用户原话校验。

配置键、默认值与枚举沿用总纲 §3.6，服务端拒绝错误类型 / 非法枚举。P3 尚无 auto 时兼容已有 auto 值按 manual 处理，P4 才正式启用。主控和执行智能体的 GPT‑6 Sol / xhigh 是开发协作模型，**不修改 OMRS 用户的 agent_model 或识图模型配置**。

### 5.5 页面状态与跨页接线

草稿前端存储独立于 inbox-store，不能把草稿伪装成收件箱 item 持久化。共用画布只接受适配后的展示数据、图片 URL、DOM id 前缀与回调；旧调用默认参数保持行为。保持 core → ui → domain → features 依赖方向；assistant 不直接 import create 页面。

跨页协议采用共享的轻量草稿导航状态加 bus：`drafts:open {id}` 先存目标再切 create，create 挂载后消费；已经挂载时也可消费，防止先发事件后订阅丢跳转。不要求新增深链接，刷新保留草稿选择可用按 id 的 sessionStorage，内容以 API 为准。`drafts:changed {ids}` 触发计数及可见卡片刷新。

卡片从服务端当前详情叠加展示，不重写历史工具事件。草稿内容 / 状态变化必须使已结束运行的渲染版本失效。启动、页面重新进入、窗口重新聚焦、建草稿 / 保存 / 入库 / 丢弃后重取计数；只有助手运行中或草稿后台任务活动时做短轮询，隐藏页面暂停，卸载清理监听与定时器。获取计数失败不能把上次成功数值强行变成 0；卡片获取失败显示可重试状态。

### 5.6 训练、自动框选与清理

来源图关联和训练标注分别存储：文字块被提取后，训练框仍保留原 section、坐标、box_origin、ai_box；P4 的纯训练框也放在独立任务 / 标注记录里，不能充当题目图片区。训练任务和作业状态采用增量 schema 迁移，不重建旧库。

训练登记不用 upload_images（避免 pending 与上传自动检测）。收件箱新增 `training_only` 标志，默认 false，chat 登记写 true；普通队列与 commit 入口均排除此类 item，数据集统计 / 导出显式包含。保持总纲要求的 ready/other/chat；只排除 source=chat 不够，因为之后可能有其他来源用途。登记按图 hash 幂等，稳定 region id 由草稿 / 训练标注身份派生，共用图追加不同草稿的框，不覆盖人工框。

若同 hash 已是用户普通收件箱条目，不把它转成 training_only，不改变其状态 / 版式 / 原框；通过单独的聊天训练关联保留来源和新增标注，统计与导出按图去重。训练关闭表示本流程不新增登记，不删除用户原本上传的数据。已成功登记的图在草稿界面显示“已登记”，开关只读；本期不引入撤回数据集功能。未登记的图共享设置，UI 提示会影响其他草稿。

检测复用现有提供方与 parse/merge 逻辑，但不先上传收件箱；默认 `layout=other`，长图遵循现有切片规则。仅对能明确匹配 section 的待框 image 块自动应用候选；多候选 / 数量不匹配保留建议让用户选，不能猜框并入库。ai_box 保留最初建议，用户移动后 origin=ai_edited。共用图、已有人工作框、旧任务重试均需在回写前再检验；每个图 / 草稿版本最多一个活动任务。

force_crop 只在创建草稿时按当时配置生成任务，开启开关不追溯扫描全部历史；旧草稿可从详情手动发起。只有题目已入库且训练框完成的图才登记；先入库后补框，在保存有效训练框后自动登记，失败仍可重试。无图纯文字草稿不生成虚构任务。

丢弃满 `draft_discard_keep_days` 后可清理该草稿的临时裁图、草稿图片关联；原图必须确认没有活动或已入库草稿、存活聊天消息、训练关联引用后才能删。conv_images 不能因为丢弃一题就全部删除；done 题目附件是独立文件，永不被草稿清理删掉。清理入口在草稿区显式操作并在建草稿时作轻量过期清理，不新增 systemd 定时任务；失败记录事件，不影响建草稿。

## 6. 边界情况

| 场景 | 规定行为 |
|---|---|
| 空列表 / 列表请求失败 | 空态与失败重试区分；不把读取失败当作无草稿 |
| 题目有内容、答案为空 | 允许；题目无有效文字或图片块则不能保存 / 入库 |
| 保存失败后切页、快速点通过 | 保留编辑；同一草稿串行请求、按钮忙态；服务端仍用 revision 与持久操作记录兜底 |
| 两个标签页同时编辑 / 通过 | 至多一次入库；旧编辑 409，无静默覆盖 |
| 确认等待时编辑、丢弃、改模式 | 旧请求失效；不把新内容包含在旧确认里 |
| 图片缺失、裁图坏数据、无 Pillow | 报具体图 / 块；不静默丢图；页面 canvas 与整图路径可用，工具缺条件时保留草稿 |
| 一个图对应多题、同图在多对话出现 | 按 hash 管图、按草稿管块；跨对话不能冒用工具入库，共用图不能自动 detect |
| 一图题目框、另一图只有答案框 | 可登记训练，不能复用旧 ready 校验强迫每张训练图都有题目框 |
| detect/extract 后用户已编辑 | 返回 conflict，保留人工内容，可重新发起 |
| 题目成功、训练失败 | done + 可重试训练提示，后续重试只登记训练 |
| 重启遇到活动后台任务 / 入库操作 | 任务 interrupted；入库按持久记录恢复，不能自动再次执行用户已拒绝的确认 |
| 清理时其他草稿 / 聊天仍引用 | 保留原图，并报告仍被引用；不为“清理成功”删活数据 |

## 7. 修改范围

- **预计涉及：** §4 的文件与其直接测试；新增草稿存储辅助模块、工作区模块和专用测试须按各角色所有权创建；映射文档由主控同步。
- **明确不要修改：** 真实 `错题/`、生产配置、已有 `.playwright-mcp/`、无关未提交文件；不重写历史任务日志或 P1 执行说明。
- **本次执行必须完成：** P2–P4 用户流程与本文验收、向后兼容迁移、必要的来源 / 顺序 / 并发修补、文档与本地提交。本轮规划仅修改计划及文档，不实现这些功能。
- **可以顺手处理：** 本计划引用文档的已证实事实错误；为新草稿复用所必需的最小画布参数化；相关测试中写死“五个工作区”的断言。
- **本次不要处理：** AI 修改 / 丢弃草稿、回到聊天重写草稿、批量审题新功能、模型训练、local_http 服务、MCP、助手全局 B2 幂等、前端框架替换、收件箱流程重设计、生产发布。

## 8. 验收标准

| 编号 | 可检验结果 | 主要责任 |
|---|---|---|
| V1 | 假模型收两张截图创建一题，来源两图可见；纯文字草稿也保留来源；Ledger 数不变 | A/C |
| V2 | 在真实页面编辑 / 保存、整图或框选、通过后题库出现题目；图文顺序与预览一致，错因可由用户改，`_draft` 可追溯 | A/B |
| V3 | 丢弃只减少待审核数；done/discarded 不能改正文；刷新和重启状态仍在 | A/B |
| V4 | 并发点击、重试、响应丢失及故障恢复不会重复创建；Ledger 后失败不删有效文件 | A |
| V5 | silent 无 commit_draft；confirm 只允许本对话该版本，拒绝/超时/中止无创建；用户手工通过不在 agent 撤销中 | C/A |
| V6 | 卡片跳转准确，初次打开和已挂载都能选中；入库 / 丢弃后旧运行卡片和两处角标更新 | B/C/主控 |
| V7 | 手动框选、调整、转文字成功且失败保留内容；多图、手机触摸、切页回来正常；旧收件箱 E2E 通过 | B/A |
| V8 | 训练关闭不新增 inbox 图；开启并入库后数据集含正确 chat 标注，待处理/待创建队列无它；反复登记无重复 | A/B |
| V9 | 同图多草稿累积框而非覆盖；与既有普通收件箱图去重不改其状态；纯答案图也能导出 | A |
| V10 | 过期丢弃清理不删共享 / 聊天引用图、题目附件或训练图；原聊天缩略图仍可打开 | A/C |
| V11 | ask/auto/manual 各按设置触发；共享图与人工框不被自动改；空结果、错误与冲突有可操作提示 | A/B/C |
| V12 | force_crop 开时全文字题可先入库后补训练框，题目无多余裁图；关时无强制任务；无图不造任务 | A/B/C |
| V13 | 浅/深 × 桌面/手机真实浏览器无横向溢出、行内样式违规或新控制台异常；全量单测和规定门禁通过 | 主控 |

## 9. 验证步骤

先跑风险最高的领域 / HTTP 测试，再做真实页面。测试预期数量以本次实际输出为准，不能把规划基线 226 / 339 当作新增后的计数。任何故障注入只在临时 Vault。

每个切片集成时运行以下命令；本段 shell 变量只指本轮基线，不复用 HOME 等系统变量：

```bash
unset OMRS_SYSTEMD_SERVICE
python3 -m unittest discover -s tests -p 'test_*.py' -q
node --test tests/app/*.test.mjs
python3 tests/check_ui.py
python3 tests/check_contrast.py
python3 tests/app/run_browser.py
python3 tests/e2e/create.py
python3 tests/e2e/assistant.py
python3 tests/e2e/settings.py
python3 tests/e2e/drafts.py
python3 tests/e2e/shell_router.py
```

`tests/e2e/drafts.py` 是本计划要求 B 新增的用例入口，不是基线已存在文件。覆盖 V1–V12 中实际用户路径，假模型用现有脚本机制，extract/detect 用临时本地提供方或测试替身，不能用页面假响应代替最终服务联调。真实模型只在隔离配置中已提供凭据时测试；未提供则列明未验证，不从生产复制密钥、不伪称验证了识图质量。

页面手工 / 浏览器验收顺序：助手两张图建草稿 → 点卡片 → 修改、保存、通过 → 打开题目确认顺序 → 另一草稿丢弃 → 回助手核对卡片与角标 → 确认模式允许/拒绝/变更版本 → 精细框选及转文字 → 训练开关与导出 → auto / 共用图 / force_crop。检查页面错误与网络失败提示。浅深主题各跑桌面 1440 与手机 390；图片使用自行生成的数学 / 解析测试图，不需要用户上传截图。

终检补跑全部现有 E2E（包含独立标注页）。避免手抄遗漏，可串行执行：

```bash
for omrs_e2e in tests/e2e/*.py; do
  env -u OMRS_SYSTEMD_SERVICE python3 "$omrs_e2e" || exit 1
done
```

只在对应文件确有变化时重跑相关失败项；不因为“保险”无限重复已经通过的全套。视觉与文档收尾由主控串行执行，`OMRS_DRAFT_BASE` 在阶段 0 设为实际实现基线：

```bash
OMRS_DRAFT_BASE=2bb401c
env -u OMRS_SYSTEMD_SERVICE python3 tests/visual/run.py --ref "$OMRS_DRAFT_BASE" --out /tmp/omrs-ai-draft-visual
python3 tests/check_docs.py --write-routes
python3 tests/check_docs.py --write-log-index
git diff --name-status
python3 tests/check_docs.py --diff HEAD
```

视觉脚本默认页面截图未必进入新草稿工作区，必须同时保存专用 drafts E2E 的四档截图，不能拿默认上传页截图冒充草稿验收。每个提交之前对 HEAD 检查，提交后复核时对该提交父级；不对干净 HEAD 做“本任务已留日志”的证明。视觉差异逐项记任务日志。

## 10. 执行原则、停止与恢复

先读后改，以代码为准；复用现有抽象，不做无关重构。本文的目标、权限、数据契约与验收不能由执行智能体自行改变，实现细节的调整记日志。每期提交包含代码、相关测试、受影响文档、该逻辑任务日志和 progress；三方不争写收尾文件。版本变更只在 P4 最终提交同步全套版本落点。

只在以下情形暂停对应依赖工作并报告；其他情况持续推进，不问“要不要继续”：

1. 必须操作真实数据、推送或部署才能继续，而会话没有该项授权。
2. 工作区出现与本任务冲突且无法逐 hunk 判断归属的用户改动。
3. 实测证明本文目标 / 权限 / 契约无法成立，需要改变用户预期；普通实现难点不算此项。
4. 指定 GPT‑6 Sol / xhigh 不可用，不能按用户指定模型执行委派。
5. 必需验收环境不可用且安全替代方案已经查尽；保留完成工作、明确未验收项，不写“全绿”。

服务 / 真实模型凭据缺失不阻碍离线实现及假模型验证；生产部署未授权不阻碍本地完成。迁移失败只允许对本轮临时库排障，不对生产数据试错。框选共用图或检测失败属于预期回退，不是停止条件。

中断后恢复：读 Git 状态、最近 15 个提交、progress；状态块记录当前期、各角色已改文件、未集成事项、未执行门禁与下一步。活动角色的文件所有权先核对再续派，不能把同一文件重复交给两个智能体。每期完成后 progress 更新，下一期不重新询问授权。

最终用中文汇报：①提交哈希 / 版本 / 一句话内容；②已实际执行的验证及结果；③未执行的验证和原因；④遗留问题与不确定性；⑤下一步。主诉求未完成不得只交基础接口，也不得把 P2 完成写成整个计划完成。
