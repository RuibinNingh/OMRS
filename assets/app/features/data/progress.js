/** 攻克状态的只读派生；当前击杀题数、累计击杀成绩和复核档位分别统计。 */
const number = value => Number(value) || 0;
export const killed = item => !!item.is_killed || number(item.mastery) >= 1 || String(item.tag || '').includes('已击杀');
export const FILTERS = [
  { key: 'all', label: '全部题目', match: () => true },
  { key: 'killed', label: '已击杀', match: killed },
  { key: 'dormant', label: '休眠中', match: item => killed(item) && !item.is_revived },
  { key: 'revived', label: '复燃待复核', match: item => killed(item) && !!item.is_revived },
  { key: 'attacking', label: '待攻克', match: item => !killed(item) },
  { key: 'never', label: '从未复习', match: item => number(item.attempts) === 0 },
  { key: 'leech', label: '顽固题', match: item => !!item.is_leech },
];

export function progressSummary(items = []) {
  const active = items.filter(item => !item.suspended);
  const mastered = active.filter(killed);
  return {
    dormant: mastered.filter(item => !item.is_revived).length,
    revived: mastered.filter(item => item.is_revived).length,
    killCount: active.reduce((sum, item) => sum + number(item.kill_count), 0),
    everKilled: active.filter(item => number(item.kill_count) > 0).length,
    stages: Array.from({ length: 5 }, (_, i) => {
      const stage = i + 1;
      const count = mastered.filter(item => Math.max(1, Math.min(5, number(item.revive_stage))) === stage).length;
      return { key: String(stage), label: `第 ${stage} 档`, value: count, display: `${count} 题`,
        pct: mastered.length ? count / mastered.length * 100 : 0, tone: 'success' };
    }),
  };
}

/** 过滤在分页之前；筛选计数随科目和搜索变化，翻页仍能覆盖完整匹配结果。 */
export function questionRows(items = [], { filter = 'killed', subject = '', query = '', page = 1 } = {}, size = 10) {
  const active = items.filter(item => !item.suspended);
  const text = query.trim().toLocaleLowerCase();
  const scoped = active.filter(item => (!subject || item.subject === subject)
    && (!text || [item.uid, item.subject, item.category, ...(item.labels || [])].join(' ').toLocaleLowerCase().includes(text)));
  const match = FILTERS.find(row => row.key === filter)?.match || FILTERS[1].match;
  const rows = scoped.filter(match).sort((a, b) => Number(!!b.is_revived) - Number(!!a.is_revived)
    || String(b.last_review || '').localeCompare(String(a.last_review || '')) || String(a.uid).localeCompare(String(b.uid)));
  const pages = Math.max(1, Math.ceil(rows.length / size));
  const current = Math.max(1, Math.min(pages, Math.trunc(number(page)) || 1));
  return { rows: rows.slice((current - 1) * size, current * size), uids: rows.map(item => item.uid),
    total: rows.length, page: current, pages,
    counts: FILTERS.map(row => ({ ...row, count: scoped.filter(row.match).length })),
    subjects: [...new Set(active.map(item => item.subject).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN')) };
}

export function statusOf(item) {
  if (killed(item)) return { label: item.is_revived ? '复燃待复核' : '已击杀 · 休眠中', tone: item.is_revived ? 'warning' : 'success' };
  return { label: number(item.attempts) ? '待攻克' : '待攻克 · 未复习', tone: 'muted' };
}
