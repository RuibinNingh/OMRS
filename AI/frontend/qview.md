# 前端：共享题目视图 qview（domain/question）

> **速查**
> - 职责：题目 Markdown / KaTeX 渲染（内容哈希缓存）、练习记录、共享题目视图 qview、题目详情缓存、题目弹窗与翻页、Markdown 编辑器、画廊卡骨架
> - 入口：`assets/app/domain/question/index.js`（题面、记录、弹窗、编辑器）；错因交互与模板在同目录 `reflections.js`、`reflections-view.js`，样式在 `reflections.css`
> - 不变量：题面只经 `renderMd()` 渲染；练习记录只经 `qRecordsFromDetail()` 读取；反馈或历史修正后必须 `qvInvalidateMany()`；挂载点是尺寸容器，页面不再自补容器查询；模板不写 `style=`
> - 必跑测试：`tests/app/question.test.mjs`、`tests/app/rich-markdown.test.mjs`、`tests/app/run_browser.py`（对话框底座）、`tests/e2e/questions.py`、`tests/e2e/instant.py`、`tests/e2e/feedback.py`、`tests/e2e/reflection_layout.py`、`tests/e2e/notes_markdown.py`、`tests/e2e/reflection_dates.py`
> - 相关：`AI/frontend/architecture.md`（domain 层与过渡桥）、`AI/frontend/library.md`（题库页）

## 1. 模块

| 文件 | 内容 |
|---|---|
| `markdown.js` | `renderMd(text, mode)`（带缓存）、`renderMdUncached`、`renderMdInline`、表格、图片、KaTeX、`mdLineBreakMode()` |
| `math-text.js` | `normalizeMathDelimiters(text)`：成对 LaTeX 定界符转美元符号，与后端共用回归夹具 |
| `review-cycle.js` | `reviewCycle(item)`：共用复核档位、间隔、实际日期与累计成绩文案，停用题不显示周期 |
| `records.js` | `parseQHistory`、`qRecordsFromDetail`、`qHistoryStats`、`qStreakHtml`、`parseDay` |
| `view.js` | 纯函数：`qvHtml(detail, item, opts)`、`qvChips`、`qvToolsHtml`、`qvRecordHtml`、`qvCreationHtml`、`qvGalleryCard`、`qvGalleryIdHtml`、`QV_DEFAULTS`、`QV_CARD_OPTS` |
| `mount.js` | `ensureDetail`、`qvRender`、`qvInvalidate(Many)`、`qvRerenderAll`、`qvSetContext`、`bindQuestionDom()`（工具按钮委托、题图降级，并登记弹窗 ←/→） |
| `modal.js` | 题目弹窗（`ui/dialog` 外壳）：`viewQ(uid, context?, {returnFocus}?)`、`closeModal`、`modalOpen`、`modalUid`；翻页条与 ←/→（P5 第 3 轮起） |
| `editor.js` | Markdown 编辑器（`ui/dialog`）：`openEditor(uid)`、`closeEditor`、`editorOpen`（P5 第 3 轮起，原 questions.js 的 `.modal#md-editor`） |
| `ops.js` | 题目操作：`editQuestion`（打开 `editor.js` 的编辑器）、`suspendQuestion` / `resumeQuestion` / `deleteQuestion` / `moveQuestion`、`batchSuspend`、`exportA4`；确认走 `ui/dialog`，写后清缓存 → `reloadData()` → 失效重绘，并通过 `history:changed` 通知历史页与仪表盘刷新 |
| `index.js` | 对外出口；页面用 `mountQuestion`（即时练习）、`mountQuestionStage` 与 `mountReflections`（反馈录入）、`invalidateQuestions`，并转出 `ops.js` 全部与 `dropDetail`（删除 / 迁移后丢旧详情） |
| `qview.css` | `layer(domain)`：qview 的全部外观（布局与挂载点容器、题头、题面块、Markdown 段落 / 表格 / 题图、记录模块、战绩带、占位、别处容器的覆盖）与题目弹窗、编辑器外观（P5 第 4 轮起旧 `styles.css` 不再有 qview 规则） |

各页从 `index.js` 取。输出都是字符串，页面经 `raw()` 嵌入模板。

## 2. Markdown 渲染与缓存

题面与答案使用`markdown.js`的轻量渲染与缓存。「备注」先经`notes.js`移除错因节，再用`assets/app/domain/rich-markdown.js`的`richMarkdown(text, mode)`排版：支持标题、平铺有序/无序列表、加粗、斜体、引用、行内与围栏代码、http(s)/锚点链接；表格、图片和公式复用基础渲染。普通备注、关联与未知子节保留，围栏代码不按标题截断。备注沿用`mdLineBreakMode()`偏好，普通HTML转义，代码原样显示，只查看不回写Markdown。错因只在错因记录区显示；问题说明与错因历史复用同一安全子集，附件路由由问题域单独映射。

- 逐行渲染：普通文本默认保留每一处换行（`full`），输出为同一段中的 `<br>`；空行分段为 `<p class="md-p">`（连续空行只算一段），所以 Markdown 段落和 AI 的普通逐行文本都能直接显示。`lean` 是显式兼容选项，把单个换行当软换行接续；行尾两个空格在两种模式下都是硬换行。换行偏好归本模块：`mdLineBreakMode()` / `setMdLineBreakMode()`，存 `localStorage('omrs-qb-md-mode')`（键名沿用旧版；没有旧偏好时迁移到 `full`）；题库页「显示设置」切换后调 `qvRerenderAll()`。题库、录入预览、草稿审核、反馈、即时练习和展示板详情都复用这条渲染路径。
- 加粗：同一普通正文行或表格单元格内的成对双星号输出 `<strong class="md-strong">`，沿用正文颜色与半粗字重。加粗可包含行内公式；代码、公式和图片标记内部的星号及转义、未配对的标记按字面保留。源码编辑仍显示 Markdown 原文。
- 表格：表头 + 分隔行（`:?-{3,}:?`），`\|` 是单元格内竖线，输出 `.md-table-wrap > table.md-table`。
- 图片：`![[名.png|300]]` 与 `![说明](路径)`，只取文件名，输出 `<img class="md-img" data-omrs-image=… width=…>`；宽度上限 600，不写行内样式。加载失败时由 `bindQuestionDom` 的捕获监听换成 `.md-img-missing` 文件名提示。
- 公式：渲染前把同一行成对的 `\(...\)` 转为 `$…$`，把可跨行的 `\[...\]` 转为 `$$…$$`，不改变公式命令与正文换行；代码、已有美元公式、转义或未配对的定界符保留。`$…$`、`$$…$$`（可跨行）走 KaTeX；KaTeX 不可用时降级为 `<span class="math">` 源码。普通文本一律先转义，只生成题图、KaTeX 输出、降级公式和加粗等受控内容；兼容渲染不回写旧题目文件。
- 缓存键是规范化后的「换行模式 | 长度 | FNV-1a 哈希」，上限 600 条，最近使用的留下。KaTeX 还没加载时含公式的结果不进缓存，包括从反斜杠定界符转换的公式，免得降级结果粘住。`mdCacheStats()` 看命中，`clearMdCache()` 清空。`tests/app/math-delimiters.test.mjs` 验证转换、完整答案及延迟加载。

备注块用`.q-notes-md`恢复正常空白折叠，换行由渲染器决定；标题、列表与段落按阅读间距分隔，公式、表格与代码在各自容器内横滚。`tests/e2e/notes_markdown.py`从真实题库行打开合成题，验证格式、受控题图、HTML转义、旧文件字节不变及编辑保存重绘，并截图浅深主题1440/1024/390/320px。

## 3. qview

`opts` 默认值（`QV_DEFAULTS`）：`layout:'split'`（`'stack'` 单栏）、`reveal:true`、`showAnswer/showNotes/showHistory/showMeta:true`、`bare:false`、`actions:[]`、`clamp:0`。

- 结构：`.qv > .qv-head`（UID / chips / 工具栏）+ `.qv-q`（题目）+ `.qv-a`（答案 / 备注）+ `.qv-rec`（记录模块，通栏）+ `.qv-creation`（创建信息，完整详情视图显示）。`.qv-creation` 位于记录之后，显示 Markdown `录入日期` 和 Ledger 精确 `创建时间`；旧迁移题缺少精确时间时显示 `—`，时间按设置页 Ledger 时区格式化。
- `reveal:false` 不渲染答案 DOM，只给「显示答案」按钮（`opts.onReveal` 回调）。
- `actions`：`edit`、`board`、`labels`、`suspend`（按当前状态显示停用 / 恢复）、`delete`、`open`（关弹窗，经过渡桥 `questionsLoadPreset({'q-search': uid, …})` 切到题库并按 UID 搜索，停用题同时放开停用筛选）。按钮只带 `data-qv-act`，由 `mount.js` 的委托处理器调 `ops.js`（编辑、停用 / 恢复、删除）或旧全局（`boardQuickAdd`、`openLabelPicker`）。
- `bare:true` + `clamp:N` 给画廊缩略卡：去掉正文边框底色，正文写 `data-clamp="N"`（1–12），由 `qview.css` 的档位规则截断。
- 详情取不到时 `ensureDetail` 缓存一份带 `_fallback:true` 的降级副本，qview 显示「无法加载题目预览 + 重试」，重试即 `qvInvalidate`。
- 击杀题在到期chip后显示「复核第 N 档」，到期显示「复燃 · 第 N 档」；共用 `review-cycle.js`，显示当前档位和实际下次复核日。`due_date` 是实际排期，提前练习不延期；旧击杀题缺可靠日期时显示「待复核」。
- 画廊缩略卡和即时练习通过 `showCreation:false` / `showHistory:false` 隐藏创建信息；题目详情弹窗保留完整记录和创建信息，即使没有练习记录也显示该区块。

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

`<dialog id="modal">` 由 `ui/overlay` 的 `openModal` 打开：进浏览器顶层、背景 inert（焦点陷阱）、Esc 与点遮罩关闭、背景滚动锁定。结构是 `.ui-dialog--xl` 面板、头部（`.qv-nav` 翻页条、「＋错因」、关闭按钮）与 `.qv-dialog__body` 正文；正文包含 `#modal-stage` 挂载点（`tabindex=-1`，打开时拿初始焦点）和错因区。面板限制在视口内，正文占据头部以下剩余高度；滚动布局见「快捷错因与草稿」。题面内部公式和表格仍在各自块内横滚。只有一题时翻页条隐藏；手机上翻页按钮只留图标（`aria-label` 仍是「上一题 / 下一题」），可点区域40×40。

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
| 展示板滑入详情（`features/board/index.js`） | `qvRender(el, uid, {layout:'stack', showMeta:false, actions:[]})` |
| 复习调度「安排复习」画廊（`features/schedule/arrange-ctl.js`） | `qvRender(节点, uid, {...QV_CARD_OPTS, clamp:8})` |

画廊缩略预览容器 `.gallery-preview` 带 `white-space:pre-wrap`，而 qview 输出是多行模板，标签之间的空白文本节点在 pre-wrap 下不会折叠；旧 `styles.css` 用 `.gallery-preview .qv{white-space:normal}` 关掉，正文 `.qv .q-md` 自己声明 `pre-wrap` 保留题目里的换行。P5 第 4 轮起 qview 的全部外观都在 `qview.css` 并换成 token：题面 / 答案 `--text-lg` + `--leading-read`（设计系统的阅读正文），缩略卡（`bare`）`--text-sm`；题面块底色 `--surface-sunken`，答案块 `--success-subtle` / `--success-line`，战绩带 `--streak-ok` / `--streak-bad`。题头是 `<header>`，旧全局 `header{}` 在 legacy 层仍生效，所以内外边距、边框、对齐都显式写。旧页面容器（`.gallery-preview`、`.gallery-card`、`.sch-gallery-preview`）对 qview 的覆盖也在该文件末尾，随各页迁移删除。

## 稳定身份与缓存

`domain/question/ref.js` 冻结 `{question_id}`，共享写操作、标签选择器与 Markdown 编辑器在首个异步等待前保存它。详情读取可传 ID；缓存仍按显示 UID 提供兼容入口，但发现缓存 ID 与当前题目 ID 不同即失效。挂载状态保存固定 ID，旧 UID 被复用时不会加载新题正文，题面工具按钮沿用该挂载的身份。

`domain/question/picker.js` 是共享单题选择器；对候选快照搜索并显式确认稳定身份，目前由 Session 详情绑定入口使用。日期解析和战绩间隔共用 `core/date.js`，天差按日序号计算，夏令时不改变天数。

同一挂载点每次渲染以请求对象判定有效性，不能只比较 UID；同 UID 不同身份的迟到响应也会丢弃。`tests/e2e/audit_identity.py` 通过延迟旧身份详情、先完成新身份渲染复现并验证这个边界。

## 在途请求失效

详情失效同时移除该UID的缓存和在途token。旧响应返回后不能回填缓存或覆盖新的挂载，而是等待当前有效详情；旧请求的finally也不能删除新请求。全量失效包含只有在途请求、尚未产生缓存的UID。

## 快捷错因与草稿

共享控制器 `mountReflections(host, questionId, {idPrefix}?)` 同时用于题目弹窗与反馈判定栏，返回 `toggle`、`canLeave`、`dispose`；页面通过统一出口调用。默认页签 ID 使用题目身份，反馈页另加前缀，支持同题两处挂载而不重复 ID。每个宿主管理自身重绘与卸载，反馈页由路由和换题动作调用离开守卫。

弹窗正文先题目、后错因区。面板可用宽度至少1040px时，错因区占右侧340px，题面和答案在左侧上下阅读，两区分别滚动；不足时错因区顺排到题目后面，正文统一滚动，头部保持可见。头部「＋错因」切回录入并把编辑框滚入可视区，重复点击保持录入。翻题立即清除上一题的错因区，迟到的题目读取不能重新挂载旧身份的记录。

错因区默认「历史记录」，在前的历史页签显示条数，另一页签为「记录本次」。切换只改变面板显隐，复用编辑框并保留草稿、选区与展开状态。正文必填、问题关联可选；「关联问题」「更多信息」按需展开，后者可改发生日期、加附件或新建问题。新增与再次发生默认上海业务当天，保存后下一条重新取当天；可主动清空。历史标明「发生日期：…」，发生日期未知但有记录时间时显示「记录于…」，两者均未知显示「发生日期未知」；详情明确标注记录时间及发生日期，再展开来源、版本及再次发生、修订和撤回操作；AI假设提示始终显示。旧裸错因也纳入历史，不再在备注区重复显示；分页按游标读全。

Markdown编辑器携带原文content_hash保存，成功后派发题目身份通知，当前错因面板重新读取历史并保留未保存草稿；记录修订携带原题content_hash，拒绝覆盖期间的外部编辑。数据和Markdown格式见`AI/problems.md`、`AI/data.md`。打印与导出仍保留有效错因。

保存后清空当前草稿、恢复输入焦点并留在当前题连续录入；写入成功但历史刷新失败会明确提示已保存。草稿按稳定question_id存sessionStorage，写入失败和重试保持幂等编号，输入改变才换编号。Ctrl/⌘+Enter在输入法组合期间禁用；翻题、关闭、Esc与遮罩通过保存/放弃/继续编辑保护。

快捷录因切换修订或再次发生前也执行草稿保护；保存中禁用表单，避免在途编辑被清空。修订可修改关联问题和发生日期；用户可为AI错因补充明确确认依据，修订事件继续保留。

错因草稿的幂等编号复用`core/request-id.js`，通过getRandomValues兼容局域网HTTP。`tests/e2e/problems_http.py`验证真实非安全上下文的连续保存、刷新、390px表单无横向溢出，以及取消关闭保护后焦点回到触发关闭的按钮、草稿仍保留。

`tests/e2e/questions.py`同时验证共享弹窗的翻页、焦点陷阱、浮层和编辑器；390×844及320×640的长题用真实滚轮检查正文滚动、背景锁定、创建信息末尾和题后录入框可达性。

新默认值仅用于空白新表单；旧版保存后留下的无正文、无修订、无再次发生引用的空表单采用当天。有正文的旧草稿、补记日期、明确留空及修订历史保留原值；草稿格式标记区分新版主动留空，避免重开时补日期。日期与生产历史不做批量回填，浏览器专项见`tests/e2e/reflection_dates.py`。

反馈页的暂停计划只挂只读题面预览。题库及共享题面中的停用、恢复、归档或迁移成功后，同步刷新 Session 列表中的反馈处置。页面上有未保存错因时，反馈工作台等用户通过错因守卫后再采用新的计划快照。
