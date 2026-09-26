/**
 * 卡片：card({title, subtitle, actions, body, footer, interactive, flat, action})；body/actions/footer 传 html`` 结果。
 */
import { html, cls } from '../core/html.js';

export function card({ title, subtitle, actions, body, footer, interactive = false, flat = false, action, state } = {}) {
  const c = cls('ui-card', interactive && 'ui-card--interactive', flat && 'ui-card--flat', state && `is-${state}`);
  const head = title || actions ? html`<header class="ui-card__head"><div class="ui-card__heading">${title ? html`<h3 class="ui-card__title">${title}</h3>` : ''}${subtitle ? html`<p class="ui-card__subtitle">${subtitle}</p>` : ''}</div>${actions ? html`<div class="ui-card__actions">${actions}</div>` : ''}</header>` : '';
  return html`<article class="${c}"${interactive ? html` tabindex="0"` : ''}${action ? html` data-action="${action}"` : ''}>${head}${body != null ? html`<div class="ui-card__body">${body}</div>` : ''}${footer ? html`<footer class="ui-card__foot">${footer}</footer>` : ''}</article>`;
}
