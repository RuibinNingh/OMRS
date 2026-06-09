# 2026-06-08 录入题目增强 + AI 自动识别

> 本条经同日多轮澄清后定稿，以下直接描述**最终行为**；末尾附「迭代过程」备查。

## 背景与目标

原「录入题目」只能建骨架文件，正文需到 Obsidian 手动补。本次让用户可以在录入页**直接**输入题目正文 / 答案 / 错因，或**粘贴 / 拖拽 / 选择**题目图与答案图，并用多模态模型辅助：

- 题目图片区「🤖 提取并填充信息」：读题目图 → 回填**科目 / 分类 / 难度 / 相关知识点**（**不抄题、不解题**，题目以图片随题保存）。
- 答案图片区「🤖 提取答案」：读答案图 → 把答案/解析**提取为纯文本**填入答案框（可选；也可不提取、直接嵌图或手动输入）。

设计原则：AI 调用走**后端转发**（`urllib`，标准库，无第三方依赖），避免浏览器跨域、密钥只留本机 `config.json`；当前「科目 / 分类 / 知识点」由后端从 `mastery_data.csv` 汇总后注入提示词，保证分类口径权威、复用已有项。请求按阿里云百炼（Qwen-VL）OpenAI 兼容文档定稿：**不设 System Message**，指令文本 + 图片都放在 user 消息的 `content`（图片在前、文本在后），`POST {ai_base_url}/chat/completions`。

## 关键约束与交互

- **相关知识点硬约束**：`classify` 返回的 `knowledge_tags` 由后端过滤为「已有分类 ∪ 已有知识点」的子集，模型造的新词一律剔除；空池则为 `[]`。提示词同步要求「只能从已有分类/知识点原样挑选，禁止造新词」。知识点可与分类重叠（如「手拉手模型」既是分类也是知识点）。
- **尊重用户已填值**：点 classify 时把表单当前 `subject` / `category` 作为 hint 发给模型，提示词要求**原样沿用、不要改动**；前端只填**空缺**的科目/分类（`fillIfEmpty`，不覆盖已填值），难度给估计值，知识点与已填的**合并去重**。
- 配置「保存即生效、无需重启」（`load_config` 每次读盘）。

## 后端改动

### 新增 `omrs/ai_assist.py`（仅标准库 urllib + json + re）
- `collect_taxonomy(vault)`：从 `mastery_data.csv` 汇总去重排序的 `subjects / categories / knowledge_tags`（`Knowledge_Tags` 按 `|` 拆分）。
- `_call_model(vault, user_text, image_data_url, max_tokens, timeout)`：读 `ai_base_url/ai_api_key/ai_model`，缺任一项抛 `ValueError("尚未配置 AI…")`；组**单条 user 消息**（`content` = `image_url`(data URL) 在前、`text` 在后，**无 system**），`temperature=0.1`，`urllib` POST 到 `_endpoint(base)`；解析 `choices[0].message.content`（兼容分块列表）；上游 HTTP/连接/超时错误统一转可读 `ValueError`。
- `classify_question(vault, image, timeout=90, hint_subject="", hint_category="")`：用 `CLASSIFY_TEMPLATE`（注入 taxonomy）+ 可选 hint 段；`max_tokens=600`；`knowledge_tags` 经 `_as_str_list` 后**硬过滤**到「已有分类 ∪ 已有知识点」；返回 `{mode:"classify", subject, category, difficulty(1-10), knowledge_tags[], raw}`（解析失败 `raw` 回传原文）。
- `extract_answer(vault, image, timeout=90)`：用 `ANSWER_PROMPT`，`max_tokens=2000`；返回 `{mode:"answer", answer}`（`_strip_fences` 去围栏）。
- `recognize_question(vault, image, mode="classify", timeout=90, hint_subject="", hint_category="")`：分派；`answer` 模式忽略 hint。
- 辅助：`_endpoint`（base 末尾自动补 `/chat/completions`）、`_clamp_difficulty`、`_as_str_list`（拆 `,，、|`、去 `[[]]`、去重）、`_strip_fences`、`_extract_json`。

### 重写 `omrs/creation.py`
- `create_question(vault, subject, category, difficulty, note="", related_tags=None, question_text="", answer_text="", cause="", question_images=None, answer_images=None)`，并**真正使用** `note`（写入 YAML `页码`，此前被忽略）。
- `_save_pasted_images(vault, uid, images, suffix)`：解码 data URL / 裸 base64，按 mime 定扩展名，存到 `错题/附件/`，命名 `<uid>-<suffix>-N.<ext>`（`suffix`='q'/'a'，冲突顺延）；返回文件名与完整路径。
- `_build_markdown(...)`：题目正文 + 题目图 `![[名]]` → `# 题目`；答案文本 + 答案图 → `# 答案`；`cause` → `# 备注` 的 `## 错因`（保留 `## 关联`）；`# 历史` 留空。
- `build_index` 失败回滚：删除本次 md **与**所有已存图片。返回含 `images`(全部) / `question_images` / `answer_images`。

### `omrs/server.py`
- `import recognize_question`。
- 扩展 `POST /api/create`：透传 `question_text / answer_text / cause / question_images / answer_images`。
- 新增 `POST /api/ai-recognize`：体 `{image, mode, subject, category}` → `recognize_question(..., mode, hint_subject, hint_category)` → `{status:"ok", ...}`，错误 `{status:"error", msg}` + 400。
- 配置复用现有 `GET/POST /api/config`（`save_config` 合并键），无需新增端点。

## 前端改动

- `assets/core.js`：全局 `let CR_Q_IMAGES=[],CR_A_IMAGES=[],CR_IMG_SEQ=0;`；`populateCreateLists` 额外填充 `cr-ktag-list`（「已有分类 ∪ 已有知识点」）。
- `omrs_dashboard.html`：
  - 「录入题目」左卡：**两个图片区**——题目图（`#cr-q-paste`/`#cr-q-file`/`#cr-q-images` + `#cr-classify-btn`/`#cr-classify-status`）与答案图（`#cr-a-paste`/`#cr-a-file`/`#cr-a-images` + `#cr-extract-btn`/`#cr-extract-status`）。字段顺序：科目/分类/难度/**相关知识点**(`#cr-related`，挂 `cr-ktag-list`)/题目正文(`#cr-question`)/答案图区/答案(`#cr-answer`)/页码(`#cr-note`)/**错因**(`#cr-cause`)。新增 `<datalist id="cr-ktag-list">`。
  - 「设置」新增「🤖 AI 自动识别」卡片：`#st-ai-base`(示例含 dashscope compatible-mode) `/ #st-ai-key`(密码+显隐) `/ #st-ai-model`(datalist：qwen-vl-max/qwen-vl-plus/qwen3-vl-plus/qwen3-vl-flash/qwen3.7-plus/gpt-4o/gpt-4o-mini) + 保存按钮 + 状态。
- `assets/styles.css`：`textarea.input / .paste-zone(.dragover) / .img-previews / .img-thumb / .ai-row / .ai-status` 等。
- `assets/schedule.js`：`doCreate` 读 `#cr-question/#cr-answer/#cr-cause` 与两区图片，发 `cause / question_images / answer_images`，成功提示含图片数；`resetCreateForm` 清空全部含两区图片与两处状态。
- `assets/app.js`：`loadSettings` 兼填 AI 字段；`toggleAiKey / saveAiSettings`；图片处理按 `kind`('q'/'a')参数化（`crPickFiles/crFileInput/crDragOver/crDragLeave/crHandleDrop/crAddFiles/crAddBlob/crRenderImages/crRemoveImage`）+ 粘贴目标 `crSetPasteTarget` + `crHandlePaste`（仅录入页激活时拦截图片，按聚焦区/上次目标分发）；`crClassify`（发 hint、`fillIfEmpty`、知识点合并去重、难度填）与 `crExtractAnswer`（填 `#cr-answer`）。AI 默认读各区**第 1 张**图。

## 数据格式影响

- `config.json` 新增可选键：`ai_base_url / ai_api_key / ai_model`（见 data.md）。
- 题目 Markdown：YAML 可含 `页码`；`# 题目`(正文+题目图) / `# 答案`(答案文本+答案图) / `# 备注` 的 `## 错因`(错因) 可在创建时直接写入；结构不变，`get_question_content` 原样解析，`exporting._parse_notes_subsections` 能读到 `## 错因` 用于 Word 导出。
- 图片落在 `错题/附件/`，命名 `<uid>-q-N` / `<uid>-a-N`；`/api/image?name=` 与 `![[名]]` 既有机制复用（图片服务仅 PNG/JPEG/GIF，剪贴板截图通常为 PNG）。

## 测试

- 后端单测（临时库 + mock urllib）：含题目/答案图分区的创建与回读（题目图入 `# 题目`、答案图+答案文本入 `# 答案`、`cause` 入 `## 错因` 且可被导出解析、`页码` 入 YAML）；`collect_taxonomy`；`_extract_json/_strip_fences/_clamp_difficulty/_as_str_list/_endpoint`；classify（端点 URL、Bearer、**无 system**、单 user 消息图前文后、taxonomy 注入、hint「原样沿用」、`knowledge_tags` 硬过滤剔除新词、空池为空）；answer（去围栏）。
- 前端（真实 `crClassify` 源 + mock DOM）：预填分类不被覆盖、空科目被填、难度填、知识点合并去重；两者皆空则都填。
- 服务级（loopback）：静态资源、`/api/config` 读写持久化（含 `ai_*`，免重启）、`/api/create` 含两区图、`/api/question` 回读、`/api/image` 出图、`/api/ai-recognize`(classify/answer) 未配置/无网返回干净 400。

## 后续可选

- 多图联合识别（当前每区只读第 1 张）。
- webp 截图的服务端解码（`_read_image_info` 暂不支持 webp）。

---

## 迭代过程（备查）

本特性同日经四轮澄清定稿，要点：①AI 改为不抄题，拆「提取并填充信息 / 提取答案」两按钮、两 `mode`，题目图与答案图分区（`question_images`/`answer_images`，`<uid>-q/a-N`）；②「备注」→「错因」（写 `## 错因`），相关知识点改为自动填充并上移；③相关知识点加硬约束（仅取自已有分类∪已有知识点）+ 手动输入挂 datalist；④尊重用户已填科目/分类（hint + 前端 `fillIfEmpty` 不覆盖）。
