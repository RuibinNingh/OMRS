# AI 草稿区（drafts）

> **速查**
> - 职责：聊天建草稿、独立图片与来源管理、人工更新 / 丢弃 / 一次性入库
> - 入口：`omrs/drafts.py`（存储与公共函数）、`omrs/draft_write.py`（编辑与入库）、`omrs/server.py`（草稿路由）
> - 不变量：建草稿、编辑、丢弃不写 Ledger；通过才创建题目；图片按对话编号，AI 工具只用 IMG-n 引用
> - 必跑测试：`tests/test_drafts.py`、`tests/test_agent_draft_tools.py`、`tests/e2e/drafts.py`
> - 相关：`AI/agent.md`、`AI/data.md`、`AI/api.md`、`AI/frontend/create.md`

## 1. 存储与来源

文件在 `错题/.omrs/drafts/`：drafts.db 保存草稿、块、来源和入库操作，images/<sha256>.<ext> 保存聊天原图，events.jsonl 追加事件。草稿不会自动进入收件箱或题库；只有通过才调用创建题目的领域入口。

images 以 sha256 去重，保存 mime / width / height / bytes、转述缓存与训练预留字段；conv_images 按 conversation_id + n 将每张图映射为 IMG-n。同一对话重复贴同图沿用编号。图片支持 PNG/JPEG/GIF，单张解码后不超过 8MB；尺寸由现有图片头解析器读取。

`drafts` 含 id、四态 status、conversation_id/run_id/tool_call_id、科目分类、知识点、难度、标记、错因及原话、备注、入库 uid/question_id、时间和整数 revision；老库增量加列，revision 初始 1。`blocks` 含稳定 id、section（题目/答案）、ord、kind（text/image）、text/image_sha、归一化 box、box_origin、ai_box、note。

`draft_images` 保存每份草稿的完整来源图及顺序，全文字草稿也能关联图片。老来源先从图片块恢复，再按准确的对话 / 运行 / 工具调用恢复 images 参数，无法证实的来源标 sources_complete=false；不会把整段对话的所有图猜成一道题。详情另提供 conversation_images，供用户明确补关联。

来源未完整恢复时，仅保存字段或回传相同来源列表不会把标记改为完整；用户实际修改关联列表后才记录已补关联。

转述缓存按 sha256 + 模型命中；换模型覆盖旧缓存。创建草稿的来源、内容更新、丢弃和入库均有本模块事件记录，不进 Ledger 不等于没有留痕。

## 2. 状态与人工编辑

cropping 表示仍有缺框的图片块；全部图片块有合法框后为 review。done 与 discarded 正文只读。人工保存字段与完整块数组时验证 revision，再一次性更新并递增版本；非法字段、坐标或图片来源不部分写入。

框为有限数值的 x/y/w/h，位于 0–1 内且宽高为正，origin 只接受 manual/ai/ai_edited。P2 页面通过「使用整图」显式写 0/0/1/1；全是文字的草稿直接待审核。块 id 保持稳定，新块由服务端生成，数组顺序确定 ord。难度 1–10，知识点最多 8 个；科目、分类与有效题目内容必填，答案可空。

AI 创建时非空错因必须有 cause_statement，并由工具层核对用户消息原话。人工编辑错因不需要伪造对话原话；原始证据保留。AI 不提供修改或丢弃草稿工具。

## 3. 一次性入库

`commit_operations` 在题目创建之前持久保存 draft_id、revision、预留 uid/question_id、路径与阶段。入库在全局写锁和草稿锁内进行，先查已有 `_draft` 创建提交；响应丢失或草稿状态更新失败后的重试返回原题，不重复创建。已有 Ledger 提交时修复投影并补 done 状态，不能删除已被提交引用的正文或附件。

创建入口的内部有序块参数按题目 / 答案各自 ord 保持文字与图片交错；旧快速录入 / 收件箱参数的输出不变。附图预校验后保存，坏数据报错，不静默漏图。整图可直接使用原件；局部裁图按当前可用路径提供，无裁图条件时保留草稿报错。

创建提交顶层 payload 包含 `_draft:{draft_id,conversation_id}` 并参与哈希。手工通过来源 api；确认工具沿用 agent_actor，来源 agent 并带 `_agent`，可按运行撤销。已入库草稿再次提交返回 reused=true；后续题目撤销不会自动重新建题。

done 详情的 question_available 同时核对题目当前投影与正文文件；已归档、撤销或文件缺失时，页面显示题目不可用，不提供有效题目跳转。Ledger 前中断的暂存操作只清理路径与内容哈希均匹配的自有文件；Ledger 已提交时，后续编辑或丢弃先恢复 done，再返回状态冲突。

## 4. HTTP 与 Python 入口

GET 保留 `{status:"ok",drafts:[...]}` / `{status:"ok",draft:{...}}` / `{status:"ok",counts:{...}}` 包装。

| 路由 | 行为 |
|---|---|
| GET `/api/drafts/list?status=&conversation=&limit=` | 缺省排除 discarded；pending 联合 cropping/review；limit 限制在 1–500 |
| GET `/api/drafts/item?id=` | 详情含 blocks、revision、source_images、sources_complete、conversation_images |
| GET `/api/drafts/image?sha=` | 原图二进制，sha 为 64 位十六进制，private/max-age=86400 |
| GET `/api/drafts/counts` | cropping/review/done/discarded 四态计数 |
| POST `/api/drafts/update` | `{id,revision,fields,blocks,source_images?}`；fields 白名单；source_images 为 sha 数组，返回 draft |
| POST `/api/drafts/discard` | `{id,revision}`；仅活动草稿可丢弃；重复 discarded 返回当前值，不立即删图 |
| POST `/api/drafts/commit` | `{id,revision,crops?}`；返回 draft/result/reused/training；result 含 uid/question_id/file_path |

POST 沿用登录、同源与全局写锁。DraftError 含 status/code/current_revision：非法输入 400，不存在 404，状态或版本冲突 409；锁忙 503。GET 保持原错误兼容。页面不能提交 origin/uid/status 覆盖服务端身份。

公共 Python 函数仍由 drafts.py 提供：add_image、resolve_image、conversation_refs、image_path/image_data_url、get_transcript/set_transcript、create_draft、get_draft、list_drafts、counts；新增 update_draft(vault,id,revision,fields,blocks,source_images=None)、discard_draft(vault,id,revision)、commit_draft(vault,id,revision,crops=None)。写入实现委托 draft_write.py。

## 5. 查询与界面联动

存储列表缺省含 done；助手 list_drafts 缺省只给活动草稿，录入页显式用 pending 筛选。侧栏与工作区计数为 cropping + review。草稿详情保存显式提交 revision，后台读取不会覆盖未保存表单。助手卡片的当前状态单独从 API 读取，不重写历史运行事件。

## 6. 测试边界

后端覆盖草稿校验、图片引用、老库来源恢复、HTTP、并发 / 重复入库、来源归属与创建失败恢复；助手工具测试覆盖原话校验、动态注册与确认版本。真实浏览器 `tests/e2e/drafts.py` 走审核、整图、保存失败保留、冲突、丢弃与窄屏路径。所有实例使用临时 Vault；真实模型与生产数据不作为自动测试输入。
