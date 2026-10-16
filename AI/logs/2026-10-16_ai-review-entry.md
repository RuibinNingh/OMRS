# 2026-10-16 审核中心并排录入与生产发布

## 背景与范围

用户要求「重设计一下审核中心录入题目的UI」「右侧如果有空可以利用一下做成选择图片然后框选的效果」「打个草稿」，随后授权「实现一下部署生产提交GitHub」。按并排核对草稿实现；执行者Codex，完整模式。开工基线a5a6580，分支codex/ai-review-entry。原有AI/plans/omrs-maintenance/validation.json未提交修改保留，不纳入本任务。

## 行为变化

默认左侧阅读、编辑字段与图文正文，右侧通过缩略图选择完整来源并框选；待审队列收进顶部选择器，可展开完整列表和分页。窄于760px的详情容器自动上下排列，聊天抽屉也复用此布局。无来源的旧草稿仍能补关联；放大框选、独立训练、AI框选和转文字继续可用。

未框配图显示明确占位，可定位到对应来源和图片块。右侧可直接添加当前来源为题目／答案图片；新块切图后按本地稳定键保持选中。手动画框实时更新正文裁图预览，暂存或入库后才持久化；沿用现有交互，没有引入第二次「采用选区」确认。取消切题保持未保存输入并恢复选择器原值。已入库／丢弃正文保持只读。

版本为v2.8.1，AI框选仍调用现有本地检测服务，模型与后端存储契约不变。本批发布也包含线上f05eda0之后已完成的长期待审和维护提交，具体行为见本版本changelog及既有任务日志；没有将整批发布描述成仅前端样式修改。

## 影响文件

已按git diff复核：审核中心draft-actions、drafts-block-actions、drafts-canvas-ctl、drafts-review、drafts-view、drafts.css及外框index／view／review.css，新增drafts-sources.js分离来源展示。未修改草稿后端API或业务数据。

新增tests/e2e/ai_review_entry.py覆盖完整交互；drafts、drafts_blocks和ai_review_refresh通过真实可见队列／顶部选择器导航，公共帮助函数位于tests/e2e_navigation.py。可见性审计排除已折叠details；原有横溢、过小目标、行内事件与样式检查继续保留。视觉入口增加--review-kind draft，保持默认提案截图。

同步README、版本文件和侧栏、AI/README、changelog、frontend/ai-review、frontend/design-system、frontend/architecture及environment。环境文档订正发布前实测的v2.8.0源码目录和既有保全，部署后继续记录本次结果。

## 已执行验证

测试均使用临时Vault与随机端口，清除OMRS_SYSTEMD_SERVICE、OMRS_BOXDETECT_CONTROL；浏览器使用共享CDP的独立上下文，未向生产写入测试题目。Python解释器为现有生产依赖omrs-zyb-deps-20261011/.venv/bin/python。

- python -m unittest discover -s tests -p 'test_*.py' -q：1043项通过，163.053秒。
- node --test tests/app/*.test.mjs：529通过，0失败／跳过。
- python tests/app/run_browser.py：34通过，0失败。
- python tests/check_ui.py：全仓0问题；python tests/check_contrast.py：58组全通过。
- python tests/e2e/ai_review_entry.py：24/24通过，含未保存保护、切图新块、真实拖框、暂存刷新、放大返回、双主题四宽度、实际裁图入库和只读。
- python tests/e2e/drafts.py：82/82通过；drafts_blocks.py：59/59；drafts_p4.py：24/24；ai_review.py：48/48；ai_review_refresh.py：56/56；assistant_review.py：28/28。

首轮新增测试修正了取消按钮选择器歧义与入库后等待下一份完成的时序。旧回归随顶部选择器和并排定位调整；首轮并发浏览器回归有一次转文字结果等待未命中，保留原记录，独立顺序重跑82/82通过。生产归档的浏览器门禁逐项顺序执行，不将首轮失败计为通过。

## 视觉对照

已执行python tests/visual/run.py --ref a5a6580 --pages ai-review --review-kind draft --out /tmp/omrs-entry-visual，双主题×桌面／手机4对，无脚本错误、整页横溢、过小目标和行内样式。差异分别为浅色桌面5.304%、深色桌面9.484%、浅色手机43.501%、深色手机43.561%。桌面由隐藏常驻队列、顶部选择器和正文／原图双栏造成；手机由新增来源画布与顶部导航使页面变长。已实际查看桌面与手机截图，均为预期布局变化。

最终文案与版本同步后，以相同命令再次对照并另存/tmp/omrs-entry-visual-final：浅色桌面5.319%、深色桌面9.501%、浅色手机43.528%、深色手机43.590%，差异还包括侧栏版本、选择器序号与状态文案。4对均无脚本错误、整页横溢、过小目标、行内样式或可见元素横溢。文档差异门禁146份／0问题／3条既有体积提醒，git diff --check通过。

## 发布进度与未执行项

生产发布前只读核验：线上v2.8.0、源码omrs-f05eda0，主服务／网关／检测均active/running且NRestarts=0；实际运行任务、恢复意图和受管检测操作为0。发布脚本已准备在仓库外专用私有目录，长期待审只保留，不依据旧期限作废。尚未将归档复验或生产切换计为完成，结果在同一任务日志追加。

未运行实体手机、Windows、真实供应商／付费模型调用和真实模型推理；本次保持其原配置，没有将合成库浏览器验收代替这些项目。生产验收只读，不提交真实草稿。

## 最终发布与交付

实现提交d835677（v2.8.1），已将origin/main从3101869正常快进到该提交，包含本次UI和前述已完成维护，无强推。生产从同一提交生成1527个文件精确归档/root/workspace/apps/releases/omrs-d835677，不包含工作区原有validation.json修改，依赖保持。

归档内重新执行Python定向94/94、全部Node529/529、UI0问题、对比度58组，以及顺序浏览器录入24/24、草稿82/82，全部通过。第一遍部署脚本在停服前因遗留的「要求整个工作区干净」断言停止，线上无变化；修正为核对唯一原有修改的路径及SHA256后继续，未放宽源码归档校验。失败和重试记录均保全。

2026-10-16T15:27:53.534450+00:00完成切换，用时5.721秒。停服保全/root/workspace/apps/releases/OMRS-v281-release-m0e8sy5o解包核验1148个文件和8个SQLite库；49张原业务表全部原列／原行、1035个原正文／图片／关键配置文件保持，网关账号／设备／密钥保持。源码别名原子指向新归档；三服务active/running、NRestarts=0，真实cwd一致，Nginx和隧道未变化。

生产只读58/58检查通过：版本、10项版本化资源字节／缓存／匿名保护、公网PIN入口、MCP与网关鉴权、在线真实模块在浏览器渲染合成草稿、服务目录与错误日志、模型控制身份和全部原业务数据。生产没有写入合成题目；未执行项仍以上节为准。验证、状态及回退脚本已保存在私有保全目录，回退只切源码并保留最新数据。

收尾文档提交记录实际线上源码和验收，不再次重启服务；原有AI/plans/omrs-maintenance/validation.json继续留在工作区，内容哈希未变化。
