# 前端：反馈录入工作台

> **速查**
> - 职责：反馈录入工作台（选 Session、逐题判对错打分、查看和补记错因、导入答题卡 / 反馈 JSON、分批提交）
> - 入口：`assets/app/features/feedback/`（`index.js` 页面契约）、地址 `#/feedback`
> - 不变量：rail 显示全部题目；新提交使用 `{question_id, entry_id?, sub_score, is_correct, note}`；判定、打分、写备注不重建题面；数据与操作经领域模块
> - 必跑测试：`tests/app/feedback.test.mjs`、`tests/e2e/feedback.py`、`tests/e2e/feedback_reflections.py`、`tests/check_ui.py`；复习调度联动另见 `tests/e2e/schedule.py`
> - 相关：`AI/omr-import.md`（答题卡协议）、`AI/frontend/architecture.md`（页面契约）、`AI/frontend/review.md`（复习调度）、`AI/frontend/qview.md`

## 页面与文件

计划选择器标出「已暂停」，选中后显示保留的录入进度与恢复提示，提交按钮禁用；快捷提交也会校验暂停状态。暂停不清除本页表单，恢复调度后可继续；跨客户端的旧页面提交仍由后端写事务拒绝。暂停状态和恢复入口见 `AI/frontend/review.md`。

入口 Tab：`反馈录入`，地址 `#/feedback`。面板 `#panel-feedback` 只是挂载点，页面由 `assets/app/features/feedback/` 渲染，写法照 `instant/`。

| 文件 | 职责 |
|---|---|
| `index.js` / `controller.js` | 页面挂载、动作与快捷键；控制器处理计划、切题、录入、导入、单题处置与结单 |
| `state.js` | 模块单例状态与纯逻辑：Session 进度、rail 条目、光标、判定与默认分、提交体，以及 OMR / 反馈 JSON 解析器 |
| `importer.js` | 一段文本 → 导入计划（解析、分流、算出新行与状态报告），纯函数；三个导入入口共用 |
| `view.js` | `html``` 模板：顶栏、导入折叠面板、rail、题面挂载点、判定面板、状态行、提交结果明细 |
| `feedback.css` | features 层版式（类名前缀 `fbw-`） |

Session 列表归 `domain/sessions.js`。服务端 `progress` 定义原计划题数与处置计数。题号取 `entries` 原序，交互按固定 `entry_id` 合并。只读条目的 DOM 键回退到稳定题目身份，兼容 UID-only 记录使用原 UID。

## 流程

1. 默认光标落在首个可录且未判定条目。Enter 在原序中找下一道可录的未判定题，可点击任何题号查看处置。手动模式可加行，正式计划使用原条目。
2. 判定、评分和备注存于页面内存，直到成功回执才算已录。分批提交只发送仍可录且已判定的条目。部分失败或重读失败时保留未成功行，重新读取按固定 `entry_id` 对齐。题目绑定改变时新身份使用新草稿。
3. 活动计划在当前题的次级操作提供「仅本次跳过」或「撤销本次跳过」。已判题会提示这条反馈本次不提交。撤销复用当前页内存中的判定、分数与备注。待确认的条目还可转到计划详情手动绑定。
4. 全题录入后自动完成。待录和身份待确认均清空时可显式结束，确认框列出已录、跳过、不可录数量。结束后展示结单时处置，零反馈显示「已结束 · 无反馈」。暂停时需先恢复。
5. 整页刷新从服务器恢复反馈处置与结单历史。尚未提交的判定与备注随页面内存释放。

## 渲染与不变量

rail 保留原序与全部条目，状态和操作区各有固定键。表单判定、分数和备注变化时复用题面挂载点。结单时已有反馈而当前因历史修正无效的条目，面板显示两者的区别。

## 错因记录

有效题目的判定栏在表单后显示共享错因区，默认「历史记录」，旧裸错因与日期化记录按同一题目 Markdown 读取；「记录本次」可直接补记、关联问题、修订和撤回。已录入作答的题仍可查看和补记错因，归档、停用或身份不明条目不挂载。错因独立保存；「本次作答备注」与原反馈一起提交，用于页码或作答情况。

错因挂载点按稳定 question_id 标识并带 `data-morph="skip"`，判定、打分和标记重绘不重建记录或编辑框。换题释放旧监听，按新身份读取；反馈页与题目弹窗使用不同页签 ID，避免同时打开同题时相互控制。错因格式、分页、草稿与保存协议见 `AI/frontend/qview.md`。

换题、换 Session、改 UID、添加／移除行、导入、提交、刷新、跳过、撤销和结单前，先通过错因保存／放弃／继续编辑守卫；取消保持原题与表单。路由离开使用同一守卫，卸载释放守卫与监听。焦点位于错因区时，Ctrl/⌘+Enter 只保存错因。`tests/e2e/feedback_reflections.py` 使用临时 Vault 验证真实保存、失败重试、身份、作答独立性、离开保护与双主题四档宽度；证据目录由 `OMRS_FEEDBACK_REFLECTION_EVIDENCE` 指定。

## 版式

- >1160：整屏工作台，题目列表 264px | 题面 | 判定面板 340px 三列，各自滚动。
- ≤1160：单栏竖排，依次是题目列表横条（只留序号与状态）、判定面板、题面——对着纸面结果判定时不必每题滚过整个题面（与改前一致；DOM 顺序不变，用 `order` 调整）。
- ≤760：顶栏动作两列网格，「刷新」占整行；判定按钮不显示快捷键角标，不显示快捷键提示行。
- 题面双栏在挂载点宽度 ≤680px 时改单栏；整行超宽的公式只在自己的块里横滚，不撑出整页横向滚动。两条都由 qview 自身的 `assets/app/domain/question/qview.css` 处理，本页不再自补。

## 快捷键与粘贴

作用域 `feedback`（`core/keys.js`），输入框里、弹层打开时不触发：`J` / `↓` 下一题，`K` / `↑` 上一题，`1` 判对，`2` 判错，`0` 与 `3`–`9` 打分（需已判定），`Enter` 下一道未判定（焦点在按钮上时让给按钮），`E` 编辑 Markdown，`⌘` / `Ctrl` + `Enter` 提交。

`core/keys.js` 只管 keydown，而局域网 http 下只有 paste 事件能拿到剪贴板，所以「在本页空白处 `⌘`/`Ctrl`+`V` 读答题卡」是挂载期间的 document `paste` 监听：本页可见、焦点不在输入控件、没有弹层时才接管（守卫是 `dialog[open]:not(.is-closing), .modal-overlay.open`：退场动画中的对话框不算，P5 第 3 轮起），卸载时移除。

## 导入

三个入口——「读剪贴板填写」按钮、空白处粘贴、导入面板的文本框 +「导入 JSON」——都走 `importer.js::planImportText()`：答题卡 `/result` 协议按 Session entries 的固定序号对号（必须先选 Session），反馈 JSON 可用原题号或稳定身份匹配原计划，导入仅填写待录条目，题目 JSON 被拦下。报告写进导入面板的状态行，面板自动展开。协议与判定规则见 [`omr-import.md`](../omr-import.md)。

反馈 JSON 导入失败时保留当前计划与输入。

## 跨页联动

复习调度先切 `feedback` 路由，再发送 `feedback:session`；反馈页刷新列表后选中计划。列表改变发 `sessions`，删除计划发 `feedback:reset` / `feedback:clear-results`，标记更新发 `feedback:render`。生产不注入旧全局，旧 E2E 兼容断言仅由测试适配器提供。

进度由 `domain/sessions.js::sessionProgress` 适配服务端计数。Session UID-only 导入只在该计划的已绑定条目内解析；多个条目都匹配同一个 UID 时不会猜测。OMR 与同 UID 的归档／新题不会互串，行为回归见 `tests/app/audit-identity-uploads.test.mjs`。

`tests/app/feedback.test.mjs` 覆盖同 UID 的已录条目、空 UID 的固定身份与旧计划兼容；`tests/e2e/feedback.py` 用合成 Session 列表验证 40 题中 31 已录、9 待录的真实页面，核对历史只读、题面及判定。浅深色桌面／手机截图保存在独立临时目录，可用 `OMRS_FEEDBACK_SHOTS` 指定位置。

提交结果显示服务端实际状态、熟练度变化、复核档位（击杀题）和「下次复习 YYYY-MM-DD」。一次高分立即显示「已击杀」；已击杀题低分答对显示「磨合中」、3天后巩固，答错1天后重练；提前高分显示原档位与原日期。熟练度变化用 `core/format.js` 的 `formatPercent`。关闭题目 Markdown 编辑器走 Esc（对话框不把 Esc 外泄给页面）。

`node tests/e2e/feedback_closeout.mjs` 使用本机 Chromium 和随机回环端口覆盖错因守卫、撤销跳过、跨端停用、分批提交、恢复后草稿、按原号导入、结单历史与调度入口。
