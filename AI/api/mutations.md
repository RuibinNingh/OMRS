# HTTP API：题目、反馈、配置与维护写入

> **速查**
> - 职责：题目、反馈、配置与维护写入的请求、响应及错误语义
> - 入口：`omrs/http/registry.py`、`omrs/http/` 领域适配
> - 不变量：统一鉴权、读取期限和生命周期边界见 `AI/api.md`；注册表是路由唯一来源
> - 必跑测试：`tests/test_http_boundaries.py`、`tests/test_security.py`
> - 相关：`AI/api.md`、`AI/routes.md`、`AI/security.md`

## POST 端点

所有 POST 在读取请求体前检查浏览器 `Origin` 与 `Sec-Fetch-Site`；跨站请求返回 403。非豁免远端请求还需 PIN 会话，本机无浏览器请求头的 CLI 调用保持可用。认证细节见 `AI/security.md`。

### `POST /api/scan`
执行一次工作区自检与投影更新，返回 `{status:"ok", count, scan}`；复用同一次扫描回执，不生成或轮转CSV。GET 不执行扫描。

### `POST /api/entry-background`
使用 `multipart/form-data` 保存入口锁屏背景。字段为 `mode`（`black-hole` / `custom`）、`style`（`gaussian-blur`）、`blur_px`（0–32）、可选 `asset_id`（复用已保存媒体）和可选 `file`（单个图片或视频）。服务端分块接收文件并按签名、声明 MIME、空文件和 200MB 上限校验；文件路径由服务端生成，拒绝 SVG、HTML、未知格式、路径穿越和类型不一致。选择黑洞不需要文件，切回黑洞会保留旧自定义文件但不会通过公共接口暴露。成功返回 `{status:"ok",entry_background}`；失败返回 400 `{status:"error",msg}`，配置和文件均保持原值。

### `POST /api/auth/login`、`/api/auth/logout`、`/api/auth/activity`
远端登录提交 `{pin}`，成功设置 `HttpOnly; SameSite=Strict` 会话 Cookie；退出清除会话。真实用户操作按分钟节流调用 `activity` 刷新空闲时间。`GET /api/auth/session` 可在登录前查询 `{instance_id, remote, authenticated, lan_pin_exempt, pin_configured, warning_required}`；免 PIN 网段直连时 `remote=true`、`authenticated=true`、`lan_pin_exempt=true`。

`instance_id` 是每个服务进程启动时随机生成的 32 位十六进制串，同一进程内不变、重启后改变，只用于判断服务是否已换成新实例；它不是凭据，不能用于授权或会话校验。

### `POST /api/auth/pin`、`/api/auth/disable`、`/api/auth/warning-ack`
`pin` 接受 `{pin, current_pin?, idle_minutes}`，新 PIN 为 4–12 位数字；只调空闲时间可省略 `pin`（尚未设置 PIN 时返回「请先设置 PIN」）。已设置 PIN 时，远端（含免 PIN 网段直连）修改须给正确的 `current_pin`，校验与登录共用每 IP 15 分钟 5 次的失败上限；尚未设置 PIN 时，免 PIN 网段设备可直接设置首个 PIN。更换 PIN 使全部远端会话失效；只改空闲时间不注销会话，新的空闲上限立即生效。停用 PIN 仅限本机且 `allow_external=false`。HTTP 提醒确认只记在当前会话。

### `POST /api/schedule`
创建常规 Session：追加 `session.create` Ledger commit，再重建并导出兼容投影 `sessions.csv`。

**请求体：**
```json
{ "subject": "数学", "count": 10 }
```
`subject` 可省略（全科）。

**响应：** Session 信息 + 题目列表。

---

### `POST /api/session/delete`
复习调度详情的「删除调度」入口调用此接口，追加 `session.retract` commit，不物理删除 Ledger 记录。待完成和已完成计划均可撤销；关联反馈整体退出有效投影，重新计算熟练度、复习日期与统计，题目正文保留。可通过历史记录恢复 Session。成功返回 `{"status":"ok","deleted":true}`；计划不存在时返回 HTTP 200 与 `{"status":"error","deleted":false}`，调用方必须检查业务字段。

**请求体：**
```json
{ "session_id": "EXP-20260422120000" }
```

---

### `POST /api/feedback`
提交本次练习反馈。在同一 SQLite 写事务中追加 `review.batch_submit` 并增量发布熟练度、EF、标签与 Session 的 SQL 投影；Markdown 历史不作为算法事实源，CSV 仅按需导出。

**请求体：**
```json
{
  "session_id": "EXP-20260422120000",
  "feedbacks": [
    { "uid": "三角函数1", "sub_score": 8, "is_correct": true, "source": "due", "note": "" }
  ]
}
```

`sub_score` 范围 0–10，越大越熟练。
`source` 可选，取值 `due` / `proficiency` / `instant` / `manual` / `legacy_unknown`。若 `session_id` 对应持久化 Session，则优先使用 Session 中保存的来源；无 Session 的即时练习可逐题传 `source` 以保留 SM-2 策略差异。

**响应：** 每条反馈的 `label`、`old_mastery`、`new_mastery`、`tag`、`source`、`new_interval`、`new_due_date`。

响应状态来自本次实际投影结果。服务端在写事务内核对活动参数及链头；其它进程已调参或追加事实时重建后重试，避免使用旧参数响应。投影发布失败时反馈事实一并回滚；已撤销的持久化 Session 拒绝新反馈。

聊天练习卡提交时，`session_id` 必须为服务端签发的 `IMM-<attempt_id>`，请求顶层另带 `attempt_id`，每条反馈带卡片的 `question_id` 与相同的 `entry_id`。服务端按稳定题目身份解析当前 UID、核对卡片及来源；`IMM-PA-*` 缺少 attempt 身份会拒绝。返回的 `results` 逐条标 `status:ok/error`，已落账重试返回 `ok`、`reused:true`，失败项不锁定。创建或打开卡片不写反馈；只有首次成功提交才增加 Attempts。

---

### `POST /api/create`

`question_images`/`answer_images` 中可用 `{upload_ref:"upl_..."}`；服务端验证所属操作者、用途、Vault 世代和过期时间。旧 data URL 保持兼容并在解析时逐图转成暂存引用。
创建题目 Markdown 文件。可只建骨架，也可直接写入完整内容（正文/答案/备注/图片）。

**请求体：**
```json
{
  "subject": "数学",
  "category": "三角函数",
  "difficulty": 6,
  "related_tags": ["二倍角公式"],
  "labels": ["考前必看"],
  "question_text": "题目正文（可选，含 LaTeX/多行）",
  "answer_text": "答案/解析（可选）",
  "cause": "错因（可选，写入 ## 错因）",
  "question_images": [{ "data": "data:image/png;base64,..." }],
  "answer_images":   [{ "data": "data:image/png;base64,..." }]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `subject` / `category` | string | 必填。科目 / 分类 |
| `difficulty` | int | 难度 1-10，默认 5 |
| `related_tags` | array | 相关知识点，写入 YAML `相关知识点` 为 `[[双链]]` |
| `labels` | array | 用户标记名称，写入 YAML `标记`；名称去重，默认空列表 |
| `question_text` | string | 题目正文，写入 `# 题目`；为空则写占位提示 |
| `answer_text` | string | 写入 `# 答案` |
| `cause` | string | 错因（为什么做错），写入 `# 备注` 的 `## 错因` 子标题（导出会带上）；`## 关联` 子标题保留 |
| `question_images` | array | 题目图：每项 `{data}`，存为 `<uid>-<omrs_id 短后缀>-q-N.<ext>`（如 `力学1-0135-q-1.png`），以 `![[名]]` 追加到 `# 题目` |
| `answer_images` | array | 答案图：每项 `{data}`，存为 `<uid>-<omrs_id 短后缀>-a-N.<ext>`，以 `![[名]]` 追加到 `# 答案` |

旧客户端仍传 `note` 时，服务端忽略它并在成功响应中返回 `deprecated_fields:["note"]`；新题不写入 YAML 页码。反馈 `note` 与草稿备注各有独立语义，不受影响。

**响应：** `{ "status":"ok", "uid", "file_path", "images":[全部], "question_images":[...], "answer_images":[...], "message" }`。
图片存到 `错题/附件/`；文件名含 UID 与 `_omrs_id` 短后缀，避免迁移后附件覆盖。建索引失败会回滚（删除本次 md 与已存图片）。图片服务仅支持 PNG/JPEG/GIF。

### `POST /api/label/save`
创建或更新用户标记定义。题目 Markdown 保存的是标记名称，不是定义的内部
`id`；更新名称时会级联重写所有引用题目的 YAML，并统一重建投影。

**请求体：**
```json
{
  "id": "LB-20260904-a1b2c3",
  "name": "考前必看",
  "color": "#dc2626",
  "priority_bonus": 0.3,
  "order": 1
}
```

- `id` 可省略；省略时创建新定义，提供时更新已有定义。
- `name` 必填且唯一，不能含换行或 `|`；`color` 归一化为 `#rrggbb`。
- `priority_bonus` 钳制到 `0–1`，默认 `0`；`order` 控制选择器顺序。

**响应：** `{"status":"ok","label":{...,"count":0,"affected":0}}`。更新名称时
`affected` 是实际改写题目数；没有改名时为 `0`。不存在或校验失败返回 HTTP 400。

### `POST /api/label/delete`
删除标记定义。默认先从所有题目的 YAML `标记:` 中移除该名称，再删除定义。

**请求体：**
```json
{ "id": "LB-20260904-a1b2c3", "detach": true }
```

`id` 也可传标记名称；`detach` 传 `false` 时保留题目中的旧名称引用。

**响应：** `{"status":"ok","deleted":true,"name":"考前必看","affected":12}`。
`affected` 是被解绑题目数。

### `POST /api/label/merge`
把一个标记合并到另一个标记。引用源标记的题目会保留其它标记，并去重后
改为目标标记；完成后删除源定义。

**请求体：**
```json
{ "from": "计算失误", "into": "考前必看" }
```

也兼容字段名 `source` / `target`。**响应：**
`{"status":"ok","merged":true,"from":"计算失误","into":"考前必看","affected":8}`。

### `POST /api/question/labels`
覆盖单道题目的用户标记。

**请求体：**
```json
{ "uid": "三角函数1", "labels": ["考前必看", "计算失误"] }
```

名称会去空白、去重；`labels: []` 表示显式清空。成功响应为
`{"status":"ok","uid":"三角函数1","labels":[...],"changed":true}`。有变化时会
重写 Markdown、追加 `question.metadata_update_external` 并重建投影；同样内容重复提交
不会产生新 commit。

### `POST /api/questions/labels`
批量给多道题添加或移除标记。

**请求体：**
```json
{
  "uids": ["三角函数1", "三角函数2"],
  "add": ["考前必看"],
  "remove": ["已打印"]
}
```

操作按题目逐条执行，`add` 与 `remove` 同时命中时以移除为准。**响应：**
`{"status":"ok","changed":2,"failed":[],"scan":{...}}`；`changed` 是实际发生
文件变化的题目数，失败项包含 `uid` 与 `msg`，所有成功改动完成后最多统一扫描一次。

### `POST /api/workspace/scan`
手动触发工作区自检。会检测正文变化、结构化 YAML 修改、文件移动/改名、新增 Markdown、文件消失和冲突。

### `GET /api/question/raw?uid=<uid>`
返回题目的完整 Markdown 原文与文件路径，用于纯文本编辑器。

### `POST /api/question/content/restore`
请求体 `{uid, hash, expected_content_hash?}`：只接受该活动题历史引用过的版本，并核对 blob 内容哈希与正文 `_omrs_id`；不符时不改 Markdown 或 Ledger。通过后写前对齐未入账的修改，写后记一条 `question.metadata_update` 或 `question.content_update`（payload 带 `restored_from`）。`expected_content_hash` 与文件当前正文不符返回 **409**；题目或版本不存在返回 400。

### `POST /api/question/markdown`
保存完整 Markdown 原文。

请求体：
```json
{ "uid": "三角函数1", "markdown": "---\n_omrs_id: OP-000001\n..." }
```

若用户试图修改 `_omrs_id`，后端拒绝保存。仅正文变化写 `question.content_update`；结构化字段变化写 `question.metadata_update`，前后 Markdown 版本随提交入账。


可选 `expected_content_hash`：写入方看到的正文哈希（`GET /api/question/raw` 与本接口的响应都带 `content_hash`），与文件当前正文不符时返回 **409**「题目正文已被修改，请刷新后重试」。保存经 `omrs/content_history.py` 写前对齐、原子写文件并入账（来源 `api`）。

### `POST /api/question/move`
迁移题目到目标分类，使用最小缺口 UID 分配算法。

请求体：
```json
{ "uid": "三角函数4", "subject": "数学", "category": "二次函数" }
```

> **访问边界：** 本机及显式豁免的局域网直连免 PIN；其他远端需登录。全部 POST 使用统一来源校验，见 `AI/security.md`。

### `POST /api/question/suspend`

停用题目但保留 Markdown 正文和所有历史。停用后题目不进入复习调度、统计、数据分析或导出；只追加 `question.suspend` Ledger commit。

请求体：
```json
{ "uid": "三角函数4", "reason": "暂不复习" }
```

成功响应：`{"status":"ok","uid":"三角函数4","suspended":true}`。重复停用返回 400。

### `POST /api/question/resume`

恢复已停用题目，保留原有熟练度、SM-2 排期和历史；只追加 `question.resume` Ledger commit。恢复后立即重新参与调度与统计。

请求体：
```json
{ "uid": "三角函数4", "reason": "恢复复习" }
```

成功响应：`{"status":"ok","uid":"三角函数4","suspended":false}`。未停用或不存在返回 400。

停用题目会从尚未完成的 Session API 题目列表和待反馈计数中排除；原始 Session 记录仍保留在 Ledger / sessions 投影中以便审计。若一个活动 Session 的题目全部已停用，则不再出现在活动 Session 管理列表。

### `POST /api/question/delete`

删除一个题目的 Markdown 正文，并追加 `question.archive` Ledger commit。请求体：

```json
{ "uid": "三角函数4" }
```

删除前核对文件身份，把当前 Markdown 存入 blob 并逐字确认可取回；失败不删除，归档提交失败则恢复文件。成功响应包含 `uid`、原 `file_path` 与 `archived: true`。题目会从题库、统计、调度和兼容 CSV 投影中移除，历史反馈和账本记录保留。附件图片不会自动删除，因为它们可能被其他题目引用；已归档正文可按题目历史查询和取回，但结构化恢复不重建 Markdown 文件。

### 历史修正端点

以下端点都只追加 commit，不修改旧记录：

- `POST /api/history/review/replace`
- `POST /api/history/review/retract`
- `POST /api/history/review/restore`
- `POST /api/history/session/retract`
- `POST /api/history/session/restore`
- `POST /api/history/state/restore`

提交前会校验目标：反馈修正要求 `target_commit_id` 指向 `review.batch_submit` 且 `target_review_index` 未越界；Session 修正要求该 Session 曾在 Ledger 中出现；`state.restore` 要求目标 `seq` 存在。校验失败返回 400，不追加脏 commit。

---

### `POST /api/ai-recognize`
用已配置的 OpenAI 兼容多模态模型识别一张图片，返回**自动填充建议**（不落库，纯识别）。对应源文件：`omrs/ai_assist.py`。

请求只用 user 角色：指令文本 + 图片（`image_url` 传 data URL）都放在 user 的 `content` 里（不设 System Message，符合 Qwen-VL 推荐用法）；协议为 `POST {ai_base_url}/chat/completions`，`Authorization: Bearer <key>`，由本地后端用标准库 `urllib` 转发（不经第三方、规避浏览器跨域）。

`ai_thinking` 控制 AI 识图请求的思考，默认 `false`。使用 `deepseek-flash` 时，所有识图用途按开关发送 `thinking:{type:"enabled"}` 或 `thinking:{type:"disabled"}`；其它模型不附此参数。该设置不改变 AI 助手主模型的思考配置。

**请求体：**
```json
{ "image": "data:image/png;base64,...", "mode": "classify", "subject": "数学", "category": "手拉手模型" }
```
`mode='classify'` 时可选带 `subject` / `category`（用户在表单里**已填**的值）：后端会把它们写进提示词并要求模型**原样沿用、不要改动**，据此判断难度与知识点。前端拿到结果后**只填空缺项、不覆盖已填的科目/分类**（知识点与已填的合并去重）。

快速录入额外传 `scope:"quick"`。该分支不向模型请求用户标记，也不返回 `labels` 或白名单外字段；识别结果只供当前图片和字段版本使用。分类结果可附 `cause_candidate:{value,evidence_text,source,requires_confirmation}`，证据仅是模型引用的题图文字，前端要求用户对照原图并主动采纳，不直接写错因。共享分类器的其他调用方仍保持既有标记能力。

是否把识别出的知识点限定在「已有分类 ∪ 已有知识点」内，由配置 `ai_restrict_tags`（默认 `true`，见设置页「AI 自动识别 → 仅从已有知识点中选择」开关）决定，**每次请求读盘、即时生效、无需重启**；该端点不接受 per-request 覆盖。

分类提示中的已有用户标记定义通过 `list_label_defs()` 读取，并排除已归档定义；该查询失败不会把旧版不存在的 `list_labels()` 当作替代 API。

| `mode` | 用途 | 提示词 | 返回 |
|---|---|---|---|
| `classify`（默认） | 读**题目**图，判断科目/分类/难度/相关知识点（不抄题、不解题） | 注入当前科目、按科目分组的分类树、知识点；要求先定科目，再只能从该科目下选分类，禁止跨科目借用分类；`ai_restrict_tags=true` 时要求 knowledge_tags **只能取自所选科目下的已有分类+已有知识点**，`false` 时**优先复用、无贴切项才可新建** | `{subject, category, difficulty, knowledge_tags, restrict_tags, raw}`；普通调用可带 `labels`，quick 分支不带 |
| `question_text` | 读**题目**图，把题干/条件/选项/图表说明提取为纯文本 | 要求只输出题目正文，不解题、不补答案/解析；若开头有题号，只去掉开头题号，正文内部编号保留 | `{question_text}` |
| `answer` | 读**答案**图，忠实转录全部可见答案与解析 | 保留详解、推导、计算步骤、选项说明、原顺序和必要换行；若开头是对应题号+答案/解析标题，只去掉该开头题号；禁止概括、压缩、省略或补写，只有图片确实没有解析时才只返回答案 | `{answer}` |

**响应：** `{ "status":"ok", "mode", ...上表字段 }`。
- `classify`：`difficulty` 夹在 1-10；`restrict_tags` 回传本次实际采用的开关值；若模型返回“已有分类但不属于所选科目”的组合，后端会清空 `category` 防止误填；`knowledge_tags` 在 `restrict_tags=true` 时由后端**硬过滤**为「所选科目下的已有分类 ∪ 已有知识点」的子集（模型若造新词一律剔除，空池则返回 `[]`），在 `false` 时仅归一化去重并**上限 4 个**（允许新词）；模型未按 JSON 返回时 `raw` 回传原文（前端可提示重试）。
- `question_text`：`question_text` 为去围栏、去掉开头题号后的题目正文纯文本，前端填入 `#cr-question`；只处理整段开头，不删除选项或正文内部编号。
- `answer`：`answer` 去掉包裹整段响应的代码围栏，并在开头为“题号+答案/解析标题”时去掉对应题号；模型返回的答案/解析正文、内部步骤编号及换行原样保留。
- 未配置 `ai_base_url/ai_api_key/ai_model`、网络不可达、上游 HTTP 错误或解析失败 → `{ "status":"error", "msg":"…" }` + 400。

---

### `POST /api/config`

活动配置来自 SQLite；保存可携 `expected_revision`，过期版本返回409。成功回执含 `revision` 与 `mirror_pending`，镜像失败不能冒充数据库回滚。tuning 变化在事务内重算历史并发布新投影。
更新服务配置。`save_config` 按键合并，故可单独提交任意子集。

`http_json_mib` 控制普通JSON及上传引用元数据，缺省2，接受1–8192的整数；`http_legacy_upload_mib` 控制旧图片JSON/multipart，缺省128，接受2–8192的整数。提交 `{ "http_json_mib": 3 }` 后后续普通正文采用3MiB上限；专用auth/MCP/训练/分块上限不受影响。候选配置统一校验，非法类型或越界返回400，活动配置保持原值。
启用 `allow_external` 需先设置 PIN 或配置 `lan_pin_exempt_cidrs`。网段必须是 RFC1918 IPv4 或 IPv6 ULA 中的规范 CIDR，最多 8 个；修改后立即生效。提交非空 `ai_api_key` 会替换密钥；省略或提交空串会保留旧值，明确清除须提交 `{ "clear_ai_api_key": true }`。

**请求体：**
```json
{ "allow_external": true }
```
保存 AI 配置（前端「设置 → AI 自动识别」用此，**无需重启**，因 `load_config` 每次读盘）：
```json
{ "ai_base_url": "https://api.openai.com/v1", "ai_api_key": "sk-...", "ai_model": "gpt-4o", "ai_restrict_tags": true }
```
（`ai_restrict_tags` 单独切换也可，例如只发 `{ "ai_restrict_tags": false }`。）

**响应：** `{ "status": "ok" }`

### `POST /api/restart`
触发程序重启。

后端会先返回响应。由 systemd 管理的实例通过 `systemctl restart --no-block omrs.service` 交给服务管理器重新拉起，避免主进程正常退出后 `Restart=on-failure` 将服务留在 stopped 状态；手工命令启动的实例仍使用关闭服务器、延迟 1.5 秒后启动新进程的回退路径。监听 socket 由 `omrs/cli.py::OMRSTCPServer` 创建并启用 `SO_REUSEADDR`（不启用 `SO_REUSEPORT`），旧连接处于 `TIME-WAIT` 时新进程可立即绑定；仍有进程在监听时照常报错。

客户端判断重启完成的方式：重启前读取 `GET /api/auth/session` 的 `instance_id`，之后轮询同一端点，直到 `instance_id` 改变。仅凭 200 不能判断，因为重启命令刚排队时旧进程仍会应答。

**响应：** `{ "status": "ok", "msg": "正在重启..." }`

### `POST /api/backup/export`
打包整个 `错题/` 目录并以 zip 下载，文件名 `OMRS-backup-YYYYMMDD-HHMMSS.zip`。响应头仍返回 `X-OMRS-Backup-Token` 供审计与兼容，但图片压缩不再强制要求先备份；备份 zip 不写入数据目录，由浏览器下载给用户保存。

### `POST /api/backup/import`
导入用户选择的备份 zip（原始ZIP、`multipart/form-data` 字段 `file`，或JSON `{upload_ref}`），只做校验和预览，不立即覆盖当前数据。

上传引用必须为backup用途，服务端以安全普通文件打开并在锁外分块复制、核对完成时的SHA256与长度，结束后再检查世代与有效期。同长度内容篡改返回400，不产生恢复预检；临时副本总会清理。

JSON引用元数据使用 `http_json_mib`（默认2MiB），声明超限即413且不读取正文或运行预检；原始ZIP和备份multipart保留8GiB传输上限。

**响应：** `{ "status":"ok", "restore_id", "preview": { "filename", "files", "bytes", "md_files", "image_files", "has_attachments" } }`

### `POST /api/backup/restore`
按 `restore_id` 恢复备份，恢复前后端会先在临时目录重建索引，验证通过后才替换当前 `错题/` 目录。

仅JSON布尔 `confirm:true` 允许执行恢复；字符串、数值、false或缺失确认返回400，当前题库与世代保持原值。

**请求体：**
```json
{ "restore_id": "restore-xxxx", "confirm": true }
```

**响应：** `{ "status":"ok", "restored":true, "question_count":155, "vault_generation", "reauth_required":true, "cleanup_pending":false }`。目录交换、启动恢复及回退协议见 `AI/backup.md`。

### `POST /api/optimize/scan`
启动图片快扫后台任务。快扫只枚举 `错题/附件/` 图片、统计格式与体积，并筛出可进入深扫压缩的范围；不会生成优化副本，也不会做像素校验。PNG 在 Pillow 可用时进入深扫范围；JPG/JPEG 仅在 `jpegtran` 可用时进入深扫范围；GIF/WebP/BMP 只统计跳过原因。

**响应：** `{ "status":"ok", "job": { "kind":"scan", "job_id", "total", "processed", "done" } }`。前端继续轮询 `/api/optimize/job?id=<job_id>`；完成后 `job.result` 含 `{ "exact": false, "scan_id", "candidate_count", "potential_bytes", "candidates", "skipped" }`。

### `POST /api/optimize/compress`
启动深扫压缩后台任务。必须显式 `confirm=true`；`backup_token` 为兼容保留的可选审计字段，可以为空。任务会逐张生成优化副本、校验 PNG 像素一致或调用 `jpegtran`，只在新文件更小时替换原文件。

**请求体：**
```json
{ "scan_id": "scan-xxxx", "backup_token": "", "confirm": true }
```

前端仍在确认框中建议用户先导出备份，但这不是后端前置条件。

**响应：** `{ "status":"ok", "job": { "job_id", "status", "total", "processed", "saved_bytes" } }`


### `POST /api/session/bind`

请求 `{session_id,entry_id,question_id}`，仅给 unresolved 条目追加绑定事实；不修改创建提交。成功返回 `{status:"ok",session}`，已绑定、无效身份或状态冲突返回409。

参数更新响应含实际发布版本、完整`tuning_effective`与持久`recalculation`回执；回执status为complete时已完成历史重算。镜像失败返回mirror_pending；第三方冲突另有mirror_conflict并保留两份内容。跨进程后续保存已覆盖本次版本时返回superseded及当前完整状态，不把旧镜像覆盖回新参数。设置页调参请求期限10分钟，断连通过只读配置核验，不凭默认超时宣称失败。


## MCP 正式计划创建

外部 create_review_session 直接调用受限 Session 领域操作，不转发 Web 请求、不开放 Web PIN 权限；与现有网页计划共用 session.create 事实和反馈投影。MCP 的稳定身份、幂等和权限契约见 AI/mcp.md §14，网页 /api/schedule 与 /api/confirm-schedule 行为保持。
