/** 学习参数表单的范围与重算回执。数值由服务端有效配置提供。 */
export const TUNING_FIELDS = [
  { key: 'high_score_threshold', label: '高分阈值', min: 0, max: 10, step: 1, hint: '主观分达到此值视为高分' },
  { key: 'revive_intervals_days', label: '五档复核间隔（天）', kind: 'intervals', hint: '用逗号分隔五个递增正整数，如 7,21,60,120,180；一次高分答对即可击杀' },
  { key: 'ef_cold_attempts', label: '冷启动复习次数', min: 0, step: 1, hint: '达到此次数前保持难度系数' },
  { key: 'leech_fail_threshold', label: '顽固题连错次数', min: 1, step: 1, hint: '连续答错达到此次数视为顽固题' },
  { key: 'decay_mastery_factor', label: '熟练度衰减系数', min: 0, exclusiveMin: true, step: 'any' },
  { key: 'decay_base', label: '衰减基础天数', min: 0, exclusiveMin: true, step: 'any' },
  { key: 'ef_up', label: '答对难度系数增量', min: 0, step: 'any' },
  { key: 'ef_down', label: '答错难度系数减量', min: 0, step: 'any' },
  { key: 'priority_days_divisor', label: '优先级天数基准', min: 0, exclusiveMin: true, step: 'any' },
  { key: 'priority_days_weight', label: '优先级天数权重', min: 0, step: 'any' },
  { key: 'attack_bonus', label: '待攻克优先级加成', min: 0, step: 'any' },
  { key: 'attack_mastery_threshold', label: '待攻克熟练度阈值', min: 0, step: 'any' },
  { key: 'proficiency_factor', label: '熟练答对折中系数', min: 0, exclusiveMin: true, max: 1, step: 'any' },
  { key: 'leech_priority_bonus', label: '顽固题优先级加成', min: 0, step: 'any' },
  { key: 'label_bonus_cap', label: '标记优先级加成上限', min: 0, step: 'any' },
  { key: 'revive_priority_bonus', label: '复燃题优先级加成', min: 0, step: 'any' },
  { key: 'kill_demote_factor', label: '复燃答错降级系数', min: 0, max: 1, step: 'any' },
];

export function readTuning(valueOf) {
  const tuning = {};
  for (const field of TUNING_FIELDS) {
    const raw = String(valueOf(field.key) ?? '').trim();
    if (field.kind === 'intervals') {
      const values = raw.split(/[,，]/).map(part => part.trim() ? Number(part) : NaN);
      if (!validIntervals(values)) throw new Error('复核间隔必须是五个严格递增的正整数');
      tuning[field.key] = values;
      continue;
    }
    const value = Number(raw);
    if (!raw || !Number.isFinite(value)) throw new Error(`${field.label}必须是有效数字`);
    if (field.step === 1 && !Number.isInteger(value)) throw new Error(`${field.label}必须是整数`);
    if (value < field.min || (field.exclusiveMin && value === field.min)) throw new Error(`${field.label}必须${field.exclusiveMin ? '大于' : '不小于'}${field.min}`);
    if (field.max !== undefined && value > field.max) throw new Error(`${field.label}不能大于${field.max}`);
    tuning[field.key] = value;
  }
  return tuning;
}

export const validIntervals = values => Array.isArray(values) && values.length === 5 && values.every((value, index) =>
  Number.isSafeInteger(value) && value > 0 && (!index || value > values[index - 1]));

export const tuningMatches = (effective, requested) => TUNING_FIELDS.every(field => field.kind === 'intervals'
  ? validIntervals(effective?.[field.key]) && validIntervals(requested?.[field.key]) && effective[field.key].every((value, i) => value === requested[field.key][i])
  : typeof effective?.[field.key] === 'number' && effective[field.key] === requested?.[field.key]);

export function recalculationText(data) {
  const result = data?.recalculation;
  const revision = result?.revision ?? data?.revision;
  if (result?.status === 'unchanged') return `学习参数已生效，无需重算${revision == null ? '' : `；配置版本 ${revision}`}`;
  if (!result || !['completed', 'complete', 'done'].includes(result.status)) return '学习参数已生效；重算结果待确认';
  const seconds = Number(result.seconds);
  return `历史重算完成：${result.questions ?? 0} 题、${result.feedbacks ?? 0} 条反馈，耗时 ${Number.isFinite(seconds) ? seconds.toFixed(2) : '—'} 秒；配置版本 ${revision ?? '—'}`;
}
