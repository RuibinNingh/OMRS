# 2026-10-12 作业帮取图搜题与自动预览

## 背景

执行者Codex，完整模式。用户要求合并搜题和拍照、将原搜题图片块换为候选、选择候选自动渲染、摄像头/上传可切换并支持粘贴；批准交互草稿后要求「执行」。原话与实施边界在AI/plans/zuoyebang-search-ui/plan.md。

开工基线9509251。工作区已有index.js、zyb-camera.js、zyb-state.js、zyb-view.js、zyb.css五份相关半成品，保留并接续；原始差异备份在/tmp/omrs-zyb-search-99w2e26l/initial.patch。同期网关面板任务独立完成0bf977c；本次只提交OMRS录入工作区及相关文档/测试，不改该任务业务文件。原文档中「相机只预览、候选需再点渲染」与本轮目标冲突，已同步为当前行为。版本仍为v2.5.0。

## 行为变化

- 「取图搜题」内部切摄像头/上传；拍照按视频实际分辨率取帧为JPEG，不按CSS宽度缩图，拍后保留原图、释放设备并搜题。服务未就绪时可先拍照保留，不因网关状态禁止本地取图。
- 上传支持选择、拖放、粘贴按钮和Ctrl/⌘+V；复用原始文件与8MiB校验。剪贴板失败给键盘替代提示；不拦截表单输入的粘贴，切模式/离页后的异步结果不会覆盖新来源。
- 原图片块改为单列候选；初始不选择第一项，点击候选即自动渲染题干/答案。渲染中可继续切换，只排队最后选择；旧结果不显示到新候选，失败保留来源和重试入口。
- 桌面保留右预览440px与左侧弹性布局，取图和候选并排；手机顺序阅读。已有图片时上传入口缩为紧凑区域，主拍照/搜题按钮铺满可用操作行；触摸取图按钮与候选至少44px高。
- 既有人工编辑确认、AI提取防覆盖、历史与幂等入库保持；新模式和渲染冻结上下文随sessionStorage恢复，不存凭据或图片字节。

## 影响文件

按最终git diff --name-status复核：

- assets/app/features/create/：index.js登记三个入口；zyb-camera.js负责取帧和取消；zyb.js连接来源、剪贴板与自动渲染队列；zyb-state.js初始未选候选；zyb-view.js/zyb.css实现合并布局、加载/失败与触摸状态。
- tests/app/create-zyb.test.mjs：原始尺寸、无帧、空编码、编码取消、网关未连接仍可本地取图；tests/e2e/zuoyebang.py：真实MediaStream拍照、粘贴、最后选择、失败重试及既有完整主路径。
- README.md、AI/frontend/create.md、AI/frontend/design-system.md、AI/frontend/architecture.md、AI/zuoyebang.md：同步现状。
- AI/plans/README.md、AI/plans/zuoyebang-search-ui/：独立计划与完成进度；本日志及自动生成索引。

## 已实际执行的验证

所有服务测试移除OMRS_SYSTEMD_SERVICE与OMRS_BOXDETECT_CONTROL，使用临时Vault和随机高端口；摄像头专项还移除OMRS_TEST_CDP_URL，使用独立Chromium的fake-device真实MediaStream。作业帮/AI上游为合成响应，HTTP上传、PNG渲染、文件与Ledger创建实际执行。

| 命令 | 结果 |
|---|---|
| node --test tests/app/*.test.mjs | 496项通过，0失败/跳过；其中作业帮15项 |
| python3 tests/app/run_browser.py | 34项通过 |
| python3 tests/e2e/zuoyebang.py | 63/63通过，含8档页面及账号菜单审计 |
| python3 tests/e2e/create.py | 124/124通过 |
| /root/workspace/apps/releases/omrs-zyb-deps-20261011/.venv/bin/python -m unittest tests.test_zuoyebang tests.test_zuoyebang_render -q | 33项通过 |
| python3 tests/check_ui.py | 全仓0问题 |
| python3 tests/check_contrast.py | 58组通过 |
| python3 tests/visual/run.py --ref 9509251 --pages create --create-stage zuoyebang | 4组前后截图；无脚本错误、横溢、行内样式或过小目标 |
| python3 tests/check_docs.py --write-log-index | 已生成日志索引 |
| python3 tests/check_docs.py --diff HEAD | 115份文档，0问题，2条既有大计划文件提醒 |
| git diff --check | 通过 |

首次浏览器验收发现开启状态用了组件库不存在的close图标，导致状态渲染中断；改用x并补回归。失败注入测试最初在route回调内移除自身，触发Playwright已处理路由错误；改为观察失败后移除，重试路径最终通过。默认python3后端33项中有1项因缺少segno失败；使用已安装的完整依赖环境重跑33项全通过，未修改依赖或生产环境。

提交前复核本任务差异及日志索引，未纳入网关面板文件。没有运行全量Python套件；本轮未改后端，相关33项与真实页面链路覆盖改动边界。

## 视觉对比与产物

产物保存在/root/.codex/artifacts/omrs-zyb-search-ui-20261012/，包含visual/report.html、audit.json、前后截图/差分、桌面/手机结果截图及门禁日志；测试运行目录为/tmp/omrs-zyb-search-99w2e26l/。

| 对比 | 像素差异 | 原因 |
|---|---|---|
| 浅色桌面 | 3.447% | 合并取图区、候选移入原图片位置、来源切换/粘贴及主按钮布局更新 |
| 深色桌面 | 3.729% | 与浅色相同的结构变化，沿用全站主题token |
| 浅色手机 | 20.318% | 合并来源块后整页高度与后续候选/预览位置变化，控件上下排列 |
| 深色手机 | 22.586% | 与浅色手机相同的重排与高度变化，未改主题对比度 |

有题图的8档截图进一步核对候选、1080预览、人工编辑与账号菜单；所有页面/菜单在320、390、1024、1440px及浅深主题中无横向溢出。

## 未执行与后续

未连接真实作业帮官方账号、未调用付费模型、未使用实体手机相机验收；模拟媒体覆盖浏览器取帧与释放生命周期，不能代替硬件兼容验证。未推送、部署、重启生产、修改systemd/Nginx或真实题库。本轮源码目标完成，后续真实账号与设备验收由维护者在相应环境进行。
