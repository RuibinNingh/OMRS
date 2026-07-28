# 2026-07-28 Ledger 时间线时区显示

## 变更摘要

- 增加 Ledger 提交时间的前端格式化：带 UTC/时区偏移的 `created_at` 会转换为所选显示时区。
- 设置页新增时区选择，默认跟随浏览器；可选中国标准时间、UTC 和常用跨区时区。
- 历史时间线、修正记录和仪表盘「最近动态」统一使用同一格式化逻辑。

## 行为与兼容性

- Ledger 仍以 UTC 写入；不改变数据库、提交哈希或 API 返回值。
- 时区设置只写浏览器 `localStorage('omrs-ledger-time-zone')`，立即生效且无需重启。
- 没有 `Z` 或 `±HH:MM` 时区偏移的旧时间戳保持原有文本，避免把未知来源的本地时间错误换算。

## 修改文件

- `assets/core.js`
- `assets/history.js`
- `assets/dashboard.js`
- `assets/app.js`
- `omrs_dashboard.html`
- `README.md`
- `AI/frontend.md`
- `AI/logs/log.md`

## 验证

- `python -m unittest discover -s tests -p "test_*.py" -v`：9 项通过。
- `node --check assets/core.js`、`assets/history.js`、`assets/dashboard.js`、`assets/app.js`：通过。
- Node 运行时检查：`2026-01-01T00:00:00+00:00` 在 `Asia/Shanghai` 下显示为 `2026-01-01 08:00:00`；无时区旧时间戳保持原样。
- `git diff --check`：通过。

## 同步过的文档

- `README.md`
- `AI/frontend.md`
- `AI/logs/log.md`
