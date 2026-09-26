/** 访问与安全：访问概览、局域网范围、PIN 和远程登出。 */
import { get, post } from '../../core/api.js';
import { confirm } from '../../ui/dialog.js';
import { describeAccess, networkNeedsRestart, parseLanCidrs, pinControlState } from './state.js';

export function createAccess(root, restart) {
  const el = id => root.querySelector(`#${id}`);
  const state = { cfg: null, auth: null, status: null };
  let alive = true;
  let loadId = 0;
  let busy = false;
  const note = (id, text, tone = '') => {
    const target = el(id);
    if (target) { target.textContent = text; target.dataset.tone = tone; }
  };
  const value = id => String(el(id)?.value || '').trim();

  function render() {
    if (!alive) return;
    const info = describeAccess(state);
    const box = el('st-access-overview');
    if (box) box.dataset.level = info.level;
    note('st-access-summary', info.summary);
    note('st-fact-listen', info.listen + (info.listenNote ? ` · ${info.listenNote}` : ''));
    note('st-fact-pin', info.pin);
    note('st-fact-cidrs', info.cidrs);
    note('st-fact-you', info.you);
    const pin = pinControlState(state);
    note('st-pin-status', pin.statusText);
    if (el('st-pin-current-row')) el('st-pin-current-row').hidden = !pin.needCurrent;
    note('st-pin-new-label', pin.newLabel);
    note('st-pin-new-hint', pin.newHint);
    if (el('st-pin-logout')) el('st-pin-logout').hidden = !pin.showLogout;
    const disable = el('st-pin-disable');
    if (disable) { disable.hidden = !pin.showDisable; disable.disabled = !!pin.disableBlocked; disable.title = pin.disableBlocked; }
    networkChanged();
  }

  function networkChanged() {
    const allow = !!el('st-allow-external')?.checked;
    const cidrs = parseLanCidrs(value('st-lan-pin-exempt-cidrs'));
    const hint = allow && state.cfg && !state.cfg.pin_configured && !cidrs.length
      ? '开启前请先在上方设置 PIN，或填写免 PIN 网段。'
      : networkNeedsRestart(allow, state)
        ? allow ? '保存后会重启服务，开始监听局域网。' : '保存后会重启服务，之后只有本机能访问。'
        : '保存后立即生效，不需要重启。';
    note('st-net-hint', hint);
  }

  async function load() {
    const mine = ++loadId;
    const [cfg, auth, status] = await Promise.all([
      get('/api/config'), get('/api/auth/session'), get('/api/status'),
    ]);
    if (!alive || mine !== loadId) return;
    state.cfg = cfg.ok ? cfg.data : null;
    state.auth = auth.ok ? auth.data : null;
    state.status = status.ok ? status.data : null;
    if (state.cfg) {
      if (el('st-allow-external')) el('st-allow-external').checked = !!state.cfg.allow_external;
      if (el('st-lan-pin-exempt-cidrs')) el('st-lan-pin-exempt-cidrs').value =
        (Array.isArray(state.cfg.lan_pin_exempt_cidrs) ? state.cfg.lan_pin_exempt_cidrs : []).join(', ');
      if (el('st-pin-idle')) el('st-pin-idle').value = Number(state.cfg.idle_minutes) || 30;
    }
    render();
    if (!cfg.ok) note('st-pin-action-status', `无法读取配置：${cfg.error?.message || '未知错误'}`, 'danger');
    return state;
  }

  async function saveAccess() {
    if (busy) return;
    const allow = !!el('st-allow-external')?.checked;
    const cidrs = parseLanCidrs(value('st-lan-pin-exempt-cidrs'));
    const needsRestart = networkNeedsRestart(allow, state);
    if (needsRestart && !allow && state.auth?.remote && !await confirm('关闭局域网访问？', {
      hint: '服务重启后只接受本机访问，你当前这台设备将无法再打开 OMRS。',
      okText: '关闭并重启', danger: true,
    })) return;
    busy = true;
    note('st-net-status', '正在保存…', 'busy');
    const result = await post('/api/config', { allow_external: allow, lan_pin_exempt_cidrs: cidrs });
    if (!alive) return;
    busy = false;
    if (!result.ok) { note('st-net-status', `保存失败：${result.error?.message || '未知错误'}`, 'danger'); return; }
    if (needsRestart) {
      note('st-net-status', '已保存，正在重启服务以应用新的监听范围…', 'busy');
      await restart('st-net-status');
      return;
    }
    note('st-net-status', '已保存，立即生效。', 'success');
    await load();
  }

  async function savePin() {
    if (busy) return;
    const pin = value('st-pin-new');
    const current = value('st-pin-current');
    const idle = Number(el('st-pin-idle')?.value);
    const controls = pinControlState(state);
    const fail = text => note('st-pin-action-status', text, 'danger');
    if (pin && !/^\d{4,12}$/.test(pin)) return fail('PIN 必须是 4 到 12 位数字。');
    if (!Number.isInteger(idle) || idle < 5 || idle > 240) return fail('空闲时间须为 5 到 240 之间的整数分钟。');
    if (!pin && !controls.configured) return fail('请先输入要设置的 PIN。');
    if (controls.needCurrent && !current) return fail('从其他设备修改时，请先输入当前 PIN。');
    busy = true;
    note('st-pin-action-status', '正在保存…', 'busy');
    const result = await post('/api/auth/pin', { pin, current_pin: current, idle_minutes: idle });
    busy = false;
    if (!alive) return;
    if (!result.ok) return fail(`保存失败：${result.error?.message || '未知错误'}`);
    if (el('st-pin-new')) el('st-pin-new').value = '';
    if (el('st-pin-current')) el('st-pin-current').value = '';
    if (pin && controls.showLogout) { location.assign('/login'); return; }
    const done = !pin ? `空闲时间已改为 ${idle} 分钟。`
      : controls.configured ? 'PIN 已更换，所有远端设备需要重新登录。' : 'PIN 已设置。';
    await load();
    note('st-pin-action-status', done, 'success');
  }

  async function disablePin() {
    if (busy) return;
    const controls = pinControlState(state);
    if (controls.disableBlocked) { note('st-pin-action-status', controls.disableBlocked, 'danger'); return; }
    busy = true;
    if (!await confirm('停用远端 PIN？', {
      hint: '所有远端登录会立即失效。之后开启局域网访问前，必须重新设置 PIN 或填写免 PIN 网段。',
      okText: '停用 PIN', danger: true,
    })) { busy = false; return; }
    if (!alive) { busy = false; return; }
    const result = await post('/api/auth/disable', {});
    busy = false;
    if (!alive) return;
    if (!result.ok) { note('st-pin-action-status', `停用失败：${result.error?.message || '未知错误'}`, 'danger'); return; }
    await load();
    note('st-pin-action-status', 'PIN 已停用。', 'success');
  }

  async function logout() {
    await post('/api/auth/logout', {});
    location.assign('/login');
  }

  return { state, render, load, saveAccess, savePin, disablePin, logout, networkChanged,
    dispose() { alive = false; loadId += 1; } };
}
