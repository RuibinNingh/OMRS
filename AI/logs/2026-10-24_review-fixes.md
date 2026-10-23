# 2026-10-24 全面审查问题修复与发布

> **任务**
> - 标识：review-fixes
> - 状态：进行中

## 背景

用户原话：「执行一下修复」「提交GitHub部署生产」「版本+0.0.1」。承接本聊天确认的六个问题，执行者Codex，完整模式，全程不委派子代理。本任务独立于已交付的旧审计与维护计划。开发基线162532f，版本v2.8.4；目标v2.8.5。生产实际基线另行预检，不以开发版本推定线上状态。

开工已有AI/plans/omrs-maintenance/validation.json改动，保留且不纳入提交或发布；原SHA-256和补丁存于/tmp/omrs-fixes-20261024-0xxk0wzu/baseline.json及preserved.patch。用户已明确授权GitHub推送和生产部署，验证仍只使用临时Vault与随机高端口，并清除生产控制环境变量。

## 行为变化

1. 普通即时练习首次提交生成安全随机practice_round_id，以轮次／question_id将完整回执和反馈、投影同事务保存。同轮批内重复、并发和丢响应重试只计分一次，失败项可重试，新轮允许再次作答。回执同步首次接纳的判定与分数，避免断网后改判被误显示为成功。旧客户端省略字段时保留原重复作答语义。
2. 推荐接口接收label_mode=any/all，在排序和题数截断前筛选；即时练习同步「全部命中」选项，非法匹配方式返回400。
3. 标记与知识点列表用JSON字符串编码生成YAML双引号值，完整转义引号、反斜杠与控制字符，创建、保存及扫描保留原名称。
4. 无候选的调度返回HTTP200及完整empty结果，不创建Session或反馈。
5. Chat Completions流提前EOF、坏JSON或未知结束原因均返回error，AgentLoop不执行该轮工具；length继续走原截断流程。显式finish_reason或[DONE]可正常结束。
6. Chat与Responses中止已建立响应时shutdown底层socket，由请求线程关闭响应，避免停止接口争用缓冲读取锁。连接建立和响应头到达之前的取消时机不在本修复范围。

版本v2.8.4升至v2.8.5。生产预检确认为v2.8.3、omrs-f56c21d；将发布当前main的精确提交，包含此前已提交但尚未上线的v2.8.4展示板空态、审核中心自适应双栏及诊断维护改动，不把发布范围误记成只有六个补丁。

## 影响文件

已按git diff --name-status复核：omrs/feedback.py、http/learning.py、http/core.py、scheduling.py、sessions.py、question_ops.py、creation.py、llm/openai_compat.py实现六项修复；assets/app/features/instant/index.js与state.js同步轮次身份、回执和筛选。

tests/test_instant_feedback.py、test_llm_chat.py新增事务／并发／慢SSE故障回归；test_labels.py、test_http_boundaries.py与tests/app/instant*.test.mjs、tests/e2e/instant.py扩充真实接口及浏览器路径。omrs/version.py、omrs_dashboard.html、README.md、AI/README.md同步版本，AI/changelog.md记录行为；AI/agent.md、algorithm.md、api.md、api/mutations.md、api/queries.md、data.md、ledger.md、labels.md、frontend/instant.md、frontend/architecture.md同步当前契约；本日志与脚本生成的AI/logs/log.md留痕。AI/environment.md待生产切换完成后更新实际事实。

## 已执行验证

证据目录：/tmp/omrs-fixes-20261024-0xxk0wzu。Python使用/root/workspace/apps/releases/omrs-zyb-deps-20261011/.venv/bin/python；所有回归清除OMRS_SYSTEMD_SERVICE、OMRS_BOXDETECT_CONTROL、OMRS_TEST_CDP_URL，使用临时Vault、随机高端口和独立Chromium。

- 后端：-m unittest discover -s tests -p 'test_*.py' -q，1122项全部通过，175.831秒，无跳过，见backend.log。此前定向tests.test_instant_feedback、test_llm_chat、test_labels、test_recommendations、test_http_boundaries、test_maintenance_backend共60项通过，见targeted.log。
- 前端：node --test tests/app/*.test.mjs，562项通过、0失败，见frontend.log；此前即时练习13项定向通过，见instant-node.log。
- 组件：tests/app/run_browser.py，35项通过、0失败，见components.log。
- 真实浏览器：tests/e2e/instant.py 27/27、practice.py 17/17、feedback.py 31/31、assistant.py 59/59通过，见对应*-e2e.log。即时练习实际在服务端接纳反馈后丢弃响应，再改判重试并核对原回执；all匹配用真实创建的A与A+B两题验证截断前筛选。
- 界面：tests/check_ui.py零问题，tests/check_contrast.py 58组全部达标。tests/check_docs.py --diff HEAD退出0，155文档、零问题、3项既有体积提醒；git diff --check通过。
- 视觉：tests/visual/run.py --ref 162532f --pages instant --out /tmp/omrs-fixes-20261024-0xxk0wzu/visual退出0。浅色桌面与深色桌面均0.002%差异，均为侧栏版本4→5；浅色手机、深色手机均0%。已查看桌面差异图，四档脚本错误、小目标、行内样式、横向溢出均为0，字号均3种；report.html与audit.json留存。
- 发布预检：git fetch origin成功，main领先origin/main五个提交且没有远端独有提交；原有validation.json哈希与补丁已留存。生产三服务active，十一类活动任务计数为0，无恢复或未完成写入意图，训练锁可取得；未在生产创建测试题或调用模型。

## 未执行验证

实现回归已完成；Git提交推送、精确归档验证、停服备份、生产切换及公网验收待连续执行，完成后更新本日志。真实供应商、付费模型、实体手机和Windows Edge未验证；本机合成SSE与浏览器回归不代表这些外部环境。
