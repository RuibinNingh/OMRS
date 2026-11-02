# 记忆算法

> **速查**
> - 职责：记忆衰减、熟练度状态机、统一调度优先级、SM-2、五档复核、双列表推荐与 Leech 检测
> - 入口：`omrs/scheduling.py`、`omrs/common.py`（`DEFAULT_TUNING`）
> - 不变量：反馈先写 Ledger，再由投影重放出熟练度；反馈响应、增量投影、历史重放与助手预览共用纯转换；调参立即按当前参数重算全部历史
> - 必跑测试：`tests/test_recommendations.py`、`tests/test_leech_streak.py`、`tests/test_revive_cycle.py`、`tests/test_schedule_workbench.py`、`tests/test_data_runtime.py`
> - 相关：`AI/ledger.md`、`AI/data.md`

> 对应源文件：`omrs/scheduling.py`

> 反馈事件先写 Ledger，再通过 `scheduling.transition_review()` 更新 SQL 熟练度、EF、状态标签和 SM-2。CSV 只按需导出；统计、推荐和 Session 读取 SQL。

---

## 1. 时间衰减 `time_decay(mastery, days_since, factor=30, base=5)`

```
decayed = mastery × e^( -days / (mastery×factor + base) )
```

- **衰减常数**随熟练度升高而增大，熟练度越高衰减越慢。
- `mastery = 0` 时直接返回 `0.0`。
- 按默认 `factor=30`、`base=5`：mastery=0.9 时 30 天后约为 0.352；mastery=0.3 时 30 天后约为 0.035。
- `factor`/`base` 默认 `30`/`5`，可经活动配置的 `tuning`（`decay_mastery_factor`/`decay_base`）覆盖，见 §9。

---

## 2. 熟练度更新 `compute_mastery_update(old_m, ef, sub_score, is_correct, attempts, high_correct_streak)`

### 主观分语义
- 分值范围：0–10，**越大越熟练**（与前端评分控件一致）。
- 阈值：`sub_score >= high_score_threshold`（默认 7）视为高分（自信/熟练）。

### 状态机

| 条件 | 标签 | 新熟练度 | tag_action |
|---|---|---|---|
| 高分 AND 答对 | 已击杀 | 1.0 | `kill` |
| 低分 AND 答对 | 磨合中 | `min(0.95, old_m + sub_score/30 × ef/2.5)` | `keep` |
| 高分 AND 答错 | 粗心/陷阱 | `old_m × 0.8` | `trap` |
| 低分 AND 答错 | 真不会 | `old_m × 0.3` | `lock` |

一次高分答对立即击杀；分数与对错缺一不可，默认6分答对、7分答错均不能击杀。非击杀态熟练度上限0.95，低分累积不能绕过击杀判定。

`High_Correct_Streak` 保留连续高分答对计数，仅供调试，不决定击杀或复核排期。低分答对或任意答错清零。

### 易错因子（EF）更新
- `attempts < ef_cold_attempts`（默认 3，冷启动期）：不更新 EF。
- 高分 AND 答对：`EF = min(3.0, EF + ef_up)`（默认 `+0.15`）
- 答错：`EF = max(1.3, EF - ef_down)`（默认 `-0.2`）
- 低分 AND 答对：EF 不变。

> 上述阈值/增量均可经 `tuning` 覆盖（`high_score_threshold`/`ef_cold_attempts`/`ef_up`/`ef_down`），见 §9。

---

## 3. 调度优先级 `compute_priority(decayed_mastery, ef, days, tag, mastery, wrong_streak=0, tuning=None, labels=None, label_bonuses=None)`

> 统一公式，集中在 `scheduling.py`。此前在 `schedule_questions()`、`generate_recommendations()`、`stats.py` 各写一份，已合并，避免三处逻辑漂移。

```
priority = (1 - decayed_mastery) × (eff_diff/10) + (days/60) × 0.3
```

- **`eff_diff` 不再是静态 `Difficulty` 字段**，而是由 EF 反推的「有效难度」（见 §3.1）。`Difficulty` 仍保留在 CSV / 展示 / 导出，可由人工或 AI 在录入时设为 1–10；但它只是静态初始估计，不会随复习表现自适应，因此不再喂给优先级公式。真正自适应的是 EF。

额外加成：
- 标签含 `待攻克` 且 `mastery < attack_mastery_threshold`（默认 0.3）：`priority += attack_bonus`（默认 0.5）
- **leech（顽固题）**：`wrong_streak >= leech_fail_threshold`（默认 3）且未击杀：`priority += leech_priority_bonus`（默认 0.4），见 §10
- **复燃题**：已击杀且休眠够久（§11）：`priority += revive_priority_bonus`（默认 0.3），保证从熟练度列表被召回时也排在前面

`60`/`0.3` 即 `priority_days_divisor`/`priority_days_weight`，连同上述加成阈值均可经 `tuning` 覆盖，见 §9。

### 3.2 用户标记加成（v1.14.0，可选）

题目上的用户标记不改变状态机，也不默认参与调度。只有标记定义的
`priority_bonus` 设置为正数时，`compute_priority()` 才加入：

```text
label_bonus = clamp(
    Σ max(0, priority_bonus[题目上的每个标记]),
    0,
    label_bonus_cap
)
```

默认 `priority_bonus=0.0`，因此不改变 v1.13.0 的推荐顺序。总加成默认由
`label_bonus_cap=1.0` 封顶；标记定义、调度推荐和题目条目的连接方式见
`labels.md`。

排序：降序，取前 `count` 条。

### 3.1 有效难度 `ef_to_difficulty(ef)`

```
eff_diff = clamp( 1 + (3.0 - ef)/(3.0-1.3) × 9, 1, 10 )
```

EF 越低 = 越不稳定 = 越难 = 权重越高。EF=3.0→难度 1，EF=1.3→难度 10，EF=2.5（新题默认）→约 3.65。

### 关键约束
- 已击杀题目**不设**熟练度下限（早期版本有 `max(mastery, 0.85)` 的错误下限，已删除）。
- 常规调度会跳过 `#状态/已击杀` 或 `Mastery = 1.0` 的题目，但**不是永久跳过**：休眠达到复燃周期（§11）后会重新进入调度。复燃题答错则降级回 `#状态/待攻克`（§4），立即回到推荐前面。
- **停用题目**（兼容投影 `Suspended = 1`）不会进入常规调度、双列表推荐、行动计划或反馈录入；恢复后沿用原有熟练度与 Due_Date 重新参与。手动按 UID 确认调度遇到停用题也会被后端拒绝；已有活动 Session 的停用题会从待反馈接口中隐藏，原始 Session 仍保留供审计。
- 新建 Session 和 `/api/recommend` 推荐时都会排除仍处于 `active` 状态的旧 Session 题目，避免连续创建或确认重复调度同一批题。
- `count < 0` 会按 `0` 处理；旧迁移输入中的异常数值会回退到安全默认值，避免整次调度失败。
- 日期解析使用 `parse_date()`（见 `common.py`），兼容 `YYYY-MM-DD` 和 `YYYY/M/D`；解析失败按 30 天处理。

---

## 4. 已击杀状态回退规则

唯一反馈转换 `transition_review()` 同时处理状态与排期：已击杀题答错回到 `#状态/待攻克`，复核档位归零、周期起始日清空，`repetition=0`，1天后重练。熟练度为 `min(状态机结果, 答错前 mastery × kill_demote_factor)`，默认0.3；取最小值避免低分答错的状态机惩罚再次连乘。

已击杀题低分答对也退出击杀，结果显示「磨合中」；熟练度最高0.95，复核档位及周期起始日清零，`repetition=0`，3天后巩固。累计 `kill_count` 均保留。退出后一次高分答对可重新击杀，从第1档7天起步，累计成绩不会拉长新周期。

v1.1.0 起 Markdown 文件内的 `tags` 不再被反馈流程回写（早期 `feedback.py::_writeback_md()` 已随 Ledger 架构移除）：结构化标签的唯一事实源是 Ledger 投影，Markdown YAML 只作为输入——外部人工改动由工作区自检以 `question.metadata_update_external` 记录。因此 Obsidian 中看到的 YAML 标签可能与投影标签不一致，属设计边界（详见 `ledger.md` §3）。

目的：防止调度持续低估已回退题目的复习优先级。

---

## 5. `_row_to_item()` — 题库条目转换

从 SQL 兼容列行转为统一的题目对象，供 `/api/stats` 和临时调度使用。

- `decayed_mastery`：以当日为基准计算衰减值。
- `interval`、`due_date`、`repetition`：实际间隔、下次复习日与连续答对次数；普通题用SM-2，击杀题用分档复核。
- `_source`：推荐来源标记（`due` / `proficiency`），仅在推荐/确认流程中赋值。
- 日期解析失败时：`days = 0`（列表视图语义：今天刚看过）。
- `high_correct_streak`：连续高分答对次数，仅供调试。
- `kill_count`：累计击杀次数（来源 `mastery_projection.kill_count`，老 CSV 缺 `Kill_Count` 列按 0 处理）。仅表示累计成绩，不参与排期。
- `entry_date` / `created_at`：题目录入日期与 Ledger 首次创建时间，供题库和助手检索排序使用；不参与熟练度或推荐优先级计算。
- `revive_stage` / `revive_anchor_at`：复核档位（普通题0，击杀题1–5）及本周期起始业务日期；提前练习不改起始日。
- `is_revived` / `dormant_days` / `next_revive_date`：是否已到实际复核日、当前档的配置间隔、实际复核日期。非击杀态间隔为0、日期为空。无可靠日期的旧击杀题 `is_revived=true`、日期为空，表示「待复核」。


---

## 6. SM-2 间隔排期 `calc_sm2_interval()`

> 对应源文件：`omrs/common.py`

普通题低分答对、答错沿用 SM-2；击杀与降级由§4、§11覆盖排期，不受来源折中系数影响。标准 SM-2 间隔计算，基于 Repetition（连续答对次数）：

| Repetition | 间隔 |
|---|---|
| 0（答错或首次） | 1 天 |
| 1 | 6 天 |
| ≥ 2 | `old_interval × EF` |

**来源差异化（折中方案）：**

| 来源 | 答对 | 答错 |
|---|---|---|
| `due`（到期列表） | 标准 SM-2 全量更新 | 重置 Repetition=0, Interval=1 |
| `proficiency`（熟练度列表） | 间隔 × 0.7 折中系数 | 同到期（重置） |

设计理由：提前练习（熟练度列表选题，Due_Date > 今天）答对不能充分证明长期记忆，故用 0.7 系数保守增长。答错则说明比预判更薄弱，理应紧急召回。

---

## 7. 双列表推荐 `generate_recommendations()`

> 对应源文件：`omrs/scheduling.py`  
> API 端点：`/api/recommend`

后端调用 `/api/recommend` 时会传入当前 active Session 的 UID 排除集；若前端 stale 或手工请求在 `/api/confirm-schedule` 中提交了已被 active Session 占用的 UID，确认阶段会拒绝创建重复 Session。

`due_count` 与 `prof_count` 会先转换为整数并钳制到不小于 `0`；负数按 `0` 处理，避免 Python 负切片意外返回大批题目。推荐数量为零时对应列表为空。

### 互斥分配逻辑

```
1. 遍历未停用题；跳过未到复核日的击杀题，到期或无可靠日期的击杀题重新入列
2. 先按可选筛选项裁剪：科目 `subject`、分类 `category`、知识点 `knowledge_tag`、
   用户标记 `label`（可重复；label_mode=any为任一命中，all为全部命中）
3. Due_Date ≤ 今天（或日期缺失/无效）→ 到期列表
4. Due_Date > 今天 → 熟练度列表
```

两道列表天然不重复。

标记匹配在排序及due_count／prof_count截断前完成，防止先截断的任一命中候选挤掉真正全部命中的题；label_mode默认any，非法值拒绝。

active Session 的排除集合只依据持久化记录的 `Status == "active"`；Session 不会因为创建时间超过固定天数而被隐式视为过期，必须通过正常反馈完成或显式撤销改变状态。

### 到期列表排序

1. 已逾期（Due_Date < 今天）排最前面
2. 今日到期排第二
3. 按 EF 升序（EF 越低越不稳定，越优先）

### 熟练度列表排序

推荐接口返回的顺序是复习工作台的基础顺序；前端均衡模式只在该顺序内按科目轮选，不重新计算一套优先级。列表条目的 `_source`、`due_date`、`mastery` 和 `_overdue_days` 来自后端投影，避免浏览器依据本地日期或静态字段推断推荐原因。用户标记筛选支持任一或全部匹配，难度/熟练度范围和到期状态筛选只裁剪候选，不改变后端排序。

按统一优先级公式（`compute_priority()`，见 §3）降序，含 leech 加成：

```
priority = (1 - decayed_mastery) × (eff_diff/10) + (days/60) × 0.3
```

待攻克且 mastery < 0.3 额外 +0.5；leech 额外 +0.4。标记定义存在正
`priority_bonus` 时再加 `label_bonus`，并受 `label_bonus_cap` 封顶；缺省均为
0，不影响未配置标记的题目。

---

## 8. 反馈闭环中的 SM-2 更新

> 对应源文件：`omrs/feedback.py`、`omrs/projections.py`

反馈提交后：
1. `POST /api/feedback` 解析并校验反馈，在 SQLite 写事务内重新核对链头、投影检查点和当前算法参数；其它进程已经更新时先重建再重试。
2. 在同一事务追加 `review.batch_submit` 并增量发布 SQL 读模型，记录 `question_id`、当时 UID、来源、分数、对错、备注和时间；发布失败整体回滚，并废止已修改的进程缓存。
3. 投影与助手预览共用纯 `transition_review()`，同批同题按顺序转换；反馈响应直接采用本次已发布投影的结果，避免另算一套状态。
4. 不逐次生成 CSV；持久化 Session 的完成检查在反馈事务提交后执行。
5. UTC 时间戳保留时区，反馈、统计和排期通过 `common.business_time()`／`business_today()` 按 Asia/Shanghai 业务日期一致计算。使用系统 IANA 时区规则；缺少数据库时，仅上海 1992 年起的时间使用有名 UTC+08 固定偏移，无需额外安装依赖。更早历史或其它缺失时区明确报告无法可靠转换，历史投影保留原时间，不猜夏令时。长期连续正确的间隔以日期可表示上限夹紧，最晚到期和复燃日期为 `9999-12-31`，完整重放不因日期溢出失败。
6. 撤销 Session、撤销/替换/恢复旧反馈时，不写逆向补丁，而是从有效事件流重新计算相关算法状态。

临时/即时练习可传 `source=instant|manual|due|proficiency`；持久化 Session 反馈优先采用 Session 中保存的来源。

---

## 9. 可调参数 tuning

> 对应源文件：`omrs/common.py` → `DEFAULT_TUNING` / `load_tuning()`

默认参数集中在 `DEFAULT_TUNING`，活动配置的 `tuning` 只需列出覆盖项。`save_config()` 验证完整候选，在同一 SQLite 事务内重算全部有效历史并发布投影、policy hash、revision 与配置；成功返回时新算法状态立即可见。调参不冻结旧反馈参数，后续修正和 `state.restore` 同样使用当前参数。`config.json` 是镜像，手改须在下次启动通过同一发布路径导入；运行时不靠文件缓存决定算法。

| 键 | 默认 | 含义 |
|---|---|---|
| `decay_mastery_factor` / `decay_base` | 30 / 5 | 时间衰减常数（§1） |
| `high_score_threshold` | 7 | 高分阈值（§2） |
| `revive_intervals_days` | [7,21,60,120,180] | 五档复核间隔，五个严格递增正整数（§11） |
| `ef_cold_attempts` | 3 | EF 冷启动冻结门槛（§2） |
| `ef_up` / `ef_down` | 0.15 / 0.2 | EF 增/减量（§2） |
| `priority_days_divisor` / `priority_days_weight` | 60 / 0.3 | 优先级时间项（§3） |
| `attack_bonus` / `attack_mastery_threshold` | 0.5 / 0.3 | 待攻克加成（§3） |
| `proficiency_factor` | 0.7 | 熟练度来源答对的间隔折中系数（§6） |
| `leech_fail_threshold` / `leech_priority_bonus` | 3 / 0.4 | 连续答错判定与加成（§10） |
| `revive_priority_bonus` | 0.3 | 复燃题的优先级加成（§11） |
| `kill_demote_factor` | 0.3 | 复燃后答错的熟练度降级系数（§4） |
| `label_bonus_cap` | 1.0 | 同一题所有用户标记 `priority_bonus` 的加成上限（§3.2）；默认标记加成仍为 0 |

`config.json` 示例：

```json
{
  "allow_external": false,
  "tuning": { "revive_intervals_days": [7,21,60,120,180], "leech_fail_threshold": 5 }
}
```

旧 `kill_streak`、`revive_decay_threshold`、`revive_tier_multiplier` 兼容读取但不生效，保存时从配置中清理。复核数组必须恰有五个严格递增的正整数，拒绝布尔、浮点、重复、零及负数。

校验：拒绝未知键、布尔冒充数字、NaN/Infinity、错误整数类型、负值与危险分母/系数范围。提交前重放失败时活动配置和学习状态保持旧值；镜像失败时新状态已生效并返回 `mirror_pending:true`。

---

## 10. Leech（顽固题）检测

> 对应源文件：`omrs/scheduling.py` → `build_fail_counts()` / `build_wrong_streaks()` / `is_leech()`

利用由 Ledger 重建的兼容投影 `history_log.csv`：按记录顺序统计每道题末尾的连续答错次数（`Is_Correct == 0`）；一次答对（`Is_Correct == 1`）即清零。累计答错次数仍单独统计为 `fail_count`。有稳定 `Question_ID` 时按当前 UID 归属历史记录。当前调度和统计读取该投影，而非题目 Markdown `# 历史`。

- **判定**：未击杀，且最近**连续**答错次数 ≥ `leech_fail_threshold`（默认 3）→ 标记为 leech；答对后立即解除。
- **优先级加成**：leech 在熟练度列表的 `compute_priority` 上 `+leech_priority_bonus`（默认 0.4），优先被召回。
- **暴露位置**：`/api/recommend`、`/api/stats` 与 `/api/analytics` 的题目条目带 `fail_count`（累计答错）、`wrong_streak`（最近连错）和 `is_leech`；`/api/stats` 的 `review_alert.leech` 给出未击杀 leech 总数。
- **用途**：提示「反复错的题」值得重新拆解/整理，而非继续机械重刷。

---

## 11. 已击杀题分档复核

> 对应源文件：`omrs/scheduling.py` → `review_cycle()` / `transition_review()` / `is_revive_eligible()`

| 事件 | 复核档位 | 下次复习 |
|---|---|---|
| 首次或重新高分击杀 | 第1档 | 本次日期加7天 |
| 第1档到期高分通过 | 第2档 | 本次日期加21天 |
| 第2档到期高分通过 | 第3档 | 本次日期加60天 |
| 第3档到期高分通过 | 第4档 | 本次日期加120天 |
| 第4、5档到期高分通过 | 第5档 | 本次日期加180天 |
| 提前或同日高分练习 | 保持原档 | 保持原定日期和周期起始日 |

间隔来自 `revive_intervals_days`。每次到期成功只升一级，逾期很久也不跳档；新周期从实际复核成功日计算。`last_review_at` 可随提前练习更新，`revive_anchor_at` 与 `due_date` 独立保存。累计击杀次数仅在首次／重新击杀及到期高分通过时加1，提前练习不增加；即使到达日期上限，同日起始的周期也不能重复晋级。

`is_revive_eligible()` 对非击杀态返回False；击杀态比较实际 `due_date` 与业务日期。到期题进入推荐、今日待复习及逾期提醒，获得 `revive_priority_bonus`。休眠题不进入常规推荐，其未来复核日期仍计入到期预测。停用题始终排除。

升级采用 `ledger-v4` 投影，以当前参数重放全部有效反馈，不改写原始Ledger。只有旧导入快照的击杀题从第1档迁移，有效最后复习日加第1档间隔；无可靠日期时保持日期为空，标为「待复核」并纳入队列，首次高分后从第1档起步。周期规范化由 `review_cycle()` / `resolve_review_fields()` 共用；重放失败时旧活动配置和投影整体保留。

题库、题目详情和复习调度共用 `domain/question/review-cycle.js`，统一档位与实际日期；题库和调度的提示还显示间隔及独立的累计击杀成绩。反馈结果显示本次状态、档位及下次复习日期，避免从最后练习日推算排期。
