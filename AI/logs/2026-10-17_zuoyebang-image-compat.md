# 2026-10-17 作业帮PNG搜题兼容修复

## 背景

用户在滚动修复发布后反馈「wtf\」并附搜题失败截图。承接此前生产发布授权进行故障修复，执行者Codex，完整模式；基线3c6d1d5。原有 `AI/plans/omrs-maintenance/validation.json` 修改保持，不纳入本任务。

## 实测与原因

生产OMRS与网关均active/running、无自动重启，原图上传成功。三次搜题失败均为官方返回4000；网关历史为502/upstream，OMRS再降为gateway_upstream和「作业帮服务请求失败」。同尺寸JPEG此前成功，而这三次为同一张2180×3083、3186541字节PNG。

对已失败原图只生成质量95、同尺寸JPEG请求副本（1451982字节），经既有鉴权网关单次请求真实官方，返回200/ok及8组mainPageInfo。未打印凭据、原图或题干；没有改题库、账号或设备配置。该实测只证明这张PNG的JPEG副本成功，不推断官方对所有PNG或大小的普遍限制。

此前合成上游接受所有图片，原测试只证明原字节传输与本地流程，未覆盖官方拒绝PNG的路径。新的合成上游对非JPEG返回4000，验证兼容副本确实被发送，并且只请求一次。

## 行为变化与影响文件

- `services/zuoyebang/zyb_gateway/search.py`：完整验证并留存原图后，PNG/WebP转同尺寸JPEG请求副本，质量95，透明处白底，不转置／缩放；JPEG原样发送。副本超过8MiB先报错，不消耗官方请求预算；picMD5和签名由既有DirectClient按实际发送字节计算。
- `services/zuoyebang/tests/test_search.py`：真实HTTP校验JPEG multipart、摘要、尺寸、原图历史保留、透明PNG／WebP／调色板和副本预算。
- `tests/e2e/zuoyebang_gateway_integration.py`：双服务浏览器链路增加拒绝非JPEG的官方边界，检查副本摘要、原始坐标题框与原图历史。
- `AI/zuoyebang-service.md`、`AI/zuoyebang.md`、`AI/frontend/architecture.md`、两处README及网关API文档：同步请求副本与原件保留的区别；用户上传协议与存储格式不变。

## 验证进度

已实际执行网关全量单测：64项通过，退出0；命令为在services/zuoyebang目录执行 `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL /root/workspace/apps/releases/omrs-17f4ff0/.venv/bin/python -m unittest discover -s tests -t . -q`，日志 `/tmp/omrs-zyb-image-gateway-tests.log`。首轮定向6项因新增测试使用了错误筛选参数type而失败，改用现有action并重跑全量通过。

双服务前缀浏览器联调23/23通过，退出0：`env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL /root/workspace/apps/releases/omrs-17f4ff0/.venv/bin/python tests/e2e/zuoyebang_gateway_integration.py --out /tmp/omrs-zyb-png-dual --with-prefix`。覆盖真实上传、官方JPEG副本及签名摘要、原坐标题框、1080完整答案、人工创建、刷新回执、网关历史原字节与反代前缀，无脚本错误。

`python3 tests/check_docs.py --write-log-index`已生成索引，`python3 tests/check_docs.py --diff HEAD`通过：146份、0问题、3条既有体积提醒；git diff --check通过。生产修复发布仍在进行，结果随后追加。不把前一轮滚动修复的86项结果计为本次重跑。

未执行全量OMRS后端、Node及视觉对照：本次仅改网关Python及相关测试，未改前端代码。实体设备和付费模型也不在本次验证范围；真实官方仅针对已失败图片做故障复核。

## 生产发布与故障复核

本地提交b7225bb，精确归档 `/root/workspace/apps/releases/omrs-b7225bb`，1530个文件逐字节一致。2026-10-17 21:42:36（北京时间）完成原子切换，耗时3.334秒；三服务active/running并确认实际cwd。切换前实际任务与恢复意图均0；停服保全 `/root/workspace/apps/releases/OMRS-v281-release-0doj620t`，解包校验1159个文件及8个SQLite库。unit、依赖、账号及设备配置不变，版本保持v2.8.1，未推送远端。

发布后将先前失败的原始PNG（未在客户端转码）单次提交真实生产网关，返回200/ok、8组mainPageInfo，历史242保留PNG原字节，与失败原件逐字节相等。这是本次故障定向复核，不代表全量生产验收；未执行浏览器或公网生产验收，亦未创建或修改真实题目。用户刷新页面后重新开始搜题即可。
