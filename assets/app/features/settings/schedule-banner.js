/** 调度提醒集中在复习调度素材库管理，设置页保留直达入口。 */
import { html } from '../../core/html.js';

export const bannerView = () => html`<div class="card st-card" id="st-banner-card"><div class="card-title">调度提醒</div><p class="hint">在复习调度的「提醒素材」中生成、导入或删除首页提醒，并选择新计划默认；已有计划保留原提醒。</p><div id="st-banner-editor"><button class="ui-btn" type="button" data-banner-manage>管理提醒素材</button></div></div>`;

export function createScheduleBanner(root) {
  const host = root.querySelector('#st-banner-editor');
  const click = event => {
    if (!event.target.closest('[data-banner-manage]')) return;
    globalThis.__omrs?.router.go('schedule');
    globalThis.__omrs?.emit('schedule:view', 'reminders');
  };
  host?.addEventListener('click', click);
  return { async load() {}, dispose() { host?.removeEventListener('click', click); } };
}
