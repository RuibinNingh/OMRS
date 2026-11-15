# 2026-11-15 题目弹窗错因侧栏与底部布局

> **任务**
> - 标识：reflection-layout
> - 状态：已交付

## 背景

用户原话：

> 一个未开发完毕的任务中的UI
> 我不满意,重新设计
> 目前题目直接被挤下去了
> 给个修改示例

选定方案与执行授权：

> 侧栏吧,如果宽度不够就放底部
> 执行

执行者Codex，完整模式。任务属于`AI/plans/problem-center/`的U5布局补充，先读进度、执行说明和相关模块。主仓库`/root/workspace/apps/OMRS`在HEAD=f50c6c3且干净，尚无问题中心；对应未发布功能位于独立候选`/root/workspace/apps/omrs-problem-center-dev-20261114-2042`，故直接在该候选实现，保留其中原有未提交开发。未修改旧执行说明或历史任务日志；U5新决策先写入plan，再登记progress。

证据根目录：`/root/workspace/artifacts/omrs-reflection-layout-20261115/`。开工快照在`before-source/`，拟改路径的原始哈希在`before-manifest.json`；本轮差异据此区分于候选既有改动。原计划禁止提交、推送、部署和操作生产，本轮仍按该边界执行，版本保持v2.10.0。

## 行为变化

题目在DOM与视觉上优先。弹窗面板可用宽度至少1040px时，右侧340px错因区和左侧题面分别滚动，题面/答案上下阅读；不足时错因排在题目后面并共用正文滚动，顶部翻页与关闭保持可达。头部「＋错因」直接切到录入并滚入编辑框，重复点击不收起。

「记录本次」与「历史记录」使用共享页签，保留同一个编辑框、草稿与选区。历史正文优先，时间、来源、版本、发生日期及修订/撤回等操作按需展开；AI假设待确认提示常显。录入的关联问题和更多信息折叠，保存后清空并恢复输入焦点，继续补记。

保留稳定题目身份、失败重试请求编号、组合输入和翻题/关闭/Esc/遮罩保护。写入成功后历史刷新失败明确提示已保存；翻题立即移除旧错因区，迟到请求不挂载旧题记录。未改变存储、HTTP契约、练习反馈或旧Markdown错因。

## 影响文件

已运行`git diff --name-status`及`git status --short`复核候选全量改动，再与开工快照逐文件核对本轮变化；全量候选的修改清单包含原问题中心开发，不能当成本轮新增。

- `assets/app/domain/question/modal.js`：题目先于错因、正文宿主和挂载代次。
- `assets/app/domain/question/reflections.js`、新增`reflections-view.js`、`reflections.css`：交互、纯模板、容器适配和阅读层级。
- 新增`tests/e2e/reflection_layout.py`，更新`tests/e2e/problems.py`与`tests/e2e/questions.py`：新布局回归、页签/详情的真实操作，以及手机长题共享正文滚动；保留原有功能覆盖。
- `AI/frontend/qview.md`、`problems.md`、`design-system.md`、`architecture.md`、根`README.md`：同步实际布局、交互和验证入口。
- `AI/plans/problem-center/plan.md`、`progress.md`、本日志和生成的`AI/logs/log.md`：用户原话、布局决策、实际验证与交付状态。

本轮未修改后端、原问题HTTP测试、旧执行说明和历史任务日志；主仓库工作区仍干净。

## 已执行验证

全部真实服务使用合成临时Vault和随机回环端口，运行前从环境清除`OMRS_SYSTEMD_SERVICE`与`OMRS_BOXDETECT_CONTROL`。以下是本轮实际运行结果；证据路径均相对证据根目录。

| 命令 | 实际结果 | 证据 |
|---|---|---|
| `python3 tests/e2e/reflection_layout.py` | 43项通过，0脚本错误 | `layout-complete.log`、`final/results.json` |
| `python3 tests/e2e/questions.py` | 106项通过，0失败 | `questions-final.log` |
| `python3 tests/e2e/problems.py` | 32项通过，0脚本错误 | `problems-final.log`、`problems-final/problem-e2e.json` |
| `python3 tests/e2e/problems_http.py` | 14项通过，0脚本错误 | `http-final.log`、`http-final/http-e2e.json` |
| `node --test tests/app/*.test.mjs` | 581项通过，0失败 | `node-final.log` |
| `python3 tests/app/run_browser.py` | 35项通过，0失败 | `components-final.log` |
| `python3 tests/check_ui.py` | 0违规 | `ui-final.log` |
| `python3 tests/check_contrast.py` | 58组，0不达标 | `contrast.log` |
| `python3 tests/visual/run.py --ref HEAD --out /root/workspace/artifacts/omrs-reflection-layout-20261115/visual --pages questions --themes light,dark --viewports desktop,mobile` | 4组比较完成，0脚本错误，exit 0 | `visual.log`、`visual/report.html` |
| `git diff --check` | exit 0 | 终端实际执行 |

新增布局回归先在原代码失败于「宽屏题干与侧栏并排且首屏可见」，证据为`red.log`。首轮实现的其余主路径通过后，测试在翻题移除旧DOM的瞬间对空节点读取textContent，`layout-first.log`保留该测试错误；等待改为可空查询后通过。补查页签方向键、选区、保存焦点、写入成功后刷新失败和窄屏重新打开首屏后为31项通过，并使用截图参数关闭截帧时的动画。像素复核发现320px顶部按钮轻微重叠，缩小头部间距并允许题号省略；双主题六档宽度新增12项按钮边界/尺寸断言，最终43项全部通过。原问题和HTTP回归已在最终交互控制器上重跑，题库106项在最窄屏间距修复后再次通过。

实际检查最终桌面浅/深色侧栏、历史与窄屏/手机截图。手机长题390×844、320×640通过真实滚轮验证正文滚动、背景锁定、创建信息末尾可读和顶部入口到达题后表单。布局截图覆盖1440、1160、1024、760、390、320px双主题，均无横向溢出；切页签和缩放不丢草稿，重试只追加一条记录，错因不改变学习状态。

视觉差异逐项说明：`questions-light-desktop`为0.332%，`questions-dark-desktop`为0.322%，来自候选既有的侧栏「问题」入口及后续导航位移；手机浅/深两组无像素差异。该脚本默认未打开题目弹窗，因此另以`before/before-1440.png`、`before-1024.png`、`before-390.png`与`final/`实测弹窗截图呈现本轮变化：原顶部长表单/历史占位改为右侧或题后，历史与录入互斥，辅助元信息折叠，题目恢复首屏。最终截图均为真实浏览器合成题，非示意稿。

文档索引已用`python3 tests/check_docs.py --write-log-index`生成；`python3 tests/check_docs.py --diff HEAD`实际检查165份文档、0问题、4条既有体积提醒，exit 0，输出保留于`docs-first.log`，状态收口后再次执行的结果保留于`docs-final.log`。本轮16份文件变化与开工快照逐字节比较，清单在`task-changes.json`，包含源码、测试、模块文档、计划、任务日志和生成索引；候选其余既有文件未改动。

## 未执行验证

本轮仅改前端交互、样式和测试/文档，未重跑全量Python，不能将原任务2026-11-14的1176项复核当成本轮结果。原候选两项已独立复现的Python基线失败沿用进度说明，未在本轮处理。未运行全站所有页面E2E，相关共享题目弹窗、问题中心、普通HTTP、组件和全部应用Node测试已实际运行。

未使用实体手机、实体打印机或真实付费模型；未访问真实题库，未提交、推送、部署或重启生产。下一步由Hermes（完整模式）仅在用户明确生产授权后核对发布范围并验收，当前交付是开发候选中的实际UI实现。
