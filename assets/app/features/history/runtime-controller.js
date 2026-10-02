/** 系统运行记录：分页、详情、请求竞争与进行中调用刷新。 */
import { fetchRuntimePage, fetchRuntimeDetail, fetchMcpOperation, decideMcpOperation } from '../../domain/history.js';

export function runtimeController(s, paint, filters, active) {
  let alive = true, request = 0, slow = 0, poll = 0;
  let loadedFilter = '', linkedSeq = null;
  const detailRequests = new Map();
  let operationRequest = 0;
  async function openOperation(id) {
    const mine = ++operationRequest;
    s.operationError = '';
    const result = await fetchMcpOperation(id);
    if (!alive || operationRequest !== mine) return;
    if (result.ok) { s.operation = result.operation; s.selectedSeq = null; }
    else { s.operation = null; s.operationError = result.error; }
    paint();
  }
  async function decide(id, decision) {
    if (s.operationBusy || !id) return;
    s.operationBusy = true; s.operationError = ''; paint();
    const result = await decideMcpOperation(id, decision);
    if (!alive) return;
    s.operationBusy = false;
    if (result.ok) {
      if (s.operation?.operation_id === id) s.operation = result.operation;
      s.details.clear();
      await load();
    } else s.operationError = result.error;
    paint();
  }
  async function detail(seq, force = false) {
    const key = String(seq);
    if (!force && (s.details.has(key) || detailRequests.has(key))) return;
    const ticket = Symbol();
    detailRequests.set(key, ticket);
    s.detailErrors.delete(key);
    const result = await fetchRuntimeDetail(seq);
    if (!alive || detailRequests.get(key) !== ticket) return;
    detailRequests.delete(key);
    if (result.ok) s.details.set(key, result.detail);
    else s.detailErrors.set(key, result.error);
    paint();
  }
  async function load(more = false) {
    if (more && (!s.hasMore || s.loadingMore)) return;
    const mine = ++request;
    const options = filters(), signature = JSON.stringify(options);
    const oldest = !more && signature === loadedFilter ? s.records.at(-1)?.seq : null;
    clearTimeout(slow); clearTimeout(poll);
    s.loadingMore = more;
    if (!s.records.length) slow = setTimeout(() => {
      if (alive && request === mine) { s.phase = 'loading'; paint(); }
    }, 300);
    let result = await fetchRuntimePage(more ? s.nextBeforeSeq : null, options);
    if (!alive || mine !== request) return;
    // 刷新覆盖已加载范围，进行中轮询不会丢掉用户已经翻到的旧记录。
    const summary = result.summary;
    while (result.ok && oldest != null && result.has_more && result.records.at(-1)?.seq > oldest) {
      const next = await fetchRuntimePage(result.next_before_seq, options);
      if (!alive || mine !== request) return;
      result = next.ok ? { ...next, records: [...result.records, ...next.records], summary } : next;
    }
    if (!alive || mine !== request) return;
    clearTimeout(slow);
    s.loadingMore = false;
    if (result.ok) {
      loadedFilter = signature;
      s.records = more ? [...s.records, ...result.records] : result.records;
      s.summary = result.summary; s.keys = result.keys;
      s.hasMore = result.has_more; s.nextBeforeSeq = result.next_before_seq;
      s.phase = 'ready'; s.error = '';
      if (s.selectedSeq !== linkedSeq && !s.records.some(row => row.seq === Number(s.selectedSeq))) s.selectedSeq = null;
      if (s.selectedSeq == null && s.records.length && !s.operation) s.selectedSeq = s.records[0].seq;
      if (s.selectedSeq != null) {
        const row = s.records.find(row => row.seq === Number(s.selectedSeq));
        const cached = s.details.get(String(s.selectedSeq));
        if (!more && (cached?.status === 'running' || (row && cached?.status !== row.status))) {
          void detail(s.selectedSeq, true);
        } else if (!cached) void detail(s.selectedSeq);
      }
    } else { s.error = result.error; s.phase = 'error'; }
    paint();
    if (active() && (s.summary.running || s.summary.pending_confirmation || s.summary.applying)) poll = setTimeout(() => {
      if (s.operation?.status === 'pending_confirmation' || s.operation?.status === 'applying') void openOperation(s.operation.operation_id);
      void load();
    }, 2500);
    return result;
  }
  return { load, detail, openOperation, decide,
    select(seq, linked = false) { s.operation = null; s.operationError = ''; linkedSeq = linked ? Number(seq) : null; s.selectedSeq = Number(seq); paint(); void detail(seq, s.detailErrors.has(String(seq))); },
    pause() { request++; clearTimeout(slow); clearTimeout(poll); s.loadingMore = false; },
    refresh() { if (s.selectedSeq != null) void detail(s.selectedSeq, true); return load(); },
    dispose() { alive = false; request++; operationRequest++; clearTimeout(slow); clearTimeout(poll); detailRequests.clear(); },
  };
}
