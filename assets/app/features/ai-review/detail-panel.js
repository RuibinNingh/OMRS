/** 对话内的审核详情：复用中心控制器，局部派发动作并保护关闭时的未保存输入。 */
import { openDrawer } from '../../ui/drawer.js';
import { createReviewController, reviewActions } from './index.js';

export function createReviewPanel(ctx) {
  let drawer = null, controller = null, guarding = false;
  async function canClose() {
    if (guarding) return;
    guarding = true;
    try { if (await controller.guard()) drawer?.close(); }
    finally { guarding = false; }
  }
  function dismissible() {
    if (!controller) return true;
    const s = controller.state, draft = controller.editor()?.state;
    if (s.busy || draft?.busy) return false;
    if (!s.dirty && !draft?.dirty) return true;
    void canClose(); return false;
  }
  async function open(id, returnFocus) {
    if (!id) return;
    if (drawer) { await controller.select(id); return; }
    drawer = openDrawer({ title: '操作详情', dismissible, returnFocus,
      onClose() { controller?.dispose(); controller = null; drawer = null; ctx.onClose?.(); } });
    drawer.el.classList.add('ast-review-panel');
    controller = createReviewController(drawer.body, ctx, { embedded: true, id });
    const handlers = reviewActions(() => controller);
    for (const [type, attr] of [['click', 'action'], ['input', 'input'], ['change', 'change']]) {
      drawer.el.addEventListener(type, event => {
        const el = event.target.closest?.(`[data-${attr}]`), name = el?.getAttribute(`data-${attr}`);
        if (!name?.startsWith('ai-review.')) return;
        event.stopPropagation();
        if (el.disabled || el.getAttribute('aria-disabled') === 'true') return;
        handlers[name.slice('ai-review.'.length)]?.({ el, arg: el.dataset.arg, value: el.value, event });
      });
    }
  }
  return { open, dispose() { drawer?.close(); } };
}
