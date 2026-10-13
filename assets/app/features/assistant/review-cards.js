/** 对话内审批与结果：当前服务端状态叠加历史事件，批准只针对已经展示的提案版本。 */
import { html } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { status } from '../../ui/status.js';
import { fetchReviewDetail, decideReview, openReview, publishReviewChange } from '../../domain/ai-review.js';
import { post } from '../../core/api.js';
import { toolTitle, toolIcon, toolPreview } from './tools-view.js';
import { icon } from '../../ui/icon.js';
import { REVIEW_LABELS, isPending, inlineTools, attention, reviewTone, reviewSummary, confirmLabel } from './review-model.js';
import { inlinePreview } from './review-preview.js';
import { transferNote } from './permissions.js';
import { mmss, applyEvent } from './state.js';

const ACTIVE = ['pending_confirmation', 'approved', 'applying', 'running'];
export const operationId = step => step?.operationId || step?.result?.operation_id || '';
export function reviewCard(S, run, step) {
  const id = operationId(step);
  if (!id) return '';
  const current = S.reviews?.[id], item = current?.item, key = `${run.id}|${step.callId}`;
  const args = item?.payload?.arguments || item?.payload?.args || item?.payload || step.args || {};
  const targets = item?.tool === 'set_question_labels' ? [args.add?.length ? `加「${args.add.join('、')}」` : '', args.remove?.length ? `去「${args.remove.join('、')}」` : ''].filter(Boolean).join('，') : '';
  const pending = isPending(item), simple = inlineTools.has(item?.tool), tone = reviewTone(item);
  const center = item?.permission?.channel === 'center';
  const automatic = item?.permission?.automatic;
  const expanded = S.reviewOpen?.has(id) || attention(item) && !S.reviewClosed?.has(id);
  const label = pending && center ? '已送审核' : item ? REVIEW_LABELS[item.status] || item.status : current?.error ? '状态暂不可用' : '正在读取操作状态…';
  const phase = item?.status === 'applied' || item?.status === 'unchanged' ? 'is-done' : pending ? 'is-waiting'
    : item?.status === 'rejected' ? 'is-denied' : attention(item) ? 'is-error' : '';
  const autoPreview = ['create_draft', 'update_draft', 'create_category', 'create_practice_card'].includes(step.name)
    && step.status === 'done' && ['applied', 'unchanged'].includes(item?.status);
  return html`<section class="ast-tool ast-op ${phase}" data-operation="${id}" aria-label="对话内操作">
    <header class="ast-op__head"><span class="ast-op__title">${icon(toolIcon(step))}${toolTitle(step)}${targets ? ` · ${targets}` : ''}</span>
      <span class="ast-op__state is-${tone}" role="status">${tone === 'success' ? icon('check-circle') : tone === 'warning' ? icon('clock') : ''}${label}</span></header>
    ${pending && center ? html`<p class="ast-op__summary">${transferNote(item.permission)}</p>` : reviewSummary(item) ? html`<p class="ast-op__summary">${reviewSummary(item)}</p>` : ''}
    ${automatic ? html`<p class="ast-op__automatic">${icon('alert-triangle')}危险模式 · 自动同意${item.status === 'approved' ? '，等待执行' : ''}</p>` : ''}
    ${current?.error ? status({ tone: 'danger', text: `${current.error}；保留上次读取的内容，请重试核对。` }) : ''}
    ${item?.error_code ? status({ tone: 'danger', text: `未完成：${item.error_code}` }) : ''}
    ${step.error && (attention(item) || item?.status === 'rejected') ? status({ tone: 'danger', text: step.error }) : ''}
    ${item?.revision > (step.reviewRevision || 1) && pending ? html`<p class="ast-op__muted">提案已修订，以下为第 ${item.revision} 版。</p>` : ''}
    ${pending && simple && !center || expanded ? html`<div class="ast-op__preview">${inlinePreview(item, step)}</div>` : ''}
    ${autoPreview ? html`<div class="ast-op__preview">${toolPreview(step, S.drafts?.[step.result?.draft_id], S.draftCropMode)}</div>` : ''}
    <div class="ast-op__actions">
      ${pending && simple && !center ? button({ label: confirmLabel(item), variant: 'primary', size: 'sm', action: 'assistant.approve', arg: `${key}|${item.revision}`, disabled: current.busy || !!current.error }) : ''}
      ${pending && !center ? button({ label: '拒绝', size: 'sm', action: 'assistant.deny', arg: key, disabled: current.busy || !!current.error }) : ''}
      ${pending && !center && item.permission?.mode === 'manual' ? button({ label: '送到审核中心', size: 'sm', variant: 'ghost', action: 'assistant.defer', arg: key, disabled: current.busy || !!current.error }) : ''}
      ${pending ? button({ label: center ? '查看审核详情' : simple ? '完整预览与修订' : '查看详情并确认', variant: simple || center ? 'ghost' : 'primary', size: 'sm', action: 'assistant.gate', arg: key, disabled: current.busy })
        : item ? html`${button({ label: expanded ? '收起变更' : '查看变更', size: 'sm', variant: 'ghost', action: 'assistant.toggleReview', arg: key })}${button({ label: '操作详情', size: 'sm', variant: 'ghost', action: 'assistant.gate', arg: key })}` : ''}
      ${item?.tool === 'propose_label_plan' && item.status === 'applied' && !item.result?.reverted_by ? button({ label: '预览整批撤销', size: 'sm', action: 'assistant.gate', arg: key }) : ''}
      ${current?.error ? button({ label: '重试状态', size: 'sm', action: 'assistant.retryReview', arg: id }) : ''}
      ${pending && item.expires_at && !center ? html`<span class="ast-op__muted ast-op__expiry">${mmss(Date.parse(item.expires_at) - Date.now())} 后${item.permission?.mode === 'manual' ? '自动送审' : '过期'}</span>` : ''}
    </div></section>`;
}
export function createReviewCards(S, schedule, { bus, request = fetchReviewDetail, decide = decideReview,
  open = openReview, onApplied, document: doc = globalThis.document, timers = globalThis } = {}) {
  S.reviews ||= {}; S.reviewVer ||= 0; S.reviewOpen ||= new Set(); S.reviewClosed ||= new Set();
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
      if (out.ok && out.item.permission?.channel === 'center' && !ACTIVE.includes(out.item.status)) {
        const item = out.item;
        for (const run of S.items.map(entry => entry.run).filter(Boolean)) {
          const step = run.steps.find(value => operationId(value) === id);
          if (!step || step.reviewSynced === item.status) continue;
          applyEvent(run, { type: 'tool.reviewed', t: run.clock.t, data: { call_id: step.callId,
            status: ['applied', 'unchanged'].includes(item.status) ? 'done' : item.status,
            result: { ...item.result, operation_id: id }, commits: item.commits, wrote: item.status === 'applied' || item.status === 'partial' } });
          step.reviewSynced = item.status;
          if (item.status === 'applied' || item.status === 'partial') void onApplied?.(item);
        }
      }
      S.reviews[id] = out.ok ? { item: out.item, busy: deciding.has(id) } : { ...S.reviews[id], error: out.error || '操作状态读取失败' };
      changed();
    }));
    schedulePoll();
  }
  async function sendDecision(step, decision, notify, viewed) {
    const id = operationId(step); if (!id) return;
    if (deciding.has(id)) return;
    if (decision === 'approve' && (!Number.isSafeInteger(viewed) || !inlineTools.has(S.reviews[id]?.item?.tool))) return;
    deciding.add(id); if (S.reviews[id]) S.reviews[id].busy = true; changed();
    try {
      await refresh([id]);
      const current = S.reviews[id];
      if (!S.alive || !visible().has(id) || !isPending(current?.item) || current?.error) return;
      if (decision === 'approve' && current.item.revision !== viewed) {
        notify('提案已变化，请核对更新后的内容，再点确认。'); return;
      }
      const out = await decide(id, current.item.revision, decision);
      if (!S.alive) return;
      if (out.ok && out.item) S.reviews[id] = { item: out.item, busy: true };
      if (!out.ok) notify(out.error || '决定未核实，请重试读取当前状态。');
    } finally { deciding.delete(id); if (S.reviews[id]) S.reviews[id].busy = false; changed(); }
    await refresh([id]);
  }
  const off = bus?.on?.('ai-review:changed', payload => { void refresh(payload?.ids); });
  return { refresh, reject: (step, notify) => sendDecision(step, 'reject', notify), approve: (step, notify, viewed) => sendDecision(step, 'approve', notify, viewed),
    async defer(step, notify) {
      const id = operationId(step), current = S.reviews[id];
      if (!isPending(current?.item) || deciding.has(id) || current.error) return;
      deciding.add(id); current.busy = true; changed();
      try {
        const out = await post('/api/agent/review/defer', { operation_id: id, expected_revision: current.item.revision });
        if (!out.ok) notify(out.error?.message || '送审失败，请重新读取状态');
        else publishReviewChange([id]);
      } finally { deciding.delete(id); current.busy = false; changed(); }
      await refresh([id]);
    },
    open: (step, returnFocus) => open(operationId(step), returnFocus),
    toggle(step) { const id = operationId(step), expanded = S.reviewOpen.has(id) || attention(S.reviews[id]?.item) && !S.reviewClosed.has(id);
      if (expanded) { S.reviewOpen.delete(id); S.reviewClosed.add(id); } else { S.reviewOpen.add(id); S.reviewClosed.delete(id); } changed(); },
    dispose() { if (poll) timers.clearTimeout(poll); off?.(); requests.clear(); } };
}
