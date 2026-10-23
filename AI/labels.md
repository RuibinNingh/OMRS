# 用户标记

> **速查**
> - 职责：用户标记定义、题目 YAML `标记:`、投影与可选调度加成
> - 入口：`omrs/labels.py`、`omrs/question_ops.py`、`assets/app/domain/labels/index.js`
> - 不变量：标记定义存 `labels.json`，题目只通过 YAML 引用标记值
> - 必跑测试：`tests/test_labels.py`、`tests/test_label_plan.py`、`tests/test_label_plan_recovery.py`、`tests/e2e/label_plans.py`、`tests/app/labels.test.mjs`
> - 相关：`AI/frontend/library.md`、`AI/algorithm.md`

> 对应源文件：`omrs/labels.py`、`omrs/question_ops.py`、`omrs/projections.py`、`assets/app/domain/labels/index.js`。

## 1. 概念边界

OMRS 里有三种容易混淆的题目标签：

| 层 | 内部字段 | UI 名称 | 来源 | 是否参与算法 |
|---|---|---|---|---|
| 状态 | `Current_Tag` / `tag` | 状态 | 反馈状态机 | 是 |
| 知识点 | `Knowledge_Tags` / `knowledge_tags` | 知识点 | 人工或 AI | 否，供筛选和统计 |
| 用户标记 | `Labels` / `labels` | 标记 | 用户或经批准的 AI | 默认否，可配置优先级加成 |

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

网页上的单题修改先原子重写 Markdown，再立即扫描入账；内容没有变化时不产生重复提交。定义级联与 AI 整理在同一 Ledger 事务中记录逐题原生事实和批次审计，再发布投影。Obsidian 外部编辑仍由扫描入账。

创建与列表改写使用JSON字符串编码生成YAML双引号值，完整转义反斜杠、引号和控制字符；知识点双链同样处理。定义、Markdown重读、扫描投影及标记计数保留同一原始名称，回归见 `tests/test_labels.py`。

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
| POST | `/api/question/labels` | 优先 `{question_id, labels: [...]}`，覆盖单题标记；旧 `uid` 兼容 |
| POST | `/api/questions/labels` | 优先 `{question_refs: [{question_id}], add: [...], remove: [...]}`，批量添加／移除；旧 `uids` 兼容 |

`/api/stats`、`/api/question`、`/api/analytics` 和推荐/导出相关数据都提供题目的
`labels`。`/api/recommend` 接受可重复的 `label=` 参数，多个参数按 OR 过滤。

## 5. 前端组件

`assets/app/domain/labels/index.js` 是原生 ES Module 聚合入口；芯片、颜色、状态、选择器和管理对话框分别由同目录子模块实现。

- `labelChip(labelOrName, options)` / `labelChips(names, options)` 把 `chipHtml()` / `chipsHtml()` 字符串模板包装为 `raw()` 片段。芯片为 `<=>` 双尖形，支持 soft / solid / print；高度分别为默认 20px、`lg` 24px、`print` 18px。`add`、`max`、`uid` 选项控制添加入口、折叠与委托目标。颜色写 `data-lbl-c`，由 `sheet.js` 登记样式规则。
- `lblInk(hex, theme)` 按主题钳同色相亮度，`labelFg()` 为 solid 选择文字色；用户保存的 `color` 不变。
- `openLabelPicker(uid, anchor)` 为已有题打开选择器；`openCreateLabelPicker(anchor, {get, onSave})` 为录入表单复用选择器。底层 `picker.js` 还接收自定义 `get` / `onSave` / `title`。支持搜索、键盘切换、创建、最近标记与 Esc；点「完成」才保存，失败回滚并提示。
- `openLabelManager()` 管理名称、颜色、调度加成、合并、删除与新建；改名、删除和合并提示影响范围，并重载全站数据。
- 筛选状态由各页面的 controller / state 持有，条件交给 `domain/items.js` 的 `filterItems()`；名称也参与全文搜索。
- `state.js` 的 `saveQuestionLabels()` 与 `batchLabels()` 负责单题和批量写入；`refreshLabelViews()` 失效题面缓存，并通知标记、题库、调度、反馈和展示板重绘。

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
- 标记定义仍以 JSON 为当前读取格式；整批写入在 Ledger 保存审计事实和定义前后撤销材料，题目标记变化以原生 metadata update 入账。
- `labels.json` 与题目 Markdown 一起属于 `.omrs`/题库数据，备份会随 `错题/` 打包。
- 批次替换和恢复期间标签与题面读取经过一致性屏障；其它业务的写锁占用不阻塞普通统计读取。


## 审计修复契约

标记查询从 SQL 读模型取得题目归属，CSV 只用于首次迁移与按需导出。定义文件和 Markdown 级联的入口参与 Vault 生命周期屏障，恢复期间不能跨目录交换写入。标签变更只更新实际元数据差异，不覆盖学习状态，见 `AI/ledger.md`。

## 标记整理批次

标记创建、编辑、合并与删除使用 `omrs/label_plan.py` 编译和 `omrs/label_plan_journal.py` 整批写入。定义与全部活动题目（含停用）的引用一起替换；故障提交前整体回滚，提交后以 Ledger 原生回执为准。未扫描的外部题目修改会拒绝，要求先扫描。

## 整批标记归类

预览列出全部级联题目与各科目题数，跨范围操作默认不执行。发现有相关标记引用的未扫描新文件或未扫描题目修改时拒绝，先扫描再提案，避免遗漏新增引用。

撤销预览列出定义名称、颜色、排序与逐题归属的逆变更。除已扫描的新引用外，相关未扫描新文件也会阻止撤销，原定义、题目与 Ledger 不变；扫描后重新预览。
