/**
 * 收件箱数据所有者（只有录入页用，留在 feature 里）：图片列表、勾选、当前图与画框状态、保存队列、后台任务轮询。
 * I/O 全部注入：api.{get,post} 返回 core/api 的 { ok, data, error }；emit(type) 发通知；notify(text, kind, action) 出提示；
 * timers 提供 setTimeout / clearTimeout / setInterval / clearInterval。真实单例在 inbox.js，node 测试直接构造。
 *
 * 保存队列沿用旧 ibSaveSoon 的语义：同一张图的补丁在防抖期内合并（cards 按题卡合并），同一张图的请求串行；
 * 每次改动递增修订号，响应只在修订号未变时回写服务端版本，免得覆盖请求发出后的本地改动。flush() 立即写出全部待存改动。
 */
export const STATUS_NAMES = Object.freeze({ pending: '待处理', boxed: '已框选', ready: '待创建', done: '已录入', discarded: '已丢弃' });

export function mergePatch(a = {}, b = {}) {
  return { ...a, ...b, cards: { ...(a.cards || {}), ...(b.cards || {}) } };
}

export function inboxCounts(items = []) {
  const live = items.filter(item => item.status !== 'discarded');
  const count = status => live.filter(item => item.status === status).length;
  return { pending: count('pending'), boxed: count('boxed'), ready: count('ready') };
}

export function createInboxStore({ api, emit = () => {}, notify = () => {}, timers = globalThis, pollMs = 1200 } = {}) {
  const state = {
    items: [], cur: null, sel: new Set(), csel: new Set(), stage: 'upload',
    drawRole: 'question', selR: null, drawCard: 1, dragging: false, loaded: false,
  };
  const pending = { timers: new Map(), patches: new Map(), items: new Map(), chains: new Map(), revisions: new Map() };
  const polls = new Map();
  const resetting = new Set();

  const item = id => state.items.find(row => row.id === id) || null;
  const current = () => item(state.cur);
  const live = () => state.items.filter(row => row.status !== 'discarded');
  const queue = () => live().filter(row => row.status !== 'done');
  const changed = () => emit('inbox:changed');
  const bump = id => { const next = (pending.revisions.get(id) || 0) + 1; pending.revisions.set(id, next); return next; };

  async function load() {
    const result = await api.get('/api/inbox/items');
    if (result.ok) state.items = Array.isArray(result.data?.items) ? result.data.items : [];
    else { notify(`读取收件箱失败：${result.error?.message || '未知错误'}`, 'warn'); state.items = []; }
    const ids = new Set(live().map(row => row.id));
    for (const id of [...state.sel]) if (!ids.has(id)) state.sel.delete(id);
    if (state.cur && !ids.has(state.cur)) state.cur = null;
    state.loaded = true;
    changed();
    return result.ok;
  }

  function save(target, patch = {}) {
    if (!target) return Promise.resolve(null);
    const id = target.id;
    timers.clearTimeout(pending.timers.get(id));
    pending.timers.delete(id);
    const merged = mergePatch(pending.patches.get(id) || {}, patch);
    const local = pending.items.get(id) || target;
    const resetEpoch = local.reset_epoch;
    pending.patches.delete(id);
    pending.items.delete(id);
    const revision = bump(id);
    const previous = pending.chains.get(id) || Promise.resolve();
    const run = previous.catch(() => null).then(async () => {
      const result = await api.post('/api/inbox/item/update', { id, regions: local.regions, layout: local.layout, ...merged, reset_epoch: resetEpoch });
      if (!result.ok) { if (pending.revisions.get(id) === revision) notify(`保存失败：${result.error?.message || '未知错误'}`, 'warn'); return null; }
      const saved = result.data?.item || null;
      const index = state.items.findIndex(row => row.id === id);
      if (saved && index >= 0 && pending.revisions.get(id) === revision) {
        // 正在拖动这张图的框时只同步状态：替换对象会让手势改到脱离列表的旧区域上。
        if (state.dragging && state.cur === id) state.items[index].status = saved.status;
        else state.items[index] = saved;
      }
      changed();
      return saved;
    });
    pending.chains.set(id, run);
    run.finally(() => { if (pending.chains.get(id) === run) pending.chains.delete(id); });
    return run;
  }

  function saveSoon(target, patch = {}, delay = 500) {
    if (!target) return;
    const id = target.id;
    bump(id);
    pending.patches.set(id, mergePatch(pending.patches.get(id) || {}, patch));
    pending.items.set(id, target);
    timers.clearTimeout(pending.timers.get(id));
    pending.timers.set(id, timers.setTimeout(() => { save(target); }, delay));
  }

  const flush = () => Promise.all([...pending.patches.keys()].map(id => save(pending.items.get(id))));
  const unsaved = () => pending.patches.size;

  async function reset(id) {
    if (!id || resetting.has(id)) return null;
    resetting.add(id);
    timers.clearTimeout(pending.timers.get(id));
    pending.timers.delete(id);
    pending.patches.delete(id);
    pending.items.delete(id);
    pending.chains.delete(id);
    bump(id);
    try {
      const result = await api.post('/api/inbox/item/reset', { id });
      if (!result.ok) { notify(`重置失败：${result.error?.message || '未知错误'}`, 'warn'); await load(); return null; }
      const fresh = result.data?.item;
      const index = state.items.findIndex(row => row.id === id);
      if (fresh && index >= 0) state.items[index] = fresh;
      changed();
      return fresh || null;
    } finally { resetting.delete(id); }
  }

  /** 提交后台任务并每 pollMs 轮询一次；完成时调 onDone(job)。提交失败抛出，由调用方提示。 */
  async function job(type, payload, onDone, onError) {
    const created = await api.post('/api/inbox/jobs', { type, ...payload });
    if (!created.ok) throw new Error(created.error?.message || '未知错误');
    const id = created.data?.job?.id;
    let inFlight = false;
    const stop = () => { timers.clearInterval(polls.get(id)); polls.delete(id); };
    polls.set(id, timers.setInterval(async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const result = await api.get(`/api/inbox/job?id=${encodeURIComponent(id)}`);
        if (!result.ok) throw new Error(result.error?.message || '未知错误');
        const task = result.data?.job || {};
        if (task.done || task.status === 'done' || task.status === 'error') {
          stop();
          if ((task.errors || []).length) notify(`${type} 有 ${task.errors.length} 个失败：${task.errors[0].msg}`, 'warn');
          if (onDone) await onDone(task);
        }
      } catch (error) {
        stop();
        notify(`读取任务进度或同步结果失败：${error.message || error}`, 'warn');
        if (onError) await onError(error);
      } finally { inFlight = false; }
    }, pollMs));
    return id;
  }

  /** 切换工作区；离开处理区时立即写出未到防抖时间的框位。 */
  function go(stage) {
    if (state.stage === 'process' && stage !== 'process') flush();
    state.stage = stage;
    if (stage === 'process' && !current()) state.cur = queue()[0]?.id || null;
    changed();
  }

  function open(id) {
    state.cur = id;
    state.selR = null;
    state.drawCard = 1;
    changed();
  }

  return {
    state, item, current, live, queue, changed, load, save, saveSoon, flush, unsaved, reset, job, go, open,
    counts: () => inboxCounts(state.items),
    polling: () => polls.size,
  };
}
