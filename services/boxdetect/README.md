# 独立 AI 框选服务

`services/boxdetect/` 可独立部署，提供题目／答案 ONNX 推理、管理员面板、调用 Key、整图历史与模型切换。面板和 API 共用原检测监听；OMRS 用已有主站端口的 `/boxdetect/` 接入，不为面板新增端口。依赖仅 onnxruntime、numpy、Pillow，不导入 OMRS、训练框架或访问题库。Python 3.11+，精确依赖见 requirements.txt。

## 安装和连接

在本目录创建独立环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m boxdetect_service serve --model-dir /path/to/model --data-dir /path/to/private-state --port 18765
```

18765是手动启动默认值；已有部署必须传原端口，不据此修改生产监听。默认仅127.0.0.1。模型目录含 model.onnx/model.json，启动核验SHA、两类标签、640/960输入与实际尺寸；私有状态目录必须在仓库外。首次启动生成0600的admin-secret.txt，使用其密码登录管理员面板；当前没有网页改密入口，密码文件需妥善保管。

OMRS「设置 → AI 框选服务」填写已有服务根地址，保存后点击「打开管理面板」，通过主站 `/boxdetect/` 进入；在面板创建调用Key，再填回OMRS设置、保存并测试，选择默认提供方为独立服务。可用本机服务或其他用户提供的HTTPS服务，地址可有安全反代前缀。每个客户端用独立Key；留空保存保留原Key，清除需明确操作。

也可 `pip install .` 后从源码外运行 `python -m boxdetect_service` 或 `omrs-boxdetect`。安装包包含三项面板资产，不包含模型、图片和私有库。旧tools/boxdetect入口委托同一实现。

## 共享与鉴权

外部调用须先在面板设置开启「允许对外调用」，或启动时明确传 `--allow-external`；此开关不调整监听或HTTPS。使用已有OMRS HTTPS入口分享时，客户端配置 `https://主站/boxdetect`，API仍由框选Key鉴权，管理员页面还受OMRS登录保护。独立部署可把现有HTTPS入口反代到同一个检测监听；明确设置 `--public-origin https://服务域名 --secure-cookie`，需要时用 `--allow-host` 登记精确Host。

`--trusted-proxy`只登记可信代理网段，默认回环；代理必须清理并写入真实X-Forwarded-For。不能把任意来源登记为可信。公网直接监听需显式 `--bind` 与网络部署；推荐复用已有HTTPS入口。调用Bearer Key和管理员会话相互隔离，管理写操作有Origin/CSRF保护，Key只在创建时显示、库内保存摘要，可立即吊销。默认Key每分钟10次，可调1–100；暂停接单保留管理能力。

## 协议和历史

`GET /healthz`仅返回存活信息。`GET /api/v1/status`和`POST /api/v1/detect`需 `Authorization: Bearer <调用Key>`。检测请求为 `{image:dataURL,request_id?,source?}`，编号为32位小写十六进制，source为inbox/draft/test/api/legacy。响应包括0–1的 `boxes:[{role,x,y,w,h,conf}]`、width、height、strips、parts、model、elapsed_ms及history_id。一次整图一条历史；相同Key／编号／图片返回既有回执，冲突409。

图片支持PNG/JPEG/GIF，≤15MiB、≤4000万像素、JSON≤22MiB，新版高宽比≤100。长图在服务切片，沿用高宽比>3、条带约2倍宽、8%重叠、JPEG85与跨条带合框。推理串行，队列最多8个，HTTP同时最多32个连接；ORT线程3／1。框选回执与原图只进服务私有SQLite，不自动进训练集。

面板可筛选历史、查看原图叠框和完整回执，默认30天／10000条／256MiB原图；原图容量超限先清图片，回执仍按记录期限保留。重启将未完成任务标中断；未知网络结果应使用原编号核对，不能假定请求未执行。仅管理员可读原图。

## 模型、训练和兼容

`--models-dir /path/to/candidates`登记候选模型的直接子目录；网页仅能选择登记项。应用或恢复上一模型须确认、核对revision，加载/哈希/实际尺寸/白图推理通过后才提交，失败保留原模型。模型选择和操作记录持久化，模型文件须保留；不要修改已登记文件来代替显式应用。预检只证明能推理，内容准确率在训练评测中核对。

训练、导出与人工复核仍通过OMRS `/train`及离线工具；训练完成不会自动切换在线模型。OMRS保存新版连接后关闭旧模型控制器，设置仅保留部署者登记的固定unit启停。旧服务的managed/active及训练产物不被自动迁移，独立服务持有新模型选择。

`GET /health`、`POST /detect`保留旧返回格式，默认须Key。旧匿名本机客户端必须由部署者显式传 `--legacy-loopback`；该例外仅限实际回环来源，不能对外开放匿名检测。迁移既有部署前保全原unit、模型、端口、状态与资源限额，先完成隔离验收；源码安装不自动重启生产或修改密钥。部署模板见 [deploy/boxdetect.service](../../deploy/boxdetect.service)，示例必须按实际环境填写。

模型预检可单独运行：`python -m boxdetect_service probe --model-dir /path/to/model`。CPU/内存/时间限制由部署者设置，预检不发布模型或启动训练。

## 验证与备份

```bash
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_*.py' -q
python3 tests/package_smoke.py --model-dir /path/to/model-snapshot --wheelhouse /path/to/wheels --out /tmp/boxdetect-package.json
```

安装包冒烟需pip/setuptools/wheel及推理依赖wheel；在临时目录复制源码、模型，构建并安装到新环境，删除源码副本后验证真实推理、预检、旧协议、Key整图历史和面板资产。省略wheelhouse会按清单安装依赖。`--port 0`仅用于隔离测试。

私有目录含boxdetect.sqlite3和初始密码，不随安装包或OMRS题库备份。备份服务时停止该实例并保全完整私有目录及已选择模型；SQLite清理复用空闲页，不保证立即缩小文件。协议与OMRS安全边界见仓库 `AI/boxdetect.md`。
