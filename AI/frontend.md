# 前端

> **速查**
> - 职责：前端文档索引：按页面拆分，任务只读相关的一两份
> - 入口：`omrs_dashboard.html` + `assets/app/main.js`（原生 ES Module，无构建步骤）
> - 不变量：模块文档只写当前行为；改哪个页面就更新对应分册
> - 必跑测试：`node --test tests/app/*.test.mjs`、`tests/app/run_browser.py`、`tests/check_ui.py`、`tests/check_contrast.py`
> - 相关：`AI/api.md`、`AI/board.md`、`AI/inbox.md`、`AI/omr-import.md`

前端是单页仪表盘：`omrs_dashboard.html` 只有外壳骨架，页面由 `assets/app/features/<页>/` 的页面契约挂载，hash 路由切换面板。以下分册各自独立，改动某个页面时只需读对应分册。

设计 token 集中在 `assets/app/styles/tokens.css`；样式总入口 `assets/app/styles/index.css` 用 `@layer` 把 KaTeX、base、组件、外壳、domain 与各页样式排好序。新前端代码一律放 `assets/app/`，纪律见 `frontend/design-system.md`，组件与过渡桥见 `frontend/components.md`。

无构建步骤：主仪表盘和手机收件箱从 `assets/vendor/fonts/fonts.css` 加载本地 Noto Sans SC 与 JetBrains Mono，字体 CSS 不含远程 URL；KaTeX 从 `assets/vendor/katex/` 本地加载，不可用时降级为公式源码片段；图表用纯 CSS 与内联 SVG。各版本改了什么见 `AI/changelog.md`。

| 分册 | 内容 |
|---|---|
| [`frontend/design-system.md`](frontend/design-system.md) | **设计系统**：设计 token、尺度、旧名别名、对比度规则，以及 `check_ui.py` 的新代码纪律与旧代码棘轮 |
| [`frontend/architecture.md`](frontend/architecture.md) | **架构**：`assets/app/` 的目录与依赖方向、core 底座、页面契约、hash 路由、启动顺序、过渡桥与静态资源缓存 |
| [`frontend/components.md`](frontend/components.md) | **ui 组件库、过渡桥与 gallery**：`assets/app/ui/` 的 23 个组件与图标、`html``` 渲染约定、全站唯一的 toast 与对话框、旧入口过渡桥、组件陈列页与浏览器单测 |
| [`frontend/shell.md`](frontend/shell.md) | **外壳、布局与主题**：页面外壳：`assets/` 文件划分与加载顺序、整屏工作台布局、主题 token 与深色对比度 |
| [`frontend/dashboard.md`](frontend/dashboard.md) | **仪表盘与目录页**：仪表盘图表、行动推荐规则、目录树页 |
| [`frontend/library.md`](frontend/library.md) | **题库、筛选与标记**：题目库页（`assets/app/features/questions/`：表格 / 画廊、筛选抽屉、批量、视图预设、窄屏卡片列表）、题目操作 `domain/question/ops.js`、`filterItems()` 筛选语义、标记组件接入 |
| [`frontend/qview.md`](frontend/qview.md) | **共享题目视图 qview**（`assets/app/domain/question/`）：Markdown / KaTeX 渲染与缓存、练习记录、qview、题目详情缓存、题目弹窗与 Markdown 编辑器 |
| [`frontend/board-ui.md`](frontend/board-ui.md) | **展示板页面**：板列表、常驻纸面、题目面板、详情与浮层、保存队列和每题留白（数据模型与打印见 `AI/board.md`） |
| [`frontend/review.md`](frontend/review.md) | **复习调度**：复习调度工作台、临时调度与常规 Session 的区别 |
| [`frontend/instant.md`](frontend/instant.md) | **即时练习**（`assets/app/features/instant/`，第一个新架构页面）：取题、判定、提交、渲染不变量、快捷键、旧入口 |
| [`frontend/feedback.md`](frontend/feedback.md) | **反馈录入工作台**：反馈录入工作台布局、渲染分层、快捷键与提交结果弹窗（答题卡导入见 `AI/omr-import.md`） |
| [`frontend/settings.md`](frontend/settings.md) | **设置页**：设置页六个分区：外观、访问与安全、AI 识别、AI 助手、数据与存储、服务与运行 |
| [`frontend/assistant.md`](frontend/assistant.md) | **AI 助手页**：对话列表、运行轨迹、确认与撤销、检查器（后端见 `AI/agent.md`） |
| [`frontend/annotate.md`](frontend/annotate.md) | **框选标注页**（`/annotate`，`assets/app/features/annotate/`）：独立于题库的训练数据采集页，批量上传、只标题目 / 答案框、快捷键、导出 |
| [`frontend/create.md`](frontend/create.md) | **录入题目与收件箱入口**：录入题目页表单、AI 识别入口、提交后表单状态，以及收件箱在前端的入口（流程细节见 `AI/inbox.md`） |
| [`frontend/records.md`](frontend/records.md) | **历史记录、数据复盘与报告**：Ledger 时间线、数据复盘页、AI 报告托管页 |

独立训练面板 `/train` 的入口、图表、实时测试与可选积累见 `AI/frontend/trainpanel.md`。
