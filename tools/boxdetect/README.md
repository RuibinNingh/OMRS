# 本地框选训练工具

执行者：维护者，完整模式。在仓库根目录运行下列命令。CPU 训练、数据、模型与日志位于仓库外 `~/omrs-train/`；真实 Vault 只读。主程序不加载 torch 或 onnxruntime；训练环境与仅推理环境的依赖分开锁定。ultralytics 为 AGPL-3.0，本工具按本机自用运行。

## 安装

```bash
uv venv ~/omrs-train/.venv --python 3.13
uv pip install --python ~/omrs-train/.venv/bin/python torch==2.14.0+cpu torchvision==0.29.0+cpu --index-url https://download.pytorch.org/whl/cpu
uv pip install --python ~/omrs-train/.venv/bin/python -r tools/boxdetect/requirements-train.txt
mkdir -p ~/omrs-train/pretrained
curl -fL https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8n.pt -o ~/omrs-train/pretrained/yolov8n.pt
```

仅运行固定模型服务的环境安装 requirements-serve.txt 即可（onnxruntime、numpy、Pillow）。CPU wheel 不可用时可改 Python 3.12 建环境。

## 四步重训与验证

选择尚不存在的数据版本与实验名，以下 20260929-2 只是例子。首次训练先额外用独立实验名、`--epochs 3` 测量耗时与内存；正式训练前先运行模板基线（下一节），不跳过这两步。

```bash
~/omrs-train/.venv/bin/python tools/boxdetect/build_dataset.py --vault /root/workspace/apps/OMRS --out ~/omrs-train/datasets/20260929-2
nice -n 19 ~/omrs-train/.venv/bin/python tools/boxdetect/train.py --dataset ~/omrs-train/datasets/20260929-2 --run ~/omrs-train/runs/20260929-2 --epochs 120
~/omrs-train/.venv/bin/python tools/boxdetect/evaluate.py --dataset ~/omrs-train/datasets/20260929-2 --run ~/omrs-train/runs/20260929-2
~/omrs-train/.venv/bin/python tools/boxdetect/serve.py --model-dir ~/omrs-train/models/current --port 18765
```

第三步显式导出 ONNX，在验证集选择置信度，再评估冻结测试集，不会发布 models/current 或修改 OMRS 配置。发布必须另行显式运行 publish.py。第四步仅绑定 127.0.0.1，`GET /health` 返回 SHA-256，POST 地址可用 `/detect`。隔离实例把 inbox_local_detect_url 配成该地址；生产服务常驻与配置切换须另行授权。

训练脚本 CPU 最多 6 线程，默认 batch 4、640 输入；workers 固定 0。固定 nice 19、关闭 RAM 图像缓存，独立看护每 0.5 秒检查内存：可用低于 2 GiB 或训练进程树 RSS 超过默认 6 GiB 即停止。默认最多 4 小时；启动时可用内存不足 4 GiB 拒绝运行。训练日志是 run/train.log，每轮原子 status.json 和追加 metrics.jsonl 供面板读取。

## 单独评估、导出与恢复

```bash
# 必须先于模型测试结果产出，模板只从训练集选参考图
~/omrs-train/.venv/bin/python tools/boxdetect/evaluate.py --dataset ~/omrs-train/datasets/20260929-1 --baseline template
# 只导出，不修改当前模型
~/omrs-train/.venv/bin/python tools/boxdetect/publish.py --run ~/omrs-train/runs/20260929-yolov8n-640 --export-only
# 只在验证集选阈值，产出 thresholds.json
~/omrs-train/.venv/bin/python tools/boxdetect/evaluate.py --dataset ~/omrs-train/datasets/20260929-1 --model ~/omrs-train/runs/20260929-yolov8n-640/model.onnx --split val --select-conf
# 使用已选阈值评估，例中的 .55 是本次 640 实验结果
~/omrs-train/.venv/bin/python tools/boxdetect/evaluate.py --dataset ~/omrs-train/datasets/20260929-1 --model ~/omrs-train/runs/20260929-yolov8n-640/model.onnx --conf .55
# 仅显式发布已有导出文件；校验 best.pt、ONNX 与 export.json 一致
~/omrs-train/.venv/bin/python tools/boxdetect/publish.py --run ~/omrs-train/runs/20260929-yolov8n-640 --conf .55
# 中断后以完全相同数据与参数恢复 last.pt；已完成且检查点已结束的实验不再 resume
nice -n 19 ~/omrs-train/.venv/bin/python tools/boxdetect/train.py --dataset ~/omrs-train/datasets/20260929-1 --run ~/omrs-train/runs/20260929-yolov8n-640 --epochs 120 --resume
```

评估是整图「slice_plan → JPEG 85 条带推理 → merge_strip_boxes」。指标包括题目／答案平均 IoU、IoU≥0.75 占比、多余框，以及两类都达标且无多余框的整图无需修改率；叠加图长边不超过 1600。阈值候选 .1/.25/.4/.55 只看验证集，按两类达标率总和、整图无需修改、较少多余框、较高阈值依次择优，不看测试集调参。

## 数据规则

`--vault` 接受 Vault 根目录或其错题子目录。只读 SQLite mode=ro，不调用会建目录或迁移数据库的业务连接函数。排除缺类、未编辑 AI 框、缺失／损坏图片、尺寸／哈希不符与非法坐标；不容忍截断图片。原图和框形成外部快照，训练不再访问真实 Vault。

64 位 dHash 阈值默认 4，连通分组后以种子 20260929 切分约 70/15/15，测试图至少 15 张。新版本默认读取同一 datasets 目录下最早的 manifest 冻结测试集，也可用 --frozen-manifest 指定。冻结图／标签变更拒绝构建；与测试图近似的新图进入 quarantine，不扩充测试集、不泄漏到训练。空条带保留为负样本，截断框的保留高度须同时达到条带高 3% 和原框高 15%。

## 检查

```bash
python3 -m unittest tests.test_boxdetect tests.test_boxdetect_training tests.test_boxdetect_inference tests.test_trainpanel -q
python3 tests/e2e/trainpanel.py
python3 tests/e2e/boxdetect.py --dataset ~/omrs-train/datasets/20260929-1
```

前一行可使用未安装 torch/onnxruntime 的系统 Python；真实模型 E2E 会用训练根目录下的独立 venv 启动服务，OMRS 和浏览器只使用临时 Vault。实验与限制见 `AI/training/`；当前精度是否达标以实验记录为准，不能因服务成功返回框就建议上线。


## DeepSeek 内容评测

以下命令在仓库根目录运行；替换评测名时用尚不存在的目录。prepare 只推理生成实际裁图，run 才付费调用；run 中断后使用相同命令恢复，不覆盖已有结果。CLI沿用agent渠道，固定deepseek-flash、思考开启、4096输出；单并发/60秒，临时错误最多重试两次。整个轮次默认共用content-round-1台账，最多300次请求、官方等价费用达到US$2后暂停；中转真实扣费未知。不能换台账绕过本轮限额。

```bash
~/omrs-train/.venv/bin/python tools/boxdetect/audit.py prepare --dataset ~/omrs-train/datasets/20260929-content-1 --model ~/omrs-train/runs/20260929-yolov8n-640/model.onnx --split val --conf .55 --out ~/omrs-train/audits/new-val
~/omrs-train/.venv/bin/python tools/boxdetect/audit.py run --out ~/omrs-train/audits/new-val --config /root/workspace/apps/OMRS/错题/.omrs/config.json
```

验证集比较.1/.25/.4/.55，按内容通过数、较少缺漏、较少多余、较高阈值选定，再冻结参数评test（历史回归）和independent。省略--model生成模板基线。不传人工框或预期给DeepSeek；漏检不调用也计失败。原判和复核记录在/train查看。历史25次实验用audit.py import导入，保留失败、思考参数、提示版本及校准标记。

重训需要先在train分区评测、逐个目视确认困难案例。reweight.py --dataset 原快照 --audit-path 训练评测目录 --out 新快照，只对经复核失败的训练原图全部条带重复采样一次。评测来自验证/测试或manifest不符则拒绝。先3轮冒烟再正式120轮，640/batch4/线程6；无新数据与困难样本就不重复训练。冻结图或标签变动、跨集合近似桥接均停止构建。

阈值选择使用 `decision.py select --audits 四个验证评测目录 --out 新选择文件.json`；候选比较使用 `decision.py compare --baseline 旧模型回归目录 --candidate 新模型回归目录 --out 新结论文件.json`。存在独立集时必须同时传 `--independent-baseline` 和 `--independent-candidate`。select与compare要求全部参与案例已有用户或执行者复核，并校验原图集合一致；不会发布current。

prepare核对冻结原图SHA，run恢复前验证裁图及资源清单SHA；哈希不符停止。错误记录不可因人工改判绕过调用失败门禁。

## 受管服务登记（部署者，完整模式）

已有systemd检测服务时，先备份unit和主程序drop-in，再初始化受管映射。以下本机示例不适用于任意外部检测服务器，运行前需获得生产变更授权：

```bash
python3 tools/boxdetect/bootstrap_control.py --root /root/omrs-train --model-dir /root/omrs-train/models/production-20260929-yolov8n-640
```

在部署文件/etc/omrs-boxdetect-control.json登记root、vault、unit、port、python。本机值分别为/root/omrs-train、/root/workspace/apps/OMRS、omrs-boxdetect.service、18766、/root/omrs-train/.venv/bin/python。主服务环境设置OMRS_BOXDETECT_CONTROL为该文件路径；检测unit的--model-dir改为/root/omrs-train/managed/active，保留内存/CPU限制。daemon-reload后重启两服务，确认health的SHA/阈值/尺寸仍与原模型一致。登记文件不能由网页配置，unit必须为固定名称、URL必须匹配回环端口；无systemd或未登记只显示说明。

模型候选来自runs中完整导出且权重/ONNX/评估身份一致的实验。应用先以限30秒/768MiB的独立进程运行probe.py，再原子切换并重启，健康检查失败恢复上一配置。训练占用training.lock时拒绝切换。正常启动/停止不换模型；恢复上一模型是显式操作。models/current用于训练工具，与受管指针独立。

检查：`python3 -m unittest tests.test_traincontrol -q`、`python3 tests/e2e/traincontrol.py`。后者使用测试后端及临时Vault/随机端口，覆盖启停、切换、回滚和四种尺寸/主题。
