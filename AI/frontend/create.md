# 前端：录入题目与收件箱入口

> **速查**
> - 职责：录入题目页表单、AI 识别入口、提交后表单状态，以及收件箱在前端的入口（流程细节见 `AI/inbox.md`）
> - 入口：`assets/app.js`（录入段）、`assets/inbox.js`
> - 不变量：提交成功后保留科目 / 分类等上下文字段，只清空题目内容
> - 必跑测试：`tests/test_inbox.py`、`tests/test_ai_assist_taxonomy.py`
> - 相关：`AI/frontend.md`（索引）

## 录入题目页（`panel-create`）与提交后表单状态

> 脚本分布：表单提交 `doCreate` / 重置 `resetCreateForm` 在 `assets/schedule.js`；科目/分类 datalist `populateCreateLists` 在 `core.js`；**图片处理、AI 识别、AI 设置、运行状态加载**在 `assets/app.js`；题目图与答案图分别暂存在全局 `CR_Q_IMAGES` / `CR_A_IMAGES`（`CR_IMG_SEQ` 为自增 id）；通用工具 `parseLooseJson` / `copyTextToClipboard` / `looseBool` 均在 `core.js` 声明；反馈页 JSON 导入与 AI 反馈提示词已迁到 `assets/app/features/feedback/`（见 `AI/frontend/feedback.md`）。

> **布局重设计**：原「左卡＝整张表单 / 右卡＝使用说明」改为**双栏工作台** `.cr-workbench`（≤900px 转单列）：**左栏「截图工作区」**`.card` 放两个截图区（题目 / 答案，中间 `.cr-div` 发丝分隔 + `.cr-tip` 提示），**右栏「题卡内容」**`.card` 放结构化字段。顶部 `.cr-steps` 编号步骤条（截图→识别→核对→保存——真序列才编号）；底部 `.cr-actionbar` 横跨双栏，含「重置」（直接调既有 `resetCreateForm()`）+「创建题目」（`#cr-btn`）与一行静态保存说明，`#cr-result` 紧随其后；原使用说明 / 文件结构树收进底部折叠块 `<details class="cr-help">`。右栏的科目 / 分类 / 难度 / 相关知识点包进 `.cr-aigroup` 卡片（标题「🤖 AI 自动填充 · 可改」，提示这组可被识别自动填、且可改）；**错因** `#cr-cause` 独立成暖色块 `.cr-cause`（`--trap-bg` 微染 + `.cr-flag` 赭色旗标 + 「复习时先看这里」脚注，作为错题本的核心字段）。**纯样式 + 结构改动：所有 `#cr-*` 元素 id、内联处理函数、`doCreate`/`crClassify`/`crExtractAnswer`/`crSetPasteTarget` 等逻辑与后端接口全部不变。**

录入页有两个图片区（现分列于左栏上下），题目区配两个 AI 按钮、答案区配一个 AI 按钮，可混用手动录入：
- **题目图片区**（`#cr-q-paste` / `#cr-q-file` / `#cr-q-images`）：粘贴/拖拽/点击选择题目截图，随题保存并嵌入 `# 题目`。按钮 **「🤖 识别题目信息」**（`#cr-classify-btn`）→ `crClassify()` 取第 1 张题目图 `POST /api/ai-recognize {mode:'classify', subject, category}`，只回填**科目/分类/难度/相关知识点**（不抄题、不解题）。按钮 **「🤖 提取题目文本」**（`#cr-question-text-btn`）→ `crExtractQuestionText()` 取第 1 张题目图 `POST /api/ai-recognize {mode:'question_text'}`，把题干/条件/选项/图表说明**提取为文本**填入 `#cr-question`；若图片开头带题号（如 `11.`），只去掉该开头题号，选项和正文内部编号保留。其中 `knowledge_tags` 是否限定在「已有分类 ∪ 已有知识点」由设置页 `ai_restrict_tags` 开关决定（默认开=硬约束；关=允许新建，上限 4 个）。**用户已填的科目/分类会作为 hint 传给模型（要求其沿用），且前端只填空缺项、不覆盖已填值；知识点与已填的合并去重；难度给估计值。** 两个题目区按钮共用状态 `#cr-classify-status`。
- **答案图片区**（`#cr-a-paste` / `#cr-a-file` / `#cr-a-images`）：粘贴/拖拽/点击选择答案截图，嵌入 `# 答案`。按钮 **「🤖 提取答案文本」**（`#cr-extract-btn`）→ `crExtractAnswer()` 取第 1 张答案图 `POST /api/ai-recognize {mode:'answer'}`，要求模型忠实保留图片内全部答案、解析、推导和步骤；若开头是对应题号加“答案/解析”等标题，只去掉题号，解析内部步骤编号保留；不得摘要或补写，再填入 `#cr-answer`。也可不提取（答案图直接嵌入）或手动输入。状态写 `#cr-extract-status`。
- 字段分两栏：**左栏（截图工作区）** 题目截图区 + 答案截图区；**右栏（题卡内容）** 自上而下为 `.cr-aigroup`{`#cr-subject` / `#cr-category`（并排）/ `#cr-diff` 难度滑杆 / `#cr-related` 相关知识点（**classify 自动填**，挂 `cr-ktag-list` datalist，由 `populateCreateLists` 填入「已有分类 ∪ 已有知识点」供手动挑选）} → `#cr-question`（题目正文，可留空、手动输入或由 `question_text` 提取）→ `#cr-answer`（答案文本）→ `#cr-cause`（**错因**，`.cr-cause` 暖色块，写入 `# 备注` 的 `## 错因`）→ `#cr-note`（页码）。

图片交互（题目区 / 答案区各一套）：
- **显式读取剪贴板**：每个区下方有「📋 从剪贴板读取到「题目/答案」」按钮 → `crReadClipboard(kind)`（用 `navigator.clipboard.read()`，需 https 或 localhost 且浏览器授权；无图 / 不支持 / 被拒时弹提示）。这是把图读到**指定区**的最可靠方式，解决「想粘到答案却进了题目」。
- **Ctrl/⌘+V 粘贴**：`document` 级 `paste` 监听仅本页激活时拦截图片；落到「当前目标区」——由 `crSetPasteTarget`（点击/聚焦某区、点其「读取剪贴板」时）记录，默认题目区；目标区会高亮（`.paste-active`，并由 CSS `::after` 角标「粘贴目标」始终跟随当前目标区）提示 Ctrl+V 将粘到此；文本粘贴不受影响。
- 拖拽 / 点击选择按区独立（`crHandleDrop` / `crPickFiles` 带 `kind` 参数 `'q'|'a'`）。缩略图带删除 ✕ 与序号（`crRenderImages(kind)`），并据此启用/禁用对应按钮。
- 提交时 `doCreate` 把两区图片分别映射为 `question_images` / `answer_images` 一并发送；成功提示含已保存图片数。

录入页不再提供外部 AI 题目 JSON 导入，也不再维护本地录入队列；外部 JSON 导入只保留在反馈页。

**反馈页「从屏幕版或 AI 导入反馈」**（反馈录入页的导入折叠面板，`features/feedback/importer.js::planImportText` 与控制器 `copyPrompt`）：
- **屏幕版导入**：粘贴屏幕版导出件「复制作答 JSON」的产物（格式见 `data.md` §11；容忍围栏、接受 `items`/`feedbacks`/裸数组），逐条校验 `uid` 非空、`is_correct` 经 `looseBool` 宽松解析（true/1/"对"…），`sub_score` 缺省按对→10 / 错→4、钳 0–10。
- **AI 导入**：「复制 AI 反馈提示词」会按当前已选 Session / 反馈行生成 UID 清单与输出骨架，让外部 AI 根据纸面批改结果或口述反馈整理为同一份 `omrs-feedback` JSON。导入端兼容 AI 常见别名：`correct` 等价 `is_correct`，`score` 等价 `sub_score`。
- `session_id` 在 `SESSIONS` 中 → 自动选中 picker 并关联；不在列表（如 TMP- 临时卷）→ 仍以该 ID 提交写入历史，下拉里标「不在列表中」；无 ID → 按手动录入。导入的行替换当前批次后重绘，**不自动提交**——用户核对后点「提交反馈」。误贴旧题目 JSON 时提示当前只支持反馈 JSON。

提交后表单状态：
- 新题目创建成功后，清空全部输入框、两区图片与两处 AI 状态，难度滑块恢复为 5；保留创建成功提示。
  `#cr-result` 的成功提示里带「📋 加入展示板」按钮（调 `boardQuickAdd(uid)`），与收件箱提交后的
  入口一致；`boardQuickAdd` 未定义时不渲染该按钮。
- 反馈提交成功后，清空反馈行和 Session 选择状态；保留处理结果列表，便于核对本次提交。

## 收件箱录入流程（`assets/inbox.js`）

`#panel-create` 顶部是 `.ib-flow`：**上传 → 处理 → 录入**（编号真序列）+ AI 训练 + 快速录入；单题表单位于 `#ib-stage-quick`，所有 `#cr-*` id 与 `doCreate` / `crClassify` 等逻辑不变。新脚本 `assets/inbox.js` 排在 `data.js` 之后、`reports.js` 之前（依赖 `core.js` 的 `api`/`escapeHtml` 与 `questions.js` 的 `renderMdContent`）；`switchTab('create')` 调 `inboxInit()`。样式集中在 `styles.css` 末段，类名全部 `ib-` 前缀；画布标注色 `--ib-role-*` 固定不随主题。粘贴分流：`ibPaste`（捕获阶段）只在上传阶段拦截图片；`crHandlePaste` 只在快速录入阶段生效。设置页「AI 识别」分区有三个按用途的模型输入框（`#st-ai-model-detect/-extract/-classify`），随 `saveAiSettings` 一起保存。交互细节、job 轮询、沿用框位的像素锚定规则见 `AI/inbox.md` §5。处理页 / 队列脚 / 批量条有「▦ 模板框选」（`ibDetect(ids, 'template')`，零联网）；「AI 训练」页有盲标评估集与存储概览、清理按钮、以及「框选提供方与自动策略」表单（`.ib-pl-grid`，`ibLoadPolicy / ibSavePolicy` 读写 `/api/config` 的 `inbox_*` 键，与设置页共用同一 config）；大裁图自动改 JPEG。

后台文本提取完成后，处理页只更新发起提取的图片与区域结果；当前画布上的框选可以继续完成，不受完成通知影响。
