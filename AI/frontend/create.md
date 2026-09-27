# 前端：录入题目与收件箱工作台

> **速查**
> - 职责：录入页五个工作区（上传、处理、录入、AI 训练、快速录入）的界面、收件箱前端数据与保存队列；后端流程见 `AI/inbox.md`
> - 入口：`assets/app/features/create/`（`index.js` 页面契约，`inbox.js` / `inbox-store.js` 收件箱数据，其余按工作区分文件）
> - 不变量：原图先入收件箱暂存层，提交后才写题库；切页保留工作区、当前图、勾选与快速录入草稿；离开处理区或本页前写出未到防抖时间的改动；创建后保留上下文字段
> - 必跑测试：`tests/app/create.test.mjs`、`tests/app/create-process.test.mjs`、`tests/app/create-inbox.test.mjs`、`tests/e2e/create.py`、`tests/test_inbox.py`、`tests/test_ai_assist_taxonomy.py`
> - 相关：`AI/inbox.md`、`AI/frontend/architecture.md`、`AI/frontend/design-system.md`

## 页面与工作区

`#panel-create` 在 HTML 里只有导航 `#create-flow` 和五个空的 `.ib-stage` 区块，内容全部由 `features/create/index.js` 挂载。导航由 `state.js` / `view.js` 渲染五个按钮（`data-action="create.stage"`），前三项按流程编号并显示待处理、已框选、待创建三个计数。当前工作区存在收件箱单例的 `stage` 里，切到其它页面后返回仍停在原处；进入 AI 训练时重读统计与策略。

录入页的快捷键登记在页面契约的 `keys` 里，只在处理区生效：`Q` / `A` / `X` 切画框角色、`Delete` / `Backspace` 删除选中框、`Enter` 下一张、`⌘/Ctrl + Enter` 转换文本、`Esc` 取消选中框。

## 收件箱数据（`inbox-store.js` / `inbox.js`）

`createInboxStore({ api, emit, notify, timers })` 是收件箱在前端的唯一所有者，I/O 全部注入，node 测试直接构造；`inbox.js` 用 `core/api` 与 `ui/toast` 建模块级单例，挂载时 `connectInbox(bus)` 接上通知通道。状态包括图片列表、网格与处理区共用的勾选、当前图、选中框、画框角色与题卡、题卡勾选和「上一张」。任何改动都发 `inbox:changed`，各工作区控制器按需重绘。

保存队列沿用旧 `ibSaveSoon` 的语义：同一张图的补丁在防抖期内合并（`cards` 按题卡合并），同一张图的请求串行；每次改动递增修订号，响应只在修订号未变时回写服务端版本。正在拖动当前图的框时只同步状态，不替换对象。`flush()` 在离开处理区、离开本页和创建题目之前调用。后台任务 `job(type, payload, onDone)` 每 1.2 秒轮询一次，同一任务不会并发轮询；失败项与轮询错误都经提示报告。

`inbox-ops.js` 放网格、处理区和题卡共用的操作：AI / 模板框选（非模板时先按 `slice-plan` 切条带）、沿用框位、整图即题目、文本提取、题卡分类识别。`crop.js` 在浏览器里裁图，超过约 150 万像素的 PNG 改 JPEG 0.9 白底；预览 canvas 带 `data-crop="图片|区域"`，按框位键只在框变化时重画。

## 上传与收件箱网格

`upload.js` / `upload-view.js` 用 `ui/filedrop` 接受多张图片的选择与拖放；上传工作区也能粘贴图片或显式读取剪贴板，四种入口共用 `/api/inbox/upload`。非图片、剪贴板不可用和请求失败在控件旁提示；请求期间禁用入口。上传成功发 `inbox:reload`，页面重读收件箱，重复图片由接口合并。

`grid.js` / `grid-view.js` 渲染原图卡片和框位预览，提供全部、待处理、已框选、待创建、已录入五种筛选。全选只选当前筛选里未录入的图片；批量条只处理已选图片，包含 AI / 模板框选、沿用框位、整图即题目、去处理、丢弃和清空选择。已录入卡片打开关联题目；批量丢弃失败时保留选择并在网格旁提示。

## 处理（框选）

`process-view.js` 挂三栏骨架：队列、画布、区域面板。`process.js` 负责本张图的全部编辑：切图、角色、整图、沿用上一张、清空、新题卡、删除框、保存方式（转文本 / 保留图片 / 让 AI 判断）、文本编辑、提取、丢弃与标记就绪。队列行与区域卡片由 `process-content.js` 渲染，事件都是 `data-action` / `data-change` / `data-input`；点在复选框、输入框上时不触发整行动作。

画布在 `data-morph="skip"` 的 `#ib-stage-img` 里，原图与 SVG 框位由 `process-canvas.js` 直接渲染，指针手势（画框、移动、八向缩放）只由它处理，坐标为 0–1（纯函数在 `process-state.js`）。拖动时不重绘面板，松手后状态随框数更新并去抖保存。保留图片的区域在面板里显示裁图预览（外层 skip，键含框位）。标记就绪时先等提取完成，保存成功后记为「上一张」并切到下一张未就绪的图。

## 录入（题卡）

`cards-state.js` 从就绪图片按题卡分组，已创建的题卡跳过，缺表单时就地补默认表单。`cards-view.js` 每张题卡一行：左边是题目 / 答案预览（转文本的区域渲染 Markdown，带 `data-hash`；保留图片的区域画裁图），右边是科目、分类、难度、知识点、标记、错因和页码。科目、分类、知识点有取自题库的 datalist 提示。`cards.js` 把字段去抖 600ms 写进收件箱的 `cards`，写入路径随科目分类即时更新。

标记经 `domain/labels` 的录入选择器改。「AI 识别题目信息」用题卡第一个题目区域提交 classify 任务，完成后重读收件箱，服务端只填空缺项。「退回处理」把图片改回已框选并打开处理区。创建前先预检科目、分类，再 flush 待存改动，裁出保留图片的区域，随 `/api/inbox/commit` 上传。单张成功弹一条带「加入展示板」的提示；批量逐张提交，最后只弹一条汇总，「加入展示板（N 题）」一次加入这批新题。成功后刷新统计、历史和目录。

## AI 训练

`train.js` 在进入工作区时读 `/api/inbox/dataset/stats` 与 `/api/config`。`train-state.js` 把统计换成展示模型：四张指标卡（`ui/stat`）、版式与转换决策条（原生 `<progress>`）、盲标评估集与存储文案。导出是一个随格式变化的下载链接（OMRS JSONL / YOLO）。清理超期丢弃图直接执行；清空裁图缓存先确认。统计或策略读取失败时在原位显示原因和「重试」。

「框选提供方与自动策略」表单用 `ui/field`、`ui/select`、`ui/switch`：选 `local_http` 时才显示本地检测地址。保存时把阈值夹到合法范围，写 `/api/config` 的 `inbox_*` 键，结果就地显示。

## 快速录入

`quick.js` 持有快速录入草稿、图片和当前粘贴目标；`quick-view.js` 渲染截图工作区与题卡内容双栏，窄屏改为单栏。题目和答案各有独立的 `ui/filedrop`、缩略图、移除按钮和显式读取剪贴板按钮。点击或聚焦图片区切换粘贴目标，默认题目区；只有当前页的快速录入工作区会捕获图片粘贴，文本粘贴保持浏览器原行为。

题目图片区读取第一张题目图：`/api/ai-recognize` 的 `classify` 模式填科目、分类、难度、知识点和标记；`question_text` 模式把题面填入文本框。答案图片区的 `answer` 模式读取第一张答案图，把解析填入答案框。分类识别把已填科目和分类作为 hint 发送，只填空缺项；知识点合并去重。识别失败、响应模式错误和空文本都在对应图片区显示原因。

保存调用 `/api/create`，发送科目、分类、难度、页码、知识点、标记、题面、答案、错因，以及分开的 `question_images` 和 `answer_images`。科目和分类由前端预检。成功后只清空题面、答案、错因和两区图片，其余字段保留，方便连续录入。成功提示含 UID、文件路径、图片数和「加入展示板」入口（`domain/board` 的 `boardQuickAdd`，Shift + 点击直接加进上次用的板）；同时刷新统计、历史和目录。按「重置」才清空整份草稿。

## 样式

样式都在 features 层：`create.css`（导航、工作区显隐与整屏工作台、上传、快速录入、网格）、`process.css`（处理区，作用域 `#ib-stage-process`）、`cards.css`（`crc-`）、`train.css`（`crt-`）。只用 token；标注色取 `--info` / `--success` / `--danger`。旧 `styles.css` 里已没有录入页的规则。
