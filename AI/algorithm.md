# 记忆算法

> 对应源文件：`omrs/scheduling.py`

---

## 1. 时间衰减 `time_decay(mastery, days_since, factor=30, base=5)`

```
decayed = mastery × e^( -days / (mastery×factor + base) )
```

- **衰减常数**随熟练度升高而增大，熟练度越高衰减越慢。
- `mastery = 0` 时直接返回 `0.0`。
- 例：mastery=0.9，30天后衰减到约 0.70；mastery=0.3，30天后衰减到约 0.16。
- `factor`/`base` 默认 `30`/`5`，可经 `config.json` 的 `tuning`（`decay_mastery_factor`/`decay_base`）覆盖，见 §10。

---

## 2. 熟练度更新 `compute_mastery_update(old_m, ef, sub_score, is_correct, attempts, high_correct_streak)`

### 主观分语义
- 分值范围：0–10，**越大越熟练**（与前端评分控件一致）。
- 阈值：`sub_score >= high_score_threshold`（默认 7）视为高分（自信/熟练）。

### 状态机

| 条件 | 标签 | 新熟练度 | tag_action |
|---|---|---|---|
| 高分 AND 答对 AND 已达 `kill_streak-1` 次连续高分答对 | 已击杀 | 1.0 | `kill` |
| 高分 AND 答对 AND 尚未连续确认 | 高分待确认 | `min(0.95, old_m + sub_score/20 × ef/2.5)` | `keep` |
| 低分 AND 答对 | 磨合中 | `min(1, old_m + sub_score/30 × ef/2.5)` | `keep` |
| 高分 AND 答错 | 粗心/陷阱 | `old_m × 0.8` | `trap` |
| 低分 AND 答错 | 真不会 | `old_m × 0.3` | `lock` |

### 高分确认计数
- `High_Correct_Streak` 记录连续高分答对次数。
- 高分答对会令计数 `+1`；达到 `kill_streak`（默认 2）次才进入 `已击杀`。
- 低分答对或任意答错都会将计数重置为 `0`，避免一次偶然高分直接击杀。

### 易错因子（EF）更新
- `attempts < ef_cold_attempts`（默认 3，冷启动期）：不更新 EF。
- 高分 AND 答对：`EF = min(3.0, EF + ef_up)`（默认 `+0.15`）
- 答错：`EF = max(1.3, EF - ef_down)`（默认 `-0.2`）
- 低分 AND 答对：EF 不变。

> 上述阈值/增量均可经 `tuning` 覆盖（`high_score_threshold`/`kill_streak`/`ef_cold_attempts`/`ef_up`/`ef_down`），见 §10。

---

## 3. 调度优先级 `compute_priority(decayed_mastery, ef, days, tag, mastery, fail_count=0, tuning=None)`

> 统一公式，集中在 `scheduling.py`。此前在 `schedule_questions()`、`generate_recommendations()`、`stats.py` 各写一份，已合并，避免三处逻辑漂移。

```
priority = (1 - decayed_mastery) × (eff_diff/10) + (days/60) × 0.3
```

- **`eff_diff` 不再是静态 `Difficulty` 字段**，而是由 EF 反推的「有效难度」（见 §3.1）。`Difficulty` 仍保留在 CSV / 展示 / 导出，但不再喂给优先级公式——因为它恒为 5、从不随表现变化，只会向优先级灌噪声。真正自适应的是 EF。

额外加成：
- 标签含 `待攻克` 且 `mastery < attack_mastery_threshold`（默认 0.3）：`priority += attack_bonus`（默认 0.5）
- **leech（顽固题）**：`fail_count >= leech_fail_threshold`（默认 4）且未击杀：`priority += leech_priority_bonus`（默认 0.4），见 §11

`60`/`0.3` 即 `priority_days_divisor`/`priority_days_weight`，连同上述加成阈值均可经 `tuning` 覆盖，见 §10。

排序：降序，取前 `count` 条。

### 3.1 有效难度 `ef_to_difficulty(ef)`

```
eff_diff = clamp( 1 + (3.0 - ef)/(3.0-1.3) × 9, 1, 10 )
```

EF 越低 = 越不稳定 = 越难 = 权重越高。EF=3.0→难度 1，EF=1.3→难度 10，EF=2.5（新题默认）→约 3.65。

### 关键约束
- 已击杀题目**不设**熟练度下限（早期版本有 `max(mastery, 0.85)` 的错误下限，已删除）。
- 常规调度会跳过 `#状态/已击杀` 或 `Mastery = 1.0` 的题目；只有在答错后回退为 `#状态/待攻克`，才会重新进入调度。
- 新建 Session 和 `/api/recommend` 推荐时都会排除仍处于 `active` 状态的旧 Session 题目，避免连续创建或确认重复调度同一批题。
- `count < 0` 会按 `0` 处理；CSV 中异常数值会回退到安全默认值，避免整次调度失败。
- 日期解析使用 `parse_date()`（见 `common.py`），兼容 `YYYY-MM-DD` 和 `YYYY/M/D`；解析失败按 30 天处理。

---

## 4. 已击杀状态回退规则

已击杀题目答错后：
- `feedback.py`：将 `Current_Tag` 从 `#状态/已击杀` 降级为 `#状态/待攻克`。
- `_writeback_md()`：同步将 Markdown 文件内的 `- 状态/已击杀` 替换为 `- 状态/待攻克`。

目的：防止调度持续低估已回退题目的复习优先级。

---

## 5. `_row_to_item()` — 题库条目转换

从 CSV 行转为统一的题目对象，供 `/api/stats` 和临时调度使用。

- `decayed_mastery`：以当日为基准计算衰减值。
- 日期解析失败时：`days = 0`（列表视图语义：今天刚看过）。
- `high_correct_streak`：连续高分答对次数，供前端展示和调试确认。

---

## 6. SM-2 间隔排期 `calc_sm2_interval()`

> 对应源文件：`omrs/common.py`

标准 SM-2 间隔计算，基于 Repetition（连续答对次数）：

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

### 互斥分配逻辑

```
1. 遍历所有非已击杀题目
2. 先按可选筛选项裁剪：科目 `subject`、分类 `category`、知识点 `knowledge_tag`
3. Due_Date ≤ 今天 → 到期列表
4. Due_Date > 今天 → 熟练度列表
```

两道列表天然不重复。

### 到期列表排序

1. 已逾期（Due_Date < 今天）排最前面
2. 今日到期排第二
3. 按 EF 升序（EF 越低越不稳定，越优先）

### 熟练度列表排序

按统一优先级公式（`compute_priority()`，见 §3）降序，含 leech 加成：

```
priority = (1 - decayed_mastery) × (eff_diff/10) + (days/60) × 0.3
```

待攻克且 mastery < 0.3 额外 +0.5；leech 额外 +0.4。

---

## 8. 反馈闭环中的 SM-2 更新

> 对应源文件：`omrs/feedback.py`

反馈提交后：
1. 计算熟练度更新（`compute_mastery_update()`，逻辑不变）
2. 查询 Session 中该 UID 的来源（`due` / `proficiency`）
3. 根据来源调用 `calc_sm2_interval()` 计算新间隔
4. 更新 `Interval`、`Due_Date`、`Repetition` 三个字段
5. 自定义练习（TMP-）不触发此流程（不写入 mastery_data.csv）

---

## 9. `_row_to_item()` — 题库条目转换

从 CSV 行转为统一的题目对象，供 `/api/stats` 和临时调度使用。

- `decayed_mastery`：以当日为基准计算衰减值。
- `interval`、`due_date`、`repetition`：SM-2 排期字段。
- `_source`：推荐来源标记（`due` / `proficiency`），仅在推荐/确认流程中赋值。
- 日期解析失败时：`days = 0`（列表视图语义：今天刚看过）。
- `high_correct_streak`：连续高分答对次数，供前端展示和调试确认。

---

## 10. 可调参数 tuning

> 对应源文件：`omrs/common.py` → `DEFAULT_TUNING` / `load_tuning()`

此前散落在代码里的「魔法数字」已集中为一份默认表，可在 `错题/.omrs/config.json` 的 `"tuning"` 键下覆盖（只列要改的项即可，其余取默认）。改完需重启服务生效（`save_config()` 会失效进程内缓存）。

| 键 | 默认 | 含义 |
|---|---|---|
| `decay_mastery_factor` / `decay_base` | 30 / 5 | 时间衰减常数（§1） |
| `high_score_threshold` | 7 | 高分阈值（§2） |
| `kill_streak` | 2 | 连续高分答对几次才击杀（§2） |
| `ef_cold_attempts` | 3 | EF 冷启动冻结门槛（§2） |
| `ef_up` / `ef_down` | 0.15 / 0.2 | EF 增/减量（§2） |
| `priority_days_divisor` / `priority_days_weight` | 60 / 0.3 | 优先级时间项（§3） |
| `attack_bonus` / `attack_mastery_threshold` | 0.5 / 0.3 | 待攻克加成（§3） |
| `proficiency_factor` | 0.7 | 熟练度来源答对的间隔折中系数（§6） |
| `leech_fail_threshold` / `leech_priority_bonus` | 4 / 0.4 | leech 判定与加成（§11） |

`config.json` 示例：

```json
{
  "allow_external": false,
  "tuning": { "kill_streak": 3, "leech_fail_threshold": 5 }
}
```

校验：仅接受 `DEFAULT_TUNING` 中已知的键、且值为数字，其余忽略，防止脏配置污染算法。

---

## 11. Leech（顽固题）检测

> 对应源文件：`omrs/scheduling.py` → `build_fail_counts()` / `is_leech()`

利用此前只用于展示的 `history_log.csv`：统计每个 UID 的累计答错次数（`Is_Correct == 0`）。

- **判定**：未击杀，且累计答错次数 ≥ `leech_fail_threshold`（默认 4）→ 标记为 leech。
- **优先级加成**：leech 在熟练度列表的 `compute_priority` 上 `+leech_priority_bonus`（默认 0.4），优先被召回。
- **暴露位置**：`/api/recommend` 与 `/api/stats` 的每个题目条目带 `fail_count` / `is_leech`；`/api/stats` 的 `review_alert.leech` 给出未击杀 leech 总数。
- **用途**：提示「反复错的题」值得重新拆解/整理，而非继续机械重刷。
