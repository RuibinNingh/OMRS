/**
 * 框选标注页的数据所有者：createAnnotateStore({ api, notify, timers }) 持有图片列表、当前图、画框角色、选中框、缩放与保存状态。
 * I/O 全部注入（api.get / api.post / api.upload），node 测试直接构造。每次改动调用 onChange 订阅者。
 * 保存：框位改动去抖 SAVE_DELAY 毫秒整体覆盖写 /api/annotate/save；同一时刻只有一个请求在途，期间的改动排到下一轮。
 */
import { cleanBox, createHistory, filterImages, nextTodo, stepId, transferBoxes, zoomStep } from './state.js';

export const SAVE_DELAY = 400;
export const UPLOAD_CHUNK = 8;
const message = result => result?.error?.message || '未知错误';

export function createAnnotateStore({ api, notify = () => {}, timers = globalThis } = {}) {
  const state = { images: [], cur: null, filter: 'all', role: 'question', sel: null, zoom: 1, loading: true, error: '',
    uploading: null, saving: 'idle', lastDone: null, picked: false };
  const history = createHistory();
  const listeners = new Set();
  const pending = new Map();   // id → { status? }
  const inflightIds = new Set();
  const blocked = new Set();   // 保存失败后保留本地框，等待用户核对并刷新
  let timer = null;
  let inflight = null;

  const emit = () => listeners.forEach(fn => fn(state));
  const current = () => state.images.find(image => image.id === state.cur) || null;
  const visible = () => filterImages(state.images, state.filter);

  function merge(image) {
    const index = state.images.findIndex(row => row.id === image.id);
    if (index >= 0) state.images[index] = { ...state.images[index], ...image, boxes: state.images[index].boxes };
    else state.images.push(image);
  }

  async function load() {
    state.loading = true; state.error = ''; emit();
    const result = await api.get('/api/annotate/images');
    state.loading = false;
    if (!result.ok) { state.error = `读取标注图片失败：${message(result)}`; emit(); return false; }
    const local = new Map(state.images.filter(image => pending.has(image.id) || inflightIds.has(image.id) || blocked.has(image.id))
      .map(image => [image.id, image]));
    state.images = (result.data?.images || []).map(image => local.get(image.id) || image);
    if (!current()) state.cur = nextTodo(state.images, null) || state.images[0]?.id || null;
    emit();
    return true;
  }

  /**
   * 上传队列：文件排进队列，每批 UPLOAD_CHUNK 张串行发出；每批回来就并入列表，所以可以边传边标。
   * 传的过程中还能继续拖入，追加到同一个队列；队列清空后只弹一条汇总。
   */
  const queue = [];
  let worker = null;
  let tally = { created: 0, dup: 0, failed: 0, error: '' };

  async function drain() {
    while (queue.length) {
      const chunk = queue.splice(0, UPLOAD_CHUNK);
      const result = await api.upload(chunk);
      const created = result.data?.images || [];
      created.forEach(merge);
      tally.created += created.length;
      tally.dup += (result.data?.duplicates || []).length;
      if (!result.ok) { tally.failed += chunk.length - created.length; tally.error = message(result); }
      if (!current() && created.length) state.cur = created[0].id;
      state.uploading.done += chunk.length;
      emit();
    }
    const { created, dup, failed, error } = tally;
    if (failed) notify(`已上传 ${created} 张，${failed} 张失败：${error}`, 'error');
    else notify(`已上传 ${created} 张${dup ? `，${dup} 张重复已跳过` : ''}`, created ? 'ok' : 'info');
    tally = { created: 0, dup: 0, failed: 0, error: '' };
    state.uploading = null;
    worker = null;
    emit();
    return !failed;
  }

  function upload(files) {
    const list = [...(files || [])];
    if (!list.length) return worker || Promise.resolve(false);
    queue.push(...list);
    state.uploading = { done: state.uploading?.done || 0, total: (state.uploading?.total || 0) + list.length };
    emit();
    if (!worker) worker = drain();
    return worker;
  }

  function schedule(id, status) {
    const entry = pending.get(id) || {};
    if (status) entry.status = status;
    pending.set(id, entry);
    state.saving = 'pending';
    timers.clearTimeout(timer);
    timer = timers.setTimeout(() => { flush(); }, SAVE_DELAY);
  }

  async function flush() {
    timers.clearTimeout(timer); timer = null;
    if (inflight) { await inflight; return pending.size ? flush() : true; }
    if (!pending.size) return true;
    if ([...pending.keys()].some(id => blocked.has(id))) { state.saving = 'error'; emit(); return false; }
    const batch = [...pending]; pending.clear();
    state.saving = 'saving'; emit();
    inflight = (async () => {
      let ok = true;
      for (const [id, entry] of batch) {
        const image = state.images.find(row => row.id === id);
        if (!image) continue;
        const body = { id, boxes: image.boxes.map(cleanBox), expected_revision: image.revision,
          ...(entry.status ? { status: entry.status } : {}) };
        inflightIds.add(id);
        const result = await api.post('/api/annotate/save', body);
        inflightIds.delete(id);
        if (result.ok) {
          image.revision = result.data?.image?.revision;
          if (!pending.has(id)) image.status = result.data?.image?.status || image.status;
          image.updated_at = result.data?.image?.updated_at || image.updated_at;
        } else {
          ok = false;
          blocked.add(id);
          if (!pending.has(id)) pending.set(id, entry);
          notify(`保存失败：${message(result)}；本页框位已保留，请核对后刷新`, 'error');
        }
      }
      return ok;
    })();
    const ok = await inflight;
    inflight = null;
    state.saving = pending.size ? (ok ? 'pending' : 'error') : 'idle';
    if (pending.size && ok) return flush();
    emit();
    return ok;
  }

  /** 改当前图的框：先记撤销快照，再整体替换并排队保存。 */
  function setBoxes(boxes, { select = state.sel } = {}) {
    const image = current();
    if (!image) return;
    history.record(image.id, image.boxes);
    image.boxes = boxes.map(cleanBox);
    state.sel = select != null && select < image.boxes.length ? select : null;
    schedule(image.id);
    emit();
  }

  /** 拖动结束时由画布调用：before 是按下时的快照，框已在原地改过。 */
  function commitGesture(before) {
    const image = current();
    if (!image) return;
    if (JSON.stringify(before) === JSON.stringify(image.boxes)) { emit(); return; }
    history.record(image.id, before);
    image.boxes = image.boxes.map(cleanBox);
    schedule(image.id);
    emit();
  }

  function swap(boxes) {
    const image = current();
    if (!image || !boxes) return false;
    image.boxes = boxes; state.sel = null;
    schedule(image.id); emit();
    return true;
  }

  function open(id) {
    if (!id || id === state.cur) return;
    state.cur = id; state.sel = null;
    flush();
    emit();
  }

  return {
    state, current, visible, load, upload, flush, setBoxes, commitGesture, open,
    hasPending: () => pending.size > 0 || !!inflight,
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    emit,
    setRole(role) {
      state.role = role;
      const image = current();
      // 只改「点选 / Tab 选中」的框；刚画完的框也处于选中（方便拖把手），但按 Q / A 只是切换下一个框的角色
      if (image && state.picked && state.sel != null && image.boxes[state.sel] && image.boxes[state.sel].role !== role) {
        setBoxes(image.boxes.map((box, i) => (i === state.sel ? { ...box, role } : box)));
        return;
      }
      emit();
    },
    select(index) { state.sel = index; state.picked = index != null; emit(); },
    cycle(step) {
      const count = current()?.boxes.length || 0;
      if (!count) return;
      state.sel = state.sel == null ? (step > 0 ? 0 : count - 1) : (state.sel + step + count) % count;
      state.picked = true;
      emit();
    },
    removeSelected() {
      const image = current();
      if (!image || state.sel == null) return false;
      setBoxes(image.boxes.filter((_, i) => i !== state.sel), { select: null });
      return true;
    },
    clearBoxes() { const image = current(); if (image?.boxes.length) setBoxes([], { select: null }); },
    fullImage() { const image = current(); if (image) setBoxes([...image.boxes, { role: state.role, x: 0, y: 0, w: 1, h: 1 }], { select: image.boxes.length }); },
    copyPrevious() {
      const image = current();
      const source = state.images.find(row => row.id === state.lastDone && row.id !== image?.id)
        || [...state.images].reverse().find(row => row.id !== image?.id && row.status === 'done' && row.boxes.length);
      if (!image || !source) { notify('还没有可沿用的已完成图片', 'warn'); return false; }
      setBoxes(transferBoxes(source, image), { select: null });
      notify(`已沿用「${source.file || source.id}」的 ${source.boxes.length} 个框`);
      return true;
    },
    undo() { const image = current(); return !!image && swap(history.undo(image.id, image.boxes)); },
    redo() { const image = current(); return !!image && swap(history.redo(image.id, image.boxes)); },
    step(delta) { open(stepId(visible(), state.cur, delta)); },
    setFilter(filter) {
      state.filter = filter;
      const list = visible();
      if (list.length && !list.some(image => image.id === state.cur)) { open(list[0].id); return; }
      emit();
    },
    zoom(direction) { state.zoom = zoomStep(state.zoom, direction); emit(); },
    /** 完成当前图并跳到下一张未完成；allowEmpty=false 时没有框就不完成。 */
    async finish({ allowEmpty = false } = {}) {
      const image = current();
      if (!image) return false;
      if (!image.boxes.length && !allowEmpty) {
        notify('这张还没有框：画好再按 Enter；确实没有题目就按 Shift + Enter 标为空白样本', 'warn');
        return false;
      }
      image.status = 'done';
      state.lastDone = image.boxes.length ? image.id : state.lastDone;
      schedule(image.id, 'done');
      const next = nextTodo(state.images, image.id);
      if (next) open(next);
      else { flush(); notify('全部图片都已完成', 'ok'); emit(); }
      return true;
    },
    reopen() {
      const image = current();
      if (!image || image.status !== 'done') return;
      image.status = 'todo'; schedule(image.id, 'todo'); emit();
    },
    async removeImage() {
      const image = current();
      if (!image) return false;
      if (!(await flush())) return false;
      pending.delete(image.id);
      const result = await api.post('/api/annotate/delete', { id: image.id, expected_revision: image.revision });
      if (!result.ok) { notify(`删除失败：${message(result)}`, 'error'); return false; }
      const list = visible();
      const index = list.findIndex(row => row.id === image.id);
      state.images = state.images.filter(row => row.id !== image.id);
      const rest = visible();
      state.cur = rest[Math.min(index, rest.length - 1)]?.id || state.images[0]?.id || null;
      state.sel = null;
      notify(`已删除「${image.file || image.id}」`);
      emit();
      return true;
    },
  };
}
