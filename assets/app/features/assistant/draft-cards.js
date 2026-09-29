/** 助手草稿卡片只叠加服务端当前详情；历史工具事件不改写。 */
import { get, post } from '../../core/api.js';

export function detectCardState(draft) {
  const job = (draft?.jobs || []).find(item => item.type === 'detect');
  if (!job) return { phase: 'idle', message: '' };
  if (job.status === 'queued' || job.status === 'running') {
    return { phase: 'busy', message: `AI 正在框选（${job.processed || 0}/${job.total || 0} 张）` };
  }
  const reasons = [...new Set([...(job.result || []).map(item => item.reason),
    ...(job.errors || []).map(item => item.error)].filter(Boolean))];
  if (['error', 'conflict', 'interrupted'].includes(job.status)) {
    const fallback = job.status === 'conflict' ? '草稿已变化，旧框选结果没有覆盖当前内容'
      : job.status === 'interrupted' ? '框选任务被中断' : 'AI 框选失败';
    return { phase: 'retry', message: reasons[0] || fallback };
  }
  const needsReview = (job.result || []).filter(item => ['suggested', 'skipped', 'conflict'].includes(item.status));
  if (needsReview.length) return { phase: 'review', message: reasons[0] || 'AI 框选有待人工处理的图片，请打开草稿核对' };
  return { phase: 'done', message: 'AI 框选已完成，请打开草稿核对' };
}

export function createDraftCards(S, schedule) {
  const requests = {};
  const detecting = new Set();
  let pollTimer = 0;
  const visibleIds = () => new Set(S.items.flatMap(item => item.run?.steps || [])
    .filter(step => ['create_draft', 'update_draft'].includes(step.name) && step.result?.draft_id)
    .map(step => step.result.draft_id));
  function pollIfActive(visible) {
    clearTimeout(pollTimer);
    if (!S.alive || (typeof document !== 'undefined' && document.hidden)) return;
    if ([...visible].some(id => detectCardState(S.drafts[id]?.draft).phase === 'busy')) {
      pollTimer = setTimeout(() => { pollTimer = 0; void refresh(); }, 1500);
    }
  }
  async function loadMode() {
    const res = await get('/api/config');
    if (!S.alive || !res.ok) return;
    const configured = res.data?.draft_crop_mode;
    const mode = ['ask', 'auto', 'manual'].includes(configured) ? configured : 'ask';
    if (S.draftCropMode !== mode) { S.draftCropMode = mode; S.draftVer += 1; schedule(); }
  }
  async function refresh(ids) {
    const visible = visibleIds();
    const targets = ids ? [...new Set(ids)].filter(id => visible.has(id)) : [...visible];
    await Promise.all(targets.map(async id => {
      const request = (requests[id] || 0) + 1;
      requests[id] = request;
      if (!S.drafts[id]) { S.drafts[id] = { loading: true }; S.draftVer += 1; schedule(); }
      const res = await get(`/api/drafts/item?id=${encodeURIComponent(id)}`);
      if (!S.alive || requests[id] !== request) return;
      S.drafts[id] = res.ok ? { draft: res.data.draft } : { error: res.error?.message || '草稿详情暂时不可用' };
      S.draftVer += 1;
      schedule();
    }));
    pollIfActive(visible);
  }
  async function detect(id, notify) {
    if (detecting.has(id)) return;
    const draft = S.drafts[id]?.draft;
    if (!draft) { await refresh([id]); return; }
    detecting.add(id);
    S.drafts[id] = { ...S.drafts[id], detecting: true };
    S.draftVer += 1;
    schedule();
    try {
      const res = await post('/api/drafts/detect', { id, revision: draft.revision });
      if (!res.ok) notify(res.error?.message || 'AI 框选未能启动，请在草稿区处理');
    } catch (_) {
      notify('AI 框选未能启动，请在草稿区处理');
    } finally {
      detecting.delete(id);
      if (S.drafts[id]) S.drafts[id] = { ...S.drafts[id], detecting: false };
      S.draftVer += 1;
      if (S.alive) await refresh([id]);
    }
  }
  return { refresh, loadMode, detect, dispose() { clearTimeout(pollTimer); } };
}
