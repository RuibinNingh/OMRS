# 2026-10-11 作业帮独立服务中断后验收与续作

## 背景

用户要求“验收检查代码,然后继续任务”。执行者Codex，完整模式；继承主仓库与隔离候选基线e614f3a6f625f8385714aac4171870459a537c15。实现保留在OMRS-zyb-service-dev与独立zuoyebang-service，主仓库干净。开工记录既有15条已跟踪修改及15个未跟踪文件；未覆盖或还原继承代码。旧导出对话只到分派阶段，实际子代理源码及证据保留；本轮按真实代码独立验收。

本次仅交付隔离源码，不提交／合入／推送／部署，不操作systemd、Nginx、真实题库或真实凭据。原业务要求为独立作业帮服务、设置页本地／外部选择、地址与Key、管理面板生成Key及请求来源／IP历史。

## 行为变化

继承实现完成独立网关及设置／搜题适配；本轮修复扫码取消与迟到账号结果的竞争、过载时审计异常泄露／无响应、上游socket断开误归类、二维码终态按钮、空／重复转发头来源校验。OMRS修复TCP／TLS分段重复预算与定时器强制EOF误当成功、恢复后渲染失败写回、客户端与网关24MiB响应预算一致性，以及服务切换后账号观察与就绪状态错误归属。

真实两项目联调使用实际网关管理面板生成／吊销Key，OMRS保存连接、原图上传、网关实际签名解码、候选、1080宽完整答案渲染、人工核对入库、刷新幂等回执及来源IP审计。只替换官方网络为合成HTTP边界，不以合成网关替代最终联调。

## 影响文件

继承范围：settings/create服务设置与菜单、domain服务契约、HTTP注册及适配、私有配置与安全客户端、后台任务、新旧Python／Node／E2E夹具。新增tests/e2e/zuoyebang_gateway_integration.py作为可重复双项目验收。独立网关源码／测试／文档位于相邻独立目录，不属于OMRS Git变化。

同步AI/zuoyebang.md、AI/zuoyebang-service.md、AI/api.md及extensions、AI/data.md及storage、AI/security.md、前端settings/create/architecture、AI/README.md及根README；更新计划真实用户原话／执行者／收尾流程及progress。路由与任务日志索引按脚本生成。交付前按git diff --name-status及未跟踪清单复核实际范围。

## 验证

执行记录与命令在本轮证据目录 `/root/.hermes/cache/scratch/zyb-service-20261011/codex-acceptance/`。所有实例使用临时Vault、随机高端口、合成会话／官方／模型边界；移除OMRS_SYSTEMD_SERVICE与OMRS_BOXDETECT_CONTROL。

最终全量Python958项通过（399.049秒，退出0，无失败／错误／跳过）；相关后端58项、Node490项、组件浏览器34项、设置75项、原录入124项、服务26项、作业帮完整流程49项、实际两项目15项均通过，0跳过。UI全仓0问题、58组对比度全过。第一轮全量956项后补客户端截止EOF两项回归，最终结果以上述958项为准。文档111份0问题、2条既有大文件提醒；独立服务52单测、1真实浏览器、4安装包HTTP断言全绿。

旧渲染错误与摄像头超时分别来自私有TMPDIR访问权限、共享CDP未带模拟摄像头参数。本轮使用root拥有且祖先可访问的候选临时目录；作业帮流程启独立Chromium，保留真实MediaStream和原渲染断言，不改产品render.py／测试browser_runtime.py或放宽沙箱。新增失败见证覆盖真实并发／网络／状态缺陷；未把环境故障当业务成功。

## 视觉差异

执行tests/visual/run.py --ref HEAD --pages settings,create，浅／深色×桌面／手机共8组前后截图，均无脚本错误、横溢、小目标或行内样式。设置新增导航分区：浅色桌面0.242%、深色桌面0.260%、浅／深色手机各0.012%；变化为新增服务标签及其导航占位，字号和控件高度保持。录入默认工作区四组0%差异；作业帮菜单和新配置分区在专项截图另验收。

## 未执行与遗留

未执行真实官方账号／扫码／签名有效期、付费模型、公网真实域名反代或生产部署；合成官方边界不能证明真实账号在线、官方验签或RC4/gzip解码分支。既有独立服务docs/tmp私有目录不读取、不删除，交付包按源码白名单排除。继承版本v2.4.1，主仓库未合入；源码通过全部收尾门禁，交给维护者复核合入，生产动作仍须单独授权。

## 源码交付与下一步

最终收尾日期为2026-10-12，沿用本次任务日志。交付目录 `/root/.codex/artifacts/omrs-zuoyebang-20261011/` 包含完整双项目源码zip和OMRS补丁。补丁基线为e614f3a6f625f8385714aac4171870459a537c15；在该提交的干净git archive上通过git apply --check并实际应用，全部OMRS文件与候选逐字节一致。zip共1467条文件（OMRS1378、网关89），逐条SHA256与CRC检查通过；没有.git、.venv、真实题库、私有库、admin-secret或临时私有目录。只读复核补齐网关验证文档引用的两份脱敏JSON证据，按精确路径入包。校验记录在本轮证据目录package-check.json与patch-check.log。

交付前复核git diff --name-status、未跟踪清单与git diff --check，生成日志索引，最终文档门禁通过。全部本轮测试实例与独立浏览器进程已清理，共享Chrome保留。主仓库仍干净，实现保留在原隔离目录，未提交／合入／推送／部署。下一步由完整模式维护者按计划复核源码、应用补丁并复验；部署与真实账号验证在获单独授权后执行。

## 验证入口与复验命令

OMRS在隔离候选运行，网关在独立目录运行；以下每组均移除生产控制环境，证据日志写本轮目录。浏览器专项使用root拥有的候选临时目录，完整作业帮流程未启共享CDP。

```bash
 env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL \
  TMPDIR="$PWD/.venv/codex-tmp" PLAYWRIGHT_BROWSERS_PATH="$PWD/.venv/browsers" \
  OMRS_TEST_CDP_URL=http://127.0.0.1:9222 .venv/bin/python -m unittest discover -s tests
node --test tests/app/*.test.mjs
python3 tests/check_ui.py
python3 tests/check_contrast.py
 env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL \
  TMPDIR="$PWD/.venv/codex-tmp" PLAYWRIGHT_BROWSERS_PATH="$PWD/.venv/browsers" \
  OMRS_TEST_CDP_URL=http://127.0.0.1:9222 .venv/bin/python tests/app/run_browser.py
.venv/bin/python tests/e2e/settings.py
.venv/bin/python tests/e2e/create.py
.venv/bin/python tests/e2e/zuoyebang_service.py
.venv/bin/python tests/e2e/zuoyebang.py
.venv/bin/python tests/e2e/zuoyebang_gateway_integration.py --gateway-source ../zuoyebang-service --out .venv/dual-service-evidence
python3 tests/visual/run.py --ref HEAD --pages settings,create
python3 tests/check_docs.py --write-routes
python3 tests/check_docs.py --write-log-index
python3 tests/check_docs.py --diff HEAD
```

页面脚本由前端代理使用其可访问TMPDIR与Playwright浏览器路径实际运行，精确环境及stdout记录在frontend/REPORT.md；上面清单列仓库入口，不将子代理环境差异冒充相同命令。独立网关实际执行 `.venv/bin/python -m unittest discover -s tests -t . -v`、`node --check zyb_gateway/assets/panel.js` 和 `ZYB_TEST_CDP_URL=http://127.0.0.1:9222 .venv/bin/python tests/browser_acceptance.py`，源码外安装包四项HTTP断言见独立服务验证文档。
