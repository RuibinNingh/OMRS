# 2026-09-22 展示板七项完整性修复

## 用户诉求

用户原话：「全部执行修复」。范围是上一轮 `AI/logs/2026-09-22_board-functional-audit.md` 中已复现的全部 7 项问题。上一轮排查已经交付，本次修复使用独立主题日志，不改写排查记录。

## 变更摘要

1. 导出在请求前捕获板 ID、名称与模式，窗口映射和下载文件名不再读取请求返回后的当前板；纸面记录前后端均核验归属和模式。
2. 设置保存串行执行，合并响应时保留发送后产生的脏字段，继续保存到队列清空。切板、重载、导出等待保存；失败保留编辑并中止依赖动作。
3. 加题接口返回本次实际新增的 `added_uids`。普通撤销、Shift 快捷撤销和连续选板撤销仅使用该集合；快捷「换个板」只转移本次新增题目，并在目标加入成功后移除来源引用。
4. 答案与标记显示属于内容设置，保存后更新内容指纹并重新导出。几何设置仍使用 iframe 实时 relayout。
5. 打印保持同步开窗，随后等待去抖保存和在途保存完成；失败关闭占位窗口，避免导出旧版式。
6. 每个板保留其待记录导出任务。独立窗口回传自身 layout；下载 HTML 保留同份内容并在记录时测量。后续编辑不能用当前预览替换快照。导出携带正文指纹并由模板回传，防止正文在导出与记录之间变化时错记为最新版本。
7. 每份 srcdoc 注入独立 `previewToken`。请求、回传、宿主控制消息按代次隔离，并核验来源窗口、板与模式；旧消息不能使新文档提前 ready。内嵌 HTML 首屏即带 embedded，工具栏不再依赖排版完成后才隐藏。

8. 按标记同步先等待保存队列；旧打印窗口在重置纸面或切换打印范围后失效，不能回写旧快照。
9. 纸面记录服务端拒绝未知/别板/身份不一致题目、无纸面续印和越界页码；题目文件读取限制在错题目录内。

## 行为与兼容性

- `boards.json` 仍为原格式，无数据迁移。`added_uids` 仅为加题响应元数据，不持久化。
- `layout.board_id / mode` 存在但不匹配时返回 400，纸面及其历史均不写入；未知/别板题目、身份不一致、无纸面续印和越界页码同样拒绝，旧导出件缺字段时仍兼容。`layout.items[].hash` 优先保存导出时指纹，旧件缺失时回退记录时正文。
- 待记录导出任务保存在页面内存，按板隔离；当前页面刷新后不保留。独立窗口收到实际 layout 后释放对应 HTML 字符串。
- 锁定保护、增删引用与排序保留既有纸面、仅新增沿用原纸几何的规则不变。
- 前端脚本缓存串更新为 `20260922-board-integrity`；未修改版本号。真实题库及历史纸面未进行修补或迁移。

## 影响文件

- 前端：`assets/board.js`、`assets/board_picker.js`、`assets/board_preview.js`、`omrs_dashboard.html`。
- 后端与导出：`omrs/boards.py`、`omrs/exporting.py`、`omrs/export_templates/board.js`。
- 回归：`tests/test_board_integrity.py`、`tests/test_board_preview.js`、`tests/test_board_locked_incremental.js`、`tests/smoke_board_integrity.py`。
- 文档：根 `README.md`、`AI/board.md`、`AI/frontend.md`、`AI/api.md`、`AI/data.md`、`AI/export.md`、`AI/optimization.md`、本日志与 `AI/logs/log.md`。复核 `AI/README.md` 索引与摘要，无需改动。

## 验证

- JS 语法检查：`node --check` 检查三个前端修改模块，通过。
- 展示板 Python 单测：`python3 -B -m unittest discover -s tests -p 'test_board*.py'`，48 项通过。
- 展示板 JS 测试：`node --test tests/test_board*.js`，4 个测试文件全部通过；新增覆盖同板新文档、不同板/模式的迟到消息、同指纹强制刷新响应竞争、按标记同步保存顺序和旧打印窗口失效。
- 全量 unittest：`python3 -B -m unittest discover -s tests -p 'test_*.py'`，106 项通过（不含仓库中 pytest 风格用例）；有既存文件句柄 ResourceWarning，不影响通过结果。
- 全量 JS 测试：`node --test tests/test_*.js`，14 个测试文件全部通过。
- `python3 -B -m unittest tests.smoke_board_integrity tests.smoke_board_print tests.smoke_board_print_geometry`，15 项通过。
- `python3 -B tests/smoke_board_lock.py`，锁定追加、未印题留白、取消真实版式变化、补印 cursor 和透明占位检查通过，页面错误为 0。

新增浏览器测试使用临时题库、真实 HTTP 和 Chromium：答案/标记开关往返；保存响应延迟时继续编辑；切板等待保存；修改后立即打印；网络失败阻止导出与切板且恢复可重试；导出过程中切板后只记录原板；主页面记录使用独立窗口或下载的原快照；快捷撤销保留已有题；首轮排版途中切板后工具栏隐藏且单页状态生效。模拟延迟仅延后真实响应，未伪造业务数据；全部写操作在隔离题库。没有物理打印机验收。

首轮浏览器运行曾因取消导出连接打印 BrokenPipeError 服务日志，测试及页面错误检查仍通过；最终上述组合运行无该输出。MCP 浏览器所需版本未安装，全部浏览器验收使用环境中已有的 Python Playwright / Chromium。

## 服务与收尾

已执行 `systemctl restart omrs.service`，服务恢复 active。生产浏览器只读验收及文档检查结果在收尾时记录。

收尾复核补充：修正独立打印窗口的任务登记顺序，先写入 `BOARD_WINDOWS` 与当前任务表再执行
`location.replace()`，消除极快加载时版面回传早于任务登记的竞态；确认弹窗返回前再次校验
任务仍有效；同步 `AI/frontend.md`
正文签名说明，明确答案与标记开关属于组合签名；同时补上按标记同步保存队列、旧窗口
失效、纸面题目身份/页码和题目路径边界。随后再次通过 `node --check`、
展示板 Python 单测 48 项、展示板 JS 测试文件全部通过、全量 Python unittest 106 项、
全量 JS 测试文件全部通过、`python3 tests/check_docs.py`（14 个文档，0 问题）和
`git diff --check`。本机组合浏览器冒烟在此前授权运行中 15 项通过；本次受限沙箱重跑
因临时本机 socket 权限被环境拦截，未产生代码失败。最终 `git diff --name-status`
与 `git status --short` 复核通过，并保留用户已有未跟踪目录 `.playwright-mcp/`。

本次最后一轮后端改动再次执行 `systemctl restart omrs.service` 时，环境自动审批通道返回
503 并拒绝了系统级命令；未绕过权限。此前服务实例已在上一轮修复后重启并通过只读验收，
当前工作区代码和测试均已更新，部署实例需要具备系统权限时再重启加载本轮后端改动。

开始时保留上一轮排查的文档改动与用户已有的 `.playwright-mcp/`；以 `git diff --name-status`、`git status --short` 复核本轮代码、测试与文档范围。
