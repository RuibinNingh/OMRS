# 2026-10-18 Windows 题图读取修复与生产发布

## 背景与授权

用户原话：「那只修复读取」「启动补丁不加了」「提交GitHub部署生产」。执行者Codex，完整模式；基线1d6c215f49343b5b88fd52e47c9f0a0a8f1c62fa。仅合入附件question-images-windows.patch中的读取修复、两项测试及对应接口／安全文档，保持v2.8.2和当前依赖。

开工已有AI/plans/omrs-maintenance/validation.json未提交修改，SHA256为3d3cdbd203731931981a4db6d940cae48878e1069d55c1c2008c361aa58be9f9；原件和补丁保全在仓库外，本任务不修改或提交该文件。run.bat、Conda、run_port.py与Windows启动补丁不纳入本次范围。

## 行为变化与影响文件

omrs/question_images.py的无目录FD分支使用独立os.lstat获取候选文件身份，避免Windows目录扫描返回零st_dev／st_ino时误报读取期间文件变化。安全路径、同名歧义、链接／重解析点拒绝、打开后文件身份与读取期间属性检查、MCP大小和解码限制均保留，HTTP及图片原字节不变。

tests/test_question_images.py新增零文件身份下Web／MCP读取原件与打开前普通文件被替换时拒绝读取的回归。AI/api/queries.md、AI/security.md及README.md同步当前行为；本日志与自动生成的AI/logs/log.md记录任务。生产环境事实在部署后同步AI/environment.md。

已通过git apply --check并用git apply --3way干净合入四个补丁路径；git diff --cached --stat已复核，未采用启动器补丁。发布源码固定为Git精确归档，排除无关工作区修改。

## 已实际执行的验证

前一轮只读调查在临时副本模拟Windows零文件身份：旧代码复现「题目引用的图片在读取期间发生变化」，应用补丁后题图模块19项全部通过，0跳过。本轮使用现有依赖，所有测试均清除OMRS_SYSTEMD_SERVICE、OMRS_BOXDETECT_CONTROL和共享CDP变量，使用合成临时Vault与随机高端口。

- PYTHONPATH="$PWD/tests" /root/workspace/apps/releases/omrs-zyb-deps-20261011/.venv/bin/python -B -m unittest tests.test_question_images tests.test_security tests.test_http_boundaries tests.test_mcp tests.test_mcp_exports tests.test_export_fonts -q：75项通过，0失败／跳过，其中题图模块19项。
- python3 -B -m pytest tests/test_report_export.py -q -p no:cacheprovider：7项通过。
- 仓库外verify_http_browser.py：8项通过。真实HTTP旧实现模拟返回404，修复后200且PNG原字节一致；1440／390px真实Chromium分别核对题库弹窗和即时练习图片naturalWidth=96、无缺图占位、无页面脚本错误。临时服务与浏览器已关闭，合成Vault已删除。
- python3 tests/check_docs.py --write-log-index已生成索引；python3 tests/check_docs.py --diff HEAD：146份文档、0问题、3条既有体积提醒；git diff --check通过。

首轮模块调用因tests/test_mcp_exports.py使用顶层test_mcp导入而失败，补上测试目录PYTHONPATH后75项通过；生产依赖环境未安装pytest，改用已有系统pytest运行7项通过，未安装或升级依赖。临时浏览器模拟器初次缺少scandir迭代协议、定位器匹配到两个按钮，修正验收脚本后8项通过，未修改业务断言。MCP导入保留Pydantic forward reference提醒，未屏蔽。附件自报的Windows验收结果不计为本机实测。

## 未执行与限制

本机为Linux，无原生Windows运行环境；Windows行为通过强制路径分支及零文件身份模拟验证。本次不修复附件中另列的Windows备份、临时文件和测试路径问题，不改启动入口或Python环境。未执行真实供应商搜题、付费模型、训练、实体手机与生产测试写入。

## 发布与数据保全

用户已授权推送GitHub和部署生产。发布沿用现有精确归档、任务与写入意图预检、持训练锁停服保全和原子切换源码别名流程；异常只回退源码，保留最新数据。实际提交、备份、切换及上线验证结果完成后补充。

本轮证据目录为/root/workspace/apps/releases/OMRS-windows-image-release-hvt9yawk，仅保存本机验证与受限权限发布材料，不提交私有备份或凭据。
