# 错题本 / OMRS

> **O**bsidian **M**istake **R**econstruction **S**ystem — 一个面向个人学习的错题管理系统，基于 Markdown 与本地 HTTP 服务构建。

---

## 这是什么

OMRS 是一个**本地优先、核心运行时零必装第三方依赖**的个人错题本：

- 题目以 **Markdown 文件** 形式存放在 `错题/` 目录，可被 Obsidian 等笔记软件直接打开、编辑、双链。
- 一个 **Python 后端** 读取题库、提供 HTTP API、维护不可变的提交链（Ledger），所有算法（记忆衰减、SM-2、调度、Leech 检测）都是纯标准库实现。
- 一个 **HTML/CSS/JS 单页前端**（`omrs_dashboard.html` + `assets/`）负责录入、即时练习、复习 Session、反馈、数据复盘与导出。
- 没有构建步骤，题库、算法、Ledger、复习和导出均可离线使用；界面字体随 `assets/vendor/fonts/` 本地提供，AI 图片识别以及报告中用户选择的 HTTPS 外部资源属于可选联网能力。

当前版本：**v1.28.1**。

展示板锁定后仍可添加新题并补印：增删引用、排序和调整未打印题留白不会清空旧纸面记录；仅新增会沿用纸面记录中的实际比例与留白，改动已打印区域的版式才需要明确确认重印。

展示板导出会先完成设置保存；打印窗口与下载文件各自保留当次纸面快照，之后切板或改设置不改变其记录归属。答案与标记开关同步更新预览；快捷加入后的撤销只移除本次新增题目。

---

## 已知技术债

完整清单见 [`AI/optimization.md`](AI/optimization.md)。目前最值得优先处理的是：

| 优先级 | 技术债 | 影响 | 建议方向 |
|---|---|---|---|
| 高 | HTTP 服务单线程 | AI 识别等慢请求会阻塞整个界面 | 改用线程化 HTTP Server，并为 CSV、Markdown、Ledger 写入增加统一锁 |
| 中高 | Ledger 每次全量重放 | 历史提交增长后，反馈/录入后的重建耗时线性增加 | 引入按 seq 的持久化快照和增量重放 |
| 中 | 前端大量 `innerHTML` + 行内 `onclick`（各约 200 处） | DOM 高频重建、事件逻辑与模板耦合，也阻碍 ES Module 化 | 反馈工作台已在 v1.10.0 改为局部更新 + 事件委托；其余列表页仍待处理 |
| 低 | `styles.css` 同名规则叠加 | 实测顶层选择器定义 ≥3 次的只有 4 个（`:root`、`.card-title`、`.paste-zone`；`.instant-qbtn` 已随即时练习迁移删除），比早先估计的轻 | 顺手收拢即可，不单列任务 |
| 中 | 后端 `server.py` 路由分支过长 | 请求解析和错误处理重复，维护成本高 | 改为路由表 + 统一请求体解析 |
| 中 | 测试框架与覆盖不完整 | 当前 `unittest` 与 pytest 风格测试混用，核心算法边界覆盖仍不足 | 统一测试入口，补齐算法、Ledger 集成、异常输入和浏览器回归 |

这些项目是已知的维护与扩展成本，不影响当前核心功能运行；线程化服务与增量投影涉及架构边界，实施前应单独设计和验证。远端 PIN、来源校验及报告隔离的当前行为见 [`AI/security.md`](AI/security.md)。

---

## 特性一览

- **AI 助手**（在「设置 → AI 助手」里开启，需要支持工具调用的 OpenAI 兼容模型）：用对话找题、看哪块最弱、排复习、打标记；改正文、记反馈会先请你点「允许」，这些写入可以按运行撤销。录新题暂存为 AI 草稿，不直接写入题库；草稿审核界面与聊天贴图入口尚未上线。

| 模块 | 能力 |
|---|---|
| **收件箱录入** | v1.12.0 起「录入题目」页改为 **上传 → 处理 → 录入** 三步：手机在同一 Wi-Fi 打开 `http://<局域网IP>:8471/m` 直接投整张截图（sha256 去重）；手机页随主站浅色 / 深色设置切换。电脑端上传后可在收件箱网格按状态筛选、全选当前筛选图片并批量处理；已录入图片可打开关联题目。处理区可框题目 / 答案（可多题卡），每块可「转文本」（AI 转录 + 判断能否转）或「保留图片」；AI 框选（长图自动切片）、沿用上一张框位、整图即题目、批量勾选处理；就绪的题卡填科目分类后一键写入题库。所有框位、AI 原框、采纳方式、转换决策留作训练数据，「AI 训练」页可看统计并导出 JSONL / YOLO 数据集。v1.13.0：框选可选提供方（多模态模型 / 零联网的版式模板 / 训好后的本地检测服务）、每 N 张盲标作干净评估集、置信度达标自动转文本并就绪、上传即自动处理（需 Pillow）、超期丢弃图自动清理，都在「AI 训练」页配置。原单题表单保留为「快速录入」。收件箱数据集版式标签的新上传默认是「作业帮截图」（`zuoyebang`），可在处理页改为拍照/扫描、已裁好的题图或其他。后台提取文字完成时只刷新对应图片的结果，不中断当前框选。详见 `AI/inbox.md` |
| **题目录入（快速）** | 两图片区（题面 / 答案）、Markdown 原文编辑、Obsidian 双链分类、`![[image]]` 嵌入图、AI 识别（外部大模型，按需调用）；题目库可单题停用/恢复（不参与复习与统计）或删除并保留可审计归档记录 |
| **记忆算法** | 时间衰减 `time_decay`、熟练度状态机 `compute_mastery_update`、SM-2 间隔、易错因子 EF、统一优先级 `compute_priority`；未击杀且最近连错至少 3 次标记为 Leech（顽固题），答对后解除。已击杀题不再永久消失：休眠按记忆衰减反解的**分级周期**（第 1/2/3/4 次击杀后约 56 / 101 / 182 / 327 天）复燃重进调度，复燃后答错即降级待攻克 |
| **即时练习** | 浏览器内直接做、在线翻答案、即时反馈（分数滑杆 + 对错） |
| **复习 Session** | 复习调度工作台自动加载推荐，支持建议 10 题、折叠筛选、chips、保留已选、列表/画廊题面预览和按科目均衡；已有计划可查看详情、进度、预览、导出并跳转反馈；详情支持删除调度（关联反馈一并撤销，可在历史记录恢复）。正式计划支持单题，旧单题 TMP 调用仍兼容 |
| **答题卡回填** | v1.11.0 起可把答题卡扫描（OMR）的正式结果 JSON 读进反馈页：选中该 Session → 在 OMR 识别详情页复制 `/api/v1/recognitions/<id>/result` JSON → 点「📋 读剪贴板填写」或直接 ⌘/Ctrl+V，按题号自动填对错与 0–10 主观分。只接受顶层 `recognition_id/template_id/mode/status/questions/unresolved` 协议，明确拒绝旧 raw/items、裸数组与包装层；`unresolved` 涉及的题不自动猜测，转人工处理。Anki 模式仍按 `questions[].answer` 映射为 OMRS 评分。 |
| **行动推荐** | 仪表盘顶部按当前题库状态排出「现在该做什么」：逾期、今日到期、未录反馈的 Session、顽固题、久未复习、最薄弱科目/分类等，每条带数字依据和一键跳转 |
| **目录** | 树状展示 `错题/` 的真实文件夹结构，每层标注题量、待复习、顽固题与平均熟练度；支持搜索、展开折叠、显示非题目文件，点题目文件直接开详情 |
| **用户标记** | 自定义名称与颜色的 `<=>` 芯片；录入、题库、反馈、推荐、即时练习和展示板均可添加/筛选，支持批量编辑、改名、删除、合并；默认不改变调度，设置 `priority_bonus` 后才参与优先级 |
| **展示板** | 板列表、常驻纸面和题目列表并列，可在行内调留白、打开滑入式题目详情，通过浮层调整版式和查看纸面记录；持久化题目引用集合支持拖拽/菜单排序与按关联标记同步，导出左题右空 A4「错题集」；题栏与右侧留白默认各占可分配宽度的 50%，页面左右各留 10mm，不额外预留装订区或绘制装订导引线；打印后确认记录实际纸面几何，新加的题可**只补印新增**并沿用原纸比例接在空白处，页码始终是绝对页码 |
| **题库交互重设计** | 筛选抽屉、激活条件 chips、列设置、舒适/紧凑密度、命名视图预设和批量加入展示板/打标记/停用/导出 |
| **练习记录** | 画廊卡脚注的战绩带（一根竖条一次练习，绿对红错、高度是主观分，可关）与题目详情底部的记录模块（次数 / 正确率 / 平均分 / 平均间隔 + 主观分走势 + 明细）。v1.16.1 起数据来自 Ledger 投影（`GET /api/question` 的 `records[]`），题目 Markdown 里的 `# 历史` 只作老格式兼容 |
| **数据复盘** | 仪表盘（统计/雷达/热力/散点/趋势）、Ledger 时间线、历史修正（显式开启修正模式）、撤销/恢复/还原 |
| **错题导出** | **自包含 HTML**（图片 base64 内联），分 **A4 打印版**、**展示板左题右空版** 与 **屏幕版**（卡片 + 判分 + 进度持久化）。题面区只留题干与「关联」；**错因**与答案同属「做完才能看」的信息，一律排到末尾**反馈区**（屏幕版折在「显示答案」后面），勾选导出答案时每题答案下面紧跟同题错因、不分开，不勾选则反馈区只列错因 |
| **报告托管** | 上传/浏览/删除复盘报告，浏览器内直接查看 |
| **源码协助** | 设置页按源码目录和文件类型下载当前工作区的脱敏 ZIP，包含未提交源码且不依赖 Git；排除个人题库、附件、运行数据、日志、缓存和生成导出文件 |
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

可参考 [`deploy/omrs.service`](deploy/omrs.service)。服务默认监听 TCP 8471。本机直连免 PIN；设置页「访问与安全」可显式填写私有局域网网段（如 `192.168.0.0/24`），使该网段的设备直连时免 PIN。页面顶部概览会说明当前谁能访问，以及配置是否要重启后才生效；只改网段立即生效，切换「允许局域网访问」才会重启。此项默认关闭，经 Nginx 的 HTTPS 访问仍需 PIN。启用 `allow_external` 前须配置免 PIN 网段或 4–12 位数字 PIN；未配置 PIN 的其他远端请求会被拒绝。远端登录使用 Cookie，会在 30 分钟无操作或登录 12 小时后过期，设置页可调整空闲时间。手机上传页 `/m` 遵循相同访问规则。核心运行路径只依赖 Python 标准库。

若在同机 Nginx 后使用 HTTPS，OMRS 可保持仅绑定 `127.0.0.1`。Nginx 需覆写 Host、客户端 IP 和协议头；OMRS 只信任来自 `OMRS_TRUSTED_PROXIES` 的代理头（默认 `127.0.0.1,::1`，异机代理时设为其实际 IP）：

```nginx
server {
    listen 443 ssl;
    server_name omrs.example.com;
    ssl_certificate /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;
    location / {
        proxy_pass http://127.0.0.1:8471;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

不强制 HTTPS；远端经 HTTP 登录后每个会话提示一次传输风险。HTTP 上的 PIN 和 Cookie 可能被同网段窃听，建议使用上述 HTTPS 代理。源码下载、备份及完整 Vault 路径仅供本机、显式豁免的直连局域网设备或已登录远端使用。免 PIN 网段内的设备可使用全部功能，须只填写可信设备所在网段。AI 密钥不会从配置接口回显；设置页留空保留旧密钥，点击“清除”才删除。

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
│   ├── app/styles/tokens.css ← 设计 token（颜色 / 字号 / 间距等），新前端代码都放 assets/app/
│   ├── app/features/questions/ ← 题目库（表格 / 画廊、筛选抽屉、批量、视图预设）
│   ├── app/features/instant/ ← 即时练习
│   ├── app/features/create/ ← 录入题目：上传、收件箱网格、框选、题卡、AI 训练与快速录入
│   ├── app/features/settings/ ← 设置页
│   ├── styles.css
│   ├── core.js / app.js / questions.js / schedule.js
│   ├── app/features/reports/ ← 报告托管、上传与隔离预览
│   ├── inbox_mobile.html   ← 手机上传页（录入页五个工作区在 app/features/create/）
│   ├── labels.js / board.js ← 标记与展示板交互（题库页 v1.24.0 起在 app/features/questions/）
│   ├── vendor/fonts/       ← Noto Sans SC / JetBrains Mono（本地 WOFF2 分片）
│   ├── vendor/katex/       ← KaTeX（本地，公式离线渲染）
│   └── app/ui/             ← 统一提示、对话框与基础控件
├── 错题/                   ← 题库（Markdown + Obsidian 双链）
│   ├── .omrs/              ← 结构化数据目录（Ledger / 投影 / 备份）
│   │   ├── ledger.db       ← v1.1.0+ 唯一可信事实源
│   │   ├── mastery_data.csv
│   │   ├── history_log.csv
│   │   ├── sessions.csv
│   │   ├── labels.json       ← 用户标记定义
│   │   └── boards.json       ← 展示板引用与打印设置
│   └── report/             ← 托管的 AI HTML 报告与 index.json
├── tests/                  ← 后端 unittest + 前端 node:test；check_docs.py 文档体检，check_ui.py / check_contrast.py 前端纪律与对比度，visual/ 截图对比，fixtures/ 演示数据
│                              （tool/ 与 Task/ 为本地工作目录，已被 .gitignore，不在仓库里）
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

默认端口 **8471**。端点的请求体与响应字段见 [`AI/api.md`](AI/api.md)；全部路由及其说明文档见自动生成的 [`AI/routes.md`](AI/routes.md)。

---

## 前端

入口 `omrs_dashboard.html` 是纯结构文件，样式与脚本拆到 `assets/`。

- **无构建步骤**：所有 JS 是普通 `<script>`（非 ES module），共享全局作用域。
- **图表纯 CSS + 内联 SVG**，无 ECharts/Chart.js 等图表库。
- **KaTeX** 放在 `assets/vendor/katex/`，公式离线渲染；不可用时降级显示源码。
- **响应式**：≤860px 侧栏自动转为顶部横滚条。
- **侧边栏应用式 shell** + 雪碧图图标，无外部图标库依赖。
- **行动推荐 / 目录树纯前端派生**：行动推荐只读已加载的 `/api/stats` + `/api/sessions`，不新增接口；目录页结构取自 `/api/tree`，熟练度等状态由本地题库按路径前缀叠加。

加载顺序（`core.js` → 模块 → `app.js`）详见 [`AI/frontend/shell.md`](AI/frontend/shell.md)；各页面说明见 [`AI/frontend.md`](AI/frontend.md) 索引。

---

## 错题导出

导出为**单文件 HTML**，图片 base64 内联、KaTeX 字体 data URI 内联——拷到任何带浏览器的设备都能打开。

- **A4 打印版**（默认）：导出时选择双栏或整份单栏；内容块会尽量填满栏位，放不下的块完整移到下一栏而不截断，临近栏底的公式文字按公式边界续栏，长图按白缝切片（缝带算法）；初次排版等待字体稳定，浏览器预览和打印复用同一版面，所见即所打印。
- **展示板左题右空版**：以 `boards.json` 的持久化题目引用为输入，左侧按题目顺序排版（KaTeX / 表格 / 长图切白缝 / 跨页续排）、右侧完全留白；题栏与右侧留白默认对半，标题固定为「错题集」，左右各留 10mm 普通页边距，支持题间留白、附答案页、绝对页码；「仅打印新增」把新题排在纸面记录的续排位置，已打印区域留白，把原纸放回打印机即可补印。
- **屏幕版**：卡片式复习 App，可判对错、打分、记录进度（持久化到 localStorage）。

旧 docx 导出方案已被完全替换——HTML 既解决了「长图被截断 / 双栏栏底留白」问题，也让基础导出不再依赖 Pillow。详见 [`AI/export.md`](AI/export.md)。

---

## AI 协作

[`AI/`](AI/) 是给 AI 维护者用的项目知识库。本仓库有三个维护者：Hermes Agent 与 Codex 在本机完整环境工作，Claude Code Web 只拿到脱敏源码 zip、在受限沙箱里工作。两种模式的规则写在根 [`AGENTS.md`](AGENTS.md)，环境与工具清单写在 [`AI/environment.md`](AI/environment.md)。

入口是 [`AI/README.md`](AI/README.md) 的「按任务找文档」。模块文档开头都有速查头，前端按页面拆成 `AI/frontend/` 分册，路由总表 `AI/routes.md` 由脚本生成。每个产生持久化改动的任务都要更新受影响的文档并新建任务日志；交付前运行 `python3 tests/check_docs.py --diff <基线>`。

---

## 依赖

**核心运行时零必装第三方依赖。**

- Python：仅用标准库（`http.server`、`sqlite3`、`csv`、`json`、`struct`、`datetime`）。
- 可选图片优化：检测到 Pillow 时可深扫 PNG，检测到 `jpegtran` 时可无损优化 JPEG；缺失时基础功能不受影响。
- 前端：无 npm、无 webpack；界面字体与 KaTeX 均作为本地静态资源放在 `assets/vendor/fonts/` 和 `assets/vendor/katex/`，页面不依赖 Google Fonts 外链。
- AI 识别：只有调用 `/api/ai-recognize` 时才访问用户配置的 OpenAI 兼容服务。
- AI 报告：核心 HTML 可自包含；报告提示词允许按需引用 HTTPS 字体/图表/图标资源，并要求失败时正文仍可读。
- 数据：纯文件（Markdown + SQLite/CSV），无外部数据库。

---

## 版本

当前版本 **v1.28.1**。各版本改了什么见 [`AI/changelog.md`](AI/changelog.md)（倒序）。

---

## 许可

个人项目，未声明开源协议。
