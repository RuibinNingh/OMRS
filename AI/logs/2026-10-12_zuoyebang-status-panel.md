# 2026-10-12 作业帮服务面板状态优先重设计

## 背景

用户原话：“重设计作业帮服务面板”“画草稿”“状态，执行修复”“继续”。此前已交互展示两版草稿，用户选择状态优先。本次执行者 Codex，完整模式；实现独立网关面板，不执行旧服务接入计划中的生产发布步骤。

基线 `950925139b17a65a7746d623580cd832fac8ee21`，分支 `codex/zuoyebang-status-panel`。开始实施时面板文件没有既有改动。共享工作区另有录入页改动，期间继续变化，包括 `assets/app/features/create/`、`tests/app/create-zyb.test.mjs` 和 `tests/e2e/zuoyebang.py`；这些文件不属于本任务，保留且不纳入本次提交。

## 行为变化

- 登录默认进入服务概览：状态主提示、设备／账号／签名三个独立状态卡、账号摘要、当前服务地址与密钥摘要、最近活动。访问范围和管理员操作置于侧栏，窄屏导航移到顶部。
- 设备 JSON、手动凭据、扫码和一次性密钥使用原生弹窗，粘贴 JSON 默认折叠。主题跟随系统浅深色，图标为本地 SVG，无构建或远程依赖。
- 状态使用真实网关观察，导入后待核对；账号与签名独立确认失效。没有官方 TTL，只显示观察时间及区间；网络／协议错误保留此前成功。本地读取失败给出提示并保留快照。
- 保留现有核对、刷新、扫码手动检查／取消、密钥复制／吊销、审计筛选／分页／两类 IP、访问设置与实际预算。概览地址从当前服务目录生成，保留反代前缀；密钥存在不声称 OMRS 已连接。
- 退出、会话失效、页面离开与窗口关闭清理敏感输入。会话世代阻止旧回执恢复私密界面；窗口世代丢弃迟到密钥／二维码。生成期间关闭密钥窗口后明确提示吊销重建；关闭扫码窗口请求取消。
- 使用窗口内错误提示、原生焦点约束和 Escape，关闭后返回入口。分页读取失败保留原页与列表，下一次翻页不会跳过失败页。

后台接口、权限、私有存储格式、服务版本和发布配置没有修改。

## 影响文件

依据 `git diff --name-status` 复核本任务路径：

| 路径 | 内容 |
|---|---|
| `services/zuoyebang/zyb_gateway/assets/index.html` | 侧栏、概览、管理分区和五个弹窗 |
| `services/zuoyebang/zyb_gateway/assets/panel.css` | 双主题状态色、响应式布局、表单、焦点和弹窗 |
| `services/zuoyebang/zyb_gateway/assets/panel.js` | 真实状态投影、操作生命周期、敏感内容清理和失败恢复 |
| `services/zuoyebang/tests/browser_acceptance.py` | 四组真实浏览器行为、失败、迟到响应、布局与对比度回归 |
| `tests/e2e/zuoyebang_gateway_integration.py` | 适配弹窗、确认与候选渲染入口，核对实际前缀地址；截图显式前置对应页面 |
| `AI/frontend/zyb-panel.md`、`AI/frontend.md` | 新面板行为分册与索引 |
| `AI/zuoyebang-service.md`、`AI/frontend/architecture.md` | 独立面板与两项目验收当前契约 |
| `services/zuoyebang/README.md`、`README.md` | 用户首次操作与状态／窗口说明 |
| 本日志、`AI/logs/log.md` | 任务证据与脚本生成索引 |

## 已实际执行的验证

所有实例使用临时私有目录／Vault 和随机端口，启动清除 `OMRS_SYSTEMD_SERVICE`、`OMRS_BOXDETECT_CONTROL`；设备、官方登录／搜题边界均为合成数据。使用现有依赖环境 `/root/workspace/apps/releases/omrs-zyb-deps-20261011/.venv/bin/python`，只读取依赖，不修改生产目录。浏览器复用可信本机 CDP9222，只关闭各测试自建 context。

| 检查 | 命令／入口 | 实际结果 |
|---|---|---|
| 网关单测 | 网关目录 `python -m unittest discover -s tests -t . -v` | 52 项通过，0 失败／错误／跳过 |
| 面板浏览器 | 网关目录 `ZYB_TEST_EVIDENCE_DIR=…/browser python tests/browser_acceptance.py` | 最终 4 组通过，20.395 秒，无 pageerror |
| 双项目真实前缀联调 | `python tests/e2e/zuoyebang_gateway_integration.py --with-prefix --out …/integration` | 工作区及仅含本任务改动的干净副本均 18/18 通过；原图、真实签名解码、完整答案、人工入库、回执和吊销通过 |
| JavaScript 语法 | `node --check services/zuoyebang/zyb_gateway/assets/panel.js` | 通过 |
| Python 语法 | `python3 -m py_compile services/zuoyebang/tests/browser_acceptance.py tests/e2e/zuoyebang_gateway_integration.py` | 通过 |
| 前端纪律 | `python3 tests/check_ui.py` | 0 问题 |
| 主应用 token 对比度 | `python3 tests/check_contrast.py` | 58 组全部达标 |
| 面板实际文字与背景 | 浏览器验收浅深色 × 1280／780／390／320px × 五页 | 40 个页面状态、3261 个文本检查点，最低比值 5.14；弹窗另验，全部通过 |
| 工作区差分形式 | `git diff --check` | 通过 |
| 本任务隔离文档门禁 | `python3 tests/check_docs.py --diff 950925139b17a65a7746d623580cd832fac8ee21` | 113 份文档，0 问题，2 条既有大计划提醒；退出码 0 |

浏览器业务覆盖：未配置到导入待核对、文件／粘贴、非法 JSON 保留输入、手动凭据、核对／刷新、账号与签名独立失效、网络失败保留时间、一次性密钥复制与清空、恶意名称按字面显示、扫码手动确认／取消／终态、创建窗口关闭与退出时迟到回执、状态／密钥／分页读取失败、管理会话过期、确认取消、真实非回环访问拒绝、审计分页与两类 IP、主题布局、窗口焦点。

本次修正了浏览器发现的概览主按钮刷新后保持禁用、扫码入口临时禁用导致焦点返回丢失。双项目验收先遇到共享录入页改动使旧“渲染所选题目”按钮消失，改为选择候选并兼容显式渲染，再等待真实生成图；没有修改录入源码或放宽生成断言。两次共享 CDP 后台页截图超时后，截图前显式 `bring_to_front()`，最终全部通过。

共享工作区直接文档门禁初查失败，原因是本次日志尚未生成及另一任务的录入源码尚未同步 `AI/frontend/create.md`／`AI/inbox.md`。本任务验收使用基线的干净本地副本，仅应用上表中的本任务路径，排除他人未提交源码；日志索引仍由脚本生成，不为其它任务补写模块事实。

隔离副本位于证据目录下 `candidate-mdf52eg0`；其中另跑双项目联调的 `integration-owned/checks.json` 全部 18 项为真，确认本次提交不依赖共享工作区中尚未提交的录入改动。

提交复核发现 README 与架构文档在验收期间新增并行录入任务的段落。按段重建本任务的文档差分后，修订本地提交；仅移出这些并行段落，不覆盖工作区文件，原段落留给其所属任务提交。最终提交内容与按段隔离后的验收副本逐字节复核。

## 视觉对比

证据根目录：`/root/.codex/artifacts/omrs-zyb-panel-20261012/`，截图均不包含完整调用密钥、管理员密码或真实凭据。

- `visual-panel/report.html`：同一合成设备、有效观察和密钥元数据，对比基线与新页面；六类页面（登录、概览、账号、密钥、审计、设置）× 浅深色 × 桌面／手机，共 24 组。新面板全部无脚本错误与页面横溢。
- `browser/panel-layout-evidence.json`：四种宽度、双主题、五页文字对比度与零横溢证据；另有各操作窗口桌面和 320px 截图。
- `visual-omrs/report.html`：按仓库要求实际运行 `python tests/visual/run.py --ref 950925139b17a65a7746d623580cd832fac8ee21 --pages settings --settings-section service --settle 0 --out …/visual-omrs`；四组无脚本错误和页面横溢。

面板差异逐类解释：登录改为简洁登录卡与服务品牌；概览将旧账号表单入口换为真实状态和建议操作；账号页收起常驻导入内容并分离观察；密钥页改为列表和一次性弹窗；审计保留表格／筛选／分页，采用新外壳与间距；设置采用访问策略卡和四个真实预算格。浅色基线仍是旧暗色主题，差异 98.602%–99.897%；深色差异 5.812%–48.157% 来自上述外壳、内容、色彩与响应式布局。页面高度变化符合内容自然流动，服务端观察时间与随机端口允许差异。

OMRS 设置页四组差异仅 0.007%（桌面）／0.028%（手机），逐图裁切核实为隔离 Vault 名称 `vault-ref` 与 `vault-cur` 的不同。该页面没有本任务业务变化。

## 未执行的验证与交付边界

未验证真实官方设备／账号／搜题有效期、生产 HTTPS 入口、实体手机和 Safari／Edge。真实凭据和生产发布未获本轮授权；模拟 viewport 不等于实体设备验收。未安装依赖、改 systemd／Nginx、重启生产、推送或部署。

## 下一步

本地提交通过后的面板可供用户复核。上线须另行授权后按仓库发布规则部署；部署后由用户导入真实设备，在面板主动核对并于 OMRS 设置测试连接。
