# 前端：外壳、布局与主题

> **速查**
> - 职责：页面外壳：`assets/` 文件划分与加载顺序、侧栏与顶栏、hash 路由的外壳一侧、整屏工作台布局、主题 token 与深色对比度
> - 入口：`omrs_dashboard.html`、`assets/app/theme-boot.js`、`assets/app/main.js`、`assets/app/shell.js`、`assets/app/styles/shell.css`、`assets/app/styles/tokens.css`、`assets/app/styles/index.css`
> - 不变量：`main.js` 装配页面契约与领域服务后启动路由；外壳负责面板生命周期、侧栏和顶栏状态；颜色一律走 token，不在规则里写死浅色值
> - 必跑测试：`tests/e2e/shell_router.py`、`tests/e2e/catalog.py`、`tests/app/settings.test.mjs`、`tests/e2e/settings.py`
> - 相关：`AI/frontend.md`（索引）

## 文件组织（assets/）
```
omrs_dashboard.html   ← 页面骨架，加载主题启动脚本、样式、KaTeX 与模块入口
assets/
├── app/main.js       ← ES Module 启动入口，登记页面并加载共享快照
├── app/shell.js      ← 页面生命周期、侧栏、顶栏、全局动作
├── app/core/         ← 路由、请求、事件、状态、总线等底座
├── app/ui/           ← 无业务通用组件
├── app/domain/       ← 跨页面的题目、标记、Session 等领域模块
├── app/features/     ← 仪表盘、题库、展示板、复习、录入等页面
├── app/styles/       ← token、基础样式、外壳样式与分层总入口
└── vendor/           ← 本地字体与 KaTeX
```

首次打开 `/` 或 `/login` 时，服务端先返回独立的锁屏入口。入口沿用 Gravity Journey 的全屏布局：固定视口中的 Three.js/WebGL 黑洞、金白色吸积环、公式曲面与星尘，顶部 `( Deploy ) / ( Preview ) / ( Ship )` 网格和底部工作区标识保持同一排版；滚动推进镜头，指针扰动场景，点击产生脉冲。入口背景可在「设置 → 外观与显示」切换为黑洞预设或当前 Vault 的自定义图片 / 视频；自定义媒体通过公开的当前资源端点读取，使用 `cover` 裁切、固定暗色遮罩和 0–32px 高斯模糊。视频自动静音循环播放，`prefers-reduced-motion` 下暂停视频并关闭黑洞动画。启用 PIN 时在右下入口栏输入 4–12 位数字解锁，未启用 PIN 且当前来源有访问权限时点击「进入 OMRS」。解锁后通过带当前进程 handoff token 的 `/?unlocked=1` 地址回到原有单页外壳，Hash 路由继续保留；工作台 HTML 响应为 `no-store`，避免重启或部署后复用旧页面壳。入口页只加载场景 vendor 资源和当前背景，不读取题库数据；媒体加载失败、配置损坏或 WebGL 不可用时回退黑洞参考主视觉。

**加载约定：**
- `<head>` 先运行 `assets/app/theme-boot.js` 读取主题、密度、侧栏与图片反色偏好；随后加载本地字体、`tokens.css`、`index.css` 和 KaTeX 脚本。`index.css` 用 `@layer` 引入 KaTeX 样式、基础样式、组件、领域与页面样式。
- 页面底部仅以 `<script type="module">` 加载 `assets/app/main.js`。它安装共享组件，创建外壳和页面路由，连接领域服务，并在初始标签、统计、Session 数据加载后进入当前 hash 页面；详见 `AI/frontend/architecture.md` §2。
- 题目 Markdown 的 HTML 由 `domain/question/markdown.js` 统一生成，`domain/question/qview.css` 提供题面块与换行样式；普通换行默认逐行显示，空行仍分段。题库显示设置可显式切回简略模式，测试见 `tests/app/question.test.mjs`。
- 后端由 `/assets/<file>` 通用静态路由提供资源（`server.py` → `_serve_asset()`，含路径穿越防护与按扩展名的 content-type）。页面样式放在对应的 `features/<页>/`；外壳样式在 `app/styles/shell.css`，组件样式在 `app/ui/`，颜色与尺度在 `app/styles/tokens.css`。

设置页的六个分区由 `tests/e2e/settings.py` 在桌面与手机、浅色与深色下逐一审计；访问与安全分区还包含 MCP Key 的一次性明文展示与元数据列表，助手分区同时验证最大输出 Token 的输入、保存和回读。

页面切换或卸载后的异步响应由各页面控制器按请求序号和当前身份核对，不反写外壳的现有路由选择。`tests/e2e/assistant_race.py`、`tests/app/create-inbox.test.mjs`、`annotate.test.mjs` 与 `board-locked.test.mjs` 覆盖迟到响应、未保存编辑和目标读取失败时的页面状态；入口与具体契约见对应页面分册。

录入页的可搜索建议层挂在 body，页面控制器卸载时移除，不由外壳持有；手机端依据 VisualViewport 可见高度贴在键盘上方。快速录入的迟到识别结果只在当前题目和图片版本仍匹配时应用。

## 侧栏、顶栏与路由（`assets/app/styles/shell.css`、`assets/app/shell.js`）

- 地址形如 `#/questions`：刷新停在原页，浏览器前进后退可用，页面可以直接用链接打开。路由与页面契约见 `AI/frontend/architecture.md` §3。
- 页面 `<head>` 注册 `assets/app/omrs-favicon.svg` 作为 16–32px 标签页图标，注册 `assets/app/omrs-icon.svg` 作为 48px 以上与触控主屏图标；侧栏左上角 32px 品牌位使用小尺寸图标，旁边保留 OMRS 名称与中文副标题。
- 侧栏宽 232px，导航项是 `<a class="tab" href="#/页面">`（键盘可达）。当前页：强调浅底、半粗、左侧 3px 指示条，并带 `aria-current="page"`。
- 侧栏页脚在 `omrs_dashboard.html` 声明当前版本号，与 `omrs/version.py`、根 `README.md` 和 `AI/README.md` 保持同步；运行中 `/api/status` 返回同一版本。
- 侧栏、折叠按钮和手机汉堡按钮的图标都引用页面内的 `#i-*` SVG sprite；`.nav-ico` 统一设置 `currentColor` 描边、无填充、圆角线帽和 18px 盒子，避免 symbol 缺少外观规则时退回浏览器默认填充。
- 折叠：侧栏按钮的 `data-action="app.collapse"` 更新 `<html data-sidebar>` 和 localStorage，侧栏收成 58px 图标栏；折叠时外壳给导航项挂 `data-tooltip`，悬停显示页面名。
- 顶栏：标题是 `<h1 id="topbar-title">`，由外壳按页面登记写入，同时写 `document.title`。顶栏的全局「录入题目」按钮走 `app.create`。各页的「重新扫描」按钮走 `app.scan`：外壳调用 `domain/scan.js::scanVault()`，期间相关按钮置忙；在目录页扫描成功时发 `catalog:refresh`，使目录控制器重读磁盘树。
- 手机（≤760px）：侧栏变左侧抽屉（汉堡按钮打开，遮罩或 Esc 关闭，切页后自动关闭）；顶栏的「录入题目」只留 40×40 图标（文字对读屏保留），标题占满剩余宽度、过长时省略，不再被按钮挤压。
- 助手手机模式在挂载期给 `.content` 加 `is-assistant`，由助手头部的一行按钮打开同一个主导航抽屉；外壳的重复顶栏隐藏，卸载时恢复。其页面高度与输入框增长由助手控制器按可见视口调整，具体见 `AI/frontend/assistant.md`。
- 助手的用量弹层和圆环指标属于助手页面状态，模式偏好在浏览器本地存储；切换外壳页面或刷新后仍按该偏好呈现，具体语义见 `AI/frontend/assistant.md`。

## 整屏工作台布局（`.is-workbench`）

多栏工作台按页面契约启用整屏布局：

1. 外壳（`assets/app/shell.js`）按页面登记表的 `workbench` 字段给 `.content` 切 `.is-workbench` 类，命中五页：
   `questions` / `feedback` / `create` / `board` / `instant`。
2. `assets/app/styles/shell.css` 在大于 1160px 时让 `.content.is-workbench` 变成
   `height:100vh; overflow:hidden` 的 flex 列，`.topbar` 不收缩，`.panel.active` 拿走剩余高度。
3. 各页把自己的滚动容器标成 `flex:1; min-height:0; overflow-y:auto`。

因此高度是从 `.content` 一路分下去的，**不再出现 `calc(100vh - 魔数)`**；页头加减工具栏无需重算。

| 页面 | 撑高的容器 | 各自滚动的区域 |
|---|---|---|
| 题目库 | `.qlb` → `.qlb-card` → `.qlb-body`（`features/questions/questions.css`） | `.qlb-main` 里的表格 / 画廊、`.qlb-drawer` |
| 反馈录入 | `.fb-work`（`grid-template-rows:minmax(0,1fr)`） | `.fb-rail` / `.fb-stage` / `.fb-panel` 三栏独立 |
| 录入题目 | `#create-app` → `.ib-stage.on`；处理页额外 `#ib-stage-process.on` → `.ib-proc` | 上传、处理、录入与 AI 训练各工作区按自身布局滚动；处理区的成功状态写在右侧标题下，不占用全局 toast 层 |
| 展示板 | `.brd` → `.brd-main` → `.brd-work` | 板列表、纸面桌面、题目面板各自滚动 |
| 即时练习 | `.inst-work`（`features/instant/instant.css`） | `.inst-main` / `.inst-queue__list` |

配套：题库表头 `position:sticky; top:0`，列表再长表头也在；抽屉不 sticky（父级已经限高，自己滚）。

**只在 ≥1161px 生效**。窄屏沿用原有响应式：反馈工作台仍走 1160 / 820 两档重排，
题库抽屉 ≤1160 落到列表上方，都不受影响。

改这几页时的注意点：
- 新增的滚动容器必须同时写 `min-height:0`，否则 flex 子项按内容撑开，`overflow` 不生效。
- 往工作台页面加新的顶部工具栏，记得给它 `flex-shrink:0`，否则会被压扁。
- 新增工作台型页面时，在页面契约里写 `workbench: true`，不需要动 CSS 结构。

## 主题与对比度（`assets/app/styles/tokens.css`）

`assets/app/theme-boot.js` 在样式加载前读取 `omrs-theme`、`omrs-density`、`omrs-sidebar-collapsed` 和 `omrs-invert-img`，分别设置 `<html>` 的 `data-theme`、`data-density`、`data-sidebar` 和 `data-invert-img`。未设置主题时默认深色，密度默认紧凑。切换控件与持久化见 `AI/frontend/settings.md`「外观与显示」。

浅色语义 token 定义在 `:root`，深色覆盖定义在 `[data-theme="dark"]`；包括表面、文字、描边、强调、状态和图表颜色。外壳与各页只引用这些 token，字号、间距和控件尺度也由 `tokens.css` 统一给出。`index.css` 的分层顺序是 `vendor < base < ui < shell < domain < features < utilities`，其中 `shell.css` 负责侧栏、顶栏及工作台布局。浅色与深色的对比度由 `tests/check_contrast.py` 校验；约束见 `AI/frontend/design-system.md`。

## AI 草稿角标

录入题目侧栏入口的 `#nav-draft-count` 使用现有 ui-badge，显示 cropping + review，超过 99 显示 99+，零时隐藏。计数读取、刷新与跨页导航由 `domain/drafts.js` 统一拥有，助手关闭时仍能审核已有草稿。

草稿工作区手机队列默认折叠，侧栏角标仍显示全部待审核数。入库后工作区主动刷新角标和待审列表，再切到下一份草稿；跨页打开草稿仍通过 `domain/drafts.js` 的目标交接，避免在页面尚未挂载时丢失导航。


助手页面的手机外壳使用 `100dvh` 与可见视口同步，专项浏览器回归同时检查窄屏无横向溢出。
