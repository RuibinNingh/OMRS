# 2026-09-02 答题卡扫描 JSON 回填 + 画廊预览空白修复（v1.11.0）

## 变更摘要

两件互不相关的事，合并为 v1.11.0：

1. **反馈录入接上答题卡扫描（OMR）的识别 JSON。** 流程：扫完答题卡 → 复制
   `GET /api/v1/recognitions/<id>` 的 JSON → 反馈页读剪贴板 → 按题号自动填对错与主观分。
   全部在前端完成，`/api/feedback` 与提交体 `{uid, sub_score, is_correct, note}` 零改动。
2. **修掉题目库画廊式预览顶部约 220px 的空白。** `.gallery-preview` 上给 v1.10.0 之前
   纯文本预览留的 `white-space:pre-wrap`，把 qview 结构化 HTML 里标签之间的换行也
   渲染成了空行，10 个空行几乎填满 `max-height:240px` 的预览框。

## 行为与兼容性

### 答题卡导入

- **题号 → UID 只认当前 Session 的题目顺序**：OMR 的 `seq N` ↔
  `sessionUniqueUids(session)[N-1]`，与 `omrs/exporting.py` 打印「第 N 题 [UID]」用的
  `enumerate(questions, 1)` 同一口径。**没选 Session 直接拒绝导入**，不做任何猜测。
  已知边界：导出答题卡之后再停用某题，`list_sessions` 会把它从 `uids` 滤掉，其后题号
  整体前移，纸面与 Session 不再对齐；UI 文案与导入面板都写明了，中栏题面是核对手段。
- 接受的复制形态：完整识别记录、详情页内嵌 `detail_json`（**没有 `field`**，按选项集合
  反推行的种类）、裸 items 数组、`{recognition|record|result|data:{...}}` 包一层；
  列表接口 `/api/v1/recognitions` 会被识别出来并提示去打开单条记录。
- 版式：OMRS（`qN_result` C/W + `qN_level` 0–10）、Anki（E/G/H/A 按 SM-2 口径映射，
  A=错/1 分，H=对/5，G=对/8，E=对/10）、通用 A/B/C/D（纸面只有选项、推不出对错，
  全部留给人工）。
- `manual_value` 优先于机器读数；空字符串表示人工判为空白。
- **不做静默降级**（与 OMR 项目 `decisions/0004` 同一原则）：`blank` / `multi_marked` /
  `ambiguous` / `invalid` / `pending` 一律不猜对错，只建行并把原因以 `OMR：` 前缀写进
  该题备注。扫描没覆盖到的题保持 `correct=null`，`fbRowsForSubmit()` 本来就不提交它们。
- 任务级：`failed` 拒绝并回显 `error_message`；`uploaded`/`queued`/`processing` 提示
  尚未识别完；`needs_review` 照常导入但提示去 OMR 纠错后重新复制。
- 超出 Session 题数、以及本 Session 已录入过的 UID 都跳过并在状态行报计数；全部题号
  都超范围时直接提示多半选错了 Session。
- 三个入口共用一套解析（`fbImportText` → `fbPayloadKind` 分流）：顶栏「📋 读剪贴板填写」、
  面板内 `⌘`/`Ctrl`+`V`、折叠面板里的粘贴框。三者都同时接受答题卡 JSON 与旧的反馈 JSON。
  保留粘贴事件入口是必要的：`navigator.clipboard` 只在 HTTPS 或 localhost 可用，
  局域网 `http://` 打开时按钮会失效。
- **兼容性**：`importFeedbackJson()` 函数名与行为保留（内部拆出
  `fbImportFeedbackPayload()` 返回 `{ok, message}`）；屏幕版与 AI 反馈 JSON 路径不变。

### 画廊预览

- `.gallery-preview .qv{white-space:normal}` 只关掉 qview 子树继承来的 `pre-wrap`；
  正文自己的 `.qv .q-md` 单独声明了 `white-space:pre-wrap`，直接命中元素优先于继承，
  题目里的换行照常保留。
- `recommend.js` 的画廊仍走 `renderMdContent()` 老路径、DOM 里没有 `.qv`，不受影响，
  其容器上的 `pre-wrap` 保留原样。
- 顺带修同一处的另一个 bug：`[data-theme="dark"] .qv .q-md`（三个类）权重高于
  `.qv-bare .q-md`（两个类），把 `bare:true` 本应去掉的底色又加了回去，缩略卡看起来
  像「卡中卡」。

## 修改文件

| 文件 | 改动 |
|---|---|
| `assets/feedback.js` | 新增答题卡 JSON 解析段（`omrTemplateMode` / `omrFieldInfo` / `omrLineKind` / `omrItemRead` / `omrExtractRecord` / `omrReadSheet` / `omrApplyToRows` / `omrReportHtml`）与导入入口（`fbPayloadKind` / `fbImportOmrScan` / `fbImportAnyJson` / `fbImportText` / `fbReadClipboardAndFill` / `fbHandlePaste`）；`importFeedbackJson` 拆出 `fbImportFeedbackPayload`；补 document 级 `paste` 监听；快捷键提示加一项；`module.exports` 增加解析函数供单测 |
| `assets/styles.css` | 新增 v1.11.0 段：`.gallery-preview .qv{white-space:normal}`、`[data-theme="dark"] .qv-bare .q-md{background:transparent}`、`.fb-import-warn` 与 `code`/`kbd` 样式 |
| `omrs_dashboard.html` | Session 栏加「📋 读剪贴板填写」按钮；导入折叠面板改写（答题卡 / 屏幕版 / AI 三条路径 + 注意事项 + 新 placeholder）；版本号与 `styles.css`/`feedback.js` 的缓存查询串 |
| `omrs/version.py` | `v1.10.0` → `v1.11.0` |
| `README.md` | 当前版本；功能表新增「答题卡回填」一行 |
| `AI/frontend.md` | 顶部 v1.11.0 摘要；§2.2 末尾新增「画廊缩略预览与 `white-space`」；§4 画廊式补一行交叉引用；§5.1 标题与布局图、快捷键；新增 §5.1.1「答题卡扫描 JSON 导入」 |
| `AI/optimization.md` | 测试覆盖清单补两个新测试文件 |
| `AI/README.md` | 「当前版本」由过时的 v1.8.2 更新为 v1.11.0 |
| `tests/test_omr_import.js` | **新增**，`node:test`，16 例 |
| `tests/smoke_feedback_omr_import.js` | **新增**，vm + 最小 DOM 桩，17 项检查 |

后端 Python 除 `version.py` 外一行未改。`assets/qview.js`、`questions.js`、`export.js`、
`recommend.js` 未改。

## 验证

```
node --test tests/test_omr_import.js                  # 16 pass / 0 fail
node --test tests/test_feedback_ui.js                 #  3 pass / 0 fail（原有，未回归）
node --test tests/test_question_suspend_frontend.js   #  1 pass / 0 fail
node tests/smoke_feedback_omr_import.js               # 17 项全部通过
node tests/smoke_frontend_actions_catalog.js          # 全部通过
PYTHONPATH=. python3 tests/test_*.py                  # 8 个文件全部通过
```

夹具的 `field` 名与选项集合不是手写的：用答题卡项目的 `omr/geometry.py` 实跑
`layout()` + `sample_fields()` 生成三种版式，确认 `q1_result`(C/W)、`q1_level`(0–10)、
anki 的 `q1`(E/G/H/A)、通用 `q1`(A/B/C/D) 与解析器的假设一致。

画廊空白的诊断做了两侧交叉验证：一侧在用户截图上按像素量——五张内容完全不同的卡片
（纯文字 / 带公式 / 带图 / 图加载失败）预览框内首个墨迹像素行都精确落在同一位置，
说明空白是结构性的；另一侧把 `qvHtml()` 在 `QV_CARD_OPTS` 下的真实输出打出来数空白
文本节点，得到 10 个空行 × 22.3px ≈ 223px，与像素测得的「标签上方 ≈ 89px（4 行）」
吻合。**样式改动本身没有自动化测试**（无浏览器环境），需人工在题目库画廊页复核。

## 同步过的文档

`AI/frontend.md`、`AI/optimization.md`、`AI/README.md`、根 `README.md`。
本日志需在 `AI/logs/log.md` 增加一行索引。
