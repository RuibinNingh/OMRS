# 2026-09-25 前端重构 P5：共享题目视图迁到 domain/question；题目库迁到 features/questions；计划文件夹入库；题目弹窗与 Markdown 编辑器换 ui/dialog；标记迁到 domain/labels、qview 外观归位

---

## 项目基本信息

| 项 | 值 |
|---|---|
| 项目名 | OMRS（Obsidian Mistake Reconstruction System）|
| 当前版本 | v1.23.0（P5 第 2 轮交付时升 v1.24.0，第 3 轮升 v1.24.1，第 4 轮升 v1.24.2；第 1 轮不改版本号）|
| 类型 | 个人错题本，Markdown + 本地 HTTP 服务 |
| 后端入口 | `omrs_engine.py` |
| 前端文件 | `omrs_dashboard.html`（结构）+ `assets/`（旧脚本与 `styles.css`）+ `assets/app/`（ES Module：core、ui、domain、features、外壳、过渡桥）|
| 数据目录 | 结构化数据在 `错题/.omrs/`；生成的 AI 报告在 `错题/report/` |
| 依赖边界 | 核心 Python 运行路径无强制第三方库；前端无构建依赖；浏览器单测、E2E 与截图需要 playwright + Chromium（可选，缺失时跳过）|

---

## 执行者与模式

- 执行者：Claude（claude.ai 沙箱，等同 CCW）。**受限模式**：源码来自 P4 交付的完整包 `OMRS-v1.23.0-2026-09-25.zip`，无网络、无 systemd、碰不到生产与 Git 远端。
- 基线：解压后 `git init` 提交 `1f07f3c`（v1.23.0）。补丁 ⑥ 在该基线上可干净反向应用，确认完整包已含 P4。开工门禁与交接文档 §3.2 逐项一致：unittest 156、node 171、浏览器 31、shell_router 20、ui_bridge 15、instant 23、feedback 31、check_ui 0（存量 244/161/215/185/355）、check_contrast 54 组 0 不达标、check_docs 0 问题 1 提醒。
- 后端零改动，接口与数据格式不变。

## 第 1 轮（本日志；第 2 轮在下方续写）

### 用户诉求

- 用户原话：「建议在文档里面放计划文件，每个计划可以是一个文件夹表示总计划，然后里面任务进度维护」「执行吧」。
- 原计划 P5 第一条：`domain/question/`，Markdown 和 KaTeX 按内容哈希缓存，qview 与记录模块迁入；交接文档 §3.3 遗留：根治 qview 容器查询与超宽公式，删掉页面补丁。

### 行为变化（用户可见）

- 题目弹窗在窄屏（挂载点 <680px，手机即是）改为单栏；改前手机上仍是挤在一起的双栏。
- 所有 qview（题目弹窗、反馈录入、即时练习、推荐预览）里整行超宽的公式只在自己的块里横滚，页面不被撑出横向滚动；改前只有反馈录入页有补丁。
- 题图写了宽度（`![[图.png|300]]`）时按该宽度显示（与 Obsidian 语义一致）；改前是「不超过该宽度」，原图比写的宽度小时不放大。原图更宽时两者一样。
- 题图缺失提示改用类名（外观不变）。

### 架构

| 文件 | 说明 |
|---|---|
| `assets/app/domain/question/markdown.js` | 从 `questions.js` 迁入的 Markdown / 表格 / 图片 / KaTeX 渲染；`renderMd` 按「换行模式 + 长度 + FNV-1a」缓存（上限 600，LRU）；KaTeX 未就绪时含公式的结果不缓存 |
| `assets/app/domain/question/records.js` | 从 `core.js` 迁入 `parseQHistory` / `qRecordsFromDetail` / `qHistoryStats` / `qStreakHtml`；战绩带高度改 `data-h` 档位 |
| `assets/app/domain/question/view.js` | 从 `qview.js` 迁入的纯函数：`qvHtml`、chips、工具栏、记录模块、画廊卡骨架；截断改 `data-clamp` |
| `assets/app/domain/question/mount.js` | 详情缓存 `ensureDetail`（读写旧 `QUESTION_CACHE`，请求走 `core/api.js`）、`qvRender` / 失效 / 重绘、题目弹窗 `viewQ` / `closeModal` 与翻页、按钮委托、题图降级、弹窗 ←/→（`core/keys.js`，`inDialog:true`）|
| `assets/app/domain/question/index.js` | 出口；原 `domain/questions.js` 的 `mountQuestion` / `mountQuestionStage` / `invalidateQuestions` / `editQuestion` 并入（旧文件删除）|
| `assets/app/domain/question/qview.css` | `layer(domain)`：双栏时挂载点是 `qv` 容器；超宽公式；截断与战绩带档位；题图 |
| `assets/app/legacy-bridge.js` | 新增 `installQuestionBridge`：20 个同名全局逐条注明调用方 |
| 删除 | `assets/qview.js`、`assets/app/domain/questions.js`；`questions.js` 的渲染 / 详情 / 弹窗 63 行；`core.js` 的记录函数；`styles.css` 里 `.qv` 自身的容器声明与从不生效的 `@container` / `@supports` 块；`instant.css`、`feedback.css` 的挂载点补丁 |

计划文件夹：`AI/plans/README.md`（约定）、`AI/plans/frontend-rearch/plan.md`（原计划，只加一行指向进度）、`AI/plans/frontend-rearch/progress.md`（进度，取代包外交接文档里的大部分内容）。`tests/check_docs.py` 新增规则 9（计划文件夹两件齐全、`progress.md` 状态块），计划文档不查路径存在、不计入路由说明；`AGENTS.md` 加开工读 `progress.md` 与收尾第 9 条，映射表加 `assets/app/domain/question/` → `AI/frontend/qview.md`。

### 测试

- `tests/test_md_linebreaks.js`（8）、`test_question_record_ui.js`（13）、`test_qview_gallery.js`（5）合并为 `tests/app/question.test.mjs`（34）：新增渲染缓存、KaTeX 缺席不缓存、哈希、题图无行内样式、战绩带档位、clamp 档位、reveal:false、降级重试。旧 `questions.js` 画廊脚注两条经 `createRequire` 加载旧文件测。
- 新增 `tests/e2e/questions.py`（第 1 轮 23 项）：题库点行开弹窗、桌面双栏、←/→ 翻页、Esc；420px 挂载点单栏、900px 恢复双栏、超宽公式块内横滚且挂载点不溢出、题图缺失；画廊截断走 `data-clamp`、无行内样式；手机弹窗单栏、无横向滚动；脚本错误 0。
- `tests/e2e/ui_bridge.py` 的分层断言加上 `domain`（P5 起该层有样式表）。

### 过程中的坑

- 新 E2E 初版把 LaTeX 写成 `\\frac`（Python 字符串里多转义一层），KaTeX 把 `\\` 当换行，公式不够宽，断言「块内横滚」失败；改成 `\frac` 后通过。
- 翻页断言在键盘事件后立刻读题面 uid，详情尚未取回时挂载点里只有加载占位，读到 None；改为等条件成立。

### 验证（第 1 轮，已实际执行）

| 命令 | 结果 |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 156 OK |
| `node --test tests/*.js tests/app/*.test.mjs` | 179 / 179（删 3 个旧文件共 26 个用例，新增 `question.test.mjs` 34 个）|
| `python3 tests/app/run_browser.py` | 31 / 31 |
| `python3 tests/e2e/shell_router.py` | 20 / 20 |
| `python3 tests/e2e/ui_bridge.py` | 15 / 15（分层断言加 `domain` 后）|
| `python3 tests/e2e/instant.py` | 23 / 23（全量那次「标记筛选」22，单独重跑 23；交接文档记载的已知偶发）|
| `python3 tests/e2e/feedback.py` | 31 / 31 |
| `python3 tests/e2e/questions.py` | 23 / 23（连跑两次）|
| `python3 tests/check_ui.py` | 0 处问题；存量下调为 handlers 244、html_assign 157、inline_style 211、color_literals 185、font_size_literals 354 |
| `python3 tests/check_contrast.py` | 54 组，0 不达标 |
| `python3 tests/check_docs.py --diff 1f07f3c` | 0 处问题，1 条提醒（`AI/api.md` 53KB）|
| `python3 tests/visual/run.py --ref 1f07f3c` | 48 张 0 张有差异；页面脚本错误无（12 页不打开题目弹窗，qview 的变化在下面的专拍里）|
| 题目弹窗改前 / 改后专拍（`git worktree` 起 v1.23.0 实例，同一 fixture，题面注入一行超宽公式） | 手机 390：改前双栏、公式溢出题面卡片压到弹窗边缘；改后单栏、公式在块内横滚。桌面 1440：两者都是双栏。浅 / 深色各一张，均无页面横向滚动 |

未执行：生产部署、远端 / 手机真机验收（按流程归 Hermes，在最后一次部署时做）。

## 第 2 轮（CCW · 受限，基线 P5 第 1 轮中间包 `OMRS-v1.23.0-p5r1-2026-09-25.zip`）

### 用户诉求

- 「那继续p5」→ 执行 `AI/plans/frontend-rearch/progress.md` §5 第 2 轮任务书。
- 「我给你的就是最新的包了，继续执行吧，实在不行重做」→ 本轮补丁以 p5r1 包为基线（没有更早的 v1.23.0 包，见下文「补丁」）。

### 行为变化（用户可见）

- 题目库改由 `assets/app/features/questions/` 渲染，功能与旧页一一对应：搜索、筛选抽屉（科目 / 分类 / 知识点、标记、难度与熟练度双滑块、到期 / 状态 / 题目分段）、条件 chips、计数条快捷筛选、排序、表格 / 画廊、列设置、密度、画廊列数、战绩带、元数据、题面换行、视图预设、批量条、行内「⋯」菜单、键盘。
- 勾选、筛选、切视图不再整页重建列表（morph 差量），画廊题面只在换题或换密度时重挂。
- 手机（≤760）：表格变卡片列表（改前是横向挤掉后几列的表格）；搜索框占满一行、提示文字不截断（改前截断成「标记…」）；可点目标 ≥40px。
- 行内「⋯」改用 `ui/menu`（键盘可操作）；停用 / 删除 / 迁移 / 批量打标记 / 存为视图 / 管理视图全部是 `ui/dialog`。批量打标记可当场新建标记并添加（改前要再点「＋ 新建标记」弹第二个输入框）。
- 修正：题库里按 Esc 关题目弹窗时不再顺手清空勾选；标记选择器开着时按 Esc 只关选择器。
- 有意差异：画廊卡「未练习」只在从未作答时显示，作答过但熟练度 0 的题显示 0% 进度条（改前与旁边的「1 次」矛盾）；标记「任一 / 全部命中」只在选了 ≥2 个标记时出现（选 0–1 个时两者等价）；画廊卡脚注常驻「＋ 标记」（改前只在已有标记时出现），可直接打标记。
- 偏好、视图预设、题面换行的 localStorage 键与格式不变，升级后原样保留。

### 架构

| 文件 | 变化 |
|---|---|
| `assets/app/features/questions/index.js`（309 行） | 页面契约 + 控制器：`paint()` = morph + `afterPaint()`（全选半选、双滑块 `--lo/--hi`、画廊 `qvRender`）；根上委托整行点击；document 点击关显示设置浮层（`composedPath`，重绘后目标脱离 DOM 也判得准）；`loadPreset()` 供过渡桥 |
| `state.js`（291） | 模块单例 + 纯函数：筛选 / chips / 撤销、快捷筛选、双滑块、偏好读写（旧键）、视图预设（旧格式）、选择、游标、到期 / 状态 / 复燃 / 画廊标、菜单项、批量打标记计划 |
| `view.js`（158）/ `list.js`（101）/ `dialogs.js`（69）/ `questions.css`（242） | 外壳模板；表格与画廊模板、`streakFoot()`；三个对话框；样式（前缀 `qlb-`） |
| `domain/question/ops.js`（新，126） | 题目操作从旧 questions.js 迁入；`mount.js` 的弹窗按钮改调它（两文件互相 import，只在调用时取函数） |
| `domain/question/markdown.js` | 题面换行偏好归这里（`setMdLineBreakMode`），原来读 qtable.js 的 `QB_MD_MODE` |
| `domain/items.js`、`domain/labels.js`、`domain/board.js`（新） | 适配器：`allItems` / `itemOf` / `filterAll`；标记选择器、管理、新建、批量增删、`pickerOpen`；加入展示板 |
| `legacy-bridge.js` | 新增 `installQuestionsPageBridge`（`renderQ` / `filterQ` / `questionsLoadPreset`）与 `installEscapeBridge`（全局 Esc：选择器 → 弹窗） |
| 删除 | `assets/qtable.js`（557 行）；`questions.js` 从 189 行缩到 21 行（只剩 Markdown 编辑器、`masteryBarHtml`、`reviveChipHtml`）；`panel-questions` 旧 HTML；`styles.css` 166 条规则（另 3 条去掉失效的选择器）；`legacy-bridge.css`「题库工具栏」段；`app.js` / `labels.js` 的 document 级 Esc；`actions.js::actionResetQuestionFilters`；`core.js` 的 `Q_VIEW` 与题库下拉填充 |

### 测试

- 新增 `tests/app/questions.test.mjs`（20 个用例）：迁入 `tests/test_qtable_ui.js`（3，文件删除）与 `question.test.mjs` 里旧画廊脚注（2）；其余 15 个覆盖 state 纯函数与模板约束（D4 的 `data-label`、转义、不写 `style=`、画廊挂载点 key）。node 179 → 192。
- `tests/e2e/questions.py` 23 → 70 项：题库主路径（搜索、`/`、搜索框 Esc、F、科目下拉、徽标、chip 撤销、双滑块键盘拖动、分段、标记、快捷筛选、排序、列设置、点外面关浮层）、键盘与行内菜单（↓、Space、半选、Enter 开详情、翻页顺序、Esc 不清勾选、菜单打标记、Esc 先关选择器）、批量与视图预设（批量打标记当场新建、批量停用、存 / 应用视图、仪表盘旧入口、「在题目库打开」）、手机 D4 / ≥40px / 搜索框，桌面 / 手机 × 浅 / 深审计。
- `tests/test_question_suspend_frontend.js`：断言 `actionGoQuestions` 把预设原样交给 `questionsLoadPreset`（清停用筛选的纯函数断言在 `questions.test.mjs`）。
- `tests/e2e/ui_bridge.py` 的 D2 改测新工具栏 `.qlb-bar`；`tests/app/browser_tests.js` 的旧控件高度用例去掉已删的 `.qb-bar` 夹具，改测通用规则。

### 过程中的坑

- **同一次点击关浮层**：「⋯」菜单里点「打标记」，菜单的 Promise 在点击的监听回调之间就 resolve，选择器随即打开，同一次点击冒泡到 document 时被旧 labels.js 的「点外面关闭」立刻关掉。菜单项改在 `setTimeout(0)` 后执行。
- **Esc 被两处处理**：`app.js` 在 document 上挂的 Esc 比 `core/keys.js` 先注册，总是先关弹窗；等 core/keys 处理时弹窗已关，题库页的 Esc 当成自己的去清勾选。改为全局 Esc 统一登记在 core/keys（`installEscapeBridge`）。同一作用域同一键只能有一个处理函数，选择器与弹窗必须合在一个函数里。
- **点 label 会把焦点给复选框**：E2E 点表格左上角落在全选框的 label 上，焦点进了复选框，之后的 F 被当成输入不响应（还顺手全选了）。E2E 统一点中性区 `.qlb-total` 再按键。
- **KaTeX 输出自带行内样式**；标记芯片的颜色也是旧 labels.js 的 `style=`。E2E「不写行内样式」排除这两类，后者第 3 轮随 `domain/labels/` 去掉。
- **旧全局 `header{}`**（padding / border-bottom / margin-bottom / justify-content）作用到抽屉头和画廊卡头，显式清零。
- **`ui-btn[aria-pressed]` 有自己的 hover 变量**：只改 `--btn-bg` 会在悬停时变成浅底浅字，改回标准按下态。
- **删旧 CSS**：用一个小 CSS 解析器找「选择器引用的类 / id 在 JS 与 HTML 里已无人使用」的规则逐条删，部分选择器失效的只去掉那几个选择器；删完人工清孤立注释，`git diff` 逐段核对，`git diff --check` 通过。保留仍被用到的 `.qb-search`（board.js）、`.q-label-cell`、`.board-sync-options`、`.gallery-card .qv .q-md`。
- **后台门禁与截图并发**：E2E 用条件等待，与另一个截图任务同时跑也全过；但改前 / 改后专拍放在门禁跑完之后，避免互相拖慢。

### 未做（移到 P5 第 3 轮，已登记在 progress.md）

- 题目弹窗换 `ui/dialog`：叠在它上面的 Markdown 编辑器、标记选择器、选板浮层要能先进顶层，否则被 inert；Markdown 编辑器同批换。
- `domain/labels/`：芯片去掉 `style=`（`data-*` + 运行时样式表）、LabelPicker 与标记管理的数据部分；`test_labels_ui.js` 随之迁到 `tests/app/`。
- qview 其余外观从 `styles.css` 整体搬进 `qview.css`（连同 `.gallery-card .qv …`、深色 `.qv .q-md`、`.sch-gallery-preview .qv` 覆盖）。
- 剩余 document 级 keydown（按 `document.addEventListener('keydown'` 计）：`app.js`（closeDrawer）、`board.js`、`board_picker.js`、`inbox.js`、`schedule.js`。

### 补丁

用户确认 p5r1 包就是最新基线（没有 v1.23.0 包可用）。本轮交付 `changes-2026-09-25-p5r2.patch`（相对 p5r1 包，`git diff --binary`）。补丁链里的 ⑦ = 第 1 轮 `p5r1` 补丁 + 本轮 `p5r2` 补丁，按序应用；终检时如需一份相对 v1.23.0 的合并补丁，在 v1.23.0 干净解压上依次应用两份后 `git diff` 即得。

### 验证（第 2 轮）

| 命令 | 结果（已实际执行，交付包上最后一次全量） |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 156 OK |
| `node --test tests/*.js tests/app/*.test.mjs` | 192 / 192（删 `test_qtable_ui.js` 3 个、`question.test.mjs` 移出 2 个，新增 `questions.test.mjs` 20 个）|
| `python3 tests/app/run_browser.py` | 31 / 31（旧控件高度用例去掉 `.qb-bar` 夹具后）|
| `python3 tests/e2e/shell_router.py` | 20 / 20 |
| `python3 tests/e2e/ui_bridge.py` | 15 / 15（D2 改测 `.qlb-bar`）|
| `python3 tests/e2e/instant.py` | 23 / 23 |
| `python3 tests/e2e/feedback.py` | 31 / 31 |
| `python3 tests/e2e/questions.py` | 70 / 70（连续三次全量均通过）|
| `python3 tests/check_ui.py` | 0 处问题；存量下调为 handlers 221、html_assign 143、inline_style 204、color_literals 179、font_size_literals 320 |
| `python3 tests/check_contrast.py` | 54 组，0 不达标 |
| `python3 tests/check_docs.py --diff fd41951` | 0 处问题，1 条提醒（`AI/api.md` 53KB）|
| `python3 tests/visual/run.py --ref fd41951`（p5r1） | 48 张 26 张有差异：题库 4 张（手机约 69%、桌面约 7–8%，页面重做）；其余 22 张都是桌面侧栏版本号「v1.23.0 → v1.24.0」的一个数字（逐张算过差异包围盒，全部是 49,873–54,881 这 6×9 px）；页面脚本错误无 |
| 题库改前 / 改后专拍（`git worktree` 起 p5r1 实例，同一 fixture 的两份副本；表格 / 抽屉 / 画廊 / 勾选 × 桌面 1440 / 手机 390 × 浅 / 深，32 张拼成 16 组） | 见下 |

改前 / 改后差异逐项：

- **手机表格**：改前是横向表格，只露出 UID / 标记 / 熟练度三列，其余被挤出屏幕；改后是卡片列表，每格带小标题，勾选 / 题目 / `⋯` 在第一行。改前搜索框提示截断成「…标记…」，改后完整。改前按钮 28–32px，改后 ≥40px。
- **桌面表格**：列、配色、状态标基本一致；游标行由浅灰底改为上下两条焦点色描边（与选中底色区分开）；勾选框改为 16px、可点区域 28px；表格外加一圈边框与圆角，表头吸顶保留。
- **工具栏**：改前计数条在工具栏同一行（宽屏）或下一行，改后固定为第二行，右侧是「共 N 题 · 显示 N · 已选 N」；视图切换按下态改为标准 `ui-btn` 按下态（实心）。
- **抽屉**：内容与顺序一致；分段按钮高度统一 28；标记「任一 / 全部命中」只在选了 ≥2 个标记时出现；底部固定「重置全部 / 完成」。
- **画廊**：卡片增加勾选框与 `⋯`；「今日 / 逾期」等标位置不变；去掉题面上方的「题目」小标题（与导出 / 展示板画廊卡一致）；作答过但熟练度 0 的题显示 0% 进度条而非「未练习」；脚注常驻「＋ 标记」。
- **批量条**：位置与按钮一致，快捷键提示改用 `ui/kbd`；手机上铺满底部可换行。

未执行：生产部署、远端 / 手机真机验收（按流程归 Hermes，在最后一次部署时做）；真实题库规模（数百题）下的性能只在 40 题 fixture 上看过。

## 第 3 轮（CCW · 受限，基线 P5 第 2 轮包 `OMRS-v1.24.0-p5r2-2026-09-25.zip`）

### 用户诉求

- 「P5 第 3 轮继续」→ 执行 progress.md §5 第 3 轮任务书。第一次会话工具预算用完、没有交付（沙箱里的改动保留了下来，本次接着做）。
- 按当时提出的拆分方案，用户回复「继续」：第 3 轮只做题目弹窗与 Markdown 编辑器换 `ui/dialog`（含叠在上面的旧浮层进顶层）、E2E 与交付；`domain/labels/`、qview 样式归位、剩余 keydown 移到第 4 轮（`plan.md` P5 与 `progress.md`「计划变更」已登记）。

### 行为变化（用户可见）

- 题目弹窗换成 `ui/dialog`：打开时焦点进题面区，背景拿不到焦点，Esc / 点遮罩 / 关闭按钮关闭，关闭后焦点回到被点的行；翻过页则游标与焦点落在最后看的那一题。改前关闭后焦点丢在页面上，游标停在原来那一行。
- 翻页条与关闭按钮换成 `ui-btn`（改前是旧 `.btn` 与右上角「✕」字符）；手机上翻页按钮只留图标、40×40；题面区单独滚动、头部不动（改前整个弹窗一起滚）。
- Markdown 编辑器是叠在弹窗上的 `ui/dialog`：有未保存修改时 Esc / 点遮罩不关、状态行提示；Ctrl / ⌘ + Enter 保存；失败写出原因、不关；内容没改直接关；关闭后焦点回到「编辑」按钮。改前 Esc 不起作用、点遮罩直接丢弃修改，保存后焦点丢失。
- 弹窗里的标记选择器、选板浮层、「管理标记…」叠在对话框上仍可操作；Esc / 点外面先关浮层、弹窗留着；浮层关掉后焦点回到打开它的按钮。标记管理可以按 Esc 关闭（改前关不掉）。
- 修正：弹窗里打标记后芯片立即更新。改前停在保存前的样子：打标记先乐观更新题目列表并重绘，重绘时重新拉的详情先于保存请求到达服务端。

### 架构

| 文件 | 变化 |
|---|---|
| `assets/app/ui/overlay.js` | 客人浮层 `hostGuest` / `releaseGuest`、`topModal` / `guestOpen`；`dismissible` 可为函数；`returnFocus`；Ctrl / ⌘ + Enter 在多行文本里也触发 `onEnter`；点遮罩改在按下时判定有无客人 |
| `assets/app/ui/dialog.js`、`dialog.css` | `size:'xl'`、`id`、`onOpen`、异步 `onOk`（`aria-busy`，失败留下）、`returnFocus`、`closeDialog(el)` |
| `assets/app/domain/question/modal.js`（新，118 行） | 题目弹窗：`viewQ(uid, context?, {returnFocus})`、`closeModal`、`modalOpen`、`modalUid`、←/→（从 `mount.js` 迁出） |
| `assets/app/domain/question/editor.js`（新，74 行） | Markdown 编辑器（原 `questions.js`） |
| `mount.js`、`ops.js`、`index.js`、`view.js`、`qview.css` | 去掉弹窗代码；`editQuestion` 直接打开编辑器；出口加两个新文件；qview 的标记以题目列表为准；弹窗与编辑器外观 |
| `assets/app/legacy-bridge.js`、`domain/labels.js` | `__omrsUi.host` / `release`；`closeMarkdownEditor`；`installEscapeBridge` 去掉关弹窗、加关标记管理；`managerOpen` / `closeManager` |
| `assets/labels.js`、`assets/board_picker.js` | 浮层经 `__omrsUi.host` 放进宿主对话框、关闭时 `release`；`closeLabelManager` / `labelManagerOpen`；选板浮层「点外面关闭」只让不包含它的弹层挡住 |
| `assets/app/features/questions/` | 行 / 卡 `tabindex=-1`；`open()` 传 `returnFocus`（`focusRow` 移游标并交出行）；行焦点不另画框（游标描边即可见焦点） |
| `assets/app/core/keys.js`、`features/feedback/index.js` | 「有对话框打开」的守卫排除退场中的 `.is-closing` |
| 删除 | `omrs_dashboard.html` 的 `#modal` 与 `#md-editor` 外壳（6 个 `on*=`、4 个 `style=`）；`questions.js` 的编辑器三个函数；`styles.css` 的 `.modal-wide`、`#md-editor`、`.qv-nav` 四条、`.modal .q-meta` 与焦点圈规则里的 `.qv-nav .btn` |

### 测试

- 浏览器单测 31 → 34：客人浮层（进最上层对话框、可聚焦、Esc 先关客人、点遮罩不关宿主、宿主关闭时先关客人、无对话框时进 body）；`onOk` 返回 false 留下与忙碌态、`dismissible` 为函数、多行文本里 Enter 不确认而 Ctrl+Enter 确认；`returnFocus`。
- `tests/e2e/questions.py` 70 → 91：模态与初始焦点、焦点陷阱、关闭后焦点回到行；键盘翻页后关闭，游标与焦点落在翻到的题；手机翻页与关闭按钮 ≥40×40；弹窗里新建并保存标记（真实点击）、芯片即时更新、Esc 只关选择器且焦点回到按钮；选板浮层进对话框、点浮层外只关浮层；编辑器是第二个模态对话框、Enter 换行不提交、未保存时 Esc 不关、Ctrl+Enter 写回文件、焦点回到重绘后的「编辑」；桌面 / 手机 × 浅 / 深的弹窗打开状态审计（小目标 0、无横向溢出、不写行内样式，字号 6 种）。
- `tests/e2e/instant.py`、`feedback.py`：编辑器打开判定改读 `dialog.open`，关闭后等元素移除再继续。

### 过程中的坑

- **入场动画期间量尺寸**：面板 `ui-pop-in` 从 `scale(.98)` 起，刚打开就量按钮，40px 量成 39px。E2E 等 400ms 再量。
- **退场动画期间对话框仍是 `[open]`**：关编辑器后立刻按 Ctrl+Enter 提交反馈，会被「有对话框打开」的守卫挡掉。守卫改为 `dialog[open]:not(.is-closing)`。
- **客人浮层的 Esc**：overlay 在 document 捕获阶段拦 Esc；选板浮层自己也在捕获阶段监听、注册更晚，所以 overlay 让位（`escape:false`）由它处理；标记选择器与标记管理登记 `escape:true`，由 overlay 代关，Esc 不会先关掉底下的弹窗。
- **点遮罩**：选板浮层的「点外面」是捕获阶段的 click，先于对话框自己的 click 关掉浮层；对话框若在 click 时判定就会把自己也关了，所以改在 mousedown 时判定有无客人。
- **没先存 WIP 补丁**：第一次会话没按 progress.md §7 在开头把补丁写进下载目录，预算用完时改动只在沙箱里。这次开工第一步先写 WIP 补丁。

### 未做（移到 P5 第 4 轮，已登记在 progress.md）

- `domain/labels/`：芯片不写 `style=`（`data-*` + 运行时样式表，写进 `@layer domain`），预设色进 `tokens.css`；LabelPicker 与标记管理的数据部分；`test_labels_ui.js` 迁到 `tests/app/`。
- qview 其余外观从 `styles.css` 搬进 `qview.css`（连同覆盖规则；domain 层受 check_ui R1–R4 约束，要逐条换 token，截图差异逐项解释）。
- 剩余 5 处 document 级 keydown（`app.js` 的 closeDrawer、`board.js`、`board_picker.js`、`inbox.js`、`schedule.js`）都属于未迁页面，与弹窗无关，随各自页面迁（P6 / P7）。选板浮层的捕获阶段 keydown 已与 overlay 的客人机制协调。

### 补丁

本轮交付 `changes-2026-09-25-p5r3.patch`（相对 p5r2 包，`git diff --binary`）。补丁链 ⑦ = `p5r1` → `p5r2` → `p5r3`（→ 第 4 轮 `p5r4`），按序应用。

### 验证（第 3 轮）

| 命令 | 结果（已实际执行，交付包上最后一次全量） |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 156 OK |
| `node --test tests/*.js tests/app/*.test.mjs` | 192 / 192 |
| `python3 tests/app/run_browser.py` | 34 / 34（新增 3 个）|
| `python3 tests/e2e/shell_router.py` | 20 / 20 |
| `python3 tests/e2e/ui_bridge.py` | 15 / 15 |
| `python3 tests/e2e/instant.py` | 23 / 23 |
| `python3 tests/e2e/feedback.py` | 31 / 31 |
| `python3 tests/e2e/questions.py` | 91 / 91（第一次全量 89 / 91：手机按钮在入场动画中量成 39px、弹窗里的芯片停在保存前；修正后又全量跑了两次，都全过）|
| `python3 tests/check_ui.py` | 0 处问题；存量下调为 handlers 215、html_assign 141、inline_style 198、color_literals 179、font_size_literals 316 |
| `python3 tests/check_contrast.py` | 54 组，0 不达标 |
| `python3 tests/check_docs.py --diff 1e66576` | 0 处问题，1 条提醒（`AI/api.md` 53KB）；先运行了 `--write-routes`（`/api/question/raw`、`/api/question/markdown` 的说明文档加上 `AI/frontend/qview.md`）|
| `python3 tests/visual/run.py --ref 1e66576`（p5r2） | 截图阶段完成（96 张），差分阶段进程中途退出、没有留下错误输出。改用同一批截图逐张比较（通道差 > 24）：48 对里 24 对有差异，全是桌面侧栏版本号 v1.24.0 → v1.24.1 那一个数字（包围盒都是 x 62–68、y 873–880）；手机 24 对无差异。它自带的逐页运行时审计与页面脚本错误统计这次没有产出，脚本错误由各 E2E 的断言覆盖 |
| 改前 / 改后专拍（p5r2 实例对本轮实例，同一 fixture 的两份副本；题目弹窗、编辑器 × 桌面 / 手机 × 浅 / 深，弹窗里的标记选择器 × 桌面 × 浅 / 深，共 10 组） | 见下 |

改前 / 改后逐项：

- **桌面题目弹窗**：布局一致（1180 宽，题面 | 答案双栏）；翻页条换成 `ui-btn` 加 `‹` `›` 图标，关闭按钮从「✕」字符换成图标按钮；题面区单独滚动。
- **手机题目弹窗**：改前是居中弹窗、翻页按钮带文字；改后贴底，翻页按钮只留图标（40×40），题面单栏不变。
- **Markdown 编辑器**：改前 980 宽，叠在弹窗上时露出底下弹窗的边；改后与题目弹窗同为 1180 宽、完全盖住，文本框下多一行状态（「Ctrl / ⌘ + Enter 保存」或未保存提示）；手机上贴底，按钮铺满一行。
- **弹窗里的标记选择器**：位置与外观不变（改前也能用，因为旧弹窗不是模态；改后在模态对话框里仍可操作）。

未执行：生产部署、远端 / 手机真机验收（按流程归 Hermes，在最后一次部署时做）；Safari / Firefox 未测（沙箱只有 Chromium 141）。

## 第 4 轮（CCW · 受限，基线 P5 第 3 轮包 `OMRS-v1.24.1-p5r3-2026-09-25.zip`，P5 最后一轮）

### 用户诉求

- 「继续」→ 执行 progress.md §5 第 4 轮任务书：`domain/labels/`（芯片不写 `style=`、预设色进 tokens、选择器与管理的数据部分、测试迁移）、qview 其余外观归位、E2E 去掉对芯片的排除、交付并收尾 P5。

### 行为变化（用户可见）

- 题面与答案按设计系统的阅读正文显示：16px、行高 1.75（原 12.9px / 1.8）；画廊与导出、展示板缩略卡 13px（原 12.3px）。题目弹窗、反馈录入、即时练习的题面都变大，更易读。
- 题头去掉了旧全局 `header` 规则带来的 16px 顶部空白；题头编号、记录模块的数字与判定字重 600（原 700）；记录模块的小字统一到 11 / 12px（原 10.2 / 11.1px）。
- 深色主题下答案块恢复浅绿底与绿边（原被深色覆盖规则盖掉，与浅色主题不一致）。
- 标记芯片、色板、颜色圆点外观不变（颜色改走 `data-lbl-c` 与运行时样式表）。

### 架构

| 文件 | 变化 |
|---|---|
| `assets/app/domain/labels/`（新目录，替代 `domain/labels.js`） | `color.js`（颜色算法，预设色经 `presetColors()` 读 tokens）、`sheet.js`（运行时样式表，`@layer domain`）、`chips.js`（芯片，同旧签名）、`model.js`（选择器与管理的数据部分，纯函数）、`index.js`（出口 + 旧适配器）、`labels.css`（色板按 `data-lbl-c` 取色） |
| `assets/labels.js` | 删颜色工具、`LABEL_PRESETS`、`lblChip` / `lblChips`、最近使用三函数与 `module.exports`；排序、增改、选择器候选、批量、管理表单改调过渡桥挂的纯函数；色板与颜色圆点改写 `data-lbl-c` |
| `assets/app/legacy-bridge.js` | 新增 `installLabelsBridge`（14 个同名全局，逐条注明调用方） |
| `assets/app/domain/question/view.js` | qview 的标记芯片直接用 `domain/labels/chips.js`（不再读旧全局） |
| `assets/app/domain/question/qview.css` | 重写：qview 全部外观（160 行），全部 token 化；别处容器对 qview 的覆盖搬到文件末尾 |
| `assets/styles.css` | 删 qview、`.md-p` / `.md-table*`、战绩带、占位与覆盖规则共约 100 行；两条深色组合选择器里去掉 `.qv .q-md` 与 `.qv-locked` |
| `assets/app/styles/tokens.css` | 新增 `--surface-sunken`、`--success-subtle` / `--success-line`、`--streak-ok` / `--streak-bad`、`--lbl-preset-1…10`、`--lbl-fg-dark` / `--lbl-fg-light` |
| `tests/check_contrast.py` | 加 `fg-1` / `fg-2` 压在 `surface-sunken` 上两组（54 → 58） |
| `AGENTS.md` | 映射表加 `assets/app/domain/labels/` → `AI/frontend/library.md` |

### 测试

- 原 test_labels_ui.js 的 5 个用例迁到 `tests/app/labels.test.mjs`（断言按新结构改写：颜色写 `data-lbl-c`、solid 前景是 token 引用），新增 5 个：预设色来自 tokens 且本目录 JS 无颜色字面量、运行时规则与登记去重、选择器候选、最近使用与快速区、下一个颜色 / 批量 / 表单 / 排序。node 192 → 197。
- `tests/e2e/questions.py` 91 → 92：弹窗与画廊审计的「不写行内样式」去掉对芯片的排除；新增「芯片颜色走 data-lbl-c + 运行时样式表，全页芯片不写 style=」。

### 过程中的坑

- **题头是 `<header>`**：旧全局 `header{padding:16px 0 24px;…;justify-content:space-between}` 在 legacy 层给题头加了 16px 顶部内边距。搬到 domain 层时内外边距、边框、对齐全部显式写，这 16px 随之去掉（有意差异）。
- **覆盖规则一起搬**：深色 `.qv .q-md` 的覆盖在旧文件里特异度高于 `.qv .q-answer-md`，把答案块的绿底盖掉了；搬进同一层并按顺序排列后，答案块在深色下也有浅绿底（有意差异）。
- **R2 不许 `line-height:0`**：战绩带原来靠它压掉基线空白；它是固定高度的 inline-flex、子项没有文字，去掉后高度不变。
- **dash 没有进程替换**：沙箱的 `/bin/sh` 是 dash，`<(...)` 语法报错，需要时用 `bash -c`。
- **对比度配对加了新 token，单测里的最小 token 集也要补**：`tests/test_ui_gates.py` 的对比度用例用自带的最小 CSS 调 `check_contrast.evaluate()`，新配对引用的 `--surface-sunken` 不在里面，抛 KeyError；给它补上这一个 token。

### 补丁

本轮交付 `changes-2026-09-25-p5r4.patch`（相对 p5r3 包，`git diff --binary`）。补丁链 ⑦ = `p5r1` → `p5r2` → `p5r3` → `p5r4`，按序应用；P5 到此结束。

### 验证（第 4 轮）

| 命令 | 结果（已实际执行，交付包上最后一次全量） |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 156 OK（第一次全量 1 个错误，即上面「最小 token 集」那条；补上后全量重跑 156 OK）|
| `node --test tests/*.js tests/app/*.test.mjs` | 197 / 197（删 5 个、新增 10 个）|
| `python3 tests/app/run_browser.py` | 34 / 34 |
| `python3 tests/e2e/shell_router.py` | 20 / 20 |
| `python3 tests/e2e/ui_bridge.py` | 15 / 15 |
| `python3 tests/e2e/instant.py` | 23 / 23 |
| `python3 tests/e2e/feedback.py` | 31 / 31 |
| `python3 tests/e2e/questions.py` | 92 / 92（本轮两次全量都全过）|
| `python3 tests/check_ui.py` | 0 处问题；存量下调为 handlers 215、html_assign 141、inline_style 195、color_literals 160、font_size_literals 307 |
| `python3 tests/check_contrast.py` | 58 组，0 不达标 |
| `python3 tests/check_docs.py --diff 5c057f7` | 0 处问题，1 条提醒（`AI/api.md` 53KB）|
| `python3 tests/visual/run.py --ref 5c057f7`（p5r3） | 全程跑完。48 对里 21 对有差异，全是桌面侧栏版本号 v1.24.1 → v1.24.2 那一个数字（包围盒都在 x 63–67、y 873–880）；手机无差异；页面脚本错误无。运行时审计的行内样式计数下降：数据复盘 186 → 180、即时练习 4 → 1（芯片不再写 `style=`）。12 页首屏都不打开题目，题面字号的变化见下面的专拍 |
| 改前 / 改后专拍（p5r3 实例对本轮实例，同一 fixture 的两份副本；题目弹窗 × 桌面 / 手机 × 浅 / 深，题库画廊与标记管理 × 桌面 × 浅 / 深，共 8 组） | 见下 |

改前 / 改后逐项：

- **题目弹窗**：题面 / 答案字号 12.9 → 16px、行高 1.8 → 1.75；题头上方 16px 空白去掉；题头编号字重 700 → 600；深色下答案块有浅绿底。E2E 审计里弹窗的字号种数 6 → 5（桌面 / 手机 × 浅 / 深都是 5）。
- **题库画廊**：缩略卡题面 12.3 → 13px，其余不变；芯片颜色与改前一致。
- **标记管理**：色板、颜色圆点、芯片颜色与改前一致（改走 `data-lbl-c` 与运行时样式表）。

未执行：生产部署、远端 / 手机真机验收（按流程归 Hermes，在最后一次部署时做）；Safari / Firefox 未测（沙箱只有 Chromium 141）；导出文件没有逐个打开目测（导出模板本轮未改，单测里的导出用例已跑）。
