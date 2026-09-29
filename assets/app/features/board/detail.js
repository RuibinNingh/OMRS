/**
 * 展示板「板详情」的控制器（P7 第 6 轮起；原 assets/board.js 的 BOARD_DETAIL / BOARD_PRINT_MODE / BOARD_SELECTED_UID、
 * 数据加载与详情上的全部操作，旧文件已删）。
 * - 状态：当前板详情、打印范围（'all' | 'new'）、选中题、视图（纸面 / 列表 / 画廊，只存本地）、预览最近一次失败原因、加载序号。
 *   snapshot() 给页面画状态条、舞台、列表 / 画廊与检查器；onDetail(fn) 订阅变化（展示板页挂着时重绘）。
 * - 子控制器：保存队列 save.js、打印协调 print.js、版面设置 settings.js 都在这里懒创建并注入回调；常驻预览经 deps.preview。
 * - I/O 全部经 deps（createBoardDetail(deps) 要给全），node 单测注入替身；浏览器里的缺省 I/O、模块单例 boardDetail()、
 *   接到 domain/board/detail-port.js 的端口与窗口级监听在 runtime.js。请求沿用旧 api() 的语义（成功返回数据、失败抛 Error）。
 * - 板列表归 domain/board/boards.js（adoptBoards、boardRemember 等），这里只在重读 / 加载时采纳与记住当前板。
 */
import { boardUniqueUids } from '../../domain/board/model.js';
import { adoptBoards, boardRemember, boardPreferredId, boardCurrentId } from '../../domain/board/boards.js';
import { boardStatusModel, boardMoveItems, boardItemsPayload, boardItemsSignature, boardGapMap, boardSortItems, boardPaperSummary as paperSummary } from './model.js';
import { createBoardSaveQueue } from './save.js';
import { createBoardPrint } from './print.js';
import { createBoardSettings } from './settings.js';
import { syncBody } from './view.js';

export const BOARD_VIEW_KEY = 'omrs-board-view';
const clamp = (value, lo, hi, fallback) => (value === '' || value == null || !Number.isFinite(Number(value)) ? fallback : Math.max(lo, Math.min(hi, Number(value))));

export function createBoardDetail(initialDeps = {}) {
  let deps = { ...initialDeps };
  const st = { detail: null, mode: 'all', selected: '', previewError: '', seq: 0 };
  const listeners = new Set();
  let save = null;
  let print = null;
  let settings = null;
  let previewBound = false;

  const items = () => st.detail?.items || [];
  const itemOf = uid => items().find(item => item.uid === uid || item.question_id === uid) || null;
  const hasPaper = board => paperSummary(board || st.detail).pages > 0;
  const toast = (text, options) => deps.toast(text, options);

  /** 只重绘（状态条、检查器、读数）。 */
  function changed() {
    listeners.forEach(fn => { try { fn(); } catch (error) { console.error('[board] 详情订阅出错', error); } });
  }
  /** 重绘 + 同步常驻预览（旧 boardRender）。 */
  function render() { changed(); syncPreview(); }

  // ---------- 视图（只存本地） ----------
  function view() {
    try { const value = deps.storage()?.getItem(BOARD_VIEW_KEY); return value === 'list' || value === 'gallery' ? value : 'paper'; } catch (error) { return 'paper'; }
  }
  function setView(next) {
    const value = next === 'list' || next === 'gallery' ? next : 'paper';
    try { deps.storage()?.setItem(BOARD_VIEW_KEY, value); } catch (error) { /* 隐私模式 */ }
    render();
  }

  // ---------- 子控制器 ----------
  function saveQueue() {
    if (!save) save = createBoardSaveQueue({
      detail: () => st.detail,
      post: (path, body) => deps.post(path, body),
      adopt: (board, { hadPaper }) => {
        st.detail = board;
        boardSettings().revoke();
        if (hadPaper && !hasPaper(st.detail)) render();
      },
      drained: () => { changed(); syncPreview(); },
      failed: (error, options) => { if (!options.silent) toast(`保存展示板失败：${error.message}`, { kind: 'error' }); },
      setTimer: (fn, ms) => deps.setTimer(fn, ms),
      clearTimer: id => deps.clearTimer(id),
    });
    return save;
  }
  const flush = (options = {}) => saveQueue().flush(options);
  const markDirty = kind => { saveQueue().mark(kind); changed(); };

  function boardSettings() {
    if (!settings) settings = createBoardSettings({
      detail: () => st.detail,
      confirm: (title, options) => deps.confirm(title, options),
      markDirty: kind => markDirty(kind),
      flush: () => flush(),
      relayout: () => pushRelayout(),
      // 输入框、滑杆的值由 morph 保留（聚焦的控件不改值），读数与继承的单题留白跟着重绘即可
      printApplied: () => changed(),
      // 被拒（锁定时取消确认）：聚焦中的控件 morph 不改值，先让页面放掉焦点再重绘，控件才回到旧值
      printRejected: () => { deps.rejected?.(); changed(); },
      gapRejected: () => { deps.rejected?.(); changed(); },
      gapApplied: () => changed(),
    });
    return settings;
  }

  /** 导出用的打印范围与状态条显示的是同一个判断（记录纸面后 mode 仍是 'new' 而新增数已归零时按全部导出）。 */
  const effectiveMode = () => boardStatusModel(st.detail, st.mode, null).scope;

  function boardPrint() {
    if (!print) print = createBoardPrint({
      detail: () => st.detail,
      mode: () => effectiveMode(),
      flush: () => flush(),
      post: (path, body) => deps.post(path, body),
      reload: () => reloadData(),
      renderStatus: () => changed(),
      toast: (text, options) => toast(text, options),
      confirm: (title, options) => deps.confirm(title, options),
      previewLayout: () => deps.preview.boardPreviewLayout?.() || null,
      recorded: (board, boardId) => { if (boardCurrentId() === boardId) { st.detail = board; st.mode = 'new'; } },
      reset: board => { st.detail = board; st.mode = 'all'; },
    });
    return print;
  }

  // ---------- 常驻预览 ----------
  function bindPreview() {
    if (previewBound || typeof deps.preview.boardPreviewOn !== 'function') return;
    previewBound = true;
    deps.preview.boardPreviewOn({
      onLayout: () => changed(),                                   // 翻页条页码 / 页数
      onSelect: message => { if (message?.uid) { select(message.uid); deps.onPaperSelect?.(message.uid); } },
      onGap: message => applyGapDrag(message.uid, message.lines),
    });
  }
  function syncPreview(options = {}) {
    if (typeof deps.preview.boardPreviewSetBoard !== 'function') return;
    if (saveQueue().busy()) return;
    if (!st.detail || view() !== 'paper' || !deps.pageActive()) return;
    bindPreview();
    const fingerprint = {
      signature: [boardItemsSignature(st.detail.items), st.detail.print?.answers, st.detail.print?.show_labels].join('|'),
      printedAt: paperSummary(st.detail).at || '',
      force: !!options.force,
    };
    deps.preview.boardPreviewSetBoard(st.detail.id, effectiveMode(), fingerprint).then(() => {
      if (st.previewError) { st.previewError = ''; changed(); }
    }, error => {
      st.previewError = error?.message || String(error);   // 翻页条显示原因；下一次同步成功后清掉
      changed();
    });
  }
  /** 几何类改动：只让 iframe 重排，全程不发请求。 */
  function pushRelayout() {
    if (!st.detail || typeof deps.preview.boardPreviewRelayout !== 'function') return;
    deps.preview.boardPreviewRelayout(st.detail.print || {}, boardGapMap(st.detail.items));
  }
  /** 人工兜底：题目正文在应用外改过、预览还是旧的时强制重新生成。 */
  async function regen() {
    if (!st.detail) return;
    if (!(await flush())) return;
    deps.preview.boardPreviewInvalidate?.();
    syncPreview({ force: true });
    toast('正在按最新正文重新生成纸面…');
  }

  // ---------- 数据加载 ----------
  // 收件箱录完题会同时触发全局 reloadData() 和「加入展示板」，两条链都会重读展示板；序号保证先发后到的旧响应不盖新数据。
  async function reloadData() {
    if (!(await flush())) return;
    deps.preview.boardPreviewInvalidate?.();
    const seq = ++st.seq;
    try {
      const result = await deps.get('/api/boards');
      if (seq !== st.seq) return;
      adoptBoards({ boards: result.boards || [], folders: result.folders || [] });
      if (boardCurrentId() && !(result.boards || []).some(board => board.id === boardCurrentId())) {
        st.detail = null;
        boardRemember('');
      }
      const selected = boardPreferredId();
      if (selected) {
        await load(selected, false, seq);
        if (seq !== st.seq) return;
      } else {
        st.detail = null;
        boardRemember('');
      }
    } catch (error) {
      if (seq !== st.seq) return;
      adoptBoards({ boards: [], folders: [] });
      st.detail = null;
    }
    boardSettings().revoke();
    render();
  }
  async function load(id, repaint = true, seq = null) {
    if (!id) return;
    if (!(await flush())) return;   // 保存失败留在原板，保留待重试的编辑
    const token = seq ?? ++st.seq;
    try {
      const result = await deps.get(`/api/board?id=${encodeURIComponent(id)}`);
      if (token !== st.seq) return;
      st.detail = result.board || null;
      boardRemember(id);
      if (!items().some(item => item.uid === st.selected)) st.selected = '';
      if (st.mode === 'new' && !hasPaper()) st.mode = 'all';
      if (repaint) render();
    } catch (error) {
      if (token !== st.seq) return;
      toast(`读取展示板失败：${error.message}`, { kind: 'error' });
    }
  }

  // ---------- 加题（六处入口统一走这里） ----------
  async function addToBoard(boardId, uids, options = {}) {
    const clean = boardUniqueUids(uids);
    if (!clean.length || !boardId) return null;
    if (!(await flush())) return null;
    try {
      const result = await deps.post('/api/board/items/add', { id: boardId, uids: clean });
      const board = result.board;
      boardRemember(board.id);
      if (boardCurrentId() === board.id) st.detail = board;
      await reloadData();
      if (options.goto) deps.gotoBoard();
      const addedUids = board.added_uids || [];
      const added = Number(board.added ?? addedUids.length);
      const actions = [];
      if (addedUids.length) actions.push({ label: '撤销', onClick: () => deps.post('/api/board/items/remove', { id: board.id, uids: addedUids }).then(reloadData).then(() => toast('已撤销加入')) });
      if (boardCurrentId() !== board.id || !deps.pageActive()) {
        actions.push({ label: '打开展示板', onClick: () => { deps.gotoBoard(); load(board.id); } });
      }
      const done = options.moveFromName
        ? `已从《${options.moveFromName}》移到《${board.name}》`
        : `已加入《${board.name}》（现共 ${(board.items || []).length} 题）`;
      if (!options.silent) toast(added ? done : `这些题已经在《${board.name}》里了`, { actions, kind: added ? 'ok' : 'warn' });
      return board;
    } catch (error) { toast(`加入展示板失败：${error.message}`, { kind: 'error' }); return null; }
  }

  // ---------- 条目操作 ----------
  async function removeItem(uid) {
    if (!st.detail) return;
    if (!(await flush())) return;
    const item = itemOf(uid);
    try {
      const boardId = st.detail.id;
      const result = await deps.post('/api/board/items/remove', { id: boardId, uids: [uid] });
      st.detail = result.board;
      await reloadData();
      toast(`已移除 ${uid}${item?.printed ? '（纸上仍有这道题，纸面记录保留其占位）' : ''}`, { actions: [{ label: '撤销', onClick: () => addToBoard(boardId, [uid], { silent: true }) }] });
    } catch (error) { toast(`移除失败：${error.message}`, { kind: 'error' }); }
  }
  async function persistItems(list, message = '') {
    if (!st.detail) return;
    if (!(await flush())) return;
    if (!(await boardSettings().allow({ items: list }))) return;
    saveQueue().drop('items');
    try {
      const result = await deps.post('/api/board/update', { id: st.detail.id, items: boardItemsPayload(list) });
      st.detail = result.board;
      await reloadData();
      if (message) toast(message);
    } catch (error) { toast(`保存展示板失败：${error.message}`, { kind: 'error' }); }
  }
  /** 键盘 / 拖拽换位：from → to 落盘（锁定保护与冲刷都在 persistItems 里）。 */
  function moveItemTo(from, to) {
    if (!st.detail) return undefined;
    return persistItems(boardMoveItems(st.detail.items, from, to), '排序已保存');
  }
  function sort(choice) {
    if (!st.detail || !choice) return undefined;
    return persistItems(boardSortItems(st.detail.items, choice), '排序已保存');
  }
  function cleanMissing(kind) {
    if (!st.detail) return undefined;
    const kept = items().filter(item => (kind === 'suspended' ? !item.suspended : !item.missing));
    return persistItems(kept, kind === 'suspended' ? '已移出停用题' : '已清理缺失条目');
  }
  async function clear() {
    if (!st.detail) return;
    const ok = await deps.confirm(`清空展示板「${st.detail.name}」？`, { hint: '移除全部题目引用；题目本身与纸面记录不受影响。', okText: '清空', danger: true });
    if (!ok) return;
    await persistItems([], '展示板已清空');
  }
  async function syncLabel(preferred = '') {
    if (!st.detail) return;
    // 加题同步会在服务端追加引用；先落盘本地待保存的 items，避免随后重读用旧快照覆盖新题。
    if (!(await flush())) return;
    const defs = deps.labels();
    if (!defs.length) { toast('还没有标记，先在题目上打一个「考前必看」之类的标记', { kind: 'warn' }); return; }
    let label = preferred && defs.some(item => item.name === preferred) ? preferred : '';
    if (!label) {
      const current = st.detail.source_labels?.[0] || '';
      const res = await deps.dialog({
        title: '按标记同步', okText: '同步到展示板', focus: '[data-dialog-ok]',
        hint: '把带有该标记、且还不在板里的题目追加到末尾；之后新打的标记不会自动进板，需要时再同步一次。',
        body: syncBody(defs, current),
      });
      if (!res.ok) return;
      label = defs.find((item, index) => res.values[`bd-sync-${index}`] === true)?.name;
    }
    if (!label) return;
    if (!(await flush())) return;   // 对话框关闭后再查一次：同步追加前没有新的脏字段或在途保存
    const uids = deps.items().filter(item => !item.suspended && (item.labels || []).includes(label)).map(item => item.uid);
    try {
      const result = uids.length ? await deps.post('/api/board/items/add', { id: st.detail.id, uids }) : { board: { added: 0 } };
      if (!preferred) await deps.post('/api/board/update', { id: st.detail.id, source_labels: [label] });
      await reloadData();
      toast(result.board.added ? `已同步 ${result.board.added} 道「${label}」题目` : `没有带「${label}」的新题目`);
    } catch (error) { toast(`同步标记失败：${error.message}`, { kind: 'error' }); }
  }

  // ---------- 选中、打印范围、留白 ----------
  /** 选中的唯一入口：纸面点击、列表 / 画廊点击、键盘上下都走它，三处选中态才不会各说各话。 */
  function select(uid) {
    st.selected = uid || '';
    changed();
  }
  /** 打印范围：换了范围，上一次「等待记录」作废，状态、主按钮文案与纸面当场按新范围变化。 */
  function setMode(mode) {
    if (!st.detail) return;
    st.mode = mode === 'new' ? 'new' : 'all';
    boardPrint().clearAwaiting(st.detail.id);
    changed();
    syncPreview();
  }
  const setItemGap = (uid, value, options = {}) => boardSettings().setItemGap(uid, value, options);
  const applyPrintField = (field, value) => boardSettings().applyPrintField(field, value);
  /** 拖切割线松手：一次合并保存；失败就把这道题的留白恢复成拖动前的值。 */
  async function applyGapDrag(uid, lines) {
    const item = itemOf(uid);
    if (!item) return;
    const before = item.gap_lines;
    select(uid);
    if (!(await setItemGap(uid, clamp(lines, 0, 48, 0)))) return;
    if (await flush({ silent: true })) return;
    setItemGap(uid, before);
    toast('题后留白没能保存，已恢复拖动前的值', { kind: 'error' });
  }

  // ---------- 离开 / 关页 / 打印窗口 ----------
  function flushIfDirty() { if (saveQueue().dirty()) flush(); }
  /** 关页 / 刷新：fetch 会被中断，用 sendBeacon 把同一份 payload 交给浏览器后台发送。 */
  function beforeUnload() {
    const payload = saveQueue().takePayload();
    if (!payload) return;
    try {
      const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
      if (!deps.beacon('/api/board/update', blob)) deps.post('/api/board/update', payload).catch(() => {});
    } catch (error) { try { deps.post('/api/board/update', payload).catch(() => {}); } catch (inner) { /* 放弃 */ } }
  }
  /** 独立打印窗口的回传（版面 / 「已打印，记录纸面」）只更新它自己的导出快照，见 print.js handleMessage。 */
  const handleMessage = event => boardPrint().handleMessage(event);

  /** 选板浮层新建板后先把它设为当前详情（随后整页重读会再载一次）。 */
  function adoptDetail(board) { if (board) { st.detail = board; changed(); } }

  function openItem(uid) {
    const item = itemOf(uid);
    if (item && !item.missing) deps.openQuestion(item.uid, items().filter(x => !x.missing).map(x => x.uid));
  }

  return {
    configure(patch = {}) { deps = { ...deps, ...patch }; },
    onDetail(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    snapshot: () => ({ detail: st.detail, mode: st.mode, awaiting: st.detail ? boardPrint().awaiting() : null,
      view: view(), selected: st.selected, previewError: st.previewError }),
    detail: () => st.detail,
    mode: () => st.mode,
    selected: () => st.selected,
    view, setView, render, changed, effectiveMode, itemOf,
    // 数据
    enter: () => reloadData(), reloadData, load, addToBoard, adoptDetail, gotoBoard: () => deps.gotoBoard(),
    // 条目
    removeItem, persistItems, moveItemTo, sort, cleanMissing, clear, syncLabel, openItem,
    // 选中 / 范围 / 版式
    select, setMode, setItemGap, applyPrintField, applyGapDrag,
    locked: () => !!st.detail?.print?.locked,
    // 子控制器
    saveQueue, flush, markDirty, settings: boardSettings, print: boardPrint,
    printPreview: () => boardPrint().exportCurrent(true),
    exportCurrent: () => boardPrint().exportCurrent(false),
    markPrinted: () => boardPrint().markPrinted(),
    resetPrinted: () => boardPrint().resetPrinted(),
    markAwaiting: (mode, job = null) => boardPrint().markAwaiting(mode, job),
    clearAwaiting: (boardId = st.detail?.id) => boardPrint().clearAwaiting(boardId),
    /** 板 ⋯ 菜单「导出 HTML」：先切到那块板再导出。 */
    async exportBoard(id) { await load(id, true); return st.detail?.id === id ? boardPrint().exportCurrent(false) : undefined; },
    // 预览
    syncPreview, pushRelayout, regen,
    // 生命周期
    flushIfDirty, beforeUnload, handleMessage,
  };
}
