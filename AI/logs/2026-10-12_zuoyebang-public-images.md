# 2026-10-12 作业帮附图支持任意公网域名

## 背景

用户先询问截图中的「附图地址不属于允许的作业帮图片服务」，随后要求：「能不能允许任何发来的域名」。只读核对保存的失败记录后，定位到位置二的候选三、四均使用 `img.cdnjtzy.com`，当前发布的固定域名名单未包含该域。位置一的两份文字候选已有成功渲染记录。

执行者：Codex，完整模式。基线：`3cf3f80cd14ab96fa19eaf1d5b60a7d1d4aa5dda`；开工时工作区干净，工作分支为 `codex/zuoyebang-public-images`。这是既有功能交付后的独立修复，不改已完成计划的执行说明。

## 行为变化

- 删除附图域名白名单。搜题返回的题干、答案附图，以及图片下载的跨域跳转，均接受任意域名的标准端口 HTTP/HTTPS 地址。
- 保留每次请求、每次跳转的全部 DNS 结果检查和实际连接 IP 固定，TLS 按原域名验证；拒绝非公网地址及组播地址，不转发账号 Cookie 或 Authorization。
- 无主机、非法端口、异常 IPv6 地址和带用户名／密码的 URL 统一返回 `image_address` 中文错误。原有图片字节、像素、总量预算和图片解码检查保留，失败仍保留原候选。
- 组播地址显式拒绝：`ipaddress.is_global` 本身不足以排除全部组播地址，取消域名名单后将公网限制明确为公网单播目标。

## 影响文件

按 `git diff --name-status` 复核本任务范围：

- `omrs/zuoyebang/html.py`：地址策略、格式错误及公网单播检查。
- `tests/test_zuoyebang.py`、`tests/test_zuoyebang_render.py`：替换旧域名名单断言，覆盖题干／答案不同域名、正文与附图去重、原字节保留、公开跨域跳转、连接 IP 固定、无凭据请求、非公网／组播／混合 DNS 及私网跳转拒绝。
- `tests/e2e/zuoyebang.py`：合成搜题返回两种不同域名的题干／答案图片，仅替代附图下载，地址校验、本地化、后端 Chromium 与真实页面继续执行。
- `AI/zuoyebang.md`、`AI/security.md`：同步当前附图地址和网络安全边界。
- `AI/frontend/create.md`、`AI/frontend/architecture.md`、根 `README.md`：同步用户可见行为和浏览器验证范围。
- 本日志及自动生成的 `AI/logs/log.md`：记录实际结果并同步索引。

## 已实际执行的验证

使用现有 Python 依赖 `/root/workspace/apps/releases/omrs-zyb-deps-20261011/.venv/bin/python`，Pillow 12.3.0、Playwright 1.62.0、Segno 1.6.6。所有隔离实例使用临时 Vault 和随机高端口，清除 `OMRS_SYSTEMD_SERVICE` 与 `OMRS_BOXDETECT_CONTROL`，未连接生产 Vault 或生产端口。

以下 Python 命令以该解释器运行，设置 `PYTHONDONTWRITEBYTECODE=1`，浏览器临时目录为 `/root/workspace/apps/omrs-verification/2026-10-12-public-images`：

```bash
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL \
  /root/workspace/apps/releases/omrs-zyb-deps-20261011/.venv/bin/python \
  -m unittest tests.test_zuoyebang tests.test_zuoyebang_render tests.test_zuoyebang_service_jobs -q
node --test tests/app/create-zyb.test.mjs
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL \
  OMRS_ZYB_SHOTS=/root/workspace/apps/omrs-verification/2026-10-12-public-images/e2e \
  /root/workspace/apps/releases/omrs-zyb-deps-20261011/.venv/bin/python tests/e2e/zuoyebang.py
```

结果：Python 40/40、Node 10/10、真实浏览器 E2E 50/50，无跳过。E2E 覆盖两种图片域名、完整题图／答案长图、部分识别失败重试、在途刷新与人工内容保护、幂等创建、账号菜单焦点、摄像头释放及浅深主题的四档屏宽。

另直接使用之前失败的两份候选的公开 CDN 附图 URL，未重新搜题、未读取设备凭据、未写入真实题库。通过真实下载、原字节验证和后端 Chromium 生成结果如下：

| 来源 | 附图数量 | 题目 PNG | 答案 PNG |
|---|---|---|---|
| 位置二 · 候选三 | 2 | 1080 × 621，1 张附图 | 1080 × 236，1 张附图 |
| 位置二 · 候选四 | 3 | 1080 × 588，1 张附图 | 1080 × 1849，2 张附图 |

引擎均为 MathJax 3.2.2。候选三题图及答案图已实际查看，英文题面和完整答案清晰可见；生成图在验证目录的 `real-candidate-3/`、`real-candidate-4/`，不进入仓库。

```bash
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL \
  /root/workspace/apps/releases/omrs-zyb-deps-20261011/.venv/bin/python tests/visual/run.py \
  --ref 3cf3f80cd14ab96fa19eaf1d5b60a7d1d4aa5dda --pages create --create-stage zuoyebang \
  --out /root/workspace/apps/omrs-verification/2026-10-12-public-images/visual
```

视觉前后对比：4/4 完成，浅深主题各桌面／手机，差异 0/4，页面脚本错误为零。该对比验证初始工作区布局；原报错候选的预览可用性由真实附图渲染和 50 项页面 E2E 验证。

`python3 tests/check_docs.py --write-log-index` 已生成日志索引；`python3 tests/check_docs.py --diff HEAD` 检查 112 份文档，0 问题，2 条既有大计划文件提醒，退出码 0。`git diff --check` 通过；提交前已复核 `git diff --name-status` 及新增日志，实际改动均属本任务。

## 未执行与下一步

未重新调用官方搜题或付费模型，未测试实体手机摄像头；本次使用成功搜题保存的公开附图地址及隔离网络替身。未跑无关模块全量门禁，未改前端资产或页面结构。

未部署、重启生产服务或推送远端。根 `AGENTS.md` 要求生产重启、systemd、Nginx、推送等外部变更由用户单独授权；当前授权仅用于完成本次代码修复和验证。下一步在收到部署授权后发布已验证提交，再从原搜题候选主动重新渲染。
