# 本地题目／答案框选模型：训练、训练面板与接入计划

> 本计划一次写成执行说明（按 `AGENTS.md`「规划模式」模板），进度只记在同目录 `progress.md`。
>
> - 执行者：Codex · 完整模式（用户也可指定 Claude Code · 完整模式）
> - 规划者：Claude Code · 完整模式，2026-09-28，基于本机 HEAD `2bb401c`（v1.29.0）
> - 训练要连续跑数小时，允许分两个会话；正式训练在后台跑时并行做训练面板（§4），中断恢复见 §10
> - 与 `ai-draft` 并行：那边的工作树也改 `assets/app/features/create/`、`omrs/server.py`、`omrs/common.py`；本计划只在这些文件里加小块，开工与每次提交前先同步 `main`
> - 生产部署（常驻检测服务、切换生产配置）不在本计划内，须用户另行授权

## 0. 用户诉求清单（原话）

| # | 原话 | 分类 | 落点 |
|---|---|---|---|
| T1 | "我的错题本准备进行AI训练了,我需要你帮我制定计划,开始吧" | 明确要求：出训练计划；本轮只写计划 | 全文 |
| T2 | "我先明确训练输入,只有题目和答案的范围,不包含是否录入图片或者文字"（见 `AI/training/README.md`） | 明确要求：任务是两类框检测 | §1、§5 D1 |
| T3 | 训练地点"按用户选择采用本地 CPU"（见 `AI/training/README.md`） | 明确要求 | §2、§5 D3 |
| T4 | "那么AI文件夹里面先初始化一个用于记录训练的文件夹吧,在里面沉淀经验" | 明确要求：实验记在 `AI/training/` | §4 每阶段的记录 |
| T5 | ai-draft U6："手动框选又要收集数据训 AI"；U8："……也要框选，这样一般是为了训练模型创造更多数据" | 隐含前提：训练的最终用途是替代手工框选，数据会持续增长 | §3、§4 阶段 5（可重复训练） |
| T7 | "记得还有弄一个新的AI训练面板,独立于现在的面板,入口同样是录入题目-AI训练-打开训练面板" | 明确要求：独立新页；入口放在录入题目 → AI 训练工作区，按钮叫「打开训练面板」；现有 AI 训练工作区保留 | §3.2、C5–C7 |
| T8 | "里面展示一些可视化数据" | 明确要求 | §3.2 数据、评估、历史三块 |
| T9 | "如果可以的话展示进度啥的也不错" | 明确要求（用户标为"如果可以"，本计划能做到，列入主线） | §3.2 训练进度；§5 D10 |
| T10 | "模型训练完应该是固定文件吧" | 问题：答复见 §5 D9（是，固定的 ONNX 文件 + 校验值） | D9 |
| T11 | "我倒挺期待上传一个图片看看它的效果,也就是实时测试" | 明确要求：用户上传一张图，当场看模型框 | §3.3、C6 |
| T12 | "顺便也可以积累数据*(可选择是否积累)" | 明确要求：实时测试的图可选进训练数据，开关由用户选；默认关 | §3.3、§5 D12 |
| T6 | `inbox_detect_provider` 已预留 `local_http`，注释写「训好的 YOLO / ONNX 服务」（`omrs/ai_assist.py::detect_regions_local`） | 隐含前提：训练成果经现有 `local_http` 协议接入，不另造接口 | §3、§5 D5 |

## 1. 任务目标

**主目标：** 用现有 128 张人工标注的作业帮截图，在本机 CPU 上训练一个题目／答案两类框的检测模型，包装成符合 `local_http` 协议的本地检测服务，并在隔离的 OMRS 实例里通过收件箱「AI 框选」真实跑通；在固定测试集上用整图指标与现有「模板框选」对比，给出是否值得接入生产的结论。

必须同时满足：

1. 训练输入是原图（按 OMRS 同款条带切片），标签只有 `question`／`answer` 矩形（T2）；
2. 数据构建、训练、评估、服务四步都是仓库里的脚本，数据变多后一条命令能重训（T5）；
3. 每次实验按 `AI/training/template.md` 记录，经验沉淀到 `lessons.md`（T4）；
4. OMRS 主程序保持零依赖：不 import torch／onnxruntime，模型只经 `local_http` 协议调用（T6）；检测协议与现有收件箱、标注页行为不改；
5. 新增独立的「训练面板」页 `/train`，从 录入题目 → AI 训练 →「打开训练面板」进入，展示数据、训练进度与曲线、评估对比、实验历史（T7–T9）；
6. 面板里能上传图片实时测试模型，并可选择把这张图积累进标注集（T11、T12）。

## 2. 当前背景与约束

**规范来源：** `AI/training/README.md`（口径、记录原则）、`AI/training/records/2026-09-28-baseline.md`（数据与硬件快照）、`AI/inbox.md` §4 `detect_regions_local` 与 §8 提供方、`AI/data.md` §16（标注集存储）、`AGENTS.md`「完整模式」测试实例规则。

**实测事实（2026-09-28，规划者在本机，SQLite `mode=ro` 或临时副本）：**

| 事实 | 值 | 来源 |
|---|---|---|
| 独立标注集已完成图 | 69 张，每张恰好 1 题目框 + 1 答案框 | 实测 `annotate.db` |
| 收件箱已完成图 | 63 张，其中 59 张两类齐全；1 个未改过的 AI 题目框 | 实测 `inbox.db`；与基线记录一致 |
| 两批完全重复图 | 0（sha256） | 实测 |
| 图片尺寸 | 宽恒为 1080；高 2376–6752；高宽比 2.2–6.25 | 实测 |
| 题目框顶端 | 441–576 px（很稳定） | 实测 |
| 答案框顶端 | 相对高度 0.42–0.91（变化大） | 实测 |
| 模板框选基线（沿用上一张，69 张标注集） | 题目 平均 IoU 0.627，IoU≥0.75 占 23/68；答案 平均 IoU 0.272，IoU≥0.75 占 5/68 | 实测：临时副本上调用 `omrs.inbox.template_boxes` |
| OMRS 调用本地服务的方式 | 高宽比 >3 的图按 `slice_plan` 切成 1080×2160 条带（重叠 8%），每条带单独 `POST`，结果经 `merge_strip_boxes` 合并 | 读代码 `omrs/inbox.py::_detect_with_provider` |
| 协议 | 请求 `{image: dataURL, layout, width, height}`；响应数组或 `{boxes:[{label, bbox_2d:[x1,y1,x2,y2], confidence}]}`，坐标全 ≤1 时按 0–1 小数解析 | 读代码 `omrs/ai_assist.py` |
| 硬件 | i5-12400，12 线程，31 GiB 内存；**当时可用 10 GiB，swap 已用 9 GiB**；无 GPU；根分区剩 43 GB | 实测 |
| 生产进程 | `omrs.service` 以 root 运行 `/usr/bin/python3`（有 Pillow 12.3），端口 8471，代码在 `/root/workspace/releases/omrs-63adade`；`~` 即 `/root` | 实测 `systemctl cat omrs` |
| 面板相关现状 | `/train`、`/api/trainpanel/*` 未被占用；前端没有图表库，现有图表都是手写 SVG；独立页先例 `/annotate`（`assets/app/annotate.html` + `features/annotate/`） | 实测 grep |
| 依赖 | 本机无 torch／ultralytics／onnxruntime；有 `uv`、Pillow、numpy；可联网，PyPI 有 cp313 的 onnxruntime 1.30.0、torch 2.14.0；ultralytics 8.4.x 为 AGPL-3.0 | 实测 |

**已定位的问题：** 答案框是模板框选的主要短板（IoU≥0.75 仅 7%）——答案起点随题目长度变化，模板无法预测。这正是模型要解决的问题。

**硬约束：**
- 训练脚本对真实数据只读：`错题/` 下任何文件不得由脚本写入；构建数据集只读 SQLite（`mode=ro`）和原图文件，产物写到仓库外。唯一写 `错题/` 的新路径是面板「积累」开关打开时经 `omrs/annotate.py` 现有函数写标注集，且只在测试实例里验证。
- 训练产物（数据集、权重、日志）一律放仓库外的 `~/omrs-train/`，不进 Git；文档只记相对位置、数量与 SHA-256。
- 本机同时跑着生产 OMRS：训练必须 `nice -n 19`、限制线程数，且不碰生产端口与 systemd。
- 测试实例按 `AGENTS.md`：临时 Vault、随机高端口、去掉 `OMRS_SYSTEMD_SERVICE`。

## 3. 最终预期行为

### 3.1 数据流

```
错题/.omrs/annotate + inbox（只读）
        │  build_dataset.py：筛选 → 近似去重分组 → 按组切分 → 按 slice_plan 切条带 → YOLO 格式
        ▼
<训练目录>/datasets/<版本>/   train/val/test + manifest.json
        │  train.py：YOLO 小模型，CPU，后台，可续训；每轮写 status.json + metrics.jsonl
        ▼
<训练目录>/runs/<实验>/        weights/ · status.json · metrics.jsonl · eval.json · overlays/
        │  evaluate.py：测试集整图，走 OMRS 同款 slice_plan + merge_strip_boxes，模板为对照
        │  publish：best.pt → model.onnx，复制到 models/current/（附 model.json）
        ▼
<训练目录>/models/current/model.onnx ──► serve.py（onnxruntime，127.0.0.1，local_http 协议）
                                               ▲
OMRS（零依赖）                                  │ POST 条带
 ├─ /api/trainpanel/*  只读 <训练目录> 下约定的文件 ─► 训练面板 /train（数据、进度、曲线、评估、历史）
 └─ /api/trainpanel/try  上传一张图 → Pillow 切条带 → 逐条带调 serve.py → 合并 → 画框
          └─ 「积累」开关打开 → annotate.upload + save（status=todo，预填模型框）→ 去标注页校正后才成训练数据
```

`<训练目录>` 默认 `~/omrs-train`（生产服务以 root 运行，即 `/root/omrs-train`），可由配置 `train_dir` 覆盖。

### 3.2 训练面板 `/train`（T7–T9）

**入口：** 录入题目 → AI 训练工作区，在现有「框选标注页」一栏旁加一栏「训练面板」：一行摘要（当前模型名与测试集答案框达标率，或「还没有模型」；训练中显示「训练中 第 n / N 轮」），按钮「打开训练面板」以新标签页打开 `/train`。与「打开标注页」同样的写法（`target="_blank"`）。现有工作区其余内容不动。

**页面：** 与 `/annotate` 一样不经主页外壳，只加载 tokens、base、ui 样式与本页样式；主题、续期、401 跳登录都照 `/annotate`。顶栏：页名、当前模型（名称、发布时间、SHA-256 前 8 位）、检测服务状态点（在线／未启动／未配置）。主体五块，从上到下：

| 块 | 内容 | 数据来源 |
|---|---|---|
| ① 训练进度 | 最新一次实验：状态（训练中／已完成／失败／已中断）、第 n / N 轮进度条、已用时间与预计剩余、每轮耗时；训练中每 5 秒自动刷新；已中断时显示续训命令（可复制） | `runs/<最新>/status.json` |
| ② 训练曲线 | 两张折线图：损失（训练 / 验证的 box、cls）、验证集 mAP50 与 mAP50–95；横轴为轮次；训练中随刷新增长 | `metrics.jsonl` |
| ③ 效果评估 | 模型 vs 模板对照：题目／答案各自的「IoU≥0.75 占比」「平均 IoU」分组条形；「整图无需修改」占比大数字；IoU 分布直方图；达标线画成参考线；失败样本墙（IoU 最低的至多 12 张叠加缩略图，点开看大图） | `eval.json`、`overlays/` |
| ④ 数据概况 | 数据集版本、train/val/test 张数与条带数、排除张数（按原因）；当前标注集与收件箱里「比数据集多出的已完成图」张数，≥10 张时提示「可重新构建数据集并重训」及命令 | `manifest.json` + 实时读两库计数 |
| ⑤ 实验历史 | 表格：实验名、日期、数据版本、轮数、总耗时、测试集题目／答案达标率、是否当前模型 | 各 `runs/*/status.json` 与 `eval.json` |

实时测试（§3.3）放在顶栏下方、①之前，因为它是用户最想点的。**面板不启动、不停止训练**：没有训练时显示「开始训练」的命令文本供复制。

**状态：** 训练目录不存在或为空 → 整页空状态，列出四条上手命令；某个文件损坏或缺失 → 只有对应块显示「读取失败」并可重试，其余块照常；接口 401 → 跳登录。

### 3.3 实时测试（T11、T12）

- 拖放 / 选择 / 粘贴一张 PNG / JPEG / GIF（≤ 15 MB），点「测试」。服务端用 Pillow 按 `slice_plan` 切条带，逐条带调 `inbox_local_detect_url` 指向的检测服务，`merge_strip_boxes` 合并，返回整图框、每框置信度、条带数与总耗时。
- 页面显示原图与叠加框（题目 `--info`、答案 `--success`，与标注页一致），列出每个框的角色与置信度、总耗时。一次只测一张，结果不落盘（开关关时）。
- 「积累到标注集」开关（配置 `train_try_collect`，默认关，改动即保存）。打开时，每次测试成功后把原图经 `annotate.upload` 写入标注集，并以模型框调 `annotate.save(status=None)` 预填，状态保持 `todo`；结果区显示「已加入标注集（待校正）」和打开标注页的链接。只有用户在标注页校正并标为完成后才进导出与训练（导出默认只含 done）。同一张图（sha256 已存在）不重复加入、不覆盖已有框，提示「标注集里已有这张」。
- 检测服务地址为空 → 提示去 AI 训练工作区的「本地检测服务地址」填写；连不上 → 显示「检测服务未启动」与启动命令；两种情况都不写任何数据。
- 可选（低成本时做）：同一张图旁边显示模板框选结果作对照。

## 4. 实施计划

提交粒度：7 个提交（下文 C1–C7），每个门禁全绿，含代码、测试、文档、任务日志 `AI/logs/<开工日期>_box-detect.md` 与 `progress.md` 更新。C1–C4 不升版本号；C7 升次版本号（按当时 HEAD 顺延），`changelog.md` 一段写全训练面板与本地模型。

**顺序：** 阶段 0 → C1 → C2 冒烟 → 启动正式训练（后台）→ 训练跑着的同时做 C5、C6（面板可以直接看正在跑的真实训练）→ 训练结束后完成 C2 评估 → C3 → C4 → C7。C2 的正式训练开始前，§5 D10 的文件契约必须已在 `train.py` 里实现。因此提交的实际顺序是 C1 → C5 → C6 → C2 → C3 → C4 → C7；C5、C6 的测试用假训练目录和假检测服务，不依赖 C2、C3。

### 阶段 0：复核与环境

1. `git status --short`；开工时工作区里已有他人未提交的 `AI/training/`、`AI/plans/ai-draft/` 等改动，保留不动，提交只纳入本任务路径（`AI/training/` 若届时仍未提交，先停下问用户是否由本任务一并提交——见停止条件 4）。
2. 复核 §2 实测表中数据量那三行，不一致时以现值为准写进任务日志，不停工。
3. 建环境：`uv venv ~/omrs-train/.venv --python 3.13`，装 CPU 版 torch/torchvision（`--index-url https://download.pytorch.org/whl/cpu`）、固定版本的 ultralytics、onnx、onnxruntime。实际版本写进 `tools/boxdetect/requirements-train.txt`（精确到补丁号）；服务端另写 `requirements-serve.txt`（只有 onnxruntime、numpy、Pillow）。
4. 跑 §9 门禁，把计数写进任务日志「基线」。

### C1 数据集构建 `tools/boxdetect/build_dataset.py`

- 读两个来源（只读）：标注集 `status='done'`；收件箱 `status='done'`。
- 排除规则（§5 D2）：缺任一类框的图、含未编辑 AI 框（`origin='ai'`）的图、原图缺失或无法解码的图。每条排除写进 manifest 的 `excluded`（id + 原因）。
- 近似去重与分组：对每张图算感知哈希（dHash，Pillow 实现，不引新依赖）；汉明距离 ≤ 阈值的归为同组。阈值先在数据上看分布再定，写进记录。
- 按组切分 train/val/test ≈ 70/15/15，固定随机种子；**测试集清单一经生成就冻结**（`test_ids.txt` 进 manifest，后续重训沿用，新图只进 train/val）。
- 切条带：对每张图调用 `omrs.inbox.slice_plan(1080, H)`，把整图框裁到各条带（§5 D4 的残框规则），写 YOLO 标签。整图级的原始框另存，供评估用。
- 输出 `~/omrs-train/datasets/<YYYYMMDD-n>/`：`images/{train,val,test}/`、`labels/…`、`data.yaml`、`manifest.json`（来源、数量、排除、分组、SHA-256）。
- 纯函数（条带裁框、分组、切分）放 `tools/boxdetect/common.py`，只依赖标准库与 Pillow。
- 测试 `tests/test_boxdetect.py`（unittest，不依赖 torch/onnxruntime）：裁框边界、残框丢弃、同组不跨集、种子可复现、测试集冻结后新图不进测试集。
- 文档：`tools/boxdetect/README.md`（给人看的四条命令）；`AI/training/README.md` 加「工具入口」一节；`AGENTS.md` 映射表加 `tools/boxdetect/` → `AI/training/README.md`。

### C2 训练与评估 `train.py`、`evaluate.py`

- `evaluate.py` 先写、先跑**模板基线**：在测试集整图上跑 `template_boxes`（沿用训练集中同版式最近一张），得出与模型同口径的指标。这是对照组，必须先于模型结果产出。
- `train.py`：封装 ultralytics 训练，参数全部写进运行目录的 `args.yaml`；支持 `--resume`；按 §5 D10 每轮写 `status.json` 与 `metrics.jsonl`（ultralytics 回调），异常退出时把状态写成 `failed` 并记错误摘要。
  1. 冒烟：3 轮，记录每轮耗时、内存峰值；
  2. 按冒烟耗时定正式轮数，正式训练总时长上限 4 小时（`nice -n 19`，后台跑，轮询日志）；
  3. 在验证集上选置信度阈值（让验证集整图指标最优），**不看测试集调参**。
- `evaluate.py` 对模型：测试集每张整图走「slice_plan → 逐条带推理 → merge_strip_boxes」，与 OMRS 线上完全同路径；输出 §8 的指标、逐图表和叠加图，按 D10 写 `eval.json`（含模板对照）与 `overlays/`（人工框绿、预测框红，JPEG，长边 ≤ 1600）。
- `publish.py`（或 `train.py publish` 子命令）：导出 ONNX，写 `models/current/model.onnx` 与 `model.json`（D9），旧的当前模型移到 `models/<实验名>/`。
- 记录：`AI/training/records/<日期>_yolo-baseline.md` 按模板填全；达标与否都写；可复用结论进 `lessons.md` 并更新 E 编号。

### C3 检测服务 `serve.py`

- 标准库 `http.server` + onnxruntime；只绑 `127.0.0.1`，端口参数化；`POST` 任意路径按 §5 D5 协议返回；`GET /health` 返回模型文件名、SHA-256、类别。
- 推理前处理与训练一致（letterbox 到训练尺寸）；后处理每类 NMS，输出 0–1 小数坐标。
- 测试：`tests/test_boxdetect.py` 增加前后处理纯函数的用例（坐标换算、NMS、空结果）；服务本体在 E2E 中验证。

### C4 端到端验证与收尾

- 起 `serve.py`（随机高端口）+ 隔离 OMRS 实例（临时 Vault，`inbox_detect_provider=local_http`，`inbox_local_detect_url` 指向服务）。
- 用真实浏览器：上传 3 张**测试集**原图（从 `~/omrs-train/datasets/` 取，不从 `错题/` 直接拖）→ 处理区点「AI 框选」→ 截图确认题目、答案框出现且位置合理；再把服务停掉点一次，确认界面显示「连不上本地检测服务」而不是卡死。
- 收尾：任务日志、`progress.md`、`AI/inbox.md` §8 `local_http` 一行补「本地服务见 `tools/boxdetect/`」；在 `progress.md`「下一步」写好生产切换的两步操作供用户授权。

### C5 训练面板后端 `omrs/trainpanel.py` 与路由

- 新模块，只读 `<训练目录>`：`overview(vault)` 返回 ①④⑤ 所需的汇总（最新实验状态、数据集 manifest 摘要、实验列表、当前模型 `model.json`、两库实时的已完成计数）；`run_detail(vault, run)` 返回 ② ③（`metrics.jsonl` 全部行、`eval.json`）；`overlay_path(vault, run, name)` 只返回 `eval.json` 里登记过的文件。
- 「是否已中断」由 D10 的规则判断；进程是否存活用 `os.kill(pid, 0)`，不读 `/proc` 以外的东西。
- 路由（`omrs/server.py` 挂 `_trainpanel_get` / `_trainpanel_post`，照 `_annotate_get` 的写法；方法名登记到 `tests/check_docs.py` 的 `ROUTE_METHODS`，再 `--write-routes`）：
  - `GET /train` → `assets/app/trainpanel.html`
  - `GET /api/trainpanel/overview`、`GET /api/trainpanel/run?name=`、`GET /api/trainpanel/overlay?run=&name=`、`GET /api/trainpanel/service`（对检测服务的 `/health` 做 2 秒超时探测，返回在线／未启动／未配置与模型信息）
- 配置键（`common.CONFIG_DEFAULTS`）：`train_dir`（默认 `""`，即 `~/omrs-train`）、`train_try_collect`（默认 `false`）。
- 测试 `tests/test_trainpanel.py`：用临时训练目录造假实验文件，覆盖空目录、训练中、已完成、失败、已中断（pid 不存在且过期）、损坏 JSON 只影响对应字段、`run` / `name` 路径穿越被拒、overlay 未登记被拒。
- 文档：`AI/api.md` 新增「训练面板」小节；`AI/data.md` 新增一节写 `<训练目录>` 文件契约与两个配置键；`AGENTS.md` 映射表加 `omrs/trainpanel.py`。

### C6 实时测试接口

- `POST /api/trainpanel/try`（multipart 单文件，同源校验，走进程写锁仅在积累时需要）：校验类型与大小 → Pillow 读尺寸并按 `slice_plan` 切 JPEG 条带 → 逐条带 `ai_assist.detect_regions_local` → `merge_strip_boxes` → 返回 `{boxes, width, height, strips, elapsed_ms, collected?}`。
- `train_try_collect` 为真时按 §3.3 写标注集；为假时不写任何文件（验收 12 会查）。积累失败不影响测试结果返回，结果里带 `collect_error`。
- 保存开关：沿用 `POST /api/config` 写 `train_try_collect`，不另开接口。
- 测试：`tests/test_trainpanel.py` 起一个线程内的假检测服务（`http.server`，返回固定框），覆盖多条带合并、服务未配置、连不上、返回非法 JSON、积累开／关、重复图不覆盖已有框、非图片与超限 400。

### C7 训练面板前端与收尾

- 新页 `assets/app/trainpanel.html` + `assets/app/features/trainpanel/`（`index.js` 入口、`store.js` 数据所有者、`state.js` 纯函数、`view.js` 模板、`charts.js` SVG 图表、`try.js` 实时测试、`trainpanel.css`）。结构、样式约束照 `features/annotate/`；组件复用 `ui/`（stat、progress、table、switch、filedrop、status、empty、skeleton、dialog）。
- 图表手写 SVG，不引第三方库；颜色只用设计 token；折线图有坐标轴刻度与图例，条形图有数值标签；训练中增量刷新不整页重绘（保留滚动与展开状态）。
- 轮询：①的状态为「训练中」时每 5 秒拉 `overview`，有新轮次再拉 `run`；页面隐藏时暂停；其余状态不轮询。
- 入口：`features/create/train-view.js` / `train.js` 加「训练面板」一栏（§3.2 入口），摘要读 `overview`，失败时只显示说明。
- 测试：`tests/app/trainpanel.test.mjs`（刻度与坐标换算、中断判断文案、预计剩余时间格式、增量合并 metrics）；`tests/e2e/trainpanel.py`（临时 Vault + 假训练目录 + 假检测服务：从录入页入口打开新标签页；五块渲染；改写 `status.json` 追加一轮后 10 秒内进度与曲线更新；实时测试出框；积累开关开／关对标注集的影响；服务停掉的错误态；空目录、读取失败、加载中、正常四档审计，照其他 E2E 的写法）；在 `AI/environment.md` 登记新 E2E 命令。
- 门禁：`check_ui.py`、`check_contrast.py`、`tests/app/run_browser.py`、`node --test`、`tests/visual/run.py --ref <C6 提交>` 前后对比（录入页 AI 训练工作区多出一栏，差异在日志里解释）。
- **真实数据走一遍（只读查看，不开积累）：** 用生产训练目录 + 隔离 OMRS 实例（临时 Vault、`train_dir` 指向真实 `~/omrs-train`，这是只读的）打开面板，截图确认五块显示的是本次真实训练的数字，与实验记录一致。
- 文档：新建 `AI/frontend/trainpanel.md`（速查头），`AI/frontend.md` 索引、`AI/frontend/create.md`「AI 训练」一节、`AI/README.md`、根 `README.md` 功能介绍各加一句；`AGENTS.md` 映射表加 `assets/app/features/trainpanel/`、`assets/app/trainpanel.html`；版本号按「任何版本号变更」一行全部同步。

## 5. 关键技术决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | 两类：`0=question`、`1=answer`，与两份导出一致 | T2；导出已统一类别号 |
| D2 | 缺类图、含未编辑 AI 框的图**排除**，不在本计划里补标 | 128 张够首轮；补标是人工活，列为「需用户确认」；排除清单留在 manifest，补标后重跑 C1 即可 |
| D3 | 模型：ultralytics YOLO 最小档（n），COCO 预训练权重微调，CPU；输入 640；batch 4 起步，workers 2，torch 线程 6 | 数据少必须迁移学习；n 档 CPU 可训；线程留一半给生产服务。AGPL-3.0 仅本机自用，不分发，可接受 |
| D4 | 训练、推理都按 `slice_plan` 切条带；框被条带边缘截断时，保留条带内部分，若保留高度 < 条带高 3% 或 < 原框高 15% 则丢弃 | 与线上推理同分布；过小残片是噪声，`merge_strip_boxes` 会把相邻条带的框并回整框。阈值可在验证集上调，调了写进记录 |
| D5 | 服务响应 `{"boxes":[{"label":"question"\|"answer","bbox_2d":[x1,y1,x2,y2],"confidence":c}]}`，坐标为条带内 0–1 小数 | `parse_detect_output` 全 ≤1 即按小数解析，不依赖传入宽高；不改协议 |
| D6 | 评估以**整图**为准：合并后的框与人工框算 IoU；条带级 mAP 只作参考 | 用户最终看到的是整图上的框（`AGENTS.md` 防漂移第 6 条） |
| D7 | 测试集冻结，重训沿用；只在验证集调阈值 | 数据少，一旦对测试集调参结论就不可信 |
| D8 | 训练产物在 `<训练目录>`（默认 `~/omrs-train/`），脚本在仓库 `tools/boxdetect/`，OMRS 不 import 它们 | 主程序零依赖；权重和数据含私人截图，不进 Git；不放 `错题/` 是因为设置页备份会整个打包 `错题/`，数据集与权重会让备份膨胀 |
| D9 | 模型是**固定文件**：`models/current/model.onnx` + `model.json`（`{name, run, created_at, sha256, bytes, classes:["question","answer"], imgsz, conf, dataset}`）。换模型 = publish 新文件、重启 `serve.py`；训练不会让线上模型悄悄变化 | 回答 T10；可复现、可回滚 |
| D10 | 训练脚本与面板之间只靠文件契约：`status.json`（`{state: running\|done\|failed, epoch, epochs, started_at, updated_at, epoch_seconds, pid, dataset, error?}`，每轮原子写——先写临时文件再 `os.replace`）；`metrics.jsonl`（每轮一行，含 epoch、各项 loss、val mAP50、mAP50-95、时长）；`eval.json`（模型与模板两组指标、逐图 IoU、overlays 清单）。`state=running` 但 pid 不存在、或 `updated_at` 超过 `max(3×epoch_seconds, 10 分钟)` 未更新 → 面板显示「已中断」 | 面板不控制训练进程，也不依赖 torch；只读几份小 JSON |
| D11 | 实时测试走检测服务，不在 OMRS 进程里加载模型 | 零依赖（T6）；与收件箱「AI 框选」同一路径，测到的就是上线后的效果 |
| D12 | 积累进标注集时状态为 `todo`，预填模型框；不新增「来源」字段，不改 `annotate.db` 表结构 | 未经人确认的模型框进训练集会自我强化错误（同基线记录里「未编辑 AI 框」的问题）；导出默认只含 done，现有机制就够 |
| D13 | 面板只读、不启动训练；开始／续训／重建数据集都以可复制命令呈现 | 数小时的 CPU 任务从网页启动，会和生产服务抢资源、进程生命周期也难管；用户没有要求网页里点训练 |

## 6. 边界情况

- **某张原图解码失败或尺寸与库记录不符：** 排除并记原因，不中断构建。
- **图的高宽比 ≤3：** `slice_plan` 返回整图一条，照常处理。
- **条带里没有任何框：** 作为负样本保留（空标签文件）。
- **近似图跨来源（标注集与收件箱各一份）：** 归同组，不跨集。
- **训练中断（会话结束、OOM、机器重启）：** 用 `--resume` 从 `last.pt` 续训；续训前核对数据版本与参数未变。
- **可用内存降到 2 GiB 以下：** 立即停训，batch 减半重来，记进记录。
- **模型对一张条带输出同类多个框：** 保留（NMS 后），由 `merge_strip_boxes` 与评估处理；评估里同类取与人工框 IoU 最高的一个，多余框计为误检。
- **服务收到非图片或损坏 dataURL：** 返回 400 JSON `{error}`；OMRS 侧会显示为单元失败，不影响其他图。
- **面板打开时训练目录还不存在／只有数据集没有实验／有实验没有 eval.json：** 各块独立显示空状态或「评估尚未运行」，不报错。
- **训练中 `status.json` 正被替换：** 原子写保证读不到半截；读到解析失败时本轮沿用上次结果、下次轮询再读。
- **同时开两个面板标签页：** 各自轮询，互不影响；积累开关以服务端配置为准，另一页刷新后同步。
- **实时测试连续点两次：** 第一次未返回前按钮为加载态，不重复提交。
- **实时测试的图是超长截图（高 > 10000）：** 条带数随之增加，照常处理；耗时写在结果里。
- **积累时标注集里已有同一张图：** 不新建、不覆盖框，提示已存在。

## 7. 修改范围

- **预计涉及：** 新增 `tools/boxdetect/`（`common.py`、`build_dataset.py`、`train.py`、`evaluate.py`、`publish.py`、`serve.py`、`README.md`、两个 requirements）、`tests/test_boxdetect.py`；新增 `omrs/trainpanel.py`、`assets/app/trainpanel.html`、`assets/app/features/trainpanel/`、`tests/test_trainpanel.py`、`tests/app/trainpanel.test.mjs`、`tests/e2e/trainpanel.py`；小改 `omrs/server.py`（两个分发分支）、`omrs/common.py`（两个配置键）、`assets/app/features/create/train-view.js` 与 `train.js`（入口一栏）、`tests/check_docs.py`（`ROUTE_METHODS`）；文档见 C5、C7；`AI/training/` 下 README、lessons、新实验记录；本计划 `progress.md`；任务日志；版本号相关文件。
- **明确不要修改：** `local_http` 协议与 `detect_regions_local`、`DETECT_PROMPT`、`omrs/inbox.py`、`omrs/annotate.py`（只调用现有函数）、标注页与 AI 训练工作区的现有内容、`错题/` 真实数据、生产配置与 systemd。
- **本次必须完成：** C1–C7 全部，含模板对照、模型整图指标、收件箱真实浏览器走通、训练面板五块与实时测试（含积累开关）真实浏览器走通。
- **可以顺手处理：** `AI/training/` 里与实测矛盾的文字订正（在日志说明）。
- **本次不要处理：** 面板里启动／停止训练或重建数据集的按钮、面板里校正框（校正去标注页）、多模型同时对比、标注页「AI 预框」、主动学习挑图、VLM 框选对比、补标那 4+1 张图、把服务做成 systemd、切换生产 `inbox_detect_provider`、调 `inbox_auto_ready_conf`、换更大模型或做超参搜索（只允许 §8 列出的一次补救尝试）、ai-draft 计划的任何内容。

## 8. 验收标准

1. `python3 tools/boxdetect/build_dataset.py --out …` 在只读源上成功；`错题/` 下文件修改时间无变化（构建前后 `find 错题/.omrs -newer <标记文件>` 为空）。
2. manifest 里 train/val/test 按组不相交，测试集 ≥ 15 张整图；排除清单与原因完整。
3. 实验记录含：模板基线与模型在**同一测试集**上的题目／答案各自 平均 IoU、IoU≥0.75 占比、「两框都 ≥0.75（整图无需修改）」占比；每轮耗时、总耗时、内存峰值；最佳权重 SHA-256。
4. **达标线（评估前固定，不得事后修改）：** 测试集上答案框 IoU≥0.75 占比 ≥ 80%，题目框 ≥ 90%，且两项都高于模板基线。未达标不算失败交付：按 §10 停止条件 3 做一次补救（输入 960 或延长轮数二选一），仍未达标就如实记录、给出原因分析和需要补多少样本的估计，并结束。
5. `serve.py` 起来后 `GET /health` 返回模型 SHA-256；`POST` 一张测试条带返回符合 D5 的 JSON。
6. 隔离 OMRS 实例里，收件箱「AI 框选」对测试图产生题目与答案框（真实浏览器截图存进任务日志引用的临时目录并描述）；服务停掉后界面给出错误提示、不卡住。
7. 全部现有门禁仍通过，计数不减；`tests/test_boxdetect.py` 在没有 torch/onnxruntime 的系统 Python 下通过。
8. 录入题目 → AI 训练工作区出现「训练面板」一栏，点「打开训练面板」在新标签页打开 `/train`；AI 训练工作区原有内容与行为不变（E2E 与视觉对比证明）。
9. 训练目录为空时面板显示空状态与上手命令；有真实训练时五块显示的数字与实验记录、`eval.json` 一致（截图 + 对照写进日志）。
10. 训练进行中打开面板，不刷新页面，新一轮结束后 10 秒内进度条与两张曲线都前进一格；把训练进程杀掉（E2E 用假 pid 模拟）后面板显示「已中断」和续训命令。
11. 实时测试：上传一张测试集原图，面板画出题目与答案框、显示置信度与耗时；耗时写进日志（CPU，不设硬阈值，但 6752 高的图超过 30 秒要在日志里分析原因）。检测服务停掉时显示「检测服务未启动」与启动命令，页面可继续操作。
12. 积累开关关：测试前后 `annotate.db` 行数与 `annotate/images/` 文件数不变，且无其他新文件（`find <临时 Vault> -newer <标记>` 只允许 `config.json` 以外为空）。积累开关开：标注集多一张 `todo` 图，框为模型框；再传同一张不新增、不改框；开关状态刷新页面后保持。
13. `check_ui.py`、`check_contrast.py`、`run_browser.py` 全绿；新页浅色与深色主题都看过（截图）。
14. 生产 OMRS 服务全程在线（训练前后各 `curl` 一次生产健康页只读检查，不重启）。

## 9. 验证步骤

```bash
# 门禁（系统 Python，每个提交都跑）
python3 -m unittest discover -s tests -p 'test_*.py' -q
node --test tests/app/*.test.mjs
python3 tests/check_docs.py --diff <上一个提交>

# 训练链路（训练 venv）
~/omrs-train/.venv/bin/python tools/boxdetect/build_dataset.py --vault 错题 --out ~/omrs-train/datasets/<版本>
~/omrs-train/.venv/bin/python tools/boxdetect/evaluate.py --dataset … --baseline template
nice -n 19 ~/omrs-train/.venv/bin/python tools/boxdetect/train.py --dataset … --epochs 3   # 冒烟
nice -n 19 ~/omrs-train/.venv/bin/python tools/boxdetect/train.py --dataset … [--resume]  # 正式，后台
~/omrs-train/.venv/bin/python tools/boxdetect/evaluate.py --dataset … --model …/model.onnx
```

```bash
# 面板（C5–C7）
python3 -m unittest tests.test_trainpanel -q
node --test tests/app/trainpanel.test.mjs
python3 tests/e2e/trainpanel.py
python3 tests/check_ui.py && python3 tests/check_contrast.py && python3 tests/app/run_browser.py
python3 tests/visual/run.py --ref <C6 提交>
python3 tests/e2e/create.py      # 入口改动后录入页不回归
python3 tests/e2e/annotate.py    # 积累写标注集后标注页不回归
```

命令名与参数可由执行者调整，但要在 `tools/boxdetect/README.md` 写成最终形态。真实浏览器一步（验收 6）用本机 playwright，按 `AI/environment.md` 的隔离实例配方起服务。

## 10. 执行原则

先读后改；以代码为准；实现可调，但目标、D1–D8、达标线和验收标准不改；复用 `omrs.inbox` 的纯函数，不复制一份。

**停止条件（未列出的一律继续）：**
1. 需要写真实 `错题/`（面板积累只在临时 Vault 验证）或改生产配置、systemd、生产端口才能继续。
2. 依赖装不上（无 CPU 版 torch 的 cp313 包等）：先试 `uv venv --python 3.12`；仍不行才停。
3. 冒烟显示正式训练预计超过 8 小时，或补救一次后仍未达标：记录后结束，不继续加码。
4. 开工时 `AI/training/` 仍是他人未提交的改动：问用户是否一并提交，得到答复前其余工作照做、只是不提交这些文件。

**中断恢复：** 训练在后台跑、日志写 `~/omrs-train/runs/<实验>/train.log`；会话结束前在 `progress.md` 状态块写清数据版本、运行目录、已跑轮数与恢复命令。下次先看 `git status`、`git log --oneline -10`、状态块，再 `--resume`。

**最终汇报（中文，五项）：** 提交清单；实际执行的验证与数字（模板 vs 模型对比表、面板截图位置）；未执行的验证与原因；遗留（含是否建议接入生产）；下一步（生产切换：部署新版本、常驻 `serve.py`、填 `inbox_local_detect_url`、按需把提供方切到 `local_http`——都待授权）。
