/**
 * 题目弹窗（P5 第 3 轮起换成 ui/dialog 外壳；原 omrs_dashboard.html 的 .modal-overlay#modal）：翻页条 + 一个 qview 挂载点。
 * - <dialog id="modal"> 用 ui/overlay 的 openModal 打开：进浏览器顶层、焦点陷阱、Esc 与点遮罩关闭、背景滚动锁定、
 *   关闭后焦点回到触发元素；调用方可传 returnFocus(uid)，把焦点交给「最后看的那一题」（题库页交给它的行并移动游标）。
 * - 叠在上面的旧浮层（标记选择器、选板浮层、标记管理）经 ui/overlay 的 hostGuest 放进本对话框，不会被 inert；
 *   Markdown 编辑器（editor.js）是叠上去的第二个模态对话框。
 * - ←/→ 翻页登记在 core/keys 全局作用域（inDialog）；本对话框不在最上层（编辑器、确认框叠在上面）或有客人浮层时让位。
 * - 关闭时立刻去掉 id（退场动画期间再打开也不会出现两个 #modal）。
 */
import { html } from '../../core/html.js';
import { toElement } from '../../core/dom.js';
import { registerKeys } from '../../core/keys.js';
import { icon } from '../../ui/icon.js';
import { openModal, topModal, guestOpen } from '../../ui/overlay.js';
import { qvRender, qvUnmount, qvContext } from './mount.js';

const OPTS = { layout: 'split', actions: ['edit', 'board', 'labels', 'suspend', 'delete'] };
let nav = { list: [], index: -1 };
let current = null;   // { el, stage, entry, returnFocus }

const template = () => html`<dialog class="ui-dialog ui-dialog--xl qv-dialog" id="modal" aria-label="题目详情">
<div class="ui-dialog__panel qv-dialog__panel">
<header class="ui-dialog__head qv-dialog__head">
<nav class="qv-nav" id="qv-nav" aria-label="翻页">
<button type="button" class="ui-btn ui-btn--sm qv-nav__btn" data-qv-nav="prev" aria-label="上一题" aria-keyshortcuts="ArrowLeft" title="上一题（←）">${icon('chevron-left')}<span>上一题</span></button>
<span class="qv-nav__pos" id="qv-nav-pos" aria-live="polite"></span>
<button type="button" class="ui-btn ui-btn--sm qv-nav__btn" data-qv-nav="next" aria-label="下一题" aria-keyshortcuts="ArrowRight" title="下一题（→）"><span>下一题</span>${icon('chevron-right')}</button>
</nav>
<button type="button" class="ui-btn ui-btn--ghost ui-btn--icon ui-btn--sm ui-dialog__close" data-dialog-cancel aria-label="关闭" title="关闭（Esc）">${icon('x')}</button>
</header>
<div class="qv-dialog__stage" id="modal-stage" tabindex="-1"></div>
</div></dialog>`;

function navRender() {
  if (!current) return;
  const total = nav.list.length;
  const single = total <= 1;
  const box = current.el.querySelector('.qv-nav');
  box.classList.toggle('is-single', single);
  current.el.querySelector('.qv-nav__pos').textContent = single ? '' : `第 ${nav.index + 1} / ${total} 题`;
  current.el.querySelector('[data-qv-nav="prev"]').disabled = single || nav.index <= 0;
  current.el.querySelector('[data-qv-nav="next"]').disabled = single || nav.index >= total - 1;
  current.el.setAttribute('aria-label', `题目 ${nav.list[nav.index] || ''}`.trim());
}

function show(key) {
  navRender();
  current.stage.scrollTop = 0;
  return qvRender(current.stage, key, OPTS);
}

function open(returnFocus) {
  const el = toElement(template());
  const self = { el, stage: el.querySelector('.qv-dialog__stage'), returnFocus };
  el.addEventListener('click', event => {
    const step = event.target.closest?.('[data-qv-nav]');
    if (step) { navGo(step.dataset.qvNav === 'prev' ? -1 : 1); return; }
    if (event.target.closest?.('[data-dialog-cancel]')) closeModal();
  });
  current = self;
  self.entry = openModal(el, {
    initialFocus: '.qv-dialog__stage',
    returnFocus: () => (typeof self.returnFocus === 'function' ? self.returnFocus(nav.list[nav.index]) : null),
    onClose: () => {
      qvUnmount(self.stage);
      el.removeAttribute('id');
      self.stage.removeAttribute('id');
      el.querySelectorAll('[id]').forEach(node => node.removeAttribute('id'));
      if (current === self) current = null;
    },
  });
}

/**
 * 打开题目弹窗。context 可传 uid 数组或 qvSetContext() 登记过的名字，不传就是单题（弹窗开着时沿用当前翻页序列）。
 * options.returnFocus(uid) → 元素：关闭后把焦点交给它（没有或已脱离文档时还给打开前的焦点）。
 */
export async function viewQ(uid, context, options = {}) {
  const key = String(uid || '').trim();
  if (!key) return null;
  const list = Array.isArray(context) ? context : (typeof context === 'string' ? qvContext(context) : null);
  if (list && list.length && list.includes(key)) nav = { list: [...list], index: list.indexOf(key) };
  else if (current && nav.list.includes(key)) nav.index = nav.list.indexOf(key);
  else nav = { list: [key], index: 0 };
  if (!current) open(options.returnFocus);
  else if (typeof options.returnFocus === 'function') current.returnFocus = options.returnFocus;
  return show(key);
}

export function closeModal() { current?.entry.close(false); }
export const modalOpen = () => !!current;
/** 当前弹窗里的题（没开时空串）。 */
export const modalUid = () => (current ? nav.list[nav.index] || '' : '');

async function navGo(step) {
  const index = nav.index + step;
  if (!current || index < 0 || index >= nav.list.length) return false;
  nav.index = index;
  await show(nav.list[index]);
  return true;
}

const navKey = step => ({
  inDialog: true,
  handler: () => {
    if (!current || topModal() !== current.el || guestOpen()) return false;
    navGo(step);
    return true;
  },
});

let bound = false;
/** 由过渡桥在启动时调用一次（经 mount.js 的 bindQuestionDom）。 */
export function bindModalKeys() {
  if (bound) return;
  bound = true;
  registerKeys('global', { arrowleft: navKey(-1), arrowright: navKey(1) });
}
