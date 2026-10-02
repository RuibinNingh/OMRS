# 前端：设置页

> **速查**
> - 职责：外观、访问与安全、AI 识别、AI 助手、数据与存储、服务与运行六分区
> - 入口：`assets/app/features/settings/index.js`，挂载根 `omrs_dashboard.html` 的 `#st-app`
> - 不变量：重启只认新的 `instance_id`；只改免 PIN 网段不重启；AI Key 不回显；外观键名保持兼容
> - 必跑测试：`tests/app/settings.test.mjs`、`tests/e2e/settings.py`、`tests/e2e/mcp.py`、`tests/test_source_export.py`
> - 相关：`AI/frontend/shell.md`、`AI/security.md`、`AI/api.md`、`AI/frontend/design-system.md`

## 页面结构与生命周期

`main.js` 注册 `settings` 页面契约；`index.js` 在 `#st-app` 渲染六个静态分区，使用页面动作代理分发按钮、输入和变更事件。`appearance.js`、`access.js`、`ai.js`、`agent.js`、`storage.js`、`service.js` 各管理一个分区；`state.js` 和 `storage-state.js` 保存纯投影。进入时各区读取当前服务状态；离开时撤销事件监听和图片任务轮询，未保存的输入按原行为丢弃，不拦截切页。

左侧导航是 `tablist`，支持方向键、Home、End、焦点移动及 `aria-selected`；上次分区保存在 `localStorage('omrs-settings-section')`，非法值回退到外观。手机端导航横向滚动，分区正文单列。通用样式在 `settings.css`，MCP 区域与其弹窗样式在 `mcp-keys.css`，均使用设计 token。除仍被测试或外部调用的标识外，旧设置 DOM 的 ID 不作为兼容契约。

## 外观与显示

主题、密度与深色题图反相分别使用原有 `omrs-theme`、`omrs-density`、`omrs-invert-img` 本地键；修改后立刻更新 `<html>` 对应属性。首次主题沿用首帧脚本的深色默认值。Ledger 时区使用 `omrs-ledger-time-zone`，修改时发 `ledger:tz` 总线事件，历史记录与仪表盘最近动态按新时区显示；带时区偏移的时间戳才转换，旧的无偏移时间保留原墙上时间。

同一分区的「入口背景」卡片写入当前 Vault 的 `entry_background`：默认黑洞 WebGL 预设，也可切换到自定义并上传图片或视频。浏览器先本地预览，保存时才通过 `multipart/form-data` 上传；支持的文件由服务端再次校验，单文件上限 200MB。自定义模式首版提供「高斯模糊」，滑杆为 0–32px，预览与入口页使用同一套夹取规则。切回黑洞不会删除已保存媒体，卡片会显示当前文件类型和大小，并提示入口访问设备都能看到自定义背景。

## 访问与安全

`access.js` 并行读取 `/api/config`、`/api/auth/session` 和 `/api/status`，用运行中 `listen_external` 判断当前暴露范围；读不到运行状态时退回已保存配置。概览显示本机 / 远端、PIN 和免 PIN 网段；保存 `allow_external` 与 `lan_pin_exempt_cidrs` 时，仅运行监听范围需要改变才请求重启。只改免 PIN 网段时立即生效。远端关闭局域网前先确认失联后果。

访问与安全分区的“外部 AI / MCP”包含能力说明和密钥管理两个面板，由 `mcp-keys.js` 调用 `/api/mcp/keys`、`/api/mcp/keys/update` 和 `/api/mcp/keys/revoke`；结构与元数据投影分别在 `mcp-keys-view.js`、`mcp-keys-state.js`。首屏以可用密钥列表为主，显示名称、短前缀、权限、最近使用和到期时间；ID 与完整时间放在可展开的详情里。已吊销和已到期的密钥进入默认折叠的失效记录，到期时自动更新分组。时间按设备本地时区显示，当天简写为“今天 HH:mm”。刷新保留展开状态，读取失败保留上次成功列表并显示原因，迟到的旧读取结果不覆盖当前状态。

“创建密钥”使用共享 `ui/dialog`：名称可选，默认永不过期，也可指定未来时间；六项权限卡可整卡点击，至少选择一项，默认及依赖见下方「MCP 权限编辑」。请求进行中禁止重复提交与关闭，失败保留表单供重试。成功后同一窗口切换为一次性明文展示，提供复制反馈和“我已保存，完成”。明文只在当前控制器内存和窗口输入框中，关闭窗口、刷新页面或离开设置页时清空值及 `value` 属性，不写入浏览器存储、配置或普通日志；列表刷新仅读取元数据。

吊销窗口显示密钥名称与影响，默认聚焦“保留密钥”；失败可在原窗口重试，成功后密钥立即失效并移入失效记录，草稿和题库保留。写入成功先更新本地元数据，后续刷新失败仍显示已完成的状态。MCP 密钥不会改变 Web PIN、AI 模型密钥或普通 API 权限。

PIN 支持首次设置、更换、空闲分钟修改、本机停用和远端登出。PIN 为 4–12 位数字，空闲时间为 5–240 整数分钟；远端更换已有 PIN 须提供当前 PIN，成功后已登录远端跳回登录页。本机仍允许局域网访问时不能停用 PIN。网络或配置请求失败在所属分区显示原因；写操作进行中防重复提交。

## AI 识别

AI 地址、模型、三种用途模型、思考与知识点限制开关经 `/api/config` 保存后立即生效。`ai_thinking` 默认关闭；使用 `deepseek-flash` 时，开启/关闭分别发送 `thinking:{type:"enabled"}` / `thinking:{type:"disabled"}`，覆盖提取、分类等 AI 识图请求及助手图片转述，不控制 AI 助手主模型。其它模型不附思考参数，遵循服务商默认行为。API Key 仅在输入非空时提交；服务端只返回 `ai_api_key_configured`，页面不回显密钥，留空表示保留。清除密钥需确认，单独提交 `clear_ai_api_key:true`。

## AI 助手

`agent.js` 并行读取 `/api/config` 与 `/api/agent/status`：开关、地址、模型、厂商兼容、最大输出 Token（默认 10240，留空恢复默认，允许 1–65536）、三项预算（留空用默认，输入会被夹到默认上限以内）、请求日志开关，以及「主 AI 支持图片」`agent_vision`。输出上限用于助手每轮模型请求，不控制 AI 识别或连接测试；非整数与越界值在页面原地拒绝。开时图片直接发给主模型；关时先用「AI 识别」的转录模型转文字。助手密钥同样只提交不回显，状态行说明是单独配置还是沿用「AI 识别」的密钥；清除提交 `clear_agent_api_key:true`。启用时模型名必填（进程用假模型时除外，此时分区顶部有提示）。保存后发总线事件 `agent:config`，侧栏入口随之显示或隐藏。「测试连接」先保存，再请求 `/api/agent/test`，显示耗时、工具调用结果与图片直传探测的 `vision_ok`（视觉开时）。

「AI 录题方式」可选静默草稿或确认入库，默认 silent；保存 draft_mode 后工具注册表随配置更新。该设置不改变模型或密钥配置，也不把静默录题解释为自动写题库。

## 数据与存储

`storage.js` 从 `/api/optimize/summary` 读取数据链、题目文件和图片占用，`storage-state.js` 投影比例与候选大小。Pillow 不可用时禁用扫描与压缩。扫描、压缩均经 `/api/optimize/job?id=` 轮询；任务中显示进度并防重复启动，离开页面暂停本页轮询，再进入时继续查询仍有效的任务。压缩开始前须二次确认，已导出备份的 token 可随请求提供。

备份导出由 `/api/backup/export` 下载 ZIP。导入先确认上传，再向 `/api/backup/import` 取预览，第二次确认后才向 `/api/backup/restore` 发覆盖请求；取消不改变数据。恢复成功后刷新统计和存储摘要。下载、导入和任务错误在数据分区原地显示。

## 服务与运行

运行状态取自 `/api/status`。重启前读取 `/api/auth/session` 的 `instance_id`；读不到则不请求重启。发出 `/api/restart` 后每 500ms 探测新实例，最长 90 秒；旧实例仍响应、连接暂断或探测超时都不会刷新。只有读到不同的 `instance_id` 才刷新页面。E2E 用 `page.route` 拦截重启请求，隔离实例移除 `OMRS_SYSTEMD_SERVICE`。

脱敏源码下载直接调用 `/api/source/export`，完成后由 `core/download.js` 下载 ZIP。测试实例的 Vault 是临时空目录，E2E 用固定 ZIP 响应核对前端下载路径；服务端真实打包契约由 `tests/test_source_export.py` 验证，源码包包含可选 `requirements-mcp.txt`，排除 Vault 中的 MCP Key 摘要与明文。

助手设置提供「图片框选方式」与「默认用于训练数据」：询问模式在聊天草稿卡片给出 AI 框/我来框；自动模式为新草稿排检测任务；手动模式从草稿区处理。另有「全文字也要框」开关，只影响之后新建且有来源图的全文字草稿，训练任务不阻止入库。训练默认开关只影响新图的初值，已有图仍按图设置，关闭不撤销已经登记的数据。

## MCP 权限编辑

创建弹窗保留查询/创建草稿两项默认，新增修订草稿、保存报告、管理板、删除板四项默认关闭，说明读权限依赖与网页确认边界。有效密钥提供“权限”按钮，在共享弹窗编辑当前勾选项，经 /api/mcp/keys/update 实时更新；不修改密钥明文、到期和吊销状态。已失效记录不提供编辑入口，服务端也拒绝复活。
