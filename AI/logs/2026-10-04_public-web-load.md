# 2026-10-04 公网首屏与刷新加载优化

## 背景

用户原话：「OMRS速度能不能优化?」「在公网的话不像内网传输那么快」。补充定位为「首次打开或刷新页面」。执行者：Codex，完整模式；基线为 `21b4bb1`，开工 `git status --short` 为空。本任务不属于既有计划。

现有主入口同步加载原生模块图，浏览器实测加载 214 份 JS 和 61 份 CSS；原静态资源每次刷新需条件校验，后端文本没有 gzip。模拟公网测量和全部验证只使用演示 Vault、随机高端口，没有生产重启、推送、Nginx 修改或真实题库写入。

## 行为变化

- HTML、普通 JSON 和静态文本协商 gzip：至少 1KiB 且压缩有收益时启用，长度按压缩字节计算，保留 HEAD 和条件请求语义。登录和 MCP 凭据回执不压缩，图片、字体、视频、下载附件保持原字节。
- HTML 资源地址绑定资源树内容与生成器源码的 SHA256，版本资源可在浏览器私有缓存复用一年。HTML 保持 no-store，资源改变后新文档取得新版本，未知版本或版本内已改文件返回 404。
- 原生模块保持分层源码与相对 import；HTML 注入静态依赖的 modulepreload，提前发现依赖。
- 版本化主样式递归合并 CSS import，将 61 次 CSS 请求减少为 3 次；保留层级、顺序和相对字体路径。独立页面及原 /assets/ 地址继续兼容。
- 静态 gzip 缓存最多 128 份，每份原文最多 256KiB；用户接口正文不进入此缓存，派生样式和模块图随内容版本失效。

## 影响文件

- `omrs/server.py`：文本压缩协商、版本资源发送和 HTML 加载处理。
- `omrs/web_assets.py`：新增内容版本、路径校验、模块图、样式合并与静态 gzip 缓存。
- `tests/test_asset_cache.py`、`tests/test_web_assets.py`：gzip / HEAD / 304、版本资源授权、依赖变动、字体地址、穿越和符号链接验证。
- `tests/bench_web_load.py`：新增真实 Chromium 限速测量工具，每轮使用新上下文测首屏，再用真实 reload 测缓存刷新。
- `AI/api.md`、`AI/api/queries.md`、`AI/frontend/architecture.md`：当前传输和加载契约；`AI/environment.md`：测量入口；根 `README.md`：公网加载行为。
- 本日志与脚本生成的 `AI/logs/log.md`：任务记录和索引。

## 性能测量

基线源码来自 `git archive 21b4bb1`，隔离在 `/tmp/omrs-web-baseline`；同一演示数据生成入口、1440×900 Chromium、100ms 延迟、5Mbps 下载、1Mbps 上传，每组 3 轮。测量的是仪表盘初始数据实际可用时间，不包含人工输入 PIN；不等同于实际公网线路延迟。

```bash
OMRS_TEST_CDP_URL=http://127.0.0.1:9222 python3 tests/bench_web_load.py --tree /tmp/omrs-web-baseline --out /tmp/omrs-web-before.json --runs 3
OMRS_TEST_CDP_URL=http://127.0.0.1:9222 python3 tests/bench_web_load.py --out /tmp/omrs-web-after-final.json --runs 3
```

三轮中位数如下，所有加载均无脚本或 HTTP 错误：

| 指标 | 基线 | 当前 | 变化 |
|---|---|---|---|
| 首次仪表盘就绪 | 7,584ms | 5,323ms | 减少 29.8% |
| 缓存刷新就绪 | 5,546ms | 441ms | 减少 92.0% |
| 首次传输量（含文档） | 3,290,533 字节 | 1,675,160 字节 | 减少 49.1% |
| 刷新传输量（含文档） | 327,710 字节 | 32,621 字节 | 减少 90.0% |
| 首次 CSS 资源数 | 61 | 3 | 减少 58 次请求 |
| 刷新实际联网资源数 | 289 | 12 | 减少 277 次校验 / 下载 |

JS 仍为 214 个原生资源，未引入打包器。当前刷新复用 235 项资源缓存；总资源条目从 305 降为 247，首次实际联网资源数为 246。结果位于 `/tmp/omrs-web-before.json` 与 `/tmp/omrs-web-after-final.json`。

## 验证

### 已实际执行

- `python3 -m unittest tests.test_asset_cache tests.test_http_boundaries tests.test_security tests.test_write_lock -q`：43 项通过。
- `python3 -m unittest tests.test_web_assets tests.test_asset_cache -q`：最终 17 项通过。
- `python3 -m unittest discover -s tests -p 'test_*.py' -q`：最终 809 项通过，无跳过。
- `node --test tests/app/*.test.mjs`：449 项通过，无跳过。
- `python3 tests/check_ui.py`：全仓五类计数均为 0，0 处问题。
- `python3 tests/check_contrast.py`：58 组，0 组不达标。
- `python3 tests/app/run_browser.py`：34 项通过，0 失败。
- `python3 tests/e2e/shell_router.py`：24 项通过，涵盖 13 页直接进入、真实刷新、PIN、导航守卫、手机抽屉与 304。
- `python3 tests/e2e/entry_background.py`：5/5，默认黑洞和自定义背景的桌面 / 手机路径通过。
- `python3 tests/e2e/annotate.py`：34/34，独立页面、图片、持久框位、真实刷新及四档审计通过。
- `python3 tests/check_docs.py --write-log-index`：索引由脚本生成；`python3 tests/check_docs.py --diff HEAD`：102 份文档、0 问题，2 条既有计划篇幅提醒。
- `python3 tests/visual/run.py --ref HEAD --pages dashboard,data,questions,board,catalog,schedule,instant,feedback,create,history,reports,settings,ai-review,assistant --out /tmp/omrs-web-visual`：14 页 × 浅深色 × 桌面 / 手机，共 56 组前后截图；全部差异 0%，尺寸一致，两侧无脚本错误或页面横向溢出。样式合并没有引入视觉变化。

首次全量 Python 回归发现同大小快速覆盖文件时，文件系统可能保持完全相同的 mtime / ctime，不能仅凭元数据复用内容版本。已改为 HTML 请求复核实际 SHA256，并在版本资源和生成样式读取时核验文件内容。最终全量 809 项和资源专项 17 项均通过，最终性能测量重新运行三轮。

浏览器 E2E、组件与限速测量使用本机受信任 CDP，各自关闭创建的上下文；视觉对比使用独立 Chromium。测试进程环境没有 `OMRS_SYSTEMD_SERVICE`，新测量工具还显式清除此变量。

### 未执行

- 生产部署、生产重启、真实公网线路测量：本次未获得生产变更授权；当前验证结果来自隔离实例与模拟网络。
- 全套业务 E2E、Windows 实机：本次使用与传输改动相关的路径及全量 Python / Node 回归，未执行完整业务浏览器总门禁和 Windows 实机。

## 下一步

实现、验证和文档收尾已完成，按一个完整优化切片提交。上线须另行取得用户生产授权，按现有发布流程切换 release 后复核实际公网首屏与缓存刷新。
