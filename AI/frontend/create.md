# 前端：录入题目与收件箱入口

> **速查**
> - 职责：五个工作区的导航、原图上传和快速录入；收件箱框选、题卡与训练流程见 `AI/inbox.md`
> - 入口：`assets/app/features/create/`（页面、上传、快速录入）、`assets/inbox.js`（收件箱列表和其余工作区）
> - 不变量：切页保留工作区与快速录入草稿；原图先入收件箱暂存层；快速录入提交后保留上下文字段，只清空题目内容与图片
> - 必跑测试：`tests/app/create.test.mjs`、`tests/e2e/create.py`、`tests/test_inbox.py`、`tests/test_ai_assist_taxonomy.py`
> - 相关：`AI/inbox.md`、`AI/frontend/architecture.md`、`AI/frontend/design-system.md`

## 页面与工作区

`#panel-create` 由 `features/create/index.js` 登记页面契约。`state.js` 与 `view.js` 渲染五个键盘可操作的工作区按钮：上传、处理、录入、AI 训练、快速录入。前三项按流程编号。切到其它页面后返回，导航仍显示离开前的工作区。收件箱列表、处理、题卡和训练仍由 `assets/inbox.js` 控制，其余工作区的结构暂留在 `omrs_dashboard.html`。

`upload.js` / `upload-view.js` 用 `ui/filedrop` 接受多张图片的选择与拖放。上传阶段也能粘贴图片或显式读取剪贴板；四种入口共用 `/api/inbox/upload`。非图片、剪贴板不可用和请求失败在控件旁提示；请求期间禁用入口。上传成功发 `inbox:reload`，旧列表据此刷新，重复图片由接口合并。上传原图不直接写入题库。

## 快速录入

`quick.js` 持有快速录入草稿、图片和当前粘贴目标；`quick-view.js` 渲染截图工作区与题卡内容双栏，窄屏改为单栏。题目和答案各有独立的 `ui/filedrop`、缩略图、移除按钮和显式读取剪贴板按钮。点击或聚焦图片区切换图片粘贴目标，默认题目区；只有当前页的快速录入工作区会捕获图片粘贴，文本粘贴保持浏览器原行为。

题目图片区读取第一张题目图：`/api/ai-recognize` 的 `classify` 模式填科目、分类、难度、知识点和标记；`question_text` 模式把题面填入文本框。答案图片区的 `answer` 模式读取第一张答案图，把解析填入答案框。分类识别把已填科目和分类作为 hint 发送，只填空缺项；知识点合并去重。识别请求失败、响应模式错误和空文本都在对应图片区显示原因。标记通过 `domain/labels` 打开共用选择器。

保存调用 `/api/create`，发送科目、分类、难度、页码、知识点、标记、题面、答案、错因，以及分开的 `question_images` 和 `answer_images`。必填科目和分类由前端预检。成功后只清空题面、答案、错因和两区图片；科目、分类、难度、知识点、标记和页码保留，方便连续录入。成功提示包含 UID、文件路径、图片数和「加入展示板」入口；同时刷新统计、历史和目录。按「重置」才清空整份草稿。

## 收件箱其余工作区

`assets/inbox.js` 继续处理收件箱网格筛选与批量操作、框选画布、检测和提取任务、题卡提交及训练策略，详细数据流与边界见 `AI/inbox.md` §5。后台文本提取只同步发起提取的图片与区域结果，不中断当前框选。全局 `cr-*` 图片数组与旧快速录入函数已删除；`core.js` 的 `populateCreateLists` 暂为旧收件箱题卡提供三个 datalist，待题卡迁移后删除。
