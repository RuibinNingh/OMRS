# 2026-08-14 审计偏差修复（文档-代码同步）

## 背景

2026-08-13 只读审计（未留痕）发现 11 项文档与代码偏差（P1 行为 2 项、P2 文档过时 5 项、P3 小缺口 4 项）。本任务逐项修复。

## 变更摘要

### 行为修复

1. **`/api/feedback` 响应 `new_due_date`/`new_interval` 与投影器对齐**（`omrs/feedback.py`）：
   - 此前 `new_due_date` 返回的是反馈前的旧到期日（CSV 行值），前端结果行展示的 Due 是旧值。
   - 现改为与 `projections.py::_apply_single_review` 同一口径：`new_interval` 用更新后的 EF（`update["ef"]`）计算，`new_due_date = compute_due_date(反馈发生日, new_interval)`。
2. **录入图片格式限制**（`omrs/creation.py`）：`_MIME_EXT` 移除 WebP/BMP；`_save_pasted_images()` 对不支持格式直接抛 `ValueError("不支持的图片格式 …（仅支持 PNG/JPEG/GIF）")`，与 `/api/image` 与导出的 `_read_image_info()` 支持范围一致（此前 WebP/BMP 可落盘但无法被图片服务读取）。
3. **移除死代码**：
   - `omrs/feedback.py`：删除无调用的 `_writeback_md()` / `_update_frontmatter_tags()` / `_normalize_tags()` 及 `os`/`re` 导入、`STATUS_ATTACKING`/`STATUS_KILLED`/`TRAP_TAG` 常量（v1.1.0 Ledger 架构后标签转移由投影器 `_apply_single_review()` 实现）。
   - `assets/core.js`：删除无 UI 入口的 `getScheduleRecommendation()` / `renderScheduleRecommendation()` / `applyRecommendedScheduleCount()`（依赖的 `#sch-subject`/`#sch-count`/`#sch-recommend-note` 元素不存在），并从 `populateFilterOptions()` 移除 `'sch-subject'`。
   - `assets/schedule.js`：删除 `createSession()`（旧「新建 Session」流程，`POST /api/schedule` 端点保留兼容），`refreshSessions()` 不再调用 `renderScheduleRecommendation()`；Session 列表空态文案改为「点击上方「开始常规复习」创建」。
   - `assets/app.js`：`reloadData()` 不再调用 `renderScheduleRecommendation()`。
   - `omrs/reports.py`：删除无调用的 `_ID_RE` 与 `_valid_id()`（及 `re` 导入）。
4. **CSS 重复定义收拢**（`assets/styles.css`）：删除 v1.4.2 遗留的 `.instant-queue`（55vh）定义，保留 v1.5.0 的 62vh 段。

### 文档同步

5. `AI/algorithm.md` §4：改为描述当前行为——标签击杀/回退由投影器 `_apply_single_review()` 重放实现；Markdown `tags` 不再被反馈回写，YAML 仅作输入（外部改动走 `question.metadata_update_external`）。
6. `AI/frontend.md`：
   - §3 圆角数值改为实际值 `--radius:14 / -sm:10 / -lg:20`；
   - 新增 v1.6.0 版本注记（单题删除、Ledger 时区、调度页双按钮、侧栏版本号）；
   - 文件组织 schedule.js 描述去掉「创建」；
   - §4 入口双按钮改为「开始常规复习」+「导出」，说明 TMP- 批次的两条产生路径与旧入口移除；
   - §6 自定义练习操作改为导出面板操作（函数名对应）；
   - §6 表格 TMP 的 SM-2 行更正：反馈同样更新 Interval/Due_Date（无 Session 来源按 `due`，可逐题传 `source`）；
   - v1.2.0 注记 `.bar-fill.*` 改纯色的说法更正为实际的 accent 渐变（`linear-gradient` 段覆盖早期纯色）。
7. `AI/api.md`：
   - `/api/analytics` 分组表补 `generated_at` 与 `forecast` 的 `"7+"` 键；
   - `/api/create` 图片命名表改为实际 `<uid>-<omrs_id 短后缀>-q/a-N.<ext>`。
8. `AI/data.md`：§5 录入说明图片命名同步短后缀；§7 日志路径改为 `<vault>/logs/omrs_YYYY-MM-DD.log`（标准启动 vault=仓库根）。
9. `AI/optimization.md`：CSS 重复定义债条目补记 2026-08-13 收拢 `.instant-queue`。

### 数据清理

10. 删除 2026-08-01 误用 vault 的遗留：`错题/错题/`（含 0 题的空白 bootstrap `.omrs`：ledger.db、空 CSV、`legacy_backup/20260801-141439`）与 `错题/logs/omrs_2026-08-01.log`（INDEX total 0 的误运行日志）。真实运行日志在仓库根 `logs/`，不受影响。

## 修改文件

- `omrs/feedback.py`
- `omrs/creation.py`
- `omrs/reports.py`
- `assets/core.js`
- `assets/app.js`
- `assets/schedule.js`
- `assets/styles.css`
- `omrs/export_templates/screen.js`（数据形状注释 `answers:[{idx,uid,blocks}]`）
- `AI/algorithm.md`、`AI/frontend.md`、`AI/api.md`、`AI/data.md`、`AI/optimization.md`
- `AI/logs/log.md`（本日志索引）
- 删除：`错题/错题/`、`错题/logs/omrs_2026-08-01.log`

## 验证

- `python -m pytest tests/`：16 passed。
- `python -m py_compile omrs/feedback.py omrs/creation.py omrs/reports.py`：通过。
- `node --check assets/core.js assets/app.js assets/schedule.js omrs/export_templates/screen.js`：通过。
- 临时 vault 实测（`$TEMP` 下脚本，已清理）：首次高分答对 → 响应 `new_interval=6`、`new_due_date=发生日+6`，与 `rebuild_projection()` 的 `mastery_projection` 完全一致；答错 → 重置 `interval=1`、到期日=发生日+1；`verify_ledger()` valid；WebP data URL 被 `ValueError` 拒绝。
- 服务重启后 `/api/status`、`/api/ledger/verify`、`/api/scan` 正常（若在本次会话内重启）。

## 同步过的文档

- `AI/algorithm.md`、`AI/frontend.md`、`AI/api.md`、`AI/data.md`、`AI/optimization.md`
- `AI/logs/log.md`
