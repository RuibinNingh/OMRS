# 前端：即时练习

> **速查**
> - 职责：即时练习页（按推荐算法取题、在线翻答案、判定打分、提交反馈），第一个迁到新架构的页面
> - 入口：`assets/app/features/instant/`（`index.js` 页面契约）、地址 `#/instant`
> - 不变量：不写 `sessions.csv`（`session_id` 为 `IMM-*`）；判定、打分、切队列不重建题面；已提交的题锁定；只经 `assets/app/domain/` 碰旧全局
> - 必跑测试：`tests/app/instant.test.mjs`、`tests/e2e/instant.py`、`tests/check_ui.py`
> - 相关：`AI/frontend/review.md`（复习调度与临时 / 常规 Session）、`AI/frontend/architecture.md`（页面契约）、`AI/frontend/qview.md`

## 页面与文件

入口 Tab：`即时练习`，地址 `#/instant`。面板 `#panel-instant` 只是挂载点，页面由 `assets/app/features/instant/` 渲染——第一个迁到新架构的页面，页面契约见 `AI/frontend/architecture.md` §3。

| 文件 | 职责 |
|---|---|
| `index.js` | 页面契约；控制器（取题、切题、翻答案、判定、打分、提交）；动作与快捷键 |
| `state.js` | 模块单例状态与纯逻辑：合并推荐、预设翻译、判定与默认分、待提交行、下一道未判定 |
| `view.js` | `html``` 模板：设置条、题卡、判定区、右栏（进度与提交、队列）、提交结果、空 / 加载 / 出错状态 |
| `instant.css` | features 层版式 |

## 流程

1. 「加载推荐」调 `GET /api/recommend`：`due_count` 与 `prof_count` 都等于题数（1–50），可带 `subject` / `category` / `knowledge_tag` 与多个 `label`。两份列表再经 `domain/items.js` 转调全站筛选语义 `filterItems()`（排除停用题，不排序）。
2. 到期列表在前、熟练度列表在后，按 uid 去重，截到题数，成为队列。不调用 `/api/confirm-schedule`，不写 `sessions.csv`。
3. 题面由 qview 渲染（经 `domain/question/index.js::mountQuestion`，`showMeta:false`；工具按钮：编辑 Markdown、加入展示板、编辑标记）。先只显示题面，点「显示答案」或按空格翻开答案与备注。
4. 判对或错：默认分对 8、错 4，手动打过的分不被覆盖；主观分 0–10。
5. 「提交」把已判定未提交的题发给 `POST /api/feedback`：`session_id` 为 `IMM-YYYYMMDDHHMMSS`，每题 `source` 为 `due` 或 `proficiency`，`note` 为「即时练习」；只写历史与 mastery，不建调度 Session。

即时练习复用 `process_feedback()` 的熟练度、EF、SM-2 更新逻辑。提交成功后这些题锁定：不能再改判，也不会被下一次提交重复发送；右栏列出本次结果（熟练度前 → 后），随后 `reloadData()`，并让这些题的 qview 失效重绘。有已判定未提交的题时重新取题，会先弹确认。

## 渲染与不变量

- 每次状态变化 `morph(#panel-instant, view(state))`；会出现或消失的块都带 `data-key`，morph 按 key 对齐。
- 题面挂载点带 `data-morph="skip"`，key 是「uid + 是否翻开」：只有换题、翻答案时换新挂载点。判定、打分、切队列都不碰题面，KaTeX、图片与滚动位置保留，聚焦的按钮与滑杆保留焦点。
- 状态是模块单例：离开页面再回来，队列、判定、筛选都还在；整页刷新后清空。
- 取题时按钮立即进入加载态；超过 300ms 还没返回才换成骨架屏。
- 字号全部来自 token（页面自身 ≤6 种，题面 qview 子树不计）；可点目标桌面 ≥28px、手机 40px。

## 版式

- >1160：整屏工作台，题卡在左、自己滚动；右栏 300px 放进度与提交、队列（自己滚动），提交结果在右栏底部。
- ≤1160：单栏竖排，依次是进度与提交、队列（横条，只留序号与状态）、题卡、提交结果。
- ≤760：设置条两列网格，「加载推荐」占整行；判定按钮两列；导航里「下一道未判定」整行放最上；不显示快捷键提示。
- 题面双栏在挂载点宽度 ≤680px 时改单栏：挂载点就是 qview 的尺寸容器，规则在 `assets/app/domain/question/qview.css`，本页不再自补。

## 快捷键

作用域 `instant`（`core/keys.js`），输入框里、弹层打开时不触发，与反馈工作台一致：`J` / `↓` 下一题，`K` / `↑` 上一题，空格显示答案，`1` 判对，`2` 判错，`0` 与 `3`–`9` 打分（需已判定），`Enter` 下一道未判定，`E` 编辑 Markdown，`⌘` / `Ctrl` + `Enter` 提交。焦点在按钮上时，空格与 `Enter` 让给按钮本身。

## 旧入口（过渡桥，P8 删除）

- 仪表盘行动推荐调 `actions.js::actionGoInstant(preset)`：`switchTab('instant')` 后调过渡桥的 `instLoadPractice(preset)`。预设键沿用旧元素 id（`inst-subject` / `inst-category` / `inst-ktag` / `inst-count`），新页面先清空科目、分类、知识点再套用，然后取题。
- 旧代码改了标记定义（`labels.js::renderLabelFilterOptions()`）后经 bus 发 `labels`，新页面重画标记筛选。
- 标记芯片与标记筛选来自 `domain/labels/index.js`（`labelChip(s)`、`listLabels()`；P5 第 4 轮起 `domain/labels.js` 扩成目录，芯片颜色写 `data-lbl-c`，不写 `style=`）。
- `INSTANT_QUEUE` 是只读兼容属性，给旧冒烟测试用。

熟练度百分比用 `core/format.js` 的 `formatPercent`（空值按 0% 显示）。E2E 只经 DOM、`window.__omrs` 与真实模块断言；审计前先等入场动画结束，缩放中的按钮会被量小。
