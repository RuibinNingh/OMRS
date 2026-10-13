# 作业帮独立网关接入

> **速查**
> - 职责：OMRS网关连接配置、密钥投影、地址策略及有界状态／搜题请求
> - 入口：`omrs/zuoyebang/service_config.py`、`gateway.py`、`targets.py`、`service.py`
> - 不变量：本地与外部都通过独立网关鉴权；密钥不回显；服务切换／恢复后旧结果不发布
> - 必跑测试：`tests/test_zuoyebang_service.py`、`tests/test_zuoyebang_service_http.py`、`tests/test_zuoyebang_service_jobs.py`、`tests/e2e/zuoyebang_service.py`
> - 相关：`AI/zuoyebang.md`、`AI/security.md`、`AI/data/storage.md`、`AI/frontend/settings.md`

## 1. 职责与配置

独立网关拥有设备会话、扫码账号、签名、官方搜题／解码、调用密钥和HTTP审计。OMRS保留原图上传、候选、1080px完整渲染、AI识别、人工核对及幂等创建。正常搜题不绕过网关；设备和账号凭据不迁移。网关面板使用独立管理员会话，调用Key不能获得管理权限。

网关与OMRS源码同仓，入口 `services/zuoyebang/zyb_gateway/__main__.py`，安装和管理见 `services/zuoyebang/README.md`。两进程可共用精确Git发布目录和Python依赖，私有数据分别存储。systemd模板见 `deploy/zuoyebang.service`；网关运行目录不能作为静态资源或源码导出目录。

本地默认根地址为 `http://127.0.0.1:8745`，可改为OMRS服务器上的其它回环端口；它表示独立本机网关。外部模式连接指定网关，默认只允许公网HTTPS；显式启用allow_private_targets后可连接可信私网HTTP／HTTPS。网关应用外部访问开关与其实际监听／反代独立，OMRS连接配置不会自动修改部署。

`GET /api/zuoyebang/service`返回service投影：mode、base_url、allow_private_targets、revision、api_key_configured、api_key_fingerprint、panel_url。`POST /api/zuoyebang/service`只接受mode/base_url/api_key/allow_private_targets/clear_api_key；留空Key保留，明确clear_api_key清除，两者冲突拒绝。保存后产生新的revision。私有文件格式见 `AI/data/storage.md` §11。

`POST /api/zuoyebang/service/test`只接受空对象，通过已保存配置读取网关状态；不搜题、刷新账号或验证官方TTL。`GET /api/zuoyebang/status`执行相同脱敏状态读取。两者返回connected、service及账号摘要；网络失败不改变有效期观察。配置／测试接口继承Web认证、POST同源及MCP隔离。

## 2. 网络与资源边界

地址接受HTTP(S)根地址或安全路径前缀，如 `https://example.org/zuoyebang`；拒绝userinfo、查询、片段、非法端口、空路径段、`.`／`..`、百分号编码与路径参数。状态／搜题路径追加在此前缀后。本地只准回环；外部私网须显式允许。元数据、链路本地、未指定、组播等地址始终拒绝。DNS在有限线程槽中解析并复核全部地址，连接固定已核验IP；HTTPS用原域SNI及证书校验。请求不读取环境代理、不重定向、不自动重复搜题。

每进程最多四个在途网关请求；DNS调用者等待至多3秒（超时解析线程结束前仍占槽），状态整体10秒，搜题整体45秒。TCP与TLS共用剩余预算，慢速响应头和正文也受整体截止限制。状态最多128KiB，搜题最多24MiB，与独立网关默认解码响应预算一致；压缩响应拒绝，声明长度与实际字节不一致失败。原图片仅PNG/JPEG/WebP，8MiB和4000万像素，不重编码。

网关调用使用Bearer Key，本机同样鉴权。状态仅投影账号／签名布尔值、有限枚举、时间与最近100条白名单观察；忽略上游额外字段。错误Key、外部拒绝、限流、响应超限、协议与网络故障使用固定中文错误，不将Key或官方响应原文带到页面。

## 3. 生命周期与页面状态

状态查询和后台任务开始时捕获服务快照及Vault世代；网络／浏览器期间不持业务写锁或长期磁盘租约。发布前在短租约和写锁内复查配置，切换地址、模式或Key使旧结果失效。渲染失败写回也核对世代，整库恢复后的记录不能被旧失败覆盖。旧渲染／人工内容仍可只读查看和核对，不重放网络。

设置成功保存／清除发zuoyebang:service-changed；录入菜单通过domain模块进入设置。账号观察绑定mode/base_url/私网开关/revision/Key指纹等非敏感身份；切换后清空旧观察，同配置的暂态失败可保留最近观察。管理链接保留地址前缀并补尾斜杠，新标签页使用noopener，不带Key。

网关面板使用相对资源和管理请求，支持反代剥离前缀。Nginx模板见 `services/zuoyebang/deploy/zuoyebang.nginx.example`：覆盖XFF、不新增公网端口、把管理Cookie限制到/zuoyebang/。网关须配置公开Origin、Secure cookie及精确信任的回环代理；不能用反代头绕过管理员／调用Key鉴权。

网关请求记录可按搜题筛选，管理员通过 `GET /api/admin/history/<id>` 查看该次请求的年级、原图元数据和完整已解码回执，通过 `GET /api/admin/history/<id>/image` 读取原图片字节；这些是网关端点，不是OMRS端点。成功与安全失败回执和请求元数据在同一个SQLite事务写入。已经校验的原图即使搜题失败也保留，未发布的旧会话结果不保存为成功。详情仅在网关私有库中，默认30天／10000条及256MiB内容预算，原有无详情的记录仍可读；接口、清理和容量选项见 `services/zuoyebang/docs/api.md`、`services/zuoyebang/README.md`。

面板默认进入服务概览，分别展示设备配置、账号和签名观察，再按真实状态给出导入、登录、核对或密钥配置入口。设备导入、手动凭据、扫码与一次性密钥使用弹窗；关闭及管理会话失效清空敏感内容，迟到回执不恢复窗口。页面按需读取，资源、焦点、双主题与异步生命周期见 `AI/frontend/zyb-panel.md`。

## 4. 双项目验收

`tests/e2e/zuoyebang_service.py`使用真实HTTP合成网关验收配置及错误边界。`tests/e2e/zuoyebang_gateway_integration.py`默认读取同仓services/zuoyebang，也可通过 `--gateway-source` 指定其它源码；`--with-prefix`增加真实HTTP前缀反代边界。启动两个实际服务及合成官方边界，验证面板生成／吊销Key、OMRS本地／可信内网模式、原图传输、实际签名解码、1080完整渲染、人工创建、刷新回执、请求来源IP及前缀Cookie。网关与OMRS分别使用临时私有数据和随机高端口；真实官方账号／网络及付费模型不在该验收范围。

以下命令在OMRS源码目录运行，临时数据与截图写指定输出目录：

```bash
mkdir -p .venv/codex-tmp
 env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL \
  TMPDIR="$PWD/.venv/codex-tmp" PLAYWRIGHT_BROWSERS_PATH="$PWD/.venv/browsers" \
  .venv/bin/python tests/e2e/zuoyebang_gateway_integration.py \
  --with-prefix --out "$PWD/.venv/dual-service-evidence"
```

该命令启动独立测试Chromium；完整作业帮摄像头专项需独立浏览器的模拟媒体参数，不能用未启模拟设备的共享CDP替代。只测试常规页面时可用显式OMRS_TEST_CDP_URL，并仅关闭本次context。
