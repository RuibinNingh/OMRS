# 2026-10-17 作业帮手机宽度题图

## 背景

用户原话：「按照手机宽度排版吧」「有方案吗」，确认360px排版、17px正文及3倍输出的实际对比方案后，追加「可以,就这么做」。执行者Codex，完整模式；本次为独立功能实现，不改已结束的历史计划。基线8a39245，版本保持v2.8.1；未部署、推送或操作生产服务。

开工唯一已有修改为AI/plans/omrs-maintenance/validation.json，本次保留且不提交。原SHA256为3d3cdbd203731931981a4db6d940cae48878e1069d55c1c2008c361aa58be9f9。

## 行为变化

候选题目和答案以360 CSS px宽、17px正文、16px边距、1.65行距排版，Chromium倍率3，仍各输出一张1080物理像素宽的完整PNG。完整高度乘3后核算1亿物理像素预算，再截图并校验实际尺寸；不整题缩放、分页或截断。

可信layout.js在公式、字体与附图就绪后测量宽度，仅缩放超宽的MathJax公式、旧HTML公式或整张宽表格，正文保持字号。表内公式随表适配，保留行列关系。实测旧nobr公式的文字可溢出固定宽度span而不改变元素矩形，补充Range实际文字测量；超宽仍无法解决时明确失败并保留来源。附图内部小字仍受原图清晰度限制。

渲染记录增加layout={version:mobile-360-v1,css_width:360,device_scale_factor:3}，图片尺寸继续表示物理像素，每区另记fitted_formulas/fitted_tables。旧记录无需迁移；当前版本之外的未预留候选提供「重新生成手机版」，复用保存的搜题正文建立新render_id。完成时转移最新人工表单、标记、正文、保存方式与版本，保留旧草稿及PNG。生成期间编辑和刷新均可恢复；原图裁切、已有创建预留和已入库记录没有升级入口。

## 影响文件

- omrs/zuoyebang/render.py、paper.css、layout.js、jobs.py：手机排版、局部适配、物理预算及版本元数据。
- assets/app/features/zuoyebang/index.js、zyb.js、zyb-state.js、zyb-view.js：主动升级入口、后台任务恢复及编辑移交。
- tests/test_zuoyebang_render.py、tests/app/create-zyb.test.mjs、tests/e2e/zuoyebang.py、tests/e2e/zuoyebang_mobile.py：中文实际字高、输出预算、长公式／宽表格、记录保护与浏览器升级主路径。
- README.md、AI/zuoyebang.md、AI/frontend/zuoyebang.md、AI/frontend/architecture.md、AI/api/extensions.md、AI/data.md、AI/data/storage.md、AI/environment.md：当前行为、响应字段、存储兼容与隔离验证。
- 本日志及自动生成的AI/logs/log.md：交付记录。

## 已实际执行的验证

Python使用现有完整依赖解释器/root/workspace/apps/releases/omrs-b7225bb/.venv/bin/python，下列命令均先清除OMRS_SYSTEMD_SERVICE；独立浏览器命令同时清除OMRS_TEST_CDP_URL。测试只用临时Vault、随机端口及合成网络边界，不访问真实题库或官方服务。

| 命令 | 实际结果 |
|---|---|
| python -m unittest tests.test_zuoyebang tests.test_zuoyebang_render tests.test_zuoyebang_geometry -q | 43项通过，退出0 |
| python -m unittest tests.test_zuoyebang_service tests.test_zuoyebang_service_http -q | 24项通过，退出0 |
| node --test tests/app/*.test.mjs | 531项通过，退出0 |
| python tests/e2e/zuoyebang.py | 96/96通过，退出0；含手机升级10项、真实滚轮、八档页面、完整图、识别与创建 |
| python tests/app/run_browser.py | 34通过、0失败，退出0 |
| python3 tests/check_ui.py | 全仓0问题，退出0 |
| python3 tests/check_contrast.py | 58组、0不达标，退出0 |
| python tests/visual/run.py --ref 8a39245 --pages create --create-stage zuoyebang --out /tmp/omrs-zyb-mobile-visual | 四组前后对比，0差异、无脚本错误、横向溢出或过小目标 |

标准视觉脚本为未搜题的空工作台，四组0差异符合预期，不作为生成题图的证据。另用真实render_documents逐条渲染三组合成化学题，题图均宽1080，高度699／1119／1035；后两组各有一条长公式局部适配。逐张查看手机显示尺寸的题图及390px旧预览入口截图，公式、正文均完整，无整体缩小或重叠。实际新图与此前现状图同宽对比保存在/tmp/omrs-zyb-mobile-output/comparison.png。

浏览器产物在/tmp/omrs-zyb-mobile-e2e，含checks.json、旧入口320/390px、新预览、题图、完整长答案及合成入库Markdown。专项验证：生成期间刷新后保留最新人工答案、科目分类与错因；只提交一次render，无search；旧record.json和PNG原字节相同；已入库无升级入口。

首轮新增宽公式回归暴露旧nobr文字测量不足，修正后13项正文专项及43项相关组均通过；首轮Node新增用例的创建预留替身缺少合法payload结构，修正替身后全量531项通过。没有把首轮失败记为通过。

已运行python3 tests/check_docs.py --write-log-index生成索引；python3 tests/check_docs.py --diff 8a39245检查146份文档，0问题、3条既有大文件提醒，退出0。git diff --check通过，按git diff --name-status及暂存区逐项核对范围；原validation.json的SHA256保持开工值，未纳入提交。

## 未执行与边界

未执行生产验收、实体手机／摄像头、真实作业帮网络、付费AI或全仓Python回归；本次不修改网关协议、账号配置、正式题目及原像素裁切。生产发布与GitHub推送未执行，当前仅本地实现和验证。
