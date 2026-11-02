/** 复核状态文案：档位决定间隔，累计击杀次数只表示成绩。 */
export function reviewCycle(item) {
  if (!item || item.suspended || !(item.is_revived || Number(item.mastery) >= 1 || String(item.tag || '').includes('已击杀'))) return null;
  const stage = Math.max(1, Math.min(5, Number(item.revive_stage) || 1));
  const interval = Number(item.dormant_days) || Number(item.interval) || 7;
  const date = item.next_revive_date || item.due_date;
  return {
    label: `${item.is_revived ? '复燃 · ' : '复核'}第 ${stage} 档`,
    title: `复核第 ${stage} 档 · 间隔 ${interval} 天 · ${date ? `下次复核 ${date}` : '待复核'} · 累计击杀 ${Number(item.kill_count) || 0} 次`,
  };
}
