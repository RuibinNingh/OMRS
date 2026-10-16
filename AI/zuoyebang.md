# 作业帮搜题与保真录入

> **速查**
> - 职责：独立网关搜题、候选、后端完整长图、AI 保真提取与幂等创建
> - 入口：`omrs/zuoyebang/`、`omrs/http/zuoyebang.py`；页面见 `AI/frontend/zuoyebang.md`
> - 不变量：题干答案按候选绑定；候选题目/答案各一张1080像素完整图，原图裁切保持实际像素；失败保留来源；凭据不进入响应或日志
> - 必跑测试：`tests/test_zuoyebang.py`、`tests/test_zuoyebang_render.py`、`tests/test_zuoyebang_geometry.py`、`tests/app/create-zyb.test.mjs`、`tests/e2e/zuoyebang.py`
> - 相关：`AI/api.md`、`AI/security.md`、`AI/data/storage.md`、`AI/inbox.md`

## 1. 服务与账号

「设置 → 作业帮服务」配置本地或外部独立网关。本地默认 `http://127.0.0.1:8745`，允许改为其它回环端口；两种模式都必须提供网关调用密钥。网关负责设备会话、扫码、账号、签名与解码，OMRS负责上传原图、选择候选、渲染、识别及核对创建。配置、地址策略与网络预算见 `AI/zuoyebang-service.md`。

账号菜单提供服务设置、独立管理面板和脱敏有效期记录。设备会话导入、扫码、检查与刷新只在独立面板执行，OMRS不读取或迁移旧账号凭据；缺少已登记设备时不能伪造设备身份。旧导入及账号管理HTTP端点返回409，指导用户进入独立面板。状态读取与连接测试只查询网关本地状态，不联系官方；网络错误不改变账号或签名观察。

网关分别记录account/signing的最后成功、首次确认失效、有效时间区间与恢复结果；OMRS只接收白名单摘要和最近100条脱敏事件，没有官方TTL时只展示观察区间。`omrs/zuoyebang/direct.py`、`account.py`、`session.py`保留为协议来源与回归实现，正常搜题通过配置的网关执行。

## 2. 搜题与后端渲染

侧栏「作业帮」打开独立整卷工作台。摄像头、上传、拖放和粘贴共用原图，左侧查看试卷与题框，右侧按位置选择候选、完整预览与核对。候选初始未选，点击即自动生成题干与答案；快速切换只继续最后选择，失败保留来源并可重试。交互与刷新恢复见 `AI/frontend/zuoyebang.md`。

图片以 zuoyebang 用途的既有分块上传引用发送，不重编码原件；仅 JPG/PNG/WebP、不超过8MiB且不超过4000万像素，完成上传时用 Pillow 验证完整解码。用途不能借用于普通题目创建；旧上传用途仍仅支持 PNG/JPEG/GIF。解码后的结果按照片位置和显式候选保存，不合并相似题树；题干和对应答案一起选择。接口返回摘要，原始上游内容留在独立记录。

HTMLParser 白名单保留文字、列表、表格、上下标和图片，移除可执行内容、事件和任意 CSS。题库类名单保留tkspec上下标/填空/文字强调/对齐、tk-md2html正文、tB表格及旧HTML公式的math/fM/fI/pA/pR/pS；必要的数值尺寸、定位、字体比例、单色分数线和有限display值经严格筛选。样式由可信paper.css定义，不加载上游CSS。旧公式使用本地MathJax字体；波浪线用CSS绘制，1080px纸面统一字体、字号及边距，不能据此声称与手机原页面像素完全一致。

附图URL或picList[].pid依原App规则转换；支持tk_、zyb_、zyb数字_、qa10_和qa数字_域映射。正文和附图列表去重，题干答案共用原字节下载缓存；远程附图接受任意域名的标准端口HTTP/HTTPS地址，不设域名白名单。每次请求及跳转复核地址格式和全部DNS结果，只连接公网单播IP，实际连接固定已校验IP，TLS按原域名验证；拒绝凭据URL、其它协议、异常端口和非公网／组播目标。下载不携带账号Cookie，图片验证后内联原字节。

Chromium拦截器只读取OMRS本地字体、MathJax3及可信渲染配置，不访问外网、Vault或任意文件。传统题库正文用官方MathJax3.2.2 tex-chtml-full与typesetPromise；支持美元和反斜杠数学定界符，无定界符的裸命令兼容原App预处理。禁用动态TeX扩展、菜单和外部公式URL/样式。全部23份CHTML字体、许可与SHA256清单位于assets/vendor/mathjax；其它OMRS页面仍用KaTeX。跨HTML节点拆开的定界符不强行拼接；公式错误整体失败。

SVG、MathML、canvas和音视频等不能按当前白名单保真渲染的视觉内容会明确报错并保留来源，不静默删除必要图形。搜题响应结构或解码格式异常记 protocol，不当作账号或签名过期。

真实 Chromium deviceScaleFactor=1，题干与答案各一张宽1080的 PNG，高度按全文。答案不分块、分页或裁断。等待字体、公式和所有图片 decode，校验 PNG 尺寸与 SHA256；记录引擎版本及每区公式数。缺图、公式错误、横向超出1080均整体失败并保留原候选。单附图12MiB、附图总量80MiB、单输出1亿像素是物理资源预算，超限报错，不缩放或截断。纸面固定白底，前端主题只改变外框；HTML 预览用文本显示，内联图片字节以提示替代。

### 题目坐标与原图

网关和保留的协议实现解码 answers.locs / angles：逐项base64后按主解码Key执行RC4，不用正文的gzip或tid候选Key；明文encode模式只解base64。解码失败的单项留空，不丢弃可读候选。网关几何字段计入累计24MiB解码预算，最多200项。

`geometry.py` 按 queryInfo.locIndex（归一化后的location_index）将候选关联到题目位置。loc为8个以@分隔的有限数值，组成四点；rotateAngle允许0/90/180/270。原图宽高W/H，工作平面的(x,y)还原分别为(x,y)、(y,H-x)、(W-x,H-y)、(W-y,x)。返回原像素polygon与轴对齐bounds{x,y,width,height}，附可用angle；越界、退化或格式异常不返回bounds。候选和无匹配的有效位置仍保留，不能据此保证整卷每题都有框。

成功搜索将原始上传字节保存到私有source.bin，并返回image的尺寸、MIME、SHA、字节数、orientation和受鉴权URL。EXIF方向不为1时额外生成不转置像素、移除EXIF的PNG预览，让浏览器画布与坐标处于同一像素平面；上游与归档原件不重编码。读取验证SHA及路径边界。旧记录无原图时明确404，不追溯补造。

用户可核对／调整题框后保留原题图片；source作业按原图范围裁成PNG，向外取整并限制原图边界，输出保持实际像素尺寸。生成标准render记录，source_kind=crop、bounds、候选index=null、location为位置索引、答案empty；复用保真提取与人工幂等创建，不使用Chromium或补写答案。

## 3. 后台作业与 AI

search/render/source/extract 在守护线程执行，每个 Vault 最多同时两个任务，同一来源去重。开始捕获世代与服务配置，网络与浏览器期间不持磁盘租约或业务写锁，快照读写与发布取短租约/写锁。切换服务或密钥后，旧任务不发布成功结果，可在带原service身份的记录中保存failed；失败不得替代新服务状态。整库恢复后，旧成功／失败均不能写回新世代。作业状态持久化，并保存内部开始世代；重启或同进程整库恢复后，旧 running 记录只读显示中断，不永远等待，也不自动重放网络调用。

AI 复用 extract_region、judge=True 和现有识别配置；每个角色一次读取完整图。完整转录文字/公式时保存文本，否则保留整图，不补写解答。两区独立保存，重试只处理失败项；分类只补科目、分类、难度和知识点，不写标记。模型 finish_reason=length/max_tokens 时拒绝当作完整转录。供应商自身的图像和输出限额仍适用，失败可按整图入库。

## 4. 创建与恢复

用户核对后主动创建；客户端提交 render_id、人工表单和两区 mode/text。图片由后端读取不可变 PNG，不接受外部 HTML/路径。空答案使用 none，非空答案不可隐式丢弃，文本要求非空。

首次提交冻结内容摘要、UID/question_id/路径和日期，复用 CreationOperation 产物校验与 Ledger op_results 回执；其它录入入口跳过作业帮预留 UID。中断重试用同一身份，已有回执直接复用；不同内容重试返回409并保留首次内容，浏览器可从记录恢复。正式提交为 question.create，actor=zuoyebang，内部来源 _inbox.zuoyebang_render_id 关联渲染。

工作区扫描跳过尚未入账的作业帮预留身份，避免已写出的中间文件被当作外部新增题目。恢复由用户从原渲染记录重试，不在启动时重放网络或自动创建。全库备份包含这份私有目录，恢复世代使在途任务及旧上传引用失效。

## 5. HTTP 契约

全部沿用 OMRS Web 鉴权、POST 同源校验及 MCP Key 边界，不返回第三方凭据。

| 方法与路径 | 请求与响应 |
|---|---|
| `GET /api/zuoyebang/service` | 私有连接配置的脱敏投影；不返回密钥 |
| `POST /api/zuoyebang/service` | 保存mode/base_url/api_key/allow_private_targets；空Key保留，clear_api_key明确清除 |
| `POST /api/zuoyebang/service/test` | 空请求体，查询已保存网关状态；不搜题或刷新账号 |
| `GET /api/zuoyebang/status` | 查询网关账号脱敏观察及冻结服务配置；不联系官方 |
| `POST /api/zuoyebang/profile` | 409 gateway_management，设备会话在独立面板导入 |
| `POST /api/zuoyebang/account` | 409 gateway_management，账号管理在独立面板执行 |
| `POST /api/zuoyebang/jobs` | `{type:"search",image:{upload_ref},grade?:0..12}` / `{type:"render",search_id,candidate_index}` / `{type:"source",search_id,region_index:int或null,bounds?:{x,y,width,height}}` / `{type:"extract",render_id,force?:boolean}`，返回 job |
| `GET /api/zuoyebang/job` | `?id=job-…`；running/done/failed，含 result 或 error/code |
| `GET /api/zuoyebang/record` | `?id=search-…或render-…`；候选摘要、image/regions/rotation或渲染/images/extraction/创建预留和回执，不返回 source |
| `GET /api/zuoyebang/history` | 最近30份搜索及渲染的状态、尺寸、摘要与时间 |
| `GET /api/zuoyebang/image` | `?id=render-…&role=question或answer` 返回PNG；`?id=search-…&role=source`返回原图或无EXIF方向预览，实际MIME；均核对SHA、private/no-store |
| `POST /api/zuoyebang/commit` | `{render_id,form:{subject,category,difficulty,related_tags,labels,cause},sections:{question:{mode,text},answer:{mode,text}}}`；返回身份、图片名、commit_id、reused |

source的region_index须存在于搜索记录，null允许显式整图范围；省略bounds时使用该位置的有效bounds，未取得有效范围返回400。坐标字段必须有限数值且在原图内。

非法输入400；会话/流程/预留过时409；并发预算429；依赖缺失503；上游故障502。后台渲染和识别错误经 job 报告，轮询HTTP本身仍200，原内容保留。
