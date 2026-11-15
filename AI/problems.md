# 问题中心与错因记录

> **速查**
> - 职责：独立问题、题目材料关联、多次错因、修订审计与原生回执
> - 入口：`omrs/problems.py`、`omrs/problem_store.py`、`omrs/problem_assets.py`、`omrs/problem_review.py`
> - 不变量：稳定question_id；不改变熟练度、Attempts、EF、到期或Session进度；普通读不建库
> - 必跑测试：`tests/test_problems.py`、`tests/test_mcp_problems.py`、`tests/test_schedule_banner.py`、`tests/e2e/problems.py`
> - 相关：`AI/frontend/problems.md`、`AI/data.md`、`AI/ai-review.md`、`AI/backup.md`

## 领域与身份

问题允许无关联题，题目与问题多对多。状态为analyzing（待分析）、working（处理中）、verifying（待验证）、resolved（已解决）、parked（搁置）。状态切换必须提供理由，允许跳转和重新开启，不推导任何学习成绩。

独立错因以REF身份追加，正文必填，可关联多个问题、可引用同题记录表示再次发生。新增记录同事务补齐问题与该题的材料关系；修订/撤回保留事件旧值，不级联删除旧附件。occurred_at为空表示发生时间未知，created_at仅表示记录时间。旧题Markdown错因仍由原题展示，不自动迁移或拼接。

## 存储与事务

`错题/.omrs/problems.db` schema 1：objects保存problem、entry和asset当前值，links保存problem_id/question_id与UID展示快照，events只追加修订事实，receipts保存幂等结果，ai_review_receipts保存同事务审核回执，settings保存调度提醒。读取使用只读连接且不初始化架构；不支持的版本或损坏明确报错。写入依次取得生命周期租约、全局写锁和SQLite事务，事件记录当前世代。

每次写必须提供request_id；同编号同内容重试返回原结果，同编号不同内容409。修改问题、关联、修订记录必须expected_revision匹配。关联查询按原question_id解析当前UID，归档或不可用材料保留原身份，不能跳转到复用UID的新题。

## HTTP

GET `/api/problems`分页搜索（query/status/question_id/limit/cursor），可带sort为updated_desc（默认）、updated_asc、title或questions_desc，deleted=only只看回收站，缺省隐藏已删除问题。响应为items/total/next_cursor/counts，limit最大100；counts统计当前搜索及题目范围的五状态、all与trash，不受status分页影响。排序使用稳定身份打破同值，关联数统一聚合。GET `/api/problem?id=`读取详情、关联与事件，包含回收站问题；GET `/api/reflections?question_id=`分页读取记录。

POST `/api/problems/write`接收`{action,data}`，常规action为create_problem、update_problem、link_problem_questions、unlink_problem_questions、add_reflection_entry、revise_reflection_entry、add_problem_asset。服务端固定Web操作者，不接受客户端冒充AI或用户来源。

网页专用manage_problems接收operation（trash／restore／status）、items（1至100个`{id,expected_revision}`）、request_id；status操作另须status及非空reason。整批身份、版本和目标状态先核验，任一冲突整批回滚；成功响应problems数组及原生回执。trash设置deleted_at，restore置空并保留原处理状态，全部操作推进revision与updated_at并逐项追加事件。重复请求依原幂等规则处理，删除保留题目关联、附件、独立错因与审计。

回收站问题拒绝内容、状态和材料修改及全新错因关联。既有错因的修订和明确引用旧记录的再次发生可保留原问题关联，不重开问题、不增加材料或问题revision。旧对象缺少deleted_at时视为正常问题，无须schema迁移。manage_problems不加入AI工具与审核白名单，agent／mcp来源调用明确拒绝。

GET `/api/problem-asset?name=`读取内容寻址附件。上传操作接收data_base64，图片完整解码且最大8MiB，SVG最大256KiB与1000节点，拒绝脚本、外链、事件和可执行结构。问题图只采用页面几何profile；题目SVG的90mm规范不改变。附件不可覆盖，描述保存引用PA摘要身份；HTML始终转义。

## 审核与可信边界

MCP查询需omrs:read与problem:read，写还需problem:write；默认Key不扩权。所有正式MCP写先进入统一审核，批准前重新核验Key、世代和revision，结果以领域同事务回执为准。助手工具为confirm级，走原对话的手动、送审或显式危险模式。AI记录标记ai_hypothesis，业务状态改变不能将假设变成用户确认。

用户明确确认问题或错因时须提供依据，AI修改描述会重新标记假设。新增错因首次补齐材料关系时同步推进问题revision并追加reflection_link审计；既有关联不重复推进。修订记录保留发生日期及最多50条近期修订事件。审核影响预览显示当前值与新值，附件预览只使用已校验的字节。
