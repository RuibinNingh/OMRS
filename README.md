# 错题本 / OMRS

> **O**bsidian **M**istake **R**econstruction **S**ystem — 一个面向个人学习的错题管理系统，基于 Markdown 与本地 HTTP 服务构建。

---

## 这是什么

OMRS 是一个**纯本地**、**零第三方依赖**的个人错题本：

- 题目以 **Markdown 文件** 形式存放在 `错题/` 目录，可被 Obsidian 等笔记软件直接打开、编辑、双链。
- 一个 **Python 后端** 读取题库、提供 HTTP API、维护不可变的提交链（Ledger），所有算法（记忆衰减、SM-2、调度、Leech 检测）都是纯标准库实现。
- 一个 **HTML/CSS/JS 单页前端**（`omrs_dashboard.html` + `assets/`）负责录入、即时练习、复习 Session、反馈、数据复盘与导出。
- 没有任何云依赖、没有任何构建步骤；离线可用，拷走就走。

当前版本：**v1.5.0**。

---

## 特性一览

| 模块 | 能力 |
|---|---|
| **题目录入** | 两图片区（题面 / 答案）、Markdown 原文编辑、Obsidian 双链分类、`![[image]]` 嵌入图、AI 识别（外部大模型，按需调用） |
| **记忆算法** | 时间衰减 `time_decay`、熟练度状态机 `compute_mastery_update`、SM-2 间隔、易错因子 EF、统一优先级 `compute_priority`、Leech（顽固题）检测 |
| **即时练习** | 浏览器内直接做、在线翻答案、即时反馈（分数滑杆 + 对错） |
| **复习 Session** | 调度器挑题 → 列表预览 → 启动 Session → 反馈录入 |
| **数据复盘** | 仪表盘（统计/雷达/热力/散点/趋势）、Ledger 时间线、历史修正（显式开启修正模式）、撤销/恢复/还原 |
| **错题导出** | **自包含 HTML**（图片 base64 内联），分 **A4 打印版**（双栏 + 长图缝带切片）与 **屏幕版**（卡片 + 判分 + 进度持久化） |
| **报告托管** | 上传/浏览/删除复盘报告，浏览器内直接查看 |
| **外观** | 浅色（默认，编辑式暖色）/ 深色（**暖石墨 Warm Graphite**）切换；图表全 token 化，深色自动跟随 |
| **数据可信** | v1.1.0 起改用不可变 **Ledger 提交链** 作为唯一事实源；CSV 仅作兼容投影；任何状态都可重放还原 |

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

### 打包给 AI 协助

```bat
pack_for_ai.bat
```

会在 `_ai_packages/` 下生成一个 `.zip`，**不含 `.git` 与 `错题/` 数据**，可直接交给 AI 助手协作。

---

## 项目结构

```
错题本/
├── omrs_engine.py          ← 后端入口（兼容垫片）
├── omrs_dashboard.html     ← 前端 HTML（仅结构）
├── omrs/                   ← 后端 Python 包（标准库，无第三方依赖）
│   ├── cli.py              ← 命令行入口 + HTTP 服务
│   ├── server.py           ← HTTP 路由
│   ├── ledger.py           ← 不可变提交链（SQLite）
│   ├── projections.py      ← 重放 Ledger 导出 CSV / 内存投影
│   ├── scheduling.py       ← 记忆算法（衰减/状态机/SM-2/优先级/Leech）
│   ├── ai_assist.py        ← AI 识别（外部大模型调用）
│   ├── exporting.py        ← 错题 HTML 导出
│   ├── feedback.py / sessions.py / creation.py
│   ├── analytics.py / stats.py / reports.py
│   ├── migration.py / workspace_sync.py / indexing.py
│   └── export_templates/   ← A4 / 屏幕版 HTML 模板（CSS + JS）
├── assets/                 ← 前端静态资源（无构建）
│   ├── styles.css
│   ├── core.js / app.js / dashboard.js / questions.js
│   ├── schedule.js / export.js / feedback.js / history.js
│   ├── recommend.js / instant.js / data.js / reports.js
│   └── vendor/katex/       ← KaTeX（本地，公式离线渲染）
├── 错题/                   ← 题库（Markdown + Obsidian 双链）
│   └── .omrs/              ← 数据目录（Ledger / 投影 / 报告 / 备份）
│       ├── ledger.db       ← v1.1.0+ 唯一可信事实源
│       ├── mastery_data.csv
│       ├── history_log.csv
│       ├── sessions.csv
│       └── report/
├── tests/                  ← 历史投影等回归测试
├── tool/migrate_ledger.py  ← 数据迁移工具
├── Task/Goal.md            ← 项目目标
├── Skills/                 ← 第三方技能目录
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
- 任何时候都能从 Ledger 重放出完整运行状态——这也是「撤销 / 恢复 / 还原」的原理。

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
| POST | `/api/create` | 录入新题 |
| POST | `/api/feedback` | 提交一次反馈 |
| POST | `/api/recommend` | 推荐下一题 |
| POST | `/api/schedule` | 创建复习 Session |
| POST | `/api/ai-recognize` | AI 识别图片 |
| GET | `/api/ledger/verify` | 校验提交链完整性 |

---

## 前端

入口 `omrs_dashboard.html` 是纯结构文件，样式与脚本拆到 `assets/`。

- **无构建步骤**：所有 JS 是普通 `<script>`（非 ES module），共享全局作用域。
- **图表纯 CSS + 内联 SVG**，无 ECharts/Chart.js 等图表库。
- **KaTeX** 放在 `assets/vendor/katex/`，公式离线渲染；不可用时降级显示源码。
- **响应式**：≤860px 侧栏自动转为顶部横滚条。
- **侧边栏应用式 shell** + 雪碧图图标，无外部图标库依赖。

加载顺序（`core.js` → 模块 → `app.js`）详见 [`AI/frontend.md`](AI/frontend.md)。

---

## 错题导出

导出为**单文件 HTML**，图片 base64 内联、KaTeX 字体 data URI 内联——拷到任何带浏览器的设备都能打开。

- **A4 打印版**（默认）：双栏排版，长图按白缝切片（缝带算法），所见即所打印。
- **屏幕版**：卡片式复习 App，可判对错、打分、记录进度（持久化到 localStorage）。

旧 docx 导出方案已被完全替换——HTML 既解决了「长图被截断 / 双栏栏底留白」问题，也移除了对 Pillow 的依赖（项目恢复零第三方依赖）。详见 [`AI/export.md`](AI/export.md)。

---

## AI 协作

[`AI/`](AI/) 文件夹是给 AI 助手（Claude 等）用的**项目知识库**，每次对话先读它就能快速建立上下文。

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
└── logs/           ← 逐次会话的详细变更记录
```

AI 协作完成后，会在 `AI/logs/` 留下当日变更记录，并在 `logs/log.md` 补一行索引。

---

## 路线 / 已知技术债

节选自 [`AI/optimization.md`](AI/optimization.md)：

- [ ] **服务器单线程** — `ai-recognize` 调用大模型时整界面卡死，需换 `ThreadingHTTPServer` + 文件锁。
- [ ] **投影全量重放** — `rebuild_projection` 随历史线性变慢，需定期落投影快照。
- [ ] **后端路由超长 if/elif** — `server.py` 的 `do_GET`/`do_POST` 是手写分支链，可收成派发表。
- [ ] **CSS 重复定义** — `styles.css` 多次「现代化」后留下了真实叠加债，需按组件集中收拢。

---

## 依赖

**零第三方依赖。**

- Python：仅用标准库（`http.server`、`sqlite3`、`csv`、`json`、`struct`、`datetime`）。
- 前端：无 npm、无 webpack；页面运行时外链 Google Fonts，KaTeX 作为本地静态资源放在 `assets/vendor/katex/`。
- 数据：纯文件（Markdown + SQLite/CSV），无外部数据库。

---

## 版本

| 版本 | 说明 |
|---|---|
| v1.5.0 | 暖石墨深色主题 + 录入/即时/优化页重做、模块拆分与全宽布局 |
| v1.1.1 | 历史修正体验修复（撤销/恢复真正生效）；历史页只读浏览需显式开启修正模式；时间线改为题目优先 |
| v1.1.0 | 数据格式大变动：改用链式存储（Ledger），数据可回溯可复原，一切操作记录在链上 |
| v1.0.x | 初版 |

---

## 许可

个人项目，未声明开源协议。