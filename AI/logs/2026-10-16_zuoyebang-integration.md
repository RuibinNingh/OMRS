# 2026-10-16 作业帮整卷改造与维护修复合入

## 背景

用户在了解原有作业帮改造尚未提交、两行维护修复仅以最小补丁保存后，要求「那提交吧」。执行者Codex，完整模式；基线2306363。提交前60个路径均属于该改造，39个源码／测试路径与上一轮合成验收副本逐字节一致；没有新增运行代码变化。用户已要求真实环境验收先跳过。

## 行为与提交范围

将已有作业帮整卷工作台完整纳入版本控制：独立侧栏页面、原图及上游题框、逐题候选、移动／缩放、原像素裁图、编辑与刷新恢复。共用分类表单移至domain层，后端与独立网关保留坐标解码和原图存储，录入页维持五个工作区。

R07新题标记选择器和R08加展示板的两行修复随完整zyb.js纳入，已完成的标记保存／入库、浮层锚点及Shift最近使用板行为保持。既有preserved-wip.patch保留为历史恢复材料，当前源码不再需要单独打补丁。

## 影响文件

按git diff --name-status复核：features/create旧作业帮模块迁入features/zuoyebang，配套main／HTML／样式、domain/create-form.js、omrs/zuoyebang及HTTP、网关vendor与元数据、Node／Python／E2E／视觉兼容脚本。原有AI模块、README、AGENTS映射、版本与历史日志同步纳入；原已写好的v2.8.0标记保持，不另加版本。本次新增任务日志与计划授权记录，同步optimization的源码跟踪状态，日志索引由脚本生成。所有已忽略生成物及截图留在磁盘，不纳入提交。

## 验证

本次实际执行：

- 完整依赖解释器运行tests/run_gates.py --ref 2306363 --groups ui --only node,discipline,contrast：Node529/529，UI及对比度检查通过，均无skip。
- 同解释器运行python -m unittest discover -s tests -p 'test_zuoyebang*.py' -q：72/72通过；保留非致命ResourceWarning日志。
- OMRS_TEST_CDP_URL指向已确认的本机Chromium运行python tests/app/run_browser.py：34/34通过，只关闭本轮上下文。
- python tests/visual/run.py --ref 2306363 --pages create --create-stage zuoyebang：4组前后比较完成，无脚本错误或整页横溢，已查看前后桌面／手机图片。

视觉逐项解释：浅色桌面6.281%、深色桌面7.57%，来自作业帮迁出录入导航、侧栏入口及版本文字、默认上传与左右两栏；浅色手机33.825%、深色手机40.237%，来自取消录入阶段导航、原图／核对区纵排及页面高度变化。均为本次纳入的既有独立页设计，没有新增运行代码修改。

证据目录/tmp/omrs-zuoyebang-commit-20261016，含完整命令、退出码、源码保全核对及视觉报告。上一轮同源码的根1039、服务／网关联调及16项受影响E2E等结果保留在维护validation.json，原始失败与重跑不改写；本次不把复用结果称为重跑。python3 tests/check_docs.py --diff 2306363通过：146份文档、0问题、3条既有体积提醒。git diff --cached --check及git diff --check通过；暂存源码与已验证字节一致，已忽略生成物仍在磁盘且未入索引。

## 未执行与下一步

Windows、实体摄像头、真实供应商／账号、付费模型与冻结检测推理按用户要求暂跳过；没有推送、部署或生产服务操作。R14独立场景来源／授权仍需可信材料，与本次作业帮合入无关。
