'use strict';
// Restart readiness: the settings page must only reload after it has seen a
// *new* service instance_id. Only the restart helpers are extracted from
// assets/app.js so that the file's global init() never runs here.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const APP = fs.readFileSync(path.resolve(__dirname, '..', 'assets', 'app.js'), 'utf8');

// Return the full source of a top-level function starting at `head`: match the
// parameter list's parentheses first (defaults may contain braces), then the
// body's braces, skipping strings, template literals and comments.
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

function extractConst(name) {
  const match = APP.match(new RegExp(`const ${name}\\s*=[^;]+;`));
  assert.ok(match, `assets/app.js 中缺少常量 ${name}`);
  return match[0];
}

function loadRestartHelpers() {
  const status = { innerHTML: '' };
  const sandbox = {
    reloads: 0,
    status,
    console, Date, Promise, Error, Math, JSON, setTimeout, clearTimeout, AbortController,
    escapeHtml: value => String(value).replace(/[&<>"']/g, ch => `&#${ch.charCodeAt(0)};`),
    document: { getElementById: id => (id === 'st-status' ? status : null) },
    api: async () => { throw new Error('api() not stubbed'); },
  };
  sandbox.window = { location: { reload: () => { sandbox.reloads += 1; } } };
  vm.createContext(sandbox);
  vm.runInContext([
    extractConst('RESTART_READY_TIMEOUT_MS'),
    extract('async function waitForRestartReady('),
    extract('async function doRestart('),
    'this.waitForRestartReady = waitForRestartReady; this.doRestart = doRestart;',
  ].join('\n'), sandbox, { filename: 'app.js#restart' });
  return sandbox;
}

// Virtual clock: sleep() advances time instantly so timeouts are deterministic.
function fakeClock() {
  let t = 0;
  return { now: () => t, sleep: async ms => { t += ms; } };
}

test('waitForRestartReady 忽略旧实例，看到新 instance_id 才返回 true', async () => {
  const sb = loadRestartHelpers();
  const clock = fakeClock();
  const answers = ['old', 'old', 'new'];
  let probes = 0;
  const ready = await sb.waitForRestartReady('old', {
    ...clock,
    request: async url => {
      assert.equal(url, '/api/auth/session');
      return { status: 'ok', instance_id: answers[probes++] };
    },
  });
  assert.equal(ready, true);
  assert.equal(probes, 3);
});

test('doRestart：旧 ID 持续期间不刷新，探测到新 ID 后刷新一次', async () => {
  const sb = loadRestartHelpers();
  const clock = fakeClock();
  const probes = ['old', 'old', 'old', 'new'];
  const calls = [];
  sb.api = async (url, options = {}) => {
    calls.push(`${options.method || 'GET'} ${url}`);
    if (url === '/api/restart') return { status: 'ok' };
    if (calls.filter(c => c === 'GET /api/auth/session').length === 1) return { status: 'ok', instance_id: 'old' };
    assert.equal(sb.reloads, 0, '仍是旧实例时不得刷新');
    return { status: 'ok', instance_id: probes.shift() };
  };
  await sb.doRestart(true, { ...clock });
  assert.equal(sb.reloads, 1);
  assert.deepEqual(calls.slice(0, 2), ['GET /api/auth/session', 'POST /api/restart']);
  assert.equal(probes.length, 0);
});

test('探测一直看到旧实例：超时返回 false，doRestart 不刷新并提示', async () => {
  const sb = loadRestartHelpers();
  const clock = fakeClock();
  let probeCount = 0;
  sb.api = async url => {
    if (url === '/api/restart') return { status: 'ok' };
    probeCount += 1;
    return { status: 'ok', instance_id: 'old' };
  };
  await sb.doRestart(true, { ...clock });
  assert.equal(sb.reloads, 0);
  assert.ok(probeCount > 10, '超时前应持续轮询');
  assert.match(sb.status.innerHTML, /未检测到新服务实例/);
  assert.ok(clock.now() <= 90_000, '等待时间必须有界（90 秒）');
});

test('连接拒绝 / Abort 视为未就绪并继续重试', async () => {
  const sb = loadRestartHelpers();
  const clock = fakeClock();
  const outcomes = [
    () => { throw new TypeError('Failed to fetch'); },
    () => { const e = new Error('aborted'); e.name = 'AbortError'; throw e; },
    () => ({ status: 'ok', instance_id: 'new' }),
  ];
  let i = 0;
  const ready = await sb.waitForRestartReady('old', { ...clock, request: async () => outcomes[i++]() });
  assert.equal(ready, true);
  assert.equal(i, 3);
});

test('网络错误持续到超时也不能当成就绪', async () => {
  const sb = loadRestartHelpers();
  const clock = fakeClock();
  const ready = await sb.waitForRestartReady('old', {
    ...clock,
    timeoutMs: 5_000,
    request: async () => { throw new TypeError('Failed to fetch'); },
  });
  assert.equal(ready, false);
  assert.ok(clock.now() >= 5_000 && clock.now() <= 5_500);
});

test('读不到重启前 instance_id 时不发重启、不刷新', async () => {
  const sb = loadRestartHelpers();
  const calls = [];
  sb.api = async (url, options = {}) => {
    calls.push(`${options.method || 'GET'} ${url}`);
    return { status: 'ok' };
  };
  await sb.doRestart(true, fakeClock());
  assert.deepEqual(calls, ['GET /api/auth/session']);
  assert.equal(sb.reloads, 0);
  assert.match(sb.status.innerHTML, /重启未完成/);
});
