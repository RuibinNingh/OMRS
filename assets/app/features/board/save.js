/**
 * 展示板保存队列（P7 第 2 步从 assets/board.js 搬来，行为不变）：
 * - 按字段记脏（items / print），去抖 500ms，合并成一次 POST /api/board/update；
 * - 在途保存串行化：flush 先等在途那次，再发下一次；
 * - 响应到达时，发送后又改过的字段以本地为准（boardAdoptSaved），并继续保存直到队列清空；
 * - 失败时把这次的字段放回脏队列、返回 false，依赖它的动作（切板、导出、记录纸面）随之中止。
 * 队列不读全局：当前板、请求、定时器与回调都由调用方注入；旧 board.js 经 boardSaveQueue() 懒创建唯一实例。
 */
import { boardDirtyMerge, boardSavePayload } from './model.js';

/** 保存响应与本地快照合并：发送后又改过的字段（dirty 里的）以本地为准，其余以服务端为准。 */
export function boardAdoptSaved(saved, live, dirty) {
  return { ...saved, ...(dirty?.print ? { print: live.print } : {}), ...(dirty?.items ? { items: live.items } : {}) };
}

/**
 * deps：
 * - detail() → 当前板（可为 null）；post(path, body) → Promise<{board}>；
 * - adopt(board, {hadPaper})：当前板仍是这次保存的板时，交回合并后的板；
 * - drained()：队列清空后调用（重新同步预览）；failed(error, options)：保存失败（options.silent 时不提示）；
 * - delay（默认 500）、setTimer / clearTimer（默认全局 setTimeout / clearTimeout）。
 */
export function createBoardSaveQueue(deps) {
  const { detail, post, adopt, drained = () => {}, failed = () => {}, delay = 500 } = deps;
  const setTimer = deps.setTimer || ((fn, ms) => setTimeout(fn, ms));
  const clearTimer = deps.clearTimer || (id => clearTimeout(id));
  const hasPaper = board => (((board && board.printed_summary) || {}).pages || 0) > 0;
  let dirty = null;
  let timer = null;
  let inFlight = null;
  let conflict = false;

  const queue = {
    /** 待保存的脏字段 {items?, print?}，没有时为 null。 */
    dirty: () => dirty,
    conflicted: () => conflict,
    discard() { dirty = null; conflict = false; clearTimer(timer); },
    /** 有待保存或在途的保存：预览不在这时重新导出。 */
    busy: () => !!(dirty || inFlight),
    mark(kind) {
      if (!detail()) return;
      dirty = boardDirtyMerge(dirty, kind);
      clearTimer(timer);
      if (!conflict) timer = setTimer(() => queue.flush(), delay);
    },
    /** 调用方自己整体提交了某个字段（如排序直接 POST items），把它从脏队列里拿掉。 */
    drop(kind) {
      if (!dirty?.[kind]) return;
      const rest = { ...dirty };
      delete rest[kind];
      dirty = Object.keys(rest).length ? rest : null;
    },
    /** 关页前：取出待保存的载荷交给 sendBeacon，并清空队列；没有时返回 null。 */
    takePayload() {
      const current = detail();
      if (conflict || !dirty || !current) return null;
      const sent = dirty;
      dirty = null;
      clearTimer(timer);
      return boardSavePayload(current, sent);
    },
    async flush(options = {}) {
      clearTimer(timer);
      if (conflict) return false;
      if (inFlight) {
        if (!(await inFlight)) return false;
        return queue.flush(options);
      }
      const sent = dirty;
      const current = detail();
      const payload = boardSavePayload(current, sent);
      if (!payload) return true;
      dirty = null;
      const hadPaper = hasPaper(current);
      const saving = (async () => {
        try {
          const result = await post('/api/board/update', payload);
          const live = detail();
          if (live?.id === payload.id) adopt(boardAdoptSaved(result.board, live, dirty), { hadPaper });
          return true;
        } catch (error) {
          dirty = { ...sent, ...(dirty || {}) };
          if (error.code === 'revision_conflict' || error.status === 409) conflict = true;
          failed(error, options);
          return false;
        }
      })();
      inFlight = saving;
      const ok = await saving;
      if (inFlight === saving) inFlight = null;
      if (!ok) return false;
      if (dirty) return queue.flush(options);
      drained();
      return true;
    },
  };
  return queue;
}
