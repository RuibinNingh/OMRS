/**
 * 按钮：button({label, variant, size, icon, iconRight, iconOnly, loading, disabled, pressed, type, action, arg, title, block})
 * variant: default | primary | ghost | danger；size: sm(28) | md(32，默认) | lg(40)。只有图标时 label 用作 aria-label。
 * 同一行的控件用同一档高度（design-system §3）。
 */
import { html, cls } from '../core/html.js';
import { icon as svg } from './icon.js';

export function button({ label = '', variant = 'default', size = 'md', icon, iconRight, iconOnly = false, loading = false, disabled = false,
  pressed, type = 'button', action, arg, title, block = false, state } = {}) {
  const c = cls('ui-btn', variant !== 'default' && `ui-btn--${variant}`, size !== 'md' && `ui-btn--${size}`,
    iconOnly && 'ui-btn--icon', block && 'ui-btn--block', loading && 'is-loading', state && `is-${state}`);
  return html`<button type="${type}" class="${c}"${action ? html` data-action="${action}"` : ''}${arg != null ? html` data-arg="${arg}"` : ''}${iconOnly ? html` aria-label="${label}"` : ''}${title ? html` title="${title}"` : ''}${pressed != null ? html` aria-pressed="${pressed ? 'true' : 'false'}"` : ''}${loading ? html` aria-busy="true"` : ''}${disabled || loading ? html` disabled` : ''}>${icon ? svg(icon) : ''}${iconOnly ? '' : html`<span class="ui-btn__label">${label}</span>`}${iconRight ? svg(iconRight) : ''}</button>`;
}
