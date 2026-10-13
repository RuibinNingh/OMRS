# 2026-10-13 作业帮搜题记录原图与返回详情

## 背景

用户原话：

> 作业帮面板查看记录我觉得需要对于搜题记录更加详细记录
> 保留搜题上传的图片
> 和返回结果之类的,可以作为详情功能

执行者：Codex，完整模式。开工基线09fb0bc，Git工作区干净；本任务是已交付作业帮功能后的独立新增需求，不修改历史计划或历史日志。工作期间另一任务合入00b44d8（独立框选服务迁移）；保留其全部改动，本次只提交搜题详情相关文件与日志。版本仍为v2.6.0。

## 行为变化

- 面板“请求记录”增加全部请求／搜题记录筛选；搜题行可“查看详情”。窗口展示上传原图、返回题干与答案、完整已解码回执、年级、时间、来源、客户端／对端IP、密钥ID、结果及耗时。
- 原图保存PNG/JPEG/WebP上传原字节，包含类型、宽高、字节数和SHA256，不重编码；成功回执完整保存，图片与结果绑定同一请求，不将不同候选的题干和答案合并。
- 通过鉴权和API限流后的请求捕获安全回执；图片须完整通过现有校验才保存。设备缺失、并发／每日预算、官方／网络失败仍可保留有效原图；无效图片只保存固定错误，鉴权前拒绝不保存请求正文。会话更换后的旧结果仅保存实际409错误，不留未发布的成功内容。
- 私有SQLite新增search_details，以history_id外键关联；请求与详情原子写入，写入失败返回503且不静默成功。重启后可读，旧库自动建表，原有无详情的记录不补造内容。
- 详情JSON和原图只允许独立管理员Cookie会话，调用Key不能查看；相对地址支持实际反代前缀，响应no-store／nosniff。官方HTML只在惰性template里取文字，摘要与JSON以textContent显示，不挂载脚本或远程附图。
- 关闭详情、退出、会话过期或页面离开清空图片与结果并撤销Blob URL；窗口世代阻止迟到读取覆盖另一条记录。详情或图片读取失败可手动重试。
- 默认记录最多30天／10000条，详情内容合计256MiB；CLI可调整history-days、history-limit、history-detail-bytes。历史删除级联清理图片与结果，容量超限移除较早详情并保留元数据，单条超过容量则不留存。读取和审计写入都执行清理；预算不是SQLite物理文件大小，空闲页复用且不自动VACUUM。

## 影响文件

交付前按git diff --name-status复核，新增测试用git status确认；本次范围如下：

- services/zuoyebang/zyb_gateway/storage.py、search.py、server.py：请求绑定的原件与回执、受保护详情／图片接口及清理。
- services/zuoyebang/zyb_gateway/config.py、__main__.py：详情字节预算与CLI。
- services/zuoyebang/zyb_gateway/assets/index.html、panel.js、panel.css：筛选、详情、文字摘要、原图与异步生命周期。
- services/zuoyebang/tests/test_search_history.py、browser_acceptance.py：11项HTTP专项与2项新增真实浏览器用例，覆盖留存、权限、失败、迁移、清理及生命周期。
- tests/e2e/zuoyebang_gateway_integration.py：通过实际OMRS上传／网关签名解码和反代前缀查看完整详情、逐字节验原图与关闭清理。
- AI/frontend/zyb-panel.md、architecture.md、AI/zuoyebang-service.md、AI/api/extensions.md、AI/data/storage.md、AI/security.md、根及网关README、网关docs/api.md和security.md：同步可验证行为、接口与存储边界。
- 本日志及脚本生成的AI/logs/log.md。未修改OMRS业务端点或客户端搜题协议。

## 已实际执行的验证

完整依赖Python使用现有只读环境 `/root/workspace/apps/releases/omrs-zyb-deps-20261011/.venv/bin/python`，下文记为PYTHON；命令中的PYTHON应替换为此完整路径。独立服务单测与浏览器命令在services/zuoyebang目录执行，其余在仓库根执行。服务数据全为临时私有目录／Vault和随机端口，启动OMRS时移除生产控制环境；官方边界仅合成数据，不读真实凭据或题库。

| 命令／范围 | 实际结果 |
|---|---|
| PYTHON -m unittest discover -s tests -t .（基线） | 52项通过 |
| PYTHON -m unittest discover -s tests -t .（最终） | 63项通过，含新增11项详情HTTP专项 |
| ZYB_TEST_EVIDENCE_DIR=/root/.codex/artifacts/omrs-zyb-history-20261013/baseline PYTHON tests/browser_acceptance.py | 基线4项通过 |
| ZYB_TEST_EVIDENCE_DIR=/root/.codex/artifacts/omrs-zyb-history-20261013/after PYTHON tests/browser_acceptance.py | 最终6项通过；浅深色1280／780／390／320px详情及既有五页布局／对比度通过 |
| env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL PYTHON tests/e2e/zuoyebang_gateway_integration.py --with-prefix --out /root/.codex/artifacts/omrs-zyb-history-20261013/integration-final | 22/22项通过；真实两个服务、原图、签名解码、三条候选、渲染／创建及详情前缀 |
| python3 tests/check_ui.py | 全仓0问题 |
| python3 tests/check_contrast.py | 58组通过，0组不达标 |
| node --check services/zuoyebang/zyb_gateway/assets/panel.js | 通过 |
| python3 -m py_compile services/zuoyebang/zyb_gateway/storage.py services/zuoyebang/zyb_gateway/search.py services/zuoyebang/zyb_gateway/server.py | 通过 |
| git diff --check | 通过 |
| python3 tests/check_docs.py --write-log-index；python3 tests/check_docs.py --diff HEAD | 已实际生成索引；最终在仅包含本次改动的候选副本检查差异，117份文档、0问题、2条既有大文件提醒，退出码0 |

首次系统python3运行网关测试因未安装segno，出现1失败／2错误；切换已有完整环境后基线52项与最终63项全通过，没有联网安装或修改依赖。首次浏览器验收修正测试本身的Blob读取路径和异步toggle等待：图片显示受img-src允许，fetch(blob:)受connect-src拒绝，改从同源原图接口核验摘要，没有放宽connect-src。首次新增联调断言误用不在夹具正文中的SYNTHETIC字样，改为核验实际等腰三角形题干与答案，最终22项通过。

共享工作区另一任务在00b44d8之后继续修改训练／源码导出等文件；其未完成的tools/boxdetect/train.py与模块文档同步曾使工作区差异检查返回1，未修改或纳入这些文件。最终候选以00b44d8的Git归档加本次暂存的精确补丁构建，在独立临时Git基线中执行完整check_docs.py --diff HEAD，退出码0；候选网关全量63项、实际前缀联调22项、UI0问题与对比度58组也再次通过。这保留了原工作区与另一任务的全部改动；候选位于 `/root/.codex/artifacts/omrs-zyb-history-20261013/candidate`，联调证据位于candidate-integration目录。

### 视觉前后对比

实际执行：

```bash
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL \
  OMRS_TEST_CDP_URL=http://127.0.0.1:9222 \
  /root/workspace/apps/releases/omrs-zyb-deps-20261011/.venv/bin/python \
  tests/visual/run.py --ref HEAD --pages settings --settings-section service \
  --out /root/.codex/artifacts/omrs-zyb-history-20261013/omrs-visual
```

该命令覆盖OMRS服务设置四档；无脚本错误、页面横溢、小目标或行内样式问题。差异0.006%／0.029%，逐图像素边界与截图确认只在隔离Vault路径的ref／cur后缀，主应用服务设置结构未改。

网关页面另使用相同合成原图和回执，以09fb0bc静态面板为基线，在实际隔离HTTP服务上拍浅／深色1280与390px前后截图。比较报告为 `/root/.codex/artifacts/omrs-zyb-history-20261013/panel-visual/report.html`，evidence.json记录四组差异1.613%、5.107%、1.690%、14.666%；12组列表／详情布局及实际对比度均通过，无脚本错误。只关闭自己的浏览器context，临时数据已清理。

差异逐项说明：新增记录类型筛选导致筛选区重排，搜题行新增详情入口及保留提示，页头改为包含回看原图／内容的说明，页尾显示实际期限／容量。窄屏差异还包含筛选区高度变化与下方列表位置移动。新增详情窗口包含原图、结果、元数据和完整回执折叠区，不存在对应的旧窗口。八档详情截图在after目录，实际双服务详情截图在integration-final目录；均为合成数据。

## 未执行的验证与遗留

未访问真实官方账号、真实扫码／搜题或实体手机；官方边界使用合成HTTP或固定合成响应。未部署、重启生产、操作systemd／Nginx或推送远端，本轮未获这些外部变更的单独授权。未跑OMRS全量Python／Node及组件浏览器套件：没有修改主应用业务／assets/app，采用网关全量、实际双服务与页面专项验证。

已有未保存的图片／回执无法补回；容量清理后元数据可读但内容不可恢复，这是明确保留边界。返回附图URL和完整公式源码保留在原始回执中，详情只显示文字摘要，不额外下载候选附图。

## 下一步

本地实现、验证、文档和提交完成后，后续单独授权发布时应用该提交；升级网关会自动创建新表，从新搜题开始留存详情。发布验收需以管理员打开新请求，核对上传原图、完整返回内容及实际反代前缀；旧记录显示未留存。无尚未完成的源码工作。
