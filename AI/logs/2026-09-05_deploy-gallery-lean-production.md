# 2026-09-05 v1.14.2 前端增量部署：题库画廊卡精简（gallery-lean）

## 变更摘要

部署上传包 `OMRS-gallery-lean-20260905.zip`（README 标题标 v1.14.1，但该版本号今天 12:55 已被展示板打印预览修复占用、version.py 现为 v1.14.2；**此包不含 version.py，属 v1.14.2 之上的纯前端增量**，未改动版本号避免重号）。改动 5 个文件，无新增文件、无接口改动、无构建步骤：

- `assets/questions.js` / `assets/qtable.js` / `assets/styles.css` / `omrs_dashboard.html` / `AI/frontend.md`

核心行为：画廊卡从「8 条等权横带」改为「标识 / 题面 / 脚注」三层精简（默认）；元数据收进「列 / 密度」菜单新开关「显示元数据」（`QB_GALLERY_DETAIL`，localStorage `omrs-qb-gallery-detail`，默认关）。详见包内 `交接文档_gallery-lean.md`（README 七点：去重、去卡中卡、只报异常、悬停收纳、密度、截断改渐隐、chips 空行）。

## 部署前状态

- 生产版本：`v1.14.2`；`/api/status`：`status=ok`、题目数 `147`、`conflict_count=0`
- 工作树含多项未提交改动（v1.14.1 部署 + 推荐/session 修复 + functional-bug-fixes 文档），完整状态存回滚包；本次只动上述 5 个文件，未触碰其他
- 基线核验：`git apply --check` 通过；在 /tmp 整树副本应用补丁后 5 文件与包内文件**逐字节一致**（含本地未提交的 `AI/frontend.md` 改动——包基线即当前磁盘状态，无内容丢失）
- 原始包 SHA-256（zip）：见回滚包 `MANIFEST.sha256`

## 备份

回滚包：`/root/workspace/apps/releases/OMRS-gallery-lean-rollback-20260905-213355/`

含：源码快照（omrs/ assets/ AI/ tests/ Skills/ deploy/ 等 253 文件）、`pre-deploy-git-status.txt`、`uncommitted-worktree-v1.14.2.patch`（部署前全量 git diff）、原始上传 zip、交接文档。`sha256sum -c MANIFEST.sha256` 全过（首版 MANIFEST 因自包含自身报 1 处 FAILED，排除自身后重生成，253/253 OK）。

## 部署步骤

```bash
cd /root/workspace/apps/OMRS
git apply gallery-lean.patch        # 5 文件全部 cleanly applied
```

部署后 `cmp` 逐文件核对与包内一致；HTML 缓存串 `20260904-board-rework` → `20260905-gallery-lean`。未部署 `Task/`、manifest（包内本无）。`错题/`、`omrs_engine.py`、systemd 单元未触碰。

## 门禁

- 生产树 `python3 -m unittest discover -s tests`：**56/56 OK**
- 生产树 `node --test tests/*.js`：**29/29 pass**（含前端 8 个既有测试，与改动前一致）
- 包树（/tmp 补丁后副本）与生产树同源字节一致，不再重复跑

## 重启与健康检查

`systemctl restart omrs.service` 首次遇 **bind 竞态**（`OSError: Address already in use`，旧进程 8471 未及释放，v1.11.0 部署时同款），systemd `Restart=on-failure` 自动拉起成功（restart counter 3）。最终：

- `systemctl is-active`：active；PID 256754
- `/api/status`：`status=ok`、`version=v1.14.2`、`question_count=147`、`conflict_count=0`
- `/m`：HTTP 200 text/html
- 页面 HTML 已带 `20260905-gallery-lean` 缓存串

## Live 浏览器验收（headless Chrome，localhost:8471 → 题目库 tab → 画廊视图）

- **精简默认态**：147 卡渲染；卡结构 = `.gallery-head`（`.gc-pick` 复选框 + `.gc-id` 的 `.gc-cat`/`.gc-num` 拆「分类+序号」+ `.gc-flags` 条件 badge + `.gc-more` ⋯）/ 题面（`.q-md` 透明无边框）/ 脚注
- **去重**：首卡（物质分类与变化13）meta 行无「· 物质分类与变化」重复；`knowledge_tags` 与 category 同名已过滤，为空整行不渲染（无「无额外知识点」占位）
- **只报异常**：常驻「待攻克」badge = 0；仅条件 flag（今日 / 逾期 / 顽固 / 停用）；熟练度 0 显示「未练习」92 处、无空进度条
- **悬停收纳**：headless 命中 `@media (hover:none)` 常显分支（复选框/⋯/+标记常显属预期）；桌面 `hover:hover` 分支规则静态核对在位（styles.css L1770-1772 pick、L1785-1786 more、L1836-1838 触屏兜底），真机待用户侧确认
- **整卡点击开 Modal**：委托在 questions.js L149-153（`#panel-questions [data-q-row]`，排除 button/input/label/a/标记/⋯菜单），点击第 2 张卡成功打开并渲染「物质分类与变化6」详情，父页未跳转
- **截断渐隐**：147 卡中 1 张 `.is-clipped`（仅真溢出才加）；`metaAbsent` 默认下无渐隐误伤短题
- **chips 空行**：`.qb-chips` 无激活条件时为空且 `display:none`
- **密度/限宽**：wrap `max-width:1440px`；网格 minmax(260px)
- **新开关**：默认关（localStorage 无键）；「列 / 密度 ▾」→「画廊 · 显示元数据」勾选后 localStorage=`1`，147 卡全出 `化学 · 上次复习 2026-09-04 · 衰减后 x%` 行；移除键 + 重载恢复精简
- **console.error 全程 0 条**；截图目检无乱码/错位/溢出（KaTeX 化学式正常，深色主题）

## 未做的事

- 包 README「还没做的」两项未处理：qb-bar 三行合并结构改动、大题库虚拟滚动/分页
- 桌面悬停显隐未在真机复核（headless 无 hover 能力），用户打开 `http://localhost:8471/` 题目库即可肉眼确认

## 收尾

- 未提交 Git（生产保持未提交工作树，提交时机由用户决定）；`AI/frontend.md` 更新随包并入
- 部署日志见本文件；`AI/logs/log.md` 已加索引行

## 回滚方式

```bash
cd /root/workspace/apps/OMRS
# 从回滚包 zip 取出补丁后反向应用：
unzip -p /root/workspace/apps/releases/OMRS-gallery-lean-rollback-20260905-213355/original-upload-gallery-lean.zip gallery-lean.patch | git apply -R
# 或直接从回滚包快照恢复 5 个文件（assets/questions.js assets/qtable.js assets/styles.css omrs_dashboard.html AI/frontend.md）
# 随后 systemctl restart omrs.service
```

`错题/` 未修改无需恢复。
