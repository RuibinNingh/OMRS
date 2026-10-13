# 2026-10-13 AI 助手权限模式与对话优先界面

## 背景

用户原话：

> 改一下AI助手,允许选择权限模式
> 默认是手动,可以切换危险模式和滞留模式
> 滞留模式默认会把这个滞留到审核中心,如果手动模式长时间不同意直接移到审核中心
> 危险模式会自动同意全部请求
> 先重设计一下UI,给我个草稿

用户确认手动等待时限为「10 分钟（推荐）」，选定「对话优先」草稿后要求「执行吧」。执行者为 Codex，运行模式为完整模式；本任务不属于既有执行说明，版本保持 v2.6.0。

开工基线为 4413aec，已有框选服务相关改动的基线补丁保存在 /tmp/omrs-assistant-permissions-initial.patch。该独立任务随后提交为 4cef0fe，本任务保留它的改动并以 4cef0fe 做最终文档和视觉比较；本次提交只纳入助手权限相关路径。

## 行为变化

输入框左下角常驻权限菜单，手动为默认，滞留直接送审，危险自动同意全部确认级请求；危险入口及说明持续使用红色语义。每个对话独立保存模式，刷新恢复，新对话默认手动。模式切换期间禁止发送，迟到响应不进入别的对话。桌面对话列表和运行检查器默认收起，头部保留展开、新对话和运行详情入口；手机菜单在可见视口内布局，权限入口至少 44px。

手动请求在聊天中确认或拒绝，可主动送审；等待 600 秒后自动移交审核中心。滞留直接移交，释放模型线程并继续聊天。送审保持同一操作、版本、来源、摘要、快照和世代，取消聊天期限，长期保留待审。切到滞留会移交当前未决请求，切到危险会自动批准当前对话未决请求；切回手动不拉回中心待办，已完成决定不改写。

审核中心可在原模型运行结束或普通服务重启后修订、批准、拒绝助手提案；批准复用原工具执行链和原运行来源，不新建模型运行。执行回执追加到原运行，同步实际写入统计与撤销入口，重复刷新不重复计数。正式正文、知识点及整批标记写入另核对绑定操作、版本、摘要、世代和来源的内部许可，仅有 applying 字段不能授予写权限。

危险自动批准仍遵守现有工具注册、预算、目标快照和题库世代。审批库记录服务端派生的模式设置来源及自动决定身份；模型不能切换模式，MCP 的独立人工确认规则保持。普通重启把新模式聊天等待送审并保留中心待办，整库恢复废止全部未终结许可。

## 实现与回归修复

- 新增权限模块及三条 Web 路由，旧对话库独立补齐两个模式字段，审批库补 permission_json；旧 MCP 只读记录缺少该字段时返回空权限对象。
- 手动到期视图仍保留在待审队列，草稿入库提案在移交窗口仍去重；不先变成不可批准的 expired。
- 历史导入不把 deferred 当作已执行或无变更证据，解决长期待审在重启时错误收束的问题。
- 超时线程收尾晚于中心批准时保留真实回执，返回当前实际状态；停止先于移交时取消聊天请求，迟到决定或模式切换不能恢复执行。
- 中心首次批准与单例初始化统一锁序；助手状态 GET 只读配置及已有运行，不创建数据库，写锁繁忙时仍返回状态。
- 送审预占运行写预算，实际写入只计真实执行。原助手浏览器测试通过显式展开列表及选择可见的新对话入口适配布局。

## 影响文件

- 后端：omrs/agent/permissions.py、runtime.py、http.py、policy.py、loop.py、store.py、prompts/system.md，omrs/ai_review.py、omrs/http/registry.py；覆盖模式、持久审批、独立执行与回执。
- 前端：assets/app/features/assistant/permissions.js、assistant-permissions.css、assistant.css、index.js、view.js、state.js、review-cards.js，assets/app/features/ai-review/operation-view.js、assets/app/styles/index.css；覆盖菜单、布局、送审状态、真实回执及共享详情。
- 测试：新增 tests/test_agent_permissions.py、tests/app/assistant-permissions.test.mjs、tests/e2e/assistant_permissions.py；更新原助手循环、草稿、审批和页面回归。
- 文档：AI/agent.md、ai-review.md、api.md、api/extensions.md、data.md、data/storage.md、security.md；AI/frontend/assistant.md、ai-review.md、architecture.md、design-system.md；根 README.md、自动路由及日志索引。

## 已实际执行的验证

所有服务与业务测试使用临时 Vault、随机高端口，移除 OMRS_SYSTEMD_SERVICE 和 OMRS_BOXDETECT_CONTROL，不访问真实错题库。浏览器使用真实 Chromium 与可重复的假模型；超时场景仅在隔离测试进程缩短指定调用等待，默认 600 秒另有断言。

| 命令 | 结果 |
| --- | --- |
| env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL /tmp/omrs-permissions-venv/bin/python -m unittest discover -s tests | 全仓 994 项通过，0 失败、0 错误 |
| python3 -m unittest tests.test_agent_permissions tests.test_agent_review tests.test_agent_loop | 最终并发与模式回归 40 项通过，其中权限用例 19 项 |
| node --test tests/app/*.test.mjs | 502 项通过，0 失败 |
| python3 tests/app/run_browser.py | 34/34 通过 |
| python3 tests/e2e/assistant_permissions.py | 27/27 通过；五档宽度、浅深主题、超时移交、模式切换、重启、中心批准/拒绝及撤销入口 |
| python3 tests/e2e/assistant.py | 59/59 通过，含原聊天写入、拒绝、撤销、草稿和手机图片流程 |
| python3 tests/e2e/assistant_review.py | 28/28 通过 |
| python3 tests/e2e/ai_review.py | 47/47 通过 |
| python3 tests/check_ui.py | 0 处问题 |
| python3 tests/check_contrast.py | 58 组，0 失败 |
| python3 tests/check_docs.py --write-routes；--write-log-index | 路由表及日志索引生成成功 |
| python3 tests/check_docs.py --diff HEAD | 117 个文档，0 处问题；3 条体积提醒来自既有计划和根 README |
| git diff --check | 通过 |

初次全仓 Python 回归暴露旧 MCP 字段兼容和只读状态查询两处问题，已修复；另因系统 Python 缺少 Segno 无法运行既有扫码测试。在 /tmp/omrs-permissions-venv 建带系统依赖的临时虚拟环境，安装仓库声明的 segno==1.6.6 后，992 项全仓检查通过。补充并发用例后的全仓复跑为 994 项通过；送审终态说明及两列独立迁移的小调整后，再运行相关 40 项，全部通过。

cloud-environment 运行技能用于核对测试环境；当前会话未提供 environment_status 工具，执行器也没有网络策略文件。依赖使用继承的网络与证书设置安装到临时虚拟环境，没有改系统 Python 或仓库依赖。

## 视觉比较

实际执行 python3 tests/visual/run.py --ref 4cef0fe --pages assistant,ai-review --out /tmp/omrs-permissions-visual-final。报告位于 /tmp/omrs-permissions-visual-final/report.html；8 组截图均无页面脚本错误、横向溢出和行内样式。

| 页面 | 差异 | 原因 |
| --- | --- | --- |
| assistant-light-desktop | 3.631% | 默认隐藏对话栏，增加头部新对话入口和输入区权限菜单、模式说明，空状态按所选模式说明确认级操作 |
| assistant-dark-desktop | 3.658% | 同一布局改动在深色主题中的对应差异 |
| assistant-light-mobile | 3.141% | 手机权限入口和规则说明、紧凑输入栏，头部保留对话入口 |
| assistant-dark-mobile | 2.944% | 同一手机改动在深色主题中的对应差异 |
| ai-review 浅深色桌面/手机 | 0% | 固定草稿截图没有助手权限上下文；助手提案的新详情由三模式浏览器路径实际验证 |

已人工查看最终桌面及手机截图；权限菜单截图在 /tmp/omrs-permission-shots。早期视觉报告中对话栏被 .ast-card 的 display 覆盖，已用助手范围的隐藏规则修复，最终比较以本节报告为准。

## 未执行的验证与下一步

未调用真实模型供应商：主流程使用假模型固定审批工具输出，避免测试依赖外部服务和付费调用。未进行生产部署、重启、systemd、Nginx 或远端推送：本次授权为本地实现，没有生产变更授权。权限功能没有已知阻塞项；本地提交完成后可在助手输入框左下角使用，生产发布由维护者另行安排。
