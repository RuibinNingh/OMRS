# 前端：设置页

> **速查**
> - 职责：设置页五个分区：外观、访问与安全、AI 识别、数据与存储、服务与运行
> - 入口：`assets/app.js`（设置段）、`omrs_dashboard.html`（`#panel-settings`）
> - 不变量：保留全部旧元素 ID；重启只在看到新 `instance_id` 后刷新；只改免 PIN 网段不重启
> - 必跑测试：`tests/test_settings_ui.js`、`tests/test_restart_ui.js`、`tests/test_auth_activity_ui.js`
> - 相关：`AI/frontend.md`（索引）

## 设置页面（`panel-settings`）

### 结构与导航
- 左侧 `.st-nav`（`role="tablist"`）列出五个分区，右侧 `.st-body` 同一时间只显示一个 `.st-section`：外观与显示 `#st-sec-appearance`、访问与安全 `#st-sec-access`、AI 识别 `#st-sec-ai`、数据与存储 `#st-sec-data`、服务与运行 `#st-sec-service`。窄屏（≤860px）时导航改为横向滚动的一行。
- `openSettingsSection(name)` 切换分区、设置 `aria-selected` 与 roving `tabIndex`，并把分区写入 `localStorage('omrs-settings-section')`；非法名称回退到第一个分区。`settingsNavKey()` 支持方向键、Home、End。
- `loadSettings()` 由 `switchTab('settings')` 调用：先恢复上次分区和外观控件，再并行读取 `GET /api/config`、`GET /api/auth/session`、`GET /api/status`（经 `loadRuntimeStatus()`，其返回值供访问概览使用），结果存入 `ST_STATE = {cfg, auth, status}`，然后由 `fillSettingsForm()`、`renderAccessOverview()`、`renderPinControls()`、`settingsNetworkChanged()` 回填。读取配置失败时在 PIN 状态行显示错误，不再静默。
- 所有旧元素 ID 保持不变；状态提示统一经 `setSettingsStatus(id, text, tone)` 写入，文本先转义。

### 外观与显示
- `浅色 / 深色` 分段开关 `#st-theme-switch`（`setThemeMode()`）写 `localStorage('omrs-theme')` 并切 `<html data-theme>`；当前首帧脚本在没有保存值时选择**深色**，但设置页帮助文案仍写“默认浅色”，两者尚未同步。
- 「深色模式下反转题目图片颜色」`#st-invert-img`（`setInvertImg()`）写 `localStorage('omrs-invert-img')` 并切 `<html data-invert-img>`；仅在 `[data-theme="dark"][data-invert-img="1"]` 时对题图 `img` 应用 `filter:invert(1)`（简易白↔黑）。
- `#st-ledger-time-zone` 可选「跟随浏览器」（默认）、中国标准时间、UTC 和若干常用 IANA 时区；`setLedgerTimeZone()` 将选择写到 `localStorage('omrs-ledger-time-zone')`，立即重绘 Ledger 时间线和仪表盘最近动态。`formatLedgerTime()` 只转换带 `Z` 或 `±HH:MM` 偏移的时间戳；没有偏移的旧记录保留原有墙上时间，避免无依据地猜测来源时区。
- `syncThemeControls()` 与 `syncLedgerTimeZoneControl()` 由 `loadSettings()` 回填控件状态。外观和时区状态仅存浏览器 localStorage，**不入 config.json / Ledger**，故无需重启。

### 访问与安全：访问概览
- `#st-access-overview` 用一句话说明现在谁能访问（`describeAccess()`），并列出当前监听、远端 PIN、免 PIN 网段和本次连接身份。左侧色条 `data-level`：`local` 仅本机、`guarded` 局域网须 PIN、`open` 存在免 PIN 网段、`error` 读取失败。
- 当前监听取自 `GET /api/status` 的 `listen_external`（`runningListenExternal()`），不是已保存的 `allow_external`；两者不一致时概览提示「重启服务后生效」。读不到运行状态时回退到已保存配置。

### 访问与安全：远端 PIN
- `pinControlState()` 决定控件：已设 PIN 且本次连接为远端（含免 PIN 网段）时显示 `#st-pin-current-row`；只有远端且持有 PIN 会话时显示「退出远端登录」`#st-pin-logout`；「停用 PIN」`#st-pin-disable` 只在已设 PIN 的本机显示，局域网访问开启时禁用并在状态行说明原因。未设 PIN 时新 PIN 标签改为「设置 PIN」。
- `savePinSettings()` 先在前端校验 4–12 位数字、5–240 的整数分钟、首次必须填 PIN、远端须填当前 PIN，再 `POST /api/auth/pin`。只改空闲时间提示「空闲时间已改为 N 分钟」，更换 PIN 提示所有远端需重新登录；远端会话自己更换 PIN 后直接跳转 `/login`。`disablePin()` 先弹危险确认；`logoutRemote()` 在会话已过期时也会跳转登录页。

### 访问与安全：局域网访问
- 开关 `#st-allow-external` 对应 `config.allow_external`，免 PIN 网段 `#st-lan-pin-exempt-cidrs` 由 `parseLanCidrs()` 按中英文逗号和换行拆分。改动时 `settingsNetworkChanged()` 在 `#st-net-hint` 预告保存后果；未设 PIN 且无网段时提示先设置 PIN。
- `saveSettings()` 只在开关与实际监听范围不同（`networkNeedsRestart()`）时保存后调用 `doRestart(false, {}, 'st-net-status')`；只改网段保存后立即生效、不重启，避免清空内存中的远端会话。远端设备关闭局域网访问前先确认，因为重启后它将无法访问。

### 服务与运行：重启
- 「重启服务」调用 `doRestart(showStatus = true, readyOptions = {}, statusId = 'st-status')`：先读 `GET /api/auth/session` 的 `instance_id`，读不到则不发重启；再 `POST /api/restart`，由 `waitForRestartReady()` 每 500ms 探测一次（单次 1.5s 超时，总计 `RESTART_READY_TIMEOUT_MS` = 90s）。只有看到新的 `instance_id` 才 `window.location.reload()`；连接拒绝或 Abort 视为未就绪继续重试；超时后停在页面并提示检查 `omrs.service` 状态和日志，不再自动刷新或重试重启。
- 运行状态卡展示版本、已运行时间、托管题目数、服务状态、vault 路径和入口文件/数据目录；「刷新状态」重新调用 `loadRuntimeStatus()`。`GET /api/status` 还返回 `workspace_scan`，用于判断最近一次自检是否发现冲突。
- 「源码协助」卡的 `exportSanitizedSource()` 下载脱敏源码包，状态写 `#svc-source-status`。

### AI 识别
- 字段：`#st-ai-base`（API 地址，OpenAI 兼容，如 `https://api.openai.com/v1`）、`#st-ai-key`（API Key，密码框 + `#st-ai-key-toggle` 显隐切换）、`#st-ai-model`（模型名，带常见模型 datalist）、`#st-ai-restrict`（复选框「仅从已有知识点中选择」，对应 `config.ai_restrict_tags`，默认勾选）。
- **保存 AI 配置**：`saveAiSettings()` → `POST /api/config`，密钥输入非空时才提交 `ai_api_key`；留空保留已存密钥，清除按钮明确提交 `clear_ai_api_key:true`。三个按用途模型字段留空时回退 `ai_model`。保存即生效；状态写入 `#st-ai-settings-status`。
- 密钥不回显，仅根据 `ai_api_key_configured` 显示“已配置”；`#st-ai-restrict` 按 `cfg.ai_restrict_tags!==false` 置勾。
- `ai_restrict_tags` 开关含义：开启时 `classify` 的知识点被后端硬过滤为「已有分类 ∪ 已有知识点」；关闭时允许 AI 在无贴切已有项时新建知识点（仍优先复用，上限 4 个）。仅影响知识点，**科目/分类一直允许新建**。
- 仅作配置入口；实际识别在「录入题目」页触发，调用 `POST /api/ai-recognize`（后端转发，见 api.md）。

### 数据与存储：备份与恢复
- **导出备份**（`#svc-a-export`）：`exportOptimizeBackup()` → `POST /api/backup/export`，经 `downloadExportResponse()`（过渡桥全局，实现在 `assets/app/core/download.js`）下载 `OMRS-backup-YYYYMMDD-HHMMSS.zip`，响应头 `X-OMRS-Backup-Token` 存入 `OPT_BACKUP_TOKEN` 仅作记录。
- **导入备份**（`#svc-a-import` 触发隐藏的 `#opt-import-file`）：`importOptimizeBackup()` 以 `multipart/form-data` 调 `POST /api/backup/import` 预览，二次确认后 `POST /api/backup/restore {restore_id, confirm:true}` 覆盖恢复并 `reloadData()`。两个操作卡可用 Tab 聚焦，Enter/空格触发。状态写 `#svc-backup-status`。

### 数据与存储：存储与图片压缩
- 进入设置页 `loadSettings()` 调 `GET /api/optimize/summary`，`renderOptimizeChart()` 渲染：① 顶部「存储概览」标题 + 副标题状态（刚刚更新 / 扫描中… / 压缩中… / 快扫完成，由 `updateOptimizeControls()` 据 `OPT_JOB_TIMER`+`OPT_SCAN` 推断）+ 右侧总占用大数（`#opt-total`，取 `optValues()` 的 `center`）；② 三张**指标卡** `#opt-m-data/-files/-images`（写 `opt-l-/v-/d-/b-*`：标签取自 `item.label`、值 `formatBytes`、明细=文件数+note、卡底 3px 比例条按 `item.color`）；③ 一条**堆叠比例条** `#opt-seg-data/-files/-images` + 图例；④ 依赖 pill `#opt-deps`（Pillow / jpegtran / 题图总量）。
- **扫描图片**（操作卡 `#opt-a-scan`）：`scanOptimizeImages()` → `POST /api/optimize/scan` 起快扫 job，`startOptimizeScanPolling()` 轮询 `GET /api/optimize/job?id=`；进度区 `#opt-progress`（**固定占位**、无任务 `display:none`，不再 pop-in）显示已扫描/总数，`#opt-m-images` 加 `.scanning` 暖色高亮，完成后第三张卡标签切「可压缩大小 / 待深扫图片」。
- **确认压缩**（操作卡 `#opt-a-compress`）：`updateOptimizeControls()` 在「Pillow 可用 + 快扫有候选」时解锁，不要求先导出备份。`confirmOptimizeCompression()` 仍弹**二次确认**（提示会改写图片、可先到「设置 → 数据与存储」导出），随后 `POST /api/optimize/compress {scan_id, backup_token, confirm:true}`（`backup_token` 允许为空：后端 `start_compression` 已去掉令牌强制校验，只保留 `confirm`），`startOptimizeJobPolling()` 轮询进度/已节省，结束后 `loadOptimizeSummary()` 刷新。
- 扫描/压缩结果状态写 `#opt-status`；备份状态写 `#svc-backup-status`（在「备份与恢复」卡）。全局 `OPT_SUMMARY/OPT_SCAN/OPT_BACKUP_TOKEN/OPT_JOB_TIMER` 保留语义不变。

### 工作区扫描
- 「扫描」按钮调用 `POST /api/scan` 执行工作区自检与投影重建。
- 后端服务启动后也会立即扫描，并每 10 分钟后台扫描一次。
