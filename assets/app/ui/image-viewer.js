/** 站内图片预览。只接收页面已持有的图片地址，不上传或复制图片内容。 */
import { html } from '../core/html.js';
import { toElement } from '../core/dom.js';
import { icon } from './icon.js';
import { openModal } from './overlay.js';

export function openImageViewer(images, initial = 0) {
  const entries = images.filter(image => image?.src);
  if (!entries.length) return null;
  let index = Math.max(0, Math.min(entries.length - 1, initial));
  let zoomed = false;
  const el = toElement(html`<dialog class="ui-image-viewer" aria-label="图片预览">
    <div class="ui-image-viewer__bar">
      <span class="ui-image-viewer__count" aria-live="polite"></span>
      <div class="ui-image-viewer__actions">
        <button type="button" class="ui-btn ui-btn--ghost" data-image-action="zoom" aria-label="放大图片">${icon('search')}<span>放大</span></button>
        <a class="ui-btn ui-btn--ghost" data-image-action="download" download>下载</a>
        <a class="ui-btn ui-btn--ghost" data-image-action="external" target="_blank" rel="noopener noreferrer">新标签打开</a>
        <button type="button" class="ui-btn ui-btn--ghost ui-btn--icon" data-image-action="close" aria-label="关闭预览">${icon('x')}</button>
      </div>
    </div>
    <div class="ui-image-viewer__stage">
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--icon" data-image-action="prev" aria-label="上一张">${icon('chevron-left')}</button>
      <img alt="">
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--icon" data-image-action="next" aria-label="下一张">${icon('chevron-right')}</button>
    </div></dialog>`);
  const draw = () => {
    const image = entries[index];
    const picture = el.querySelector('img');
    picture.src = image.src;
    picture.alt = image.label || `图片 ${index + 1}`;
    el.querySelector('.ui-image-viewer__count').textContent = `${index + 1} / ${entries.length} · ${picture.alt}`;
    for (const action of ['download', 'external']) el.querySelector(`[data-image-action="${action}"]`).href = image.src;
    el.querySelector('[data-image-action="download"]').download = image.filename || `图片-${index + 1}`;
    for (const action of ['prev', 'next']) el.querySelector(`[data-image-action="${action}"]`).disabled = entries.length < 2;
    el.classList.toggle('is-zoomed', zoomed);
    el.querySelector('[data-image-action="zoom"]').setAttribute('aria-label', zoomed ? '适应屏幕' : '放大图片');
    el.querySelector('[data-image-action="zoom"] span').textContent = zoomed ? '适应' : '放大';
  };
  const marker = `image-viewer-${Date.now()}-${Math.random()}`;
  const onBack = () => entry.close(false);
  const entry = openModal(el, { initialFocus: '[data-image-action="close"]', onClose: () => {
    window.removeEventListener('popstate', onBack);
    if (history.state?.imageViewer === marker) history.back();
  } });
  history.pushState({ ...(history.state || {}), imageViewer: marker }, '', location.href);
  window.addEventListener('popstate', onBack);
  el.addEventListener('keydown', event => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    index = (index + (event.key === 'ArrowRight' ? 1 : -1) + entries.length) % entries.length;
    zoomed = false;
    draw();
  });
  el.addEventListener('click', event => {
    const action = event.target.closest('[data-image-action]')?.dataset.imageAction;
    if (action === 'close') entry.close(false);
    else if (action === 'zoom') { zoomed = !zoomed; draw(); }
    else if (action === 'prev' || action === 'next') { index = (index + (action === 'next' ? 1 : -1) + entries.length) % entries.length; zoomed = false; draw(); }
  });
  draw();
  return entry;
}
