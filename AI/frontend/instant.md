# 前端：即时练习

> **速查**
> - 职责：即时练习页（推荐题或聊天练习卡的固定题序、翻答案、判定打分、提交反馈），第一个迁到新架构的页面
> - 入口：`assets/app/features/instant/`（`index.js` 页面契约）、地址 `#/instant` 或 `#/instant?practice=<card_id>`
> - 不变量：不创建常规 Session（普通轮次 `session_id` 为 `IMM-*`）；判定、打分、切队列不重建题面；已提交的题锁定；共享数据与操作由 `assets/app/domain/` 管理
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
2. 到期列表在前、熟练度列表在后，按题目身份去重，截到题数，成为队列。不调用 `/api/confirm-schedule`，不生成 Session CSV。
3. 题面由 qview 渲染（经 `domain/question/index.js::mountQuestion`，`showMeta:false`；工具按钮：编辑 Markdown、加入展示板、编辑标记）。先只显示题面，点「显示答案」或按空格翻开答案与备注。
4. 判对或错：默认分对 8、错 4，手动打过的分不被覆盖；主观分 0–10。
5. 「提交」把已判定未提交的题发给 `POST /api/feedback`：`session_id` 为 `IMM-YYYYMMDDHHMMSS`，每题 `source` 为 `due` 或 `proficiency`，`note` 为「即时练习」；只写历史与 mastery，不建调度 Session。

即时练习复用 `process_feedback()` 的熟练度、EF、SM-2 更新逻辑。提交成功后这些题锁定：不能再改判，也不会被下一次提交重复发送；右栏列出本次结果（熟练度前 → 后），随后 `reloadData()`，并让这些题的 qview 失效重绘。每条反馈发送 `question_id`；失败项保留。每轮带独立版本，旧轮迟到的提交只刷新所属领域，不能锁定新轮同 UID 的题。有已判定未提交的题时重新取题，会先弹确认。

聊天练习卡走 `#/instant?practice=<card_id>`：页面从服务端取固定题序及有效题目，移动题目使用当前 UID，删除或停用项说明原因并跳过；不重新调用推荐算法。默认续最近 attempt，刷新恢复判定、位置和 Ledger 已提交项。重新练习显式签发新 attempt，`sessionStorage` 留住请求标识供响应丢失后重试；URL 可带 `attempt` 指向指定轮次。卡片反馈使用 `IMM-PA-*` 和稳定题目身份，逐题成功才锁定；失败项保留重试。创建、打开、切题与保存界面进度均不增加 Attempts，实际反馈才增加；仍不建立正式 Session。

## 渲染与不变量

- 每次状态变化 `morph(#panel-instant, view(state))`；会出现或消失的块都带 `data-key`，morph 按 key 对齐。
- 题面挂载点带 `data-morph="skip"`，key 是「uid + 是否翻开」：只有换题、翻答案时换新挂载点。判定、打分、切队列都不碰题面，KaTeX、图片与滚动位置保留，聚焦的按钮与滑杆保留焦点。
- 常规推荐练习状态是模块单例：离开页面再回来，队列、判定、筛选都还在；整页刷新后清空。聊天卡从服务端恢复进度与提交状态。
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

仪表盘先切换路由，再发送 `instant:load` 和科目 / 分类等预设。预设沿用 `inst-subject`、`inst-category`、`inst-ktag`、`inst-count`，取题前清空前三项再应用新值。标记定义更新通过 `labels` 总线重绘筛选芯片，芯片与定义来自 `domain/labels/`。

练习卡切普通推荐时先清掉卡片和 attempt，再读取一次推荐；普通路由挂载时不沿用残留卡片上下文。每次读取带请求序号和取消信号，卸载、换卡或换请求后旧读取无效；详情预载与统计刷新等每个异步边界也检查身份。实际控制器的排序、切换、迟到读取与提交行为由 `tests/app/audit-controllers.test.mjs` 验证。

旧 `INSTANT_QUEUE` 与 `instLoadPractice` 仅由 `tests/e2e/p8_test_modules.js` 注入给旧 E2E 断言，生产页面不提供这些全局。

熟练度百分比用 `core/format.js` 的 `formatPercent`（空值按 0% 显示）。E2E 只经 DOM、`window.__omrs` 与真实模块断言；审计前先等入场动画结束，缩放中的按钮会被量小。
