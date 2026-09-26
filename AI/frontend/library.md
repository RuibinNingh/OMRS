# 前端：题库、筛选与标记

> **速查**
> - 职责：题目库页（表格 / 画廊、筛选抽屉、批量、视图预设）、`filterItems()` 筛选语义、标记组件接入
> - 入口：`assets/app/features/questions/`（`index.js` 控制器与页面契约、`state.js` 状态与纯函数、`view.js` 外壳模板、`list.js` 表格 / 画廊、`dialogs.js`、`questions.css`）；题目操作 `assets/app/domain/question/ops.js`；筛选语义仍是 `assets/core.js::filterItems()`；标记芯片、颜色与选择器数据 `assets/app/domain/labels/`，选择器浮层与标记管理的 DOM 仍在 `assets/labels.js`
> - 不变量：所有列表共用 `filterItems()`（经 `domain/items.js::filterAll`）；默认隐藏停用题；偏好与视图预设的 localStorage 键名沿用旧版；表格视图不拉题目详情
> - 必跑测试：`node --test tests/app/questions.test.mjs`、`python3 tests/e2e/questions.py`、`node --test tests/app/labels.test.mjs`、`tests/test_question_suspend_frontend.js`
> - 相关：`AI/frontend.md`（索引）、`AI/frontend/qview.md`（题面渲染与弹窗）、`AI/frontend/architecture.md`（页面契约与过渡桥）

## 题目库页（`assets/app/features/questions/`，P5 第 2 轮起）

页面契约 `{ id: 'questions', workbench: true, mount, actions, keys }`：`mount()` 读偏好、建控制器、在根上委托整行点击，
每次状态变化 `paint()` → `morph(#panel-questions, view(state, env))`，之后 `afterPaint()` 补 DOM 属性
（全选框半选态、双滑块填充条的 `--lo / --hi`——不写 `style=`，R6），画廊视图再把题面挂载点交给 domain 的 `qvRender()`。
动作一律 `data-action="questions.*"`（`data-change` / `data-input` 同命名空间），没有内联事件、没有 `innerHTML`。

**状态**（`state.js`，模块单例 + 纯函数，`tests/app/questions.test.mjs` 全覆盖）：`filters`（页面自己的数据，不读 DOM）、
`live`（双滑块拖动中的预览值：只更新命中数与文案，松手 `change` 才并进 `filters` 重排）、`quick`（计数条快捷筛选）、
`prefs`、`selected`（跨筛选保留）、`cursor`、`drawer`、`menu`。`toItemFilters()` 把 `filters` 翻成 `filterItems()` 的条件形状，
`activeFilters()` 把「用户设了什么」转成 chips（滑块在两端、下拉为空都算未设；每项带 `kind` 供 `clearFilter()` 单独撤销）。

**布局**：一张卡 = 工作栏（搜索 `/`、「筛选」带条件数徽标、排序、表格 / 画廊、「列 / 密度」或「列数 / 密度」浮层、仅图标的
「重新扫描」`app.scan`）→ 计数条（逾期 / 待攻克 / 顽固题 / 停用四个快捷筛选，再点取消；顽固题是 `filterItems` 之后的后置过滤）
→ 条件 chips → 列表 | 抽屉。>1160 整屏工作台：卡片吃满剩余高度，只有列表与抽屉各自滚动，表头吸顶；≤1160 抽屉折到列表上方；
≤760 表格降级为卡片列表（D4：每格带 `data-label` 小标题，勾选 / 题目 / `⋯` 占第一行），全部可点目标 ≥40px，批量条铺满底部。

**筛选抽屉**：科目 / 分类 / 知识点下拉、标记芯片（点亮即选，≥2 个时出现「任一 / 全部命中」）、难度与熟练度双滑块
（`.qlb-dual`：两条 range 叠放，只有滑块本体可点；推一头越过另一头时带着走）、到期 / 状态 / 题目三组分段按钮、视图预设（一键应用、存为视图）。

**表格**：默认列勾选、UID / 科目·分类（顽固题标「顽固」）、标记（芯片 + 「＋」开标记选择器）、熟练度、到期、状态、`⋯`；

叠在模态对话框（题目弹窗）上时，标记选择器与标记管理经过渡桥 `__omrsUi.host` 放进对话框（`ui/overlay` 的客人），不被 inert；Esc 由 `ui/overlay` 代为关闭。不在对话框里时，选择器与标记管理的 Esc 由过渡桥 `installEscapeBridge` 处理（P5 第 3 轮起标记管理可按 Esc 关闭）。
难度、衰减后、次数、上次复习、EF 在列设置里打开；行密度舒适 / 紧凑。状态去掉 `状态/` 前缀，复燃题在状态后跟「复燃」chip
（`title` 写明第 N 次击杀后休眠 X 天复燃 · 原定日期；停用题不出）。**表格不拉题目详情**（一屏几十行各发一次 `/api/question` 不值），
「次数」列保持纯数字。整行点击（跳过勾选框、按钮、标记格）进题目弹窗，弹窗 ←/→ 翻页顺序就是当前列表顺序（`qvSetContext('q', uids)`）。行 / 画廊卡是 `tabindex=-1`（不进 Tab 序列）：弹窗关闭后游标移到最后看的那一题，焦点回到它的行（`viewQ(uid, 'q', {returnFocus})`）；聚焦的总是游标行，游标描边就是可见焦点。

**画廊**：卡片 = 勾选 + 标识（分类前缀弱化）+ 异常标（停用 / 复燃 / 逾期 / 今日 / 顽固，开元数据时另给「N 天后」）+ `⋯`、
可选元数据行、题面预览、脚注（熟练度、难度、战绩带或次数、标记）。列数自动或 1–6（`[` / `]` 步进；≤1160 最多 3 列、≤760 单列）。
题面预览挂载点 `data-morph="skip"`，key 编码「uid + 截断行数」，只有换题或换密度才重挂；截断走 qview 的 `clamp`（`data-clamp`，
舒适 5 / 紧凑 3 行，开元数据 8 / 6 行），溢出时挂载点加 `.is-clipped` 渐隐。**战绩带不额外发请求**：画廊本来就要为预览拉一次详情，
首次拉到详情的卡全部到齐后整页重绘一次，脚注由 `streakFoot()` 换成 `qStreakHtml()` + 记录数 +（连错 ≥2 时）「连错 N」；
记录来源 `detail.records[]`（Ledger 投影），`# 历史` 旧文本只在后端没给 `records` 时兜底。

**行内 `⋯` 菜单**（`ui/menu`）：查看详情 / 加入展示板 / 打标记 / 编辑 Markdown / 迁移分类 / 停用·恢复 / 删除。菜单项在 `setTimeout(0)`
之后执行——旧 `labels.js`、`board_picker.js` 在 document 上监听点击关闭各自的浮层，同一次点击里打开会被立刻关掉。

**批量条**（fixed 底部）：加入展示板（`B`，锚定选板浮层）、打标记（`L`，`ui/dialog`：勾选添加 / 移除，另可当场新建一个标记并添加）、
停用 / 恢复（逐题，失败计数）、导出 A4（不含答案）、清空（`Esc`）。

**键盘**（`core/keys.js` 作用域 `questions`）：`/` 聚焦搜索（搜索框里 `Esc` 先清空再失焦）、`F` 抽屉、`V` 视图、`[ ]` 画廊列数、
`↑↓` 行游标、Space 勾选游标行、Enter 打开、`B` / `L` 批量、`Esc` 依次关浮层 → 清空勾选 → 关抽屉。标记选择器打开时全部让位；
焦点在按钮上时 Space / Enter 交给按钮本身。

**偏好与视图预设**（只存本机，不上传）：视图 `omrs-q-view`、密度 `omrs-qb-density`、元数据 `omrs-qb-gallery-detail`、战绩带
`omrs-qb-streak`（缺省开）、列数 `omrs-qb-gallery-cols`、列 `omrs-qb-columns`；「恢复默认显示」保留视图、其余回默认。命名视图存
`omrs-question-views`，格式沿用旧版（`fields` 以旧元素 id `q-search`、`q-filter-subj`… 为键 + `labels` + 视图 / 列 / 密度 / 列数 /
战绩带 / 元数据 / 题面换行），旧版存下的视图照样能用；当前条件与某个视图一致时该视图按钮高亮。题面换行（简略 / 完整）是全站 qview
共用的偏好，归 `domain/question/markdown.js`（`omrs-qb-md-mode`），在浮层里切换后 `qvRerenderAll()`。

**旧入口**（过渡桥 `installQuestionsPageBridge`，P8 删除）：`renderQ()` / `filterQ()`（app.js 的 `reloadData`、labels.js 保存标记后）
改为发 `'questions:render'` 让已挂载的页重绘；`questionsLoadPreset(preset)`（qview 的 仪表盘不经过渡桥：切页后发 bus `questions:preset`，题库页挂载期间收到后同样先清空条件再套用（v1.25.0 起）。
「在题目库打开」）先清空全部条件再套用预设（键沿用旧元素 id），然后切到题库——停用筛选不会残留。

### 题目操作（`domain/question/ops.js`）

迁移分类（`POST /api/question/move`，后端按目标分类已有 UID 的最小缺口分配新 UID，`question_id` 与历史保留）、停用 / 恢复
（`POST /api/question/suspend` / `POST /api/question/resume`；停用题不进调度、统计与数据分析，列表里灰色虚线弱化）、删除（`/api/question/delete`，二次确认写明
删除 Markdown 正文、只保留 Ledger 归档与历史反馈、附件图片不删）、批量停用 / 恢复、批量导出 A4。确认与输入走 `ui/dialog`，结果走
`ui/toast`；成功后清详情缓存 → `reloadData()` → 失效重绘挂着该题的 qview → 刷新历史动态。题库页、题目弹窗与各处 qview 的工具按钮共用。

**Markdown 编辑器**在 `assets/app/domain/question/editor.js`（`ui/dialog`，P5 第 3 轮起；打开、保存与焦点规则见 `AI/frontend/qview.md` §4.2）：`GET /api/question/raw` 打开纯文本，保存 `POST /api/question/markdown`；只改正文时后端只更新 fingerprint，改 YAML 结构化字段写 metadata update commit。`questions.js` 只剩 `masteryBarHtml()`（board.js，P7 迁走）与 `reviveChipHtml()`（recommend_v2.js，P6 迁走）。

### 通用 Markdown / LaTeX 渲染
- `renderMdContent()` 只允许三类受控 HTML：图片 `<img>`、KaTeX 输出、降级公式 `<span class="math">`；普通文本始终先转义。
- 支持 Obsidian 图片 `![[name.png]]`、`![[name.png|300]]` 和 Markdown 图片 `![alt](path)`，图片名统一取 basename 后走 `/api/image?name=...`。
- 题图加载失败时，捕获 `img[data-omrs-image]` 的 `error` 事件并用 `textContent` 显示缺图文件名；图片名不进入内联 JavaScript。
- 支持行内 `$...$` 和行间 `$$...$$`，包括跨多行的 `$$` 块（先合并后再交给 KaTeX，`cases` 等环境不会被按行拆散）。KaTeX 加载成功时使用 `katex.renderToString(..., {throwOnError:false})`；加载失败时保留公式内容并加 `.math` 样式。
- 新代码用 `assets/app/domain/question/` 的 `renderMd()`（旧代码经过渡桥拿到同名全局 `renderMdContent()`，调用方见 `AI/frontend/qview.md`）；题目弹窗、调度 / 推荐预览、即时练习与题库画廊都复用它，不要再用 `<pre>${escapeHtml(...)}</pre>` 展示需要图片或公式的字段。

- 支持带表头和分隔行的 Markdown 表格（分隔单元格匹配 `:?-{3,}:?`，`\|` 表示单元格内竖线）。`renderMdContent()` 逐行识别后输出 `.md-table-wrap > table.md-table`，缺失单元格补空、超出表头的单元格忽略。
- 表格单元格继续走 `renderMdInline()`，因此文本先转义，图片和 LaTeX 仍遵循同一安全规则；小屏通过 `.md-table-wrap` 横向滚动。这里不是通用 Markdown 引擎，标题、粗体、列表等语法仍按普通文本显示。

## 筛选控件（`filterItems()`）

全局筛选，题库页（`state.js::toItemFilters()` 翻译条件）、调度页和即时练习页共用：

| 控件 | 对应字段 |
|---|---|
| 搜索词 | UID / 科目 / 分类 / 标签模糊匹配 |
| 科目 | `subject` |
| 分类 | `category` |
| 状态标签 | `tag` |
| 知识标签 | `knowledge_tags` |
| 难度上下限 | `difficulty` |
| 熟练度上下限 | `mastery` |
| 排序 | 多种排序方式 |

### 用户标记筛选

`filterItems()` 额外接受 `labels: string[]` 与 `labelMode: 'any'|'all'`。
全文搜索同时匹配标记名；`any` 为命中任一标记，`all` 要求全部命中。题库（经 `domain/items.js::filterAll`）、推荐、
导出选题、即时练习和展示板添加题目都复用这份筛选语义。

### 标记组件与接入

芯片由 `assets/app/domain/labels/chips.js` 生成（新代码 `labelChip(s)` 经 `raw()` 嵌入，旧代码用过渡桥挂的同名全局 `lblChip()` / `lblChips()`），`<=>` 双尖形，变体 soft（默认）/ solid / print，高 17 / 20（`lg`）/ 15px。颜色只写 `data-lbl-c="rrggbb"`：`sheet.js` 为每种用到的颜色往 `<style id="omrs-label-colors">` 的 `@layer domain` 块登记一条规则（`--lbl-c` / `--lbl-fg` / `--lbl-rgb` / `--lbl-ink-l` / `--lbl-ink-d`），模板不写 `style=`。`color.js::lblInk()` 按主题钳亮度保证 AA 对比度，`labelFg()` 为 solid 选 `--lbl-fg-dark` / `--lbl-fg-light`；预设色是 `tokens.css` 的 `--lbl-preset-1…10`（第 9 个灰色也是缺色时的默认）。选择器与管理的数据部分（排序、增改、候选、最近使用、快速区、下一个颜色、批量增删、表单规范化）在 `model.js`，都是纯函数（`tests/app/labels.test.mjs`）；芯片本身的形状与淡底仍在旧 `styles.css` 的 `.lbl`（P8 随 styles.css 搬）。

标记接入录入表单、收件箱题卡、题库、题目 Modal、反馈、即时练习、推荐、导出、
展示板、数据复盘和仪表盘。数据页显示按标记正确率/平均分，仪表盘显示活动题目的
标记分布；`boardPickerOpen()` 统一处理各页面的「加入展示板」入口，接受单个 UID 或 UID 数组；
`boardQuickAdd()` / `boardChooseAndAdd()` 是它的薄封装，调用点函数名不变。
