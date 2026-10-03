/** 聊天只叠加审核中心当前状态，不改写历史工具事件。 */
import { html } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { fetchReviewDetail, decideReview, openReview } from '../../domain/ai-review.js';

const LABELS = { pending_confirmation: '待审核', approved: '已批准，等待执行', applying: '执行中', running: '执行中',
  applied: '已执行', rejected: '已拒绝', expired: '已过期', conflict: '有冲突', failed: '失败', failure: '失败',
  cancelled: '已中止', invalidated: '已失效', interrupted: '已中断', partial: '部分成功', unchanged: '无实际变更' };
const ACTIVE = ['pending_confirmation', 'approved', 'applying', 'running'];
export const operationId = step => step?.operationId || step?.result?.operation_id || '';
const pending = item => item?.status === 'pending_confirmation' && !item.history_readonly;
export function reviewCard(S, run, step) {
  const id = operationId(step);
  if (!id) return '';
  const current = S.reviews?.[id], item = current?.item, key = `${run.id}|${step.callId}`;
  const label = item ? LABELS[item.status] || item.status : current?.error ? '状态暂不可用' : '正在读取审核状态…';
  const summary = item?.preview?.summary || item?.preview?.title || '';
  return html`<section class="ast-gate" aria-label="审核中心当前状态"><p class="ast-gate__what">${label}</p>
    ${summary ? html`<p>${summary}</p>` : ''}${item?.revision > (step.reviewRevision || 1) ? html`<p class="ast-gate__note">提案已修订，请以审核中心的当前内容为准。</p>` : ''}
    ${current?.error ? html`<p class="ast-note is-error">${current.error}；保留上次读取的状态。</p>` : ''}
    <div class="ast-gate__bar">${item?.expires_at && pending(item) ? html`<span class="ast-gate__clock">有效期至 ${new Date(item.expires_at).toLocaleTimeString('zh-CN')}</span>` : ''}
      ${pending(item) ? button({ label: '拒绝', size: 'sm', action: 'assistant.deny', arg: key, disabled: current.busy }) : ''}
      ${button({ label: pending(item) ? '查看并决定' : '查看审核记录', size: 'sm', variant: pending(item) ? 'primary' : 'default', action: 'assistant.gate', arg: key })}
      ${current?.error ? button({ label: '重试状态', size: 'sm', action: 'assistant.retryReview', arg: id }) : ''}</div>
    ${pending(item) ? html`<p class="ast-gate__note">审核中心与此卡片共用同一项决定；批准后仍需等待实际执行结果。</p>` : ''}</section>`;
}
export function createReviewCards(S, schedule, { bus, request = fetchReviewDetail, decide = decideReview,
  open = openReview, document: doc = globalThis.document, timers = globalThis } = {}) {
  S.reviews ||= {}; S.reviewVer ||= 0;
  const requests = new Map(), deciding = new Set(); let poll = null;
  const visible = () => new Set(S.items.flatMap(item => item.run?.steps || []).map(operationId).filter(Boolean));
  function changed() { S.reviewVer += 1; schedule(); }
  function schedulePoll() {
    if (poll) timers.clearTimeout(poll); poll = null;
    if (!S.alive || doc?.hidden) return;
    if ([...visible()].some(id => ACTIVE.includes(S.reviews[id]?.item?.status))) {
      poll = timers.setTimeout(() => { poll = null; void refresh(); }, 2500);
    }
  }
  async function refresh(ids) {
    const shown = visible(), targets = ids ? [...new Set(ids)].filter(id => shown.has(id)) : [...shown];
    await Promise.all(targets.map(async id => {
      const version = (requests.get(id) || 0) + 1; requests.set(id, version);
      const out = await request(id);
      if (!S.alive || requests.get(id) !== version || !visible().has(id)) return;
      S.reviews[id] = out.ok ? { item: out.item, busy: deciding.has(id) } : { ...S.reviews[id], error: out.error || '审核状态读取失败' };
      changed();
    }));
    schedulePoll();
  }
  async function reject(step, notify) {
    const id = operationId(step); if (!id) { await open(); return; }
    if (deciding.has(id)) return;
    deciding.add(id);
    try {
    await refresh([id]);
    const current = S.reviews[id]; if (!pending(current?.item) || current?.error) return;
    const revision = current.item.revision; current.busy = true; changed();
    const out = await decide(id, revision, 'reject');
    if (!S.alive) return;
    if (!out.ok) notify(out.error || '拒绝没有送达，请重新核对当前状态');
    } finally { deciding.delete(id); if (S.reviews[id]) S.reviews[id].busy = false; changed(); }
    await refresh([id]);
  }
  const off = bus?.on?.('ai-review:changed', payload => { void refresh(payload?.ids); });
  return { refresh, reject, open: step => open(operationId(step)),
    dispose() { if (poll) timers.clearTimeout(poll); off?.(); requests.clear(); } };
}
