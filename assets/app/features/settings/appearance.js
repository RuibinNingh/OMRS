/** 外观与显示：偏好只保存在当前浏览器。 */
import { ledgerTimeZone } from '../../domain/history.js';

const put = (key, value) => { try { localStorage.setItem(key, value); } catch { /* 本次设置仍可生效。 */ } };

export function createAppearance(root, bus) {
  const sync = () => {
    const html = document.documentElement;
    root.querySelectorAll('#st-theme-switch .theme-opt').forEach(button =>
      button.classList.toggle('active', button.dataset.theme === (html.dataset.theme || 'light')));
    root.querySelectorAll('#st-density-switch .theme-opt').forEach(button =>
      button.classList.toggle('active', button.dataset.density === (html.dataset.density || 'compact')));
    const invert = root.querySelector('#st-invert-img');
    if (invert) invert.checked = html.dataset.invertImg === '1';
    const zone = root.querySelector('#st-ledger-time-zone');
    if (zone) zone.value = ledgerTimeZone();
  };
  return {
    sync,
    theme(mode) { const value = mode === 'dark' ? 'dark' : 'light'; put('omrs-theme', value); document.documentElement.dataset.theme = value; sync(); },
    density(mode) { const value = mode === 'comfortable' ? 'comfortable' : 'compact'; put('omrs-density', value); document.documentElement.dataset.density = value; sync(); },
    invert(on) { const value = on ? '1' : '0'; put('omrs-invert-img', value); document.documentElement.dataset.invertImg = value; sync(); },
    timeZone(zone) { put('omrs-ledger-time-zone', zone || 'local'); sync(); bus.emit('ledger:tz'); },
  };
}
