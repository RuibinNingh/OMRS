/** 助手草稿卡片只叠加服务端当前详情；历史工具事件不改写。 */
import { get } from '../../core/api.js';

export function createDraftCards(S, schedule) {
  const requests = {};
  async function refresh(ids) {
    const visible = new Set(S.items.flatMap(item => item.run?.steps || [])
      .filter(step => step.name === 'create_draft' && step.result?.draft_id)
      .map(step => step.result.draft_id));
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
  }
  return { refresh };
}
