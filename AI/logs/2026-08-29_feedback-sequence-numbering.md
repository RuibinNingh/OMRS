# 2026-08-29 分批反馈序号修复

## 变更摘要
修复反馈录入页在分批录入 Session 时序号重新从 1 开始的问题。待录入行现在保留其在 Session 原始题目列表中的 1-based 序号；渲染时优先按当前 Session 的 UID 位置解析，手动录入或无法匹配 Session 的行仍使用批次序号作为回退。

## 行为与兼容性
- 不改变 `/api/feedback` 请求体、Session 数据格式或提交逻辑。
- 已录入题目被过滤后，第二批及后续批次显示原始序号（例如原题目第 2、4 题显示为 2、4）。
- JSON 导入、手动添加行和旧的临时行对象仍可显示，无法映射原始 Session 位置时回退为行序号。

## 修改文件
- `assets/feedback.js`：增加 Session UID→原始序号映射，并在行徽标及无障碍标签中使用稳定序号。
- `tests/test_feedback_ui.js`：增加分批待录行序号回归断言。
- `omrs_dashboard.html`：递增 `feedback.js` 资源查询参数，确保浏览器加载修复后的脚本。
- `AI/frontend.md`：记录反馈序号按 Session 原始顺序显示的行为。
- `README.md`：补充复习 Session 支持分批反馈及稳定序号。

## 验证
- `node --test tests/test_feedback_ui.js`：3 个测试全部通过。

## 同步过的文档
- `AI/frontend.md`
- `README.md`
