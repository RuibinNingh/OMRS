# 前端：共享题目视图 qview（domain/question）

> **速查**
> - 职责：题目 Markdown / KaTeX 渲染（内容哈希缓存）、练习记录、共享题目视图 qview、题目详情缓存、题目弹窗与翻页、Markdown 编辑器、画廊卡骨架
> - 入口：`assets/app/domain/question/index.js`（`markdown.js`、`records.js`、`view.js`、`mount.js`、`modal.js`、`editor.js`、`ops.js`、`qview.css`）
> - 不变量：题面只经 `renderMd()` 渲染；练习记录只经 `qRecordsFromDetail()` 读取；反馈或历史修正后必须 `qvInvalidateMany()`；挂载点是尺寸容器，页面不再自补容器查询；模板不写 `style=`
> - 必跑测试：`tests/app/question.test.mjs`、`tests/app/run_browser.py`（对话框底座）、`tests/e2e/questions.py`、`tests/e2e/instant.py`、`tests/e2e/feedback.py`
> - 相关：`AI/frontend/architecture.md`（domain 层与过渡桥）、`AI/frontend/library.md`（题库页）

## 1. 模块

| 文件 | 内容 |
|---|---|
| `markdown.js` | `renderMd(text, mode)`（带缓存）、`renderMdUncached`、`renderMdInline`、表格、图片、KaTeX、`mdLineBreakMode()` |
| `records.js` | `parseQHistory`、`qRecordsFromDetail`、`qHistoryStats`、`qStreakHtml`、`parseDay` |
| `view.js` | 纯函数：`qvHtml(detail, item, opts)`、`qvChips`、`qvToolsHtml`、`qvRecordHtml`、`qvGalleryCard`、`qvGalleryIdHtml`、`QV_DEFAULTS`、`QV_CARD_OPTS` |
| `mount.js` | `ensureDetail`、`qvRender`、`qvInvalidate(Many)`、`qvRerenderAll`、`qvSetContext`、`bindQuestionDom()`（工具按钮委托、题图降级，并登记弹窗 ←/→） |
| `modal.js` | 题目弹窗（`ui/dialog` 外壳）：`viewQ(uid, context?, {returnFocus}?)`、`closeModal`、`modalOpen`、`modalUid`；翻页条与 ←/→（P5 第 3 轮起） |
| `editor.js` | Markdown 编辑器（`ui/dialog`）：`openEditor(uid)`、`closeEditor`、`editorOpen`（P5 第 3 轮起，原 questions.js 的 `.modal#md-editor`） |
| `ops.js` | 题目操作：`editQuestion`（打开 `editor.js` 的编辑器）、`suspendQuestion` / `resumeQuestion` / `deleteQuestion` / `moveQuestion`、`batchSuspend`、`exportA4`；确认走 `ui/dialog`，写后清缓存 → `reloadData()` → 失效重绘，并通过 `history:changed` 通知历史页与仪表盘刷新 |
| `index.js` | 对外出口；另有页面用的 `mountQuestion`（即时练习）、`mountQuestionStage`（反馈录入）、`invalidateQuestions`，并转出 `ops.js` 全部与 `dropDetail`（删除 / 迁移后丢旧详情） |
| `qview.css` | `layer(domain)`：qview 的全部外观（布局与挂载点容器、题头、题面块、Markdown 段落 / 表格 / 题图、记录模块、战绩带、占位、别处容器的覆盖）与题目弹窗、编辑器外观（P5 第 4 轮起旧 `styles.css` 不再有 qview 规则） |

各页从 `index.js` 取。输出都是字符串，页面经 `raw()` 嵌入模板。

## 2. Markdown 渲染与缓存

- 逐行渲染：空行分段为 `<p class="md-p">`（连续空行只算一段）；`lean`（默认）把单个换行当软换行接续，`full` 保留每一处换行；行尾两个空格是硬换行。换行偏好归本模块：`mdLineBreakMode()` / `setMdLineBreakMode()`，存 `localStorage('omrs-qb-md-mode')`（键名沿用旧版）；题库页「显示设置」切换后调 `qvRerenderAll()`。
- 表格：表头 + 分隔行（`:?-{3,}:?`），`\|` 是单元格内竖线，输出 `.md-table-wrap > table.md-table`。
- 图片：`![[名.png|300]]` 与 `![说明](路径)`，只取文件名，输出 `<img class="md-img" data-omrs-image=… width=…>`；宽度上限 600，不写行内样式。加载失败时由 `bindQuestionDom` 的捕获监听换成 `.md-img-missing` 文件名提示。
- 公式：`$…$`、`$$…$$`（可跨行）走 KaTeX；KaTeX 不可用时降级为 `<span class="math">` 源码。普通文本一律先转义，只放行图片、KaTeX 输出和降级公式三类 HTML。
- 缓存键是「换行模式 | 长度 | FNV-1a 哈希」，上限 600 条，最近使用的留下。KaTeX 还没加载时含 `$` 的结果不进缓存，免得降级结果粘住。`mdCacheStats()` 看命中，`clearMdCache()` 清空。

## 3. qview

`opts` 默认值（`QV_DEFAULTS`）：`layout:'split'`（`'stack'` 单栏）、`reveal:true`、`showAnswer/showNotes/showHistory/showMeta:true`、`bare:false`、`actions:[]`、`clamp:0`。

- 结构：`.qv > .qv-head`（UID / chips / 工具栏）+ `.qv-q`（题目）+ `.qv-a`（答案 / 备注）+ `.qv-rec`（记录模块，通栏）。
- `reveal:false` 不渲染答案 DOM，只给「显示答案」按钮（`opts.onReveal` 回调）。
- `actions`：`edit`、`board`、`labels`、`suspend`（按当前状态显示停用 / 恢复）、`delete`、`open`（关弹窗，经过渡桥 `questionsLoadPreset({'q-search': uid, …})` 切到题库并按 UID 搜索，停用题同时放开停用筛选）。按钮只带 `data-qv-act`，由 `mount.js` 的委托处理器调 `ops.js`（编辑、停用 / 恢复、删除）或旧全局（`boardQuickAdd`、`openLabelPicker`）。
- `bare:true` + `clamp:N` 给画廊缩略卡：去掉正文边框底色，正文写 `data-clamp="N"`（1–12），由 `qview.css` 的档位规则截断。
- 详情取不到时 `ensureDetail` 缓存一份带 `_fallback:true` 的降级副本，qview 显示「无法加载题目预览 + 重试」，重试即 `qvInvalidate`。
- 复燃题在到期 chip 之后追加「复燃 · 已休眠 N 天」：复燃题的 `Due_Date` 是击杀时的旧值，只看「逾期 N 天」会读成没做完的旧账。

### 3.1 布局：挂载点是容器

`qvRender` 给挂载点标 `data-qv-mount`；布局为双栏时，`qview.css` 让挂载点成为名为 `qv` 的 inline-size 容器，挂载点窄于 680px 时 `.qv-split` 塌成单栏。同一组件进 1180px 的题目弹窗、约 420px 的反馈中栏和手机屏幕，各处按自己的挂载点宽度决定，页面不用再补容器查询。单栏的画廊缩略卡不建容器。

超宽内容：整行公式（`.katex-display`）只在自己的块里横滚；段落里的其它超宽内容在该段 `.q-md` 内横滚（截断卡片除外）。挂载点和页面都不会被撑出横向滚动。

### 3.2 记录模块

题目详情最下面的通栏块：练习次数、正确率、平均主观分、平均间隔四个数，主观分走势（SVG），明细首屏 3 条、其余折叠。只报异常：末尾连错 ≥2 才出提示行。

数据源是 `qRecordsFromDetail(detail)`：`detail.records` 是数组就以它为准（空数组 = 后端明确说没练过，显示「还没练过。」）；只有老后端没给 `records` 时才解析 Markdown「## 历史」旧行，解析不出时 `<pre class="qv-rec-raw">` 原样保留。返回数组带 `source:'ledger'|'markdown'`。

战绩带 `qStreakHtml(records, max=8)`：一根竖条一次练习，绿对红错，高度档位 `data-h`（0–9，对应主观分 0–10，3px 起每档 +1px），更早的淡出。画廊脚注与记录模块共用。

## 4. 挂载、失效与弹窗

| 接口 | 说明 |
|---|---|
| `qvRender(target, uid, opts)` | 选择器或元素；拉详情 → 渲染 → 登记；期间切到别的题则丢弃晚到的结果；uid 为空时清空并注销 |
| `qvInvalidate(uid)` / `qvInvalidateMany(uids?)` | 清详情缓存并重绘挂着它的视图；不给 uids 清全部。反馈提交、即时练习提交（经 `invalidateQuestions`）、历史修正、停用 / 恢复 / 保存 Markdown 后调用 |
| `qvRerenderAll()` | 不动缓存，按当前显示设置（如换行模式）重画所有挂载点 |
| `qvSetContext(name, uids)` | 登记一段 uid 序列供弹窗翻页：`'q'`（题库表格 / 画廊当前筛选）、`'export'`、`'export-selection'`、`'leech'` |
| `viewQ(uid, context?, options?)` | 打开题目弹窗（见 §4.1）；context 可传数组或上下文名，不传时弹窗开着就沿用当前翻页序列；`options.returnFocus(uid)` 返回关闭后接焦点的元素 |

详情缓存归 `mount.js`（v1.25.0 起）：模块内的两个对象，`ensureDetail()` 去重拉取、`dropDetail()` 失效；旧画廊、展示板、导出读的 `QUESTION_CACHE` / `QUESTION_PENDING` 是过渡桥 `installDataBridge` 挂的只读全局，指向同一对象（`detailCacheObject()` / `pendingDetailsObject()`）。

### 4.1 题目弹窗（modal.js）

`<dialog id="modal">` 由 `ui/overlay` 的 `openModal` 打开：进浏览器顶层、背景 inert（焦点陷阱）、Esc 与点遮罩关闭、背景滚动锁定。结构是 `.ui-dialog--xl` 面板 + 头部（`.qv-nav` 翻页条、关闭按钮）+ `#modal-stage` 挂载点（`tabindex=-1`，打开时拿初始焦点，题面区单独滚动）。只有一题时翻页条隐藏；手机上翻页按钮只留图标（`aria-label` 仍是「上一题 / 下一题」），可点区域 40×40。

关闭后焦点先交给 `returnFocus(当前题)` 返回的元素（题库页把游标移到最后看的那题并交出它的行），没有或已脱离文档时还给打开前的焦点。关闭时立刻去掉 `id`，退场动画期间再打开也不会出现两个 `#modal`。

快捷键：`←/→` 翻页登记在 `core/keys.js` 的 `global` 作用域（`inDialog:true`）；弹窗不在最上层（编辑器、确认框叠在上面）或有客人浮层时让位，输入框里不触发。`Esc` 由 `ui/overlay` 在捕获阶段处理，页面与全局的 Esc 处理函数都收不到。

叠在弹窗上的旧浮层（标记选择器、选板浮层、标记管理）经过渡桥 `__omrsUi.host(node, {close, escape})` 放进弹窗（`ui/overlay` 的客人，见 `AI/frontend/components.md` §4），不会被 inert；Esc 与点外面先关浮层，弹窗关闭时一并关掉浮层，浮层关掉后焦点回到打开它的按钮。

### 4.2 Markdown 编辑器（editor.js）

`openEditor(uid)`：`GET /api/question/raw` 取原文，打开 `dialog({id:'md-editor', size:'xl'})`，从题目弹窗打开时是叠上去的第二个模态对话框。保存（「保存」、Enter 以外的 Ctrl / ⌘ + Enter）走 `onOk`：`POST /api/question/markdown` → 清详情缓存 → `reloadData()` → `qvInvalidate`；失败留在编辑器、状态行写原因；内容没改直接关闭。有未保存修改时 `dismissible()` 为假：Esc 与点遮罩不关、状态行提示，「取消」与关闭按钮照常关闭。关闭后焦点回到「编辑」按钮（qview 重绘换掉了原按钮时，交给同一挂载点里新的）。旧代码的 `closeMarkdownEditor()` 经过渡桥保留（E2E 收尾用）。

## 5. 调用点

| 调用点 | 用法 |
|---|---|
| 题目弹窗 `viewQ`（modal.js） | `{layout:'split', actions:['edit','board','labels','suspend','delete']}` |
| 反馈录入（`features/feedback`） | `mountQuestionStage` = `{layout:'split', actions:['edit','board','labels','suspend','open']}` |
| 即时练习（`features/instant`） | `mountQuestion` = `{layout:'split', reveal, showMeta:false, showHistory:false, actions:['edit','board','labels'], onReveal}`：练习中不显示记录，免得未答先看见历史分数 |
| 题库画廊（`features/questions`） | 挂载点 + `qvRender(el, uid, galleryCardOpts(prefs))`（`bare`、`clamp` 随密度 / 元数据 3–8 行）；卡片外壳由页面自己画，见 `AI/frontend/library.md` |
| 导出选题、展示板画廊 | `qvHtml(detail, item, 卡片预设)` + `qvGalleryCard(spec)` |
| 复习调度「安排复习」画廊（`features/schedule/arrange-ctl.js`） | `qvRender(节点, uid, {...QV_CARD_OPTS, clamp:8})` |

画廊缩略预览容器 `.gallery-preview` 带 `white-space:pre-wrap`，而 qview 输出是多行模板，标签之间的空白文本节点在 pre-wrap 下不会折叠；旧 `styles.css` 用 `.gallery-preview .qv{white-space:normal}` 关掉，正文 `.qv .q-md` 自己声明 `pre-wrap` 保留题目里的换行。P5 第 4 轮起 qview 的全部外观都在 `qview.css` 并换成 token：题面 / 答案 `--text-lg` + `--leading-read`（设计系统的阅读正文），缩略卡（`bare`）`--text-sm`；题面块底色 `--surface-sunken`，答案块 `--success-subtle` / `--success-line`，战绩带 `--streak-ok` / `--streak-bad`。题头是 `<header>`，旧全局 `header{}` 在 legacy 层仍生效，所以内外边距、边框、对齐都显式写。旧页面容器（`.gallery-preview`、`.gallery-card`、`.sch-gallery-preview`）对 qview 的覆盖也在该文件末尾，随各页迁移删除。
