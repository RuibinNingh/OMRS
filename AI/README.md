# AI 文件夹维护手册

本文件夹是 OMRS 的 AI 协作知识库，供 Hermes Agent、Codex、Claude Code Web 等维护者快速建立上下文。当前工作区的代码、测试和配置是行为事实，Git 历史用于解释设计意图；本目录把这些事实整理成可检索、须随任务同步的文档。协作规则、代码到文档的映射以根目录 `AGENTS.md` 为准（P4 起映射表登记了 `assets/app/features/feedback/`）。

---

## 按任务找文档

先读下表定位，再只读相关文档的速查头（每份模块文档开头的 `> **速查**` 块）。速查头已经够用时不必通读全文。

| 任务涉及 | 先读 |
|---|---|
| 某个页面的交互或样式 | `frontend.md`（索引）→ `frontend/` 下对应分册 |
| 颜色、字号、间距等设计 token，前端纪律门禁 | `frontend/design-system.md` |
| HTTP 接口 | `routes.md`（路由 → 文档）→ `api.md` 对应小节 |
| AI 助手（Harness、工具、权限、对话存储、撤销） | `agent.md`，页面见 `frontend/assistant.md` |
| 登录、PIN、访问控制、路径安全 | `security.md` |
| 记忆算法、调度、推荐 | `algorithm.md` |
| 数据格式、Ledger、投影 | `data.md`、`ledger.md` |
| 导出与展示板打印 | `export.md`、`board.md` |
| 收件箱、标记、答题卡导入 | `inbox.md`、`labels.md`、`omr-import.md` |
| AI 草稿区（助手录题、草稿存储、只读接口） | `drafts.md` |
| 技术债与已知缺陷 | `optimization.md` |
| 维护者环境、可用工具、协作配方 | `environment.md` |
| 某版本改了什么 | `changelog.md` |
| 跨多轮、多人接力的大任务（总纲、执行说明、进度、下一步） | `plans/README.md` → `plans/<计划>/progress.md` |
| 把需求写成执行计划（CCW 规划模式） | 根目录 `AGENTS.md`「规划模式」→ `plans/README.md` |

---

## 维护规则

- 行为、接口、数据格式或架构一旦改变，按 `AGENTS.md`「代码到文档的对应关系」同步模块文档，不等到以后补写。
- 每次产生持久化改动都在 `logs/` 新建任务日志；索引 `logs/log.md` 由脚本生成，不手改。
- 交付前运行 `python3 tests/check_docs.py --diff <基线>`，退出码必须为 0。改前端时另跑 `python3 tests/check_ui.py` 与 `python3 tests/check_contrast.py`（规则见 `frontend/design-system.md`）；改了 `assets/app/` 再跑 `python3 tests/app/run_browser.py`（组件见 `frontend/components.md`）。它的规则写在脚本文件头；改了路由后先运行 `--write-routes`，完整模式新增日志后运行 `--write-log-index`。
- 属于某个计划的任务，收尾更新 `plans/<计划>/progress.md`；`tests/check_docs.py` 检查每个计划文件夹有 `plan.md` 与 `progress.md`、`progress.md` 有状态块。
- 只读调查、答疑或没有产生仓库改动的任务不创建空日志，交付时说明未修改仓库。
- 事实优先级：当前工作区代码、测试和配置 > Git 历史 > AI 文档。文档与代码冲突时修文档，规划项必须标为「待办」。

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

## 背景
用户原话、所属计划（如有）、运行模式与基线（受限模式写导出包时间戳）。

## 行为变化
用户能看到或会受影响的变化；没有行为变化的写「无」。

## 影响文件
按 `git diff --name-status` 归类列出，并说明原因。

## 验证
已实际执行的命令与结果；未执行的验证与原因。

## 合入（仅受限模式交付）
补丁基线、应用命令、预期门禁计数、需要完整模式补做的步骤及验收标准。
```

---

## 项目基本信息

| 项 | 值 |
|---|---|
| 项目名 | OMRS（Obsidian Mistake Reconstruction System）|
| 当前版本 | v1.28.1 |
| 类型 | 个人错题本，Markdown + 本地 HTTP 服务 |
| 后端入口 | `omrs_engine.py` |
| 前端文件 | `omrs_dashboard.html`（结构）+ `assets/`（旧 `styles.css` 与拆分的 JS）+ `assets/app/`（ES Module：token、ui 组件、过渡桥、domain 层、已迁页面 `features/` 下的 dashboard、data、questions、schedule、instant、feedback、history、catalog、reports、settings、assistant、board）|
| 数据目录 | 结构化数据在 `错题/.omrs/`；生成的 AI 报告在 `错题/report/` |
| 依赖边界 | 核心 Python 运行路径无强制第三方库；图片优化可选 Pillow 或 `jpegtran`。前端无构建依赖，Noto Sans SC 与 JetBrains Mono 由 `assets/vendor/fonts/` 本地提供，KaTeX 作为本地静态资源放在 `assets/vendor/katex/`（不可用时公式降级显示源码片段）；AI 识别与外部报告材料按配置使用网络。|

---

## 文件索引

| 文件 | 说明 |
|---|---|
| `algorithm.md` | 时间衰减、熟练度状态机、统一优先级、SM-2、双列表推荐、Leech 检测、标记加成与 tuning |
| `agent.md` | AI 助手后端：运行时、循环、权限、工具、事件、接口、`agent.db`、按运行撤销 |
| `api.md` | 端点的请求体、响应字段与错误语义 |
| `routes.md` | 路由总表（自动生成，来源 `omrs/server.py` 与 `omrs/agent/http.py`）：方法、路径、说明文档 |
| `data.md` | CSV 字段、Markdown 题目格式、UID、labels.json、boards.json、config.json、auth.json、报告存储 |
| `frontend.md` | 前端索引，分册在 `frontend/`：设计系统（token 与门禁）、架构（core、路由、启动顺序）、ui 组件库与过渡桥、外壳与主题、仪表盘与目录、题库与标记、qview、展示板页、复习调度、反馈录入、设置、录入题目、历史 / 复盘 / 报告 |
| `export.md` | A4、屏幕版与展示板自包含 HTML 导出 |
| `ledger.md` | 不可变提交链、投影缓存、历史修正与迁移边界 |
| `board.md` | 展示板引用模型、版面设置、打印与纸面记录 |
| `inbox.md` | 收件箱「上传 → 框选 → 转换 → 提交」流程、后台 job、框选提供方 |
| `frontend/annotate.md` | 独立框选标注页 `/annotate`：训练数据批量采集、快捷键、导出（存储见 `data.md` §16） |
| `labels.md` | 用户标记定义、YAML、投影与可选调度加成 |
| `omr-import.md` | 答题卡扫描 JSON 导入反馈页 |
| `security.md` | 本机免 PIN、远端会话、来源校验、报告沙箱与安全路径 |
| `optimization.md` | 技术债、风险边界与已完成优化 |
| `environment.md` | 三类维护者的运行环境、工具清单、隔离实例与远端模拟配方 |
| `changelog.md` | 版本级变更摘要，倒序 |
| `plans/` | 计划文件夹：每个计划一个子目录，`plan.md` 总纲 + `exec-*.md` 执行说明 + `progress.md` 进度（约定见 `plans/README.md`） |
| `logs/log.md` | 任务日志索引（自动生成；不随脱敏源码包导出） |
