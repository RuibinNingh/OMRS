# 2026-09-05 v1.14.2 前端增量部署：题库 UI 优化（qb-layout）

## 变更摘要

部署上传包 `files (17).zip`（内层 `OMRS-题库UI优化.zip`）。**纯前端 + 测试增量**，无后端/接口改动，无 version.py（生产保持 v1.14.2，避免重号）。改动 6 文件：

- `assets/qtable.js` / `assets/questions.js` / `assets/qview.js` / `assets/styles.css` / `omrs_dashboard.html`
- `tests/test_md_linebreaks.js`（新增，8 个用例）

行为要点（自补丁代码归纳）：
1. **画廊列数**：`QB_GALLERY_COLS`，0=自动（按卡片最小宽度铺满）/ 1–6=固定列数；localStorage `omrs-qb-gallery-cols`；数据经 `qbClampCols()` 夹取 0–6。
2. **题面换行模式**：`QB_MD_MODE`，`lean`=忽略单个换行（当前默认，题面在卡片/表格里按段落流式）/ `full`=保留原文每处换行；localStorage `omrs-qb-md-mode`。
3. **菜单按视图分流**：`qbCurrentView()` 区分表格/画廊；表格视图菜单只露「列 + 行密度」，画廊只露「列数 + 卡片密度」，触发器文案联动「列 / 密度」↔「列数 / 密度」（`#qb-layout-label`）。
4. 密度（舒适/紧凑）对表格与画廊都生效；画廊列数写成 `data-cols` 由 CSS 决定 grid。
5. HTML 缓存串 `20260905-gallery-lean` → `20260905-qb-layout`。

## 部署前状态

- 生产版本：`v1.14.2`（紧接上一条 gallery-lean 前端增量，21:35 部署）；`/api/status`：`status=ok`、题目数 `147`、`conflict_count=0`
- 基线核验：`git apply --check` 通过（补丁基于**含 gallery-lean 的当前生产树**，无顺序冲突）；/tmp 整树副本应用后 6 文件与包内导出**逐字节一致**
- 外层 zip 无独立交接文档、无 README；内层含源码导出 + qb-ui.patch（外层/内层补丁逐字节相同）
- 工作树含历史未提交改动（v1.14.1 部署、推荐/session 修复、functional-bug-fixes 文档、gallery-lean），完整状态存回滚包

## 备份

回滚包：`/root/workspace/apps/releases/OMRS-qb-ui-rollback-20260905-222301/`

含：源码快照 254 文件、`pre-deploy-git-status.txt`、`uncommitted-worktree-v1.14.2.patch`（部署前全量 git diff）、原始上传 zip、补丁副本。`sha256sum -c MANIFEST.sha256` 0 失败。

## 部署步骤

```bash
cd /root/workspace/apps/OMRS
git apply qb-ui.patch    # 6 文件全部 cleanly applied
```

部署后 `cmp` 逐文件与包内导出核对一致。未部署 `Task/` 等（包内本无）；`错题/`、`omrs_engine.py`、systemd 单元未触碰。

## 门禁（生产树）

- `python3 -m unittest discover -s tests`：**56/56 OK**
- `node --test tests/*.js`：**37/37 pass**（29 既有 + 新增 test_md_linebreaks.js 8 用例），0 fail
- 包树（/tmp 补丁后副本）与生产树同源字节一致

## 重启与健康检查

`systemctl restart omrs.service` 一次成功（本次无 bind 竞态）。

- `/api/status`：`status=ok`、`version=v1.14.2`、`question_count=147`、`conflict_count=0`
- `/m`：HTTP 200 text/html
- 页面 HTML 已带 `20260905-qb-layout` 缓存串

## 验收说明

按用户指示**跳过浏览器实测验收**；以上门禁 + API + 页面缓存串为部署判定依据。UI 行为（列数 1–6、lean/full 换行、视图化菜单）建议下次打开页面时肉眼确认。

## 未做的事

- 浏览器 UI 实测（用户明确跳过）
- `AI/frontend.md` 未随包更新：本包不含文档改动；且该文件正被并行会话修改，本次不代为编辑以免覆盖。题库 UI（列数/换行模式/视图菜单）的文档同步待后续任务补齐。

## 收尾

- 未提交 Git（生产保持未提交工作树，提交时机由用户决定）
- 部署日志见本文件；`AI/logs/log.md` 已加索引行

## 回滚方式

```bash
cd /root/workspace/apps/OMRS
unzip -p /root/workspace/apps/releases/OMRS-qb-ui-rollback-20260905-222301/original-upload-qb-ui.zip qb-ui.patch | git apply -R
# 或直接从回滚包快照恢复 6 个文件；随后 systemctl restart omrs.service
```

`错题/` 未修改无需恢复。
