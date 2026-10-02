/** 助手列表、成组历史与运行事件分页；响应只归入仍有效的页面。 */
import { get } from '../../core/api.js';
import { toast } from '../../ui/toast.js';
import { applyEvent, historyItems, mergeHistoryItems } from './state.js';

export function createAssistantHistory(S, { schedule, paint, scroller }) {
  async function loadList(older = false) {
    if (older && (!S.listMore || S.listBusy)) return;
    const request = ++S.listRequest;
    const cursor = older ? S.listCursor : '';
    S.listBusy = true; schedule();
    const [st, cv] = await Promise.all([get('/api/agent/status'), get(`/api/agent/conversations?limit=30${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`)]);
    if (!S.alive || request !== S.listRequest) return;
    S.listBusy = false;
    if (st.ok) S.status = st.data;
    if (cv.ok) {
      const rows = cv.data.conversations || [];
      const seen = new Set(rows.map(row => row.id));
      S.convs = older ? [...S.convs, ...rows.filter(row => !S.convs.some(current => current.id === row.id))]
        : [...rows, ...S.convs.filter(row => !seen.has(row.id))];
      if (older || !S.listCursor) { S.listMore = !!cv.data.has_more; S.listCursor = cv.data.next_cursor || ''; }
    } else toast(cv.error?.message || '对话列表读取失败', { kind: 'error' });
    schedule();
    return st.data;
  }


  async function loadHistory() {
    if (!S.historyMore || S.historyBusy || !S.convId) return;
    const id = S.convId, request = S.convRequest;
    S.historyBusy = true; schedule();
    const beforeHeight = scroller.scrollHeight, beforeTop = scroller.scrollTop;
    const res = await get(`/api/agent/conversation?id=${encodeURIComponent(id)}&limit=20&cursor=${encodeURIComponent(S.historyCursor)}`);
    if (!S.alive || id !== S.convId || request !== S.convRequest) return;
    S.historyBusy = false;
    if (!res.ok) { toast(res.error?.message || '历史读取失败', { kind: 'error' }); schedule(); return; }
    S.items = mergeHistoryItems(historyItems(res.data.items), S.items);
    S.historyMore = !!res.data.has_more; S.historyCursor = res.data.next_cursor || ''; S.stick = false;
    paint();
    scroller.scrollTop = beforeTop + scroller.scrollHeight - beforeHeight;
  }
  async function loadRunEvents(id) {
    const run = S.items.find(item => item.run?.id === id)?.run;
    if (!run?.eventsMore || run.eventsBusy || run.following) return;
    run.eventsBusy = true; run.ver += 1; schedule();
    const res = await get(`/api/agent/events?run=${encodeURIComponent(id)}&after=${run.next}&limit=200&wait=0`);
    if (!S.alive) return;
    run.eventsBusy = false;
    if (!res.ok) toast(res.error?.message || '运行记录读取失败', { kind: 'error' });
    else {
      for (const ev of res.data.events || []) applyEvent(run, ev);
      run.next = res.data.next ?? run.next; run.eventsMore = !!res.data.has_more;
    }
    run.ver += 1; schedule();
  }
  return { loadList, loadHistory, loadRunEvents };
}
