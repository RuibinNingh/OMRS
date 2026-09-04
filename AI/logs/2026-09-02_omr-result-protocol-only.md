# 2026-09-02 OMR 剪贴板仅接受 `/result` 顶层协议

## 变更摘要

- OMR 剪贴板导入只接受 `GET /api/v1/recognitions/{id}/result` 的顶层对象：`recognition_id/template_id/mode/status/questions/unresolved`。
- 明确拒绝旧原始识别记录 `items`、裸数组、包装层和缺少 `unresolved` 等字段的不完整形态；错误信息直接提示正确端点。
- OMRS mode 读取 `questions[].result`（C/W）与 `questions[].level`（0–10）；Anki mode 保留 `questions[].answer` → OMRS 对错/评分映射。
- 任一 `unresolved` 命中的题均不自动填写，即使 `questions` 同时带值也不覆盖；字段名与状态写入 `OMR：` 备注，转人工处理。
- 原反馈 JSON（屏幕版 / AI 的 `omrs-feedback`）导入路径保持不变。

## 行为与兼容性

旧 raw/items 协议不再兼容。用户必须在 OMR 识别详情页点击「复制结果 JSON」，或直接取得 `/api/v1/recognitions/{id}/result` 响应。`failed`、`uploaded`、`queued`、`processing` 状态仍拒绝导入；`needs_review` 可导入，但 unresolved 题全部进入人工处理。

## 修改文件

- `assets/feedback.js`：改为严格识别 `/result` 顶层协议；删除 raw/items 证据解析与字段类型猜测；实现 OMRS/Anki 结论映射及 unresolved 阻断。
- `omrs_dashboard.html`：更新按钮说明、导入指引、警告、示例和 `feedback.js` 缓存串。
- `tests/test_omr_import.js`：切换到正式 `/result` 夹具，覆盖 OMRS、Anki、unresolved、旧协议拒绝、状态与 Session 映射。
- `tests/smoke_feedback_omr_import.js`：端到端桩改用 `/result`，验证 unresolved 与旧 items 拒绝。
- `README.md`、`AI/frontend.md`：同步唯一支持的协议和兼容性边界。
- `AI/logs/log.md`：增加本日志索引。

## TDD 记录

依次看到预期 RED 后才实现：正式 `/result` 起初报“需要 items”；Anki answer 起初全部保持未判定；unresolved 起初仍自动填值；旧协议拒绝测试起初拿不到 error；失败/处理中状态起初未拒绝。旧 smoke 夹具在切换实现后出现 10 项失败，改为正式协议夹具后恢复全绿。

## 验证

```text
node --check assets/feedback.js
node --test tests/test_omr_import.js
# 11 pass / 0 fail

node tests/smoke_feedback_omr_import.js
# 17 项全部通过

node --test tests/test_feedback_ui.js tests/test_question_suspend_frontend.js
# 4 pass / 0 fail

node tests/smoke_frontend_actions_catalog.js
# 全部通过

PYTHONPATH=. uv run --with pytest python3 -m pytest tests -q
# 31 passed in 0.24s
```

未重启生产服务。

## 同步过的文档

`README.md`、`AI/frontend.md`。
