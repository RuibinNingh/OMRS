# 收件箱录入流程（inbox，v1.12.0；v1.13.0 加提供方 / 盲标 / 自动策略 / 清理）

> 对应源文件：`omrs/inbox.py`（存储 / 任务 / 提交 / 数据集）、`omrs/ai_assist.py`（`detect_regions` / `extract_region` / `parse_detect_output` / 按用途选模型）、`omrs/server.py`（`_inbox_get` / `_inbox_post` / `_multipart_files`）、`assets/inbox.js`、`assets/inbox_mobile.html`、`omrs_dashboard.html`（`#panel-create` 的 `ib-*` 结构）、`assets/styles.css` 末段。
> 设计历史已归入 `AI/logs/2026-09-03_inbox-intake*.md`；当前行为以本文件与源码为准。

## 1. 它解决什么

原「录入题目」页一次一题、只读第 1 张图、要先手工裁题目/答案。收件箱把流程拆成 **上传 → 处理 → 录入** 三步：手机把整张作业帮长截图投进收件箱，电脑端在网页上框「题目 / 答案」，每块可选转文本（AI 转录 + 可转性判断）或保留裁图，最后复用 `create_question` 写题库。所有人工动作（框位、AI 原框、采纳方式、转换决策、结果）留作训练数据。

**边界**：收件箱是暂存层，**不进 Ledger**。只有 `commit` 走 `creation.create_question`，写 Ledger 的路径与旧录入完全一致。原图即使题目已转文本也留在收件箱；已丢弃原图会按 `inbox_discard_keep_days`（默认 7 天）在上传时自动清理，也可由数据集页调用 `/api/inbox/cleanup` 手动清理，记录和标注事件会保留。

## 2. 存储 `错题/.omrs/inbox/`

```
inbox.db             SQLite：items / regions / cards / jobs
raw/<sha256>.<ext>   上传原件（PNG/JPEG/GIF），按内容哈希命名 → 重复上传合并
crops/<region>.png   裁剪缓存（前端 canvas 生成后随 job / commit 上传；可删可重建）
annotations.jsonl    append-only 事件：item.upload / regions.update / item.ready / ai.detect / ai.extract / item.commit / item.discard
```

`items`：`id (IB-YYYYMMDD-xxxxxx)、sha256、file、mime、width、height、bytes、source (phone|desktop|paste)、uploaded_at、status、layout、link_uid、link_question_id、blind、blind_boxes`（后两列 v1.13.0 由 `connect()` 用 ALTER 补齐；`blind_boxes` 只进事件与导出，不进 item 响应）。另有 `meta(key, value)` 表：`rejected_ai_boxes`（拒绝的 AI 框增量计数）、`detect_counter`（盲标间隔计数）。
`status`：`pending → boxed → ready → done`，另有 `discarded`。`done` 后不可再改。
`layout`：`zuoyebang | photo | plain | other`（训练标签，也进 detect 提示词）。新上传图片默认使用 `zuoyebang`（界面显示“作业帮截图”）；需要时可在处理页改为拍照/扫描、已裁好的题图或其他。

`regions`（一张图 N 个，坐标归一化 0–1）：`card`（同图第几道题）、`ord`、`role (question|answer|ignore)`、`x y w h`、`origin (manual|ai|ai_edited)`、`conf`、`ai_box`（AI 原框，人工改过也保留，用于算 IoU）、`convert (text|image|auto)`、`text`、`text_status (none|running|done|stale|error)`、`judge {ok, reason}`、`judge_overridden`。

`cards`（`item_id + card`）：`subject、category、difficulty、tags(JSON)、cause、page、classified、created_uid、created_question_id`。

图片尺寸由 `inbox.image_size()` 直接读文件头（PNG/GIF/JPEG SOF），不依赖 Pillow。

## 3. HTTP API（`/api/inbox/*`，同源校验与其他端点一致）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/inbox/upload` | multipart 多文件（字段名任意，按 `filename=` 识别）或 JSON `{images:[{name,data}], source}`；UA 含 `Mobile` 记为 `phone`。返回 `{items, duplicates:[{file,item_id}]}` |
| GET | `/api/inbox/items?status=` | 列表（默认排除 discarded），每项含 `regions`、`cards`、`link` |
| GET | `/api/inbox/item?id=` | 单项 |
| GET | `/api/inbox/raw?id=` | 原图二进制（`Cache-Control: private, max-age=86400`） |
| POST | `/api/inbox/item/update` | `{id, regions?, cards?, layout?, status?}`；regions **整体覆盖**；`status=ready` 时服务端校验：≥1 题目框、无 `auto`、`text` 区域必须有文本。不传 status 时按框数自动在 pending/boxed 间切换 |
| POST | `/api/inbox/discard` | `{id}` 或 `{ids:[…]}` |
| GET | `/api/inbox/slice-plan?width=&height=` | 长图切片计划 `{strips:[{y0,y1}]}`（高宽比 >3 才切，条带高≈2×宽，重叠 8%，末尾碎条并入上一条） |
| POST | `/api/inbox/jobs` | `{type: detect\|extract\|classify\|auto, …}` → `{job}`；后台线程逐单元执行，单元失败进 `errors` 不中断 |
| GET | `/api/inbox/job?id=` | `{status, processed, total, result[], errors[], done}` |
| POST | `/api/inbox/crops` | `{crops:{region_id: dataURL}}` 只缓存裁图 |
| POST | `/api/inbox/commit` | `{id, card, form{subject,category,difficulty,tags,cause,page}, crops{region_id:dataURL}}` → 调 `create_question` → `{uid, question_id, file_path, images…, item_id, card}`；该图全部题卡都建完后 item→done |
| GET | `/api/inbox/dataset/stats` | 张数、框数按角色、版式分布、AI 建议/采纳/微调/拒绝（拒绝数来自 `meta`，老库首次从 annotations 回填一次）、微调平均 IoU、转文本决策与判断一致率、`blind`（盲标评估集：张数 / 已评估 / 隐藏 AI 框数 / IoU≥0.5 命中 / 平均 IoU）、`storage`（raw / crops 字节数、待清理的已丢弃张数） |
| GET | `/api/inbox/dataset/export?format=omrs_jsonl\|yolo&raw=1` | zip：`labels.jsonl`（每图一行，归一化 regions）、`images/`、`annotations.jsonl`；yolo 另含 `labels/*.txt` + `classes.txt` |
| POST | `/api/inbox/cleanup` | `{discarded_days?, crops?}`：删除丢弃超过 N 天（缺省 `inbox_discard_keep_days`）的原图（行保留、`file` 置空），`crops=true` 清空裁剪缓存；上传时也自动跑一次 |
| GET | `/m` | 手机极简上传页 `assets/inbox_mobile.html`（需 `allow_external`） |

**job 单元格式**
- `detect`：`items:[{item_id, strips?:[{y0,y1,data}], replace?, provider?, blind?}]`。`provider` 缺省取配置 `inbox_detect_provider`（见 §8）；`template` 不需要 strips。前端按 slice-plan 切条带并附 JPEG data URL；不附 strips 时有 Pillow 就在服务端按同一 slice_plan 切，否则整图送模型（长图会被模型端压缩，精度下降）。结果 `{item_id, provider, blind, boxes, hidden?, regions, auto?}`。结果经 `inbox.merge_strip_boxes()` 映射回整图并合并跨条带的同角色框（同一条带内的框永不合并）。已有框时默认**追加**（`replace=false`）。
- `extract`：`regions:[{region_id, crop?}]`。裁图优先级：请求附带 → `crops/` 缓存 → Pillow 服务端裁 → 框覆盖全图时用原图；都没有则该单元报错。`convert=auto` 时先判可转性再决定 text/image；`text` 时直接转录。
- `classify`：`cards:[{item_id, card, crop?}]`，取该题卡第一个题目框，调 `classify_question`（带已填科目/分类 hint），只填空缺项。
- `auto`：`items:[{item_id, provider?}]`，无人值守：服务端切片 → detect → §8 自动策略。`inbox_auto_on_upload` 打开时 `upload_images` 会自动排一个（响应多一个 `job` 字段）。

## 4. AI 层（`ai_assist.py` 新增）

- `_ai_config(vault, purpose)`：按 `ai_model_detect / ai_model_extract / ai_model_classify` 选模型，留空回退 `ai_model`（`common.CONFIG_DEFAULTS` 已加三键；设置页有三个输入框）。
- `detect_regions_local(url, image, layout, width, height)`（v1.13.0）：`local_http` 提供方，`POST url` JSON `{image, layout, width, height}`，响应数组或 `{boxes:[…]}`，同样经 `parse_detect_output` 归一化（传了宽高所以像素坐标也能解析）。
- `detect_regions(vault, image, layout)`：`DETECT_PROMPT` 要求输出 `[{label, card, bbox_2d:[x1,y1,x2,y2], confidence}]`，坐标 **0–1000 相对**（Qwen3-VL 约定）。`parse_detect_output()` 兼容三种坐标：≤1 视为小数；>1000 且给了尺寸视为绝对像素（Qwen2.5-VL 风格）；否则 /1000。`label` 以 answer/答案/解析 开头 → answer，其余 → question。
- `extract_region(vault, image, role, judge)`：复用 `ANSWER_PROMPT` / `QUESTION_TEXT_PROMPT`，`judge=True` 时追加 `JUDGE_SUFFIX` 要求返回 `{convertible, reason, text}`；模型不按 JSON 返回时整段当 text、`convertible=True`。题目文本会去掉整段开头题号；答案仅在开头为“题号+答案/解析标题”时去掉题号，解析内部步骤编号保留。`max_tokens=4000`。
- 旧的 `/api/ai-recognize` 三种 mode 行为不变（classify 现在也走 `purpose="classify"`）。

## 5. 前端（`assets/inbox.js`，全局 `IB`，类名前缀 `ib-`）

- 入口：`switchTab('create')` → `inboxInit()`（首次绑定事件委托，随后 `ibLoad()`）。`#panel-create` 顶部 `.ib-flow` 五个入口：**上传 / 处理 / 录入**（真序列，编号）+ **AI 训练** + **快速录入**（原单题表单原样搬进 `#ib-stage-quick`，`#cr-*` id 与 `app.js` / `schedule.js` 逻辑不变）。
- 粘贴：`ibPaste` 以捕获阶段注册，仅在收件箱「上传」阶段拦截图片并上传；`crHandlePaste` 只在 `IB.stage==='quick'` 时接管。
- ① 上传：拖拽 / 选文件 / 读剪贴板 → `POST /upload`；网格缩略图上叠框位；筛选、全选、勾选后底部 `.ib-batchbar`（AI 框选 / 沿用框位 / 整图即题目 / 去处理 / 丢弃）——**只处理勾选项**。
- ② 处理三栏：队列（可勾选）| 画布（拖拽画框、移动、八向缩放，框外 SVG mask 遮暗，AI 框带置信度）| 区域面板（按题卡分组；角色 / 来源 / 归一化坐标与裁出尺寸 / 转文本·保留图·让 AI 判断 / 提取 / 文本编辑 + `renderMdContent` 预览 / 保留图的 canvas 预览）。改动去抖 500ms 调 `/item/update`。快捷键 `Q/A/X`、`Del`、`Enter`、`⌘/Ctrl+Enter`。
- 沿用上一张框位 `ibTransferBoxes`：横向照搬；`y<0.35` 的框（题目）按**像素**锚定顶部，其余按比例——因为不同截图高度差异极大，归一化 y 不能直接搬。
- AI 框选 `ibDetect`：`slice-plan` → canvas 切条带（JPEG 0.85）→ `jobs detect` → 1.2s 轮询 → 完成后 `ibLoad()` 回填。提取 / 分类同理。
- ③ 录入：`ready` 的每张题卡一行——左预览（文本 `renderMdContent` 或裁图 canvas）右表单；字段去抖保存到 `cards`；`AI 识别题目信息` 走 classify job；`创建题目` 把图片区域 canvas 裁成 PNG 随 `commit` 上传，成功后 `reloadData()`。
- AI 训练：`dataset/stats` 四张指标卡 + 版式 / 转换决策条 + 盲标评估集与存储概览 + 导出（JSONL / YOLO）+ 清理按钮（`ibCleanup`）+「框选提供方与自动策略」表单（`ibLoadPolicy / ibSavePolicy`，直接读写 `/api/config` 的 `inbox_*` 键）。
- 模板框选：处理页 / 队列脚 / 批量条各有「▦ 模板框选」按钮 → `ibDetect(ids, 'template')`，不切片；「🤖 AI 框选」不传 provider，由服务端按配置选。detect 完成的 toast 会汇总盲标张数、自动就绪张数与失败数。区域面板 meta 行对盲标图显示「盲标（AI 框已隐藏，请直接手画）」。
- `ibCrop`：PNG 裁图超过 150 万像素（整张长截图的答案区）自动改 JPEG 0.9（白底），避免 commit 请求带几 MB base64。

## 6. 测试

`tests/test_inbox.py`（unittest，当前共 14 例）：覆盖图片头解析、长图切片计划、跨条带框合并、detect 三种坐标解析、上传去重 → 画框 → 就绪校验 → commit（文本 + 整图图片区）→ done → 统计 → YOLO 导出 → annotations 事件、丢弃、模板框选、provider 分派、盲标、自动策略、上传即 auto job 与清理。测试用 `FakeAI` 替身，不联网。运行：`python3 -m unittest tests.test_inbox`。

## 7. 已知边界 / 待办

- **单线程服务器**：job 在后台线程跑，界面不卡；但 `commit` 与旧端点仍在请求线程串行。job 线程只写 `inbox.db`（自有 `_LOCK`），不碰 Ledger。
- detect 效果取决于模型：Qwen3-VL 系列支持 0–1000 定位；不支持定位的模型返回 `[]`，前端提示「0 框」。长截图必须切片（前端已做；无前端在环时需 Pillow 才能服务端切）。
- 服务端裁图需要 Pillow（可选）；自动策略 / 无人值守流水线在没有 Pillow 时只对覆盖全图的框（整图即题目）有效，其余会以「自动转文本失败」中止并停在 boxed。
- 模板框选没有 OCR：答案框「从答案标题起」用的是同版式样本的比例位置（或默认模板），需要人工微调；有几张人工样本后会自动改用最近一张的框位。
- **AI job 尚未接真实模型验证**（沙箱无网络）：`parse_detect_output` 对具体模型输出是否解析正确、`local_http` 与真实检测服务的对接都待实机跑一遍。
- 待办：手机页作为 PWA share target（需 HTTPS）；`_blind_stats` 每次全量读盲标行（盲标样本通常很少，暂不优化）；`_TEMPLATE_DEFAULTS` 的作业帮数值是估计值，拿到真实截图后校准。

## 8. 提供方与自动策略（v1.13.0）

配置键（`config.json`，`common.CONFIG_DEFAULTS`；「AI 训练」页有表单，也可直接 `POST /api/config`）：

| 键 | 默认 | 说明 |
|---|---|---|
| `inbox_detect_provider` | `vlm` | `vlm`：设置页的多模态模型（联网）；`template`：版式模板（零联网）；`local_http`：本地检测服务 |
| `inbox_local_detect_url` | `""` | `local_http` 的 POST 地址，协议见 §4 `detect_regions_local` |
| `inbox_blind_every` | `0` | 每 N 张盲标；0 关闭 |
| `inbox_auto_ready_conf` | `0` | AI 框全部 ≥ 阈值时自动转文本并置就绪；0 关闭 |
| `inbox_auto_on_upload` | `false` | 上传即排 `auto` job |
| `inbox_discard_keep_days` | `7` | 丢弃的原图保留天数 |

**模板框选 `template_boxes(item, reference)`**：`_template_reference` 取最近一张同版式、已就绪/已录入、含人工确认框的图；有则沿用其框位（横向照搬；`y<0.35` 的框按**像素**锚定顶部，其余按比例，答案框延伸到底），没有则按 `_TEMPLATE_DEFAULTS`（单位为图片宽度倍数：作业帮题目框 `y=0.20W, h=0.75W`，答案框 `y=1.30W` 到底；`plain` 整图即题目）。conf 分别为 0.6 / 0.4，`origin=ai`，因此采纳率 / IoU 统计与 VLM 一样适用。

**盲标**：`_should_blind` 先看单元里的 `blind`（显式覆盖），否则 `meta.detect_counter` 每 N 次命中一次。命中时 detect 照常跑，但结果只写 `items.blind_boxes`、`items.blind=1`，不写 regions；事件 `ai.detect` 带 `blind:true`。人工画完标记就绪时 `item.ready` 事件多出 `blind:true, ai_boxes, blind_eval{pairs[{role,iou}], total, matched, mean_iou}`（`blind_eval` 对每个隐藏 AI 框找同角色 IoU 最高的人工框，≥0.5 计命中）。`dataset/stats.blind` 汇总；导出的 `labels.jsonl` 对盲标图多 `blind, blind_ai_boxes`。

**自动策略 `_auto_policy`**：非盲标 detect 之后，若阈值 > 0、有题目框、所有框 conf ≥ 阈值、且该图没有人工框：对每个非忽略区域按 `convert=auto` 跑 `_run_extract`（可转性判断决定 text/image），全部成功后 `update_item(status=ready)`；任一步失败记 `item.auto` 事件的 `reason` 并停在 boxed。结果放在 detect 单元结果的 `auto` 字段。

**清理 `cleanup(vault, discarded_days, crops)`**：删除 `status=discarded` 且 `updated_at` 早于 N 天的原图，`file` 置 NULL（行与事件保留；`raw_file` 对这类项报「已被清理」）；`crops=True` 清空 `crops/`。写 `inbox.cleanup` 事件。`upload_images` 末尾会 `cleanup_expired`（吞异常）。
