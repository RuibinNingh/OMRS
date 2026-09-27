# 2026-09-24 七项安全问题修复

## 变更摘要

- 题图缺失提示改用 DOM 文字节点；科目、分类及题目来源/目标路径在写入、移动、删除前做组件和真实路径校验。
- 本机直连免 PIN；远端页面、资源及 API 统一经 PIN 会话保护。PIN 加盐哈希、失败限速、30 分钟默认空闲超时、12 小时绝对时限和真实用户操作续期已接入设置页、桌面及手机上传页。
- 所有 POST 在分派前检查 `Origin` 与 Fetch Metadata；有写入效果的扫描入口改为 POST。配置 GET 不回显 AI 密钥，提供替换和明确清除操作。
- 托管报告保留原始 HTML，浏览时加无同源权限的 CSP 沙箱；静态附件图片以当前会话的单图签名继续显示，远端图片响应禁止缓存。源码包、备份、状态中的完整 Vault 路径由统一远端认证入口保护。

## 行为与兼容性

启用 `allow_external` 先配置 PIN。旧外部访问配置若没有 PIN，远端请求先拒绝，本机可设置。Nginx 同机代理需覆写 Host、`X-Real-IP` 和 `X-Forwarded-Proto`；默认只信任回环代理，可用 `OMRS_TRUSTED_PROXIES` 指定。远端 HTTP 登录每个会话提示一次传输风险；HTTPS 不提示。`GET /api/scan` 返回 405，前端按钮使用 POST。AI 密钥输入留空保留旧值。报告中静态 `/api/image?name=` 附件引用保持可用；无效或不在附件目录的图片不签名。

## 修改文件

- 后端：`omrs/security.py`、`omrs/path_safety.py`、`omrs/server.py`、`omrs/creation.py`、`omrs/question_ops.py`、`omrs/reports.py`。
- 前端：`assets/app/domain/items.js`、`assets/questions.js`、`assets/schedule.js`、`assets/app/main.js`、`assets/inbox_mobile.html`、`omrs_dashboard.html`。
- 验证：`tests/test_security.py`。
- 文档：`README.md`、`AI/README.md`、`AI/api.md`、`AI/data.md`、`AI/frontend.md`、`AI/inbox.md`、`AI/optimization.md`、`AI/security.md`、本日志与 `AI/logs/log.md`。

## 验证

- `python3 -m unittest discover -s tests -p 'test_*.py' -q`：124 项通过。
- `node --test tests/test_*.js`：120 项通过。
- 临时题库上启动真实 HTTP Handler 并用 Chromium 走通本机设置、题图错误提示、远端 PIN 登录、HTTP 提醒、报告脚本与题图；会话内重载不重复提醒，沙箱报告读取 `/api/config` 被浏览器拒绝。
- 独立临时题库及 Git 夹具上用 Chromium 走通手机页远端登录与图片上传、桌面设置页、备份 ZIP 与脱敏源码 ZIP 下载；HTTP 提醒仅出现一次。报告图片签名链接在退出登录后返回 401，远端响应不缓存。
- `python3 tests/check_docs.py`：15 个文档，0 处问题。

## 边界

HTTP 局域网传输仍不加密，部署时建议通过 Nginx 提供 HTTPS。报告静态题图使用会话内签名；脚本运行时动态构造的图片 URL 不自动签名。
