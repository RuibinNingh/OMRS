# 2026-09-12 反馈提交结果改弹窗

> 本仓库是从「脱敏源码包」（`OMRS-source-sanitized-20260912T130848Z.zip`）恢复出来的工作副本，
> 不含 `.git`，所以本次没有 `git status --short` / `git diff --name-status` 可跑；改动范围改用
> 与导出包原始内容逐文件 `diff` 核对，结果见下方「验证」一节。**这份日志文件本身也需要你手动
> 放回真实仓库的 `AI/logs/`，并在 `AI/logs/log.md` 里补一条索引**（该文件不在脱敏导出范围内，
> 我这边看不到它现在的条目格式，无法安全地帮你续写）。

## 用户诉求

> 反馈录入后的结果显示改成弹窗式的显示,不然占用屏幕空间还关不掉

原话只有一条，没有分期，本次即按「执行到这条满足为止」处理。

## 行为变化

- 提交反馈（`submitFb()`）后，「本次处理结果」明细不再直接写进页内 `#fb-results`（会把
  `.fb-work` 三栏工作台挤矮，且此前唯一的清空时机是换 Session / 重新导入，没有任何关闭入口）。
- 新增 `#fb-result-modal` 弹窗（复用 `#modal` / `#md-editor` 同一套 `.modal-overlay` 骨架）。
  提交后自动弹出，明细渲染进弹窗内的 `.fb-result-list`（自己滚，头尾固定）。
- 页内改为 `.fb-statusbar` 一行：`#fb-status` 一句小结（不变）+ `#fb-result-reopen`
  「查看本次结果」按钮，提交过一次之后就一直可点，能把上一次结果重新弹出来。
- 关闭入口四个：右上 `✕`、底部「知道了」、点遮罩、`Escape`。
- 弹窗开着时，`fbHandleKey` 只认 `Escape`（其余分支直接 `return`），`J`/`K`/`1`/`2`/
  `⌘`/`Ctrl`+`Enter` 都打不到后面被弹窗盖住的判定面板；`fbHandlePaste` 同样在弹窗打开时让路。
- 换 Session（`onFbSessionChange(true)`）、答题卡导入（`fbImportOmrScan`）、反馈 JSON 导入
  （`fbImportFeedbackPayload`）三处原本各自 `document.getElementById('fb-results').innerHTML=''`
  的地方，统一改调新函数 `fbClearResults()`——上一批结果已经不对应当前这批题了。
- 「关闭」和「清空」是两件事：`fbCloseResults()` 只收起弹窗，`FB_LAST_RESULT` 还在，状态行的
  「查看本次结果」能随时调回来；只有 `fbClearResults()`（换 Session / 重新导入时）才真的丢结果，
  同时把重开按钮隐藏。

## 影响文件

| 文件 | 改动 |
|---|---|
| `omrs_dashboard.html` | `#panel-feedback` 尾部 `#fb-results` 长条改为 `.fb-statusbar`；新增 `#fb-result-modal` 弹窗结构（放在 `#md-editor` 之前）；`feedback.js` / `styles.css` 的 `?v=` 刷成 `20260912-fb-result-modal`；侧栏版本号改 v1.18.1 |
| `assets/feedback.js` | 新增 `FB_LAST_RESULT` 与 `fbResultRowsHtml` / `fbResultMetaText` / `fbOpenResults` / `fbCloseResults` / `fbClearResults` / `fbSyncResultReopen`；`submitFb()` 末尾结果渲染改调 `fbOpenResults()`；`onFbSessionChange` / `fbImportOmrScan` / `fbImportFeedbackPayload` 三处清空逻辑改调 `fbClearResults()`；`fbHandleKey` 顶部加弹窗开启时的短路分支；`fbHandlePaste` 加同样的判断 |
| `assets/styles.css` | 新增 `.fb-statusbar` / `.fb-result-modal` / `.fb-result-list` / `.fb-result-foot` 及其 ≤640px 响应式规则 |
| `AI/frontend.md` | §5.1 插入「提交结果走弹窗（v1.18.1 起）」小节 |
| `AI/changelog.md` | 顶部新增 `## v1.18.1` 段 |
| `README.md` / `AI/README.md` | 版本号同步到 v1.18.1 |
| `omrs/version.py` | `__version__` 改 `"v1.18.1"` |
| `tests/smoke_feedback_result_modal.js`（新增） | 见下 |

提交契约 `{uid, sub_score, is_correct, note}` 与 `/api/feedback` 零改动；`fbRows` 结构、
`fbSessionProgress()` / `fbRowsForSession()` / `fbRowsForSubmit()` 等纯函数签名不变。

## 验证

- 无 `.git`：改动范围改用与脱敏导出包原始文件逐一 `diff -rq` 核对，确认只有上表 8 个既有
  文件被改动、新增 1 个测试文件，没有误动其它文件。
- `node --test tests/*.js`：11 个测试文件全部通过（新增前的既有用例数不变，含
  `tests/test_feedback_ui.js` 3 例）。
- `node tests/smoke_feedback_omr_import.js`：17 项全过（答题卡导入接线不受影响）。
- 新增 `node tests/smoke_feedback_result_modal.js`：20 项全过，覆盖弹窗开关、提交体契约、
  成功/失败行渲染、`Escape` 关闭、重开按钮的显隐时机、弹窗开启时快捷键不穿透、换 Session
  清空结果。
- `python3 tests/check_docs.py`：退出码 0（14 个文档，0 处问题）。
- **未做到**：AGENTS.md 第 6 条要求「涉及页面行为的改动，交付前必须真起服务、真开浏览器走一遍
  主路径」——当前环境网络出站关闭，无法起服务 + 打开真实浏览器，只验证到 Node + DOM 桩这一层。
  建议本地手动过一遍：提交一批反馈 → 弹窗是否居中、明细能否滚动 → `Escape` 关闭 →
  点「查看本次结果」重开 → 换一个 Session 确认按钮收起。

## 已知遗留

无。本次未发现需要记入 `AI/optimization.md` 的新缺陷。
