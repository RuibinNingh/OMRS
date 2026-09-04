# 2026-09-03 收件箱 P3：框选提供方 / 盲标 / 自动策略 / 清理（v1.13.0）

接 `2026-09-03_inbox-intake.md` 交付后的新任务：执行交接文档 §3 第 2–6 项与 §5 两条已知问题。

## 行为变化
- `detect` 单元新增 `provider`（`vlm` / `template` / `local_http`，缺省取 `inbox_detect_provider`）与 `blind`；结果多 `provider / blind / hidden / auto`；`ai.detect` 事件记 `provider`。
- 新 job 类型 `auto`（服务端切片 → detect → 自动策略）；`inbox_auto_on_upload` 打开时上传即排 `auto` job（响应多 `job`）。
- 盲标：命中时不写 regions，只写 `items.blind_boxes`；`item.ready` 事件成对带 `ai_boxes` 与 `blind_eval`；`dataset/stats` 多 `blind`、`storage`；导出 `labels.jsonl` 多 `blind / blind_ai_boxes`。
- 自动策略：`inbox_auto_ready_conf` 达标且无人工框 → 自动转文本 → ready；失败记 `item.auto` 事件停在 boxed。
- 新端点 `POST /api/inbox/cleanup`；上传时自动清理超期丢弃原图；`raw_file` 对已清理项报「已被清理」；`items.file` 置 NULL。
- 拒绝 AI 框数改为 `meta.rejected_ai_boxes` 增量计数（老库首次统计回填）。
- `inbox.db`：新表 `meta`，`items` 新列 `blind`、`blind_boxes`（`connect()` ALTER 补齐）。
- `config.json` 新键 6 个 `inbox_*`（`CONFIG_DEFAULTS`）。
- 前端：「▦ 模板框选」按钮 ×3；AI 训练页盲标评估集、存储、清理按钮、策略表单；大裁图自动 JPEG；detect toast 汇总盲标 / 自动就绪 / 失败。
- 旧接口与默认行为不变：不配置任何 `inbox_*` 键时，`detect` 仍走 VLM、不盲标、不自动就绪、丢弃图 7 天后才清理。

## 影响文件
`omrs/inbox.py`、`omrs/ai_assist.py`（`detect_regions_local`）、`omrs/server.py`（`/api/inbox/cleanup`）、`omrs/common.py`、`omrs/version.py`（v1.13.0）、`assets/inbox.js`、`assets/styles.css`（`.ib-pl-grid`）、`omrs_dashboard.html`、`tests/test_inbox.py`（+6 例）、`AI/inbox.md`（§2/§3/§4/§5/§6/§7 更新，新增 §8）、`AI/api.md`、`AI/data.md`、`AI/frontend.md`、`AI/README.md`、根 `README.md`、`Task/录入流程重构规划.md`（状态）、`Task/HANDOVER_2026-09-03-2.md`（新）。

## 验证
- `python3 -m unittest discover -s tests`：39 例通过（inbox 14 例，新增 6 例用 `FakeAI` 替身覆盖模板 / provider 分派 / 盲标 / 自动策略 / 上传即 auto / 清理）。
- `node --check assets/inbox.js` 通过。
- 真实服务端（临时 vault）：HTTP 上传 → `layout=zuoyebang` → `jobs detect provider=template` 得 2 框（题目 y≈0.036 像素锚定，答案到底）→ 切 `local_http` 指向不可达地址得「连不上本地检测服务」错误 → `dataset/stats` 含 `blind`/`storage` → `cleanup` 返回 0 → `/api/config` 回读。
- Playwright：录入页上传 → 处理页模板框选出 2 框 → AI 训练页盲标 / 存储文案、保存策略并回读（provider=template、blind=3、conf=0.85，local 行按提供方隐藏）→ 清理 toast；除沙箱断网导致的一条外部资源 403 外无 JS 报错。
- 未验证：VLM / 本地检测服务 / 自动转文本的真实模型调用（沙箱无网络）。
