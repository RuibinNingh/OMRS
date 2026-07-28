# 2026-07-16 AI 报告提示词与可选图片材料导出

## 变更

- 报告页“创建报告”卡片新增 AI 报告提示词复制与分析数据下载入口。
- 用户可选择是否包含题目图片：关闭时下载轻量 Markdown，开启时下载 Markdown 与实际引用题图组成的 ZIP。
- 提示词根据图片选项切换约束，要求输出完整单文件 HTML、数据结论可验证；允许按需使用 HTTPS 外部字体、图表和图标资源，禁止广告/追踪，并要求依赖失败时优雅降级。
- 提示词增加编辑式数据叙事、统一视觉概念、响应式排版、图表语义、无障碍、克制动效和 A4 打印要求，以专业数据产品为视觉质量目标。
- 含图片材料只供 AI 读取；最终托管 HTML 必须继续使用 `/api/image?name=<URL编码文件名>`，禁止引用 ZIP 相对路径、`file://` 或 base64。
- `/api/export-review` 新增 `include_images=1` 查询参数，默认 Markdown 行为保持兼容。
- 报告脚本与样式资源使用 `20260716-ai-report` 版本参数，避免升级后浏览器继续复用旧缓存。
- 外部资源与视觉增强提示词更新后，报告脚本版本参数推进至 `20260716-ai-report-v2`。
- 报告页双栏改用 `.rp-layout` 响应式规则，窄屏下切为单栏，避免原内联网格覆盖移动端布局。

## 修改文件

- `omrs_dashboard.html`
- `assets/reports.js`
- `assets/styles.css`
- `omrs/analytics.py`
- `omrs/server.py`
- `tests/test_report_export.py`
- `AI/api.md`
- `AI/frontend.md`
- `AI/data.md`

## 验证

- Python 与 JavaScript 语法检查通过。
- 自动化测试覆盖无图片 Markdown、含图片 ZIP、去重、缺失图片跳过和 ZIP 路径安全。
