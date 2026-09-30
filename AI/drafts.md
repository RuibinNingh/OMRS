# AI 草稿区（drafts）

> **速查**
> - 职责：聊天建草稿、独立图片与来源管理、人工更新 / 框选提取 / 一次性入库与训练登记
> - 入口：`omrs/drafts.py`（存储与公共函数）、`omrs/draft_write.py`（编辑与入库）、`omrs/draft_jobs.py`（异步提取）、`omrs/draft_detect.py`（自动框选）、`omrs/draft_training.py`（训练与清理）、`omrs/server.py`（草稿路由）
> - 不变量：建草稿、编辑、丢弃不写 Ledger；通过才创建题目；图片按对话编号，AI 工具只用 IMG-n 引用
> - 必跑测试：`tests/test_drafts.py`、`tests/test_agent_draft_tools.py`、`tests/test_draft_p3_http.py`、`tests/test_draft_p4_http.py`、`tests/e2e/drafts.py`、`tests/e2e/drafts_p4.py`
> - 相关：`AI/agent.md`、`AI/data.md`、`AI/api.md`、`AI/frontend/create.md`

## 1. 存储与来源

文件在 `错题/.omrs/drafts/`：drafts.db 保存草稿、块、来源和入库操作，images/<sha256>.<ext> 保存聊天原图，events.jsonl 追加事件。草稿不会自动进入收件箱或题库；只有通过才调用创建题目的领域入口。

images 以 sha256 去重，保存 mime / width / height / bytes、转述缓存与训练预留字段；conv_images 按 conversation_id + n 将每张图映射为 IMG-n。同一对话重复贴同图沿用编号。图片支持 PNG/JPEG/GIF，单张解码后不超过 8MB；尺寸由现有图片头解析器读取。JPEG 沿标记段跳过 EXIF 与缩略图，主图结尾后的相册数据会清除，扫描数据缺尾时补结束标记；整理后计算 hash 并保存，已有图片在生成 data URL 时临时整理，旧文件不改写。编码像素与其他格式字节保持不变；这不代表能恢复已丢失的像素。

`drafts` 含 id、四态 status、conversation_id/run_id/tool_call_id、科目分类、知识点、难度、标记、错因及原话、备注、入库 uid/question_id、时间和整数 revision；老库增量加列，revision 初始 1。`blocks` 含稳定 id、section（题目/答案）、ord、kind（text/image）、text/image_sha、归一化 box、box_origin、ai_box、note。草稿备注和图片说明是独立语义；入库时不会被映射成题目 YAML 的旧页码。

`draft_images` 保存每份草稿的完整来源图及顺序，全文字草稿也能关联图片。老来源先从图片块恢复，再按准确的对话 / 运行 / 工具调用恢复 images 参数，无法证实的来源标 sources_complete=false；不会把整段对话的所有图猜成一道题。详情另提供 conversation_images，供用户明确补关联。

来源未完整恢复时，仅保存字段或回传相同来源列表不会把标记改为完整；用户实际修改关联列表后才记录已补关联。

转述缓存按 sha256 + 模型命中；换模型覆盖旧缓存。创建草稿的来源、内容更新、丢弃和入库均有本模块事件记录，不进 Ledger 不等于没有留痕。

## 2. 状态与人工编辑

cropping 表示仍有缺框的图片块；全部图片块有合法框后为 review。done 与 discarded 正文只读。人工保存字段与完整块数组时验证 revision，再一次性更新并递增版本；非法字段、坐标或图片来源不部分写入。

框为有限数值的 x/y/w/h，位于 0–1 内且宽高为正，origin 只接受 manual/ai/ai_edited。页面通过手动画布调整框，或「使用整图」显式写 0/0/1/1；全是文字的草稿直接待审核。块 id 保持稳定，新块由服务端生成，数组顺序确定 ord。难度 1–10，知识点最多 8 个；科目、分类与有效题目内容必填，答案可空。

AI 创建和修订时，非空错因必须有 cause_statement，并由工具层核对用户消息原话。人工编辑错因不需要伪造对话原话；原始证据保留。AI 的 `update_draft` 按 revision/CAS 和稳定块 id 只改指定字段、文字或说明，不改图片 SHA、框、顺序、身份、状态及训练任务。人工更新过的字段或块记录在 `draft_manual_edits`；AI 遇到这些目标返回建议，不覆盖人工输入。AI 不提供丢弃工具。

## 3. 一次性入库

`commit_operations` 在题目创建之前持久保存 draft_id、revision、预留 uid/question_id、路径与阶段。入库在全局写锁和草稿锁内进行，先查已有 `_draft` 创建提交；响应丢失或草稿状态更新失败后的重试返回原题，不重复创建。已有 Ledger 提交时修复投影并补 done 状态，不能删除已被提交引用的正文或附件。

创建入口的内部有序块参数按题目 / 答案各自 ord 保持文字与图片交错；答案没有图片时只保留一个文字块，步骤和段落用换行保存，只有图片夹在答案文字中间时才在图片处分块。旧快速录入 / 收件箱参数的输出不变。附图预校验后保存，坏数据报错，不静默漏图。整图可直接使用原件；局部裁图按当前可用路径提供，无裁图条件时保留草稿报错。

创建提交顶层 payload 包含 `_draft:{draft_id,conversation_id}` 并参与哈希。手工通过来源 api；确认工具沿用 agent_actor，来源 agent 并带 `_agent`，可按运行撤销。已入库草稿再次提交返回 reused=true；后续题目撤销不会自动重新建题。

done 详情的 question_available 同时核对题目当前投影与正文文件；已归档、撤销或文件缺失时，页面显示题目不可用，不提供有效题目跳转。Ledger 前中断的暂存操作只清理路径与内容哈希均匹配的自有文件；Ledger 已提交时，后续编辑或丢弃先恢复 done，再返回状态冲突。

## 4. HTTP 与 Python 入口

GET 保留 `{status:"ok",drafts:[...]}` / `{status:"ok",draft:{...}}` / `{status:"ok",counts:{...}}` 包装。

| 路由 | 行为 |
|---|---|
| GET `/api/drafts/list?status=&conversation=&limit=` | 缺省排除 discarded；pending 联合 cropping/review；limit 限制在 1–500 |
| GET `/api/drafts/item?id=` | 详情含 blocks、revision、source_images、sources_complete、conversation_images、training_tasks、jobs |
| GET `/api/drafts/image?sha=` | 原图二进制，sha 为 64 位十六进制，private/max-age=86400 |
| GET `/api/drafts/counts` | cropping/review/done/discarded 四态计数 |
| POST `/api/drafts/update` | `{id,revision,fields,blocks,source_images?}`；fields 白名单；source_images 为 sha 数组，返回 draft |
| POST `/api/drafts/discard` | `{id,revision}`；仅活动草稿可丢弃；重复 discarded 返回当前值，不立即删图 |
| POST `/api/drafts/commit` | `{id,revision,crops?}`；返回 draft/result/reused/training；result 含 uid/question_id/file_path |
| POST `/api/drafts/boxes` | `{id,revision,blocks?,training_boxes?}`；部分正文框或指定训练任务框替换，返回 draft |
| POST `/api/drafts/extract` | `{id,revision,block_ids,crops?}`；异步提取，返回 job |
| POST `/api/drafts/detect` | `{id,revision,sha?}`；来源图异步检测，返回 job；指定 sha 可为旧全文字草稿显式发起训练框选 |
| POST `/api/drafts/image/train` | `{id,revision,sha,enabled}`；图级共享开关，返回 draft/image |
| GET `/api/drafts/job?id=` | 返回 job，状态 queued/running/done/error/conflict/interrupted |
| POST `/api/drafts/cleanup` | 只接受 `{}`；返回 cleaned:{drafts,images,crops}、retained:{images} |

POST 沿用登录、同源与全局写锁。DraftError 含 status/code/current_revision：非法输入 400，不存在 404，状态或版本冲突 409；锁忙 503。GET 保持原错误兼容。页面不能提交 origin/uid/status 覆盖服务端身份。

AI 修订不另开 HTTP 写端点，由助手工具在写锁内调用 `patch_draft`；只接受 subject、category、knowledge_points、cause、note 和已有块的 text/note。旧 revision、其他对话、done/discarded、入库中的草稿和未知块 id 均拒绝。成功新增 `draft.ai_update` 事件，包含 actor、run/call、旧新 revision 与实际字段变化；草稿保存本身不写 Ledger。人工 `/api/drafts/update` 对实际变更的字段与块写保护标记。

公共 Python 函数仍由 drafts.py 提供：add_image、resolve_image、conversation_refs、image_path/image_data_url、get_transcript/set_transcript、create_draft、get_draft、list_drafts、counts；新增 update_draft(vault,id,revision,fields,blocks,source_images=None)、discard_draft(vault,id,revision)、commit_draft(vault,id,revision,crops=None)。写入实现委托 draft_write.py；框选/训练/作业公共入口为 set_boxes、start_extract、start_detect、set_image_training、get_job、cleanup。

## 5. 查询与界面联动

存储列表缺省含 done；助手 list_drafts 缺省只给活动草稿，录入页显式用 pending 筛选。侧栏与工作区计数为 cropping + review。草稿详情保存显式提交 revision，后台读取不会覆盖未保存表单。助手卡片的当前状态单独从 API 读取，不重写历史运行事件。

## 6. 框选提取与训练任务

来源图对应独立 training_tasks，training_boxes 保存归一化框、section、box_origin 和 ai_box。正文图片框同步为训练标注，提取成文字后仍保留标注；正文与训练任务分别管理，done 正文不可再改。用户独立编辑或清空训练任务后，manual_override 持久标记使后续正文保存不再自动覆盖该任务的人工标注。训练任务状态为 pending/ready/registered/error。

extract 创建持久 draft_jobs 后异步调用现有识图提取；模型请求不持全局写锁，回写复核 revision、来源与框快照。失败保留对应原块，冲突不覆盖人工内容。详情 jobs 返回最近任务，页面重进可继续轮询；服务新进程把失去执行线程的 queued/running 标为 interrupted，用户可重试。

`POST /api/drafts/boxes` 支持正文 blocks 和独立 training_boxes；后者按指定 task_id 整体替换。`{task_id,box:null}` 表示清空单个任务，空数组不修改，空标记与有效框混用返回 400；不接受客户端任意任务或块 id。

图级 train 初值取 draft_train_default（默认 false），关联同一 SHA 的草稿共用开关；变更使相关草稿 revision 失效。只有已入库且有有效训练框的图会登记，失败记为 error，重复 commit 只补登记、不重复建题。training 摘要包含 registered 的 SHA 数组、failed 的 {sha,error} 数组、pending 的 SHA 数组。已登记开关和框只读，关闭不会删除既有数据。

登记走 inbox 专用入口：新图 ready/other/chat/training_only，普通队列与创建入口排除它，统计和导出包含它；同哈希普通收件箱条目保持原状态、版式和原框，聊天标注写独立关联后按图合并导出。来源移除与误框删除不留下待登记标注，转换成功后的训练框继续保留。

过期清理只从超过 draft_discard_keep_days 的 discarded 草稿释放关联并建立清理候选，受其他草稿、存活聊天或训练引用保护的原图保留。已清理草稿带 cleaned_at，读取不会从旧工具参数复活关联；不清理刚上传的无草稿图片，不删除已入库题目附件。跨库训练关联查询失败时保守保留；引用释放先提交，再删除候选文件，中断后可继续清理。建草稿时尝试轻量清理，失败记录事件且不阻止建草稿。

## 7. 自动框选与全文字任务

start_detect(vault,id,revision,sha=None) 持久登记后台任务，复用当前 inbox_detect_provider（vlm/local_http；旧 template 配置按 vlm 处理）、长图切片和合框逻辑，不先上传收件箱。模型调用前及回写前均检查来源完整性、非 discarded 草稿共享关系（包括 done）和人工框；共享图、manual/ai_edited 或人工清空训练任务均不能自动覆盖。无 Pillow 时长图退回整图检测。

仅待框 image 块与题目/答案候选一一对应时自动写框。多题、多候选或数量不匹配只保留建议，正文不变。逐图 result 包含 sha、status（applied/suggested/skipped/conflict）、reason_code、reason、candidates、applied_blocks、training_task_id；空结果和歧义给出人工处理提示。revision 或快照变化后 job 为 conflict；重启后孤立作业为 interrupted。同图同草稿版本的 detect/extract 活动任务互斥；相同 detect 请求复用作业，部分重叠返回 409。详情按持久插入顺序打破同秒时间戳并列，重试不会取到旧任务。ai_box 保存原建议，人工移动标为 ai_edited。

training_tasks.force_crop 区分强制训练任务与普通来源图标注容器。仅创建有来源图的全文字草稿时按 draft_force_crop 配置设置；修改配置不会追溯旧草稿，无图不造任务。旧全文字草稿可逐图显式发起检测或手工训练框选。训练任务不添加正文图片，不阻止入库；done 仍可完成任务，正文不可改。是否登记仍取决于图级训练开关；入库后有效训练框保存或检测完成会尝试登记，失败可重试。

## 8. 测试边界

后端覆盖草稿校验、图片引用、老库来源恢复、HTTP、并发 / 重复入库、来源归属与创建失败恢复；助手工具测试覆盖原话校验、动态注册与确认版本。真实浏览器 `tests/e2e/drafts.py` 走审核、整图、保存失败保留、冲突、丢弃与窄屏路径；`tests/e2e/drafts_p4.py` 使用本地检测替身走自动框、歧义采纳、共享回退和入库后训练。所有实例使用临时 Vault；真实模型与生产数据不作为自动测试输入。
