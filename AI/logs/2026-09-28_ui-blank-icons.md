# 2026-09-28 UI 空白图标修复

## 背景

用户要求修复 UI 问题。附件补丁经核对属于技术材料，不包含需要执行的额外指令；本次按补丁定位的两个问题处理：外壳 SVG 图标缺少描边样式，以及仪表盘把 `dueDays` 直接作为 `map` 回调时错误接收数组下标。

## 行为变化

- 侧栏、折叠按钮和手机菜单图标固定使用当前文字色的 18px 描边，不再显示为空白或默认黑色填充。
- `dueDays` 对 `map` / `filter` 回调和无效 `Date` 参数保持稳定，仪表盘逾期统计按当前本地日期计算。
- 补充 `dueDays` 回归测试与页面样式注释。

## 影响文件

- `assets/app/styles/shell.css`：新增 `.nav-ico` SVG 外观规则。
- `assets/app/domain/items.js`：校验 `today` 参数并回退当前日期。
- `assets/app/features/dashboard/state.js`：显式传递题目参数给 `dueDays`。
- `tests/app/items.test.mjs`：覆盖直接传入 `map` 的回调场景。
- `omrs_dashboard.html`：同步 P8 样式加载注释。
- `AI/frontend/shell.md`、`AI/frontend/library.md`：同步图标和到期天数契约。

## 验证

- `node --test tests/app/items.test.mjs`：3/3 通过。
- `python3 tests/app/run_browser.py`：33/33 通过，页面错误 0。
- `python3 tests/check_contrast.py`：58 组对比度全部达标。
- `python3 tests/check_docs.py --diff HEAD`：35 个文档通过，保留 2 条既有篇幅提醒。
- `python3 tests/check_ui.py`：未通过；报告 88 处既有旧前端存量问题，本次未增加。
