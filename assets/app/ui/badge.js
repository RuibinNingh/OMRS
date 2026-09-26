/**
 * 徽标：badge(value, {tone:'neutral'|'accent'|'danger'|'success'|'warning', max, dot, label})；超过 max 显示 max+。
 */
import { html, cls } from '../core/html.js';

export function badge(value, { tone = 'neutral', max = 99, dot = false, label } = {}) {
  const c = cls('ui-badge', tone !== 'neutral' && `ui-badge--${tone}`, dot && 'ui-badge--dot');
  if (dot) return html`<span class="${c}" role="status" aria-label="${label || '有新内容'}"></span>`;
  const n = Number(value);
  const text = Number.isFinite(n) && n > max ? `${max}+` : value;
  return html`<span class="${c}"${label ? html` aria-label="${label}"` : ''}>${text}</span>`;
}
