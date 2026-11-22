# OMRS 2.0.0：审核优先与移动端工作流升级计划

> 状态：已完成源码调查和规划；业务实现、测试、部署均未执行。
> 调查日期：2026-09-29。
> 仓库：RuibinNingh/OMRS；锁定 main 提交 `1d082194ad959aaf6d754a90ed95db9183484adc`，`omrs/version.py` 为 `v1.35.0`。
> 目标发布：`v2.0.0`。执行者建议为 Codex（完整模式）；生产部署另行授权。
> 证据性质：GitHub 源码、同提交模块文档和用户截图的静态核对。没有运行测试、启动网站、测量交互耗时或验证用户设备上的计算样式。文中的尺寸、点击次数和性能要求均为拟定验收目标，不是已测结果。
> 本包是计划文档，不是应用源码包或已经应用的补丁；没有修改远端仓库。

## 1. 任务目标

将 OMRS 从“流程信息很多、用户反复寻找操作”调整为“审核题目、保存入库、随时练习”的工作台。保持现有本地 Markdown 题库、Ledger、草稿数据库、原生 ES Module 前端和训练模型边界，不进行换框架式重写。

用户需求对照：

| 编号 | 用户原意 | 交付点 |
|---|---|---|
| R1 | AI 草稿核心应是审核，手机滚动过长，电脑也费劲 | 审核优先布局、逐题队列、必要时才编辑或框选 |
| R2 | 快速录入截图区不居中 | 修复选择器冲突，并压缩空状态 |
| R3 | 助手不能拖拽文件，自己上传的图片直接跳转 | 聊天主区域可拖图，站内图片预览 |
| R4 | 手机助手别扭、效率低 | 键盘适配、单层头部、紧凑输入、信息折叠 |
| R5 | AI 创建分类、修改草稿；聊天中有不属于正式 Session 的临时练习 | 分类工具、版本化草稿补丁、聊天练习卡 |
| R6 | 删除笔记本页码 | 删除活动入口和新写入；保留不可变历史，不误删备注 |
| R7 | 历史卡片信息量不足 | 面向学习内容的摘要与变化展示 |
| R8 | 题目面板错因等字段自动识别 | 证据化识别、字段级补全、人工优先 |
| R9 | 快速录入不允许 AI 修改标记 | 提示词、响应白名单、前端合并三层禁写 |
| R10 | 下拉、展开列表像浏览器默认样式 | 共享选择器与折叠组件，完整键盘交互 |
| R11 | 助手圆环显示缓存占比，详情显示缓存占比和本次总 token | 明确分母、跨轮累计、缺失值语义和辅助调用统计 |

## 2. 当前背景与约束

### 2.1 已确认的源码事实

1. **草稿信息顺序确实偏向加工而不是审核。** `features/create/drafts-view.js::detailView()` 依次渲染来源图、canvas、字段、内容块。`drafts.css` 已有 sticky 页脚，所以不能把“新增固定页脚”当成主要改进。来源图和训练仍有作用，但不应占据审核首屏。[S1]
2. **截图区存在明确的 CSS 覆盖。** `ui/filedrop.js` 用 `<label class="ui-filedrop">` 包装；组件 CSS 为 flex 居中；`features/create/create.css` 的 `.crw-pane label` 将其改为 grid。`styles/index.css` 中 features 层晚于 ui 层。改后仍须在真浏览器查看 computed style 与截图。[S2]
3. **助手不是完全没有拖拽代码。** `assistant/index.js` 只处理落在 `.ast-composer` 的拖拽；现有接收链路是 PNG/JPEG/GIF 图片，不是任意文档解析器。`openImage` 调用 `window.open`；已发送图片也走外部打开式入口。[S3]
4. **手机版不是完全没有响应式。** 已有抽屉和断点；主要问题在外壳与聊天区域叠层、`100dvh - --ast-chrome` 固定扣高、输入区占位、建议与统计常驻。不能只加一个窄屏 media query。[S3]
5. **分类目前允许在建题时出现新名称。** `classify_question` 提示词允许合适时建议新分类；`creation.py::create_question` 创建分类目录与锚点文件。但 `collect_taxonomy()` 主要从已有题目投影读取分类，因此“显式创建零题分类并在各入口可见”还没有独立闭环。[S4]
6. **AI 草稿工具缺少编辑能力。** `omrs/agent/tools/drafts.py` 有 create/list/get，但没有 update 工具；`get_draft` 的块输出没有完整稳定块标识与编辑所需信息。存储和人工编辑已有 revision/CAS，应复用，不另造无版本接口。[S5]
7. **即时练习已满足不创建正式 Session 的基础要求。** `features/instant/index.js` 从推荐组队列，再向 `/api/feedback` 提交 `IMM-*`；不调用正式调度创建。缺的是接收聊天生成的明确题序与稳定卡片引用。[S6]
8. **“页码”和“备注”同名不同义。** quick 的 `form.note` 通过 create payload 进入 Markdown `页码:` 和 metadata；题卡使用 `page`。反馈的 `note` 是历史备注；draft 图片块 `note` 是说明。不能按 note 全局删。[S7]
9. **快速录入确实会加入 AI 标记。** `quick.js::recognize()` 合并 `data.labels`；`ai_assist.py` 的两个分类模板都要求 labels；`state.js::mergeClassification()` 还会直接改难度，不是所有字段都只补空。[S8]
10. **历史已有时间线和对错色条。** 缺的是可直接阅读的题目/变化摘要；当前详细内容主要是折叠后的 payload 文本。不是从零增加历史功能。[S9]
11. **缓存 token 已经贯通。** `openai_compat.py::_usage()` 读取 OpenAI/DeepSeek 缓存字段，`assistant/state.js` 按 round 累加 cached；检查器已有缓存命中绝对量，没有完整比例/总量表达。`ai_assist.py` 的辅助模型调用目前主要返回文本，不提供同等完整的用量归属。[S10]
12. **v1.35.0 已修复一批重要数据保护问题。** 正文 blob 覆盖、身份校验、入库及收件箱并发、助手迟到请求等是本次需要保护的基线，不能重复宣称这些全部仍未修复。[S11]

### 2.2 不变量

- 题库正文写入仍走现有 creation/content_history/Ledger 链路；草稿保存不等于入库。
- 只有实际练习反馈才增加练习次数、改变熟练度和排期。
- 不伪造用户错因，不把模型建议当成已确认事实。
- 分类、知识点、用户标记、熟练度状态是不同概念；R9 不等于删除全站标记能力。
- 保留草稿修订号、来源图片 SHA 引用、块顺序、人工框优先、独立训练任务以及按版本入库。
- 对话、草稿和练习卡有自己的生命周期；不得把聊天附件、草稿与正式题目的删除混成一个动作。
- 不更换前端框架，不修改 SM-2/熟练度算法，不启动新训练，不引入订阅、账号或云同步系统。

## 3. 最终预期行为

原计划第 3.1–3.11 节的完整内容见 [最终预期行为分册](behavior.md)。

## 4. 分阶段实施计划

每阶段是风险控制与提交边界，不是提前结束交付的理由。最终到 R1–R11 全部通过并形成 v2.0.0 候选发布才结束实现；生产部署另授权。

| 阶段 | 核心任务 | 依赖 | 主要提交切片 | 放行条件 |
|---|---|---|---|---|
| P0 | 基线、契约、夹具、复现记录 | 无 | 计划/基线；契约测试 | 11 项均有对应入口和验收，不覆盖已有工作 |
| P1 | AI 草稿审核工作台 | P0 | 审核布局；编辑与保存入库 | 手机逐题审核、409/失败不丢编辑、训练不被破坏 |
| P2 | 快速录入、字段识别、禁改标记、页码退役、共享选择器 | P0；复用 P1 必要组件 | CSS与控件；识别补丁；页码兼容 | 居中、人工优先、标签不变、旧数据可读 |
| P3 | 助手拖拽、预览、手机交互 | P0；复用共享浮层 | 附件；预览；键盘与布局 | 主消息区可拖、预览不离页、输入法/键盘真机通过 |
| P4 | 分类工具与 AI 编辑草稿 | P1、P2 | 分类领域函数；update_draft | 空分类可见，旧 revision 拒绝，AI 不越权入库 |
| P5 | 聊天练习卡、即时练习接入、反馈幂等 | P3、P4 的工具/事件规范 | 卡片持久化；路由队列；幂等提交 | 无正式 Session，刷新可继续，重试不重复计分 |
| P6 | 历史摘要、缓存与总 token | P3、P5 | 历史读模型；用量归一化；UI | 历史不伪造、完整与部分用量正确、重放不重计 |
| P7 | 全链路、兼容迁移、版本与交付 | P1–P6 | 回归修复；发布元数据 | 所有必验场景通过；发布版本 v2.0.0 |

每个提交包含同一逻辑切片的代码、相关测试、模块文档与 progress 更新。禁止把 11 个需求合成一个大提交后才测试。涉及共享字段或协议时，后端与前端在同一兼容切片内交付；不得留下某中间版本会丢数据的状态。

执行责任：Codex 主代理负责契约、集成和最终门禁；GPT-6 Sol / High 子代理负责阶段实现与对应测试、文档。P3 与 P4 可在隔离工作树中并行推进无共享文件的切片，但按 P3、P4 顺序集成；P5 在两者工具及事件契约集成后实施，P6 在 P5 后实施，P7 最后验收。共享文件冲突由主代理逐项合并并重跑门禁，不以并行开发改变上表的依赖、停止条件或验收标准。

## 5. 关键技术决策汇总

| 问题 | 默认决策 |
|---|---|
| 是否换 React/Vue 或构建系统 | 不换，保留 assets/app 原生模块及现有 morph/路由 |
| 草稿是否自动入库 | 不。AI 可修订待审草稿，正式写入仍审核 |
| 是否删除训练能力 | 不。降低默认界面权重，保留来源与标注不变量 |
| 快速录入是否保留 AI 标签开关 | 不增加开关；此入口禁止 AI 改标签，手动能力保留 |
| 无依据错因如何处理 | 留空或待采纳建议，不自动落成事实 |
| 空分类如何存储 | 提取现有目录/锚点实现，统一词表读取；不引入平行数据库 |
| 独立新分类是否确认 | 默认确认；草稿中的分类建议随入库审核 |
| 临时练习是否写 sessions.csv | 不写，卡片和进度归属聊天，真实反馈仍进 Ledger |
| 是否新增一套练习 UI | 不新增，扩展现有 instant 的显式题序加载 |
| 是否把所有旧页码物理抹除 | 不在默认升级破坏旧正文/历史；活动功能和新写入彻底移除 |
| 拖拽是否等于任意文档解析 | 否，本次明确支持现有图片范围；其他格式清楚报错 |
| token 缺失是否显示 0 | 不，区分实测、估算、部分与未知 |
| 版本号与存储 schema 是否同一件事 | 不，应用升级 v2.0.0；存储迁移独立版本、幂等执行 |

## 6. 边界情况与风险登记

| 情况 | 必须行为 |
|---|---|
| 人工草稿脏数据遇到 AI 更新 | 保留本地输入，提示新版本并展示冲突，不热替换 |
| AI 修改草稿碰到 done/discarded/入库中 | 拒绝；不反向恢复成 review |
| 同一来源图被多个草稿使用 | 保留 SHA 引用及人工框优先，不合并成错误训练真值 |
| 保存成功、commit 响应丢失 | 重试复用同一入库操作，不另建 UID |
| 待发送图片读取时切换会话 | 丢弃旧 generation 的写回，不附到新会话 |
| 拖入 URL、文字或不支持文件 | 不误判图片；不触发非预期导航或悄悄消失 |
| 软键盘、横竖屏、浏览器地址栏变化 | 输入仍可见、可关键盘，消息区不出现永久空白 |
| 中文候选词确认 | 不触发发送/选项提交 |
| 分类重名/非法路径/锚点已存在 | 幂等或明确拒绝，不覆盖既有文件 |
| 练习卡部分题目删除或停用 | 说明不可用项，保留其余原顺序，不静默换题 |
| 练习提交部分成功 | 仅成功项锁定；失败项保留并可重试 |
| 练习提交落账后进度写回失败 | 以 Ledger 稳定提交身份恢复，不重复反馈 |
| 聊天删除 | 禁止重新开启卡片；真实练习历史不删除 |
| 使用旧对话/旧 usage 事件 | 不崩溃，不能确定的缓存字段显示未知/历史不完整 |
| 只返回部分调用的 usage | 显示已知总量与统计范围，不伪称全量 |
| 历史分页后的撤销链 | 仍使用全链状态，不能因目标不在当前页而错误恢复 |
| 升级遇到旧页码 | 活动读写忽略，保留历史证据；备注不受影响 |
| 版本升级后回退 | 代码可回退不等于数据可降级；有 schema 不兼容则使用备份或明确的降级方案 |

## 7. 修改范围

### 7.1 已定位、预计涉及的现有文件

- 草稿：`assets/app/features/create/drafts-view.js`、`drafts.css`；同目录控制器与状态逻辑按调用链修改；`omrs/drafts.py`、`omrs/draft_write.py` 的 revision/保存/commit 公共入口。
- 快速录入与题卡：`assets/app/features/create/quick-view.js`、`quick.js`、`state.js`、`create.css`、`cards-view.js`、`cards-state.js`；相关控制器；`omrs/ai_assist.py`、`omrs/creation.py`、`omrs/inbox.py`。
- 助手：`assets/app/features/assistant/index.js`、`view.js`、`state.js`、`insp-view.js`、`assistant.css`、`assistant-side.css`、工具结果卡渲染；外壳样式只做助手模式所需调整。
- AI 与存储：`omrs/agent/tools/drafts.py`、工具注册入口、`read.py`、`runtime.py`、`policy.py`、`store.py`、`http.py`、`prompts/` 下实际使用的系统提示文件；`omrs/llm/openai_compat.py`、`omrs/ai_assist.py`。
- 即时练习：`assets/app/features/instant/index.js`、`state.js`、`view.js`；路由与 handoff；`omrs/feedback.py`、必要的 Ledger 幂等索引/投影逻辑。
- 历史：`assets/app/features/history/`、`assets/app/domain/history.js`、`history-model.js`；历史 API 的摘要与分页实现位置先沿 `/api/history` 定位。
- 版本与文档：`omrs/version.py`、根 README 的实际版本展示位置、`AI/README.md`、`AI/changelog.md`、受影响模块文档与路由/日志索引。

### 7.2 拟新增模块（不是当前已经存在）

`ui/image-viewer`、共享 combobox/折叠辅助组件、分类领域模块 `omrs/taxonomy.py`、聊天练习卡领域/工具模块、用量归一化辅助模块、针对本计划的新测试。名称可按仓库现有约定调整；契约不可随意变更。

### 7.3 必须完成

R1–R11 的可见主路径、人工编辑保护、反馈幂等与部分成功、旧数据兼容、真实浏览器验证和 v2.0.0 发布元数据。

### 7.4 可以顺手处理

只限同一行/同一组件直接相关的无效占位、错误 aria 文案、重复图片 URL 未释放、completion=0 的统计处理等。不借机跨项目整顿。

### 7.5 本次不要处理

训练新模型或自动发布模型、改调度算法、换数据库/前端框架、通用文件解析器、订阅/支付/账号系统、全站主题重画、自动改 CLMS、未经授权的批量正文清理、生产重启/推送/服务配置修改。

## 8. 验收标准

### 8.1 用户操作验收

- 草稿首屏可以看到当前题干内容或明确阻塞原因；不必先滑过训练与原始大图。
- 手机完成“查看题目 → 查看答案 → 必要修改 → 入库 → 下一题”时，不需要为寻找操作按钮来回滚长页面。
- 框选已正常的草稿不强迫再次进入框选；训练未完成不误阻断满足入库条件的纯文本草稿。
- quick 空状态图标和文案中心轴一致；答案可选；paste target 清晰。
- 手工标记集合在任何 quick AI 调用前后逐项相同，包括模型返回异常 labels 和清空数组时。
- 题图中明确写有错因时有来源可核对；没有错因时不自动写“粗心”。
- AI 调用过程中用户改过的难度、分类、错因不会被迟到响应覆盖。
- 待发送图和历史图点击均站内预览，关闭后回原位置；消息区可拖图。
- 360/390/430 宽手机与 768/1024/1440 宽视图无页面级横向溢出；长公式允许题面局部滚动。
- 手机真实软键盘开启、候选词确认、发送、关键盘、横竖屏切换都正常；不能只用缩小桌面视口验收。
- 草稿编辑工具处理旧 revision 返回冲突，原内容和人工框不损失；入库后拒绝改草稿正文。
- 新建零题分类在分类候选中可见，重复请求不重复创建，跨科目同名不串用。
- 聊天卡开始练习保持题序，sessions.csv 和正式 Session 数不变化；创建卡片与打开卡片不增加 Attempts。
- 实际练习提交后存在真实反馈；双击、刷新重发、响应丢失重试均只增加一次 Attempts。
- 一批 3 题中 1 题服务端报错时，只锁定 2 题成功项。
- 新题 Markdown 不再输出 `页码:`；quick/题卡无页码入口；反馈备注和图片说明照常保留。
- 历史默认显示题目/动作/结果而非只有技术 ID；分页与筛选不破坏撤销/恢复。
- 两轮 1000/9000 输入、0/9000 缓存、500 输出示例得到 90% 与 10500；重放结果一致。
- 无缓存字段显示“未知/未返回”；明确 0 显示 0%；没有最终 usage 的中断显示部分/估算。
- 辅助调用有单独归属；只在有完整统计时标“本次总量”，否则标“已知总量”。

### 8.2 量化与对比

在 P0 固定同一组纯文本、图文混排、长答案、框选待确认、缺错因、共享来源图、多轮 AI 的夹具。记录改前改后的完成时间、寻找控件的滚动次数、点击数、首屏内容、页面横向溢出和错误。不同任务难度分组比较，不混用一张短题和另一张长题宣称速度提升。

拟定最低 UI 条件：360px 宽可操作，触摸主按钮目标至少 44×44 CSS px；200% 缩放不丢动作；默认空输入不占多行；关键确认不只依赖颜色。不要通过缩小正文文字达成所谓高信息密度。

## 9. 验证步骤

以下是实施阶段的命令，不代表本次已经运行。执行前核对当前仓库脚本路径；若基线更新导致脚本变化，记录替代命令，不编造通过计数。

```bash
# 保护工作区与隔离生产环境
git status --short
git log --oneline -15
unset OMRS_SYSTEMD_SERVICE

# 现有基础门禁
python3 -m unittest discover -s tests -p 'test_*.py' -q
node --test tests/app/*.test.mjs
python3 tests/check_ui.py
python3 tests/check_contrast.py
python3 tests/app/run_browser.py

# 已存在的相关主路径 E2E
python3 tests/e2e/assistant.py
python3 tests/e2e/instant.py
python3 tests/e2e/feedback.py
python3 tests/e2e/history.py
python3 tests/e2e/questions.py
python3 tests/e2e/shell_router.py

# 前后视觉与空数据审计；BASE 取开工后确认的真实基线
BASE=1d082194ad959aaf6d754a90ed95db9183484adc
python3 tests/visual/run.py --ref "$BASE" --out /tmp/omrs-v2-visual
python3 tests/visual/run.py --audit-only --fixture empty --out /tmp/omrs-v2-empty

# 完整仓库中做文档收尾；按实际接口变化生成路由表
python3 tests/check_docs.py --write-routes
python3 tests/check_docs.py --write-log-index
python3 tests/check_docs.py --diff "$BASE"
```

为 R1/R2/R8/R9 增加专门的草稿/快速录入 E2E，为 R5 增加跨聊天到 instant 的路由、恢复及反馈幂等测试，为 R11 增加 provider usage、未知字段、辅助调用、重复事件测试。新脚本路径在对应实现提交中确定并加入执行记录。

浏览器测试必须在临时 Vault、随机高端口运行。真实模型验证使用专用测试配置和明确调用预算；大多数错误场景先用已有 faux 模型脚本覆盖。真机至少覆盖 Android Chromium 与 iOS Safari 的软键盘行为；若执行环境没有相应设备，要明确列为未验收，不用桌面模拟假装通过。

发布前备份真实 Vault 必须一致性完成：业务写入静止或使用数据库在线备份方式；不能在 SQLite 写入中只复制一个主文件遗漏 WAL。备份正文、附件、Ledger、agent.db、drafts、配置和分类锚点；必须演练恢复。存储格式变化先在副本升级，重复升级不重复迁移；失败不破坏原副本。

最终将 `omrs/version.py` 保持现有前缀约定改为 `__version__ = "v2.0.0"`，同步 README、AI/README、changelog 与相关页面读取链路；不要全仓替换历史日志里的 v1.*。版本展示/API/导出元信息实际引用点逐一核验。数据库迁移版本不直接用应用显示版本替代。

## 10. 执行原则、停止条件与交付

开工先复核 main 与本计划基线差异，保留用户未提交改动；以现代码为准，不用截图推断用户部署一定仍是旧版。计划指定的目标、权限边界和验收不能被实现者自行删减；实现命名与内部拆分可调整并记录理由。

仅在以下情况停止并请求决策：发现用户工作区冲突无法安全合并；必须对真实数据进行未授权不可逆清理；实际存储/鉴权与本计划前提根本不同；需要新增未批准的强制依赖或扩展到通用文档解析；只有修改调度算法才能通过现有测试；生产操作没有授权。普通阶段完成、无网络真实模型或单个测试失败不是询问“是否继续”的理由，继续可执行工作并明确未验收项。

中断时记录最新提交、当前阶段、未提交路径、已运行和未运行测试、待解决失败与下一步；下次从 progress.md、git status 和最近提交恢复，不能从头整目录覆盖。

交付报告列：每项 R 的完成入口、提交哈希、真实验证结果、未验证项目、兼容/迁移结果、遗留问题、目标版本。只有全部要求与发布验收满足，才称“2.0.0 已完成”。本计划交付不表示已经实现、发布或部署。

---

## 源码证据索引（全部固定在本文件头部提交）

| 标记 | 已阅读的关键位置 |
|---|---|
| S1 | `assets/app/features/create/drafts-view.js` 175–248：detailView 顺序与操作；`drafts.css`：sticky 与窄屏布局；`AI/drafts.md`：状态/修订/训练分离 |
| S2 | `assets/app/ui/filedrop.js`、`filedrop.css`：label + flex；`assets/app/features/create/create.css` 1–125：label 覆盖；`assets/app/styles/index.css`：层顺序 |
| S3 | `assets/app/features/assistant/index.js` 175–290、315–445：附件异步、拖拽、openImage；`view.js` 166–末尾：输入与 meter；`assistant.css`、`assistant-side.css`：断点与输入布局 |
| S4 | `omrs/creation.py` 185–300：目录/锚点；`omrs/ai_assist.py` 1–100、345–465：词表与新分类；`omrs/agent/tools/read.py` 1–100：taxonomy 工具 |
| S5 | `omrs/agent/tools/drafts.py` 1–135：get/create/原话校验；`AI/drafts.md`、`AI/agent.md`：update/commit/CAS/权限；`omrs/agent/policy.py` |
| S6 | `assets/app/features/instant/index.js` 1–180：载入与提交；`AI/frontend/instant.md`；`omrs/feedback.py` 1–170：逐条结果与落账；`omrs/agent/store.py` 1–170：消息/工具持久化 |
| S7 | `assets/app/features/create/quick-view.js`；`state.js`：note；`cards-view.js` 与 `cards-state.js`：page；`omrs/creation.py` 130–170、185–300：页码；`omrs/common.py` 1–65：历史 Note |
| S8 | `assets/app/features/create/quick.js` 1–170：AI label 合并；`state.js::mergeClassification`：难度写回；`omrs/ai_assist.py` 205–355、345–465：labels 模板与共享调用 |
| S9 | `assets/app/features/history/view.js` 1–145；`AI/frontend/records.md`：时间线/修正状态；`assets/app/domain/question/view.js` 1–110：现有 qview 展示与工具 |
| S10 | `omrs/llm/openai_compat.py` 1–170：_usage；`assets/app/features/assistant/state.js` 1–130：累计；`insp-view.js`：缓存绝对量；`view.js` 166–末尾：context ring；`omrs/ai_assist.py` 205–330：辅助调用文本返回 |
| S11 | `AI/changelog.md` 1–50：v1.35.0 已完成修复；`omrs/version.py`：版本真源 |
| S12 | `AGENTS.md` 1–220；`AI/README.md`；`AI/environment.md` 1–135：工作边界、计划结构、隔离测试与门禁 |
| S13 | `assets/app/ui/select.js`：原生 select；`cards-view.js`、`quick-view.js`：datalist；`assets/app/styles/ui.css`：现有共享组件入口 |

外部协议核对：OpenAI 官方 Chat Completions 用量/流式 usage 文档、OpenAI Prompt Caching 文档、DeepSeek 官方 Context Caching 字段文档、MDN VisualViewport 文档。实施时沿现有客户端协议核对，不借此加入新 API 迁移或缓存优化项目。
