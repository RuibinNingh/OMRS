# 2026-09-01 共享题目视图（qview）+ 反馈录入工作台

## 起因

两个用户诉求：

1. 反馈录入时看不到题目——想看一道题要「切题目库 → 搜 UID → 点查看 → 看 modal → 关 modal → 切回反馈页 → 找回那一行」六步往返；发现题目本身录错了也只能中断录入。
2. 题目预览不好用——680px 单栏纵向堆叠，题面和答案不可能同屏，长公式和整页截图尤其糟糕；没有翻页，modal 里也没有任何操作入口。

定位后发现这是同一件事：缺一个可复用的「题目视图」组件。同一份题目内容当时有三处互不相同的渲染副本（`viewQ()`、画廊卡 `.gallery-preview`、`instRender()`）。

## 变更

### 新增 `assets/qview.js`（Layer 1）

共享题目视图组件，`<script>` 排在 `questions.js` 之后、`schedule.js` 之前。

- 对外：`qvHtml(q,item,opts)`（纯函数）、`qvRender(mount,uid,opts)`、`qvInvalidate(uid)`、`qvSetContext(name,uids)`。
- `opts`：`layout`（split/stack）、`reveal`、`showAnswer/showNotes/showHistory/showMeta`、`bare`、`clamp`、`actions`、`onReveal`。
- `reveal:false` 不渲染答案 DOM，只给「显示答案」按钮，少渲染一遍 KaTeX。
- 工具按钮（编辑 Markdown / 停用恢复 / 删除 / 在题目库打开）只转调 questions.js 已有的全局函数，走 `data-qv-act` 事件委托，不把函数名拼进 HTML 字符串。
- 双栏塌陷用容器查询（`container-type:inline-size` + `@container qv (max-width:680px)`），因为同一组件要同时进 1180px 的 Modal、约 420px 的反馈中栏和 300px 的画廊卡；`@supports not` 下降级为 900px 视口断点。

### 反馈页改三栏工作台（Layer 2）

`assets/feedback.js` 渲染层拆为 `fbRenderRail` / `fbRenderPanel` / `fbRenderStage`，`renderFb()` 名字保留（`onFbSessionChange` / `importFeedbackJson` / `addFbRow` / `submitFb` 都在调它）。

- 新增纯函数 `fbRailEntries(session, rows)` 并导出：rail 渲染 `sessionUniqueUids(session)` 全量而不只是 `pending_uids`，已录入行置灰只读，序号仍取 `fbSessionPositions()`（v1.8.2 行为，不回退）；不属于本 Session 的导入/手动行追加在末尾并显示可编辑 UID 字段。
- 点「对 / 错」只走 `fbPatchRailRow()` + `fbRenderPanel()`，题目 DOM 与 KaTeX 不重渲染；`FB_STAGE_UID` 去重舞台重绘。
- 分数默认值随判定走：未手动拖过时「对」置 9、「错」置 4；拖过后 `row.scoreTouched=true` 锁定。
- 快捷键 `fbHandleKey`：J/K/↑/↓ 切题、1 对 2 错、0–9 给分、Enter 跳下一道未判定、E 编辑、⌘/Ctrl+Enter 提交。
- 控件走 `data-fb-go` / `data-fb-act` 事件委托，`fbBindPanel()` 在 `#panel-feedback` 上只绑一次。

### 题目 Modal 改双栏 + 翻页（Layer 3）

- `#modal-title` / `#modal-meta` / `#modal-body` / `#modal-notes` / `#modal-answer` / `#modal-hist` 六个节点 → `.qv-nav` + 单挂载点 `#modal-stage`；`.modal-wide` 放宽到 `min(1180px,94vw)` / `88vh`。
- `viewQ(uid, context)` 增加可选第二参数（uid 数组或 `qvSetContext` 登记的上下文名），不传退化为单题。已接入上下文：`'q'`（题目库表格 + 画廊）、`'export'`、`'export-selection'`、`'leech'`。
- `←/→` 翻页（Markdown 编辑器打开时让位），`Esc` 关闭沿用 `app.js` 既有监听。
- `#md-editor` 的 `z-index` 由 999 抬到 1000；`saveMarkdownEditor` / `suspendQuestion` / `resumeQuestion` 成功后追加 `qvInvalidate(uid)`。
- `ensureQuestionDetail` 的降级副本增加 `_fallback:true`，qview 据此渲染「无法加载题目预览 + 重试」，重试即清缓存重绘——此前失败结果会被永久缓存住。

### 三处副本收敛

- 题目库画廊卡与导出选题画廊卡的 `.gallery-preview` 改用 `qvHtml(detail, item, QV_CARD_OPTS)`（`bare` + `clamp:6`）。
- 即时练习 `instRender()` 的题面/答案块改为 `qvRender('#inst-qv', …)`，`instReveal` 作为 `onReveal` 回调传入。

### CSS

- 新增 `.qv*` 与 `.fb-work` / `.fb-rail` / `.fb-panel` 段，颜色一律 `var(--*)` 或 `rgba(var(--*-rgb),α)`。
- 删除因此作废的规则：`.modal .q-body/.q-notes/.q-answer/.q-history/.q-md`、`.instant-md/.instant-notes/.instant-answer/.instant-answer-locked/.instant-block/.instant-label`、`.fb-grid/.fb-row/.fb-row2/.fb-uid/.fb-meta/.fb-del/.fb-note/.fb-tally/.fb-question-line`，以及两条写死 `rgba(39,134,74,.04)` 的答案块规则和它们的 `[data-theme="dark"]` 补丁。
- 深色「反转题图」选择器改为 `.q-md img` / `.qv .q-md img` / `.gallery-preview img`。
- 补 `:focus-visible` 描边与 `prefers-reduced-motion` 下关闭 modal 动画。

### 边界（明确没做）

后端零改动：`/api/feedback`、`/api/question`、`/api/question/raw|markdown|suspend|resume|delete` 全部按现状调用。`fbRows` 提交体仍是 `{uid, sub_score, is_correct, note}`。Session 序号语义不变。未引入框架或构建步骤。未做双栏滚动同步。未给卡片和列表行加逐个淡入动效。

## 影响文件

| 文件 | 变化 |
|---|---|
| `assets/qview.js` | 新增 |
| `assets/feedback.js` | 重写渲染层为三栏工作台 |
| `assets/questions.js` | `viewQ` 改双栏 + 翻页；画廊预览走 qvHtml；`_fallback` 标记；三处 `qvInvalidate` |
| `assets/instant.js` | 题面/答案块改 qview |
| `assets/export.js` | 画廊/平铺预览走 qvHtml；补翻页上下文 |
| `assets/data.js` | 顽固题 / 屡练不熟表补翻页上下文 |
| `assets/styles.css` | 新增 qview + 工作台样式；删除作废规则 |
| `omrs_dashboard.html` | 反馈页三栏骨架；Modal 换挂载点；新增 qview.js `<script>`；改动过的资源 `?v=20260901-qview`；侧栏版本号 |
| `omrs/version.py` | v1.9.0 → v1.10.0 |
| `README.md` / `AI/frontend.md` / `AI/optimization.md` | 文档同步（新增 frontend.md §2.2、§5.1） |

## 验证

已执行：

```
node tests/test_feedback_ui.js                    # 3 passed，四个纯函数契约未变
node tests/smoke_frontend_actions_catalog.js      # 全部通过
node tests/test_question_suspend_frontend.js      # 通过
node --check assets/*.js                          # 全部无语法错误
```

**未执行**：浏览器手测。以下 8 条需在真实环境确认，其中第 6、7 条风险最高（前者依赖新的选择器覆盖面，后者依赖容器查询在目标浏览器的支持）。

1. 选一个部分录入的 Session → rail 显示全部题目、已录置灰、序号为 Session 原始序号。
2. 点 rail 任意题 → stage 出题面与答案双栏；点已录入题 → 面板显示只读提示。
3. 在 stage 点「编辑 Markdown」→ 保存 → 内容已更新且未离开反馈页。
4. 只判定其中 3 题 → 提交 → 未判定题仍保留，进度与「已录/总数」正确（v1.8.2 行为）。
5. 题目库开一题 → `←/→` 在当前筛选结果内翻页 → `Esc` 关闭。
6. 深色 + 「反转题图」开启 → qview 内图片正确反相。
7. 窄到 800px → 三栏塌成竖排、rail 横滚、无横向溢出。
8. 断网 / 后端停 → stage 显示降级文案与「重试」，判定与提交按钮不被卡死。
