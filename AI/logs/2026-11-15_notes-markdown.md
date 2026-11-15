# 2026-11-15 备注错因Markdown显示

> **任务**
> - 标识：notes-markdown
> - 状态：已交付

## 背景

用户原话：「备注/错因部分能不能被渲染」。这是问题中心U5的显示补充，接续已经交付的错因侧栏/窄屏底部布局；此前布局日志`2026-11-15_reflection-layout.md`保持原文。本任务在原独立开发候选`/root/workspace/apps/omrs-problem-center-dev-20261114-2042`实施，HEAD为f50c6c3，保留既有未提交开发。主仓库`/root/workspace/apps/OMRS`不包含该功能，不在其中重复实现。

执行者Codex，完整模式；已读计划进度、执行说明及相关前端文档。版本仍为v2.10.0，依原计划不提交、推送或发布，也不访问真实题库。证据根目录为`/root/workspace/artifacts/omrs-notes-markdown-20261115/`，开工1684份文件的哈希保存在`before-manifest.json`，拟改文件原文保存在`before/`。

根因是备注使用的基础渲染器只处理换行、表格、题图与公式，`## 错因`、列表和加粗仍作为文字显示。此次复用已有问题说明的安全Markdown能力，抽出共用函数；不引入新库。

## 行为变化

答案下方的「备注 / 错因」支持标题、平铺有序/无序列表、加粗、斜体、引用、行内/围栏代码与受限链接，保留表格、受控题图及美元/反斜杠公式。多行展示公式作为完整块处理；普通HTML转义，代码中的Markdown和公式保留源码。该解析器是安全子集，不承诺完整CommonMark或嵌套列表。

备注沿用题库的完整/简略换行偏好，行尾双空格始终硬换行。阅读间距、引用边线及代码底色使用现有token，公式/表格/代码在各自容器内横滚。题面与答案仍走原基础渲染；原有显示答案与显示备注守卫不变。只查看不改写旧Markdown，编辑保存后正常重绘。

问题说明和快捷错因历史使用同一共用函数，问题域包装器继续将PA附件映射到`/api/problem-asset`；题目备注图片保持`/api/image`。不修改后端、存储、学习算法、布局阈值或错因录入流程。

## 影响文件

已运行`git status --short`和`git diff --name-status`识别候选的已有改动；再以本轮开工哈希逐文件比较。候选整体差异不能视作本轮新增，最终清单保存在`task-changes.json`。

- `assets/app/domain/rich-markdown.js`：抽出共用的安全排版，保留公式、代码与换行语义。
- `assets/app/domain/problem-markdown.js`：保留问题域PA附件映射的薄包装。
- `assets/app/domain/question/view.js`、`qview.css`：备注使用共用排版及限定样式；题面/答案基础渲染保持原契约。
- `tests/app/question.test.mjs`、新增`tests/app/rich-markdown.test.mjs`和`tests/e2e/notes_markdown.py`：格式、安全边界、兼容与真实浏览器回归。
- `AI/frontend/qview.md`、`architecture.md`、`problems.md`、`design-system.md`和根`README.md`：同步当前显示能力与验证入口。
- `AI/plans/problem-center/plan.md`、`progress.md`、本日志及生成的`AI/logs/log.md`：用户原话、范围补充、实际结果和索引；`AI/routes.md`由脚本更新问题附件接口的说明文档引用，路由集合未变。未改旧执行说明或已交付日志。

## 已执行验证

真实页面均使用合成临时Vault和随机回环端口；服务启动器清除`OMRS_SYSTEMD_SERVICE`、`OMRS_BOXDETECT_CONTROL`。下列结果均为本任务实际执行，不沿用此前任务数字。

| 命令 | 实际结果 | 证据（相对证据根目录） |
|---|---|---|
| `node --test tests/app/question.test.mjs tests/app/rich-markdown.test.mjs tests/app/problems.test.mjs` | 40项通过，0失败 | `unit.log` |
| `node --test tests/app/*.test.mjs` | 587项通过，0失败 | `node.log` |
| `python3 tests/app/run_browser.py` | 35项通过，0失败 | `components.log` |
| `python3 tests/e2e/notes_markdown.py --out /root/workspace/artifacts/omrs-notes-markdown-20261115/final --before-source /root/workspace/artifacts/omrs-notes-markdown-20261115/before` | 31项通过，0脚本错误 | `notes-browser-complete.log`、`final/results.json` |
| `python3 tests/e2e/questions.py` | 106项通过，0失败 | `questions.log` |
| `python3 tests/e2e/problems.py` | 32项通过，0脚本错误 | `problems.log`、`problems/problem-e2e.json` |
| `python3 tests/e2e/reflection_layout.py` | 43项通过，0脚本错误 | `layout.log`、`layout/results.json` |
| `python3 tests/e2e/instant.py` | 27项通过，0失败 | `instant.log` |
| `python3 tests/e2e/feedback.py` | 43项通过，0失败 | `feedback.log` |
| `python3 tests/check_ui.py` | 全仓0违规 | `check-ui-final.log` |
| `python3 tests/check_contrast.py` | 58组通过，0不达标 | `check-contrast-final.log` |
| `python3 tests/visual/run.py --ref HEAD --out /root/workspace/artifacts/omrs-notes-markdown-20261115/visual-final --pages questions --themes light,dark --viewports desktop,mobile` | 4组比较，0脚本错误，exit 0 | `visual-final.log`、`visual-final/report.html` |

新增备注用例先在原渲染器失败，保留`red.log`；实现后定向40项和全部应用587项通过。浏览器首次前后截图的路由回调误把Playwright的Request当作默认参数，保留`notes-browser.log`的超时和异常；修正测试回调后30项通过。像素检查又发现后置`.md-p`规则盖掉标题后的间距，增加限定选择器、实际间距断言与固定浅色截图，最终31项通过；该次同时覆盖浅深主题1440/1024/390/320px。

浏览器从真实题库行打开合成题，核对标题、列表、加粗、引用、代码、公式、表格与真实图片解码；普通HTML没有执行。查看前后旧文件字节相同，编辑保存后仍渲染，学习状态保持不变。已检查最终桌面弹窗、备注局部及手机深色截图。`final/notes-before.png`与`notes-after.png`在同一合成题上对比；前者仅拦截本轮开工前的视图模块/样式，不回滚开发候选。`notes-preview.png`为最终备注截图上部裁剪，未重绘内容。

HEAD视觉差异逐项说明：桌面浅色0.332%、深色0.322%，来自既有候选的侧栏「问题」入口和后续导航位移；手机两组0差异。该脚本默认不打开弹窗，因此本轮备注变化由上述单独的真实浏览器截图呈现：Markdown源码变为结构化标题、列表、引用和代码，公式、表格和题图保留，标题与正文留出阅读间距。

文档索引已用`python3 tests/check_docs.py --write-log-index`生成。首次文档门禁发现路由总表的说明列未收录新增的前端附件说明，exit 1，保留`docs-first.log`；运行`--write-routes`后只增加`/api/problem-asset`的`AI/frontend/problems.md`引用，未新增或修改路由。最终`python3 tests/check_docs.py --diff HEAD`实际检查165份文档、0问题、4条既有体积提醒，exit 0，结果见`docs-final.log`。`git diff --check`已实际执行，exit 0；主仓库`git status --short`为空。本轮精确变化为17份文件，均属于上述范围，候选其余开工文件哈希保持一致。

## 未执行验证

本任务只改前端和测试/文档，未重跑完整Python套件或无关页面E2E；不把2026-11-14的1176项结果当作本轮验证。原候选两项已在基线复现的Python失败仍见计划进度，不在本任务修复。

未做实体手机、实体打印机或真实付费模型验收；未访问真实题库，未提交、推送、部署或重启生产。交付为开发候选中的实际改动，生产步骤仅在用户明确授权后执行。
