'use strict';
// Settings page: section navigation, access overview, PIN control visibility and
// "does saving restart the service" decisions. Only the helpers are extracted from
// assets/app.js so its global init() never runs.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const APP = fs.readFileSync(path.resolve(__dirname, '..', 'assets', 'app.js'), 'utf8');

function extract(head) {
  const start = APP.indexOf(head);
  assert.notEqual(start, -1, `assets/app.js 中缺少 ${head}`);
  const stack = [];
  let inBody = false;
  for (let i = start + head.length - 1; i < APP.length; i++) {
    const ch = APP[i];
    if (ch === '/' && APP[i + 1] === '/') { i = APP.indexOf('\n', i); continue; }
    if (ch === '/' && APP[i + 1] === '*') { i = APP.indexOf('*/', i) + 1; continue; }
    if (ch === '"' || ch === "'" || ch === '`') {
      for (i++; i < APP.length && APP[i] !== ch; i++) if (APP[i] === '\\') i++;
      continue;
    }
    if (ch === '(' || ch === '{') {
      if (ch === '{' && stack.length === 0) inBody = true;
      stack.push(ch);
    } else if (ch === ')' || ch === '}') {
      stack.pop();
      if (inBody && stack.length === 0) return APP.slice(start, i + 1);
    }
  }
  throw new Error(`无法完整提取 ${head}`);
}

function load() {
  const store = {};
  const tabs = ['appearance', 'access', 'ai', 'data', 'service'].map(name => ({
    dataset: { stSection: name }, attrs: {}, tabIndex: 0, focused: false,
    setAttribute(k, v) { this.attrs[k] = v; }, focus() { this.focused = true; },
  }));
  const panels = tabs.map(t => ({ id: `st-sec-${t.dataset.stSection}`, active: false,
    classList: { toggle(_c, on) { panels.find(p => p === this.owner).active = on; } } }));
  panels.forEach(p => { p.classList.owner = p; });
  const sandbox = {
    tabs, panels, console, JSON, Math, Number, String, Array,
    asNumber: (v, d) => (Number.isFinite(Number(v)) ? Number(v) : d),
    localStorage: { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = String(v); } },
    document: {
      querySelectorAll: sel => (sel.includes('st-nav-item') ? tabs : sel.includes('st-section') ? panels : []),
    },
  };
  vm.createContext(sandbox);
  vm.runInContext([
    "const SETTINGS_SECTIONS = ['appearance', 'access', 'ai', 'data', 'service'];",
    "const SETTINGS_SECTION_KEY = 'omrs-settings-section';",
    'let ST_STATE = { cfg: null, auth: null, status: null };',
    ...['function currentSettingsSection(', 'function openSettingsSection(', 'function parseLanCidrs(',
      'function runningListenExternal(', 'function networkNeedsRestart(', 'function describeAccess(',
      'function pinControlState('].map(extract),
    'this.setState = s => { ST_STATE = s; };',
    Object.keys({ currentSettingsSection: 1, openSettingsSection: 1, parseLanCidrs: 1, runningListenExternal: 1,
      networkNeedsRestart: 1, describeAccess: 1, pinControlState: 1 }).map(n => `this.${n} = ${n};`).join(''),
  ].join('\n'), sandbox, { filename: 'app.js#settings' });
  return sandbox;
}

const LOCAL = { status: 'ok', remote: false, authenticated: true, lan_pin_exempt: false };
const REMOTE_SESSION = { status: 'ok', remote: true, authenticated: true, lan_pin_exempt: false };
const LAN_EXEMPT = { status: 'ok', remote: true, authenticated: true, lan_pin_exempt: true };

test('分区导航：切换、持久化，非法名称回退到第一个分区', () => {
  const sb = load();
  assert.equal(sb.currentSettingsSection(), 'appearance');
  sb.openSettingsSection('access');
  assert.equal(sb.currentSettingsSection(), 'access');
  assert.deepEqual(sb.panels.map(p => p.active), [false, true, false, false, false]);
  assert.equal(sb.tabs[1].attrs['aria-selected'], 'true');
  assert.equal(sb.tabs[1].tabIndex, 0);
  assert.equal(sb.tabs[0].tabIndex, -1);
  assert.equal(sb.openSettingsSection('nope'), 'appearance');
});

test('免 PIN 网段输入：支持中英文逗号和换行', () => {
  const sb = load();
  assert.deepEqual([...sb.parseLanCidrs(' 192.168.0.0/24，10.0.0.0/8\nfd00::/8, ')],
    ['192.168.0.0/24', '10.0.0.0/8', 'fd00::/8']);
});

test('是否需要重启：以正在运行的监听范围为准，而不是已保存的配置', () => {
  const sb = load();
  const state = { cfg: { allow_external: true }, status: { listen_external: false }, auth: LOCAL };
  assert.equal(sb.networkNeedsRestart(true, state), true, '配置已开但尚未重启，保存时应重启以生效');
  assert.equal(sb.networkNeedsRestart(false, state), false);
  assert.equal(sb.networkNeedsRestart(true, { cfg: { allow_external: true }, status: null }), false,
    '读不到运行状态时回退到已保存配置');
});

test('访问概览：本机 / PIN 保护 / 免 PIN 网段 / 待重启 / 读取失败', () => {
  const sb = load();
  let info = sb.describeAccess({ cfg: { allow_external: false, lan_pin_exempt_cidrs: [] }, status: { listen_external: false }, auth: LOCAL });
  assert.equal(info.level, 'local');
  assert.match(info.summary, /只有这台电脑/);
  assert.equal(info.you, '本机直连，免 PIN');

  info = sb.describeAccess({ cfg: { allow_external: true, pin_configured: true, idle_minutes: 45, lan_pin_exempt_cidrs: [] }, status: { listen_external: true }, auth: REMOTE_SESSION });
  assert.equal(info.level, 'guarded');
  assert.match(info.pin, /45 分钟/);
  assert.equal(info.you, '远端，已用 PIN 登录');

  info = sb.describeAccess({ cfg: { allow_external: true, pin_configured: false, lan_pin_exempt_cidrs: ['192.168.0.0/24'] }, status: { listen_external: true }, auth: LAN_EXEMPT });
  assert.equal(info.level, 'open');
  assert.match(info.summary, /其他设备会被拒绝/);

  info = sb.describeAccess({ cfg: { allow_external: true, pin_configured: true, lan_pin_exempt_cidrs: [] }, status: { listen_external: false }, auth: LOCAL });
  assert.equal(info.level, 'local');
  assert.match(info.summary, /重启服务后生效/);
  assert.equal(info.listenNote, '重启后改为所有网卡');

  assert.equal(sb.describeAccess({ cfg: null, auth: null, status: null }).level, 'error');
});

test('PIN 控件：本机首次设置', () => {
  const sb = load();
  const st = sb.pinControlState({ cfg: { pin_configured: false, lan_pin_exempt_cidrs: [] }, auth: LOCAL });
  assert.equal(st.needCurrent, false);
  assert.equal(st.showLogout, false);
  assert.equal(st.showDisable, false);
  assert.equal(st.newLabel, '设置 PIN');
});

test('PIN 控件：远端已登录须输入当前 PIN、可退出、不能停用', () => {
  const sb = load();
  const st = sb.pinControlState({ cfg: { pin_configured: true, allow_external: true }, auth: REMOTE_SESSION });
  assert.equal(st.needCurrent, true);
  assert.equal(st.showLogout, true);
  assert.match(st.disableBlocked, /只能在本机/);
  assert.equal(st.showDisable, false, '远端无法停用，按钮直接隐藏');
  assert.match(st.statusText, /只能在本机上停用 PIN/);
});

test('PIN 控件：免 PIN 网段设备首次设置不要求当前 PIN，也不显示退出', () => {
  const sb = load();
  const st = sb.pinControlState({ cfg: { pin_configured: false, lan_pin_exempt_cidrs: ['192.168.0.0/24'] }, auth: LAN_EXEMPT });
  assert.equal(st.needCurrent, false);
  assert.equal(st.showLogout, false);
  assert.match(st.statusText, /免 PIN 网段/);
});

test('PIN 控件：本机开着局域网访问时停用按钮被锁定并说明原因', () => {
  const sb = load();
  const st = sb.pinControlState({ cfg: { pin_configured: true, allow_external: true }, auth: LOCAL });
  assert.equal(st.showDisable, true);
  assert.match(st.disableBlocked, /先关闭局域网访问/);
  assert.equal(sb.pinControlState({ cfg: { pin_configured: true, allow_external: false }, auth: LOCAL }).disableBlocked, '');
});
