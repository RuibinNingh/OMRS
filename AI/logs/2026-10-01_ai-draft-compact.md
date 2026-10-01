# 2026-10-01 AI 草稿多块审核界面精简

## 背景

用户先要求「AI草稿页的UI还可以怎么优化」「假设是多文字分块录入呢?画一个草稿」，随后确认「可以,按照这个实现」。本次落实已确认的窄队列、宽正文、多块连续阅读示意。执行者：Codex，完整模式；基线 `bec821d`，分支 `codex/ai-draft-compact`，使用独立工作树。开工时主工作区和任务工作树均无已有未提交修改。

## 行为变化

- 队列收窄为 220px，使用紧凑列表与状态下拉；刷新、清理放入共享菜单。1440px 隔离页面正文实测宽 890px。
- 信息摘要置于正文上方，错因直接显示，字段表单按需展开；审核模式取消右侧信息栏。手机队列默认折叠，信息、题目与答案连续阅读。
- 题目和答案分组显示块数，块用小序号和轻分隔线；每次只编辑一个块，编辑文字时不重复显示预览。
- 块菜单支持同组调序、下方插入文字、移至另一组末尾和确认删除；保留块 id、图框与说明。插入立即聚焦，保存后局部编辑键及当前图片区块映射为服务端 id。
- 添加图片按需选择来源；图片说明、整图、来源预览、框选、转文字、独立训练和 MCP 原图保护保留。
- 底部统一暂存、丢弃和「入库并下一题」。格式提示与提交校验共用同一数据源，缺项可定位；通过不表示 AI 内容已人工确认。取消状态切换恢复筛选下拉值。
- 保留未保存保护、版本冲突、入库前复核、丢响应重试和已入库 / 已丢弃只读行为。

浏览器复跑暴露已有 AI 框坐标写入缺陷：`_box` 从集合构建字典，自动框选使用 `rect.values()` 绑定 SQL 的 x/y/w/h 列，进程哈希顺序不同会错写坐标并使缩放柄超出图片。用反序字典回归稳定复现后，将该写入改为显式字段取值；正文、ai_box 与同步训练框坐标保持一致。接口和数据库格式没有变化，没有处理真实草稿数据。手机筛选的浏览器辅助函数等待默认首题详情加载完成后再展开队列，避免测试点击已自动折叠的队列行。

## 影响文件

以 `git diff --name-status` 和未跟踪清单复核，均属于本任务：

- `assets/app/features/create/`：修改 `drafts.js`、`drafts-view.js`、`drafts-state.js`、`drafts.css` 和动作登记 `index.js`；新增 `drafts-review.js`、`drafts-block-actions.js`，按审核视图与块操作拆分，遵守 R8。
- `omrs/draft_detect.py`：仅修正自动框选坐标列绑定。
- `tests/app/create-drafts.test.mjs`：阅读结构、统一格式校验、插入及跨组移动的稳定身份。
- `tests/e2e/drafts.py`、`tests/e2e/drafts_p4.py`：适配状态下拉、队列菜单和手机连续阅读；检测正文坐标精确断言。
- 新增 `tests/e2e/drafts_blocks.py`：多块操作、焦点、保存重读、图文入库、只读状态与四档宽度。
- `tests/test_draft_detect.py`：坐标绑定不依赖归一化字典顺序的确定性回归。
- `tests/visual/run.py`：草稿截图自动注入相同的多块公式与合成来源图夹具。
- `README.md`、`AI/frontend/create.md`、`AI/frontend/architecture.md`、`AI/inbox.md`、`AI/drafts.md`、`AI/environment.md`：同步当前布局、数据流和验证入口。
- 本任务日志与自动生成的 `AI/logs/log.md`。

## 验证

所有 HTTP / 浏览器实例使用临时 Vault、随机高端口，启动前移除 `OMRS_SYSTEMD_SERVICE`；外部 AI 使用测试替身。

| 已实际执行的命令 | 结果 |
|---|---|
| `node --test tests/app/*.test.mjs` | 400 / 400 通过 |
| `python3 tests/app/run_browser.py` | 34 / 34 通过 |
| `python3 tests/check_ui.py` | 全仓五项计数均为 0，0 处问题 |
| `python3 tests/check_contrast.py` | 58 组对比度均通过 |
| `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/drafts_blocks.py` | 58 / 58 通过，含 320 / 390 / 1024 / 1440px、深浅主题、触摸与菜单焦点 |
| `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/drafts.py` | 55 / 55 通过 |
| `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/drafts_p4.py` | 修正坐标写入与筛选等待后，24 / 24 通过 |
| `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/create.py` | 114 / 114 通过 |
| `env -u OMRS_SYSTEMD_SERVICE python3 -m unittest tests.test_drafts tests.test_draft_write tests.test_draft_training tests.test_draft_detect tests.test_draft_p3_http tests.test_draft_p4_http -q` | 67 / 67 通过 |
| `env -u OMRS_SYSTEMD_SERVICE python3 -m unittest tests.test_inbox tests.test_ai_assist_taxonomy tests.test_ui_gates -q` | 49 / 49 通过 |
| `env -u OMRS_SYSTEMD_SERVICE python3 -m unittest tests.test_draft_detect.DraftDetectTests.test_candidate_coordinates_do_not_depend_on_dictionary_order -q` | 修复前稳定失败，修复后通过 |
| `env -u OMRS_SYSTEMD_SERVICE python3 tests/visual/run.py --ref bec821d --pages create --create-stage drafts --out /tmp/omrs-ai-draft-compact-visual-final` | 4 / 4 组截图完成，页面脚本错误、行内样式、小目标和横向溢出均为 0 |
| `python3 tests/check_docs.py --write-log-index` | 已生成索引，差异仅新增本任务条目 |
| `python3 tests/check_docs.py --diff bec821d` | 检查 77 个文档，0 处问题；3 条大文档提醒均来自本次未修改文件 |
| `git diff --check` | 退出码 0 |

Python 3.13 的部分测试输出未关闭 SQLite 连接 / 文件的 ResourceWarning，测试退出码均为 0。最终草稿与训练浏览器复跑均通过，文档和日志索引已同步。未用真实手机硬件或付费模型验收；本次触摸检查使用 Playwright 触摸环境。

## 视觉差异

对照报告：`/tmp/omrs-ai-draft-compact-visual-final/report.html`，当前截图与报告另保存在会话可视化目录的 `ai-draft-implementation/`。截图使用合成数据，基线与当前工作区共用相同夹具。

- 浅色桌面 6.152%、深色桌面 7.276%：队列收窄，右侧审核信息栏移到正文上方，块外框与所属部分下拉移除；底部操作统一。
- 浅色手机 14.037%、深色手机 14.662%：移除四标签，信息与两组正文连续显示，截图高度随完整正文增加；块操作与添加图片入口适配窄屏。
- 配色、字体和控件继续使用既有 token，没有修改全站外壳或六工作区导航。

## 交付边界

本地任务分支交付代码、测试、模块文档与日志。未执行推送、合入主分支、生产重启或部署；不访问真实 Vault。没有新增需要迁移的持久化字段。
