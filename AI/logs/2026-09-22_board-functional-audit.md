# 2026-09-22 展示板功能性漏洞排查

## 用户诉求与范围

用户原话：「一厘米的问题发现是打印机故障,现在切换任务」「排查展示板有没有其他功能性漏洞」。据此结束页边距调查，检查预览、保存、导出、纸面记录和快捷加入的功能正确性。本任务交付排查结果，不包含功能修复或生产数据迁移。

任务开始时 Git 仅有用户既存的未跟踪 `.playwright-mcp/`，保留未动。

## 变更摘要

在 `AI/optimization.md` 集中登记 7 项已复现缺陷，包含优先级、触发步骤、实测结果、代码位置和修复方向。`AI/board.md`、`AI/frontend.md` 仅引用该清单，不重复维护问题。同步优化文档中已过时的展示板模块拆分、预览缓存和页数估算描述。

功能代码、接口、持久化格式、版本号均未变。真实展示板数据未写入；涉及写入的验证使用临时题库和独立 HTTP 服务。

## 验证方法与结果

### 既有检查

- `python3 -B -m unittest discover -s tests -p 'test_board*.py'`：42 项通过。
- `node --test tests/test_board*.js`：57 项通过。
- `python3 -B -m unittest tests.smoke_board_print tests.smoke_board_print_geometry`：8 项通过。
- `python3 -B tests/smoke_board_lock.py`：通过，覆盖锁定后加题、取消真实版式修改、补印 cursor 和透明占位；页面错误为 0。

以上绿灯不能覆盖本次新增发现的操作交错与快照问题。

### 真实浏览器复现

使用 Python Playwright 与 Chromium 151，1440×1000 视口。内置 MCP 浏览器缺少其要求的 Chromium 安装，改用环境中已可用的 Python Playwright；未安装额外依赖。

临时脚本 `/tmp/omrs_board_function_audit.py` 启动临时题库 HTTP 服务，通过真实页面函数、控件、打印窗口和记录请求验证六个场景。测试中的打印确认自动同意只用于临时题库，没有物理打印。保存/导出竞态仅延迟真实 fetch 响应（350ms / 700ms），不伪造返回数据。结果写入 `/tmp/omrs_board_function_audit.json`，六项均复现，页面脚本错误为 0。

| 场景 | 实测证据 |
|---|---|
| 答案开关 | 保存为 append；预览/记录 1 页无答案；独立导出 2 页且第 2 页为答案 |
| 保存响应迟到 | 最后输入 54%，磁盘与内存 42%，预览与控件 54% |
| 设置后立即打印 | 预览和最终保存 42%，打印窗口 50% |
| 导出期间切板 | A 的导出窗口映射到 B；B 原有「审查2」，其纸面记录却写入 A 的「审查1」 |
| 打印后改变版式再记录 | 独立窗口 50%，主页面记录 42% |
| 快捷加入后撤销 | 板原有 Q1；快捷加入 Q1、Q2；撤销后板为空 |

预览切板竞态由 `/tmp/omrs_board_race_audit.py` 在真实服务只读页面复现：旧板还在首次排版时切到另一板，将新板导出请求延迟 800ms。消息记录显示旧板的 layout 把新板置为 ready；新板最终 `body` 无 embedded，顶栏 display 为 flex。截图位于 `/tmp/omrs-board-race.png`。浏览器拦截了除只读 `/api/export` 外的非 GET/HEAD/OPTIONS 请求；脚本前后真实 `boards.json` SHA-256 相同。临时脚本、结果和截图均不纳入仓库。

## 影响文件

- `AI/optimization.md`：缺陷清单与相关当前行为说明。
- `AI/board.md`、`AI/frontend.md`：集中缺陷清单引用。
- `AI/logs/2026-09-22_board-functional-audit.md`、`AI/logs/log.md`：本次排查记录和索引。

## 文档收尾

使用 `git diff --name-status` 和 `git status --short` 复核实际改动（后者包含新增日志）；`git diff --check` 通过，`python3 tests/check_docs.py` 检查 14 个模块文档、0 处问题，退出码 0。收尾时真实 `boards.json` 的 SHA-256 仍与排查开始时相同。
