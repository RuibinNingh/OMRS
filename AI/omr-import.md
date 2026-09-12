# 答题卡扫描 JSON 导入（OMR → 反馈页）

> 从 `frontend.md` §5.1.1 拆出（v1.16.1）。对应源文件：`assets/feedback.js`（`omrReadSheet` / `omrApplyToRows` / `omrMergeNote` / `fbPayloadKind`）、`tests/test_omr_import.js`、`tests/smoke_feedback_omr_import.js`。后端 `/api/feedback` 零改动。

纸面复习的闭环原本断在「批改结果怎么回到 OMRS」：要么手工逐题点，要么把结果口述给 AI 让它拼反馈 JSON。v1.11.0 接上答题卡扫描项目（OMR）的正式结果输出——扫完卡在识别详情页复制 `/api/v1/recognitions/{id}/result` JSON，回本页读剪贴板，逐题自动落到判定面板上。

**全部在前端完成**，`/api/feedback` 与提交体 `{uid, sub_score, is_correct, note}` 零改动。

## 题号 → UID 的对应关系

答题卡上只有题号，没有 UID。唯一的对应依据是**当前 Session 的题目顺序**：OMR 的 `seq N` ↔ `sessionUniqueUids(session)[N-1]`，与 `omrs/exporting.py` 打印「第 N 题 [UID]」时用的 `enumerate(questions, 1)` 是同一个口径。因此**没选 Session 就直接拒绝导入**，不做任何猜测。

已知边界：导出答题卡之后再停用某道题，`list_sessions` 会把它从 `uids` 里滤掉，其后所有题号整体前移，纸面与 Session 不再对齐。UI 与导入面板都写明了这一点，中栏题面就是核对手段。

## 唯一接受的 OMR JSON 形态（`omrReadSheet`）

OMR 剪贴板导入只接受 `GET /api/v1/recognitions/{id}/result` 返回的**顶层对象**：

```json
{
  "recognition_id": 12,
  "template_id": "omrs-2col-normal-30q-tm-v2",
  "mode": "omrs",
  "status": "ready",
  "questions": [{"seq": 1, "page": 1, "result": "C", "level": "9"}],
  "unresolved": []
}
```

六个顶层字段 `recognition_id/template_id/mode/status/questions/unresolved` 必须齐全，`questions` 与 `unresolved` 必须是数组。旧的完整原始记录 `{id,status,template_id,items:[...]}`、详情页 `detail_json`、裸 `items` 数组、`{recognition|record|result|data: ...}` 包装层和扫描记录列表都明确拒绝；错误信息会要求回 OMR 识别详情页点击「复制结果 JSON」。OMRS 不再读取 `raw_value/result_status/manual_value/darkness`，也不再按选项集合反推字段种类，证据到结论的规则只留在 OMR 的 `service.result_export`。

## 逐题判定规则

- **OMRS mode**：直接读取 `questions[].result`（`C/W`）与 `questions[].level`（字符串 `0`–`10`）；level 为 `null` 且对应字段不在 `unresolved` 时，仍按对错给默认分 `correct?10:4`。
- **Anki mode**：保留原有 SM-2 映射，读取 `questions[].answer`（`A`=错/1 分，`H`=对/5，`G`=对/8，`E`=对/10）。
- **custom mode**：`questions[].answer` 只有选项、推不出对错，一律留给人工。
- `unresolved` 是唯一的待复核信号：只要某个 `seq` 有 unresolved 字段，该题就不自动填写；字段名与状态以 `OMR：` 前缀写进备注，进入三栏工作台人工处理。即使 `questions` 内同时出现了值，也不覆盖 unresolved。
- 任务级：`failed` 拒绝导入；`uploaded`/`queued`/`processing` 提示尚未识别完；`needs_review` 可读取，但其中 unresolved 题仍全部转人工。
- 超出 Session 题数的题号、以及本 Session 已录入过的 UID，都跳过并在状态行报告计数；全部题号都超范围时直接提示「多半选错了 Session」。

## 三个入口，一套解析

`fbImportText()` → `fbPayloadKind()` 分流 → `fbImportOmrScan()` 或 `fbImportFeedbackPayload()`。三个入口都同时接受答题卡 JSON 和反馈 JSON：

1. 顶栏「📋 读剪贴板填写」（`fbReadClipboardAndFill`，走 `navigator.clipboard.readText`）
2. 本面板内直接 `⌘`/`Ctrl`+`V`（`fbHandlePaste`，document 级监听，焦点在输入控件时让位）
3. 折叠面板里的粘贴框 +「导入 JSON」（`importFeedbackJson`）

第 2 条不是锦上添花：`navigator.clipboard` 只在 HTTPS 或 localhost 可用，局域网 `http://` 打开时按钮会失效，粘贴事件是那种情况下唯一能用的路径，两者都失败时才退回粘贴框。

解析器不依赖 core.js 的 `asNumber`（内部用 `omrInt`/`omrScore`），因此可在 node 侧单独 `require` 出来测：`tests/test_omr_import.js` 覆盖正式协议、旧协议拒绝、OMRS/Anki 映射、unresolved 与状态边界，`tests/smoke_feedback_omr_import.js` 用 vm + 最小 DOM 桩跑整条接线。
