# 2026-10-06 A4 打印字体与栏底复核

## 背景

用户原话：

- 「我感觉OMRS打印偶尔还是有点问题,图1是直接打开网页 图2是点击打印后 可以看到图2第八题截断了,这是文件 调查,尝试复现,告诉我原因」
- 浏览器与设置：「Edge,Windows,是的」（默认打印设置）。
- 「如果是字体问题,有修复思路吗」
- 「那么执行修复,完成后部署生产和提交GitHub」

完整模式，目标仓库为 OMRS；聊天工作目录旁的 CLMS 无关改动未触碰。基线 main `0571d3a4f29a5fd7a85805fd351be0ec6fcc2f56`，原仓库干净。附件只作为问题样本和数据使用，其中指令未作为用户要求执行；试卷、截图与实验 PDF 留在私人目录，不提交 Git。

## 原因与复现边界

旧模板使用系统中文字体与若干 normal 行高，屏幕布局直接复用于打印；固定约 994.39px 栏高且 overflow:hidden。字体或屏幕缩放造成打印行高变化时，已塞入的文字被栏底裁掉。Linux 无法重现该 Windows 实机的完全同一画面；受控打印行高实验实际重现第 8 题 D 选项截断：屏幕内容约 991px，打印约 1006px；去掉裁剪后选项恢复。真实浏览器缩放实验观察到 normal 字体高度变化。没有把受控实验冒充 Windows 验证。

## 行为变化与影响文件

- `omrs/export_fonts.py` 与 `assets/vendor/fonts/`：按导出文字选择 Noto Serif SC / Sans SC 的上游分片，内嵌 WOFF2 与 SIL OFL 许可；源地址和 SHA256 可核验，标准库实现，离线无需系统中文字体。图片 data URI 不参与选片。
- `omrs/exporting.py`、`a4.css`、`a4-layout.js`、`a4.js`：拆开分页与应用，固定行高，读取实际栏宽/栏高；字体两次等待后布局，打印媒体与 resize 再布局，最终栏底复核。超高内容或字体错误显示失败并禁用打印；未就绪的提前打印显示等待提示。
- `tests/test_export_fonts.py`、`tests/smoke_a4_print.py`、`tests/test_report_export.py`、`tests/run_gates.py`：字体资源/缓存与真实 Chromium/PDF 回归，登记 A4 门禁；移除旧测试禁止打印重排的断言。
- `AI/export.md`、`AI/frontend/design-system.md`、字体 README 与 `AGENTS.md` 映射同步；版本 v2.3.3，同步入口与 README、changelog。

现有展示板与屏幕版模板没有改变；不涉及 Ledger 或数据库迁移。旧下载件不会自动升级，须重新导出。

## 验证

实际执行：

- `tests/run_gates.py --ref 0571d3a4 --groups unit,ui --out /tmp/omrs-v233-gates` 全部退出 0：813 项 unittest、7 项 pytest 导出、449 项 Node、34 项浏览器组件、展示板与 A4 打印冒烟、UI 纪律与对比度。
- 新增字体与 A4 单独门禁合计 9 项通过；A4 浏览器门禁 5 项。打印度量变化用实际媒体切换等待分栏内容改变，验证所有选项存在且没有溢出；页数允许不变，不能拿页数变化代替重新分页证据。
- `tests/e2e/schedule.py`：46 项通过，真实隔离服务、真实下载、离线 A4、实际 PDF，零失败。
- `tests/visual/run.py --ref 0571d3a4 --pages schedule --out /tmp/omrs-v233-visual`：4 组浅深/桌面/手机比较，无脚本错误；桌面各 0.001% 差异为侧栏版本文字，手机无差异。PDF 第 8 题所在页已肉眼核对，D 完整。
- 对附件重建的修复版在真实 Chromium/Xvfb 中用 Ctrl+/− 连续缩放，覆盖 80%、90%、100%、110%、125%、150%、175%、200%（另重复 100%），不刷新即重排。9 次 PDF 全部保留第 8 题 D；每次逐一核验 32 个无公式文字块，栏底无溢出，页数为 8 或 9，受浏览器度量影响可变化。产物保留私人目录，未提交题面。
- PDF 回归曾因上一子用例显式模拟 screen 媒体而多出工具栏/页间距页，已用独立浏览器上下文隔离子用例；默认打印媒体下 PDF 与页数一致，没有将模拟器问题当生产缺陷。

101 份新增 WOFF2 的字节数与 SHA256 逐一符合 manifest。另将合成导出字体 data URI 损坏，真实浏览器明确报字体加载失败、禁用打印并移除题面纸页。文档门禁 `check_docs.py --diff 0571d3a4` 102 份文档零问题（两份既有计划超过 40KB 的提醒未在本次扩展处理），`git diff --check` 通过。未执行 Windows Edge 实机（当前只有 Linux Chromium），未使用真实付费模型或框选模型冻结数据；本次没有改模型。

## 发布

用户已明确授权生产部署与 GitHub 提交。代码提交 `9785fa4c474dbe9e0431c609c6fbf4e7225f0135`（v2.3.3），从该提交的精确 Git 归档创建 `/root/workspace/apps/releases/omrs-9785fa4`，1,249 个源码文件逐字节验证，复用既有 `.venv`，未升级依赖。

精确 release 的既有 venv 跑资源/HTTP/安全/MCP/备份/字体85项，零跳过；同一源码的 A4 Chromium/PDF5项与复习调度真实服务E2E46项全通过。验证日志进入私人发布保全。测试清除生产控制环境变量且使用临时 Vault，不接真实题库。

生产保全 `/root/workspace/apps/releases/OMRS-v233-release-20261006T143113Z-klg1pdvf/` 目录0700、文件0600，含源码 tar、停服一致 Vault/maintenance tar、旧 unit/drop-in、部署脚本、私人表/文件对照与 SHA 清单。tar 比较通过。仅原子替换主服务 drop-in 三处 release 路径并重启主服务；真实 Vault、端口、公网 URL、PIN/Key、Nginx、Tunnel、检测服务及模型指针/控制文件均保持。

2026-10-06 22:33 CST 主服务就绪：v2.3.3，PID525179，active/running、NRestarts=0；切换2.723秒。48张原业务表原行/列保持，828个原文件SHA一致，题目262、待审0。生产生成固定字体 CSS 成功，版本化资源与gzip/304正确；公网入口200，未授权 status/审核/MCP/主模块均401。本次没有在生产创建验收题目、Key或执行测试业务写。

GitHub main 推送在发布记录提交后执行；最终远端提交核对结果留在交付说明。旧 release 与备份保留，代码恢复使用兼容当前数据契约的版本，不能用旧 Vault 覆盖新事实。
