# 独立框选检测服务

同仓 `services/boxdetect/` 提供题目／答案的固定 ONNX 推理与模型预检，包名 `boxdetect_service`。运行只需 onnxruntime、numpy、Pillow，不导入 OMRS、训练工具、torch 或 ultralytics，不访问题库或写受管模型状态。Python 要求 3.11+，当前验证环境为 3.13.5；依赖精确版本见 requirements.txt。

## 安装与启动

在本目录创建独立环境并安装推理依赖：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m boxdetect_service serve --model-dir ~/omrs-train/models/current --port 18765
```

服务只绑定 127.0.0.1。`--port 0` 用于随机端口隔离测试。模型目录必须包含 model.onnx 与 model.json；启动时检查 SHA、类别和实际输入尺寸，加载一次，不热加载后续磁盘改动。Ctrl+C 正常关闭服务。

可从本目录 `pip install .` 构建安装包；安装后在源码目录外执行 `python -m boxdetect_service serve ...` 或 `omrs-boxdetect serve ...`。模型和图片仍存仓库外，不随安装包发布。根目录旧 `tools/boxdetect/serve.py`、inference.py 与 probe.py 委托同一实现，原有 CLI／导入继续可用。

## 协议与预检

`GET /health` 返回 file、sha256、classes、name、imgsz、conf，表示进程实际加载的模型。`POST /detect` 接受 `{image: dataURL}`，返回 boxes，每项含 label、归一化 bbox_2d 与 confidence。PNG／JPEG／GIF、15MiB 图片、4000 万像素和 22MiB 请求上限沿用原协议；单线程处理 HTTP，ORT 内部线程 3／1。整图切片和结果合并由 OMRS 或离线评估完成。

显式预检命令：

```bash
.venv/bin/python -m boxdetect_service probe --model-dir ~/omrs-train/models/current
```

预检核对模型文件／元数据、类别、阈值、640／960 输入及实际尺寸，并完成一次白图推理。CPU、内存和时间限制由调用者设置；OMRS 的受管预检在独立 systemd 限额单元运行。预检不发布模型、不改指针、不启动训练。

## 受管模型边界

生产服务使用部署者显式指定的 managed/active，而手动 CLI 默认 models/current；两者可能为不同模型。不要用默认参数替换生产 unit。固定 unit、控制登记、操作历史、training.lock 与模型应用／回退继续由 OMRS 管理；控制 API 和页面见仓库 AI 文档。源码安装不会更新生产服务或模型。

## 验证

```bash
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 -m unittest discover -s tests -t . -q
python3 -m pip install 'setuptools>=68' wheel
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/package_smoke.py --model-dir /path/to/model-snapshot
```

安装包冒烟在自动清理的临时目录复制源码与模型，构建 wheel，再在新最小环境安装依赖；删除源码副本后，从外部目录验证真实推理、禁止的模块依赖、预检与 HTTP。可传 `--wheelhouse /path/to/wheels` 完全离线安装依赖，`--out /path/to/result.json` 保存结果。测试不修改所给模型目录或生产解释器。
