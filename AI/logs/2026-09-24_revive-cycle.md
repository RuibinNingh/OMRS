# 反馈区重构与已击杀题复燃周期（v1.19.0）

日期：2026-09-24

## 起点：两条互不相干的用户诉求

用户原话（拆成两条）：

1. 「调度里面的错因不再显示在题目区域，因为这样会提示。错因应该在最后的一个专门区域，我打算叫做反馈区，反馈区包含答案和错因，如果不勾选导出答案就只有错因。如果勾选答案那么每一道题下面显示答案和错因，不要分开。还有生成的调度删掉原本的反馈勾选表，已经不需要这个了。」
2. 「设计一下新的复习算法。目前已击杀的题目不会再次出现，随着时间推移慢慢可能忘。因此需要有一个周期，让已击杀的题目再次出现在调度，当然周期最好比较长，符合记忆规律。如果答错了那么降级待攻克。」

第一条是版式问题：错因和答案一样，都属于「做完才能看」的信息，排在题面下方等于在作答时给解法提示。第二条是算法问题，而且是更根本的一条——**击杀被实现成了删除**。

三个决策由用户在计划阶段选定：复燃依据用**记忆衰减**（复用 `time_decay`，不为复燃另存到期日字段）、周期**分级**（越熟练越长）、`关联` **留在题面区**（关联是解题线索而不是答案）。

## 一、错因迁出题面区

### 数据侧先拆开

`omrs/exporting.py::_build_export_data()` 原本把整份 `notes` 同时给题面和答案段，于是模板想放哪就放哪，错因自然被排进了题面区。改为按小节拆开，**在数据层就断掉错因流进题面区的可能**：

```python
notes = _parse_notes_subsections(question.get("notes", "")) or {}
question_notes = {"关联": notes["关联"]} if notes.get("关联") else {}
answer_notes = {"错因": notes["错因"]} if notes.get("错因") else {}
```

`data["feedback"]`（那张反馈勾选表的数据）连同 `data["feedback"].append(...)` 一并删除——模板层面已无此需求，数据层留着只会诱使后人在别处复用它。`include_answers=false` 时 `answers[i].blocks` 是空数组但 `notes` 照旧，所以反馈区仍能只列错因。

### A4

`a4.js::buildBlocks()` 正文重排成两节：

- **一、题目**：题头 + 题面块 + `关联` + 题间留白。
- **二、反馈区**：每题一块，`ansHeadBlock` 标题行下面直接跟答案正文，**紧接着**同题的 `noteBlock("错因", ...)`，同属一块、不另起标题。这就是用户说的「不要分开」。该题既没答案也没错因时不占位；整节没有任何内容时连标题都不输出。

关键点：**未勾选导出答案时反馈区仍然出现**。「反馈区包含答案和错因，不勾选就只有错因」说明反馈区是常设区域，不是答案段的附属；导语相应改成「本次未导出答案，只列错因」。题面区在两种情况下都保持干净。

导语从「完成后在末尾的反馈表中打分和勾选对错」改成「做完后再翻到末尾的反馈区核对答案与错因」——旧文案指向一张已经删掉的表。那张表连同 `.fb-row*` 样式一起删除。

### 屏幕版与展示板

屏幕版把错因移进答案容器 `ans`，即折在「显示答案」按钮之后；`关联` 留在题面卡片。屏幕版答案恒开，所以屏幕版一定同时看到答案 + 错因，不需要额外的数据分支。

展示板原本**完全没有**错因（`build_board_export_data()` 不读 notes），这次补上：答案附页里每题答案之后追加错因块，题面栏不动。`answers:"none"` 时不输出错因——展示板是打印作答纸，不给提示。

## 二、已击杀题复燃周期

### 为什么是「反解衰减式」而不是新到期日字段

用户要的是「周期比较长，符合记忆规律」。最省事的做法是击杀时写一个 `Due_Date = today + N`，但那会引入一个必须进 Ledger、必须在修正重放时一起还原的新状态，且与既有 `time_decay` 形成两套时间语义。

选定的做法是让休眠时长从**衰减式反解**出来：现有 `decayed = mastery × e^(-days/(mastery×30+5))`，令其衰减到 `revive_decay_threshold`（0.2）：

```
dormant_days(n) = (mastery×30 + 5) × ln(1/threshold) × multiplier^(max(0, kill_count-1))
```

`mastery = 1.0`、`threshold = 0.2` 时基准为 `35 × 1.609 ≈ 56` 天，`multiplier = 1.8` 给出 **56 / 101 / 182 / 327 / 591 天**（第 1–5 次击杀后）。不新增到期日字段，`is_revive_eligible()` 每次用 `days_since_review()` 现算，因此不需要为它扩展 Ledger 与修正重放。

### 击杀次数必须进 Ledger

分级周期的自变量是 `kill_count`，它必须能从提交链重放出来，否则「撤销一次反馈重算熟练度」之后周期就漂了。所以：

- `compute_mastery_update()` 返回 `kill_count_delta`（`tag_action == "kill"` 时 +1，其余 0），`_apply_single_review()` 累加。
- `mastery_projection` 新增 `kill_count INTEGER NOT NULL DEFAULT 0` 列，老库在 `_ensure_schema()` 里用 `PRAGMA table_info` 探到缺列后 `ALTER TABLE ... ADD COLUMN` 补齐（与 `question_projection.suspended` 同一套做法），因此拿旧库直接启动不会报错；老数据一律按「还没击杀过」处理，首次击杀即第 1 次。
- `kill_count_delta` 进 `_project_state()` 的重放列表，撤销/恢复反馈时会重算。

### 接入调度

新增两个纯函数（可单测）：

```python
def revive_dormant_days(kill_count, mastery, tuning) -> int
def is_revive_eligible(mastery, tag, last_review, kill_count, today, tuning) -> bool
```

`schedule_questions()` 与 `generate_recommendations()` 里原来的 `if is_killed_state(...): continue` 改成 `if is_killed_state(...) and not is_revive_eligible(...): continue`。复燃题的 `Due_Date` 仍是击杀时的旧值（早已逾期），所以自然落进到期列表并排在最前；同时 `compute_priority()` 加 `revive_priority_bonus`（0.3），保证从熟练度列表被召回时也靠前。

## 三、踩到的坑

### 降级系数被算了两遍

`_apply_single_review()` 的降级分支原来只改标签、熟练度留在 1.0，这是「击杀后再答错会立刻再次击杀」的一半原因；另一半是直接写 `mastery × 0.3` 会在同一次 `compute_mastery_update()` 里与低分答错自身的 `old_m × 0.3` 相乘成 `0.09`。修法是先算出「未降级时的新熟练度」，再与降级值取 `min`：

```python
demoted = old_mastery * tuning["kill_demote_factor"]
new_mastery = min(new_mastery, demoted)
```

`tests/test_revive_cycle.py` 断言 `0.3, places=3` 守住这一点。

### 复燃题在画廊里被标成「逾期 90 天」

前端收尾时发现的：`galleryFlagsHtml()` 先判 due-days 再看 `is_revived`，而复燃题的 `Due_Date` 正是击杀时的旧值，于是渲染出「逾期 N 天」——恰好是推荐列表已经避免的那种误读（用户会以为是自己没做完的旧账）。改成 suspended / revived / else 的判定链，复燃优先。同时 `reviveChipHtml()` 补了 `|| item.suspended` 守卫：停用题不参与调度，谈不上复燃，与画廊的「停用 / 复燃」二选一保持一致。这两处是写文档时顺手核对渲染顺序发现的，不在原计划里。

## 四、验证

新增 `tests/test_revive_cycle.py`（unittest，仿 `tests/test_leech_streak.py` 的临时 vault 写法），覆盖六项：击杀当天不进推荐、57 天后复燃且 `is_revived == true`；击杀两次的题 70 天不复燃 / 120 天复燃（验证分级周期）；复燃后答错标签回待攻克且 `mastery ≈ 0.3`、`kill_count` 保留、`repetition == 0`；复燃后高分答对再次击杀 `kill_count == 2` 且休眠变长；`kill_count` 缺列的老 vault 重放不报错；A4 导出无反馈勾选表文本、错因不在题面块而在答案块、`include_answers=false` 时只有错因段。

回归：`tests/test_recommendations`、`tests/test_leech_streak`、`tests/test_sessions_feedback`、`tests/test_history_projection`、`tests/test_board_export`、`tests/test_report_export.py`，以及 `tests/test_*.js` 与改动过的每个 JS 的 `node --check`。文档体检 `python3 tests/check_docs.py` 退出 0。

真实浏览器核查（`AGENTS.md` 规则 6）：临时题库起 `omrs_engine.py`，走「调度 → 导出打印版」看 A4 版面与错因归属；反馈页录入一次正确反馈把某题打到击杀，手动改 `Last_Review` 后再看推荐列表的「复燃」chip。

## 五、边界与取舍

- **停用题不复燃**：停用不参与调度，也就无所谓复燃；恢复后沿用原 Mastery/SM-2 与 `kill_count`，休眠时长照旧接续。
- **`关联` 留在题面区**：关联是解题线索（比如「和 2026-03 那道椭圆题同一套设点」），不是答案，留在题面反而有助于作答。这是用户明确选定的，代码与文档都按此执行。
- **展示板不给错因的例外**：`answers:"none"` 时展示板整份不输出错因，与 A4 / 屏幕版不同——展示板导出的是打印作答纸，不导出答案时也就不该给提示。
- **反馈工作台不动**：`assets/feedback.js` 与 `assets/qview.js` 里的错因展示保持原样，那是录入端自己在用的面板，用户在那里校对的本来就是错因。
