/**
 * 快捷键提示：kbd('Ctrl', 'K') → Ctrl + K 键帽；单键 kbd('J')。
 */
import { html } from '../core/html.js';

export function kbd(...keys) {
  const caps = keys.map(k => html`<kbd class="ui-kbd">${k}</kbd>`);
  if (caps.length === 1) return caps[0];
  return html`<span class="ui-kbd-combo">${caps.map((cap, i) => (i ? html`<span aria-hidden="true">+</span>${cap}` : cap))}</span>`;
}
