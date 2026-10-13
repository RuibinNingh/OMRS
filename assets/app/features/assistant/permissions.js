/** 对话权限选择：只由页面操作改模式，迟到响应不进入其它对话。 */
import { html } from '../../core/html.js';
import { get, post } from '../../core/api.js';
import { icon } from '../../ui/icon.js';
import { openMenu, closeMenu } from '../../ui/menu.js';
import { publishReviewChange } from '../../domain/ai-review.js';

export const MODES = {
  manual: { label: '手动模式', icon: 'clock', hint: '逐项确认；10 分钟未处理后送审' },
  hold: { label: '滞留模式', icon: 'inbox', hint: '请求直接送到审核中心，稍后处理' },
  danger: { label: '危险模式', icon: 'alert-triangle', hint: '自动同意全部权限请求' },
};
export function modeControl(S, disabled) {
  const mode = MODES[S.permissionMode] || MODES.manual;
  return html`<button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ast-mode${S.permissionMode === 'danger' ? ' is-danger' : ''}" data-action="assistant.chooseMode" aria-label="权限模式：${mode.label}" aria-haspopup="menu" aria-expanded="${S.modeMenuOpen ? 'true' : 'false'}" title="${mode.hint}"${disabled || S.permissionBusy ? html` disabled` : ''}>
    ${icon(mode.icon)}<span>${S.permissionBusy ? '切换中…' : mode.label}</span>${icon('chevron-down')}</button>`;
}
export function modeNote(S) {
  const mode = S.permissionMode || 'manual';
  return html`<p class="ast-mode-note${mode === 'danger' ? ' is-danger' : ''}" role="status">${MODES[mode].hint}${mode === 'danger' ? ' · 对本对话生效' : ''}</p>`;
}
export const transferNote = permission => ({ hold: '滞留模式 · 请求已送到审核中心，聊天可继续。',
  timeout: '等待已满 10 分钟 · 已自动送到审核中心。', manual: '已送到审核中心，可稍后处理。',
  mode_change: '已切换滞留模式 · 请求移到审核中心。', restart: '服务重启 · 请求保留在审核中心。' })[permission?.reason] || '请求保留在审核中心，等待审核。';

export function createPermissions(S, { schedule, notify, refresh, create = () => post('/api/agent/conversation/create', {}) }) {
  let sequence = 0;
  function adopt(conversation) { sequence += 1; S.permissionMode = MODES[conversation?.permission_mode] ? conversation.permission_mode : 'manual'; S.permissionBusy = false; schedule(); }
  async function sync() {
    if (!S.convId || S.permissionBusy) return;
    const id = S.convId, request = ++sequence;
    const out = await get(`/api/agent/permission-mode?id=${encodeURIComponent(id)}`);
    if (S.alive && id === S.convId && request === sequence && out.ok) adopt(out.data.conversation);
  }
  async function choose(anchor) {
    const id = S.convId, conversationRequest = S.convRequest;
    S.modeMenuOpen = true; schedule();
    const selected = await openMenu(anchor, Object.entries(MODES).map(([value, mode]) => ({ value,
      label: `${mode.label}${value === 'manual' ? ' · 默认' : ''}${value === S.permissionMode ? ' · 当前' : ''}`,
      icon: value === S.permissionMode ? 'check' : mode.icon, hint: mode.hint, danger: value === 'danger' })), { label: '选择权限模式' });
    S.modeMenuOpen = false; schedule();
    if (!selected || selected === S.permissionMode || !S.alive || S.convId !== id || S.convRequest !== conversationRequest) return;
    const request = ++sequence;
    S.permissionBusy = true; schedule();
    try {
      if (!S.convId) {
        const created = await create();
        if (!S.alive || request !== sequence || S.convId !== id) return;
        if (!created.ok) { notify(created.error?.message || '新建对话失败'); return; }
        S.convId = created.data.conversation.id;
        S.convs.unshift({ ...created.data.conversation, msgs: 0, writes: 0, snippet: '' });
      }
      const target = S.convId;
      const out = await post('/api/agent/permission-mode', { conversation_id: target, mode: selected });
      if (!S.alive || request !== sequence || target !== S.convId) return;
      if (!out.ok) { notify(out.error?.message || '切换权限模式失败'); return; }
      adopt(out.data.conversation);
      publishReviewChange(); void refresh();
    } finally { if (request === sequence) { S.permissionBusy = false; schedule(); } }
  }
  return { adopt, sync, choose, dispose() { sequence += 1; closeMenu(); } };
}
