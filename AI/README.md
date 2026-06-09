# AI 文件夹维护手册

本文件夹是 OMRS 项目的 AI 协作知识库，供 AI 助手（Claude 等）在每次对话时快速建立上下文，也是人工维护系统设计的唯一权威来源。

---

## 文件夹结构

```
AI/
├── README.md          ← 本文件：维护规则、命名规范、文件索引
├── algorithm.md       ← 记忆算法：时间衰减、调度优先级、熟练度状态机
├── api.md             ← HTTP API：所有端点定义与请求/响应格式
├── data.md            ← 数据结构：CSV 字段、UID 规则、Markdown 格式
├── frontend.md        ← 前端：仪表盘、视图、图表、筛选控件
└── logs/
    ├── log.md         ← 变更日志总目录（所有改动的简明统计）
    └── YYYY-MM-DD_<主题>.md  ← 单次会话的详细变更记录
```

---

## 维护规则

### 什么时候更新
- **修改了算法逻辑**：更新 `algorithm.md` 对应函数的说明。
- **新增或修改 API 端点**：更新 `api.md`。
- **修改 CSV 字段或 Markdown 格式**：更新 `data.md`。
- **修改前端行为**：更新 `frontend.md`。
- **任何实质性改动**：在 `logs/` 中新建当日变更记录，并在 `logs/log.md` 补一行索引。

### 什么时候不需要更新
- 修复了拼写、注释等不影响行为的变动。
- 临时调试代码（提交前已撤回）。

### AI 助手的使用方式
1. 对话开始时先读 `README.md` 了解结构。
2. 按需读取对应模块文件获取细节。
3. 对话结束后，若有代码改动，必须在 `logs/` 新建记录并更新 `logs/log.md`。

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

---

## 项目基本信息

| 项 | 值 |
|---|---|
| 项目名 | OMRS（Obsidian Mistake Reconstruction System）|
| 类型 | 个人错题本，Markdown + 本地 HTTP 服务 |
| 后端入口 | `omrs_engine.py` |
| 前端文件 | `omrs_dashboard.html`（结构）+ `assets/`（`styles.css` 与拆分的 JS）|
| 数据目录 | `错题/.omrs/` |
| 无第三方依赖 | Python 端、前端均不引入第三方库（导出改 HTML 后已移除 Pillow，恢复零依赖）|

---

## 文件索引

| 文件 | 说明 |
|---|---|
| `algorithm.md` | 时间衰减、compute_mastery_update 状态机、统一优先级 `compute_priority`（EF 反推的有效难度）、SM-2、双列表推荐、Leech 检测、可调参数 tuning |
| `api.md` | GET/POST 端点完整列表、请求体、返回字段（含 analytics/export-review/reports/image、**AI 识别 `ai-recognize`** 与扩展后的 `create`） |
| `data.md` | mastery/history/sessions CSV 字段、Markdown 题目格式、UID 规则、config.json（**含 `ai_*` 配置**）、日志、report/ 报告存储、File_Path 分隔符 |
| `frontend.md` | assets/ 多文件结构与加载约定；仪表盘、题目库、调度/推荐、数据复盘页、报告托管页、设置（**含录入页两图片区 + AI 提取/答案、AI 配置卡片**）|
| `export.md` | **错题导出 HTML 架构**：A4 打印版浏览器端分页/切片引擎（缝带算法、FORCE/PACK 两种切片机制、页码）、屏幕阅读版功能、模板位置 `omrs/export_templates/`、为何 HTML 胜过 docx（无引擎依赖/无保真度差，移除 Pillow）|
| `logs/log.md` | 变更日志总索引 |
