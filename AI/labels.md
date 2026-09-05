# 用户标记

> v1.14.0 新增。对应源文件：`omrs/labels.py`、`omrs/question_ops.py`、`omrs/projections.py`、`assets/labels.js`。

## 1. 概念边界

OMRS 里有三种容易混淆的题目标签：

| 层 | 内部字段 | UI 名称 | 来源 | 是否参与算法 |
|---|---|---|---|---|
| 状态 | `Current_Tag` / `tag` | 状态 | 反馈状态机 | 是 |
| 知识点 | `Knowledge_Tags` / `knowledge_tags` | 知识点 | 人工或 AI | 否，供筛选和统计 |
| 用户标记 | `Labels` / `labels` | 标记 | 用户 | 默认否，可配置优先级加成 |

标记用于横切组织题目，例如「考前必看」「计算失误」「压轴」。它不替换
`Current_Tag`，也不改变状态机。

## 2. 标记定义 `labels.json`

路径：`错题/.omrs/labels.json`。

```json
{
  "version": 1,
  "labels": [{
    "id": "LB-20260904-a1b2c3",
    "name": "考前必看",
    "color": "#dc2626",
    "order": 1,
    "priority_bonus": 0.0,
    "archived": false,
    "created_at": "2026-09-04T12:00:00+00:00"
  }]
}
```

- `id` 是定义的内部稳定标识；题目 Markdown 不保存 id，而保存可读的名字。
- `name` 最长 80 个字符，不能含换行或 `|`；定义名称必须唯一。
- `color` 规范化为 `#rrggbb`。前端 soft 变体用原色生成淡底 + 按主题钳亮度后的同色文字，solid 变体用原色实底。
- `order` 控制管理页和选择器顺序；`priority_bonus` 为 `0–1` 的可选调度加成。
- `archived` 的定义不会出现在常规列表和选择器中；当前管理 API 删除定义而不是保留归档记录。

写入使用临时文件、`fsync` 和 `os.replace`，但 `labels.json` 当前没有像 CSV/展示板
那样的滚动 `.bak.1/2/3` 文件。

## 3. 题目 YAML 与投影链

题目 Markdown 直接保存名字：

```yaml
标记:
  - 考前必看
  - 计算失误
```

`标记: []` 表示显式清空。`metadata_hash()` 将标记纳入结构化字段，因此链路为：

```text
Markdown 标记:
  └─ scan_workspace()
       └─ question.metadata_update_external
            └─ question_projection + question_labels
                 └─ mastery_data.csv 的 Labels 列
```

网页上的单题修改先原子重写 Markdown，再触发扫描；内容没有变化时不产生重复
metadata commit。批量操作会逐题写入，完成后统一扫描投影。

`ledger.db` 的 `question_labels(question_id, label)` 是查询投影，不是另一份事实源；
删除并重建投影时会从题目元数据重新生成。`mastery_data.csv` 的 `Labels` 使用 `|`
分隔，旧 CSV 缺列时按空标记兼容。

## 4. HTTP API

| 方法 | 路径 | 请求/结果 |
|---|---|---|
| GET | `/api/labels` | 返回未归档定义，并附 `count`（引用该标记的题目数） |
| POST | `/api/label/save` | `{id?, name, color?, priority_bonus?, order?}`；无 `id` 新建，有 `id` 更新，改名级联重写题目 YAML |
| POST | `/api/label/delete` | `{id, detach?: true}`；默认先从题目 YAML 移除引用，再删除定义 |
| POST | `/api/label/merge` | `{from, into}`；把源标记并入目标、去重引用并删除源定义 |
| POST | `/api/question/labels` | `{uid, labels: [...]}`，覆盖单题标记 |
| POST | `/api/questions/labels` | `{uids: [...], add: [...], remove: [...]}`，批量添加/移除 |

`/api/stats`、`/api/question`、`/api/analytics` 和推荐/导出相关数据都提供题目的
`labels`。`/api/recommend` 接受可重复的 `label=` 参数，多个参数按 OR 过滤。

## 5. 前端组件

`assets/labels.js`（排在 `core.js` 之后、`questions.js` 之前）提供：

- `lblChip(labelOrName, {variant, lg, dim})` / `lblChips(names, {add, max, uid, lg, variant})`：
  `<=>` 双尖形芯片。三种变体：默认 **soft**（原色 16%/24% 淡底 + 同色相钳亮度文字，列表 /
  抽屉 / 反馈用）、**solid**（原色实底 + 按相对亮度选黑白文字，管理弹层用）、**print**（15px，
  导出用）。尺寸 18px / `lg` 20px / `print` 15px。`add:true` 追加「＋ 标记」入口，`max` 折叠为
  「+N」，`uid` 时外包 `<span class="lbl-row" data-lbl-target=uid>` 交给委托打开 picker。
- `lblInk(hex, theme)`：按主题只钳同色相的亮度，保证淡底上的小字达到 WCAG AA；`labelFg()`
  给 solid 变体选文字色。用户保存的 `color` 永远不变。
- `openLabelPicker(uid, anchor, {get, onSave, title})`：搜索 / ↑↓ / Space·Enter 切换 / 输入新名回车
  创建并选中 / 最近标记快速加 / Esc 关闭；点「完成」才保存（乐观更新 + 失败回滚 + toast）。
  题库 / Modal / 反馈 / 录入 / 收件箱 / 展示板共用，点任意带 `data-lbl-target` 的芯片区都能打开。
- `openLabelManager()`：管理弹层——行内编辑（名称 / 10 色预设 + 自定义色 / 调度加成）、合并到
  另一标记、删除（从题目 YAML 摘除）、新建；改名 / 合并后 `reloadData()` 刷新全站。
- 标记筛选 chips：`renderLabelFilterOptions(prefix)` 渲染到 `#<prefix>-label-filter-list`，选中
  状态存在隐藏 `#<prefix>-filter-labels`（`|` 分隔），`q / rec / pick / inst` 四处共用，
  `q-label-mode` 决定 any / all。
- 录入表单的标记字段（`renderCreateLabels` / `selectedCreateLabels`）、单题覆盖保存
  `saveQuestionLabels`、批量 `batchAddRemoveLabels`。

题库的筛选状态仍由 `getFilterState()` 统一读取；标记名称也参与全文搜索。
标记管理中的改名、删除和合并属于真实的批量 Markdown 编辑，前端会提示影响范围。

## 6. 统计与调度

数据复盘新增 `accuracy.by_label`。一题有多个标记时，一次复习会分别计入每个标记，
因此这是有意的重叠统计，不是互斥分类。每个条目包含：

```json
{
  "label": "计算失误",
  "questions": 12,
  "reviews": 38,
  "correct": 21,
  "wrong": 17,
  "accuracy": 0.553,
  "avg_score": 6.21
}
```

仪表盘另有「标记分布」卡片，统计活动题目中每个标记的题数。

标记默认不影响调度。定义上的 `priority_bonus` 大于 0 时，
`compute_priority()` 才加入所有题目标记加成之和，并以 `label_bonus_cap=1.0`
（可调）封顶。具体公式和 tuning 表见 `algorithm.md`。

## 7. 维护边界

- 标记名字写入 YAML 是为了让 Obsidian 可读、可编辑；因此改名必须级联写 N 个文件。
- 标记定义不进入 Ledger；题目标记变化通过题目 metadata update 进入 Ledger。
- `labels.json` 与题目 Markdown 一起属于 `.omrs`/题库数据，备份会随 `错题/` 打包。
- 批量改名、删除和合并在当前单线程文件写入模型下可能阻塞请求，风险记录在
  `optimization.md`。
