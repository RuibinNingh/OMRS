# 优化空间 / 技术债清单

> 初次整体代码与架构走查完成于 2026-06-15，2026-07-24 又按 Git 历史与当前工作区校正文档状态。覆盖：架构文档、后端请求/数据层（`server.py`、`cli.py`、`projections.py`、`ledger.py`、`ai_assist.py`）、前端 JS/CSS 的模式层面。**未**逐行审计算法模块（`optimization.py` / `scheduling.py` / `analytics.py`），故不含算法正确性结论。
>
> 标注:影响 / 工作量 / 状态。勾掉时把 `[ ]` 改成 `[x]`。

---

## 最值得动的

- [ ] **服务器单线程,AI 识别时整界面卡死** — 影响:高 / 工作量:中
  `cli.py` 用 `socketserver.TCPServer`(非 Threading),一次只处理一个请求。而 `ai-recognize` 同步调外部大模型(`ai_assist.py`,带 timeout,可能十几秒),期间任何请求都被阻塞;局域网多设备也排队。
  改法:换 `ThreadingHTTPServer` / `ThreadingTCPServer` + `daemon_threads=True`。**代价**:并发后文件型数据层(CSV / Markdown / ledger)写入需加锁——给改动型端点 + `append_commit` / `rebuild_projection` 套一把全局 `threading.Lock`。

- [ ] **投影是全量重放整条 ledger** — 影响:中(随时间恶化)/ 工作量:中高
  `projections.py` 的 `rebuild_projection` / `_project_state` 都 `read_commits(ascending=True)` 后从头 `for commit in commits` 算到尾。提交链只增,成本随历史线性增长——题做多了(几千 commit)每次重建肉眼变慢。
  改法:定期落投影快照(snapshot at seq N),之后只重放增量。`ledger_history` 已分页,这点很好。

## 可维护性(「臃肿 / 草率」的根)

- [x] **前端 JS 杂烩文件已按职责拆分(v1.5.0 完成)**
  原 `schedule.js`(约 100 行)混了导出 / Session / 反馈页 / 录入提交 / 历史时间线 / 扫描六件事。已拆出 `export.js`、`feedback.js`、`history.js`,`schedule.js` 仅留 Session + 扫描 + 录入提交。因共享全局作用域,拆分零行为改动(函数名/签名/调用全不变,72 个函数原样,`node --check` 通过)。
  **后续**:`app.js`(26KB,含录入页图片/AI 逻辑 + init)与 `recommend.js` 也偏大,可在需要时再拆;前端整体可考虑迁移原生 ES Module(浏览器免构建),但**前提是先把行内 `onclick` 换成 `addEventListener`**(模块作用域下行内 handler 失效)。

- [ ] **CSS 一层层叠,有真实重复定义** — 影响:中 / 工作量:中 / 风险:低
  `styles.css` 里 `.form-group`、`.fb-toggle`、`.instant-head` 等被定义两遍(历次「现代化」往后追加却没删旧的)。注意约 30 个「重复」里不少是合理的响应式 / 深色 `@media` 覆盖,不算债;上面这几个是真叠加债。建议按组件集中收拢(配合截图回归)。即时练习页已清理了一批孤立规则,重复的 `.shell` 也已删除(全宽改造时)。

- [ ] **后端路由是超长 if/elif** — 影响:中 / 工作量:中
  `server.py` 的 `do_GET`(~150 行)/ `do_POST`(~280 行)是手写分支链,`json.loads(body)` 重复十几次。可收成 `{(method, path): handler}` 派发表 + 统一 body 解析。纯整理,降认知负担。

- [ ] **前端整块 innerHTML 重渲染 + 行内 onclick** — 影响:中 / 工作量:高
  项目仍广泛使用 `innerHTML=` 和模板内 `onclick=`；具体数量会随功能变化，不在此硬编码。它们会导致高频交互重建整块 DOM、标记与逻辑混在字符串中，并阻碍 ES Module 化。务实改法：先把队列、反馈行等高频区域改为局部更新和事件委托。

## 健壮性

- [ ] **测试覆盖仍偏低** — 影响:中高 / 工作量:中
  当前已有 `test_history_projection.py`、`test_ai_assist_taxonomy.py`、`test_report_export.py`，覆盖历史撤销/恢复/替换、AI 分类约束与答案提示词、报告材料及部分 HTML 导出契约；当前工作区还增加 Markdown 表格与题间留白测试。核心缺口仍是 `compute_mastery_update` / `compute_priority` / SM-2 的边界、Ledger append→projection 集成、CSV/Markdown 异常输入和浏览器端 A4/屏幕模板回归。

- [ ] **首次主题与页面提示不一致** — 影响:低 / 工作量:低
  `omrs_dashboard.html` 首帧脚本在 `omrs-theme` 不存在时实际选择深色，但设置页帮助文案仍写“默认浅色”。应明确产品意图后统一启动逻辑、页面提示、根 README 和 `AI/frontend.md`；当前文档按真实启动行为记录为默认深色。

## 锦上添花

- [ ] `reloadData()` 每次改动全量刷新(~10 处调用):小数据无感,量大偏重,可改局部更新。
- [ ] **运行时外链 Google Fonts**:离线/弱网首屏阻塞 + 每次访问请求 Google。既然 KaTeX 已本地化,把字体也 vendoring 进 `assets/vendor/` 更彻底(离线 + 隐私 + 首屏)。工作量低。
- [ ] **局域网模式无鉴权**:`allow_external` 开启后同网段可读写、甚至命中 `/restart`。个人用通常可接受,知道边界即可。

## 已经做得好的(不要动)

- `_serve_asset`(`server.py`)路径穿越防护扎实(`normpath` + 限定 `assets/` 内);assets 一律 `Cache-Control: no-cache`。
- ledger 不可变链 + 投影的设计有想法;`ledger_history` 分页合理。
- 核心运行时只依赖 Python 标准库；Pillow、jpegtran 只用于可选图片优化，不影响基础服务和导出。
- 根 `AGENTS.md` + `AI/README.md` 已把“每次持久化任务同步模块文档、任务日志和索引”设为完成条件。
