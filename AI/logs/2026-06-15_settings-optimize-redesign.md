# 2026-06-15 设置-优化卡重设计 + 备份迁移 + 压缩不强制备份

> 前端为主 + 一处最小后端放宽。版本不变（`v1.5.0`）。全局 `OPT_SUMMARY/OPT_SCAN/OPT_BACKUP_TOKEN/OPT_JOB_TIMER` 与所有 `/api/optimize/*`、`/api/backup/*` 端点形状均不变。

## 背景
用户觉得设置页「优化」卡片交互太生硬（生硬的环状图 + 一排扁平按钮），要求：① 重做成更易读、进度自然融入的卡片；② **压缩不强制先备份**；③ 备份功能**移到「服务设置」**。随附一份详细设计稿，并说明「文本里与我冲突的地方按我定」——故对设计稿中「必须先备份」「后端不改」两点以用户口径为准。

## 改动
**HTML（`omrs_dashboard.html`）**
- 「优化」卡：环状图 + 引线 + 图例 + 4 按钮 → 头部（存储概览 + 状态副标题 + 总占用大数）+ 三张指标卡（数据链/题目文件/题目图片，含卡底比例条）+ 堆叠比例条 + 固定占位进度区 + **两张操作卡**（扫描图片 / 确认压缩）+ 依赖 pill + `#opt-status`。
- 「服务设置」卡：新增「数据备份」分隔区，放**导出备份 / 导入备份**两张操作卡（沿用 `.opt-action` 设计）+ 隐藏 `#opt-import-file` + `#svc-backup-status`。

**CSS（`assets/styles.css`）**
- 删除 `.opt-layout/.opt-donut*/.opt-callout*/.opt-legend*` 整段及 v1.3.0 覆盖段中对应规则；新增 `.opt-head*/.opt-metrics/.opt-metric*/.opt-bar*/.opt-action*/.aicon-*/.svc-sub-title`；保留 `.opt-dot/.opt-pill*/#opt-deps`、进度区 `.opt-progress*` 与 `optScanPulse`。操作卡图标用内联 SVG（放大镜/压缩/下载/上传），颜色走语义 token（trap/attack/kill/accent）。

**JS（`assets/app.js`）**
- 重写 `renderOptimizeChart`（环图→指标卡+堆叠条；调 `optValues()` 不变）、`updateOptimizeControls`（操作卡 disabled/busy + 据状态写头部副标题；**去掉备份前置**，压缩只看 Pillow+候选）；删 `renderOptimizeCalloutLines`；`confirmOptimizeCompression` 去掉 `OPT_BACKUP_TOKEN` 前置、保留二次确认、`backup_token` 传 `||''`；`exportOptimizeBackup`/`importOptimizeBackup` 状态从 `#opt-status` 改写到 `#svc-backup-status`；新增 `svcBackupStatus()`；`pollOptimizeScanJob` 去掉「请先导出备份」措辞；`startOptimizeJobPolling`/`startOptimizeScanPolling` 改用 `updateOptimizeControls()` 管理忙碌态（不再点名按钮）；`scanOptimizeImages` 去掉对已删除 `#opt-scan-btn` 的引用。

**后端（`omrs/optimization.py`）— 最小放宽**
- `start_compression()` 去掉 `if not _valid_backup_token(...) raise`，备份改为**可选**；仍保留 `confirm=true` 安全确认。`backup_token` 形参与 API 形状不变（仅不再作前置条件，留作审计）。

## 校验
- `node --check` 全部 12 个 JS 通过；`renderOptimizeChart` 等 9 个函数原地替换、`renderOptimizeCalloutLines` 删除、`svcBackupStatus` 新增；无残留 `opt-donut/opt-callout/opt-scan-btn/opt-compress-btn` 引用。
- `py_compile omrs/optimization.py` 通过。
- 截图复核四态：深色空闲 / 浅色已扫描（压缩**无需备份**即解锁）/ 深色扫描中（进度内嵌、图片卡高亮、卡片忙碌）/ 服务设置备份区。
- 参考随附的 ui-ux-pro-max 与 web-design-engineer 技能：匹配既有暖石墨视觉语汇、SVG 图标而非 emoji、破坏性操作保留二次确认、进度固定占位避免 pop-in。
