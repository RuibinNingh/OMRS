# 2026-10-17 设置页选择并导出日志

## 背景

用户原话：「加一个功能,设置里面能导出日志」「点击后弹出一个列表,通过筛选或者自由选择导出日志」。范围确认选择「运行日志和 AI 请求日志（推荐）」。执行者为Codex，完整模式；本任务不属于现有执行计划，不改生产服务。

开工基线为`d1a7169bdf2f9c6e22cf2e33dec1a5680e6c0412`。工作区已有作业帮弹窗、组件及相关文档／测试的未提交改动，已在仓库外保存文件快照和差异，本次按路径和增量保留。开发与验证不连接生产端口或真实错题数据。

执行期间原有作业帮工作由独立提交`c312872`完成，本任务没有合入或改写该工作；17份原有非共享改动文件与开工快照逐一哈希一致。共享README／架构／组件／设计系统文档仅增加本任务内容。原有维护验证JSON及其它会话的环境文档改动不属于本任务，不纳入提交。

## 行为变化

- 设置→服务与运行新增「导出日志」，共享对话框列出运行日志和AI请求日志。支持按文件名、类型及北京时间更新日期筛选，日期区间含首尾日。
- 支持逐项勾选、全选／取消筛选结果、重置筛选、清空选择。筛选保留勾选并显示筛选外选择数；未勾选时不能导出。下载ZIP只包含全部勾选文件，按类型分目录，保留原始字节和文件更新时间。
- 读取或导出失败原地提示并支持重试。刷新保留有效勾选，移除消失文件；关闭和离页使旧回调失效，离页取消下载。打包期间禁重复提交与关闭。
- 服务端仅扫描固定`logs/`及`错题/.omrs/logs/`的直接子文件，支持log／jsonl及数字轮换、gzip后缀；拒绝链接和路径穿越，不导出维护文档。每次至多1000份、原始总量256MiB；不另行脱敏。
- 只读导出豁免业务写锁，受生命周期租约保护；临时ZIP成功或失败均清理，HTTP清单与下载禁止缓存。追加中的文件只读打开时长度，删除、不可读或读取时缩短整次409。
- 共享dialog确认入口遵守业务设置的disabled状态，键盘回车不能绕过空选择或超限按钮。

## 影响文件

- 后端：新增`omrs/log_export.py`；`omrs/http/core.py`和`omrs/http/registry.py`登记清单／下载；`omrs/locking.py`登记只读豁免；`omrs/server.py`给日志JSON加no-store。
- 前端：设置页`index.js`和`service-view.js`接入口，新增`logs.js`、`logs-view.js`和`logs.css`；样式总入口导入；`assets/app/ui/dialog.js`补确认禁用检查。
- 验证：新增`tests/test_log_export.py`、`tests/app/settings-logs.test.mjs`、`tests/e2e/settings_logs.py`，使用合成日志、临时Vault和随机端口。
- 文档：同步API索引／查询／下载契约、安全边界、设置、组件、架构、设计系统和根README；路由总表与日志索引由脚本生成。

## 已实际执行的验证

- `python3 -m unittest tests.test_log_export tests.test_http_boundaries tests.test_security -q`：43项通过，包含10项新增日志／HTTP用例。
- `python3 -m unittest tests.test_source_export tests.test_write_lock tests.test_web_assets tests.test_asset_cache -q`：29项通过；写锁用例预期触发的503不代表门禁失败。
- `node --test tests/app/*.test.mjs`：542项通过，无跳过；含3项新增日志筛选／转义用例。
- `OMRS_TEST_CDP_URL=http://127.0.0.1:9222 python3 tests/app/run_browser.py`：35项通过，0失败。
- `OMRS_TEST_CDP_URL=http://127.0.0.1:9222 python3 tests/e2e/settings_logs.py`：29/29通过。真实HTTP与ZIP涵盖筛选、部分／全选、失败重试、文件删除、初次与刷新失败、空列表、关闭后迟到响应、离页取消和六档主题／视口；页面无脚本异常。
- `OMRS_TEST_CDP_URL=http://127.0.0.1:9222 python3 tests/e2e/settings.py`：75/75通过，包含原设置主路径及七分区四档审计。
- `python3 tests/check_ui.py`：全仓0处问题。
- `python3 tests/check_contrast.py`：58组对比度全部通过。
- `OMRS_TEST_CDP_URL=http://127.0.0.1:9222 python3 tests/visual/run.py --ref d1a7169bdf2f9c6e22cf2e33dec1a5680e6c0412 --pages settings --settings-section service --out /tmp/omrs-log-export-esyeo6fo/visual`：前后各4张截图完成，脚本异常、横溢、行内样式及小点击目标均为0。
- `python3 tests/check_docs.py --write-routes`与`--write-log-index`：已生成路由表和日志索引。`python3 tests/check_docs.py --diff HEAD`检查146份文档，0处问题；3条40KB提醒来自既有计划和根README，不在本任务拆分。
- `git diff --name-status`与`git diff --check`：已复核范围，无空白错误；新增文件结合`git status --short`逐项核对。

## 视觉复核

真实Chromium截图复核发现窄屏时间行使用100%宽度再加左边距会产生列表内横向滚动，已改为扣除缩进后的宽度，并将列表内部横溢加入E2E断言。原生日期与复选控件通过color-scheme跟随主题，避免深色日期图标对比不足。新增窗口在浅／深主题及320、390、1440px验收。

填入真实日期后另复核320px截图，双列日期控件会裁掉年份首位，改为窄屏日期单列；专项截图统一保留有效日期值，复核完整日期及固定页脚。该变化只作用于新窗口，不改变设置主页面的四张前后对比。

| 对比页面 | 像素差异 | 差异解释 |
|---|---|---|
| 浅色桌面 | 1.000% | 页首增加日志导出说明，新增日志卡片和按钮，源码协助区下移 |
| 深色桌面 | 0.987% | 同上，使用既有深色token |
| 浅色手机 | 4.018% | 同一新增卡片在窄屏多行呈现，源码区向下移动 |
| 深色手机 | 3.955% | 同上，使用既有深色token |

对比报告为`/tmp/omrs-log-export-esyeo6fo/visual/report.html`，窗口截图位于`/tmp/omrs-log-export-esyeo6fo/dialog-shots/`。前后截图的Vault路径由临时实例自然不同，运行时路径不作为业务差异。

## 未执行的验证与边界

- 未做生产重启、部署或推送；本次仅修改开发工作区。
- 未用Windows浏览器或实体手机验证；窄屏验收使用真实Chromium的视口模拟。
- 未跑全仓Python发现和全部页面E2E；本次按风险运行72项相关Python回归、全量前端Node／组件检查及设置专项浏览器验证。
- 本次不改变现有日志内容／记录开关，也不导出systemd journal、MCP运行数据库或`AI/logs/`维护文档。

## 遗留与下一步

本次功能和相关门禁已完成，无已知功能遗留。保持当前版本号，不修改生产服务；生产部署由用户另行授权。
