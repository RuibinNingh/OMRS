'use strict';
// Remote PIN sessions renew only on real input. Workbench pages scroll inside
// inner containers (.content is overflow:hidden), and scroll events do not bubble,
// so the listeners must use the capture phase. The phone page /m must send the
// user to /login when its session has expired instead of failing every upload.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const flush = () => new Promise(resolve => setImmediate(resolve));

function response(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
  };
}

function makeSandbox(fetchImpl, pathname = '/') {
  const listeners = [];
  const elements = {};
  const element = id => (elements[id] ||= {
    id, textContent: '', className: '', value: '', lastElementChild: { textContent: '', className: '' },
    addEventListener(name, fn) { this['on' + name] = fn; },
    prepend() {}, append() {},
  });
  const sandbox = {
    listeners, elements, assigned: [],
    console, Promise, JSON, Date, Math, Error, Number, Object, Set, Map, Intl, FormData: class { append() {} },
    setTimeout, clearTimeout, setInterval, clearInterval,
    fetch: fetchImpl,
    localStorage: { getItem: () => null, setItem() {} },
    navigator: {},
    document: {
      getElementById: element,
      querySelectorAll: () => [],
      createElement: () => element('tmp-' + Math.random()),
      addEventListener: (name, fn, options) => listeners.push({ name, options }),
      documentElement: { getAttribute: () => 'dark', setAttribute() {} },
    },
  };
  sandbox.location = {
    pathname, search: '', hash: '',
    assign: url => sandbox.assigned.push(url),
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  return sandbox;
}

function assertCaptureListeners(listeners) {
  const names = listeners.map(item => item.name);
  for (const name of ['pointerdown', 'keydown', 'touchstart', 'wheel', 'scroll']) {
    assert.ok(names.includes(name), `缺少 ${name} 活动监听`);
  }
  for (const item of listeners.filter(l => ['wheel', 'scroll'].includes(l.name))) {
    assert.equal(item.options?.capture, true, `${item.name} 必须在捕获阶段监听，内部滚动容器才会续期`);
    assert.equal(item.options?.passive, true);
  }
}

test('core.js：远端会话的活动监听覆盖内部滚动容器', async () => {
  const sb = makeSandbox(async url => {
    assert.equal(url, '/api/auth/session');
    return response(200, { status: 'ok', remote: true, authenticated: true });
  });
  vm.runInContext(fs.readFileSync(path.join(root, 'assets', 'core.js'), 'utf8'), sb, { filename: 'core.js' });
  await flush();
  assertCaptureListeners(sb.listeners);
});

function mobileScript() {
  const html = fs.readFileSync(path.join(root, 'assets', 'inbox_mobile.html'), 'utf8');
  const match = html.match(/<script>([\s\S]*?)<\/script>/);
  assert.ok(match, '手机页缺少内联脚本');
  return match[1];
}

test('/m：活动监听同样使用捕获阶段', async () => {
  const sb = makeSandbox(async url => (url === '/api/auth/session'
    ? response(200, { status: 'ok', remote: true, authenticated: true })
    : response(200, { status: 'ok', version: 'x' })), '/m');
  vm.runInContext(mobileScript(), sb, { filename: 'inbox_mobile.html' });
  await flush();
  assertCaptureListeners(sb.listeners.filter(l => l.name !== 'change'));
});

test('/m：会话过期（401）时跳转登录页并带回 /m', async () => {
  const sb = makeSandbox(async url => (url === '/api/auth/session'
    ? response(200, { status: 'ok', remote: true, authenticated: false })
    : response(401, { status: 'error', msg: '请先输入 PIN 登录' })), '/m');
  vm.runInContext(mobileScript(), sb, { filename: 'inbox_mobile.html' });
  await flush();
  assert.deepEqual(sb.assigned, ['/login?next=%2Fm']);
  assert.doesNotMatch(sb.elements.st.textContent, /已连接/);
});

test('/m：上传返回 401 时停止后续上传并跳转登录', async () => {
  let uploads = 0;
  const sb = makeSandbox(async url => {
    if (url === '/api/auth/session') return response(200, { status: 'ok', remote: false, authenticated: true });
    if (url === '/api/status') return response(200, { status: 'ok', version: 'v' });
    uploads += 1;
    return response(401, { status: 'error', msg: '请先输入 PIN 登录' });
  }, '/m');
  vm.runInContext(mobileScript(), sb, { filename: 'inbox_mobile.html' });
  await flush();
  const input = sb.elements.f;
  await input.onchange({ target: { files: [{ name: 'a.png' }, { name: 'b.png' }], value: 'x' } });
  assert.equal(uploads, 1, '401 后不应继续上传剩余文件');
  assert.deepEqual(sb.assigned, ['/login?next=%2Fm']);
});
