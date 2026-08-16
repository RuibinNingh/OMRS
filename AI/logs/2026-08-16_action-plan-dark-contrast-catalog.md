# 2026-08-16 行动推荐、目录页与深色对比度修订

## 背景

用户提出三项需求：给程序加上「行动推荐」、修掉暗色模式下配色显示不明显的问题、新增一个可以树状展示文件夹的目录页面。三项互相独立，合并为一次任务交付，版本从 v1.6.0 提到 **v1.7.0**。

## 变更摘要

### 1. 行动推荐（新增）

新增 `assets/actions.js`，在仪表盘 stat 卡与「最近动态」之间插入 `#action-plan` 卡。

- **纯前端派生**：只读已加载的 `DATA`（`/api/stats`）与 `SESSIONS`（`/api/sessions`），不新增接口、不写 Ledger、不改持久化状态。刷新时机挂在 `renderDash()` 末尾与 `refreshSessions()` 之后，`init()` 再补调一次（「未反馈 Session」那条依赖 SESSIONS，而 `reloadData()` 先于 `refreshSessions()` 完成）。
- **11 条规则**，四级排序 `urgent / warn / info / good`：`empty`、`overdue`、`due_today`、`pending_feedback`、`leech`、`untouched`、`cold`、`idle` / `never`、`low_not_due`、`weak_subject`、`weak_category`、`all_good`。除 `empty` 外全部排除已击杀题。完整判据表见 `AI/frontend.md` §1.1。
- 每条带数字依据与 1–2 个跳转按钮，按钮先清空目标页筛选控件再套 preset（`actionGoQuestions` / `actionGoInstant` / `actionGoReview` / `actionGoFeedback`）。回调是闭包，存在 `ACTION_PLAN[i].actions[j].run`，行内 `onclick` 只传下标 `runActionPlanItem(i,j)`。
- 默认显示前 4 条，其余折叠；卡头右上「建议今天练 N 道」= 逾期 + 今日到期 + 最多 3 道顽固题，封顶 20。

### 2. 深色对比度修订

问题分两层，根因不同。

**token 层**（`styles.css` 的 `[data-theme="dark"]`）：`--fg3` 由 `#6f685e` 抬到 `#8f887c`（对 `--bg2` 的对比度约 3:1 → 约 4.7:1）；`--bg` 压到 `#141311`，`.stat-card` / `.card` 的深色规则由半透明白渐变改为**实色 `var(--bg2)` + 描边**（原来卡片与页面底几乎同色，只能靠一层看不见的白叠加区分）；语义四色整体提亮一档并同步 `--*-rgb`（对 `--bg2` 均 ≥7:1）；`--border` `.10→.13`、`--border2` `.17→.23`、`--chart-surface` `.035→.055`、`--chart-line` `.11→.17`；侧栏底 `#161410→#0f0e0c`。

**规则层**：若干规则写死了浅色时代的颜色，token 切深色后不跟着走——`.q-answer .q-md` / `.instant-answer .instant-md` 的 `rgba(39,134,74,.04)` 深绿底、时间线 `.fam-review` / `.fam-session` 标签的深绿深蓝 10% 底、`.heat-0` 的 7% 空档与 `.heat-3/4` 压在浅绿上的白字、`.level-fill` / `.bar-fill` / `.chart-fill` 渐变低位停在 `.42`/`.72` 导致柱子淡进背景、`.btn.danger:hover` 的白字。全部改走 `var(--*)` / `rgba(var(--*-rgb), α)`，集中在 `styles.css` 末尾的「v1.7.0 深色对比度修订」注释段，一律以 `[data-theme="dark"]` 限定，**浅色 `:root` 未改**。卡中卡背景 `.04→.07`、`.btn` 底 `.05→.07` / hover `.10→.14`、`.input` 深色底改 `--bg3`。

### 3. 目录页（新增）

- 新增后端 `omrs/catalog.py`：`build_tree(vault)` 递归扫 `错题/`，返回嵌套目录树 + `summary` + `indexed_total`。**只读**，不写 Ledger、不改投影、不触发自检。跳过所有 `.` 开头的目录（故 `.omrs/` 不在树内，另用 `data_dir` 字段告知位置）；递归深度上限 `MAX_DEPTH = 12`，超出置 `truncated`；文件按扩展名分 `question` / `markdown` / `image` / `other` 四类，`question` 按 `mastery_data.csv` 补 `indexed` / `subject` / `category` / `tag`；未建 `错题/` 时返回空树而非报错。
- `omrs/server.py` 新增 `GET /api/tree` 路由（插在 `/api/scan` 与 `/api/config` 之间）。
- 新增 `assets/catalog.js` 与面板 `#panel-catalog`，侧栏在「题目库」与「复习调度」之间加「目录」项（新图标 `#i-tree`）。树结构来自 `/api/tree`；熟练度、待复习数、顽固题数由本地 `DATA.items` 按路径前缀逐层聚合后叠加（`catalogBuildStats()`）——这些状态刻意不放进后端接口，避免只读扫盘接口跟投影耦合。
- 交互：搜索（命中期间全树视为展开，不改动 `CATALOG_OPEN`）、全部展开/折叠、显示或隐藏非题目文件、复制相对路径、点题目文件调 `viewQ(uid)` 开详情。`/api/tree` 失败时降级为按 `File_Path` 推算的树并在状态栏说明。
- 渲染为扁平 `.tree-row` 序列 + CSS 变量 `--depth` 控制缩进，不是嵌套 DOM。

## 修改文件

**新增**

- `omrs/catalog.py`
- `assets/actions.js`
- `assets/catalog.js`
- `tests/test_catalog_tree.py`
- `tests/smoke_frontend_actions_catalog.js`

**修改**

- `omrs/server.py` — 引入 `build_tree`，新增 `GET /api/tree`
- `omrs/version.py` — `v1.6.0` → `v1.7.0`
- `omrs_dashboard.html` — 新增 `#i-tree` / `#i-target` 雪碧图符号、「目录」导航项、`#panel-catalog` 面板、`#action-plan` 卡；追加 `actions.js` / `catalog.js` 两个 `<script>`（置于 `recommend.js` 之后、`instant.js` 之前）；侧栏版本号与 `styles.css` 缓存串更新
- `assets/styles.css` — `[data-theme="dark"]` token 重配、深色卡片改实色；文件末尾追加深色修订段、`.act-*` 与 `.catalog-bar` / `.tree-*` 样式
- `assets/app.js` — `switchTab` 的 `TT` 加 `catalog`、切到目录页时 `loadCatalog()`；`reloadData()` 在目录页激活时重画；`init()` 补调 `renderActionPlan()`
- `assets/dashboard.js` — `renderDash()` 末尾调 `renderActionPlan()`
- `assets/schedule.js` — `refreshSessions()` 末尾在 `DATA` 就绪时重画行动推荐

**文档**

- `README.md` — 特性表加「行动推荐」「目录」两行、外观行补对比度修订、目录结构加 `catalog.py` 与两个前端文件、API 表加 `/api/tree`、版本表加 v1.7.0、CSS 技术债补注
- `AI/api.md` — 新增 `GET /api/tree` 完整定义
- `AI/frontend.md` — 版本沿革加 v1.7.0；文件组织与加载顺序补两个新文件；新增 §1.1 行动推荐、§2.1 目录页、§10 主题与深色对比度
- `AI/README.md` — 当前版本改 v1.7.0，`api.md` / `frontend.md` 索引描述同步
- `AI/optimization.md` — CSS 债条目补「写死浅色」这一类及其处置；测试覆盖条目补新增测试，并新记一条「测试运行方式不统一」
- `AI/logs/log.md` — 增加本日志索引

## 验证

| 项 | 命令 / 方式 | 结果 |
|---|---|---|
| Python 单元测试 | `python3 -m unittest discover -s tests -p 'test_*.py'` | 15 passed（含新增 `test_catalog_tree.py` 4 项） |
| `test_report_export.py` | 该文件是 pytest 风格（`monkeypatch` / `tmp_path` fixture），本次环境无 pytest 且无法安装，改用等价的最小 fixture 垫片逐个调用 | 5 passed |
| 前端逻辑冒烟 | `node tests/smoke_frontend_actions_catalog.js` | 20 项断言全过（空题库 / 有积压 / 无积压 三场景 + 目录树渲染、折叠、搜索） |
| JS 语法 | 对 `assets/*.js` 逐个 `node --check`；再按 HTML 中的加载顺序拼接后整体 `node --check` | 14 个文件通过；拼接后无顶层重复声明 |
| 接口实跑 | 新建含 3 道题、多级目录的临时 vault，`python3 omrs_engine.py --vault … serve` 后 `curl /api/tree` | 200；`.omrs/` 正确排除；`summary` 为 `dirs 4 / files 7 / questions 3 / orphans 0`；孤立文件场景另由单元测试覆盖 |
| 静态资源与页面标记 | `curl /assets/actions.js`、`/assets/catalog.js`、`/` | 均 200；页面含 `data-tab="catalog"`、`#panel-catalog`、`#action-plan` 与两个新 script 引用 |

## 未验证 / 限制

- **未做浏览器实测**：本次交付环境没有浏览器，行动推荐卡与目录树的实际视觉（含深色对比度改动的观感）未经截图回归。对比度是按 WCAG 相对亮度公式手算的，`--fg3` 与语义色达标，但深色下「卡片与页面底」的绝对亮度比在暗端天然只有约 1.13:1，分层实际主要靠描边——如果仍觉得卡片边界不够，下一步应调 `--border` 而不是继续调背景。
- `/api/tree` 每次请求现扫磁盘，没有缓存。题库达到几千个文件时会有可感延迟，届时可加 mtime 缓存。
- 目录页的结构只在进入页面或点「重新读取」时拉取；`reloadData()` 只重画叠加的熟练度，不重新扫盘。在 Obsidian 里新建文件夹后需要手动刷新。
- 单题级的目录内操作（重命名文件夹、拖动迁移）没有做，迁移仍走题目库的编辑菜单。
