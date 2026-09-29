# 收件箱录入流程（inbox，v1.12.0；v1.13.0 加提供方 / 盲标 / 自动策略 / 清理）

> **速查**
> - 职责：收件箱「上传 → 框选 → 转换 → 提交」暂存流程、后台 job、框选提供方与训练数据集
> - 入口：`omrs/inbox.py`、`omrs/ai_assist.py`、`assets/app/features/create/`、`assets/inbox_mobile.html`
> - 不变量：上传的原图只进暂存区，提交后才写入题库；手机页遵循与桌面相同的访问规则
> - 必跑测试：`tests/test_inbox.py`、`tests/app/settings.test.mjs`、`tests/app/create-inbox.test.mjs`、`tests/e2e/create.py`
> - 相关：`AI/frontend/create.md`、`AI/api.md`

> 对应源文件：`omrs/inbox.py`（存储 / 任务 / 提交 / 数据集）、`omrs/ai_assist.py`（`detect_regions` / `extract_region` / `parse_detect_output` / 按用途选模型）、`omrs/server.py`（`_inbox_get` / `_inbox_post` / `_multipart_files`）、`assets/app/features/create/`（录入页六个工作区与收件箱前端数据，见 `AI/frontend/create.md`）、`assets/inbox_mobile.html`。

## 1. 它解决什么

收件箱流程为 **上传 → 处理 → 录入** 三步：手机把整张作业帮长截图投进收件箱，电脑端在网页上框「题目 / 答案」，点击「一键提取」由 AI 一次输出完整文本或不可提取原因，后者保留裁图，之后人工审核并可调整保存方式，最后复用 `create_question` 写题库。所有人工动作（框位、AI 原框、采纳方式、转换决策、结果）留作训练数据。

**边界**：收件箱是暂存层，**不进 Ledger**。只有 `commit` 走 `creation.create_question`，写 Ledger 的路径与旧录入完全一致。原图即使题目已转文本也留在收件箱；已丢弃原图会按 `inbox_discard_keep_days`（默认 7 天）在上传时自动清理，也可由数据集页调用 `/api/inbox/cleanup` 手动清理，记录和标注事件会保留。

## 2. 存储 `错题/.omrs/inbox/`

```
inbox.db             SQLite：items / regions / cards / jobs
raw/<sha256>.<ext>   上传原件（PNG/JPEG/GIF），按内容哈希命名 → 重复上传合并
crops/<region>.png   裁剪缓存（前端 canvas 生成后随 job / commit 上传；可删可重建）
annotations.jsonl    append-only 事件：item.upload / regions.update / item.ready / ai.detect / ai.extract / item.commit / item.discard / item.reset
```

`items`：`id (IB-YYYYMMDD-xxxxxx)、sha256、file、mime、width、height、bytes、source (phone|desktop|paste)、uploaded_at、status、layout、link_uid、link_question_id、blind、blind_boxes、reset_epoch、revision`（扩展列由 `connect()` 为旧库幂等补齐；`blind_boxes` 只进事件与导出，不进 item 响应）。`reset_epoch` 随当前图重置递增，`revision` 随成功修改递增；HTTP 写入同时核对两者，拒绝旧页面和旧任务写回。另有 `meta(key, value)` 表：`rejected_ai_boxes`（拒绝的 AI 框增量计数）、`detect_counter`（盲标间隔计数）。
`status`：`pending → boxed → ready → done`，另有 `discarded`。`done`、`discarded` 后不可再修改处理内容。
`layout`：`zuoyebang | photo | plain | other`（训练标签，也进 detect 提示词）。新上传图片默认使用 `zuoyebang`（界面显示“作业帮截图”）；需要时可在处理页改为拍照/扫描、已裁好的题图或其他。

`regions`（一张图 N 个，坐标归一化 0–1）：`card`（同图第几道题）、`ord`、`role (question|answer|ignore)`、`x y w h`、`origin (manual|ai|ai_edited)`、`conf`、`ai_box`（AI 原框，人工改过也保留，用于算 IoU）、`convert (text|image|auto)`、`text`、`text_status (none|running|done|stale|error)`、`judge {ok, reason}`、`judge_overridden`。

`cards`（`item_id + card`）：`subject、category、difficulty、tags(JSON)、cause、classified、created_uid、created_question_id、manual_fields(JSON)、field_sources(JSON)`。旧 `page` 列只为读取旧库保留，API 不返回，保存时清空，新题不写页码。`connect()` 给旧库幂等补齐来源列；人工字段变更记入 `manual_fields`，AI 来源保存当前图片哈希、题目框 ID 和请求时 revision。

旧客户端在 `/api/inbox/item/update` 的题卡里传 `page` 时，响应返回 `deprecated_fields:["cards.<编号>.page"]`；在 `/api/inbox/commit` 的 `form.page` 传入时返回 `deprecated_fields:["form.page"]`。两者均忽略页码，现有旧库行和已入账历史不批量改写。

图片尺寸由 `inbox.image_size()` 直接读文件头（PNG/GIF/JPEG SOF），不依赖 Pillow。

## 3. HTTP API（`/api/inbox/*`，同源校验与其他端点一致）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/inbox/upload` | multipart 多文件（字段名任意，按 `filename=` 识别）或 JSON `{images:[{name,data}], source}`；UA 含 `Mobile` 记为 `phone`。返回 `{items, duplicates:[{file,item_id}]}` |
| GET | `/api/inbox/items?status=` | 列表（默认排除 discarded），每项含 `regions`、`cards`、`link`、`revision`、`reset_epoch` |
| GET | `/api/inbox/item?id=` | 单项 |
| GET | `/api/inbox/raw?id=` | 原图二进制（`Cache-Control: private, max-age=86400`） |
| POST | `/api/inbox/item/update` | `{id, expected_revision, reset_epoch, regions?, cards?, layout?, status?}`；只修改显式字段，传入 regions 时 **整体覆盖**；`status=ready` 时服务端校验：≥1 题目框、无 `auto` 或 running/stale/error、`text` 区域必须有文本。不传 status 时按框数自动在 pending/boxed 间切换 |
| POST | `/api/inbox/item/reset` | `{id, expected_revision, reset_epoch}`；仅没有任何题卡写入题库、未丢弃的普通截图可重置。原子清空区域、题卡、盲标信息及处理状态，版式回默认值，保留上传原图；代次与版本递增，旧任务结果失效 |
| POST | `/api/inbox/discard` | `{id, expected_revision, reset_epoch}` 或 `{items:[{id,expected_revision,reset_epoch},…]}`；批量先校验全部版本，再同事务丢弃，冲突时整批不动 |
| GET | `/api/inbox/slice-plan?width=&height=` | 长图切片计划 `{strips:[{y0,y1}]}`（高宽比 >3 才切，条带高≈2×宽，重叠 8%，末尾碎条并入上一条） |
| POST | `/api/inbox/jobs` | `{type: detect\|extract\|classify\|auto, …}` → `{job}`；后台线程逐单元执行，单元失败进 `errors` 不中断 |
| GET | `/api/inbox/job?id=` | `{status, processed, total, result[], errors[], done}` |
| POST | `/api/inbox/crops` | `{crops:{region_id: dataURL}}` 只缓存裁图 |
| POST | `/api/inbox/commit` | `{id, card, expected_revision, reset_epoch, form{subject,category,difficulty,tags,cause,page}, crops{region_id:dataURL}}` → 持图片锁核版本并调 `create_question` → `{uid, question_id, file_path, images…, item_id, card}`；成功后版本递增，该图全部题卡都建完后 item→done |
| GET | `/api/inbox/dataset/stats` | 张数、框数按角色、版式分布、AI 建议/采纳/微调/拒绝（拒绝数来自 `meta`，老库首次从 annotations 回填一次）、微调平均 IoU、转文本决策与判断一致率、`blind`（盲标评估集：张数 / 已评估 / 隐藏 AI 框数 / IoU≥0.5 命中 / 平均 IoU）、`storage`（raw / crops 字节数、待清理的已丢弃张数） |
| GET | `/api/inbox/dataset/export?format=omrs_jsonl\|yolo&raw=1` | zip：`labels.jsonl`（每图一行，归一化 regions）、`images/`、`annotations.jsonl`；yolo 另含 `labels/*.txt` + `classes.txt` |
| POST | `/api/inbox/cleanup` | `{discarded_days?, crops?}`：删除丢弃超过 N 天（缺省 `inbox_discard_keep_days`）的原图（行保留、`file` 置空），`crops=true` 清空裁剪缓存；上传时也自动跑一次 |
| GET | `/m` | 手机极简上传页 `assets/inbox_mobile.html`（需 `allow_external`；显式豁免网段直连免 PIN，其他远端需登录）；加载设计 token 和 base 样式，读取主站的 `omrs-theme` 浅色 / 深色设置；真实触摸、滚轮或滚动会刷新空闲会话；会话过期（401）时跳转 `/login?next=/m` 并停止剩余上传 |

**job 单元格式**
- 用户更新、重置、丢弃和录入缺少有效 `expected_revision` / `reset_epoch`，或它们与当前项不符时，返回 409 `{status:"error",code,msg,current_revision}`，不修改 `inbox.db`。同一图的后台结果只在代次、状态及相应版本/区域仍有效时写回；过期结果进入作业错误，不覆盖人工编辑。
- `detect`：`items:[{item_id, strips?:[{y0,y1,data}], replace?, provider?, blind?}]`。`provider` 缺省取配置 `inbox_detect_provider`（见 §8）；仅支持 `vlm` 与 `local_http`；旧配置 `template` 自动回退到 `vlm`，显式请求 `template` 会被拒绝。前端按 slice-plan 切条带并附 JPEG data URL；不附 strips 时有 Pillow 就在服务端按同一 slice_plan 切，否则整图送模型（长图会被模型端压缩，精度下降）。结果 `{item_id, provider, blind, boxes, hidden?, regions, auto?}`。结果经 `inbox.merge_strip_boxes()` 映射回整图并合并跨条带的同角色框（同一条带内的框永不合并）。已有框时默认**追加**（`replace=false`）。
- `extract`：`regions:[{region_id, crop?}]`。裁图优先级：请求附带 → `crops/` 缓存 → Pillow 服务端裁 → 框覆盖全图时用原图；都没有则该单元报错。所有保存方式都以 judge=True 在同一次模型调用中返回判断和文本；可提取写 text，不可提取写 image，始终退回 boxed 等人工审核。无效响应或空正文报错，不当作留图成功；重提取的失败保留旧正文。模型调用不占写锁，写回只合并目标区域并核对框位、角色及内容未改变；过期结果拒绝写入。
- `classify`：`cards:[{item_id, card, crop?, reset_epoch?}]`，取该题卡第一个题目框，调 `classify_question`（带已填科目/分类 hint）；返回后重读当前图并核对版本和题目框，只填仍空缺的项，人工新值不被覆盖。
- `auto`：`items:[{item_id, provider?, reset_epoch?}]`，无人值守：服务端切片 → detect → §8 自动策略，代次贯穿自动提取。`inbox_auto_on_upload` 打开时 `upload_images` 会自动排一个（响应多一个 `job` 字段）。

## 4. AI 层（`ai_assist.py` 新增）

- `_ai_config(vault, purpose)`：按 `ai_model_detect / ai_model_extract / ai_model_classify` 选模型，留空回退 `ai_model`（`common.CONFIG_DEFAULTS` 已加三键；设置页有三个输入框）。
- `detect_regions_local(url, image, layout, width, height)`（v1.13.0）：`local_http` 提供方，`POST url` JSON `{image, layout, width, height}`，响应数组或 `{boxes:[…]}`，同样经 `parse_detect_output` 归一化（传了宽高所以像素坐标也能解析）。若地址属于登记的受管服务，请求前后核对模型指针和健康身份；不符时拒绝把返回框写进收件箱或草稿。
- `detect_regions(vault, image, layout)`：`DETECT_PROMPT` 要求输出 `[{label, card, bbox_2d:[x1,y1,x2,y2], confidence}]`，坐标 **0–1000 相对**（Qwen3-VL 约定）。`parse_detect_output()` 兼容三种坐标：≤1 视为小数；>1000 且给了尺寸视为绝对像素（Qwen2.5-VL 风格）；否则 /1000。`label` 以 answer/答案/解析 开头 → answer，其余 → question。
- `extract_region(vault, image, role, judge)`：复用 `ANSWER_PROMPT` / `QUESTION_TEXT_PROMPT`，`judge=True` 时追加 `JUDGE_SUFFIX` 要求返回 `{convertible, reason, text}`；判断模式要求 JSON 中 convertible 为布尔值，可提取时 text 为非空字符串，否则报错供重试；不可提取不要求正文。题目文本会去掉整段开头题号；答案仅在开头为“题号+答案/解析标题”时去掉题号，解析内部步骤编号保留。`max_tokens=4000`；思考行为读取 `ai_thinking`，见 `AI/frontend/settings.md`。

`JUDGE_SUFFIX` 以删去裁图后能否仅靠文本和 LaTeX 保留解题或理解原解析所需信息为判断标准。题干依赖图形、曲线、位置关系或表格内容时，不能因文字识别完整、能概述图意或认为图形只是辅助就判为可转；拿不准时要求留图。纯装饰图及软件控件不影响判断，能完整转录行列关系的简单表格可转。服务端只验证返回类型和非空正文，实际内容仍由用户审核。

- 旧的 `/api/ai-recognize` 三种 mode 行为不变（classify 现在也走 `purpose="classify"`）。

## 5. 前端（`assets/app/features/create/`）

界面分工与文件见 `AI/frontend/create.md`；这里只记与后端流程相关的前端约定。

- 入口：`#/create` 挂载页面契约，读 `/api/inbox/items`。收件箱前端数据只有一个所有者 `inbox-store.js`（单例在 `inbox.js`），网格、处理区、题卡共用同一份图片列表与勾选。**上传 / 处理 / 录入**按真序列编号，AI 草稿、AI 训练和快速录入在旁边；切页返回后仍停在原工作区。
- 粘贴：上传工作区捕获图片粘贴并上传；快速录入工作区按当前目标接收图片；文本粘贴仍走浏览器原行为。
- ① 上传：拖拽 / 选文件 / 粘贴 / 读剪贴板 → `POST /api/inbox/upload`，成功后发 `inbox:reload` 重读。网格在原图卡片上叠框位预览，按状态筛选；批量条提供 AI 框选、整图即题目、去处理、丢弃，只处理勾选项。
- ② 处理三栏：队列（可勾选）| 画布（拖拽画框、移动、八向缩放，框外 SVG mask 遮暗，AI 框带置信度）| 区域面板（按题卡分组；角色 / 来源 / 归一化坐标与裁出尺寸 / 一键提取后的文本编辑与 Markdown 预览 / 无法提取时的裁图预览 / 结果后的次要保存方式切换）。改动去抖 500ms 调 `/item/update`，离开处理区或本页时立即写出。
- AI 框选（`inbox-ops.js` 的 `detect`）：`slice-plan` → canvas 切条带（JPEG 0.85）→ `jobs detect` → 1.2s 轮询 → 完成后重读收件箱回填。提取、分类也用后台 job 和轮询。detect 完成的提示汇总盲标张数、自动提取待审核张数与失败数；区域面板 meta 行对盲标图显示「盲标（AI 框已隐藏，请直接手画）」。
- 文本提取完成时，前端重读收件箱；正在保存、待保存或拖动的图片保留本地对象和编辑，安全字段才与服务端状态合并。读取失败时保留当前列表和编辑并提示，不以空列表替换。
- ③ 录入：`ready` 的每张题卡一行——左预览（文本 Markdown 或裁图 canvas）右表单；字段去抖 600ms 存到 `cards`；「AI 识别题目信息」走 classify job；「创建题目」先确认待存改动已全部写出，失败则中止，再用最新 revision/epoch 连同裁图提交。单张创建弹一条带「加入展示板」的提示（停留 8 秒）；批量逐张提交、最后只弹一条汇总，「加入展示板（N 题）」一次加入这批新题。
- AI 训练：`dataset/stats` 四张指标卡 + 版式 / 转换决策条 + 盲标评估集与存储概览 + 导出（JSONL / YOLO）+ 清理按钮 +「框选提供方与自动策略」表单（直接读写 `/api/config` 的 `inbox_*` 键）。
- 裁图（`crop.js`）：PNG 裁图超过 150 万像素（整张长截图的答案区）自动改 JPEG 0.9（白底），避免 commit 请求带几 MB base64。

## 6. 测试

`tests/test_inbox.py`：覆盖图片头解析、长图切片计划、跨条带框合并、detect 三种坐标解析、上传去重 → 画框 → 就绪校验 → commit（文本 + 整图图片区）→ done → 统计 → YOLO 导出 → annotations 事件、丢弃、provider 分派、重置代次、盲标、自动策略、上传即 auto job 与清理。测试用 `FakeAI` 替身，不联网。运行：`python3 -m unittest tests.test_inbox`。

## 7. 已知边界 / 待办

- **请求线程与写锁**：HTTP 服务器使用 `ThreadingMixIn`；题目写入由全局写锁串行化。job 在后台线程运行，只写 `inbox.db`（自有 `_LOCK`），不碰 Ledger。
- detect 效果取决于模型：Qwen3-VL 系列支持 0–1000 定位；不支持定位的模型返回 `[]`，前端提示「0 框」。长截图必须切片（前端已做；无前端在环时需 Pillow 才能服务端切）。
- 服务端裁图需要 Pillow（可选）；自动策略 / 无人值守流水线在没有 Pillow 时只对覆盖全图的框（整图即题目）有效，其余会以「自动转文本失败」中止并停在 boxed。
- `local_http`与真实YOLOv8n ONNX服务已通过隔离浏览器链路验证；本机生产服务配置见AI/environment.md。检测能返回框不代表内容质量达标，使用时可人工校正。
- 待办：手机页作为 PWA share target（需 HTTPS）；`_blind_stats` 每次全量读盲标行（盲标样本通常很少，暂不优化）。

## 8. 提供方与自动策略（v1.13.0）

配置键（`config.json`，`common.CONFIG_DEFAULTS`；「AI 训练」页有表单，也可直接 `POST /api/config`）：

| 键 | 默认 | 说明 |
|---|---|---|
| `inbox_detect_provider` | `vlm` | `vlm`：设置页的多模态模型（联网）；`local_http`：本地检测服务 |
| `inbox_local_detect_url` | `""` | `local_http` 的 POST 地址，协议见 §4 `detect_regions_local` |
| `inbox_blind_every` | `0` | 每 N 张盲标；0 关闭 |
| `inbox_auto_ready_conf` | `0` | AI 框全部 ≥ 阈值时自动提取并判断，仍待人工审核；0 关闭，配置键名保留兼容 |
| `inbox_auto_on_upload` | `false` | 上传即排 `auto` job |
| `inbox_discard_keep_days` | `7` | 丢弃的原图保留天数 |

旧 `template` 配置仅在读取时兼容为 `vlm`；新配置和 detect 请求不接受模板提供方。离线评估工具保留历史模板对照的计算，不参与收件箱和草稿处理。

**盲标**：`_should_blind` 先看单元里的 `blind`（显式覆盖），否则 `meta.detect_counter` 每 N 次命中一次。命中时 detect 照常跑，但结果只写 `items.blind_boxes`、`items.blind=1`，不写 regions；事件 `ai.detect` 带 `blind:true`。人工画完标记就绪时 `item.ready` 事件多出 `blind:true, ai_boxes, blind_eval{pairs[{role,iou}], total, matched, mean_iou}`（`blind_eval` 对每个隐藏 AI 框找同角色 IoU 最高的人工框，≥0.5 计命中）。`dataset/stats.blind` 汇总；导出的 `labels.jsonl` 对盲标图多 `blind, blind_ai_boxes`。

**自动策略 `_auto_policy`**：非盲标 detect 之后，若阈值 > 0、有题目框、所有框 conf ≥ 阈值、且该图没有人工框：对每个非忽略区域按 `convert=auto` 跑 `_run_extract`（可转性判断决定 text/image），全部成功后仍停在 boxed，结果 ready=false，待用户审核后主动标记就绪；任一步失败记 `item.auto` 事件的 `reason` 并停在 boxed。结果放在 detect 单元结果的 `auto` 字段。

**清理 `cleanup(vault, discarded_days, crops)`**：删除 `status=discarded` 且 `updated_at` 早于 N 天的原图，`file` 置 NULL（行与事件保留；`raw_file` 对这类项报「已被清理」）；`crops=True` 清空 `crops/`。写 `inbox.cleanup` 事件。`upload_images` 末尾会 `cleanup_expired`（吞异常）。

## 9. 聊天草稿训练登记

草稿入库后的训练图经 register_chat_training 登记，不经过 upload_images 和上传自动检测。新条目使用 source=chat、layout=other、status=ready、training_only=true；普通 items 列表和 commit 入口排除训练专用项。chat_training_boxes 用草稿与标注身份生成稳定 id，重复登记不增加重复框，只有答案框也可统计和导出。

同 SHA 已存在普通条目时，保持它的状态、版式、来源与原框，聊天框另存 chat_training_boxes；数据集按图合并，labels.jsonl 保留聊天标注来源，YOLO 同样包含这些框。用户主动上传已有训练专用图时将其提升为普通待处理项，保留独立聊天标注。普通清理跳过仍有聊天训练关联的原图。

数据集统计另有 chat:{images,boxes}：按图片 SHA 去重计算含聊天标注的图片数与聊天框数；普通收件箱同图也计入聊天来源统计，不改它原有 source。总图数不因一图多个草稿或两种来源重复累计。
