/**
 * 展示板页（P7 第 5 轮起的 features 页面；第 6 轮起整页原生，原 assets/board.js 已删）。
 * - 契约：page = { id, title, workbench, mount(root, ctx) → unmount, actions, keys }；动作命名空间与快捷键作用域都是 'board'。
 * - 数据：板列表、文件夹、当前板、折叠归 domain/board/boards.js（onBoards 变化即重绘）；板详情、打印范围、视图、选中题归
 *   detail.js（onDetail 变化即重绘）。常驻预览是本目录的 preview.js，翻页 / 缩放 / 挂载直接调它。
 * - 整页一次 morph：状态条、左栏树、舞台头、列表 / 画廊、检查器；只有舞台（常驻 iframe）与画廊卡题面挂载点是 data-morph="skip"。
 *   聚焦中的输入框与滑杆 morph 不改值，所以拖滑杆、敲留白数字时整页重绘也不丢焦点；被锁定确认拒掉时先放掉焦点再重绘。
 * - 快捷键走 core/keys.js（页面作用域）：对话框、输入框、选板浮层（浮层键盘层）打开时由 core/keys 挡住；
 *   标记选择器（旧 labels.js 浮层）打开时本页快捷键全部让位。离开本页时有待保存的改动立即落盘。
 */
import { morph } from '../../core/dom.js';
import { openMenu } from '../../ui/menu.js';
import { qvRender } from '../../domain/question/index.js';
import { dueDays } from '../../domain/items.js';
import { pickerOpen } from '../../domain/labels/index.js';
import * as B from '../../domain/board/boards.js';
import { boardDetail } from './runtime.js';
import { openBoardAdd } from './add.js';
import { boardKeySelectTarget, boardKeyReorderTarget, boardTreeDropPlan, bindBoardTreeDrag, bindBoardRowDrag } from './drag.js';
import { boardPreviewMount, boardPreviewGoto, boardPreviewStep, boardPreviewScale, boardPreviewLayout, boardPreviewView } from './preview.js';
import * as S from './state.js';
import { view } from './view.js';

const s = S.state;
let ctl = null;

const D = boardDetail();
/** 画廊卡题面：与题库画廊同一套 qview（缩略、不带答案与记录）。 */
const CARD_OPTS = Object.freeze({ layout: 'stack', showMeta: false, showAnswer: false, showNotes: false, showHistory: false, actions: [], bare: true, clamp: 5 });
/** 拖拽只绑一次：drag.js 用 data-bound 标记，但 morph 会把模板里没有的属性抹掉，所以这里另记。 */
const dragBound = new WeakSet();
const later = (fn, ms = 0) => setTimeout(fn, ms);

/** 过渡桥 boardRender() / 旧冒烟测试：本页挂着就重绘，不在本页时什么都不做。 */
export function repaintBoardPage() { ctl?.paint(); }

/** 菜单选中后隔一拍再动作：同一次点击冒泡完再开对话框（progress §6「菜单 / 浮层里触发旧浮层」）。 */
async function pick(anchor, items, label) {
  const value = await openMenu(anchor, items, { label });
  if (value == null) return null;
  await new Promise(resolve => setTimeout(resolve, 0));
  return value;
}

function createController(root) {
  const snap = () => D.snapshot();
  const items = () => D.detail()?.items || [];
  const selectedIndex = () => { const uid = D.selected(); return items().findIndex(item => item.uid === uid); };

  function paint() {
    const sn = snap();
    morph(root, view({
      status: S.statusView(sn), renaming: s.renaming && !!sn.detail,
      tree: S.treeView({ boards: B.boardList(), folders: B.boardFolders(), current: B.boardCurrentId(), collapsed: B.boardFolderCollapsed() }),
      stage: S.stageView(sn, { layout: boardPreviewLayout(), view: boardPreviewView(), zoom: s.zoom }),
      content: S.contentView(sn, { dueDays }), inspector: S.inspectorView(sn),
    }));
    // 舞台是 skip 节点：显隐与 iframe 挂载在这里做（纸面视图才挂，boardPreviewMount 同一容器重复调用无副作用）
    const stage = root.querySelector('#bd-stage');
    const paper = !!sn.detail && sn.view === 'paper';
    if (stage) { stage.hidden = !paper; if (paper) boardPreviewMount(stage); }
    if (sn.view === 'gallery') hydrate();
  }

  // 画廊题面：挂载点 key 变了（换题）才重新挂；其余重绘时 skip 节点原样保留
  function hydrate() {
    root.querySelectorAll('#bd-content-body [data-qv-host]').forEach(el => {
      if (el.dataset.qvFor === el.dataset.key) return;
      el.dataset.qvFor = el.dataset.key;
      qvRender(el, el.dataset.uid, CARD_OPTS).then(() => el.classList.toggle('is-clipped', el.scrollHeight - el.clientHeight > 4));
    });
  }

  /** 锁定确认被拒：聚焦中的控件放掉焦点，随后的重绘把它改回旧值。 */
  function releaseFocus() {
    const active = root.ownerDocument.activeElement;
    if (active && active !== root.ownerDocument.body && root.querySelector('#bd-inspector')?.contains(active)) active.blur();
  }

  async function finishRename(save) {
    if (!s.renaming) return;
    const input = root.querySelector('[data-board-rename]');
    const name = input?.value || '';
    const id = snap().detail?.id;
    s.renaming = false;          // 先落状态再重绘：输入框被移除时的 focusout 不会再保存一次
    paint();
    root.querySelector('.brd-rename-btn')?.focus({ preventScroll: true });
    if (save && id) await B.saveBoardName(id, name);
  }

  return {
    paint,
    startRename() {
      if (!snap().detail) return;
      s.renaming = true;
      paint();
      const input = root.querySelector('[data-board-rename]');
      input?.focus();
      input?.select();
    },
    finishRename,
    renameInput: target => !!target?.matches?.('[data-board-rename]'),
    releaseFocus,
    open: id => { if (id) D.load(id); },
    async newMenu(el) {
      const value = await pick(el, S.NEW_MENU, '新建');
      if (value === 'board') B.createBoard();
      else if (value === 'folder') B.createFolder();
    },
    async boardMenu(el, id) {
      const board = B.boardFind(id);
      if (!board) return;
      const value = await pick(el, S.boardMenuItems(board, B.boardFolders()), `展示板「${board.name}」操作`);
      if (value === 'rename') B.renameBoard(id);
      else if (value === 'note') B.editBoardNote(id);
      else if (value === 'duplicate') B.duplicateBoard(id);
      else if (value === 'export') D.exportBoard(id);
      else if (value === 'move-new') B.createFolder(id);
      else if (value === 'delete') B.deleteBoard(id);
      else if (typeof value === 'string' && value.startsWith('move:')) B.moveBoard(id, value.slice(5));
    },
    async folderMenu(el, id) {
      const folder = B.boardFolders().find(item => item.id === id);
      if (!folder) return;
      const value = await pick(el, S.folderMenuItems(folder, B.boardFolders()), `文件夹「${folder.name}」操作`);
      if (value === 'rename') B.renameFolder(id);
      else if (value === 'new-board') B.createBoard(null, id);
      else if (value === 'up') B.reorderFolder(id, -1);
      else if (value === 'down') B.reorderFolder(id, 1);
      else if (value === 'delete') B.deleteFolder(id);
    },
    async sortMenu(el) {
      if (!snap().detail) return;
      const value = await pick(el, S.SORT_MENU, '排序');
      if (value) D.sort(value);
    },
    page(arg) {
      if (arg === 'prev' || arg === 'next') boardPreviewStep(arg === 'prev' ? -1 : 1);
      else if (arg === 'new') { const uid = S.firstNewUid(items()); if (uid) boardPreviewGoto(uid); }
    },
    zoom(arg) {
      s.zoom = arg === 'fit' ? 'fit' : 1;
      boardPreviewScale(s.zoom);
      paint();
    },
    // ---------- 快捷键（返回 false = 没处理，交给下一层且不 preventDefault） ----------
    withDetail(fn) { if (!snap().detail) return false; fn(); return true; },
    step(delta) {
      const sn = snap();
      if (!sn.detail || sn.view !== 'paper') return false;
      boardPreviewStep(delta);
      return true;
    },
    cursor(key) {
      const sn = snap();
      const list = items();
      if (!list.length) return false;
      const uid = list[boardKeySelectTarget(selectedIndex(), key, list.length)].uid;
      D.select(uid);
      if (sn.view === 'paper') boardPreviewGoto(uid);
      root.querySelector(`[data-board-row="${CSS.escape(uid)}"]`)?.scrollIntoView?.({ block: 'nearest' });
      return true;
    },
    reorder(key) {
      const list = items();
      const index = selectedIndex();
      const to = boardKeyReorderTarget(index, key, list.length);
      if (!snap().detail || to < 0) return false;
      D.moveItemTo(index, to);
      return true;
    },
    enter(event) {
      if (this.renameInput(event.target)) { finishRename(true); return true; }
      if (event.target?.closest?.('input, textarea, select, button, a[href], [contenteditable], [role="button"]')) return false;
      const current = items()[selectedIndex()];
      if (!current || current.missing) return false;
      D.openItem(current.uid);
      return true;
    },
    escape(event) {
      if (!this.renameInput(event.target)) return false;
      finishRename(false);
      return true;
    },
    /** 列表行 / 画廊卡「留白」只读回显：选中它，再把焦点送到检查器的题后留白框。 */
    focusGap(uid) {
      D.select(uid);
      root.querySelector('#bd-ins-gap')?.focus({ preventScroll: true });
    },
    /** 回到纸面上这道题：不在纸面视图时先切过去，等舞台挂好再翻页。 */
    locate(uid) {
      if (!uid) return;
      D.select(uid);
      if (D.view() !== 'paper') { D.setView('paper'); later(() => boardPreviewGoto(uid), 60); } else boardPreviewGoto(uid);
    },
    removeSelected() {
      const current = items()[selectedIndex()];
      if (!current) return false;
      D.removeItem(current.uid);
      return true;
    },
  };
}

const ready = fn => event => (ctl && !pickerOpen() ? fn(event) : false);
const clampGap = raw => (raw === '' ? null : Math.max(0, Math.min(48, Number.isFinite(Number(raw)) ? Number(raw) : 0)));
const gapValue = el => clampGap(String(el?.value ?? '').trim());
const isGeometry = el => el?.type === 'range' || el?.type === 'number';
/** 「添加题目」：ui/dialog 对话框（add.js），确认后经 detail.js 加进当前板。 */
const openAdd = () => { const detail = D.detail(); return detail ? openBoardAdd(detail, uids => D.addToBoard(detail.id, uids)) : null; };

export const page = {
  id: 'board',
  title: '展示板',
  workbench: true,
  mount(root, ctx) {
    ctl = createController(root);
    const current = ctl;
    const onDbl = event => {
      if (event.target.closest?.('[data-board-rename-target]')) { current.startRename(); return; }
      const row = event.target.closest?.('[data-board-row]');
      if (row && !event.target.closest('input, button, label, a, [data-lbl-target]')) D.openItem(row.dataset.boardRow);
    };
    // 点条目 = 选中（按钮、复选框、标记芯片各有自己的动作）
    const onClick = event => {
      const row = event.target.closest?.('[data-board-row]');
      if (row && !event.target.closest('input, button, label, a, [data-lbl-target]')) D.select(row.dataset.boardRow);
    };
    const onBlur = event => { if (current.renameInput(event.target)) current.finishRename(true); };
    root.addEventListener('dblclick', onDbl);
    root.addEventListener('click', onClick);
    root.addEventListener('focusout', onBlur);
    D.configure({ rejected: () => current.releaseFocus() });
    const offBoards = B.onBoards(() => ctl?.paint());
    const offDetail = D.onDetail(() => ctl?.paint());
    const offLabels = ctx.bus.on('board:reload', () => D.reloadData());
    ctl.paint();
    // 左栏树与条目行的拖放（每个节点只绑一次；重新进页时节点还是那一个）
    const list = root.querySelector('#bd-list');
    if (list && !dragBound.has(list)) {
      dragBound.add(list);
      bindBoardTreeDrag(list, {
        plan: (drag, target) => boardTreeDropPlan(drag, target, B.boardList(), B.boardFolders()),
        apply: plan => B.applyTreeDrop(plan),
      });
    }
    const content = root.querySelector('#bd-content');
    if (content && !dragBound.has(content)) {
      dragBound.add(content);
      bindBoardRowDrag(content, { ready: () => !!D.detail(), length: () => (D.detail()?.items || []).length, move: (from, to) => D.moveItemTo(from, to) });
    }
    D.render();   // 先用缓存把列表 / 画廊、检查器与预览画出来
    D.enter();    // 再重读列表与当前板
    return () => {
      offBoards();
      offDetail();
      offLabels();
      root.removeEventListener('dblclick', onDbl);
      root.removeEventListener('click', onClick);
      root.removeEventListener('focusout', onBlur);
      D.configure({ rejected: null });
      s.renaming = false;
      D.flushIfDirty();
      ctl = null;
    };
  },
  actions: {
    create: () => B.createBoard(),
    newMenu: ({ el }) => ctl?.newMenu(el),
    open: ({ arg }) => ctl?.open(arg),
    menu: ({ el, arg }) => ctl?.boardMenu(el, arg),
    fold: ({ arg }) => B.boardFolderToggle(arg),
    folderMenu: ({ el, arg }) => ctl?.folderMenu(el, arg),
    rename: () => ctl?.startRename(),
    mode: ({ arg }) => D.setMode(arg),
    primary: ({ arg }) => (arg === 'mark-printed' ? D.markPrinted() : D.printPreview()),
    export: () => D.exportCurrent(),
    regen: () => D.regen(),
    view: ({ arg }) => D.setView(arg),
    add: () => openAdd(),
    sync: () => D.syncLabel(),
    sortMenu: ({ el }) => ctl?.sortMenu(el),
    clear: () => D.clear(),
    clean: ({ arg }) => D.cleanMissing(arg),
    page: ({ arg }) => ctl?.page(arg),
    jump: ({ value }) => boardPreviewGoto(Number(value) || 1),
    zoom: ({ arg }) => ctl?.zoom(arg),
    // ---------- 列表 / 画廊 ----------
    openItem: ({ arg }) => D.openItem(arg),
    remove: ({ arg }) => D.removeItem(arg),
    focusGap: ({ arg }) => ctl?.focusGap(arg),
    locate: ({ arg }) => ctl?.locate(arg),
    // ---------- 检查器：题后留白只在这里改；锁定时滑杆 / 数字框只在松手（change）时写，一轮输入一个确认框 ----------
    inspectLocate: () => ctl?.locate(D.selected()),
    inherit: () => D.setItemGap(D.selected(), null),
    gapLive: ({ el }) => { if (!D.locked()) void D.setItemGap(el.dataset.boardInspectGap, gapValue(el), { keepFocus: true }); },
    gapSet: ({ el }) => { if (D.locked()) void D.setItemGap(el.dataset.boardInspectGap, gapValue(el), { keepFocus: true }); },
    printLive: ({ el, arg }) => { if (!(D.locked() && isGeometry(el))) void D.applyPrintField(arg, el.value); },
    printSet: ({ el, arg }) => { void D.applyPrintField(arg, el.type === 'checkbox' ? el.checked : el.value); },
    seg: ({ el, arg }) => { void D.applyPrintField(arg, el.dataset.value); },
    resetPrinted: () => D.resetPrinted(),
  },
  keys: {
    n: ready(() => { B.createBoard(); }),
    a: ready(() => ctl.withDetail(() => openAdd())),
    p: ready(() => ctl.withDetail(() => D.printPreview())),
    arrowleft: ready(() => ctl.step(-1)),
    arrowright: ready(() => ctl.step(1)),
    arrowup: ready(() => ctl.cursor('arrowup')),
    arrowdown: ready(() => ctl.cursor('arrowdown')),
    'mod+arrowup': ready(() => ctl.reorder('arrowup')),
    'mod+arrowdown': ready(() => ctl.reorder('arrowdown')),
    delete: ready(() => ctl.removeSelected()),
    backspace: ready(() => ctl.removeSelected()),
    enter: { inInput: true, handler: ready(event => ctl.enter(event)) },
    escape: { inInput: true, handler: ready(event => ctl.escape(event)) },
  },
};
