# OMRS 前端重构剩余阶段：执行说明（给 Codex）

> 执行者：Codex，在本机以完整模式执行。
>
> 本说明由 CCW 在规划模式下写成，存放在 `AI/plans/frontend-rearch/exec-2026-09-26-codex.md`。
>
> - 执行者不改本说明（笔误除外），执行规则见 `AGENTS.md`「按执行说明执行」。
> - 进度、写法和遗留只记在 `progress.md`。
>
> 依据有两份：
> - 用户 2026-09-26 的原话「剩下的交给Codex执行,去掉交接文档环节」；
> - 2026-09-26T14:00Z 脱敏导出包 `OMRS-source-sanitized-20260926T140037Z.zip` 的核对结果。

---

## 任务目标

前端重构计划在 `AI/plans/frontend-rearch/`，目前做到 P6 第 5 轮（v1.25.4）。本任务要把它一直做到 P8 收尾和终检完成。执行方式同时改变：原来是「CCW 受限模式 + 补丁包和交接文档接力」，现在改成「Codex 直接在本机仓库开发，按页提交」。

完成时必须同时满足四点：

1. **页面全部迁完。** 12 个页面都运行在 `assets/app/` 新架构上，功能与现在一致。
   - 旧脚本、`assets/styles.css` 和过渡桥全部删除。
   - `plan.md` §2 的每一条指标，都有门禁结果或实测数字证明。
2. **按页提交。** 每个页面（展示板按子步骤）是本机 git 上一个独立的提交。每个提交门禁全绿，可以单独回退。
3. **不再产出包外交接物。** 补丁、完整 zip、UPGRADE、交接清单、截图包、WIP 补丁全部取消。
4. **不影响生产。** 开发全过程不影响正在运行的生产服务。部署是单独一步，等用户授权后才做。

---

## 当前背景与约束

### 规范来源

开工前按下面的顺序读：

1. `AGENTS.md`。重点读「完整模式」「按执行说明执行」「计划与用户意图」「每次任务的强制文档收尾」「代码到文档的对应关系」。
2. `AI/plans/frontend-rearch/progress.md`。重点读状态块、§4 门禁、§5b、§6 已立下的写法、§7 坑、§8 遗留。
3. `AI/plans/frontend-rearch/plan.md`。重点读 §2 指标、§3 架构、§4 设计系统、§5 门禁、§6 的 P6–P8。

本说明只写这些文件里没有的决定和变化。只有两类内容以本说明为准：执行方式（谁做、怎么交付），以及「关键技术决策」一节明确列出的项。其余一律以仓库文档和实际代码为准。

### 导出包核对结果

以下是事实，阶段 0 仍要在本机复核。

**版本和内容。** 工作区版本是 `v1.25.4`。和 CCW 交付的 p6r5 完整包相比，前端源码没有缺漏，也没有多余改动。只多出本机为浏览器测试做的适配和两份文档：

- 新增 `tests/browser_runtime.py`：设置了 `OMRS_TEST_CDP_URL` 时连接本机 CDP，否则独立启动 Chromium。另外新增 `tests/test_browser_runtime.py` 和 `tests/test_visual_diff.py`。
- 以下脚本改为「CDP 模式下只关闭自己建的 context」：8 个 E2E、4 个 `smoke_board_*`、`smoke_schedule_workbench.py`、`tests/app/run_browser.py`、`tests/visual/run.py`。`visual/run.py` 的像素差分还改成了只用 Pillow。
- `AI/environment.md` §5 新增一条：独立 Chromium 在本机可能崩溃。
- 新增 `AI/rearch-plan.md`。这是早先写的计划快照，停在「P5 待开始」，和本计划文件夹重复。
  - 本说明所在的规划提交已经删除了它，仍然有效的事实并入了 `progress.md` §2；
  - `AI/routes.md` 里因它多出的那处引用，也已随之重新生成。

**P1–P6 删除的文件都不在了。** 包括：
- `assets/` 下：`export.js`、`recommend_v2.js`、`data.js`、`dashboard.js`、`actions.js`、`qtable.js`、`qview.js`、`instant.js`
- `assets/app/domain/` 下：`schedule.js`、`questions.js`、`labels.js`
- `tests/` 下：`test_schedule_sessions.js`、`test_recommend_v2_filters.js`

**`SOURCE_EXPORT_MANIFEST.txt` 已重新生成**，不再列出已删文件。这一项原本的交接要求已经完成。

**导出包上实测的门禁（用的是独立 Chromium）：**

| 门禁 | 结果 |
|---|---|
| unittest | 159 OK。比 progress §4 记的 156 多 3 个，就是上面新增的测试 |
| node | 220 / 220 |
| `check_ui` | 0 处问题。存量：handlers 127、html_assign 84、inline_style 126、color_literals 103、font_size_literals 227 |
| `check_contrast` | 58 组，0 不达标 |
| `check_docs --diff HEAD` | 0 处问题，1 条提醒 |
| `e2e/schedule.py` | 45 / 45 |
| `smoke_schedule_workbench` | OK |

**「已合并」不等于「已提交」。** 导出工具不依赖 Git，会把未提交的文件也收进去，所以只能说明工作区里的文件是对的。`progress.md` §2 记着当时的状态（原来记在 `AI/rearch-plan.md`），阶段 0 必须重新实测：
- 本机 HEAD 是 `4fd4827`，对应 v1.18.2；
- 工作树里有大量未提交改动；
- 生产 `/api/status` 返回 v1.19.1。

### 还剩的工作

| 部分 | 内容 | 现状证据 |
|---|---|---|
| P6 剩余 | 历史记录、目录、报告、设置、录入题目（含收件箱工作台）、`inbox_mobile.html` 接入 tokens | `assets/app/legacy-pages.js` 仍登记着 catalog、create、history、reports、settings（board 属于 P7） |
| P7 | 展示板：`board.js`（1611 行）、`board_picker.js`（414 行）、`board_preview.js`（226 行） | `plan.md` §6 P7 |
| P8 | 删除 `styles.css`（约 100KB）、旧 token 别名、`legacy-bridge.js`、`legacy-pages.js`、`styles/legacy-bridge.css`；删除剩余旧脚本 `core.js`、`labels.js`、`app.js`、`questions.js`、`schedule.js`；`ui_baseline.json` 归零后删除 | `plan.md` §6 P8、progress §8 |
| 终检 | 全量门禁和 E2E；12 页 × 浅色 / 深色 × 桌面 / 手机审阅；跨浏览器测试；部署前清单 | progress §8 |

P6 剩余页面对应的旧代码如下（都在 `assets/` 下）：

| 页面 | 旧脚本 | HTML 面板 |
|---|---|---|
| 历史记录 | `history.js` | `#panel-history` |
| 目录 | `catalog.js` | `#panel-catalog` |
| 报告 | `reports.js` | `#panel-reports` |
| 设置 | `app.js` 的设置段，以及 `loadRuntimeStatus` 和 `optimize*` 系列 | `#panel-settings`，约 300 行 |
| 录入题目 | `inbox.js`（673 行）、`app.js` 的 `cr*` 快速录入段、`labels.js` 的录入标记函数 | `#panel-create`，约 270 行，含 `ib-stage-upload / process / create / train / quick` 五个工作区 |

下表是截图脚本对未迁页面的审计结果，作为这些页面的「改前」参考。条件：full fixture、浅色、桌面，在导出包上实测。

| 页面 | 字号种数 | 最小字号 | 小于 28px 的可点目标 | 带 style 的元素 |
|---|---|---|---|---|
| 目录 | 8 | 9.45px | 25 | 52 |
| 历史记录 | 8 | 10.2px | 0 | 6 |
| 报告 | 7 | 10.2px | 0 | 6 |
| 设置 | 6 | 10.2px | 0 | 1 |
| 录入题目 | 12 | 9.9px | 0 | 7 |
| 展示板 | 8 | 9.75px | 12 | 7 |

最后一列被下面这个脚本缺陷放大过，只作参考。

### 已定位的遗留：截图脚本报告的「复习调度 44 处行内样式」

progress §5b 要求第 6 轮先查这个问题。我已经复现并定位了：**问题出在 `tests/visual/run.py` 的审计脚本，不在页面。**

- **原因：** `shoot()` 先调用 `page.screenshot(full_page=True)`，然后才运行 `AUDIT_JS`。截图结束后，页面里所有 `<input>` 都会留下一个空的 `style=""` 属性，而 `AUDIT_JS` 用 `hasAttribute('style')` 计数，把它们都算了进去。
- **证据：** 复习调度的 44 处全是 input，其中候选勾选框 38 个，筛选输入 6 个。题库页的 41 处也是同样原因。截图之前数，两页都是 0，与 E2E 审计一致。
- **修法：**
  - 只统计 `style` 属性值非空（去掉空白后）的元素；
  - 按 progress §7 的约定，排除 `.katex` 内部的元素；
  - 最小字号和字号种数的统计也排除 `.katex` 内部。

### 硬约束

- **保持零构建、零依赖。** 总目标 U4 要求「让 CCW 能修改」，以后 CCW 仍会在不能联网、不能用 npm 的受限模式下改这个仓库。所以即使本机能联网，也不得引入：
  - npm 依赖、打包器、TypeScript、前端框架；
  - 任何需要构建才能运行的产物。

  新写的测试必须能离线运行。
- **不改业务行为，不改后端 API**（`plan.md` §3.9）。导出和打印模板、展示板预览 iframe 的消息协议都保持不变。
- **与生产隔离。**
  - 不在生产服务运行的目录里改文件。
  - 测试实例一律用临时 Vault 和随机高端口，绝不连 8471 端口，也不碰真实的 `错题/`。
  - 启动任何测试实例之前，从环境里去掉 `OMRS_SYSTEMD_SERVICE`。原因见 `omrs/server.py` 的 `/api/restart`：只要看到这个变量，就会执行 `systemctl restart <服务名>`，隔离实例也会因此重启生产服务。
- **需要用户单独授权的操作：** 生产重启、systemd、Nginx、`git push` 和任何远端操作。
- **用中文。** 文档、日志、代码注释、界面文案都用中文，沿用仓库现有写法。

---

## 最终预期行为

### 用户可见

- **功能不变。** 12 个页面的功能、文案和统计口径都与迁移前一致。刷新后停在当前页。Esc、快捷键、关闭后焦点回到触发元素这些交互，与已迁页面的规范一致。
- **每页达到设计指标：**
  - 渲染出的字号不超过 6 种，最小不低于 12px（KaTeX 内部除外）；
  - 可点目标桌面不小于 28px，手机不小于 40px；
  - 没有横向溢出；
  - 空态、加载态、错误态按 `plan.md` §4.6 处理：空态说明为什么空、下一步做什么；超过 300ms 才显示骨架屏；错误写出原因并给「重试」。
- **消除的缺陷：**
  - 报告页的文件上传换成 `ui/filedrop`（D6）；
  - 所有页面不再用 emoji 当图标（D7）；
  - 目录页的「重新扫描」放在本页工具栏里（DP4）。
- **主题和尺寸：** 深色、浅色主题下都正常，390px 宽的手机上也正常。
- **手机收件箱页：** `inbox_mobile.html` 的外观接入 tokens 和 base 样式，功能不变。

### 代码与数据流

- **数据所有者都在 `domain/`：**

  | 数据 | 所有者 |
  |---|---|
  | 统计快照 | `domain/data.js` |
  | Session 列表 | `domain/sessions.js` |
  | 历史 Ledger | `domain/history.js` |
  | 标记 | `domain/labels/` |
  | 题目 | `domain/question/` |
  | 筛选 | `domain/items.js`，吸收 `core.js` 的 `filterItems`、`getDueDays` 等 |

  页面只经 `domain/` 读取和写入数据。写操作成功后，经 bus 通知其它页面刷新。
- **旧文件都删除了：**
  - `assets/` 顶层只剩 `app/`、`vendor/`、`inbox_mobile.html`。
  - `omrs_dashboard.html` 只剩外壳骨架和各页的挂载根。
  - 以下都不再存在：`legacy-bridge.js`、`legacy-pages.js`、`styles/legacy-bridge.css`、`styles.css`、旧 token 别名、`switchTab`、页面代码写的 `window.*` 旧全局、`tests/ui_baseline.json`。
  - `check_ui.py` 对全仓零容忍。
- **旧测试有去处。** 原来载入旧文件的 node 测试，要么迁到 `tests/app/*.test.mjs`（用例只增不减），要么随被测代码一起删除，并在日志里写明每个用例的去向。

### 流程

- 本机分支 `frontend-rearch` 上的提交顺序是：一个基线提交，（规划补丁提交，）一个本机记录提交，之后每页一个提交。
- 每个提交都包含：代码、测试、文档、任务日志、`progress.md` 的更新。涉及运行代码时还包括版本号。
- 全部完成时，`progress.md` 的状态是「全部完成，待部署」，§8 写好部署和回滚步骤。生产仍停在原来的版本。

---

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
## 关键技术决策

1. **基线用一个快照提交，不事后重建逐期提交。**
   - 事后重建需要把补丁链 ① 到 p6r5 从 v1.18.2 起逐个重放。但本机在补丁链之外，还有 v1.18.2 到 v1.19.1 等从没提交过的改动，重放出来的结果和现有工作树不一定一致，风险大，收益只是历史更细。
   - 快照提交不改动任何文件，随时可以 `git reset --soft` 撤回。
   - 从基线往后，每页一个提交，回滚粒度照样足够。
2. **开发区的位置。**
   - 服务运行在工作区时（情况 A），开发放在 `git worktree` 里，生产目录停在基线提交。原因是 `/assets/*` 按请求读磁盘，在生产目录里改文件等于直接上线。
   - 服务在别处时（情况 B），原地开新分支开发。
3. **版本号规则。** 凡是改动 `assets/`、`omrs/`、`omrs_dashboard.html` 的提交，都升一个补丁号。P6 从 v1.25.5 起逐页递增，P7 从 v1.26.0 起，P8 从 v1.27.0 起。只改测试或文档的提交不升版本号。
4. **大页面的迁移中间态：** 先做新外壳，把旧 DOM 托管在挂载点里，再逐个工作区迁移。这是复习调度已经验证过的做法，每一步都能上线。不要一次性重写整页，那样要在一个提交里同时重写、测试和审阅几千行代码。
5. **写操作之后怎么刷新：**
   - 页面不直接刷新别的页面，也不 import 别的 feature。
   - 写操作由 domain 执行，成功后先 `qvInvalidateMany`，再调用相关 domain 的 reload（`data` 和 `sessions` 本身已有并发合并），然后发 bus 事件。
   - 页面在 `mount` 里订阅事件，在卸载函数里退订。
   - 卸载以后才返回的异步结果不得渲染（mount 期间用一个 token 或 `AbortController` 判断）。
6. **旧全局的兼容：**
   - 新代码不写 `window.xxx`。
   - 未迁页面仍在调用的旧函数，经 `install<领域>Bridge` 挂到全局，每条注明调用方和删除期。
   - 到 P8 结束，过渡桥必须为空并删除。
7. **元素 id：** 只保留测试、其它模块或 `inbox_mobile.html` 仍在引用的 id，其余随新模板改。每页盘点时先 `grep` 一遍。
8. **旧测试的去处：** 旧 node 测试在 vm 沙箱里从旧文件抽函数来测。被测函数迁走以后，测试改成 import 新模块，断言原样保留，用例只增不减。整个测试文件迁走时删除原文件，并在日志里列出新旧用例的对应关系。
9. **浏览器运行方式：**
   - 所有浏览器测试都用 `tests/browser_runtime.launch_chromium`。
   - 本机独立 Chromium 会崩溃时，改用 `OMRS_TEST_CDP_URL` 指向本机的可信 CDP。CDP 模式下每个测试只关闭自己建的 context。
   - 同一次截图对比，两侧必须用同一种运行模式。
   - 日志里写明每次验证用的是哪种模式。
10. **审计口径：**
    - 「行内样式」只统计值非空的 `style` 属性；
    - 字号种数、最小字号、行内样式都排除 `.katex` 内部；
    - 截图脚本和 E2E 审计必须用同一口径。
11. **删除 `switchTab`（P8）。** `plan.md` §6 P8 要求删除这层包装。测试改用 `location.hash = '#/<页>'`，等页面挂载完成后再操作。
12. **终检由 Codex 执行。** 用户这次的指示（U15）替代了 U12 里「由 CCW 做终检」的安排。如果用户另外指定了独立检查者，Codex 的终检记录就作为那一方的输入。
13. **部署执行者由用户指定。** 未指定时按 U13 由 Hermes 执行。无论谁执行，都要先得到用户授权。
14. **任务日志归属：**
    - P6 剩余的工作继续写在 `2026-09-25_frontend-rearch-p6.md` 里（同一个逻辑任务）；
    - P7、P8、终检各开一份新日志，文件名用实际日期；
    - 每个提交后运行 `--write-log-index`。
15. **不做计划外的设计改动。** 各页的视觉只按 `plan.md` §4 的设计尺度和 D 编号缺陷来做，不重做信息架构，不改文案。确实发现设计问题时，记进 `optimization.md`。

---

## 边界情况

### 各页共同

- **快速切页：** 请求还没返回就切走，返回后不得渲染到已卸载的根上，也不能报错。
- **服务重启或网络失败：** 首次加载失败时显示原因和「重试」；已有数据时刷新失败，保留旧数据，只在页首报错。
- **空数据：** 分别用 `make_vault.py --profile empty` 和 full fixture 检查。
- **重复提交：** 所有写按钮在请求期间置忙，连点只发一次请求。
- **写操作部分成功：** 批量操作要逐项报告结果，已成功的项不回滚，界面状态以服务端返回为准。
- **快捷键与 Esc：** 只在本页生效；弹层打开时让位给弹层；离开页面后失效。
- **深色主题、手机 390px、紧凑密度：** 三种情况下都要审计。

### 各页特有

- **历史记录：**
  - 只有创世节点；
  - 已撤销的节点再撤销（按钮不可用，或服务端报错时给出明确提示）；
  - 修正模式下切走再回来时模式的状态（保持旧行为）；
  - Ledger 时区设置变化后，时间显示要更新。
- **目录：**
  - 树接口失败时退回后备树；
  - 大树的展开全部；
  - 搜索没有结果；
  - 剪贴板权限被拒绝。
- **报告：**
  - 非 HTML 文件、超大文件、读取失败；
  - 删除正在查看的报告；
  - 报告内容里有脚本（必须仍被 sandbox 隔离）。
- **设置：**
  - 保存只成功一部分（例如网络设置和 AI 设置分开提交）；
  - 重启期间旧实例还在响应（必须等到新的 `instance_id`）；
  - 免 PIN 网段格式非法；
  - 离开页面时有未保存的修改（保持旧行为，不新增拦截）。
- **录入题目：**
  - 粘贴时剪贴板被拒绝；
  - 超大图片；
  - 框选时快速连续编辑（防抖以后只保存最后一次）；
  - 检测任务进行中切走页面，或服务重启；
  - 批量提交部分失败；
  - 收件箱为空。
- **展示板：**
  - 保存还在队列里时切走或刷新；
  - `previewToken` 过期的预览消息必须丢弃；
  - 锁定的板只补印新增部分；
  - 拖拽中途按 Esc。

---

## 修改范围

### 预计涉及

- `assets/app/`：`features/` 下新增 history、catalog、reports、settings、create、board；`domain/` 下 `history.js`、`items.js`、`labels/`、`board.js` 等；`main.js`、`shell.js`、`legacy-bridge.js`、`legacy-pages.js`（最终删除）；`styles/`（`tokens.css`、`base.css`，最终删除 `legacy-bridge.css`）；`ui/`（只在确有需要时补组件状态，并同步 gallery）。
- `assets/*.js`：迁完一个删一个，最终全部删除；`assets/styles.css` 逐步删减，最终删除；`assets/inbox_mobile.html` 只接入 tokens。
- `omrs_dashboard.html`：各页面板换成挂载根，最终只剩外壳。
- `omrs/version.py`：只改版本号。
- `tests/`：新增 `tests/app/*.test.mjs` 和 `tests/e2e/*.py`；迁移旧的 node 测试；修改 `visual/run.py`、`check_ui.py`、`test_ui_gates.py`、`ui_baseline.json`（最终删除）。
- 文档：`AI/frontend/*.md`、`AI/inbox.md`、`AI/board.md`、`AI/changelog.md`、`AI/optimization.md`、`AI/environment.md`、`AI/README.md`、`README.md`（版本号）、`AGENTS.md`（只改映射表）、`AI/plans/frontend-rearch/plan.md` 和 `progress.md`、`AI/logs/` 下的日志。

### 明确不要修改

- 后端的业务逻辑和 API：`omrs/` 下除 `version.py` 以外的文件。如果确实发现前端依赖某个后端缺陷，停下来报告。
- `omrs/export_templates/`，以及导出和打印的输出格式。
- 推荐和记忆算法、数据格式、Ledger。
- `AGENTS.md` 里维护者、运行模式、受限模式的规则，以及 `AI/environment.md` 的受限模式配方。以后 CCW 仍可能按这些规则工作。
- `deploy/`、systemd、Nginx、生产目录、`错题/`、任何真实 Vault。
- 历史任务日志里已有的内容。只允许在文末追加，或做明确标注的勘误。

### 本次必须完成

阶段 0 到 5 的全部内容。

### 可以顺手处理

仅限低风险、直接相关的事项：

- `board.js` 的 `[data-ui-ok]`；
- 本页迁移时发现的明显死代码（确认无人引用后删除）；
- 本页 CSS 里与新写法冲突的旧覆盖规则；
- `instant.py` 的偶发失败，如果定位时顺手就能修。

### 本次不要处理

- 引入框架、构建、npm、TypeScript，或者 DP1 的备选方案 Preact；
- 拆分 `AI/api.md`（`check_docs` 只是提醒）；
- 后端性能或接口的「顺便改进」；
- 新功能，以及信息架构或文案的重做；
- 改写旧日志；
- 合并或重排已经存在的提交历史；
- `git push`、部署、生产重启。

---

## 验收标准

### 流程

1. 分支 `frontend-rearch` 上的提交顺序是：基线提交 →（规划补丁提交）→ 本机记录提交 → 每页（展示板按子步骤）各一个提交。每个提交单独检出后门禁全绿。
2. 仓库里和输出目录里都没有新产生的 `changes-*.patch`、`UPGRADE-*.md`、`HANDOFF-*.md`、完整 zip 或截图包。
3. `progress.md` 状态块里的基线是实际的提交哈希；阶段 0 的记录已写进 p6 日志；`check_docs` 通过。
4. 生产服务的版本和进程在整个过程中都没有变化；生产目录的文件停在基线提交（情况 A）。

### 每页（P6、P7 各页都适用）

5. 该页不再出现在 `legacy-pages.js` 里；对应的旧 JS 已删除；`styles.css` 里只服务该页的规则已删除。
6. 该页的 E2E 全部通过，其中桌面 / 手机 × 浅色 / 深色四项审计都满足以下全部条件：字号不超过 6 种且最小不低于 12px（KaTeX 除外）、可点目标不小于 28 / 40px、没有非空 `style` 和 `on*`、没有横向溢出。
7. 截图脚本的 `--audit-only` 对该页给出同样的结论。
8. 旧测试迁移后，用例数量不减少，日志里有新旧对应表。
9. 分册文档、`AGENTS.md` 映射表、`changelog`、任务日志、`progress.md` 都已更新；`check_docs --diff HEAD` 退出码为 0。
10. 各页特有的要求：
    - 历史记录：撤销再还原以后，仪表盘「最近动态」同步更新；`dashboard.py` 仍为 26 / 26。
    - 目录：小于 28px 的可点目标为 0；「重新扫描」在本页工具栏里。
    - 报告：上传使用 `ui/filedrop`；E2E 断言报告 iframe 的 `sandbox` 属性不含 `allow-same-origin`。
    - 设置：设置页能下载脱敏源码包；`test_source_export.py` 通过；E2E 没有真的触发重启。
    - 录入题目：「上传 → 框选 → 转换 → 提交」主路径在 E2E 里走通（AI 用固定结果）；提交后上下文字段保留。
    - 展示板：四个 `smoke_board_*` 和新的 `tests/e2e/board.py` 都通过。

### P8

11. `assets/` 顶层只剩 `app/`、`vendor/`、`inbox_mobile.html`。`grep` 结果为零：`styles.css`、`legacy-bridge`、`legacy-pages`、`switchTab`、`ui_baseline`。
12. `check_ui.py` 在没有基线文件的情况下报告 0 处问题。`assets/app/` 下 JS 单文件不超过 400 行，CSS 不超过 300 行。
13. 全站只有一套 toast、一套对话框、一套空态、一套 tag（`plan.md` §2「组件唯一」）。

### 终检

14. 在新 worktree 里从零跑全部门禁和 E2E，结果全绿，计数写进 progress §4。
15. 12 页的指标表全部达标，或者逐项写明例外并登记到 `optimization.md`。
16. 全量截图对比的每一处差异都在日志里有解释；empty fixture 下所有空态都符合 `plan.md` §4.6。
17. Firefox 和 WebKit 的主路径已执行，或者写明未执行的原因。
18. progress 状态为「全部完成，待部署」，§8 有完整的部署和回滚步骤。

### 不回归

19. 已迁页面的 E2E 仍然全部通过：dashboard、data、questions、schedule、instant、feedback、ui_bridge、shell_router。`smoke_schedule_workbench` 仍然通过。
20. `check_contrast` 为 0 不达标；Python 测试全部通过。

---

## 验证步骤

**环境准备：** 每次都在开发区里执行。

```bash
unset OMRS_SYSTEMD_SERVICE          # 防止隔离实例的 /api/restart 去重启生产
# 本机独立 Chromium 崩溃时：
# export OMRS_TEST_CDP_URL=http://127.0.0.1:9222   （只允许本机可信端点）
```

**全量门禁：** 每个提交前都要跑。

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -q
node --test tests/*.js tests/app/*.test.mjs
python3 tests/app/run_browser.py
for t in shell_router ui_bridge dashboard data schedule instant feedback questions; do python3 tests/e2e/$t.py; done
# 加上已新增的 tests/e2e/{history,catalog,reports,settings,create,board}.py
python3 -m unittest tests.smoke_schedule_workbench
python3 tests/check_ui.py
python3 tests/check_contrast.py
python3 tests/check_docs.py --diff HEAD
python3 tests/check_docs.py --write-log-index
```

**P7 起追加的门禁：**

```bash
python3 -m unittest tests.smoke_board_integrity tests.smoke_board_print tests.smoke_board_print_geometry
python3 -B tests/smoke_board_lock.py
```

**截图对比：**

```bash
python3 tests/visual/run.py --ref <上一个提交>
python3 tests/visual/run.py --audit-only
python3 tests/visual/run.py --audit-only --fixture empty   # 用于检查空态
```

**手工路径：** 每页都要做。在隔离实例上用真实浏览器打开 `#/<页>`，走完主路径，再切到别的页面、切回来、刷新，看控制台有没有错误。截图存在 `/tmp`，不入库，只在日志里描述。

**计数变化：** 门禁计数变化时，同步更新 progress §4。unittest 的起点是 159，node 的起点是 220。

---

## 执行原则

- **先读后改。**
  - 开始前读规范来源里列出的文档；
  - 每页动手前先盘点现有代码；
  - 实际代码与本说明的假设不一致时，以代码为准，并在日志里写明差异。
- **可以调整的与不能改的。** 实现细节可以调整；目标、API 契约、不变量和验收标准不能改。确实需要改范围或顺序时，按 AGENTS 规则先改 `plan.md`，再在 progress §9 登记。
- **复用现有抽象。** 能用 `core/`、`ui/`、`domain/` 和 progress §6 的现成写法解决的，不要另起新架构；不做与当前页无关的大规模重构。
- **连续执行，不要在中途问「要不要继续」。** 只有遇到下面这些情况才停下，停下时说明事实、选项和推荐：
  1. 阶段 0 发现生产页面出错，或合并结果不完整；
  2. 要完成任务就必须改后端 API、数据格式或打印协议；
  3. 需要执行会丢失数据的 git 操作；
  4. 某项门禁经过合理排查仍无法转绿，而原因在本任务范围之外；
  5. 终检完成（这是正常的终点）。
- **会话中断后的恢复。**
  - 每个会话开始时，先看 `git status`、`git log --oneline -15`、`progress.md` 的状态块。
  - 本页没做完就要结束会话时，未提交的改动留在开发区，并在 `progress.md` 状态块写清停在哪一步、哪些门禁还没跑。
  - 不要提交门禁不绿的状态。
- **验证要打到用户看得见的那一层。** 单测全绿不算完成，必须有 E2E 和真实浏览器的主路径验证。交付说明要区分「已实际执行的验证」和「未执行的验证」，数字以实际运行结果为准。
- **最终汇报**（每次停下时，用中文）：
  - 完成了哪些提交（哈希、版本号、一句话内容）；
  - 实际运行的验证和结果；
  - 没有执行的验证和原因；
  - 遗留问题和不确定项；
  - 下一步。
