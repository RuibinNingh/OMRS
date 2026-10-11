/** 助手列表、成组历史与运行事件分页；响应只归入仍有效的页面。 */
import { get } from '../../core/api.js';
import { toast } from '../../ui/toast.js';
import { applyEvent, historyItems, mergeHistoryItems } from './state.js';

export function createAssistantHistory(S, { schedule, paint, scroller, notify = toast }) {
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
    } else notify(cv.error?.message || '对话列表读取失败', { kind: 'error' });
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
    if (!res.ok) { notify(res.error?.message || '历史读取失败', { kind: 'error' }); schedule(); return; }
    S.items = mergeHistoryItems(historyItems(res.data.items), S.items);
    S.historyMore = !!res.data.has_more; S.historyCursor = res.data.next_cursor || ''; S.stick = false;
    paint();
    scroller.scrollTop = beforeTop + scroller.scrollHeight - beforeHeight;
  }
  async function loadRunEvents(id) {
    const run = S.items.find(item => item.run?.id === id)?.run;
    if (!S.alive || !run?.eventsMore || run.eventsBusy || run.following) return;
    const conversation = S.convId, request = S.convRequest;
    const current = () => S.alive && conversation === S.convId && request === S.convRequest
      && S.items.some(item => item.run === run);
    S.traceClosed.delete(id);
    run.eventsBusy = true; run.ver += 1; schedule();
    try {
      // 一次操作读到末页；每次请求仍有界，失败保留已读游标供重试。
      while (current() && run.eventsMore) {
        const after = run.next;
        const res = await get(`/api/agent/events?run=${encodeURIComponent(id)}&after=${after}&limit=500&wait=0`);
        if (!current()) return;
        if (!res.ok) { notify(res.error?.message || '运行记录读取失败', { kind: 'error' }); break; }
        const events = res.data.events || [], next = res.data.next;
        if (res.data.has_more && (!events.length || !Number.isSafeInteger(next) || next <= after)) {
          notify('运行记录读取未能继续，请重试', { kind: 'error' }); break;
        }
        for (const ev of events) applyEvent(run, ev);
        run.next = next ?? run.next; run.eventsMore = !!res.data.has_more;
        run.ver += 1; schedule();
      }
    } finally {
      run.eventsBusy = false; run.ver += 1;
      if (S.alive && S.items.some(item => item.run === run)) schedule();
    }
  }
  return { loadList, loadHistory, loadRunEvents };
}
