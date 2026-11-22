# 前端重构剩余阶段：实施计划（历史执行说明分册）

> 执行者：Codex；运行模式：完整模式。该计划已完成，以下保留原执行说明正文；上下文与决策见 [执行说明](exec-2026-09-26-codex.md) 和 [进度](progress.md)。

## 实施计划

### 阶段 0：复核本机状态，建立开发基线

**目的：** 之后每个页面都要单独提交，截图对比也依赖 `git worktree`，所以必须先有一个可以当基线的提交。同时要先确认开发不会影响生产。

**0.1 记录现状。** 下面这些结果先存下来，阶段 1 写进任务日志：

- `pwd`、`git rev-parse HEAD`、当前分支；
- `git status --short` 的行数和前 50 行、`git stash list`；
- `omrs/version.py` 里的版本号；
- `systemctl cat omrs.service` 里的 `WorkingDirectory` 和 `ExecStart`；
- 生产 `/api/status` 返回的版本（端口以 unit 文件为准）；
- `AI/logs/log.md` 是否存在。

**0.2 判断生产服务是否运行在当前工作区。** 注意：`omrs/server.py` 的 `_serve_asset` 每次请求都从磁盘读 `/assets/*` 和 `omrs_dashboard.html`，后端代码则要重启才会更新。

- **情况 A：服务目录就是当前工作区。**
  - 这时工作区里的前端改动对生产是立即生效的。
  - 如果 `/api/status` 仍是 v1.19.1、而工作区已是 v1.25.4，说明生产正处在「新前端 + 旧后端」的混合状态。
  - 用浏览器（或 CDP）打开生产首页，依次进入 12 个页面，看控制台有没有错误：
    - **有页面脚本错误，或页面打不开：** 立即停下，向用户报告版本、错误内容和受影响的页面，并给出两个选项：
      1. 用户授权重启到 v1.25.4（门禁已全绿）；
      2. 用备份把工作区前端退回 v1.19.1。

      两项都不要自行执行。
    - **没有错误：** 记录下来，继续执行，并在最终报告里提醒用户。
  - 不论哪种结果，此后都**不得**在这个目录里改文件（见 0.4）。唯一的例外是 0.4 的基线提交和规划补丁：它们只动 Git 记录和文档，不影响运行中的服务。
- **情况 B：服务运行在另一个目录（例如 `/opt/omrs`）。** 当前工作区只是开发区，原地开发即可。

**0.3 复核合并结果。**

1. 版本号是 v1.25.4。
2. 上一节列出的已删文件都不存在。
3. 跑 progress §4 的全部门禁，unittest 的预期值改为 159。
4. 如果独立 Chromium 崩溃，按 `AI/environment.md` 设置 `OMRS_TEST_CDP_URL` 后重跑，并记下用的是哪种模式。

有任何不一致，说明合并不完整：停下来报告，不要自行补齐。

**0.4 建立基线提交和开发区。**

1. **先确定纳入范围。** 运行 `git status --short --untracked-files=all` 查看全部改动。
   - 只纳入导出工具的扫描范围：根目录的项目文件，以及 `AI/`、`Skills/`、`assets/`、`deploy/`、`omrs/`、`tests/`、`web/`，再加上 `AI/logs/`。
   - 范围以外的文件一律不加、不删、不动，列进日志。例如：`错题/`、`临时/`、`Task/`、`tool/`、`unused/`、`logs/`、各种备份、密钥和 `.env`、大体积二进制文件。
   - 已被 `.gitignore` 忽略的文件，不要用 `-f` 强行加入。
2. **提交基线。** 在当前工作区执行 `git switch -c rearch/base-v1.25.4`（这一步不改动任何文件），按上面的范围 `git add` 后提交。提交说明写清两点：
   - 这是一个工作树快照，包含 v1.18.2 之后所有未提交的本地改动，加上前端重构补丁 ① 到 p6r5 的合并结果；
   - 这些改动从未分段提交，补丁链之外还混有本机改动，所以无法事后还原成逐期提交。
3. **合入本说明所在的规划补丁 `changes-2026-09-26-ccw-plan.patch`。** 补丁只改文档，不影响正在运行的服务。
   - **还没应用：** 先做上一步的基线提交，再 `git apply --3way` 这个补丁，单独提交为「规划：AGENTS 规划模式与 Codex 执行说明」。
   - **已经应用**（工作区里已有本文件）：它会被包含进基线提交，在提交说明里注明即可。
4. **建开发区：**
   - **情况 A：** 执行 `git worktree add <工作区同级目录>/OMRS-rearch -b frontend-rearch rearch/base-v1.25.4`。之后所有开发、测试和提交都在这个 worktree 里做。生产工作区停在基线提交，直到用户授权部署。
   - **情况 B：** 在工作区里执行 `git switch -c frontend-rearch`。
5. **禁止的操作：** 不要改写或删除原来的分支；不要 `reset --hard`、`git clean`、`stash drop`；不要做任何会丢失改动的操作。

**0.5 在开发区复跑一遍门禁。** 结果必须与 0.3 一致。

---

### 阶段 1：补全只能在本机得到的记录

执行方式的变更已经由规划提交写进了计划，包括：
- `plan.md` 里的执行者、§6 通用约定、§9 模板停用；
- `progress.md` 的状态块、U15、§2、§4、§5b、§7、§8、§9；
- 删除 `AI/rearch-plan.md`。

这一阶段只补上规划时拿不到的事实。单独做成一个提交，不升版本号。

1. **`progress.md` 状态块和 §2：** 把「基线提交由 Codex 阶段 0 建立」换成实际的提交哈希和分支名；写入阶段 0 实测的生产版本、服务目录、属于情况 A 还是情况 B。实测结果与 §2 原来的记录不同时，以实测为准，改正并注明日期。
2. **任务日志：** 在 `AI/logs/2026-09-25_frontend-rearch-p6.md` 末尾追加「本机接手（2026-09-26）」一节，写入阶段 0 的全部记录：
   - 现状清单、情况判定、门禁数字、用的是哪种浏览器运行模式；
   - 没有纳入基线的路径清单。

   按 AGENTS 第 4 条，这是同一个逻辑任务的继续，所以追加到原日志里。规划补丁自带的日志 `AI/logs/2026-09-26_agents-planning-mode.md` 保持原样。
3. **§4 门禁计数：** 如果本机结果与 §4 不同（例如 CDP 模式下的计数），按实际结果改正。
4. **收尾：** 运行 `check_docs --diff HEAD`（退出码必须为 0）和 `--write-log-index`，然后提交。

---

### 阶段 2：P6 剩余页面

#### 2.0 每页的统一做法（迁移完成的定义）

每个页面都按下面的顺序做，全部做到才算完成：

1. **先盘点，再动手。**
   - 列出旧文件里本页的全部函数、DOM id、CSS 类、快捷键和 document 级监听；
   - 找出哪些旧全局还被别的页面或测试调用（用 `grep` 查 `assets/`、`omrs_dashboard.html`、`tests/`）；
   - 盘点结果写进任务日志。
2. **页面代码放在 `assets/app/features/<页>/`，** 写法照 progress §6：
   - 至少有 `index.js`（页面契约）、`state.js`（纯函数）、`view.js`、`<页>.css`；
   - JS 单文件不超过 400 行，CSS 不超过 300 行，超了就按工作区拆分。
3. **跨页共享的逻辑放进 `domain/`，只在本页用的留在 feature 里。** 判断标准是被两个以上页面使用。
4. **注册页面。**
   - 在 `main.js` 注册页面契约，并从 `legacy-pages.js` 删除对应的一项；
   - HTML 面板里的旧 DOM 换成挂载根。
5. **处理旧全局。** 旧代码仍需要的全局，放进 `legacy-bridge.js` 里本领域的 `install<领域>Bridge`，每条注明调用方和计划删除的时间（P7 或 P8）。
6. **删除旧代码。**
   - 删除本页的旧 JS。
   - 删除 `styles.css` 里只服务本页的规则：只按精确字符串删，删完用 `git diff` 逐段核对，并运行 `git diff --check`（见 progress §7）。
   - 其它页面仍在用的规则保留。
7. **测试：**
   - 新增 `tests/app/<页>.test.mjs`，覆盖 `state.js` 和 domain 里的纯函数；
   - 新增 `tests/e2e/<页>.py`，照 `tests/e2e/schedule.py` 的结构写：
     - 自建 fixture，起隔离实例；
     - 浏览器通过 `tests/browser_runtime.launch_chromium` 启动；
     - 只用条件等待；
     - 每段用 `guarded()` 包起来；
     - 末尾做桌面 / 手机 × 浅色 / 深色的审计：字号不超过 6 种且最小不低于 12px，可点目标不小于 28 / 40px，没有 `style=` 和 `on*=`，没有溢出；
     - CDP 模式下只关闭自己建的 context。
   - 原来载入本页旧文件的测试，迁到 node 测试或 E2E，用例只增不减。新旧用例的对应关系写进日志。
8. **文档：**
   - `AI/frontend/<分册>.md` 改写本页，速查头的入口和必跑测试要更新；
   - `AGENTS.md` 的映射表加上 `assets/app/features/<页>/` 一行；
   - 涉及 domain 或过渡桥时，同步 `architecture.md`；
   - 涉及新组件或 token 时，同步 `components.md` 或 `design-system.md`。
9. **版本和日志：**
   - 版本号加 0.0.1，同步版本号的四处位置，并在 `changelog.md` 顶部加一段；
   - 任务日志写本页的行为变化、影响的文件和验证结果；
   - `progress.md` 更新状态块、分期表、门禁计数和下一步。
10. **收尾验证：**
    - 全量门禁（见「验证步骤」）；
    - 运行 `tests/visual/run.py --ref <上一个提交>`，每一处截图差异都在日志里逐项解释；
    - 真起服务、真开浏览器，把本页主路径手工走一遍。
11. **提交。** 提交说明的第一行写成 `frontend-rearch P6: <页> → features/<页>（v1.25.x）`。

#### 2.1 修复截图脚本的审计（小提交，不升版本）

- 按上文「已定位的遗留」修改 `tests/visual/run.py` 的 `AUDIT_JS`。
- 能用单测覆盖的部分，补进 `tests/test_visual_diff.py`。
- 修完运行 `--audit-only`，确认复习调度和题库页的行内样式计数都是 0。
- 同步 `AI/environment.md`，在 p6 日志里记录，并把 progress §5b 对应的一项勾掉。

#### 2.2 历史记录（→ `features/history/`，分册 `AI/frontend/records.md`）

**`domain/history.js` 换成真实现。**
- 把 `history.js` 里的判定和投影函数搬进 `domain/history`，写成纯函数，并用 node 测试覆盖。这些函数包括：
  - 撤销状态：`historyRetractionState`、`normalizeHistoryRetractionState`、`isNodeRetracted`；
  - 节点分类：`isHistoryCorrection`、`historyCommitFamily`；
  - 标题与说明：`historyNodeTitle`、`historyNodeSubtitle`、`historySessionLabel`；
  - 统计：`historyReviewBatchStats`；
  - 排序等。
- 仪表盘的 `projectRecent` 改为直接 import 这些函数，不再经 `globalThis` 查找。仪表盘的显示不变，`dashboard.py` 必须仍是 26 / 26。

**必须保留的行为：**
- 排序切换；
- 写操作只在「修正模式」下可用（`records.md` 的不变量）；
- 修正面板、还原按钮、复习批次直接还原、Session 操作、状态还原、载荷预览、操作面板；
- 时间按设置里的 Ledger 时区显示。

**写操作：**
- 统一经 `domain/history` 发请求，返回 `{ok, data, error}`。
- 需要确认的操作用 `ui/dialog`。
- 请求期间按钮置忙，防止重复提交。
- 成功后依次执行：
  1. 让受影响题目的详情缓存失效（`qvInvalidateMany`）；
  2. 重新加载 `domain/data` 和 `domain/sessions`；
  3. 发一个 bus 事件，让仪表盘的「最近动态」刷新；
  4. 重拉历史列表。
- 失败时保留当前列表，在出错的位置显示原因。

**测试：**
- `tests/test_history_projection.py`（后端测试）保持不变；
- 新增 `tests/app/history.test.mjs`；
- 新增 `tests/e2e/history.py`，至少覆盖：列表渲染、切换排序、进入修正模式、做一次撤销再还原、确认仪表盘「最近动态」同步变化，以及审计。

#### 2.3 目录（→ `features/catalog/`，分册 `AI/frontend/dashboard.md` 的目录一节）

**必须保留的行为：**
- 目录树加载，接口失败时退回到后备树（`catalogFallbackTree`）；
- 统计信息、搜索、展开全部 / 收起全部、显示全部文件；
- 从目录打开题目（走 `domain/question` 的弹窗）；
- 复制路径，剪贴板被拒绝时要有提示。

**要修复的问题：**
- 小于 28px 的可点目标从 25 个降到 0（D9）；
- 「重新扫描」放进本页工具栏（DP4）。

**大目录树：**
- 用带 key 的 `each()` 渲染，默认收起；
- 「展开全部」在 fixture 的最大树上不能卡顿到超过 1 秒无响应。

**测试：**
- `tests/smoke_frontend_actions_catalog.js` 里的目录场景迁到 `tests/app/catalog.test.mjs`；
- `tests/test_catalog_tree.py` 保持不变；
- 新增 `tests/e2e/catalog.py`。

#### 2.4 报告（→ `features/reports/`，分册 `AI/frontend/records.md`）

**上传：** 换成 `ui/filedrop`（D6），支持拖入和点击选择。
- 非 HTML 文件、空文件、读取失败，都在控件旁边给出原因；
- 上传过程中防止重复提交。

**安全不变量（必须保持）：** 报告在 `sandbox` iframe 里渲染，`sandbox` 属性不含 `allow-same-origin`。E2E 要断言这一点。

**其它行为：**
- 删除前用 `ui/dialog` 确认；
- 「复制 AI 提示词」、下载报告数据（走 `core/download.js`）、材料提示都保持原样。

**测试：**
- `tests/test_report_export.py` 保持不变；
- 新增 `tests/app/reports.test.mjs` 和 `tests/e2e/reports.py`。

#### 2.5 设置（→ `features/settings/`，分册 `AI/frontend/settings.md`）

页面分五个分区，每个分区一个子模块：外观、访问与安全、AI 识别、数据与存储、服务与运行。`app.js` 里的 `loadRuntimeStatus` 和 `optimize*` 系列一起迁过来。

**必须保留的行为：**
- 重启后要等到看见新的 `instance_id` 才刷新页面；
- 只改「免 PIN 网段」时不重启；
- PIN 的设置、停用和远程登出；
- AI Key 不回显，清除时要确认；
- 主题、密度、反色图片的 localStorage 键名不变（外壳也在读这些键）；
- 图片压缩的扫描和任务轮询、备份导出和导入；
- **「导出脱敏源码包」必须仍然可用：** 以后 CCW 的工作包就靠它生成，`tests/test_source_export.py` 要继续通过。

**重启测试的安全要求：** E2E 里用 `page.route` 拦截 `/api/restart`，不要真的触发重启。启动隔离实例前，确认环境里没有 `OMRS_SYSTEMD_SERVICE`。

**测试：**
- `tests/test_settings_ui.js`、`tests/test_restart_ui.js`、`tests/test_auth_activity_ui.js` 都是从 `app.js` / `core.js` 里抽函数来测的，迁到 `tests/app/settings.test.mjs`，用例只增不减；
- 新增 `tests/e2e/settings.py`。

**元素 id：** 旧的元素 id 只保留测试或其它模块仍在引用的，其余可以换。`settings.md` 里的不变量「保留全部旧元素 ID」同步改写成新的规则。

#### 2.6 录入题目，含收件箱工作台（→ `features/create/`，分册 `AI/frontend/create.md`，流程细节同步 `AI/inbox.md`）

这是 P6 最大的一页，**必须分步提交**，每一步结束时页面都完整可用。做法照复习调度的先例（P6 第 3 到 5 轮）：先做新外壳，把旧 DOM 暂时托管在挂载点里，再逐个工作区迁移。

1. **页面外壳与上传区：**
   - 工作区切换；
   - 上传区：拖放、选择文件、剪贴板粘贴；
   - 收件箱网格：筛选、全选、批量打开和丢弃；
   - 快速录入区：`cr-*`，包括粘贴图片、AI 分类、提取题面和答案。
2. **框选工作区：**
   - 图片和 canvas 放在 `data-morph="skip"` 子树里，指针交互由控制器管理，不参与 morph；
   - 区域增删、角色切换、版式选择、应用上一张的框、整图一框；
   - 保存防抖：`ibSaveSoon` 的语义不变，离开页面前把未保存的内容写出去；
   - 检测和提取任务的轮询。
3. **卡片工作区：**
   - 卡片表单、标记（改用 `domain/labels`）、分类；
   - 单张提交和批量提交；
   - 送去展示板。
4. **训练与策略工作区：**
   - 数据集统计、导出；
   - 策略开关与保存、清理。

**必须保持的不变量：**
- 上传的原图只进暂存区，提交后才写入题库；
- 提交成功后保留科目、分类等上下文字段，只清空题目内容。

**测试：**
- `tests/test_inbox.py` 和 `tests/test_ai_assist_taxonomy.py` 保持不变；
- 新增 `tests/app/create*.test.mjs` 和 `tests/e2e/create.py`；
- 需要 AI 的步骤用 `page.route` 返回固定结果。

#### 2.7 `inbox_mobile.html` 接入 tokens

- 只接入 `tokens.css` 和 base 样式，替换颜色字面量；不重写页面（`plan.md` §3.9）。
- 在 390px 宽度下，浅色、深色各截一张图，把上传主路径走一遍。
- 提交时并入 2.6 的最后一个提交，或者单独提交。

#### 2.8 P6 收尾

- progress 分期表里把 P6 标为完成；
- 核对 `plan.md` §6 P6 的验收项（每页一个 E2E，每页达到 §2 的指标）；
- 在 p6 日志里写一段 P6 小结。

---

### 阶段 3：P7 展示板

这一阶段新开任务日志 `AI/logs/<实际日期>_frontend-rearch-p7.md`，版本从 v1.26.0 起。严格按 `plan.md` §6 P7 的顺序做，每一步一个提交：

1. **纯函数和测试先行。** 把 `board.js`、`board_preview.js`、`board_picker.js` 里不碰 DOM 的逻辑搬进 `features/board/` 和 `domain/board.js`。原来的 `test_board_ui.js`、`test_board_preview.js`、`test_board_regions.js`、`test_board_locked_incremental.js` 迁到 `tests/app/board*.test.mjs`，用例只增不减。这一步用户看不到变化。
2. **保存队列：** 按字段记脏，合并成一次 POST。
3. **打印协调：** 包括「仅补印新增」（锁定增量）。
4. **拖拽排序。**
5. **版面设置。**
6. **选板浮层：** 叠在对话框上时，按 progress §6 的 `__omrsUi.host` 挂载。
7. **迁移页面 UI：** 预览 iframe 的节点标 `data-morph="skip"`，消息必须带当前的 `previewToken`，协议不变。

顺手修一处：`board.js` 里 `focus: '[data-ui-ok]'` 已经过时，改成 `[data-dialog-ok]`（progress §8）。

**验收：**
- `smoke_board_integrity.py`、`smoke_board_lock.py`、`smoke_board_print.py`、`smoke_board_print_geometry.py` 全部通过；
- 新增 `tests/e2e/board.py`，覆盖建板、加题、排序、版面设置、打印预览、仅补印新增；
- `AI/frontend/board-ui.md` 和 `AI/board.md` 同步更新。

---

### 阶段 4：P8 收尾

这一阶段新开任务日志 `<实际日期>_frontend-rearch-p8.md`，版本从 v1.27.0 起。按下面的顺序做，每项一个提交：

1. **`core.js`：**
   - `filterItems`、`getDueDays` 等筛选语义搬进 `domain/items.js`；
   - `api`、`escapeHtml` 以及 `ui*` 转调，由 `core/` 和 `ui/` 的对应实现取代；
   - 仍在载入 `core.js` 的测试（`arrange`、`exporter`、`labels` 三个 `.test.mjs`，以及 `test_question_suspend_frontend.js`、`test_board_ui.js`、`test_auth_activity_ui.js`、`smoke_frontend_actions_catalog.js`）改为 import 新模块。
2. **`labels.js`：**
   - 标记选择器浮层和标记管理迁进 `domain/labels`；
   - 标记管理换成 `ui/dialog`（这是 P5 留下的可选项），同时删掉 overlay 客人登记里的对应一项；
   - 标记芯片 `.lbl` 的外观从 `styles.css` 搬进 `labels.css`。
3. **`app.js`：**
   - `init`、侧栏和抽屉的逻辑并入 `shell.js` / `main.js`；
   - 删除 `legacyDataRefresh` 和 `switchTab`；
   - 测试和脚本里的 `switchTab(...)` 全部改成 hash 导航。目前 `tests/` 下约有 16 处，`tests/visual/run.py` 已经有 hash 的写法可以参考。
4. **删除 `questions.js`、`schedule.js` 这两个残桩，以及 `legacy-pages.js`。** 过渡桥逐条清空后，删除 `legacy-bridge.js` 和 `styles/legacy-bridge.css`。
5. **`styles.css`：**
   - 把仍在生效的全局规则（例如 `header{}` 这类元素规则）搬进 `base.css` 或对应层，然后删除 `styles.css`；
   - `tokens.css` 删除旧 token 别名，`check_contrast.py` 同步调整。
6. **`omrs_dashboard.html` 只保留外壳骨架和挂载根。**
7. **门禁收紧：**
   - `ui_baseline.json` 归零后删除，`check_ui.py` 改为对全仓零容忍；
   - `tests/test_ui_gates.py` 和 `tests/app/browser.html` 同步修改；
   - `test_board_regions.js` 里「`styles.css` 不含浮层样式」的断言，改成对新样式文件断言。
8. **文档定稿：**
   - 删除 `shell.md` 的加载顺序一章；
   - `optimization.md` 里三条相关事项关闭，分别是「CSS 重复定义」「innerHTML + 行内 onclick」「board.js 多职责」；
   - `architecture.md` 和 `components.md` 删除过渡桥相关的章节；
   - `AGENTS.md` 映射表删掉已不存在的文件行，新增文件按规则补上。

---

### 阶段 5：终检

新开任务日志 `<实际日期>_frontend-rearch-final.md`。这一阶段只允许修复发现的问题，不做新功能。

1. **从零复跑：** 在一个新 worktree（从最终提交检出）里跑全部门禁、全部 E2E 和冒烟测试，数字写进日志和 progress §4。
2. **全量截图对比：**
   - `tests/visual/run.py --ref <基线提交>`：12 页 × 浅色 / 深色 × 桌面 / 手机；
   - `--fixture empty` 再跑一遍，检查所有空态；
   - 逐对人工审阅。
3. **指标表：** 12 页各一行，填入实测的字号种数、最小字号、小目标数、行内样式数、横向溢出。任何一项不达标，要么修掉，要么写明原因并登记到 `optimization.md`。
4. **跨浏览器：**
   - 允许执行 `python3 -m playwright install firefox webkit`；
   - 用 Firefox 和 WebKit 各走一遍 12 页的进入和每页的主路径；
   - 装不上或跑不起来，就写成「未执行」并说明原因。
5. **偶发失败：** 查清 `instant.py`「标记筛选」偶发失败的根因，修掉或给出证据。
6. **写部署清单：** 写进 progress §8，内容包括：
   - 备份；
   - 记录 `git status`；
   - 把生产目录切到最终提交（情况 A 是 fast-forward，情况 B 是按原部署方式同步）；
   - 重启（需要授权）；
   - 核对 `/api/status` 的版本；
   - 12 页主路径、经 Nginx 的远端访问、手机端、控制台无报错；
   - 回滚步骤：切回基线提交并重启。
7. **更新状态：** progress 状态块改为「全部完成，待部署」，然后停下，向用户汇报。

### 阶段 6：部署（不在本次自动执行范围）

用户明确授权之前，不执行任何生产变更。

---
