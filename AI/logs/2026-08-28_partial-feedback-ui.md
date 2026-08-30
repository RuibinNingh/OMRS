# 2026-08-28 分批反馈交互优化

## 变更摘要
- 为 Session API 增加已录入 / 待录入进度字段，并按 Session 原始顺序去重。
- 反馈页选择 Session 时自动只显示尚未录入反馈的题目。
- 提交后保留当前 Session，刷新并自动载入剩余题目；完成后明确提示无需重复提交。
- 反馈 JSON 导入自动跳过已录入 UID，并对重复或空 UID 阻止提交。
- 版本更新为 v1.8.1。

## 行为与兼容性
- `GET /api/sessions` 与 `GET /api/session` 新增 `feedback_uids`、`pending_uids`、`feedback_count`、`pending_count`、`feedback_complete`；原字段保持不变。
- 手动反馈模式仍可通过「添加行」使用；旧 Session 数据和旧格式 UIDs 均兼容。
- 未修改 Ledger / CSV 格式；进度由现有历史投影计算。

## 修改文件
- `omrs/sessions.py`
- `assets/feedback.js`
- `assets/schedule.js`
- `assets/styles.css`
- `omrs_dashboard.html`
- `omrs/version.py`
- `README.md`
- `AI/README.md`
- `AI/api.md`
- `AI/frontend.md`
- `tests/test_sessions_feedback.py`
- `tests/test_feedback_ui.js`

## 验证
- `python3 -m unittest tests.test_sessions_feedback -v`：2 passed。
- `node --test tests/test_feedback_ui.js`：2 passed。
- `node --check assets/feedback.js && node --check assets/schedule.js`：通过。
- 生产服务未重启；当前只完成源码与隔离测试，需浏览器刷新后由用户现场确认 UI。
