# 2026-10-18 AI 框选独立管理面板与同端口接入

## 背景

用户要求在设置新增AI框选服务、支持用户共享服务器、面板管理Key和像作业帮的请求历史，并确认独立管理面板、训练实验另设入口；执行时特别要求“记得不要再分端口了”。执行者Codex · 完整模式，基线baae15f0e6bfb90139aedb0b19e8d2e208102a20，计划见 `AI/plans/boxdetect-panel/plan.md`。保留原有 `AI/plans/omrs-maintenance/validation.json` 改动，不纳入本任务提交。

## 行为变化

设置新增第八分区AI框选服务，独立保存本机／外部地址和调用Key，连接测试、同源管理入口及精确登记的固定进程启停；训练策略不再覆盖提供方和地址。独立服务面板含概览、整图测试、Key、历史、模型和设置；面板与API沿用原检测监听，OMRS `/boxdetect/`使用主站原端口，无新增部署端口。

收件箱、聊天草稿和兼容测试统一新版Key整图协议，由服务切片／合框，一次原图一条持久历史。历史保留原图、当时模型、结果与安全失败；幂等、限流、暂停、吊销、重启中断及容量清理均有明确状态。管理员会话与调用Key隔离，明文只显示一次，原图仅管理员读取。模型由登记目录预检／应用／回退，失败保持原模型；旧控制器与新版连接互斥，防止双重发布。

`/train`保留实验、曲线、评估和人工复核，链接独立面板。旧未迁移地址只读兼容，匿名回环协议须独立服务显式legacy-loopback。服务主站同源代理只使用本仓库资产，不执行外部服务HTML/JS，JSON和图片响应类型受限，Cookie绑定连接身份，不转发主站凭据。

## 影响文件

按git diff --name-status及未跟踪文件复核：独立服务新增配置／存储／认证／运行时／切片／三项面板资产，更新HTTP服务器与安装包；OMRS新增boxdetect客户端目录、HTTP适配，修改路由／正文预算／锁豁免／三个检测入口及旧控制互斥；设置、录入训练表单和训练面板入口同步调整。新增服务与主程序集成／浏览器测试，更新受影响的旧用例和安装包／对照脚本。

模块文档同步AI/boxdetect.md、frontend/box-panel.md、settings/create/trainpanel/architecture、api及extensions、security、data及storage、inbox、drafts、training、environment、索引与根README。无版本号变更，保持v2.8.3。计划进度与此日志同提交。

## 验证

全部测试使用临时Vault／私有状态及随机高端口，去掉OMRS_SYSTEMD_SERVICE和OMRS_BOXDETECT_CONTROL；浏览器通过本机CDP，只关闭自己的context，不操作生产。

- 最终主程序完整unittest：1083项通过（170.902秒），包括新增集成、配置切换、锁隔离和迁移互斥。初轮1079项通过，最终相关专项83项亦独立通过。
- 独立服务单测：21项通过；覆盖权限、长图整图历史、去重、限流、推理中吊销、暂停、模型失败回退、容量和重启中断。
- 最终相关主程序集成与收件箱／草稿／训练／控制：83项通过。
- 全部Node：550项通过；组件真实浏览器35项通过。
- 新面板真实浏览器111项通过；设置79项、录入122项、训练面板28项、本机控制21项通过。查看了桌面浅色、手机深色与设置页截图，无页面横向溢出及脚本错误。
- 独立wheel离线安装11项通过：只复制模型到临时目录，新环境仅安装3项推理依赖，删除源码副本后完成ONNX推理／probe／旧协议／Key整图3条带／一条历史／3项面板资产；无omrs/tools/torch/ultralytics依赖。结果 `/tmp/omrs-boxdetect-package.json`。
- 视觉比较基线baae15f0：settings/create训练区/trainpanel，浅深色桌面／手机共12组，无脚本错误；10组有预期差异。报告 `/tmp/omrs-boxdetect-visual/report.html`。训练面板4组约17.1%–17.9%为移除在线控制／测试并增加独立入口；录入训练手机2组约8.5%为表单移除提供方／地址、增加入口；设置4组≤0.315%为新增导航项；录入训练桌面2组无像素差异（变更位置在截取视口之外），专项E2E另审计实际表单。

实际遇到并修复：非法图片错误分类、HTTP时间模块导入、刷新历史的异步等待、SVG隐藏方式、旧health多余字段及旧检测顺序保持。测试环境分别使用系统Python、浏览器环境和独立构建环境；一次错误PYTHONPATH导致服务tests遮蔽主仓tests，一次构建解释器缺pip，已用正确隔离环境重跑；失败不计为通过。最后一次系统Python全量回归缺少segno；改为临时目录只链接既有segno依赖后重跑，未向系统或仓库安装依赖。另一次stdin启动完整回归不适用于multiprocessing spawn，已停止该测试进程并恢复标准unittest入口；共享CDP并行连接曾自动关闭原生确认框，专项单独重跑通过。

最终UI门禁全仓五类违规计数均为0；对比度58组、0失败；git diff --check通过。文档路由和日志索引分别运行生成（脚本的两个写选项需分次调用），`python3 tests/check_docs.py --diff HEAD`为150文档、0问题；其余3条提醒为既有大文件。

主要实际命令：

```bash
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL PYTHONPATH=services/boxdetect /root/omrs-train/.venv/bin/python -m unittest discover -s services/boxdetect/tests -p 'test_*.py' -q
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 -m unittest tests.test_boxdetect_panel tests.test_traincontrol tests.test_draft_detect tests.test_inbox tests.test_trainpanel -q
node --test tests/app/*.test.mjs
python3 tests/check_ui.py
python3 tests/check_contrast.py
python3 tests/check_docs.py --write-routes
python3 tests/check_docs.py --write-log-index
python3 tests/check_docs.py --diff HEAD
```

浏览器通过OMRS_TEST_CDP_URL=http://127.0.0.1:9222分别执行tests/app/run_browser.py及tests/e2e/settings.py、create.py、trainpanel.py、traincontrol.py、boxdetect_panel.py。安装包使用临时构建环境执行services/boxdetect/tests/package_smoke.py，传入只读模型目录及离线wheelhouse；完整回归实际命令为 `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL OMRS_TEST_CDP_URL=http://127.0.0.1:9222 PYTHONPATH=/tmp/omrs-boxdetect-testdeps-due22xz2:. python3 -m unittest discover -s tests -p 'test_*.py' -q`；临时目录只链接既有segno包，1083项全部通过。

## 未执行与边界

未修改生产unit／Nginx／监听／模型指针／真实Vault，不做生产重启、发布或推送。未使用真实用户Key／图片、未测实际公网HTTPS部署和实体手机；浏览器手机尺寸验证不能替代硬件验证。真实模型安装包使用合成图片，仅证明可运行及协议，不证明内容准确率。初始管理员密码由私有文件保管，当前面板没有改密入口。

## 下一步

源码及隔离验收已完成，按计划以一个本地完整提交交付；上线时由维护者在获得部署授权后按服务README保全原状态、保持原端口、登记私有状态目录和Key、收束旧控制操作并切换连接。源码交付不代表生产已切换。
