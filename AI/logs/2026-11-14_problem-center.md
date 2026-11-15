# 2026-11-14 问题中心隔离开发候选

> **任务**
> - 标识：problem-center
> - 状态：已交付

## 背景

用户原话与冻结边界已保存于AI/plans/problem-center/plan.md。本次执行者Codex CLI，完整模式但仅隔离开发候选；基线f50c6c3，初始git status为空。本轮委派合同禁止提交、推送、部署、接触生产与继续委派；90分钟是Hermes委派的执行预算，并非用户原话。未改版本号，当前源码仍为v2.10.0的未部署候选。

## 行为变化

新增问题页面、独立问题与错因事务、稳定多对多题目关联、Markdown与私有图片/SVG。弹窗原位快捷录因支持多次追加、修订、撤回、再次发生和输入法/草稿保护。MCP独立权限及助手confirm工具复用统一审核、CAS和原生回执，AI假设不冒充用户事实。设置服务端调度提醒，正式Session创建快照，导出单次覆盖；A4首页真实测量扣减两栏，屏幕版一次显示且离线可用。学习状态、旧Markdown与展示板导出语义不变。

## 影响文件

新增omrs/problems.py、problem_store.py、problem_assets.py、problem_review.py、schedule_banner.py，HTTP/助手/MCP适配及测试；修改统一审核、Session创建和导出模板接线。新增features/problems与domain快捷录因/Markdown，修改导航、设置和导出面板。同步模块文档、README、计划、路由、任务日志和索引。最终清单由git diff --name-status与未跟踪文件复核，保存在外部证据目录。

## 已执行验证

原始红绿证据保留在/worker/evidence：problems-red/green、ai-red/green、banner-red/green、reflections-red/green、markdown-red/green。补充边界先出现真实失败，再修复：problem-hardening-red/green（AI修改标记、关联CAS审计、审核原值），problem-confirm-red/green（用户确认须依据），problem-draft-red-2与problem-e2e-10（切换动作保护草稿），problem-paste-red与problem-e2e-10（SVG粘贴），problem-review-ui-red/green（问题审核附件接口）。

最终完整Python命令为PYTHONPATH=/workspace:/pydeps python3 -m unittest discover -s tests，实际1175项，exit 1，2失败与1错误（python-full-final.log）。2失败在HEAD=f50c6c3临时展开的原代码上独立复现（baseline-two.log）：source_export的-I子进程看不到/pydeps中的Pillow；traincontrol的HTTP测试400/202差异。1错误为test_mcp_board精确发现工具集合未包含新增10个工具，属于本次尚未收束的测试同步，不能称为基线失败。

新增和相关专项101项exit 0（problem-regressions.log）；覆盖问题、真实MCP/助手审核、独立库备份恢复、身份、题目SVG、审核、调度历史、字体、Session与学习投影。真实HTTP MCP独立测试1项exit 0（problem-transport.log），十个工具从官方SDK经回环服务和Web审核执行读回；旧Key无权。A4真实浏览器/PDF回归8项exit 0（a4-print.log）；原调度导出E2E22项exit 0（schedule-export-e2e.log）。

问题真实Chromium E2E最终32项通过，exit 0（problem-e2e-10.log与problem-e2e.json）：多对多、MD/图片/SVG重开、粘贴与拖放、输入法、失败保稿与重试、连续记录、翻题/Esc/遮罩/关闭保护、修订撤回、390px、设置写入、危险SVG HTTP拒绝、审核UI、单双栏打印、离线、无横幅零占位及原有几何。截图全部为合成演示题。

node --test tests/*.js实际0项exit 0；node --test tests/app/*.test.mjs实际581通过、0跳过、exit 0。新增审核预览专项14项exit 0（problem-review-ui-green.log）。UI门禁0违规，对比度58组0失败，组件浏览器35通过。最后完整前端门禁在后续粘贴/拖放和审核预览修改前执行，后续仅专项和新增E2E复跑，须独立重跑最终全部门禁。

视觉命令python3 tests/visual/run.py --ref HEAD --out /worker/evidence/visual实际exit 0，48组前后截图，无脚本错误，30组差异。设置页26.714%以内差异来自新增提醒卡片；其余桌面约0.35%来自侧栏问题入口与后续导航位移，手机原页面无此侧栏位移。报告visual/report.html。默认输出/tmp首次只读失败后改指定输出目录重跑。视觉对比在最后草稿/附件补充前运行，最新问题截图由最终E2E生成。

## 未执行验证

已达到时间上限，停止实现并保留候选。全量尚有一处MCP工具集合断言未同步；独立中途复核发现的普通HTTP随机编号兼容问题尚未修复，唯一缺陷登记见AI/optimization.md；最后新增或修改内容未再跑完整Python与全部前端门禁。未对新版完整设计13类场景的每一个子条件都单独构造浏览器断言：学习state.restore不抹除新库、横幅本次替换/current模式的浏览器操作、横幅损坏图像/字体禁打印的专项、焦点恢复与手机错因表单尚需Hermes复核。未使用真实付费模型、实体打印机或手机实机，审核适配链使用真实服务与合成模型边界。

候选未完成最终独立验收。源码、所有证据和截图保留，未提交、未推送、未部署，生产未改。下一步先同步MCP完整工具集合断言，复跑最终门禁并检查剩余边界。当前版本保持v2.10.0，未部署。

## 限定补修（2026-11-14）

本轮按Hermes补修简报的18分钟上限只处理HTTP随机编号与MCP精确集合两项阻断，并非用户指定时限；前述首次全量失败、初轮输出被覆盖和时间上限停止均为原始执行记录，保留不抹除。`/worker/final.md`及`/worker/REVIEW_REQUIRED.md`保持原样。

两处编号调用复用现有安全随机helper，不新增随机算法、不用Math.random、不改变用户HTTP域名。调度提醒与本轮新增代码逐项检索，仅这两处依赖randomUUID。MCP集合逐名补齐10工具，新增旧Key、问题只读、缺少读权限、直接调用拒绝与实时降权断言；不修改服务权限。

红灯证据：`/worker/evidence/repair-final/mcp-red.log`实际1项exit 1，遗漏精确10名；`http-red-4.log/json`实际exit 1，isSecureContext=false、randomUUID=undefined、getRandomValues=function，真实PIN鉴权后页面新建报错且草稿payload同样TypeError。前3次HTTP代理/登录调试输出也保留。首轮修复后HTTP完整创建和两条错因已通过，但额外焦点断言误期望textarea，`http-green.log`保留exit 1；确认框关闭应恢复触发关闭按钮，修正测试预期后通过。

本轮已实际验证：helper及原草稿单测3项exit 0；MCP精确集合与权限1项exit 0；原问题E2E32场景exit 0；Node全量应用581项、顶层实际0项，均exit 0；UI零违规、对比度58组零失败、组件浏览器35项，均exit 0。真实HTTP补修E2E通过新建、两条记录、读回与刷新，兼验390px无溢出及取消关闭恢复触发按钮焦点。最终计数、文档和视觉门禁见下方收口与`/worker/repair-final.md`。

本轮Codex补修不重跑全量Python，由Hermes委派合同要求主会话对最新文件独立执行，并非用户要求跳过；旧两项基线失败仍未宣称解决。其余未覆盖边界沿用前文，不调用真实付费模型。未提交、未推送、未部署，生产未改。

### 本轮最终门禁与视觉

真实HTTP新增E2E实际14项断言全部通过、exit 0（http-green-2.log、http-e2e.json），未替换crypto。MCP精确工具集合与权限再次执行1项exit 0（mcp-green-repeat.log）。文档门禁`python3 tests/check_docs.py --diff HEAD`检查165份、0问题、4条文件体积提醒，exit 0；日志索引生成exit 0。最新视觉`python3 tests/visual/run.py --ref HEAD --out /worker/evidence/repair-final/visual`实际48组、exit 0、无脚本错误，30组有差异。本轮两行编号修复不改变视觉模板；对比HEAD包含原候选尚未提交的设置提醒与问题导航变化。逐项解释如下，设置为提醒卡及权限选项，桌面其它页为侧栏问题入口及导航位移，手机极小差异为合成数据服务端事件时间（已查看差异图）：

| 场景 | 差异 | 依据 |
|---|---|---|
| dashboard-light-desktop | 0.223% | 新增问题侧栏入口与导航位移 |
| data-light-desktop | 0.058% | 新增问题侧栏入口与导航位移 |
| questions-light-desktop | 0.329% | 新增问题侧栏入口与导航位移 |
| board-light-desktop | 0.1% | 新增问题侧栏入口与导航位移 |
| catalog-light-desktop | 0.219% | 新增问题侧栏入口与导航位移 |
| schedule-light-desktop | 0.12% | 新增问题侧栏入口与导航位移 |
| instant-light-desktop | 0.346% | 新增问题侧栏入口与导航位移 |
| feedback-light-desktop | 0.345% | 新增问题侧栏入口与导航位移 |
| create-light-desktop | 0.343% | 新增问题侧栏入口与导航位移 |
| history-light-desktop | 0.319% | 新增问题侧栏入口与导航位移 |
| reports-light-desktop | 0.344% | 新增问题侧栏入口与导航位移 |
| settings-light-desktop | 26.714% | 新增调度提醒卡片与问题权限选项 |
| dashboard-light-mobile | 0.003% | 合成库服务端事件时间的分钟文本差异 |
| history-light-mobile | 0.001% | 合成库服务端事件时间的分钟文本差异 |
| settings-light-mobile | 21.301% | 新增调度提醒卡片与问题权限选项 |
| dashboard-dark-desktop | 0.215% | 新增问题侧栏入口与导航位移 |
| data-dark-desktop | 0.056% | 新增问题侧栏入口与导航位移 |
| questions-dark-desktop | 0.317% | 新增问题侧栏入口与导航位移 |
| board-dark-desktop | 0.092% | 新增问题侧栏入口与导航位移 |
| catalog-dark-desktop | 0.206% | 新增问题侧栏入口与导航位移 |
| schedule-dark-desktop | 0.116% | 新增问题侧栏入口与导航位移 |
| instant-dark-desktop | 0.335% | 新增问题侧栏入口与导航位移 |
| feedback-dark-desktop | 0.336% | 新增问题侧栏入口与导航位移 |
| create-dark-desktop | 0.334% | 新增问题侧栏入口与导航位移 |
| history-dark-desktop | 0.31% | 新增问题侧栏入口与导航位移 |
| reports-dark-desktop | 0.336% | 新增问题侧栏入口与导航位移 |
| settings-dark-desktop | 26.708% | 新增调度提醒卡片与问题权限选项 |
| dashboard-dark-mobile | 0.002% | 合成库服务端事件时间的分钟文本差异 |
| history-dark-mobile | 0.001% | 合成库服务端事件时间的分钟文本差异 |
| settings-dark-mobile | 21.304% | 新增调度提醒卡片与问题权限选项 |

手机真实HTTP截图`/worker/evidence/repair-final/http-mobile-reflections.png`已查看：390px表单位于弹窗内，输入与按钮可见，没有横向溢出。原32场景最新截图另存repair-final/problems/screenshots，原worker/evidence中的截图和报告均保留。

## Hermes最终复核与交付（2026-11-14）

以上各节按执行阶段保留；本节是最终状态。Codex限定补修进程exit 0，模型仍为gpt-6.1-sol。Hermes独立于Codex检查当前源码、测试与真实浏览器，不另委派审查代理。完整复核的1211份源码和测试输入前后及交付前哈希一致；仅文档收口发生在最终测试之后。

全量Python实际1176项，1174通过、2失败、0错误，exit 1。两项失败均在原始HEAD展开副本复现：源码导出的隔离Python子进程缺少Pillow，以及traincontrol的400/202断言。新增MCP精确集合错误已经修复，未再出现。不能把这个结果写成全量通过。

Node应用581项、浏览器组件35项、对比度58组、UI与文档门禁均exit 0；问题E2E32项及非安全HTTP14项均通过。补充18项覆盖AI更新不继承用户确认、原文审计、旧Markdown不变、学习状态不变、学习状态恢复保留问题库、current/replace真实下载与不改快照、损坏横幅和字体禁打印、390px保存读回，全部通过。

复核脚本最初把unittest发现模式的test_source_export与显式调用的tests.test_source_export按字符串直接比较，故原verdict为false。只规范化这个模块名前缀后，基线失败集合精确一致，判定为候选通过且保留两项基线失败；原verdict、日志与修正说明完整保留，不改变套件退出码。

最后重跑32项真实浏览器E2E生成交付截图。关闭动画并等待字体与布局稳定解决侧栏过渡中的截帧；弹窗改拍真实视口而非拼接整页。主会话已检查问题页、错因弹窗和调度SVG截图。截图使用合成题，不是生产数据。

持久证据在`/root/workspace/artifacts/omrs-problem-center-20261114-2042/`，包括完整复核、18项报告、截图状态、源码哈希及红绿补修证据。原始scratch证据仍保留。生产源文件与任务前1650份清单一致，omrs.service主PID仍为1465217、启动时间未变；没有访问真实题库、提交、推送、部署或重启生产。

尚未执行：真实付费模型的完整对话、实体手机、实体打印机和生产验收。下一步等待用户明确部署授权；当前交付仅为隔离开发候选，不代表生产生效。
