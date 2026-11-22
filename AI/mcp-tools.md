# MCP 工具清单

> **速查**
> - 职责：列出外部 MCP 工具、行为与所需权限
> - 入口：`omrs/mcp/server.py`、`omrs/mcp/tool_docs.py`
> - 不变量：发现和调用均按当前 Key 权限过滤；写操作的审批边界见主文档
> - 必跑测试：`tests/test_mcp_board.py`、`tests/test_mcp_tool_docs.py`
> - 相关：`AI/mcp.md`、`AI/security.md`、`AI/problems.md`

### 完整工具清单

| 工具 | 行为 | 所需权限 |
| --- | --- | --- |
| `list_taxonomy` | 科目、分类与知识点词表 | `omrs:read` |
| `search_questions` | 筛选、排序和分页检索题目 | `omrs:read` |
| `get_question` | 稳定 question_id、可编辑字段、正文哈希与图片列表 | `omrs:read` |
| `get_question_image` | 按题目图片下标取完整图片；SVG 派生为 PNG | `omrs:read` |
| `get_overview` | 同科目范围的概况 | `omrs:read` |
| `get_recommendations` | 现有复习推荐 | `omrs:read` |
| `list_sessions` | 分页练习 Session 列表及进度、可用性计数 | `omrs:read` |
| `get_session` | 分页稳定题目条目与完整反馈进度 | `omrs:read` |
| `list_drafts` | 待审核及其它状态草稿列表 | `omrs:read` |
| `get_draft` | 草稿正文、来源与版本 | `omrs:read` |
| `list_labels` | 标记定义与引用统计 | `omrs:read` |
| `get_labeling_candidates` | 分页读取待归类题目与版本指纹 | `omrs:read` |
| `get_questions` | 最多 20 UID，保留顺序并逐项报缺失 | `omrs:read` |
| `get_question_content` | 当前或已登记版本的完整分节正文分页 | `omrs:read` |
| `get_draft_image` | 按来源图片下标取原生完整图片 | `omrs:read` |
| `get_question_history` | 有效反馈或正文版本历史 | `omrs:read` |
| `get_learning_history` | 先筛选再按 Ledger 游标读学习/变更时间线 | `omrs:read` |
| `get_analytics` | 六种详细分析视图 | `omrs:read` |
| `list_reports` | 报告元数据列表 | `omrs:read` |
| `get_report` | 报告 HTML 源码分页，不执行脚本 | `omrs:read` |
| `list_boards` | 分页板列表、完整文件夹与目录版本 | `omrs:read` |
| `get_board` | 分页题目引用、版式、纸面摘要与版本 | `omrs:read` |
| `get_mcp_operation` | 本密钥发起的确认操作状态 | `omrs:read` |
| `export_board` | 全部/仅新增的限时不可变 HTML 快照 | `omrs:read` |
| `list_schedule_reminders` | 读取提醒素材元信息，不含SVG字节 | `omrs:read` |
| `create_schedule_reminder` | 幂等新增提醒素材，网页用户选用 | `reminder:create` |
| `create_draft` | 原图或文字创建待审核草稿 | `draft:create` |
| `update_draft` | 受人工保护的字段/块修订 | `omrs:read` + `draft:update` |
| `create_report` | 幂等新建报告，不覆盖旧报告 | `report:create` |
| `propose_question_update` | 白名单正式题目修改提案；可替换、裁剪或移除已有位图配图，待人工批准 | `omrs:read` + `question:propose` |
| `stage_label_plan` | 分片准备完整标记方案，不写正式题库 | `omrs:read` + `label:write`；含合并/删除另需 `label:delete` |
| `propose_label_plan` | 提交整批标记整理审核，由网页一次批准 | `omrs:read` + `label:write`；含合并/删除另需 `label:delete` |
| `create_review_session` | 按稳定身份幂等创建正式复习计划 | `omrs:read` + `session:create` |
| `create_board` | 新建板，可带初始题目引用 | `omrs:read` + `board:write` |
| `update_board` | 局部修改板名、备注、来源标记 | `omrs:read` + `board:write` |
| `duplicate_board` | 复制引用与版式，不复制纸面记录 | `omrs:read` + `board:write` |
| `add_board_items` | 完整校验后加题，跳过已有引用 | `omrs:read` + `board:write` |
| `remove_board_items` | 移除引用，清空非空板需网页确认 | `omrs:read` + `board:write` |
| `reorder_board_items` | 所有条目引用的完整排列 | `omrs:read` + `board:write` |
| `update_board_layout` | 严格范围的局部版式补丁 | `omrs:read` + `board:write` |
| `update_board_item` | 单题留白与置顶 | `omrs:read` + `board:write` |
| `create_board_folder` | 新建文件夹 | `omrs:read` + `board:write` |
| `update_board_folder` | 文件夹名称或排序 | `omrs:read` + `board:write` |
| `move_board` | 移动板或调整组内位置 | `omrs:read` + `board:write` |
| `delete_board` | 申请删除板，由网页确认 | `omrs:read` + `board:delete` |
| `delete_board_folder` | 申请删除文件夹，默认保留板 | `omrs:read` + `board:delete` |
| `search_problems`、`get_problem`、`get_reflections` | 搜索问题、读取问题或错因记录 | `omrs:read` + `problem:read` |
| `create_problem`、`update_problem` | 提交创建或修改问题审核 | `omrs:read` + `problem:read` + `problem:write` |
| `link_problem_questions`、`unlink_problem_questions` | 提交问题与题目的关联或解除关联审核 | `omrs:read` + `problem:read` + `problem:write` |
| `add_reflection_entry`、`revise_reflection_entry` | 提交新增或修订错因记录审核 | `omrs:read` + `problem:read` + `problem:write` |
| `add_problem_asset` | 提交受管问题附件审核 | `omrs:read` + `problem:read` + `problem:write` |
