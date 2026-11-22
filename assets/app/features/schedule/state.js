/**
 * 复习调度：模块状态 + 纯函数（计划列表的筛选与卡片、计划详情、工作区切换、标签页键盘），node 单测全覆盖。
 * 工作区 view：'arrange'（安排复习，旧 recommend_v2.js）| 'plans'（已有计划，本页原生）| 'reminders'（提醒素材）| 'export'（全题库导出，旧 export.js）。
 * 进入「全题库导出」时记住来处，「返回」回到它（原 SCH_EXPORT_RETURN）。
 */
import { sessionProgress, sessionEntries, entryFeedbackState, progressText } from '../../domain/sessions.js';

export const state = {
  view: 'arrange', exportReturn: 'arrange', filter: 'active', search: '',
  selected: '', detail: null, detailPhase: 'idle', detailError: '', showDetail: false,
  deleting: new Set(), changing: new Set(), deleted: false, exporting: '', exportStatus: null,
};

export const VIEWS = ['arrange', 'plans', 'reminders'];

/** 切工作区：返回新的 { view, exportReturn }；'back' 从导出回到来处。 */
export function nextView(s, view) {
  if (view === 'back') return { view: s.exportReturn || 'arrange', exportReturn: s.exportReturn };
  if (view === 'export') return { view: 'export', exportReturn: s.view === 'export' ? s.exportReturn : s.view };
  return { view: VIEWS.includes(view) ? view : 'arrange', exportReturn: s.exportReturn };
}

/** 标签页上的 ←/→/Home/End（三个标签，自动激活）。不是这几个键时返回 null。 */
export function tabKey(view, key) {
  if (key === 'home') return 'arrange';
  if (key === 'end') return 'reminders';
  if (key === 'arrowleft' || key === 'arrowright') return VIEWS[(Math.max(0, VIEWS.indexOf(view)) + (key === 'arrowright' ? 1 : -1) + VIEWS.length) % VIEWS.length];
  return null;
}

const when = text => String(text || '').replace('T', ' ');
const planStatus = value => ({ active: '待完成', paused: '已暂停', completed: '已完成' })[value] || '待完成';

export function filterPlans(list, filter = 'active', search = '') {
  const q = String(search || '').trim().toLowerCase();
  return (list || []).filter(s => (filter === 'all' || (s.status || 'active') === filter) && String(s.session_id || '').toLowerCase().includes(q));
}

export function planCard(s) {
  const p = sessionProgress(s);
  const done = (s.status || 'active') === 'completed';
  const status = s.progress ? (done ? '已结束' : s.progress.can_finish ? '可结束' : planStatus(s.status)) : planStatus(s.status);
  return { id: s.session_id, when: when(s.created_at).slice(0, 16), done, status,
    title: `${s.subject_filter || '多科复习'} · ${p.total} 题`, total: p.total, recorded: p.feedback_count,
    ...(s.progress ? { summary: progressText(s.progress, { ended: done }) } : {}) };
}

export const activeCount = list => (list || []).filter(s => (s.status || 'active') === 'active').length;

export function detailModel(d) {
  const availabilityText = { archived: '题目已归档，历史条目保留', suspended: '题目已停用', unresolved: '题目身份待确认，请手动绑定' };
  const legacy = !Array.isArray(d.entries);
  const recorded = new Set(d.feedback_uids || []);
  const questions = (legacy ? (d.items || []) : sessionEntries(d)).map((entry, i) => {
    const item = legacy ? entry : (d.items || []).find(item => item.entry_id === entry.entry_id || (entry.question_id && item.question_id === entry.question_id)) || {};
    const uid = legacy ? item.UID || item.uid : entry.uid || entry.uid_at_creation || '未知题目';
    const unavailable = legacy ? !!item._missing : entry.availability !== 'active';
    return { n: i + 1, uid, question_id: entry.question_id || '', entry_id: entry.entry_id || '',
      preview_key: legacy ? uid : entry.question_id || '',
      availability: entry.availability || (unavailable ? 'unresolved' : 'active'), missing: unavailable,
      recorded: legacy ? recorded.has(uid) : entryFeedbackState(entry) === 'recorded',
      feedback_state: legacy ? (recorded.has(uid) ? 'recorded' : 'pending') : entryFeedbackState(entry),
      feedback_reason: entry.feedback_reason || '',
      corrected: !!d.completion && entryFeedbackState(entry) === 'recorded' && !entry.feedback_submitted,
      meta: unavailable ? availabilityText[entry.availability] || '题目已缺失，无法预览' : `${item.Subject || item.subject || ''} · ${item.Category || item.category || ''}` };
  });
  const pending = d.progress?.pending ?? (Number(d.pending_count) || 0);
  const done = d.status === 'completed';
  const paused = d.status === 'paused';
  const canFinish = !!d.progress?.can_finish;
  const summary = d.progress ? progressText(d.progress, { ended: done, ready: true }) : '';
  const hint = paused ? '进度已保留，恢复计划后可继续录入' : d.progress ? '' : pending ? `还有 ${pending} 题待录入` : '本次复习已全部录入';
  return {
    id: d.session_id, title: `${d.subject_filter || '多科'}复习计划`, when: when(d.created_at), done, paused, status: d.progress ? (done ? '已结束' : canFinish ? '可结束' : planStatus(d.status)) : planStatus(d.status),
    recorded: d.progress?.recorded ?? (Number(d.feedback_count) || 0),
    total: d.progress?.total ?? (Number(d.count) || questions.length), pending, summary, hint, canFinish,
    canFeedback: !done && !paused && (d.progress ? pending > 0 || d.progress.unresolved > 0
      : pending > 0 && questions.some(q => !q.missing && !q.recorded)),
    canExport: questions.length > 0 && questions.every(q => !q.missing),
    questions, previewable: questions.filter(q => !q.missing && q.preview_key).map(q => q.preview_key),
  };
}

/** 题间留白（行）：0–20 的整数，非法按 0。 */
export const clampGap = value => { const n = Math.round(Number(value)); return Number.isFinite(n) ? Math.max(0, Math.min(20, n)) : 0; };
