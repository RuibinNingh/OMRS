# AI 文件夹维护手册

本文件夹是 OMRS 项目的 AI 协作知识库，供 Codex、Claude 等助手和人工维护者快速建立上下文。当前工作区代码、测试和配置是行为事实，Git 历史用于解释设计意图；本目录负责把这些事实整理成可检索、必须随任务同步的维护文档。

仓库级强制规则见根目录 `AGENTS.md`。两者冲突时，先遵守 `AGENTS.md`，并在同一任务内修正文档冲突。

---

## 文件夹结构

```
AI/
├── README.md          ← 本文件：维护规则、命名规范、文件索引
├── algorithm.md       ← 记忆算法：时间衰减、调度优先级、熟练度状态机
├── api.md             ← HTTP API：所有端点定义与请求/响应格式
├── data.md            ← 数据结构：CSV 字段、UID 规则、Markdown 格式
├── frontend.md        ← 前端：仪表盘、视图、图表、筛选控件
├── export.md          ← A4/屏幕版自包含 HTML 导出
├── ledger.md          ← 不可变 Ledger、投影、恢复边界
├── optimization.md    ← 已知技术债、优化边界与已完成项
├── inbox.md           ← 收件箱录入流程（上传 / 框选 / 转换 / 提交 / 数据集）
├── labels.md          ← 用户标记：定义、YAML、投影与调度可选加成
├── board.md           ← 展示板：引用集合、版面设置、打印（全部 / 仅新增）与纸面记录、API
├── omr-import.md      ← 答题卡扫描 JSON 导入反馈页：协议、题号→UID、逐题判定（从 frontend.md 拆出）
├── changelog.md       ← 版本级变更摘要（倒序）；模块文档不再堆版本叙述
└── logs/
    ├── log.md         ← 已留痕任务的变更日志索引（完整历史以 Git 为准）
    └── YYYY-MM-DD_<主题>.md  ← 单次会话的详细变更记录
```

---

## 维护规则

### 每个任务都要执行

只要任务在仓库内产生持久化改动，AI 文档更新就是完成条件的一部分，而不是可选的后续工作：

1. **开始前**：读取根目录 `AGENTS.md`、本文件和任务对应的模块文档；运行 `git status --short`，避免覆盖既有未提交改动。
2. **实现中**：行为、接口、数据格式或架构一旦改变，同步修改对应模块文档，不等到以后补写。
3. **结束前**：检查 `git diff --name-status`；必要时用 `git log` / `git show` 复核变更意图，并逐项确认代码、测试和文档一致。
4. **每次留痕**：在 `logs/` 新建本任务日志，并在 `logs/log.md` 增加一行索引。日志至少包含“变更、影响文件、验证”；涉及历史补录时还要列出依据的提交。
5. **交付门槛**：不得在已知模块文档过时、日志缺失或验证记录与实际不符时宣告任务完成。

只读调查、答疑或最终没有产生仓库改动的任务不创建空日志；交付时说明未修改仓库。

### 改动与文档映射

| 改动 | 需要更新 |
|---|---|
| 记忆、调度、推荐、Leech 逻辑 | `algorithm.md` |
| HTTP 路由、请求体、响应字段、错误语义 | `api.md` |
| CSV、Ledger、Markdown、配置、报告存储 | `data.md`，必要时 `ledger.md` |
| A4/屏幕版导出、模板、导出 CLI/API | `export.md`，接口变化同时更新 `api.md` |
| 页面结构、样式、脚本、交互和可视化 | `frontend.md` |
| 技术债状态或跨模块维护边界 | `optimization.md`、本文件索引 |
| 用户可见行为、命令、目录、依赖或版本 | 根目录 `README.md` |
| AI 打包流程 | 确保根 `AGENTS.md`、`AI/*.md` 和 `AI/logs/` 都被打包 |
| 任何持久化仓库改动 | 当日任务日志 + `logs/log.md` |

### 什么时候不需要更新
- 未落入仓库的临时调试操作。
- 完全只读且没有修改文件的调查或答疑。

拼写、注释和纯格式修正通常不需要改模块行为说明，但只要它们构成本次仓库任务，仍应在本次任务日志中如实留痕。

### 事实优先级与写作要求

1. 当前工作区代码、测试和配置。
2. Git 提交与差异（用于解释何时、为何改变）。
3. AI 文档。

若第 3 项与前两项冲突，应修正文档，不得为了迁就旧文档改写现有行为。文档只描述已存在且可验证的事实；规划项必须明确标为“待办”，不能写成已经实现。端点、字段、函数、文件和验证命令尽量使用可搜索的准确名称。

三条硬规则（详见根 `AGENTS.md`「文档写法」）：**模块文档只写现在**，历史进 `changelog.md` / `logs/`；**一段一件事、不超过 800 字**；**已知缺陷只在 `optimization.md` 记一条**。交付前跑 `python3 tests/check_docs.py`，它会把违反前两条和「重复章节编号 / 引用不存在的文件」一并拦下。

---

## 命名规范

### 模块文档
- 全小写英文，无空格：`algorithm.md`、`api.md`、`data.md`、`frontend.md`。
- 新增模块时，命名应能从文件名直接判断内容，不超过 15 个字符。

### 变更日志文件
- 格式：`YYYY-MM-DD_<主题>.md`
- 主题用英文小写、连字符分隔，简短描述本次改动的核心：
  - `2026-04-22_bug-fixes.md`
  - `2026-04-30_exam-mode.md`
- 同一天有多次独立改动时，加后缀序号：`2026-04-22_bug-fixes-2.md`。
- 新任务应新建日志；只有纠正原记录中的事实错误时才修改旧日志，并在新任务日志中说明原因。

建议结构：

```markdown
# YYYY-MM-DD 标题

## 变更摘要
## 行为与兼容性
## 修改文件
## 验证
## 同步过的文档
```

---

## 项目基本信息

| 项 | 值 |
|---|---|
| 项目名 | OMRS（Obsidian Mistake Reconstruction System）|
| 当前版本 | v1.17.0 |
| 类型 | 个人错题本，Markdown + 本地 HTTP 服务 |
| 后端入口 | `omrs_engine.py` |
| 前端文件 | `omrs_dashboard.html`（结构）+ `assets/`（`styles.css` 与拆分的 JS）|
| 数据目录 | 结构化数据在 `错题/.omrs/`；生成的 AI 报告在 `错题/report/` |
| 依赖边界 | 核心 Python 运行路径无强制第三方库；图片优化可选 Pillow 或 `jpegtran`。前端无构建依赖，页面运行时可访问 Google Fonts，KaTeX 作为本地静态资源放在 `assets/vendor/katex/`（不可用时公式降级显示源码片段）；AI 识别与外部报告材料按配置使用网络。|

---

## 文件索引

| 文件 | 说明 |
|---|---|
| `algorithm.md` | 时间衰减、compute_mastery_update 状态机、统一优先级 `compute_priority`（EF 反推的有效难度）、SM-2、双列表推荐、Leech 检测、标记可选加成与 tuning |
| `api.md` | GET/POST 端点、请求体、返回字段（含 analytics/export-review/reports/image、目录树 `tree`、AI 识别 `ai-recognize`、标记/展示板与导出参数） |
| `data.md` | mastery/history/sessions CSV 字段、Markdown 题目格式与支持子集、UID、labels.json、boards.json、config.json、日志、report/ 报告存储、File_Path 分隔符 |
| `frontend.md` | assets/ 多文件结构与加载约定；仪表盘与行动推荐、题目库/标记/展示板、目录页、qview 与练习记录模块、调度/推荐、数据复盘、报告托管、设置与 AI 录入、深色对比度约定。只写当前行为，顶部有目录 |
| `export.md` | A4/屏幕版与展示板自包含 HTML：浏览器分页/切片、Markdown 表格、题间留白、仅打印新增（纸面记录）与导出入口 |
| `ledger.md` | **v1.1.0 Ledger 架构**：不可变提交链、投影缓存、隐藏 question_id、工作区自检、历史修正、迁移和正文不做版本控制的边界 |
| `optimization.md` | 当前技术债、风险边界、已有测试覆盖与已完成优化 |
| `inbox.md` | **v1.12.0 收件箱录入流程**：上传 → 框选 → 转换 → 提交的暂存层、`/api/inbox/*`、后台 job、AI 框选与可转性判断、训练数据集与待办；v1.13.0 §8 框选提供方（vlm / template / local_http）、盲标、自动策略、清理 |
| `labels.md` | **v1.14.0 用户标记**：`labels.json` 定义、题目 YAML `标记:`、`question_labels` 投影、单题/批量 CRUD、改名/删除/合并与可选调度加成 |
| `board.md` | **v1.14.0 展示板**：`boards.json` 引用模型、CRUD/排序、停用与缺失题处理、左题右空 A4 版面、答案附页与绝对页码 |
| `omr-import.md` | 答题卡扫描 JSON 导入反馈页：唯一接受的协议形态、题号→UID 对应、逐题判定、三个入口一套解析 |
| `changelog.md` | 版本级变更摘要，倒序；每个版本一段，改了什么、为什么 |
| `logs/log.md` | 变更日志总索引 |
