/**
 * 复习调度：模块状态 + 纯函数（计划列表的筛选与卡片、计划详情、工作区切换、标签页键盘），node 单测全覆盖。
 * 工作区 view：'arrange'（安排复习，旧 recommend_v2.js）| 'plans'（已有计划，本页原生）| 'export'（全题库导出，旧 export.js）。
 * 进入「全题库导出」时记住来处，「返回」回到它（原 SCH_EXPORT_RETURN）。
 */
import { sessionProgress } from '../../domain/sessions.js';

export const state = {
  view: 'arrange', exportReturn: 'arrange', filter: 'active', search: '',
  selected: '', detail: null, detailPhase: 'idle', detailError: '', showDetail: false,
  deleting: new Set(), answers: false, gap: 0, options: false, deleted: false, exporting: '', exportStatus: null,
};

export const VIEWS = ['arrange', 'plans'];

/** 切工作区：返回新的 { view, exportReturn }；'back' 从导出回到来处。 */
export function nextView(s, view) {
  if (view === 'back') return { view: s.exportReturn || 'arrange', exportReturn: s.exportReturn };
  if (view === 'export') return { view: 'export', exportReturn: s.view === 'export' ? s.exportReturn : s.view };
  return { view: VIEWS.includes(view) ? view : 'arrange', exportReturn: s.exportReturn };
}

/** 标签页上的 ←/→/Home/End（两个标签，自动激活）。不是这几个键时返回 null。 */
export function tabKey(view, key) {
  if (key === 'home') return 'arrange';
  if (key === 'end') return 'plans';
  if (key === 'arrowleft' || key === 'arrowright') return view === 'arrange' ? 'plans' : 'arrange';
  return null;
}

const when = text => String(text || '').replace('T', ' ');

export function filterPlans(list, filter = 'active', search = '') {
  const q = String(search || '').trim().toLowerCase();
  return (list || []).filter(s => (filter === 'all' || (s.status || 'active') === filter) && String(s.session_id || '').toLowerCase().includes(q));
}

export function planCard(s) {
  const p = sessionProgress(s);
  const done = (s.status || 'active') === 'completed';
  return { id: s.session_id, when: when(s.created_at).slice(0, 16), done, status: done ? '已完成' : '待完成',
    title: `${s.subject_filter || '多科复习'} · ${p.total} 题`, total: p.total, recorded: p.feedback_count };
}

export const activeCount = list => (list || []).filter(s => (s.status || 'active') === 'active').length;

export function detailModel(d) {
  const recorded = new Set(d.feedback_uids || []);
  const questions = (d.items || []).map((item, i) => {
    const uid = item.UID || item.uid;
    return { n: i + 1, uid, missing: !!item._missing, recorded: recorded.has(uid),
      meta: item._missing ? '题目已缺失，无法预览' : `${item.Subject || item.subject || ''} · ${item.Category || item.category || ''}` };
  });
  const pending = Number(d.pending_count) || 0;
  const done = d.status === 'completed';
  return {
    id: d.session_id, title: `${d.subject_filter || '多科'}复习计划`, when: when(d.created_at), done, status: done ? '已完成' : '待完成',
    recorded: Number(d.feedback_count) || 0, total: Number(d.count) || questions.length, pending,
    hint: pending ? `还有 ${pending} 题待录入` : '本次复习已全部录入', canFeedback: pending > 0 && !done,
    questions, previewable: questions.filter(q => !q.missing).map(q => q.uid),
  };
}

/** 题间留白（行）：0–20 的整数，非法按 0。 */
export const clampGap = value => { const n = Math.round(Number(value)); return Number.isFinite(n) ? Math.max(0, Math.min(20, n)) : 0; };
