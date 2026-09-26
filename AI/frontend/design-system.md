# 前端：设计系统（token、尺度与纪律门禁）

> **速查**
> - 职责：设计 token（颜色 / 字号 / 间距 / 控件 / 圆角 / 阴影 / 动效 / 层级）、旧名别名、对比度规则、新代码纪律与旧代码棘轮
> - 入口：`assets/app/styles/tokens.css`（`omrs_dashboard.html` 最先加载）、`assets/app/styles/index.css`（`@layer` 样式总入口）
> - 不变量：颜色字面量只写在 `tokens.css`；新代码只用语义 token；旧名别名只给旧样式用；旧代码违规计数只减不增
> - 必跑测试：`tests/check_ui.py`、`tests/check_contrast.py`、`tests/test_ui_gates.py`
> - 相关：`AI/frontend/shell.md`、`AI/environment.md`（截图对比与 fixture 配方）

## 1. 目录与分层

前端正在从「全局脚本 + 单文件 CSS」渐进迁到 `assets/app/`（原生 ES Module，无构建）。现有 `styles/`（token、分层总入口、base、组件汇总、外壳、过渡层）、`core/`（渲染、事件、快捷键、状态、总线、路由、请求、格式化）、`ui/`（23 个组件）、`main.js`、`shell.js`、`legacy-pages.js`、`legacy-bridge.js` 与组件陈列页，架构见 `AI/frontend/architecture.md`、组件见 `AI/frontend/components.md`；页面仍由 `assets/*.js` 与 `assets/styles.css` 提供，逐页迁移。

- `assets/app/` 下的一切适用 §5 的零容忍规则。
- `assets/` 根目录不再新增前端文件，新代码一律进 `assets/app/`（`check_ui.py` 会拦）。
- 样式分层：`styles/index.css` 声明 `vendor < legacy < base < ui < shell < domain < features < utilities < legacy-bridge`，KaTeX 进 `vendor`、旧 `styles.css` 进 `legacy`。新样式不靠提高选择器权重去压旧规则；也不许出现未分层的样式（未分层规则会压过全部分层规则）。
- `domain` 层：共享题目视图 `domain/question/qview.css`（P5 第 4 轮起是 qview 的全部外观，含题目弹窗与 Markdown 编辑器）与标记 `domain/labels/labels.css`（色板、颜色圆点按 `data-lbl-c` 取色）；标记颜色的运行时规则（`domain/labels/sheet.js`）也插在 `@layer domain` 块里。
- P5 第 4 轮新增 token：`--surface-sunken`（题面块等内嵌区）、`--success-subtle` / `--success-line`（答案块）、`--streak-ok` / `--streak-bad`（战绩带）、`--lbl-preset-1…10`（标记预设色）、`--lbl-fg-dark` / `--lbl-fg-light`（solid 芯片前景）；`check_contrast.py` 加「`fg-1` / `fg-2` 压在 `surface-sunken` 上」两组。
- 层次（core → ui → domain → features）与依赖方向由 `check_ui.py` 的 R7 约束；`core/`、`ui/`、`domain/`、`features/` 均已建立。每个页面的样式放 `features/<页>/<页>.css`，由 `styles/index.css` 以 `layer(features)` 引入（目前：`features/questions/questions.css`、`features/instant/instant.css`、`features/feedback/feedback.css`）；过渡层 `legacy-bridge.css` 随页面迁移分段删除（即时练习的「题数」段、题库工具栏段已删；反馈录入在其中没有段落）。旧 `styles.css` 里的全局元素规则（如 `header{padding;border-bottom;margin-bottom}`）仍在 legacy 层生效，页面用到这些元素时要在自己的层里显式清掉（反馈录入的 `.fbw-panel__head`）。
- `styles/index.css` 按层引入各页样式：features 层目前有 `questions.css`、`instant.css`、`feedback.css`、`dashboard.css`（v1.25.0 起）、`data.css`（v1.25.1 起；图表颜色用 `data-tone` 映射状态 token，`ui-progress` 的 `info` 语气在这里补）、`schedule.css`（v1.25.2 起；类名 `schd-` 前缀；旧 `styles.css` 里的 `.sch-*` 只剩服务「全题库导出」的几条）。仪表盘的「今天」数字是全站唯一的 `--text-display`；热力格四档颜色用 `color-mix(in srgb, var(--success) N%, var(--surface-1))`，不新增 token。
- 同一行的控件用同一档高度（§3 的 `--ctl-*`）。未迁移页面的旧 `.btn` / `.input` 由 `styles/legacy-bridge.css` 统一到 28 / 32 两档。

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

字号用 px 定义，不受旧样式 `html{font-size:15px}` 影响。紧凑密度 `html[data-density="compact"]` 把 `--text-sm/md/lg` 各降 1px，`--ctl-md/lg` 降到 30 / 36。窄屏（≤760px）为保证可点目标不小于 40px，三档控件高度统一为 40，不受密度影响。

## 4. 旧名别名

`tokens.css` 第 3 段把旧 token 名指向语义 token：`--bg*` → `--surface-*`，`--fg`/`--fg2`/`--fg3` → `--fg-*`，`--red/green/yellow/blue`（及 `-rgb`）→ 四个状态色，`--kill-*`/`--attack-*`/`--trap-*` → 状态色的 `-soft`/`-fg`，`--fam-*` → `--family-*`，`--border`/`--border2` → `--border-*`，`--card-shadow` → `--elev-1`。旧密度变量 `--radius*`、`--pad*`、`--gap`、`--row`、`--ctl`、`--fs*` 原值原样保留在同一段。

别名在 `<html>` 上求值，深色自动跟随，只有旧 `--shadow` 在深色块里单独覆盖。改调色板只改语义 token 一处；新代码禁止使用旧名。

`styles.css` 其余位置仍有写死的颜色（`check_ui.py --report` 可看存量），以及文件内的 `--ib-role-*` 局部变量，它们随页面迁移逐步清理。

## 5. 纪律门禁（`tests/check_ui.py`）

新代码（`assets/app/**`）零容忍，规则编号与脚本文件头一致：

- **R1** 颜色字面量只在 `tokens.css`。
- **R2** 字号、行高、字重、字体族只用 token。
- **R3** 间距不写长度字面量。
- **R4** 圆角、阴影、z-index、动效时长与缓动只用 token。
- **R5** 断点白名单。
- **R6** 模板里没有 `style=` 和 `on*=`；`innerHTML` 类写法只在 `core/dom.js`。
- **R7** 依赖方向。
- **R8** JS ≤ 400 行、CSS ≤ 300 行。
- **R9** 每个 `assets/app/features/<x>/` 须登记在 `AGENTS.md` 映射表。

旧代码（`assets/*.js`、`assets/styles.css`、`assets/inbox_mobile.html`、`omrs_dashboard.html`）按文件统计五项存量：行内事件、`innerHTML` 类赋值、行内样式、颜色字面量、硬编码字号，记在 `tests/ui_baseline.json`。

- **只减不增**：任何一项上升即失败。
- **下调基线**：减少后运行 `--update-baseline`；若有任何一项上升，拒绝写入。
- **格式**：基线按文件一行，并行修改时冲突最小；冲突时直接重跑 `--update-baseline`。

## 6. 对比度（`tests/check_contrast.py`）

脚本解析 `tokens.css` 的浅色与深色两套值，按 WCAG 2.x 计算 24 组 × 2 主题。

- **4.5:1**：文字类组合，包括 `--fg-1/2/3` 在 `surface-0/1` 上、`--fg-1/2` 在 `surface-2` 上、四个状态色在 `surface-0/1` 上、各 `-fg` 在自己的 `-soft` 上、`--on-accent` 在 `--accent` 上。
- **3:1**：`--fg-3` 在 `surface-2` 上、焦点环。
- 半透明底色先合成在 `surface-1` 上再计算。

修改任何颜色 token 后必须通过。

## 7. 待办（规划，尚未实现）

- 待办：其余页面迁到 `features/<页>/`（题目库、即时练习、反馈录入已完成），每迁一页删掉旧样式与过渡桥里对应的段落。
- 已实现：ui 组件库与组件陈列页（状态矩阵见 `AI/frontend/components.md`）；新组件须同样覆盖默认、悬停、按下、焦点、禁用、加载、空、错误、溢出、浅 / 深、舒适 / 紧凑，并在 gallery 与 `tests/app/browser_tests.js` 各加一处。
