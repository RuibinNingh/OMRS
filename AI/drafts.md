# AI 草稿区（drafts）

> **速查**
> - 职责：主 AI 聊天里建的题目草稿的存储与只读查询；草稿独立于题库与 Ledger
> - 入口：`omrs/drafts.py`（存储 / 查询）、`omrs/server.py`（`_drafts_get`）
> - 不变量：草稿只进 `错题/.omrs/drafts/`，不写 Ledger、不收件箱、不出现题库；图片属于对话而不是草稿，模型只拿得到 `IMG-n` 这种编号，拿不到 sha 或路径
> - 必跑测试：`tests/test_drafts.py`
> - 相关：`AI/agent.md`（工具层 `create_draft` / `describe_image`）、`AI/inbox.md`（图片头解析复用）、`AI/api.md`

> 对应源文件：`omrs/drafts.py`（四张表、图片去重与对话编号、转述缓存、草稿校验）、`omrs/server.py`（`_drafts_get` 只读路由）。

## 1. 它解决什么

用户在主 AI 助手里贴作业截图，说「录一下这道题」，主 AI 把题目、答案、错因整理成一份**草稿**暂存下来，等用户在草稿区核对、框选、再决定入库。草稿不是题目：它不进 Ledger、不进收件箱、不进题库，删掉或丢弃都不留痕。

本模块是草稿区的**存储层**，配套的 `/api/drafts/*` 只读接口也在这一期落地。写接口（入库、框选、丢弃、更新）属于后续阶段，见 `AI/plans/ai-draft/plan.md`。

## 2. 存储 `错题/.omrs/drafts/`

```
drafts.db             SQLite：images / conv_images / drafts / blocks
images/<sha256>.<ext> 聊天里贴的图片原件，按内容哈希命名 → 同一张图只存一份
events.jsonl          append-only 事件：image.add / image.transcribe / draft.create
```

**图片属于对话，不属于草稿。** `images` 一行一张图（`sha256` 主键、`mime / width / height / bytes`，另有 `transcript`、`transcript_model`、`train`、`inbox_item_id` 给后续阶段用）；`conv_images(conversation_id, n, sha256, run_id)` 记这张图在某个对话里叫 `IMG-n`。每个对话从 1 开始连续编号，同一对话里重复贴同一张图沿用旧编号（按 `conversation_id + sha256` 查得到就不再分配）。编号对用户和模型都可见，是工具参数引用图片的唯一方式。转述缓存按 `sha256 + 模型名` 取用：模型名对不上当作没缓存。

`drafts` 一行一份草稿：`id (DR-YYYYMMDD-xxxxxx)`、`status`、来源 `conversation_id / run_id / tool_call_id`、`subject`、`category`、`knowledge_points (JSON)`、`difficulty`（固定 5，标记不由 AI 填）、`labels (JSON)`、`cause`、`cause_statement`、`note`、`uid`、`question_id`（入库后回填）、`created_at`、`updated_at`。

`blocks` 按 `draft_id` 分组、按 `ord` 排序，`section` 为「题目」或「答案」，`kind` 为 `text`（`text` 存正文）或 `image`（`image_sha` 引用某张图，`note` 说明位置）；框选列 `x y w h`、`box_origin`、`ai_box` 这一期恒为空，后续阶段补。

`status` 四态：`cropping`（有图片块、还没框选）、`review`（全是文字块、待人审）、`done`、`discarded`。**由块推导**：建草稿时有 `kind=image` 的块就是 `cropping`，否则 `review`；`done` 与 `discarded` 只能由后续的入库 / 丢弃接口产生。

`connect(vault)` 用 `CREATE TABLE IF NOT EXISTS` 建表，可重复调用；写操作统一走模块级 `_LOCK`。图片尺寸用 `inbox.image_size()` 读文件头，不依赖 Pillow。

## 3. Python 接口（`omrs/drafts.py`）

| 函数 | 说明 |
|---|---|
| `add_image(vault, data_url, conversation_id, run_id) -> {sha256, n, ref, width, height, mime, bytes}` | 存一张聊天贴图。只收 `data:image/(png\|jpeg\|gif);base64,`，解码后 ≤8MB，尺寸由 `image_size()` 取；越界抛 `ValueError`（中文） |
| `resolve_image(vault, conversation_id, ref) -> {sha256, n, ref, width, height, mime, bytes, run_id}` | `"IMG-3"` → 本对话里那张图；找不到抛 `ValueError("本对话里没有 IMG-3")` |
| `conversation_refs(vault, conversation_id) -> {sha256: "IMG-n"}` | 本对话全部图片的编号，草稿工具把块里的 sha 还原成 IMG-n 时用 |
| `image_path(vault, sha)` / `image_data_url(vault, sha)` | 图片原件路径 / data URL；sha 未知或文件缺失抛 `ValueError` |
| `get_transcript(vault, sha, model)` / `set_transcript(vault, sha, model, transcript)` | 转述缓存的读 / 写；`get` 在无缓存或模型名不符时返回 `None` |
| `create_draft(vault, data, origin) -> draft` | 建草稿，校验失败抛 `ValueError` 且不建行；成功发 `draft.create` 事件 |
| `get_draft(vault, id)` | 按 id 读整份草稿（含 `blocks`，按 `ord` 排序）；不存在抛 `ValueError` |
| `list_drafts(vault, status=None, conversation_id=None, limit=50)` | 列表，`created_at` 倒序，`limit` 夹到 1–500 |
| `counts(vault) -> {cropping, review, done, discarded}` | 按状态计数 |

`create_draft` 的入参：`data = {subject, category, knowledge_points[], blocks[], cause, cause_statement}`，`origin = {conversation_id, run_id, tool_call_id}`。`blocks` 每项 `{section, kind, text?, image_sha?, note?}`。校验：科目与分类非空、知识点 ≤8、至少一个块、至少一个 `section=题目` 的块、文字块必须有文本、图片块引用的 sha 必须已在 `images` 里、`cause` 非空时 `cause_statement` 必填。任何一条不过就整份不建。

`list_drafts` **默认（`status=None`）只排除 `discarded`**，`done` 也照常列出——草稿区默认要能看见已入库的草稿，只有显式丢弃的才藏起来。

## 4. 只读 HTTP（`/api/drafts/*`）

本模块这一期只提供四个 GET 路由（`omrs/server.py::_drafts_get`）：`/api/drafts/list`、`/api/drafts/item`、`/api/drafts/image`、`/api/drafts/counts`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/drafts/list?status=&conversation=` | 草稿列表；参数缺省时同 `list_drafts` 默认（排除 discarded） |
| GET | `/api/drafts/item?id=` | 单份草稿（含全部块） |
| GET | `/api/drafts/image?sha=` | 图片二进制，`Cache-Control: private, max-age=86400`；`sha` 必须是 64 位十六进制，否则 400 |
| GET | `/api/drafts/counts` | 四种状态的计数 |

访问规则、同源校验与收件箱的 GET 路由一致。写接口（`/api/drafts/save`、`commit`、`discard` 等）在后续阶段加，见 `AI/plans/ai-draft/plan.md`。

## 5. 事件流 `events.jsonl`

一行一个 JSON：`{"ts", "event", ...}`。这一期发三种：

- `image.add`：`conversation_id / run_id / sha256 / n / ref / mime / width / height / bytes`。
- `image.transcribe`：`sha256 / model`（写转述缓存时发）。
- `draft.create`：`draft_id / conversation_id / run_id / tool_call_id / subject / category / status / blocks`。

后续阶段还会加 `draft.update`、`draft.crop`、`draft.commit`、`draft.discard`、`image.train`。

## 6. 测试

`tests/test_drafts.py`：建表幂等、图片去重与逐对话编号、非法图片（格式 / base64 / 超大 / 坏像素数据）、`resolve_image` 报错、转述缓存按模型命中 / 未命中、草稿状态推导（有图 → cropping，纯文字 → review）、各条校验错误、列表筛选与默认排除规则、计数、事件行，以及四个 GET 路由的 HTTP 级测试（含图片路由的 Content-Type / Cache-Control / sha 校验）。运行：`python3 -m unittest tests.test_drafts`。
