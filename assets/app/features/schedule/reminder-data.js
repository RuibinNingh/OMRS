/** 提醒素材只用服务器校验后的图片预览；原始SVG不进入页面DOM。 */
import { get, post } from '../../core/api.js';
import { html } from '../../core/html.js';
export { requestId } from '../../core/request-id.js';

export const loadReminders = sessionId => get(`/api/schedule-reminders${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''}`);
export const reminderImage = (snapshot, alt = '首页提醒预览') => snapshot?.src
  ? html`<img class="rem-image" src="${snapshot.src}" alt="${alt}">`
  : html`<div class="rem-placeholder">不显示首页提醒</div>`;

export function defaultIdentity(data) {
  return data?.default?.reminder_id || data?.items?.find(x => x.sha256 === data?.default_snapshot?.sha256)?.id || '';
}

export const saveDefault = (data, identity, enabled = true) => post('/api/schedule-banner', {
  enabled: !!identity && enabled, reminder_id: identity || null, svg: '', expected_revision: data.default.revision,
});
