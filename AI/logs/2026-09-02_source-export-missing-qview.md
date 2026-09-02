# 2026-09-02 打包源码缺 qview.js 修复

## 起因

用户发现「下载脱敏源码」ZIP 里没有 `assets/qview.js`。上一任务（2026-09-01 feedback-workbench）新增了该文件，但只改了工作区，从未 `git add`；而 `omrs/source_export.py` 的导出范围是 `git ls-files`（仅已跟踪文件），未跟踪文件一律不进包。

## 根因

- `_tracked_files()` 用 `git ls-files -z` 枚举 → 新文件在 `git add` 之前不存在于该列表。
- `assets/qview.js` 与 `AI/logs/2026-09-01_feedback-workbench.md` 两个 untracked 文件被漏掉。
- 属于流程缺口而非代码缺陷：`git status` 里的 `??` 条目没有触发任何提醒。

## 变更

- `git add assets/qview.js AI/logs/2026-09-01_feedback-workbench.md` 并提交（cfdd02d）。
- 设计层面维持「导出 = Git 已跟踪文件 + 排除清单」不变：脱敏边界以版本控制为锚，新文件走正常 add/commit 流程；不引入扫描未跟踪文件的旁路（会绕过人工审查）。

## 影响文件

- `assets/qview.js`：仅 Git 跟踪状态变化（未跟踪 → 已跟踪），内容零改动。
- `AI/logs/2026-09-01_feedback-workbench.md`：同上。

## 验证

1. 库内 `create_source_export('.')`：`meta.files=137`，zip 内含 `OMRS/assets/qview.js`。
2. 服务端 `curl http://127.0.0.1:8471/api/source/export`：HTTP 200，1,288,525 bytes，138 个条目，含 `OMRS/assets/qview.js`，manifest 清单中也列出该文件。
3. `node --check assets/qview.js` 通过（提交前复验语法）。

产出：`/root/OMRS-source-sanitized-fixed.zip`（含 qview.js 的脱敏源码包，已交付用户）。

## 边界（明确没做）

未改 `omrs/source_export.py` 逻辑；未自动 add 其余 qview 任务的工作区改动（README、AI/*.md、assets/*.js 等 M 状态文件仍属上一个任务，由其后续正常收尾提交）。服务未重启（后端逻辑无变化）。
