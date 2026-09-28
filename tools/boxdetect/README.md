# 本地框选训练工具

执行者：维护者，完整模式；CPU 训练、数据和权重均在仓库外的 `~/omrs-train/`，真实 Vault 只读。需要 Pillow；训练依赖单独安装到虚拟环境，不进入 OMRS 运行环境。

## 数据构建

```bash
uv venv ~/omrs-train/.venv --python 3.13
uv pip install --python ~/omrs-train/.venv/bin/python torch==2.14.0+cpu torchvision==0.29.0+cpu --index-url https://download.pytorch.org/whl/cpu
uv pip install --python ~/omrs-train/.venv/bin/python -r tools/boxdetect/requirements-train.txt
~/omrs-train/.venv/bin/python tools/boxdetect/build_dataset.py --vault /root/workspace/apps/OMRS --out ~/omrs-train/datasets/20260929-1
```

`--vault` 接受 Vault 根目录或其 `错题` 子目录。输出目录必须不存在且位于真实数据外。只读 SQLite `mode=ro`，不调用会建目录或迁移数据库的业务连接函数。排除缺类、未编辑 AI 框、缺失／损坏图片、尺寸／哈希不符与非法坐标；不容忍截断图片。原图与标签在外部目录形成快照，后续训练不再访问真实 Vault。

64 位 dHash 阈值默认 4，按连通分组后固定种子 20260929 切分约 70/15/15，测试图至少 15 张。后续新版本默认读取同一 datasets 目录下最早的 manifest 冻结测试集，也可指定 `--frozen-manifest`。测试图片或标签变更会拒绝构建；与测试图近似的新图进入 quarantine，既不扩充测试集也不泄漏到训练。空条带保留为负样本，截断框保留高度须同时达到条带高 3% 和原框高 15%。

## 后续工具

训练、整图评估、ONNX 发布与服务入口正在按 box-detect 计划实现，尚无可用模型；当前可执行入口为数据构建。运行 `python3 -m unittest tests.test_boxdetect -q` 验证分组冻结、只读筛选与裁框边界。
