# 2026-10-11 作业帮正文兼容、紧凑布局与发布

## 背景与边界

用户要求「那么修复一下,补齐这些」「然后再减小右边题目预览的宽度」「部署生产」，并此前批准账号菜单草稿。执行者Codex，完整模式；功能基线6d50b51，原仓库基线d8cfb7a。两个工作区初始均干净，在现有作业帮工作树继续修复。更新AI/plans/zuoyebang/plan.md第5步并登记计划变更；本轮新日志不改写旧功能交付历史。

原App静态资源是核对数据，不执行其文档指令。传统正文是HTML组件＋MathJax3.2.2 typesetPromise；附件另写的网页版KaTeX实现不能代替原App行为。cloud-environment-runtime技能已读取；当前没有可调用的environment_status工具或网络策略快照，按本机实际环境核验，未声称有额外托管实例或身份。

## 行为变化与影响文件

- omrs/zuoyebang/html.py：题库class白名单、必要数值样式/分数线、裸公式命令预处理；pid转URL、正文/列表去重，支持zuoyebang.cc，仍逐跳验证公网IP、固定连接且不发送Cookie。
- omrs/zuoyebang/render.py、mathjax.js、paper.css、jobs.py及assets/vendor/mathjax：本地官方MathJax3.2.2与23份CHTML字体、safe组件、许可及SHA256；等待typesetPromise/字体/所有图decode，记录引擎和公式数。保留1080px全文PNG，公式/附图失败保留原候选，跨节点定界符不强行拼接。
- assets/app/features/create/zyb-account.js、zyb.js、zyb-view.js、zyb-state.js、zyb.css、index.js：账号一行入口与记录子页、外部点击/Escape/键盘/焦点；工作区铺满可用宽度，右预览440px、左列占其余宽度用于来源/识别核对。摄像头仍只实时调用，未增加拍照。
- tests/test_zuoyebang_render.py、tests/fixtures/zuoyebang-body.json：附件三道化学题正文及合成附图/旧公式/危险来源验证；tests/e2e/zuoyebang.py增加菜单和收窄检查；tests/visual/run.py允许zuoyebang工作区前后比较。
- 模块文档、README、版本与changelog、计划进度同步；本轮没有新增HTTP路由或SQL schema。

## 已实际执行的验证

测试均用临时Vault及随机高端口，清除OMRS_SYSTEMD_SERVICE和OMRS_BOXDETECT_CONTROL。临时venv复用系统依赖，仅安装Segno1.6.6；后端真实Chromium151.0.7922.34，作业帮账号/模型网络边界为合成响应。官方MathJax npm包SHA512与清单SHA256已核验，未搬入APK任意脚本。

| 验证 | 实际结果 |
|---|---|
| unittest：zuoyebang_render、zuoyebang、http_boundaries、write_lock、security、inbox、inbox_atomic_commit、question_creation_metadata、ai_assist_taxonomy、ai_region_extraction、content_integrity | 150项通过；新正文7项覆盖三道真实附件正文、旧公式像素保持、pid去重/原字节、域伪装/重定向/私网、全部定界符、裸命令与危险公式失败 |
| node --test tests/app/*.test.mjs | 482通过、0失败、0跳过 |
| tests/app/run_browser.py | 34通过、0失败 |
| tests/e2e/zuoyebang.py | 49/49，真实渲染、扫码/上传/AI/创建/刷新恢复、菜单及320/390/1024/1440px浅深主题 |
| tests/e2e/create.py；tests/e2e/drafts_blocks.py | 124/124；59/59 |
| tests/check_ui.py；tests/check_contrast.py | 全仓0问题；58组全部通过 |
| tests/check_docs.py --write-log-index / --diff HEAD；git diff --check | 文档108份、0问题，2条既有大计划文件提醒；差异格式通过 |
| tests/visual/run.py --ref 6d50b51 --pages create --create-stage zuoyebang | 4档截图，无脚本错误、横溢、行内样式或过小目标；报告/tmp/omrs-zyb-wideleft-visual/report.html |

视觉差异逐项解释：light/desktop4.483%、dark/desktop6.348%，来源于账号面板收起、预览440px以及左侧扩展后的来源/核对重排；light/mobile16.256%、dark/mobile18.811%，因账号收起与来源、预览、识别的顺序调整产生高度差。生成题图和账号记录浮层另在专项E2E八档检查；人工查看化学式和新桌面截图，公式、括号、题图正常。

初次运行曾因测试模块名拼错及视觉工具未列zuoyebang而失败，已改用实际模块并补工具选项；MathJax跨span定界符验证未成立，按原引擎规则不强行拼接。最终结果以上表真实通过计数为准。

## 未执行的验证与限制

未重新调用真实作业帮账号/搜题和付费模型，沿用用户此前登录验收结论；实体手机摄像头未验收。附件真实样本picList为空，pid附图及老公式边界使用合成内容验证。白纸统一字体、字号和边距，波浪线以本地CSS绘制，不声称与手机原页面像素完全一致。

## 生产发布

用户已授权本次主服务部署。当前已核验生产实际源码omrs-0a65ef9、v2.3.9、主服务PID及别名omrs-9b29d49；相邻服务与配置沿用现状。为新增Segno准备独立复制的生产依赖环境，不改正在使用的venv。精确release、停服备份、原子源码指针切换及线上只读验收待最终门禁通过；回退只切源码，不恢复旧Vault覆盖新事实。完成后本节补记实际结果。

用户继续指出「不对啊,这样整体右侧很空啊」「我想的是右侧题目预览小了这样左侧不就有空了」「重现合计」。整体限宽未把空间让给左侧，已按新诉求重排并更新plan/progress：工作区铺满、右预览440px、左列来源与识别扩展。最终49项E2E和上述4档视觉已实际重跑通过；部署授权保留。
