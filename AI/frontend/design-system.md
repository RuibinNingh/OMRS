# 前端：设计系统（token、尺度与纪律门禁）

> **速查**
> - 职责：设计 token（颜色 / 字号 / 间距 / 控件 / 圆角 / 阴影 / 动效 / 层级）、样式分层、对比度规则与全仓前端纪律
> - 入口：`assets/app/styles/tokens.css`（主题与尺度 token）、`assets/app/styles/index.css`（`@layer` 样式总入口）
> - 不变量：颜色字面量只写在 `tokens.css`；页面样式使用语义与尺度 token；全仓 UI 违规计数为 0
> - 必跑测试：`tests/check_ui.py`、`tests/check_contrast.py`、`tests/test_ui_gates.py`
> - 相关：`AI/frontend/shell.md`、`AI/environment.md`（截图对比与 fixture 配方）

## 1. 目录与分层

前端全部在 `assets/app/`（原生 ES Module，无构建）：`styles/`（token、分层总入口、base、组件汇总、外壳）、`core/`、`ui/`（23 个组件）、`domain/`、`features/`，入口 `main.js`、`shell.js`；`assets/` 根目录只剩手机上传页 `inbox_mobile.html`。按钮与输入框只有 `ui-btn` / `ui-input` / `ui-select` / `ui-textarea` 一套。架构见 `AI/frontend/architecture.md`、组件见 `AI/frontend/components.md`。

- `assets/app/` 下的一切适用 §5 的零容忍规则。
- `assets/` 根目录不再新增前端文件，新代码一律进 `assets/app/`（`check_ui.py` 会拦）。
- 样式分层：`styles/index.css` 声明 `vendor < base < ui < shell < domain < features < utilities`，KaTeX 进 `vendor`。页面样式按职责放进对应层；未分层规则会压过全部分层规则，因此不添加未分层的页面样式。
- `domain` 层：共享题目视图 `domain/question/qview.css`（P5 第 4 轮起是 qview 的全部外观，含题目弹窗与 Markdown 编辑器）与标记 `domain/labels/labels.css`（色板、颜色圆点按 `data-lbl-c` 取色）、选板浮层 `domain/board/picker.css`（popover 进顶层，锚定位置由脚本写 `--bpicker-x` / `--bpicker-y`，是它唯一的行内样式）；标记颜色的运行时规则（`domain/labels/sheet.js`）也插在 `@layer domain` 块里。
- 内嵌题面用 `--surface-sunken`，答案块用 `--success-subtle` / `--success-line`，战绩带用 `--streak-ok` / `--streak-bad`；标记预设色用 `--lbl-preset-1…10`，实色芯片前景用 `--lbl-fg-dark` / `--lbl-fg-light`。`check_contrast.py` 同时检查 `fg-1` / `fg-2` 在 `surface-sunken` 上的对比度。
- 层次（core → ui → domain → features）与依赖方向由 `check_ui.py` 的 R7 约束。共享题目、标记与选板样式在 `domain` 层；页面样式由 `styles/index.css` 以 `layer(features)` 引入，实际导入清单以该文件为准。
- `features` 层包含题库、即时练习、反馈、仪表盘、数据复盘、复习调度、展示板、历史、目录、报告、设置、录入与助手页面样式。展示板拆成外框、目录树、题目面板、浮层和对话框；录入页拆成工作区、草稿、处理、题卡与训练样式。各页使用语义色与控件尺度，数据图表用 `data-tone` 映射状态 token。
- 同一行的控件使用同一档高度（§3 的 `--ctl-*`）。仪表盘的「今天」数字用 `--text-display`；热力格四档颜色由 `color-mix` 基于 `--success` 与 `--surface-1` 派生。

## 2. 语义 token

浅色写在 `:root`，深色写在 `[data-theme="dark"]`，两者名字一致。`data-theme` 与 `data-density` 都挂在 `<html>` 上。

| 类别 | token | 说明 |
|---|---|---|
| 表面 | `--surface-0` ~ `--surface-3` | 页面底 → 卡片 → 卡中卡 / 输入底 → 轨道 / 分隔块 |
| 文字 | `--fg-1` / `--fg-2` / `--fg-3` | 主 / 次 / 辅助 |
| 描边 | `--border-1` / `--border-2` | 常规 / 强调 |
| 强调 | `--accent`、`--accent-hover`、`--accent-muted`、`--accent-soft`、`--on-accent`、`--accent-rgb` | 主按钮、激活态 |
| 状态 | `--danger` / `--success` / `--warning` / `--info`，各带 `-rgb`、`-soft`、`-fg` | 基色可直接当文字用；`-soft` 为芯片底；`-fg` 为芯片字 |
| 其它 | `--focus-ring`、`--family-*`、`--chart-surface`、`--chart-line`、`--elev-0` ~ `--elev-3`、`--scrim` | 焦点环、时间线事件族、图表、阴影层级、遮罩 |

字号 token 叫 `--text-*`，文字颜色叫 `--fg-*`，两者不要混。

页面专用的派生值也放 `tokens.css`，按页面分段：助手页的 `--ast-*`（用户消息底色、确认卡与错误描边、思考引线、等首 token 的时间线色，以及代码与引用芯片的相对字号）由主题的 `*-rgb` 派生，深浅主题自动跟随。

展示板工作区使用 `--brd-desk` 和 `--brd-desk-line` 绘制纸面周围的桌面；浅色、深色各有一套值，纸张本身的阴影由导出模板 `omrs/export_templates/board.css` 绘制。

## 3. 尺度 token

| 类别 | 取值 |
|---|---|
| 字号 | `--text-2xs` 11 / `xs` 12 / `sm` 13 / `md` 14 / `lg` 16 / `xl` 20 / `2xl` 28 / `display` 40（px） |
| 行高 / 字重 | `--leading-tight` 1.15、`--leading-ui` 1.45、`--leading-read` 1.75；`--weight-regular/medium/semibold/bold` |
| 字体 | `--font-sans`、`--font-mono` |
| 间距 | `--sp-0_5` 2、`--sp-1` 4、`--sp-1_5` 6、`--sp-2` 8、`--sp-3` 12、`--sp-4` 16、`--sp-5` 20、`--sp-6` 24、`--sp-8` 32、`--sp-10` 40、`--sp-12` 48 |
| 控件高度 | `--ctl-sm` 28、`--ctl-md` 32、`--ctl-lg` 40（同一行只用同一档；≤760px 三档都为 40） |
| 圆角 | `--r-xs` 4、`--r-sm` 6、`--r-md` 10、`--r-lg` 14、`--r-pill` |
| 动效 | `--dur-1` 120ms、`--dur-2` 180ms、`--dur-3` 260ms；`--ease-out`、`--ease-in-out`；减少动效时时长归零 |
| 层级 | `--z-sticky` 10 < `--z-sidebar` 20 < `--z-dropdown` 100 < `--z-drawer` 200 < `--z-modal` 300 < `--z-toast` 400 < `--z-tooltip` 500 |
| 断点 | 只用 760 / 1160 / 1500（媒体查询不能用变量，由 R5 约束） |

字号 token 用 px 定义。紧凑密度 `html[data-density="compact"]` 把 `--text-sm/md/lg` 各降 1px，`--ctl-md/lg` 降到 30 / 36。窄屏（≤760px）为保证可点目标不小于 40px，三档控件高度统一为 40，不受密度影响。

## 4. token 维护边界

`tokens.css` 定义浅色与深色语义 token，以及字号、间距、控件高度、圆角、动效和层级等尺度 token；紧凑密度与窄屏覆盖也在该文件。页面专用的派生 token 按用途放在同一文件，其他样式只引用 token。

主题由 `<html data-theme>` 选择，密度由 `<html data-density>` 选择。改调色板时在 `tokens.css` 维护两套主题值，并运行 §6 的对比度门禁；`tests/check_ui.py --report` 可只读查看页面五项计数。

## 5. 纪律门禁（`tests/check_ui.py`）

`assets/app/**` 零容忍，规则编号与脚本文件头一致：

- **R1** 颜色字面量只在 `tokens.css`。
- **R2** 字号、行高、字重、字体族只用 token。
- **R3** 间距不写长度字面量。
- **R4** 圆角、阴影、z-index、动效时长与缓动只用 token。
- **R5** 断点白名单。
- **R6** 模板里没有 `style=` 和 `on*=`；`innerHTML` 类写法只在 `core/dom.js`。
- **R7** 依赖方向。
- **R8** JS ≤ 400 行、CSS ≤ 300 行。
- **R9** 每个 `assets/app/features/<x>/` 须登记在 `AGENTS.md` 映射表。

`assets/` 根目录只允许 `inbox_mobile.html`；它与 `omrs_dashboard.html` 同样按五项计数（行内事件、`innerHTML` 类赋值、行内样式、颜色字面量、硬编码字号），全部必须为 0，没有存量基线。

任一违规即失败，没有存量基线；`--update-baseline` 会报错退出。新增组件须覆盖默认、悬停、按下、焦点、禁用、加载、空、错误、溢出、浅 / 深和舒适 / 紧凑状态，并在组件陈列页与 `tests/app/browser_tests.js` 增加对应验证，状态矩阵见 `AI/frontend/components.md`。

## 6. 对比度（`tests/check_contrast.py`）

脚本解析 `tokens.css` 的浅色与深色两套值，按 WCAG 2.x 计算 29 组 × 2 主题。

- **4.5:1**：文字类组合，包括 `--fg-1/2/3` 在 `surface-0/1` 上、`--fg-1/2` 在 `surface-2` 上、四个状态色在 `surface-0/1` 上、各 `-fg` 在自己的 `-soft` 上、`--on-accent` 在 `--accent` 上。
- **3:1**：`--fg-3` 在 `surface-2` 上、焦点环。
- 半透明底色先合成在 `surface-1` 上再计算。

修改任何颜色 token 后必须通过。

## 7. 草稿审核工作区

草稿样式在 `features/create/drafts.css`，由 styles/index.css 以 features 层导入；表单与操作复用 ui-input、ui-select、ui-textarea、ui-btn，侧栏计数复用 ui-badge。草稿跨页状态不向 DOM 写行内样式。

草稿框选复用 process-canvas 的 SVG 框、遮罩和控制点；适配器只替换图片地址、元素标识与数据回调。草稿画布布局位于 drafts.css，沿用现有 token 与响应式断点，不创建独立配色或行内样式。
