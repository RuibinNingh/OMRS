# 前端：反馈录入工作台

> **速查**
> - 职责：反馈录入工作台（选 Session、逐题看题面判对错打分、导入答题卡 / 反馈 JSON、分批提交），第二个迁到新架构的页面（P4）
> - 入口：`assets/app/features/feedback/`（`index.js` 页面契约）、地址 `#/feedback`
> - 不变量：rail 显示全部题目；提交体 `{uid, sub_score, is_correct, note}` 与 `/api/feedback` 契约不变；判定、打分、写备注不重建题面；只经 `assets/app/domain/` 碰旧全局
> - 必跑测试：`tests/app/feedback.test.mjs`、`tests/e2e/feedback.py`、`tests/check_ui.py`；复习调度联动另见 `tests/smoke_schedule_workbench.py`
> - 相关：`AI/omr-import.md`（答题卡协议）、`AI/frontend/architecture.md`（页面契约）、`AI/frontend/review.md`（复习调度）、`AI/frontend/qview.md`

## 页面与文件

入口 Tab：`反馈录入`，地址 `#/feedback`。面板 `#panel-feedback` 只是挂载点，页面由 `assets/app/features/feedback/` 渲染，写法照 `instant/`。

| 文件 | 职责 |
|---|---|
| `index.js` | 页面契约；控制器（选 Session、切题、判定、打分、导入、提交）；动作与快捷键；粘贴监听 |
| `state.js` | 模块单例状态与纯逻辑：Session 进度、rail 条目、光标、判定与默认分、提交体，以及 OMR / 反馈 JSON 解析器 |
| `importer.js` | 一段文本 → 导入计划（解析、分流、算出新行与状态报告），纯函数；三个导入入口共用 |
| `view.js` | `html``` 模板：顶栏、导入折叠面板、rail、题面挂载点、判定面板、状态行、提交结果明细 |
| `feedback.css` | features 层版式（类名前缀 `fbw-`） |

Session 列表 `SESSIONS` 与当前选中 `ACTIVE_FB_SESSION` 仍归旧代码（`core.js` 声明、`schedule.js::refreshSessions()` 载入），本页只经 `domain/sessions.js` 读写；P6 数据所有权反转时只改适配器。

## 流程

1. 进入页面即经 `domain/sessions.js` 转调旧 `refreshSessions()` 拉最新进度（取代旧 `enter` 钩子）；并发的刷新共用同一个 promise。
2. 选 Session：建出「待录入」行（`fbRowsForSession`），光标落在第一道未判定题。不选 Session 时是手动录入：「添加行」后填 UID。
3. 逐题判对 / 错：没手动打过分时对 9、错 4；拖过滑杆或按数字后 `scoreTouched=true`，判定不再改分。备注、标记（快捷标记与「编辑标记」）就地改。
4. 「提交」（或 `⌘`/`Ctrl`+`Enter`）只发已判定的行；UID 空或重复、本 Session 已录过的题先拦下。成功后结果进 `ui/dialog` 弹窗，随后 `reloadData()`、让这些题的 qview 失效、刷新 Session 进度并重建待录入行；未判定题保留到下一批。失败时状态行给出原因，判定保留。

## 渲染与不变量

- 每次状态变化 `morph(#panel-feedback, view(state))`；会出现或消失的块都带 `data-key`。rail 条目的 key 是「行下标 | 只读题 uid」，保证唯一（`each()` 遇重复 key 直接报错）。
- 题面挂载点带 `data-morph="skip"`、key 为 `qv:<uid>`：只有换题时换新挂载点；判定、打分、写备注都不碰题面，KaTeX、图片与滚动保留，聚焦的按钮与滑杆保留焦点。题面经 `domain/question/index.js::mountQuestionStage()`，显示完整题头，工具按钮多给「停用」「打开」。
- rail 显示 Session 全部题目：序号沿用 Session 原始顺序；已录入的题 `is-done` 只读（判定面板显示只读提示）；不属于本 Session 的导入 / 手动行追加在末尾，面板给出可编辑的 UID 字段。
- 状态是模块单例：离开页面再回来，Session 选择、判定、导入的行都还在；整页刷新后清空。导入文本框的草稿也记在状态里，重绘不丢。
- 字号全部来自 token（页面自身 ≤6 种，题面子树不计）；可点目标 ≥28px，手机判定按钮 40px。

## 版式

- >1160：整屏工作台，题目列表 264px | 题面 | 判定面板 340px 三列，各自滚动。
- ≤1160：单栏竖排，依次是题目列表横条（只留序号与状态）、判定面板、题面——对着纸面结果判定时不必每题滚过整个题面（与改前一致；DOM 顺序不变，用 `order` 调整）。
- ≤760：顶栏动作两列网格，「刷新」占整行；判定按钮不显示快捷键角标，不显示快捷键提示行。
- 题面双栏在挂载点宽度 ≤680px 时改单栏；整行超宽的公式只在自己的块里横滚，不撑出整页横向滚动。两条都由 qview 自身的 `assets/app/domain/question/qview.css` 处理，本页不再自补。

## 快捷键与粘贴

作用域 `feedback`（`core/keys.js`），输入框里、弹层打开时不触发：`J` / `↓` 下一题，`K` / `↑` 上一题，`1` 判对，`2` 判错，`0` 与 `3`–`9` 打分（需已判定），`Enter` 下一道未判定（焦点在按钮上时让给按钮），`E` 编辑 Markdown，`⌘` / `Ctrl` + `Enter` 提交。

`core/keys.js` 只管 keydown，而局域网 http 下只有 paste 事件能拿到剪贴板，所以「在本页空白处 `⌘`/`Ctrl`+`V` 读答题卡」是挂载期间的 document `paste` 监听：本页可见、焦点不在输入控件、没有弹层时才接管（守卫是 `dialog[open]:not(.is-closing), .modal-overlay.open`：退场动画中的对话框不算，P5 第 3 轮起），卸载时移除。

## 导入

三个入口——「读剪贴板填写」按钮、空白处粘贴、导入面板的文本框 +「导入 JSON」——都走 `importer.js::planImportText()`：答题卡 `/result` 协议按 Session 顺序对号（必须先选 Session），反馈 JSON（屏幕版 / AI）带 `session_id` 且能找到时切过去并跳过已录入的题，题目 JSON 被拦下。报告写进导入面板的状态行，面板自动展开。协议与判定规则见 [`omr-import.md`](../omr-import.md)。

与旧页面的一处有意差异：反馈 JSON 导入失败（如全部已录入）时不再顺手切换当前 Session，保持原状。

## 旧入口（过渡桥，P8 删除）

- 复习调度「录入结果」调 `schedule.js::feedbackSession(sid)`：`router.go('feedback')` 后经 bus 发 `feedback:session`，新页面刷新进度再选中该计划。
- `schedule.js::refreshSessions()` 末尾的 `refreshFbSessionPicker()` 改为经 bus 发 `sessions`，新页面重绘下拉与进度。
- 删除计划时 `schedule.js` 调的 `resetFeedbackForm()` / `fbClearResults()`、标记变化后 `labels.js` 调的 `renderFb()`：由模块事件总线 挂成全局函数，分别发 `feedback:reset` / `feedback:clear-results` / `feedback:render`。
- 标记芯片与快捷标记来自 `domain/labels/index.js`（P5 第 4 轮起目录化；芯片颜色写 `data-lbl-c`，不写 `style=`）。
- Session 进度 `fbSessionProgress()` / `sessionUniqueUids()` 的实现在 `domain/sessions.js`（v1.25.2 起与复习调度共用），`state.js` 原名再导出；反馈页刷新计划列表调 `domain/sessions.js` 的 `refreshSessions()`（不抛出，失败返回原因）。
