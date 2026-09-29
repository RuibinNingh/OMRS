/**
 * 收件箱数据所有者（只有录入页用，留在 feature 里）：图片列表、勾选、当前图与画框状态、保存队列、后台任务轮询。
 * I/O 全部注入：api.{get,post} 返回 core/api 的 { ok, data, error }；emit(type) 发通知；notify(text, kind, action) 出提示；
 * timers 提供 setTimeout / clearTimeout / setInterval / clearInterval。真实单例在 inbox.js，node 测试直接构造。
 *
 * 每次保存冻结字段补丁，按服务端 revision 串行写入；失败时保留本地编辑并停止该图的后续写入。
 * load() 只更新没有本地编辑的图片；不同字段的服务端改动可安全合并，同字段冲突交由用户核对。
 */
export const STATUS_NAMES = Object.freeze({ pending: '待处理', boxed: '已框选', ready: '待创建', done: '已录入', discarded: '已丢弃' });

export function mergePatch(a = {}, b = {}) {
  const merged = { ...a, ...b };
  if ('cards' in a || 'cards' in b) merged.cards = { ...(a.cards || {}), ...(b.cards || {}) };
  return merged;
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
  const pending = { timers: new Map(), patches: new Map(), chains: new Map(), base: new Map(), fresh: new Map(), blocked: new Map() };
  const polls = new Map();
  const resetting = new Set();
  let loadRequest = 0;
  let appliedLoad = 0;

  const item = id => state.items.find(row => row.id === id) || null;
  const current = () => item(state.cur);
  const live = () => state.items.filter(row => row.status !== 'discarded');
  const queue = () => live().filter(row => row.status !== 'done');
  const changed = () => emit('inbox:changed');
  const copy = value => JSON.parse(JSON.stringify(value));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const dirty = id => pending.patches.has(id) || pending.chains.has(id) || pending.blocked.has(id);
  const snapshot = target => Object.fromEntries(['regions', 'layout', 'status', 'cards']
    .filter(key => target[key] !== undefined).map(key => [key, copy(target[key])]));
  const difference = (target, base) => Object.fromEntries(['regions', 'layout', 'status', 'cards']
    .filter(key => target[key] !== undefined && !same(target[key], base?.[key]))
    .map(key => [key, copy(target[key])]));
  const fields = (target, patch) => {
    if (Object.keys(patch).length) return copy(patch);
    return difference(target, pending.base.get(target.id) || {});
  };
  function overlay(local, fresh, patch) {
    const applied = { ...fresh, ...patch };
    if (patch.cards) applied.cards = { ...(fresh.cards || {}), ...patch.cards };
    Object.assign(local, applied);
  }
  function canRebase(base, fresh, patch) {
    return base?.reset_epoch === fresh?.reset_epoch && Object.keys(patch).every(key => {
      if (key === 'cards') return Object.keys(patch.cards).every(card => same(base.cards?.[card], fresh.cards?.[card]));
      return same(base[key], fresh[key]);
    });
  }
  function acceptFresh(fresh) {
    const id = fresh.id;
    const index = state.items.findIndex(row => row.id === id);
    const local = index < 0 ? null : state.items[index];
    if (!local) { state.items.push(fresh); pending.base.set(id, copy(fresh)); return; }
    const knownRevision = Math.max(pending.base.get(id)?.revision ?? -1,
      pending.fresh.get(id)?.revision ?? -1, local.revision ?? -1);
    if (fresh.revision < knownRevision) return;
    // 请求中或画框中先保留较新的服务端版本；替换对象会把手势写到旧对象上。
    if (pending.chains.has(id) || (state.dragging && state.cur === id)) {
      const held = pending.fresh.get(id);
      if (!held || fresh.revision >= held.revision) pending.fresh.set(id, copy(fresh));
      return;
    }
    pending.fresh.delete(id);
    const patch = pending.patches.get(id);
    const base = pending.base.get(id) || local;
    if (patch && !canRebase(base, fresh, patch)) {
      pending.blocked.set(id, 'conflict');
      notify(`${local.file || id} 已在后台改动，本地编辑仍保留；请核对后重试`, 'warn');
      return;
    }
    pending.base.set(id, copy(fresh));
    if (patch) overlay(local, fresh, patch);
    else state.items[index] = fresh;
  }

  async function load() {
    const request = ++loadRequest;
    const result = await api.get('/api/inbox/items');
    if (result.ok) {
      if (request < appliedLoad) return true;
      appliedLoad = request;
      const fresh = Array.isArray(result.data?.items) ? result.data.items : [];
      const ids = new Set(fresh.map(row => row.id));
      state.items = state.items.filter(row => ids.has(row.id) || dirty(row.id));
      fresh.forEach(acceptFresh);
    } else notify(`读取收件箱失败：${result.error?.message || '未知错误'}`, 'warn');
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
    const merged = mergePatch(pending.patches.get(id) || {}, fields(target, patch));
    const sentLocal = snapshot(target);
    pending.patches.delete(id);
    if (!Object.keys(merged).length) return pending.chains.get(id) || Promise.resolve(pending.blocked.has(id) ? null : target);
    const previous = pending.chains.get(id) || Promise.resolve();
    const run = previous.catch(() => null).then(async () => {
      if (pending.blocked.has(id)) {
        pending.patches.set(id, mergePatch(pending.patches.get(id) || {}, merged));
        return null;
      }
      let base = pending.base.get(id) || target;
      let result = await api.post('/api/inbox/item/update', { id, ...merged,
        expected_revision: base.revision, reset_epoch: base.reset_epoch });
      if (!result.ok && result.status === 409) {
        const latest = await api.get(`/api/inbox/item?id=${encodeURIComponent(id)}`);
        if (latest.ok && latest.data?.item && canRebase(base, latest.data.item, merged)) {
          base = latest.data.item;
          pending.base.set(id, copy(base));
          const local = item(id);
          if (local && !(state.dragging && state.cur === id)) {
            const later = mergePatch(difference(local, sentLocal), pending.patches.get(id) || {});
            overlay(local, base, mergePatch(merged, later));
          }
          result = await api.post('/api/inbox/item/update', { id, ...merged,
            expected_revision: base.revision, reset_epoch: base.reset_epoch });
        }
      }
      if (!result.ok || !result.data?.item) {
        pending.patches.set(id, mergePatch(merged, pending.patches.get(id) || {}));
        pending.blocked.set(id, result.status === 409 ? 'conflict' : 'failed');
        notify(`保存失败：${result.error?.message || '请核对本地编辑后重试'}`, 'warn',
          result.status === 409 ? null : { label: '重试保存', onClick: () => retry(id) });
        changed();
        return null;
      }
      const saved = result.data.item;
      const index = state.items.findIndex(row => row.id === id);
      if (state.dragging && state.cur === id) {
        // 手势结束时会排入完整框位；此处不能替换正在拖动的 region 对象。
        pending.base.set(id, copy(saved));
        changed();
        return saved;
      }
      const later = index < 0 ? {} : mergePatch(difference(state.items[index], sentLocal), pending.patches.get(id) || {});
      const held = pending.fresh.get(id);
      pending.fresh.delete(id);
      let accepted = saved;
      if (held && held.revision > saved.revision) {
        if (!canRebase(saved, held, later)) {
          pending.base.set(id, copy(held));
          pending.patches.set(id, mergePatch(later, pending.patches.get(id) || {}));
          pending.blocked.set(id, 'conflict');
          notify(`${item(id)?.file || id} 已在后台改动，本地编辑仍保留；请核对后重试`, 'warn');
          changed();
          return null;
        }
        accepted = held;
      }
      pending.base.set(id, copy(accepted));
      if (index >= 0) {
        if (Object.keys(later).length) overlay(state.items[index], accepted, later);
        else state.items[index] = accepted;
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
    const merged = mergePatch(pending.patches.get(id) || {}, fields(target, patch));
    if (!Object.keys(merged).length) return;
    pending.patches.set(id, merged);
    timers.clearTimeout(pending.timers.get(id));
    pending.timers.set(id, timers.setTimeout(() => { save(target); }, delay));
  }

  async function flush() {
    for (;;) {
      const ids = [...pending.patches.keys()];
      ids.forEach(id => { if (!pending.blocked.has(id)) save(item(id)); });
      await Promise.all([...pending.chains.values()]);
      if ([...pending.blocked.keys()].length) return false;
      if (!pending.patches.size && !pending.chains.size) return true;
      if (!pending.patches.size) { await Promise.resolve(); continue; }
    }
  }
  const unsaved = () => new Set([...pending.patches.keys(), ...pending.chains.keys(), ...pending.blocked.keys()]).size;
  function retry(id) {
    if (pending.blocked.get(id) === 'conflict') return Promise.resolve(null);
    pending.blocked.delete(id);
    return save(item(id));
  }

  async function reset(id) {
    if (!id || resetting.has(id)) return null;
    resetting.add(id);
    timers.clearTimeout(pending.timers.get(id));
    pending.timers.delete(id);
    pending.patches.delete(id);
    await pending.chains.get(id);
    pending.patches.delete(id);
    pending.blocked.delete(id);
    try {
      const base = pending.base.get(id) || item(id);
      const result = await api.post('/api/inbox/item/reset', { id, expected_revision: base?.revision,
        reset_epoch: base?.reset_epoch });
      if (!result.ok) { notify(`重置失败：${result.error?.message || '未知错误'}`, 'warn'); await load(); return null; }
      const fresh = result.data?.item;
      const index = state.items.findIndex(row => row.id === id);
      if (fresh && index >= 0) { state.items[index] = fresh; pending.base.set(id, copy(fresh)); }
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
    state, item, current, live, queue, changed, load, save, saveSoon, flush, unsaved, reset, retry, job, go, open,
    counts: () => inboxCounts(state.items),
    polling: () => polls.size,
  };
}
