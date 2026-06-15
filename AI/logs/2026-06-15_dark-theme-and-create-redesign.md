# 2026-06-15 深色主题改版（暖石墨）+ 录入题目页重设计

> 范围：纯前端（视觉 / 结构）。**版本号不变，仍 `v1.5.0`**（未改 `omrs/version.py`）。后端、API、数据格式、JS 逻辑与所有元素 id 均未改动。

---

## ① 深色主题：玻璃拟态 → 暖石墨 Warm Graphite

**动机**：原 v1.5.0 深色为「AI 味」很重的玻璃拟态——紫色主色（`#b794f6` / `#a855f7`）、紫青渐变 `--grad` 铺在按钮 / 品牌块 / 进度条 / 数值文字上、紫色辉光 `--glow`、带蓝调近黑底加四道极光径向渐变、磨砂玻璃卡片。与本就克制的浅色（近黑墨 + 暖中性灰 + 发丝描边）人格割裂。

**改动**（仅 `assets/styles.css`）：
- 重建 `[data-theme="dark"]` token：实色暖中性梯度（`--bg:#1a1916` / `--bg2:#211f1c` / `--bg3:#2b2925` / `--bg4:#3a3732`）、骨白墨（`--fg:#ece7df`）、发丝暖描边。
- 主色由紫改单色骨白：`--accent:#ece7df`、`--accent-fg:#1a1916` → `.btn.primary` 成「浅底深字」，与浅色「深底白字」互为镜像；`--accent-rgb` 同步。
- 语义色由霓虹 400 收成大地色：`--red:#d98a7e`（黏土红）/ `--green:#82ab8b`（鼠尾草绿）/ `--yellow:#cda35f`（赭黄）/ `--blue:#7e9bbf`（灰蓝），`--fam-*`、`--kill/attack/trap-*` 同步。
- 删除 `--grad`、`--glow`；新增深色专属 `--shadow` / `--card-shadow`（轻微）。
- 删除深色覆盖块里的：body 极光径向渐变、玻璃卡片（`backdrop-filter`）、玻璃侧栏、渐变 / 辉光按钮、紫色激活态、紫色进度条辉光、渐变裁切 `.stat-value`、半透明白小块。卡片 / 数值 / 进度条 / 品牌块 / 激活态全部回退由 token 驱动；深色覆盖块由约 53 行瘦到 ~16 行（侧栏压深、分隔线、modal 遮罩、次按钮 wash、滚动条等少量必要微调）。
- 浅色 `:root` 一字未动；图表内联色本就走 `var()`，自动跟随。

---

## ② 录入题目页（`panel-create`）：双栏工作台

**动机**：原页是「左卡＝整张表单 / 右卡＝使用说明」的通用表单形态，把「截图 → AI 提取 → 核对 → 保存」这条流水线摊平，易出现「想粘到答案却粘进题目」等问题。

**改动**（`omrs_dashboard.html` 的 `panel-create` 内部结构 + `assets/styles.css` 追加一段 `.cr-*` 样式）：
- 顶部 `.cr-steps` 编号步骤条（截图→识别→核对→保存，真序列才用编号）。
- `.cr-workbench` 双栏（≤900px 单列）：
  - **左「截图工作区」`.card`**：题目截图区 + `.cr-div` + 答案截图区 + `.cr-tip`。
  - **右「题卡内容」`.card`**：`.cr-aigroup`（科目 / 分类并排 + 难度 + 相关知识点，标题「🤖 AI 自动填充 · 可改」）→ 题目正文 → 答案 → **错因** 暖色块 `.cr-cause`（`--trap-bg` 微染 + 赭色旗标 + 「复习时先看这里」脚注）→ 页码。
- 底部 `.cr-actionbar` 横跨双栏：「重置」（调既有 `resetCreateForm()`）+「创建题目」（`#cr-btn`）+ 静态保存说明；`#cr-result` 紧随其后。
- 原使用说明 / 文件结构树收进折叠块 `<details class="cr-help">`。
- 粘贴目标指示：仍由 JS 切的 `.paste-active` 驱动，新增 CSS `::after` 角标「粘贴目标」，**始终跟随当前目标区**（去掉了易与实际目标错位的静态标签）。
- AI 按钮文案：`#cr-classify-btn`「🤖 提取并填充信息」→「🤖 识别题目信息」；`#cr-extract-btn`「🤖 提取答案」→「🤖 提取答案文本」。

**契约保持**：`cr-q-paste / cr-q-file / cr-q-images / cr-classify-btn / cr-classify-status / cr-a-paste / cr-a-file / cr-a-images / cr-extract-btn / cr-extract-status / cr-subject / cr-category / cr-diff / cr-diff-val / cr-related / cr-question / cr-answer / cr-note / cr-cause / cr-btn / cr-result` 全部保留；`crClassify` / `crExtractAnswer` / `crSetPasteTarget` / `crHandlePaste` / `crRenderImages` / `doCreate` / `resetCreateForm` 等逻辑与 `/api/ai-recognize`、`/api/create` 接口不变。`#cr-related` 仍为逗号分隔文本框（classify 的合并逻辑依赖之，未改成 chips）。

---

## 涉及文件

- `assets/styles.css` — 重建深色 token + 深色覆盖块；末尾追加录入页 `.cr-*` 样式。
- `omrs_dashboard.html` — 替换 `panel-create` 内部结构为双栏工作台（panel 标签与 id 不变）。
- `AI/frontend.md` — 新增「v1.5.0 暖石墨」说明；§7 增补「双栏工作台」布局说明并更新按钮文案 / 字段顺序 / 粘贴目标角标。
