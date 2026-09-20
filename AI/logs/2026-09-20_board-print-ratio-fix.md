# 2026-09-20 展示板打印比例与续印纸面快照修复

## 变更摘要

修复展示板打印新增时左右栏比例被当前设置覆盖的问题。浏览器模板在每次排版完成后把实际采用的 `PRINT_STATE` 写入 `window.OMRS_LAYOUT.print`；整板记录优先保存这份快照，增量记录继续保留原纸面的 `printed.print`。因此，已打印并锁定为 50% 的纸面在新增题补印、预览刷新和打印媒体查询中继续保持 50%。

同时修正一份用户确认的纸面记录：板 `BD-20260908-c39c2e` 当前设置为 `note_ratio=0.50`，但原 `printed.print.note_ratio=0.42`；备份原文件后仅将该字段改为 `0.50`，保留 `cursor`、题目段、正文指纹、页数和其它 JSON 值。

## 行为与兼容性

- `mode:"new"` 从纸面记录读取 `note_ratio / gap_lines`，宿主当前设置不能覆盖原纸几何；未锁定板已有的自定义比例不会被批量迁移。
- `mode:"all"` 记录时采用模板回传的 `layout.print`；旧版导出件没有该字段时回退当前板设置。`mode:"new"` 追加题目时保留已有 `printed.print`。
- 既有锁定板仍可添加、移除、排序和调整未打印题留白；真实影响已印区域的版式变化继续走确认与重印流程。

## 修改文件

- `omrs/export_templates/board.js`：排版结果增加 `layout.print`；增量实时重排固定使用原纸几何。
- `omrs/boards.py`：整板记录采用实测版面快照，增量记录保留原纸快照并兼容旧协议。
- `tests/test_board_export.py`：覆盖实测比例、增量保留和旧协议回退。
- `tests/smoke_board_print_geometry.py`：新增隔离 HTTP + Chromium 的比例与续排验收。
- `AI/api.md`、`AI/board.md`、`AI/data.md`、`AI/export.md`、`AI/frontend.md`、`README.md`：同步打印快照、续印几何和用户可见行为。
- `AI/logs/log.md`：增加本任务索引。

生产数据备份位于 `/root/workspace/apps/releases/OMRS-board-print-ratio-20260920-124742/boards.json.before`，修复记录位于同目录 `repair.json`。这两份文件不属于仓库源码包。

## 验证

- `python3 -B -m unittest discover -s tests -p 'test_board*.py'`：42 项通过。
- `node --test tests/test_board*.js`：57 项通过。
- `python3 -B -m unittest tests.smoke_board_print_geometry`：1 项通过。
- 原有 `tests.smoke_board_print` 的 7 项打印冒烟和 `tests/smoke_board_lock.py` 通过。
- `python3 tests/check_docs.py`：退出码 0；`git diff --check`：通过。
- 生产服务恢复后 HTTP 200。只读页面验收中，全部模式 16 题、仅新增模式 5 题，内嵌预览、独立打印窗口和 `print` 媒体栏宽均为 `347.047px`（比例 0.50）；增量从第 12 题、第 5 页 `top=486.25` 的旧 cursor 续排，状态保持锁定，纸面为 11 道已印题 + 5 道新增题，页面错误为 0。
- 修复前后生产验收读取期间 `boards.json` 哈希不变；数据修复前已完成备份，深比较确认除目标板 `printed.print.note_ratio` 从 `0.42` 改为 `0.50` 外没有其它 JSON 差异。

## 同步过的文档

`AI/api.md`、`AI/board.md`、`AI/data.md`、`AI/export.md`、`AI/frontend.md` 和根 `README.md` 已同步当前行为；未升级版本号，也未改写历史任务日志。
