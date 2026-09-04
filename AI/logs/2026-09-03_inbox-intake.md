# 2026-09-03 收件箱录入流程（上传 → 处理 → 录入）

## 变更摘要
- 新增 `omrs/inbox.py`：收件箱暂存层（SQLite + raw/ + crops/ + annotations.jsonl）、上传去重、区域/题卡更新与就绪校验、后台 job（detect / extract / classify）、长图切片与跨条带框合并、`commit` 复用 `create_question`、数据集统计与导出（JSONL / YOLO）。
- `omrs/ai_assist.py`：按用途选模型（`ai_model_detect/extract/classify`）、`detect_regions` + `parse_detect_output`（兼容 0–1000 / 绝对像素 / 小数坐标）、`extract_region`（转录 + 可转性判断）。
- `omrs/server.py`：`/api/inbox/*` 路由、`_multipart_files` 多文件解析（修正 filename 解析把 Content-Type 行拼进文件名的问题）、`/m` 手机上传页。
- 前端：`assets/inbox.js` 新模块；`omrs_dashboard.html` 的 `#panel-create` 改为流程条 + 五个阶段（原表单保留为「快速录入」）；`styles.css` 末段 `ib-*` 样式；`app.js` 的 `switchTab` 钩子、粘贴分流、设置页三个按用途模型字段。
- `omrs/common.py` 配置默认键；版本 v1.12.0。

## 行为与兼容性
- 旧 `/api/create`、`/api/ai-recognize` 与单题表单行为不变。
- 收件箱数据不进 Ledger；只有 commit 写题库。
- 无 Pillow 时部分区域裁图由前端 canvas 提供；后台 job 缺裁图会单元报错而不中断。

## 修改文件
`omrs/inbox.py`（新）、`omrs/ai_assist.py`、`omrs/server.py`、`omrs/common.py`、`omrs/version.py`、`assets/inbox.js`（新）、`assets/inbox_mobile.html`（新）、`assets/styles.css`、`assets/app.js`、`omrs_dashboard.html`、`tests/test_inbox.py`（新）、`AI/inbox.md`（新）、`AI/api.md`、`AI/data.md`、`AI/frontend.md`、`AI/optimization.md`、`AI/README.md`、`README.md`、`Task/录入流程重构规划.md`（新）、`Task/HANDOVER_2026-09-03.md`（新）。

## 验证
- `python3 -m unittest discover -s tests`：33 例通过（含新增 8 例）。
- 真实服务端到端：启动 `serve`，用手机 UA 上传 3 张作业帮长截图 + 2 张其他图 → 浏览器（Playwright）进入录入页 → 处理页画框（文本 + 保留图）→ 标记就绪 → 录入页填科目/分类 → 创建 → 题库出现 `集合1.md`、`附件/集合1-0001-a-1.png`，`dataset/stats` 统计正确，`annotations.jsonl` 10 条事件，页面无 JS 报错。
- AI 相关 job（detect / extract / classify）未接真实模型验证，仅验证了任务框架、坐标解析与错误回传。

## 同步过的文档
`AI/inbox.md`、`AI/api.md`、`AI/data.md`、`AI/frontend.md`、`AI/optimization.md`、`AI/README.md`、根 `README.md`。
