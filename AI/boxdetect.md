# AI 框选服务

> **速查**
> - 职责：独立 ONNX 框选、调用 Key、整图历史、模型管理与 OMRS 同端口连接
> - 入口：`services/boxdetect/boxdetect_service/`、`omrs/boxdetect/`、`omrs/http/boxdetect.py`
> - 不变量：面板与 API 共用已有监听；调用 Key 不授予管理权限；训练不自动发布在线模型
> - 必跑测试：`tests/test_boxdetect_panel.py`、`services/boxdetect/tests/test_panel.py`、`tests/e2e/boxdetect_panel.py`
> - 相关：`AI/frontend/box-panel.md`、`AI/frontend/settings.md`、`AI/security.md`、`AI/data/storage.md`

## 连接与入口

设置 → AI 框选服务保存本机／外部位置、服务根地址、调用 Key 与显式私网信任。提供方仍为 `vlm`／`local_http`；后者使用独立连接，名称不限制只能本机。私有配置与通用 AI 识别 Key 分开，空 Key 保留、显式清除。连接保存不自动切换提供方。

独立进程沿用原检测监听，面板 `/`、静态资源、管理接口与检测 API 都在同一监听。OMRS 的 `/boxdetect/` 将面板和 API 放到主站已有端口下，浏览器不连接内部检测端口；不需要为面板增加端口。服务也可独立安装并由现有 HTTPS 入口反代，安装见 `services/boxdetect/README.md`。

| OMRS 方法与路径 | 契约 |
|---|---|
| GET `/api/boxdetect/service` | 脱敏连接、提供方、`local_control`；不返回 Key |
| POST `/api/boxdetect/service` | `mode,base_url,api_key?,allow_private_targets,clear_api_key?`，成功更新 revision |
| GET `/api/boxdetect/status` | 已保存连接的受鉴权状态与实际在线模型 |
| POST `/api/boxdetect/service/test` | 测试已保存地址和 Key；不保存编辑中的表单 |
| POST `/api/boxdetect/control` | `{action:start/stop/restart}`，仅精确登记的本机固定 unit |
| GET `/boxdetect` | 跳转 `/boxdetect/` |
| GET、POST `/boxdetect/` 前缀 | 固定白名单反代，资产来自本仓库；管理接口沿用主站授权 |

仅 `/boxdetect/healthz`、`/boxdetect/api/v1/status`、`/boxdetect/api/v1/detect` 使用独立服务鉴权边界，允许外部客户端直接使用框选 Key；healthz 只返回存活信息，其余必须唯一 Bearer。该 Key 不能访问 OMRS 其它接口或管理页面。外部访问仍由框选服务的访问开关和网络部署决定。

地址使用与作业帮相同的严格解析、DNS 全地址校验及固定 IP 连接策略：公网 HTTPS，可信私网须显式允许，本机须回环；拒绝 URL 凭据、危险路径、重定向和环境代理。最多12个连接，检测总期限120秒、状态10秒、DNS至多3秒、响应最多22MiB。配置／Vault 世代变化后丢弃旧结果，收件箱和草稿写入前再核对。

## 独立服务接口

管理 API 位于 `/api/admin/`：POST login/logout；GET session/overview；GET/POST keys、POST keys/revoke；GET history、history/编号、history/编号/image；GET models、POST models/apply；GET/POST settings；POST try。除登录外均需独立管理员会话；管理写操作还须精确 Origin 和 CSRF，调用 Key 不能替代会话。

首次启动在私有状态目录生成 `admin-secret.txt`，数据库保存 scrypt 摘要。登录有失败次数限制，会话默认1小时；目前密码由初始私有文件保管，面板没有密码修改入口。Key 以 `box_` 开头，仅创建时显示明文，数据库只存摘要、指纹、名称和使用时间；吊销后立即失效，执行前后都检查有效性。

`GET /api/v1/status` 返回 `service:boxdetect,protocol:1,model,revision,paused,waiting,history_retention,limits`。`POST /api/v1/detect` 接收 `{image:dataURL,request_id?,source?}`；编号为32位小写十六进制，source 为 inbox/draft/test/api/legacy。响应含 `status,request_id,history_id,boxes,width,height,strips,parts,model,elapsed_ms`；框为0–1的 `role,x,y,w,h,conf`。空框也是成功。相同 Key／编号／图片复用回执，编号对应不同图片返回409，未结束返回409。

PNG/JPEG/GIF 单图≤15MiB、≤4000万像素，JSON≤22MiB；新版拒绝高宽比超过100。服务按既有高宽比>3、条带约2倍宽、重叠8%的规则切片，JPEG85推理后合并回整图。收件箱、聊天草稿及兼容测试接口上传原图，新版客户端不重复切片；服务保留每条带耗时与框数。旧 VLM 和旧协议继续用原切片路径。

推理串行，接纳队列最多8个，HTTP同时最多32个连接，连接读取超时10秒。默认每 Key 每分钟10次，可设1–100；每 socket 来源每分钟240次限制也覆盖管理请求。暂停只拒绝新推理，管理页仍可用。失败用固定中文错误，限流429、暂停503、Key无效401、请求冲突409；结果及安全错误写历史，不保存认证头或异常原文。

## 历史与模型

一次原图一条请求记录，保留来源、调用方、IP、实际模型、状态、耗时、原图和完整返回。仅管理员读取原图；默认30天／10000条／256MiB原图，容量超限清理较早图片，回执仍按记录期限保留。启动把在途请求和模型操作标中断；同编号可核对已结束结果，不自动重跑中断推理。服务库不由 OMRS 题库备份管理。

模型仅从部署者 `--models-dir` 登记目录选择，检查文件SHA、两类标签、640/960输入及实际尺寸，再做一次白图推理。模型应用／恢复与推理互斥，携带revision和安全request_id；候选失败保留原模型，成功在同一事务提交模型选择和操作回执，再更新内存。服务重启使用已提交选择，模型文件须保持完整；不加载网页任意路径、不运行命令。这里的预检证明可加载，不代表内容准确率，内容评测仍在训练入口查看。

OMRS 独立连接启用后拒绝旧模型控制提交和启动恢复，防止两个控制器修改同一模型；切换连接与旧操作共用文件锁，旧操作未完成／待恢复时返回409。设置中的本机启停只执行固定 unit，不改模型，发起者和结果写 `managed/service-operations/`。未登记或外部服务不出现本机控制。

## 兼容与验证

私有连接不存在时，只读投影旧 `inbox_local_detect_url`，不隐式写配置或创建 Key；旧调用继续原协议。独立服务 `/health`、`/detect` 默认须 Key；只有显式 `--legacy-loopback` 且来源确为回环时兼容匿名旧调用，不能通过可信代理伪造回环来源。迁移需先保全原模型和端口、完成隔离验证，再按部署授权配置密钥；不能直接以新默认参数覆盖运行中的旧 unit。

独立单测：`PYTHONPATH=services/boxdetect python3 -m unittest discover -s services/boxdetect/tests -p 'test_*.py' -q`。主程序：`python3 -m unittest tests.test_boxdetect_panel tests.test_traincontrol tests.test_draft_detect tests.test_inbox tests.test_trainpanel -q`。浏览器：`python3 tests/e2e/boxdetect_panel.py`、`python3 tests/e2e/traincontrol.py`；用临时 Vault、私有目录、随机高端口，事先去掉生产控制环境变量。真实安装包验收命令见服务 README。
