# 2026-06-10 全面排查 + 4 处加固修复

## 背景

对全项目（后端 `omrs/` 全模块、前端 `assets/` 全脚本、两套导出模板、HTML 内联事件）做一轮系统性排查与全管线实测：索引 / 推荐 / 统计 / 分析 / A4 与屏幕版导出（图片 base64 内联）/ 反馈闭环（连续击杀→回退、SM-2 间隔 1→6→15→重置 1、EF 第 3 次起调整、Markdown 历史与 frontmatter 标签同步）均通过。排查发现 4 处实际问题，按最小侵入修复。

## 修复

1. **`omrs/scheduling.py` · `compute_priority`**：`decayed_mastery` / `days` 参与运算前补 `_safe_float` / `_safe_int` 钳制。此前 mastery CSV 出现脏数据（空串/非数字）时会 `TypeError`，**一行脏数据崩掉整次调度**；现在按安全默认值参与计算。
2. **`omrs/log_utils.py`**：`_LOG_DIR` 单全局缓存改为 `_LOG_DIRS` 按 **vault 绝对路径**字典缓存。此前同进程先后操作多个 vault（如 CLI 跑测试库再跑正式库）时，运行日志会写进第一个 vault 的目录（日志串台）。
3. **`omrs/reports.py`**：报告 ID 校验 `_ID_RE` 由 `^RPT-\d+$` 放宽为 `^RPT-[0-9A-Za-z]+(?:-\d+)?$`。同秒提交两份报告时存盘名会追加 `-N` 后缀，旧正则导致这类合法 ID 无法通过 `/api/report/view` 读取。
4. **`assets/schedule.js` · 反馈页**：`fbRows` 初始 `correct: null`（原默认 `false` 渲染成红色「答错」，**漏判直接被当答错提交**）；`renderFb` 高亮改 `===true/===false` 严格判断；`submitFb` 提交前校验仍为 `null` 的未判定行并 alert 中止。

## 记录在案（未改）

- `core.js::scoreScheduleCandidate` 仍用旧 `difficulty/10` 公式——仅 demo 离线兜底路径使用，与后端统一优先级无关，非 bug。
- 安全隐患（已口头汇报、待专项处理）：`server.py` `do_GET` 兜底 `super().do_GET()` 会从 CWD 提供任意文件（可暴露 `错题/.omrs/config.json` 含 AI 密钥）；所有响应 `Access-Control-Allow-Origin: *` 使任意网页可跨域读 `/api/config`；单线程 `TCPServer` 在 AI 识别长请求时冻结 UI；缺 `allow_reuse_address`。

## 验证

- Python 全模块 `compileall` + 导入冒烟通过；`node --check` 全部前端脚本通过；HTML 45 个内联事件调用函数全有定义。
- 测试库（`testvault`：三角函数1 含图、动能定理1）走真实管线复测：脏 mastery 行不再崩调度；多 vault 日志各归各家；`RPT-xxx-2` 可读；反馈页漏判会被拦截。
