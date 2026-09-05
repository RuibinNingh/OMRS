# 2026-09-04 展示板 / 标记 / 题库重做 + 「仅打印新增」纸面记录

## 背景

v1.14.0 的 Codex 初版（展示板 / 用户标记 / 题库重设计）不可用：展示板页永远停在
「加载展示板…」（`boardReloadData` 只 `boardLoad(id,false)` 从不 `boardRender`）；
中文板名导出直接 500（`Content-Disposition` 里的非 ASCII 触发 latin-1 编码错误）；
导出模板没有 KaTeX / Markdown 表格、按字符硬切文字、自造分页；题库新壳、抽屉、chips、
反馈页标记区的 CSS（`.qb-*` / `.fb-labels` / `.hint` / `.grow` / `.btn.ghost`）全部缺失，
页面裸露成一列未样式化的控件；`prompt()/alert()/confirm()` 贯穿所有操作；标记管理只能
`prompt`，没有色板 / 合并 UI。用户决定：右侧留白保持纯空白、纸面标题固定「错题集」，
并把 Codex 的「打印范围 / 高水位」替换成一个真正的增量打印系统。

## 决策

- **纸面记录**：`boards.json` 新增 `printed{at,pages,cursor{page,y},print,items[{question_id,uid,hash,segments}],answer_pages}`，
  描述「纸上现在有什么」；`last_printed_page` 废弃（读到即忽略）。
- **两种打印模式**：`mode:"all"` 整板从第 1 页排；`mode:"new"` 只排未进纸面记录的题，浏览器模板
  在 `cursor.page` 页顶部放 `cursor.y` 高的透明占位块（屏幕斜纹提示、打印隐藏页眉页脚），新题接着排，
  新页用绝对页码 `pages+1`；占位页没放进新题就不输出；几何沿用纸面记录；新答案排新页。
- **记录来自浏览器实测**：模板产出 `window.OMRS_LAYOUT` 并 `postMessage`；主程序「标记为已打印」
  把同一份 HTML 放进隐藏 iframe 测量 → `POST /api/board/printed`；预览窗口「已打印」走同一条路。
  服务端记题目正文指纹，之后显示「已改动」。
- **导出模板重写**：以 `a4.js` 为基础（KaTeX、公式边界拆段、表格、长图白缝切片、题头不孤行），
  加跨页「（续）」题头、题间留白贴页底不另起页、装订线 / 孔位圈。
- **前端重写**：`labels.js`（soft / solid / print 变体、picker composedPath 防误关、管理弹层色板 /
  合并 / 删除）、`qtable.js`（抽屉双滑块 + 分段按钮驱动隐藏 select、计数条快捷筛选、chips、
  列 / 密度、视图、批量条、键盘）、`board.js`（三栏、快速加入 toast 撤销 / 换板、选题对话框、
  拖拽、打印区、纸面记录、页数实测）、`questions.js`（`⋯` 菜单含迁移分类，状态去 `状态/` 前缀）、
  `core.js` 新增 `uiToast / uiDialog / uiPrompt / uiConfirm`，`styles.css` 补齐并重写 v1.14.0 段。
- 中文文件名下载：`server.py::_download` 同时给 ASCII 兜底与 `filename*=UTF-8''`。

## 改动文件

`omrs/boards.py`（重写）、`omrs/exporting.py`（展示板段重写）、`omrs/server.py`（`_download`、
`/api/board/printed`、`/printed/reset`、export `mode`）、`omrs/export_templates/board.css|board.js`
（重写）、`assets/styles.css`、`assets/core.js`、`assets/labels.js`、`assets/qtable.js`、
`assets/board.js`、`assets/questions.js`、`omrs_dashboard.html`（题库 / 展示板面板）、
`tests/test_boards.py`、`tests/test_board_export.py`、`tests/smoke_board_print.py`（新，Playwright）、
`tests/test_labels_ui.js`、`tests/test_qtable_ui.js`（新）、`AI/board.md`（重写）、`AI/export.md`、
`AI/labels.md`、`AI/api.md`、`AI/data.md`、`AI/frontend.md`、`AI/README.md`、`AI/ledger.md`、`README.md`。

## 验证

- `python -m unittest discover -s tests -p "test_*.py"`：53 通过；`tests/smoke_board_print.py`
  在无头 Chromium 下验证整板导出无溢出 / KaTeX / 长图续排，以及仅新增模式的占位页、cursor 对齐、
  绝对页码；node 测试全部通过。
- Playwright 端到端：标记筛选 chips → picker 保存 → 批量加入展示板 → 打印预览弹窗「已打印」记录
  （3 页，cursor y=712.95）→ 题库快速加入 → 仅新增估算「本次补印 1 页（第 3 页）印在原纸上」→
  隐藏 iframe 标记为已打印（7 题，cursor y=932.33）；PDF 打印输出确认占位页只出新题墨迹、
  页眉页脚隐藏，答案页为新页。

## 待办 / 提醒

- `AI/logs/log.md` 需追加索引行（脱敏源码包不含 logs 目录）。
- 若换浏览器 / 系统字体，续排可能有像素级差异，误差落在题间留白内；跨机器打印同一板前建议
  先「打印全部」重置纸面。
