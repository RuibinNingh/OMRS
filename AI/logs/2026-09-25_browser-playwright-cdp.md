# OMRS Playwright 浏览器崩溃绕行与验收恢复

日期：2026-09-25

## 目标与结论

修复当前主机上 Playwright 独立启动 Chromium 访问 OMRS 页面时的 `Page crashed` 验收阻断。已实现可选 CDP 浏览器接入并完成实际 smoke、视觉截图与对比；**独立 Chromium 崩溃的底层原因仍未确定**，因此这是可回退的测试运行时绕行，不是对 Chromium 根因的修复，也不代表 OMRS 生产服务曾故障。

## 改动

- 新增 `tests/browser_runtime.py`：读取 `OMRS_TEST_CDP_URL` 并连接已运行的 CDP 浏览器（超时 15 秒）；变量为空/未设置时保留 Playwright 原有独立启动参数。
- 将 OMRS Playwright smoke 与 `tests/visual/run.py` 的 Chromium 启动统一接入该 helper。使用 Hermes CDP 时测试仍创建各自的 BrowserContext；运行结束只断开 Playwright，不关闭 Hermes 浏览器。
- 视觉脚本以 `/` 根路由探测服务就绪，兼容不提供 `/api/auth/session` 的旧基线；像素差异计算改用 Pillow，不依赖当前解释器缺失的 NumPy。
- 新增启动器与图片差异单测；`AI/environment.md` 记录安全使用方式。按文档门禁提示重新生成 `AI/routes.md`，以对齐工作树中现有路由。

运行示例：`OMRS_TEST_CDP_URL=http://127.0.0.1:9222 python3 -B -m unittest tests.smoke_schedule_workbench -v`。只使用受信任的本机 CDP 地址，不要暴露到公网。

## 验证

- RED→GREEN：新启动器测试在 helper 不存在时按预期导入失败；图片差异测试在旧实现上因 `numpy` 不可用失败。实现后两个测试分别通过（2/2、1/1）。
- `python3 -B -m unittest discover -s tests -v`：152 项通过。运行中出现现有文件未关闭的 `ResourceWarning`，未导致失败。
- 复习工作台 Playwright smoke（连接 Hermes CDP）：1/1 通过。
- 展示板打印/完整性/几何 smoke：15 项中 14 项通过；`tests.smoke_board_integrity.BoardIntegritySmokeTest.test_switch_during_export_records_original_board_only` 在整组及单独重跑时均失败，错误为已记录页数但 `printed.items` 为空导致 `IndexError`。此问题与 `Page crashed` 不同，本次未改业务实现，仍需另行调查，不能把该组报告为全绿。
- 视觉 `--audit-only`：退出码 0，截图完成，页面脚本错误为 0。完整 `--ref HEAD` 对比：48 组截图全部生成，脚本错误为 0；39/48 组存在像素差异，设置页差异最大（深色移动端 73.598%）。这表示对比已跑通，不等于像素一致或差异已人工全部认可。报告：`/root/.hermes/cache/scratch/omrs-playwright-cdp-visual-20260925-final/report.html`。
- `python3 tests/check_docs.py`：28 个文档、0 问题、1 条提醒（`AI/api.md` 为 52KB，建议拆分）。`git diff --check` 通过。
- Hermes Browser Use 会话 `omrs-p0-live` 再次读取本机页面成功：标题 `🐴 OMRS — 错题重构系统`，正文 1,073 字符。

## 范围与遗留

未修改 OMRS 业务页面/后端，未重启或写入生产服务，也未提交 Git。`OMRS_TEST_CDP_URL` 未设置时仍走原独立 Chromium 路径；若移除该环境变量，已知独立 Chromium 崩溃问题仍可能复现。剩余事项：继续定位独立 Chromium 根因；另行调查上述一项展示板 smoke 失败；人工审阅报告中非零视觉差异。
