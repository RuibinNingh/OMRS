# 错题本 / OMRS

> **O**bsidian **M**istake **R**econstruction **S**ystem — 一个面向个人学习的错题管理系统，基于 Markdown 与本地 HTTP 服务构建。

---

## 这是什么

OMRS 是一个**本地优先、核心运行时零必装第三方依赖**的个人错题本：

- 题目以 **Markdown 文件** 形式存放在 `错题/` 目录，可被 Obsidian 等笔记软件直接打开、编辑、双链。
- 一个 **Python 后端** 读取题库、提供 HTTP API、维护不可变的提交链（Ledger），所有算法（记忆衰减、SM-2、调度、Leech 检测）都是纯标准库实现。
- 一个 **HTML/CSS/JS 单页前端**（`omrs_dashboard.html` + `assets/`）负责录入、即时练习、复习 Session、反馈、数据复盘与导出。
- 没有构建步骤，题库、算法、Ledger、复习和导出均可离线使用；AI 图片识别、Google Fonts 以及报告中用户选择的 HTTPS 外部资源属于可选联网能力。

当前版本：**v1.16.0**。

---

## 已知技术债

完整清单见 [`AI/optimization.md`](AI/optimization.md)。目前最值得优先处理的是：

| 优先级 | 技术债 | 影响 | 建议方向 |
|---|---|---|---|
| 高 | v1.16 题库练习记录的数据源错配 | 正式复习已写入 Ledger 的题目，详情和画廊仍可能显示“未练过” | 让记录模块读取 Ledger/兼容历史投影，随后删除对 Markdown `# 历史` 的依赖 |
| 高 | HTTP 服务单线程 | AI 识别等慢请求会阻塞整个界面 | 改用线程化 HTTP Server，并为 CSV、Markdown、Ledger 写入增加统一锁 |
| 中高 | Ledger 每次全量重放 | 历史提交增长后，反馈/录入后的重建耗时线性增加 | 引入按 seq 的持久化快照和增量重放 |
| 中 | 前端大量 `innerHTML` + 行内 `onclick` | DOM 高频重建、事件逻辑与模板耦合，也阻碍 ES Module 化 | 反馈工作台已在 v1.10.0 改为局部更新 + 事件委托；其余列表页仍待处理 |
| 中 | 后端 `server.py` 路由分支过长 | 请求解析和错误处理重复，维护成本高 | 改为路由表 + 统一请求体解析 |
| 中 | 测试框架与覆盖不完整 | 当前 `unittest` 与 pytest 风格测试混用，核心算法边界覆盖仍不足 | 统一测试入口，补齐算法、Ledger 集成、异常输入和浏览器回归 |
| 低 | 局域网模式无用户认证 | `allow_external` 开启后同网段客户端可读写 | 仅在可信 LAN 使用，后续再设计认证与权限模型 |

这些项目是已知的维护与扩展成本，不影响当前核心功能运行；其中线程化服务、增量投影和鉴权涉及架构/安全边界，实施前应单独设计和验证。

---

## 特性一览

| 模块 | 能力 |
|---|---|
| **收件箱录入** | v1.12.0 起「录入题目」页改为 **上传 → 处理 → 录入** 三步：手机在同一 Wi-Fi 打开 `http://<局域网IP>:8471/m` 直接投整张截图（sha256 去重）；电脑端在网页上框题目 / 答案（可多题卡），每块可「转文本」（AI 转录 + 判断能否转）或「保留图片」；AI 框选（长图自动切片）、沿用上一张框位、整图即题目、批量勾选处理；就绪的题卡填科目分类后一键写入题库。所有框位、AI 原框、采纳方式、转换决策留作训练数据，「AI 训练」页可看统计并导出 JSONL / YOLO 数据集。v1.13.0：框选可选提供方（多模态模型 / 零联网的版式模板 / 训好后的本地检测服务）、每 N 张盲标作干净评估集、置信度达标自动转文本并就绪、上传即自动处理（需 Pillow）、超期丢弃图自动清理，都在「AI 训练」页配置。原单题表单保留为「快速录入」。收件箱数据集版式标签的新上传默认是「作业帮截图」（`zuoyebang`），可在处理页改为拍照/扫描、已裁好的题图或其他。详见 `AI/inbox.md` |
| **题目录入（快速）** | 两图片区（题面 / 答案）、Markdown 原文编辑、Obsidian 双链分类、`![[image]]` 嵌入图、AI 识别（外部大模型，按需调用）；题目库可单题停用/恢复（不参与复习与统计）或删除并保留可审计归档记录 |
| **记忆算法** | 时间衰减 `time_decay`、熟练度状态机 `compute_mastery_update`、SM-2 间隔、易错因子 EF、统一优先级 `compute_priority`、Leech（顽固题）检测 |
| **即时练习** | 浏览器内直接做、在线翻答案、即时反馈（分数滑杆 + 对错） |
| **复习 Session** | 调度器挑题 → 列表预览 → 反馈录入。v1.10.0 起反馈页是「题目列表 / 题目视图 / 判定面板」三栏工作台：录反馈时直接看到本 Session 全部题目（已录入置灰）、题面与答案双栏并排、可就地编辑 Markdown，不必来回切页；支持 J/K 切题、1 对 2 错、⌘/Ctrl+↵ 提交等快捷键。仍支持分批提交，序号始终对应 Session 原始题目顺序 |
| **答题卡回填** | v1.11.0 起可把答题卡扫描（OMR）的正式结果 JSON 读进反馈页：选中该 Session → 在 OMR 识别详情页复制 `/api/v1/recognitions/<id>/result` JSON → 点「📋 读剪贴板填写」或直接 ⌘/Ctrl+V，按题号自动填对错与 0–10 主观分。只接受顶层 `recognition_id/template_id/mode/status/questions/unresolved` 协议，明确拒绝旧 raw/items、裸数组与包装层；`unresolved` 涉及的题不自动猜测，转人工处理。Anki 模式仍按 `questions[].answer` 映射为 OMRS 评分。 |
| **行动推荐** | 仪表盘顶部按当前题库状态排出「现在该做什么」：逾期、今日到期、未录反馈的 Session、顽固题、久未复习、最薄弱科目/分类等，每条带数字依据和一键跳转 |
| **目录** | 树状展示 `错题/` 的真实文件夹结构，每层标注题量、待复习、顽固题与平均熟练度；支持搜索、展开折叠、显示非题目文件，点题目文件直接开详情 |
| **用户标记** | 自定义名称与颜色的 `<=>` 芯片；录入、题库、反馈、推荐、即时练习和展示板均可添加/筛选，支持批量编辑、改名、删除、合并；默认不改变调度，设置 `priority_bonus` 后才参与优先级 |
| **展示板** | 持久化题目引用集合，可拖拽/菜单排序、按标记同步、设置留白与装订边距，导出左题右空 A4「错题集」；不绘制打孔圆圈，但保留极浅装订导引线；打印后记录纸面，新加的题可**只补印新增**并接在原纸空白处，页码始终是绝对页码 |
| **题库交互重设计** | 筛选抽屉、激活条件 chips、列设置、舒适/紧凑密度、命名视图预设和批量加入展示板/打标记/停用/导出 |
| **练习记录（已知缺陷）** | v1.16.0 的画廊战绩带和题目详情记录模块只解析题目 Markdown 中遗留的 `# 历史` 文本；正式反馈不会再写该区，而是写入 Ledger 并投影到 `history_log.csv`。因此已有 `attempts` 的题也会显示“未练过”，且下一次复习不会自行补齐此界面；正式记录以 Ledger 及其兼容投影为准，待记录模块改用该数据源后才能正常展示。 |
| **数据复盘** | 仪表盘（统计/雷达/热力/散点/趋势）、Ledger 时间线、历史修正（显式开启修正模式）、撤销/恢复/还原 |
| **错题导出** | **自包含 HTML**（图片 base64 内联），分 **A4 打印版**、**展示板左题右空版** 与 **屏幕版**（卡片 + 判分 + 进度持久化） |
| **报告托管** | 上传/浏览/删除复盘报告，浏览器内直接查看 |
| **源码协助** | 设置页下载仅含 Git 已跟踪源码、测试和项目文档的脱敏 ZIP；自动排除个人题库、附件、运行数据、日志和生成导出文件 |
| **外观** | 深色（首次打开默认，**暖石墨 Warm Graphite**）/ 浅色（编辑式暖色）切换；v1.15.0 增加**界面密度**（紧凑 / 舒适，默认紧凑）——设置页「外观」切换，收紧全站内边距、圆角、行高与控件高度；v1.7.0 重配深色对比度（三级文字与语义色达标、卡片改实色分层）；Ledger 时间线可按浏览器或设置页所选时区显示 |
| **数据可信** | v1.1.0 起改用不可变 **Ledger 提交链** 作为结构化状态的唯一事实源；CSV 仅作兼容投影；学习、调度和 Session 状态可重放还原 |

---

## 快速开始

### 运行

```bat
:: Windows：直接双击
run.bat

:: 或手动
python omrs_engine.py serve
```

启动后访问 <http://localhost:8471/>。

### Linux / systemd

项目可部署在任意本地路径（以下以 `/opt/omrs` 为例），由 systemd 持久化运行：

```bash
sudo systemctl enable --now omrs.service
sudo systemctl status omrs.service
```

可参考 [`deploy/omrs.service`](deploy/omrs.service)。服务默认监听 TCP 8471；如需局域网访问，请在 `错题/.omrs/config.json` 中启用 `allow_external: true`，并仅对受信任的 LAN 网段放行端口。核心运行路径只依赖 Python 标准库，无需额外安装第三方包。

### 打包给 AI 协助

```bat
pack_for_ai.bat
```

会在 `_ai_packages/` 下生成一个 `.zip`，**不含 `.git` 与 `错题/` 数据**，但会保留根 `AGENTS.md`、全部 `AI/*.md` 和 `AI/logs/`，可直接交给 AI 助手协作。

---

## 项目结构

```
错题本/
├── omrs_engine.py          ← 后端入口（兼容垫片）
├── omrs_dashboard.html     ← 前端 HTML（仅结构）
├── omrs/                   ← 后端 Python 包（核心路径仅标准库）
│   ├── cli.py              ← 命令行入口 + HTTP 服务
│   ├── server.py           ← HTTP 路由
│   ├── ledger.py           ← 不可变提交链（SQLite）
│   ├── projections.py      ← 重放 Ledger 导出 CSV / 内存投影
│   ├── scheduling.py       ← 记忆算法（衰减/状态机/SM-2/优先级/Leech）
│   ├── ai_assist.py        ← AI 识别（外部大模型调用；含框选 detect 与可转性判断）
│   ├── inbox.py            ← 收件箱：上传 / 区域 / 后台 job / 提交 / 数据集（v1.12.0）
│   ├── catalog.py          ← 目录树（只读扫盘，供「目录」页）
│   ├── labels.py           ← 用户标记定义与题目标记级联
│   ├── boards.py           ← 展示板引用与打印设置（不进入 Ledger）
│   ├── exporting.py        ← 错题 HTML 导出
│   ├── feedback.py / sessions.py / creation.py
│   ├── analytics.py / stats.py / reports.py
│   ├── migration.py / workspace_sync.py / indexing.py
│   └── export_templates/   ← A4 / 展示板 / 屏幕版 HTML 模板（CSS + JS）
├── assets/                 ← 前端静态资源（无构建）
│   ├── styles.css
│   ├── core.js / app.js / dashboard.js / questions.js
│   ├── qview.js            ← 共享题目视图（题面/答案双栏），Modal / 反馈台 / 即时练习 / 画廊共用
│   ├── schedule.js / export.js / feedback.js / history.js
│   ├── recommend.js / actions.js / catalog.js
│   ├── instant.js / data.js / reports.js
│   ├── inbox.js            ← 收件箱录入流程（v1.12.0）；inbox_mobile.html 为手机上传页
│   ├── labels.js / qtable.js / board.js ← 标记、题库重设计与展示板交互（v1.14.0）
│   └── vendor/katex/       ← KaTeX（本地，公式离线渲染）
├── 错题/                   ← 题库（Markdown + Obsidian 双链）
│   ├── .omrs/              ← 结构化数据目录（Ledger / 投影 / 备份）
│   │   ├── ledger.db       ← v1.1.0+ 唯一可信事实源
│   │   ├── mastery_data.csv
│   │   ├── history_log.csv
│   │   ├── sessions.csv
│   │   ├── labels.json       ← 用户标记定义
│   │   └── boards.json       ← 展示板引用与打印设置
│   └── report/             ← 托管的 AI HTML 报告与 index.json
├── tests/                  ← 历史投影、AI 分类/提取、报告/导出回归测试
├── tool/migrate_ledger.py  ← 数据迁移工具
├── Task/2026-09-04_展示板-标记-题库重设计.md ← v1.14.0 归档设计与验收记录
├── Skills/                 ← 第三方技能目录
├── AGENTS.md               ← 仓库协作与强制文档收尾规则
├── AI/                     ← AI 协作知识库（见下）
├── run.bat                 ← 一键启动
└── pack_for_ai.bat         ← 一键打包
```

---

## 数据架构（v1.1.0+）

OMRS 的所有结构化状态以 `错题/.omrs/ledger.db` 为**唯一可信来源**——一个不可变的全局提交链。

- 每个反馈、每条修正、每次录入都生成一条 `commit`（`prev_hash` + `commit_hash` 哈希链接）。
- 旧 CSV（`mastery_data.csv` / `history_log.csv`）由 `omrs/projections.py` **重放 Ledger 导出**，仅作兼容、调试和迁移输入。
- 题目身份有两层：**UID**（Markdown 文件名，可改名/迁移）与 **`_omrs_id`**（隐藏稳定身份 `OP-000001`，写入 YAML）。历史反馈引用 `_omrs_id`，改名不会断链。
- 任何时候都能从 Ledger 重放出完整的结构化运行状态——这也是「撤销 / 恢复 / 还原」的原理；Markdown 题干、答案、备注、排版和图片引用顺序不做历史版本化。

详细见 [`AI/ledger.md`](AI/ledger.md)。

---

## 算法概览

**记忆衰减**

```
decayed = mastery × e^(-days / (mastery × 30 + 5))
```

熟练度越高衰减越慢；`mastery = 0` 不衰减。

**熟练度状态机**（反馈录入时）

| 情况 | 新熟练度 |
|---|---|
| 高分 + 答对 + 已连续 `kill_streak` 次 | `1.0`（已击杀） |
| 高分 + 答对 | `min(0.95, old + sub/20 × ef/2.5)` |
| 低分 + 答对 | `min(1, old + sub/30 × ef/2.5)` |
| 高分 + 答错 | `old × 0.8`（粗心） |
| 低分 + 答错 | `old × 0.3`（真不会） |

EF（易错因子）随之更新，高分答对 +0.15，答错 -0.2。

**统一优先级**

```
priority = (1 - decayed_mastery) × (eff_diff/10) + (days/60) × 0.3
```

其中 `eff_diff` 由 EF 反推得出（题目难度字段 `Difficulty` 不再喂公式，因其不变会灌噪声）。

所有阈值都可在 `错题/.omrs/config.json` 的 `tuning` 段覆盖。详见 [`AI/algorithm.md`](AI/algorithm.md)。

---

## HTTP API

默认端口 **8471**，详见 [`AI/api.md`](AI/api.md)。常用端点：

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/stats` | 题库条目 + 全部统计图表数据 |
| GET | `/api/status` | 服务状态 + 版本 + 工作区自检 |
| GET | `/api/analytics` | 分析聚合 |
| GET | `/api/labels` | 用户标记定义与引用数 |
| GET | `/api/boards` | 展示板列表 |
| GET | `/api/board?id=...` | 展示板详情与解析后的题目引用 |
| POST | `/api/create` | 录入新题 |
| POST | `/api/feedback` | 提交一次反馈 |
| POST | `/api/label/save` | 创建/更新用户标记 |
| POST | `/api/label/delete` | 删除标记并可解绑题目引用 |
| POST | `/api/label/merge` | 合并两个用户标记 |
| POST | `/api/question/labels` | 覆盖单题标记 |
| POST | `/api/questions/labels` | 批量添加/移除标记 |
| POST | `/api/board/create` | 创建展示板 |
| POST | `/api/board/update` | 更新展示板名称 / 备注 / 版面 / 条目顺序 |
| POST | `/api/board/printed` | 记录纸面（标记为已打印：全部替换 / 新增追加）；`/api/board/printed/reset` 重置 |
| POST | `/api/board/items/add` | 向展示板添加题目 |
| POST | `/api/board/items/remove` | 从展示板移除题目 |
| POST | `/api/board/duplicate` | 复制展示板 |
| POST | `/api/board/delete` | 删除展示板 |
| POST | `/api/export` | 导出 A4/屏幕版；`format:"board"` 导出展示板左题右空版 |
| POST | `/api/question/suspend` | 停用题目（保留正文与历史） |
| POST | `/api/question/resume` | 恢复题目 |
| GET | `/api/recommend` | 获取到期/熟练度双列表推荐 |
| GET | `/api/tree` | 错题目录树（只读扫盘，供「目录」页） |
| POST | `/api/schedule` | 创建复习 Session |
| POST | `/api/ai-recognize` | AI 识别图片 |
| * | `/api/inbox/*` | 收件箱：上传 / 框选 / 后台识别 job / 提交 / 数据集（见 `AI/inbox.md`） |
| GET | `/m` | 手机上传页 |
| GET | `/api/ledger/verify` | 校验提交链完整性 |

---

## 前端

入口 `omrs_dashboard.html` 是纯结构文件，样式与脚本拆到 `assets/`。

- **无构建步骤**：所有 JS 是普通 `<script>`（非 ES module），共享全局作用域。
- **图表纯 CSS + 内联 SVG**，无 ECharts/Chart.js 等图表库。
- **KaTeX** 放在 `assets/vendor/katex/`，公式离线渲染；不可用时降级显示源码。
- **响应式**：≤860px 侧栏自动转为顶部横滚条。
- **侧边栏应用式 shell** + 雪碧图图标，无外部图标库依赖。
- **行动推荐 / 目录树纯前端派生**：行动推荐只读已加载的 `/api/stats` + `/api/sessions`，不新增接口；目录页结构取自 `/api/tree`，熟练度等状态由本地题库按路径前缀叠加。

加载顺序（`core.js` → 模块 → `app.js`）详见 [`AI/frontend.md`](AI/frontend.md)。

---

## 错题导出

导出为**单文件 HTML**，图片 base64 内联、KaTeX 字体 data URI 内联——拷到任何带浏览器的设备都能打开。

- **A4 打印版**（默认）：导出时选择双栏或整份单栏；内容块会尽量填满栏位，放不下的块完整移到下一栏而不截断，临近栏底的公式文字按公式边界续栏，长图按白缝切片（缝带算法）；初次排版等待字体稳定，浏览器预览和打印复用同一版面，所见即所打印。
- **展示板左题右空版**：以 `boards.json` 的持久化题目引用为输入，左侧按题目顺序排版（KaTeX / 表格 / 长图切白缝 / 跨页续排）、右侧完全留白；标题固定为「错题集」，支持 22mm 装订边、极浅装订导引线、题间留白、附答案页、绝对页码；「仅打印新增」把新题排在纸面记录的续排位置，已打印区域留白，把原纸放回打印机即可补印。
- **屏幕版**：卡片式复习 App，可判对错、打分、记录进度（持久化到 localStorage）。

旧 docx 导出方案已被完全替换——HTML 既解决了「长图被截断 / 双栏栏底留白」问题，也让基础导出不再依赖 Pillow。详见 [`AI/export.md`](AI/export.md)。

---

## AI 协作

[`AI/`](AI/) 文件夹是给 AI 助手（Claude 等）用的**项目知识库**，每次对话先读它就能快速建立上下文。

根目录 [`AGENTS.md`](AGENTS.md) 把文档同步设为任务完成条件：每个在仓库产生持久化改动的任务，都要更新受影响的 `AI/*.md`、新建当日任务日志并更新日志索引。

```
AI/
├── README.md       ← 维护规则、命名规范、文件索引
├── algorithm.md    ← 记忆算法、调度、状态机
├── api.md          ← HTTP API 完整定义
├── data.md         ← CSV 字段、UID、Markdown 格式
├── frontend.md     ← 前端结构与加载约定
├── ledger.md       ← Ledger 架构
├── export.md       ← 错题导出 HTML 架构
├── optimization.md ← 优化空间 / 技术债清单
├── inbox.md        ← 收件箱录入流程
├── labels.md       ← 用户标记定义、YAML 与投影
├── board.md        ← 展示板引用、版面、打印（全部 / 仅新增）与纸面记录
└── logs/           ← 逐次会话的详细变更记录
```

任务日志写入 `AI/logs/`，总索引是 `AI/logs/log.md`。只读调查或没有修改仓库的答疑不创建空日志。

---

## 路线 / 已知技术债

节选自 [`AI/optimization.md`](AI/optimization.md)：

- [ ] **服务器单线程** — `ai-recognize` 调用大模型时整界面卡死，需换 `ThreadingHTTPServer` + 文件锁。
- [ ] **投影全量重放** — `rebuild_projection` 随历史线性变慢，需定期落投影快照。
- [ ] **后端路由超长 if/elif** — `server.py` 的 `do_GET`/`do_POST` 是手写分支链，可收成派发表。
- [ ] **CSS 重复定义** — `styles.css` 多次「现代化」后留下了真实叠加债，需按组件集中收拢。v1.7.0 已清掉深色下写死浅色的几处（答案块、时间线标签、热力格、柱状渐变），但同名规则的多处叠加仍在。

---

## 依赖

**核心运行时零必装第三方依赖。**

- Python：仅用标准库（`http.server`、`sqlite3`、`csv`、`json`、`struct`、`datetime`）。
- 可选图片优化：检测到 Pillow 时可深扫 PNG，检测到 `jpegtran` 时可无损优化 JPEG；缺失时基础功能不受影响。
- 前端：无 npm、无 webpack；KaTeX 作为本地静态资源放在 `assets/vendor/katex/`，Google Fonts 为可选外链。
- AI 识别：只有调用 `/api/ai-recognize` 时才访问用户配置的 OpenAI 兼容服务。
- AI 报告：核心 HTML 可自包含；报告提示词允许按需引用 HTTPS 字体/图表/图标资源，并要求失败时正文仍可读。
- 数据：纯文件（Markdown + SQLite/CSV），无外部数据库。

---

## 版本

| 版本 | 说明 |
|---|---|
| v1.16.0 | 题库练习记录界面：画廊战绩带（默认开，可关）+ 题目详情底部记录模块。当前错误地只解析不再写入的 Markdown `# 历史`，不能展示 Ledger 正式反馈；此限制已列为高优先级技术债，后端与数据格式未改。 |
| v1.15.0 | UI 改版：仪表盘重构为「今天 → 行动推荐 → 概览条 → 活动/薄弱科目 → 最近动态」，分布类图表交还数据复盘页；新增界面密度开关；题库、反馈录入、收件箱处理、展示板、即时练习改为整屏工作台（页面不滚，各栏独立滚动，表头吸顶） |
| v1.14.1 | 修复展示板「打印预览」弹窗被浏览器拦截：改为先同步开窗再填入导出结果 |
| v1.14.0 | 用户标记、持久化展示板（左题右空 A4 / 仅打印新增 + 纸面记录 / 绝对页码）、题库筛选抽屉与批量交互重设计 |
| v1.13.0 | 收件箱：框选提供方（多模态模型 / 版式模板零联网 / 本地检测服务 `local_http`）、盲标评估集、置信度自动就绪与上传即自动处理、超期丢弃图与裁图缓存清理、大裁图改 JPEG、拒绝计数增量化 |
| v1.12.0 | 收件箱录入流程：上传 → 处理（框选 / 转文本 / 留图）→ 录入；手机上传页；AI 框选与可转性判断走后台 job；训练数据集统计与导出 |
| v1.8.2 | 分批提交增强：允许只提交已判定题目，未判定题目自动保留；反馈卡片吸顶显示进度，题目行增加批次序号 |
| v1.8.0 | 跨行块级 LaTeX 在题目页/A4/屏幕版完整渲染；设置页重启交给 systemd，避免服务停机 |
| v1.7.0 | 仪表盘行动推荐、目录页（错题文件夹树 + `GET /api/tree`）、深色模式对比度重配 |
| v1.6.0 | 单题删除（Ledger 归档）与可配置 Ledger 时间线时区；汇总 v1.5.0 后的导出、AI 录入、仪表盘和报告托管改进 |
| v1.5.0 | 暖石墨深色主题 + 录入/即时/优化页重做、模块拆分与全宽布局 |
| v1.1.1 | 历史修正体验修复（撤销/恢复真正生效）；历史页只读浏览需显式开启修正模式；时间线改为题目优先 |
| v1.1.0 | 数据格式大变动：改用链式存储（Ledger），数据可回溯可复原，一切操作记录在链上 |
| v1.0.x | 初版 |

---

## 许可

个人项目，未声明开源协议。
