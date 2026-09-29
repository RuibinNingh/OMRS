import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import { SECTIONS, sectionOf, parseLanCidrs, networkNeedsRestart, describeAccess, pinControlState } from '../../assets/app/features/settings/state.js';
import { formatBytes, optValues } from '../../assets/app/features/settings/storage-state.js';
import { formatUptime, waitForRestartReady } from '../../assets/app/features/settings/service.js';
import { startActivityTracking } from '../../assets/app/core/activity.js';
import { createAgent } from '../../assets/app/features/settings/agent.js';
import { agentView } from '../../assets/app/features/settings/agent-view.js';
import { createAi } from '../../assets/app/features/settings/ai.js';
import { aiView } from '../../assets/app/features/settings/ai-view.js';

const LOCAL = { status: 'ok', remote: false, authenticated: true, lan_pin_exempt: false };
const REMOTE = { status: 'ok', remote: true, authenticated: true, lan_pin_exempt: false };
const EXEMPT = { status: 'ok', remote: true, authenticated: true, lan_pin_exempt: true };

test('AI 识别思考开关读取、开启与关闭后保存', async () => {
  assert.match(String(aiView()), /id="st-ai-thinking"/);
  let cfg = { ai_model: 'deepseek-flash', ai_thinking: false };
  const saves = [];
  const fields = Object.fromEntries(['st-ai-thinking', 'st-ai-model', 'st-ai-settings-status']
    .map(id => [id, { value: '', checked: false, textContent: '', dataset: {} }]));
  const root = { querySelector: selector => fields[selector.slice(1)] || null };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    if (init.method === 'POST') {
      const payload = JSON.parse(init.body);
      saves.push(payload);
      cfg = { ...cfg, ...payload };
      return new Response(JSON.stringify({ status: 'ok' }), { status: 200,
        headers: { 'content-type': 'application/json' } });
    }
    return new Response(JSON.stringify(cfg), { status: 200,
      headers: { 'content-type': 'application/json' } });
  };
  try {
    const ai = createAi(root);
    await ai.load();
    assert.equal(fields['st-ai-thinking'].checked, false);
    fields['st-ai-thinking'].checked = true;
    await ai.save();
    assert.equal(saves.at(-1).ai_thinking, true);
    assert.equal(fields['st-ai-thinking'].checked, true);
    fields['st-ai-thinking'].checked = false;
    await ai.save();
    assert.equal(saves.at(-1).ai_thinking, false);
    assert.equal(fields['st-ai-thinking'].checked, false);
    ai.dispose();
  } finally { globalThis.fetch = originalFetch; }
});

test('框选三态及全文字训练设置保存，明确选手动才替换自动', async () => {
  const view = String(agentView());
  assert.match(view, /value="auto">自动/);
  assert.match(view, /id="st-draft-force-crop"/);
  let cfg = { agent_enabled: true, agent_model: 'test', draft_mode: 'silent', draft_crop_mode: 'auto',
    draft_train_default: false, draft_force_crop: false };
  const fields = Object.fromEntries(['st-agent-enabled', 'st-agent-model', 'st-draft-mode', 'st-draft-crop-mode',
    'st-draft-train-default', 'st-draft-force-crop', 'st-agent-status'].map(id => [id, { value: '', checked: false, textContent: '', dataset: {} }]));
  const root = { querySelector: selector => fields[selector.slice(1)] || null };
  const originalFetch = globalThis.fetch;
  const saves = [];
  globalThis.fetch = async (url, init = {}) => {
    let data;
    if (url === '/api/agent/status') data = { faux: false };
    else if (init.method === 'POST') { data = JSON.parse(init.body); saves.push(data); cfg = { ...cfg, ...data }; }
    else data = cfg;
    return new Response(JSON.stringify(data), { status: 200, headers: { 'content-type': 'application/json' } });
  };
  try {
    const agent = createAgent(root, { emit() {} });
    await agent.load();
    assert.equal(fields['st-draft-crop-mode'].value, 'auto');
    fields['st-draft-train-default'].checked = true;
    fields['st-draft-force-crop'].checked = true;
    assert.equal(await agent.save(), true);
    assert.equal(saves.at(-1).draft_crop_mode, 'auto');
    assert.equal(saves.at(-1).draft_force_crop, true);
    fields['st-draft-crop-mode'].value = 'manual';
    assert.equal(await agent.save(), true);
    assert.equal(saves.at(-1).draft_crop_mode, 'manual');
    agent.dispose();
  } finally { globalThis.fetch = originalFetch; }
});

test('助手最大输出 Token 默认值、保存和输入校验', async () => {
  assert.match(String(agentView()), /id="st-agent-max-output-tokens"[^>]*value="10240"/);
  let cfg = { agent_enabled: true, agent_model: 'test' };
  const fields = Object.fromEntries(['st-agent-enabled', 'st-agent-model', 'st-agent-max-output-tokens', 'st-agent-status']
    .map(id => [id, { value: '', checked: false, textContent: '', dataset: {}, focus() {} }]));
  const root = { querySelector: selector => fields[selector.slice(1)] || null };
  const originalFetch = globalThis.fetch;
  const saves = [];
  globalThis.fetch = async (url, init = {}) => {
    const data = url === '/api/agent/status' ? { faux: false } : init.method === 'POST' ? JSON.parse(init.body) : cfg;
    if (init.method === 'POST') { saves.push(data); cfg = { ...cfg, ...data }; }
    return new Response(JSON.stringify(data), { status: 200, headers: { 'content-type': 'application/json' } });
  };
  try {
    const agent = createAgent(root, { emit() {} });
    await agent.load();
    assert.equal(fields['st-agent-max-output-tokens'].value, 10240);
    fields['st-agent-max-output-tokens'].value = '16384';
    assert.equal(await agent.save(), true);
    assert.equal(saves.at(-1).agent_max_output_tokens, 16384);
    fields['st-agent-max-output-tokens'].value = '1.5';
    assert.equal(await agent.save(), false);
    assert.equal(saves.length, 1);
    agent.dispose();
  } finally { globalThis.fetch = originalFetch; }
});

test('分区名称非法时回到外观，六个分区次序稳定', () => {
  assert.deepEqual(SECTIONS, ['appearance', 'access', 'ai', 'assistant', 'data', 'service']);
  assert.equal(sectionOf('data'), 'data');
  assert.equal(sectionOf('unknown'), 'appearance');
});
test('免 PIN 网段按中英文逗号和换行拆分', () => {
  assert.deepEqual(parseLanCidrs(' 192.168.0.0/24，10.0.0.0/8\nfd00::/8, '),
    ['192.168.0.0/24', '10.0.0.0/8', 'fd00::/8']);
});
test('是否重启取决于运行监听范围', () => {
  const state = { cfg: { allow_external: true }, status: { listen_external: false }, auth: LOCAL };
  assert.equal(networkNeedsRestart(true, state), true);
  assert.equal(networkNeedsRestart(false, state), false);
  assert.equal(networkNeedsRestart(true, { cfg: { allow_external: true }, status: null }), false);
});
test('访问概览覆盖本机、PIN、免 PIN、待重启和失败', () => {
  const local = describeAccess({ cfg: { allow_external: false, lan_pin_exempt_cidrs: [] }, status: { listen_external: false }, auth: LOCAL });
  assert.equal(local.level, 'local'); assert.match(local.summary, /只有这台电脑/); assert.equal(local.you, '本机直连，免 PIN');
  const guarded = describeAccess({ cfg: { allow_external: true, pin_configured: true, idle_minutes: 45, lan_pin_exempt_cidrs: [] }, status: { listen_external: true }, auth: REMOTE });
  assert.equal(guarded.level, 'guarded'); assert.match(guarded.pin, /45 分钟/); assert.equal(guarded.you, '远端，已用 PIN 登录');
  const exempt = describeAccess({ cfg: { allow_external: true, pin_configured: false, lan_pin_exempt_cidrs: ['192.168.0.0/24'] }, status: { listen_external: true }, auth: EXEMPT });
  assert.equal(exempt.level, 'open'); assert.match(exempt.summary, /其他设备会被拒绝/);
  const pending = describeAccess({ cfg: { allow_external: true, pin_configured: true, lan_pin_exempt_cidrs: [] }, status: { listen_external: false }, auth: LOCAL });
  assert.match(pending.summary, /重启服务后生效/); assert.equal(pending.listenNote, '重启后改为所有网卡');
  assert.equal(describeAccess({ cfg: null, auth: null, status: null }).level, 'error');
});
test('本机首次设置 PIN 时无需当前 PIN', () => {
  const s = pinControlState({ cfg: { pin_configured: false, lan_pin_exempt_cidrs: [] }, auth: LOCAL });
  assert.equal(s.needCurrent, false); assert.equal(s.showLogout, false);
  assert.equal(s.showDisable, false); assert.equal(s.newLabel, '设置 PIN');
});
test('远端已登录时更换 PIN 须输入当前 PIN，可登出但不可停用', () => {
  const s = pinControlState({ cfg: { pin_configured: true, allow_external: true }, auth: REMOTE });
  assert.equal(s.needCurrent, true); assert.equal(s.showLogout, true);
  assert.equal(s.showDisable, false); assert.match(s.disableBlocked, /只能在本机/);
});
test('免 PIN 网段首次设置时不要求当前 PIN，也不显示登出', () => {
  const s = pinControlState({ cfg: { pin_configured: false, lan_pin_exempt_cidrs: ['192.168.0.0/24'] }, auth: EXEMPT });
  assert.equal(s.needCurrent, false); assert.equal(s.showLogout, false); assert.match(s.statusText, /免 PIN 网段/);
});
test('本机开启局域网时不可停用 PIN', () => {
  const s = pinControlState({ cfg: { pin_configured: true, allow_external: true }, auth: LOCAL });
  assert.equal(s.showDisable, true); assert.match(s.disableBlocked, /先关闭局域网访问/);
  assert.equal(pinControlState({ cfg: { pin_configured: true, allow_external: false }, auth: LOCAL }).disableBlocked, '');
});
test('占用和大小投影保留数据链与图片候选', () => {
  const summary = { sizes: { data_chain: { bytes: 1024, files: 2 }, question_files: { bytes: 2048, files: 3 }, question_images: { bytes: 4096, files: 4 } } };
  assert.equal(formatBytes(1024), '1.0 KB');
  assert.equal(optValues(summary).center, '7.0 KB');
  const scan = { exact: false, potential_bytes: 3000, candidate_count: 2 };
  assert.match(optValues(summary, scan).center, /待深扫 2 张/);
  assert.equal(optValues(summary, scan, { checked_bytes: 1000 }).items[2].bytes, 2000);
});
test('精确扫描与压缩任务只报告未检查大小', () => {
  const summary = { sizes: { question_images: { bytes: 9000, files: 9 } } };
  const scan = { exact: true, compressible_bytes: 4000, candidate_count: 3 };
  assert.equal(optValues(summary, scan).center, '可压缩 3.9 KB');
  const ongoing = optValues(summary, scan, { checked_bytes: 1000, saved_bytes: 200 });
  assert.equal(ongoing.items[2].bytes, 3000);
  assert.match(ongoing.center, /已节省 200 B/);
});
test('运行时间按天、小时和分钟显示', () => {
  assert.equal(formatUptime(62), '1分钟');
  assert.equal(formatUptime(3660), '1小时 1分钟');
  assert.equal(formatUptime(90000), '1天 1小时');
});
function clock() { let t = 0; return { now: () => t, sleep: async ms => { t += ms; } }; }
test('重启探测忽略旧实例，只认新 instance_id', async () => {
  const answers = ['old', 'old', 'new']; let calls = 0;
  const ready = await waitForRestartReady('old', { ...clock(), request: async path => {
    assert.equal(path, '/api/auth/session'); return { status: 'ok', instance_id: answers[calls++] };
  } });
  assert.equal(ready, true); assert.equal(calls, 3);
});
test('重启探测中断连与 Abort 后仍继续，超时则失败', async () => {
  let calls = 0;
  const ready = await waitForRestartReady('old', { ...clock(), request: async () => {
    calls++; if (calls < 3) throw new Error('连接中断'); return { status: 'ok', instance_id: 'new' };
  } });
  assert.equal(ready, true); assert.equal(calls, 3);
  const bounded = clock();
  assert.equal(await waitForRestartReady('old', { ...bounded, timeoutMs: 5000, request: async () => null }), false);
  assert.equal(bounded.now(), 5000);
});
test('缺少旧实例 ID 时不能误判就绪', async () => {
  let calls = 0;
  assert.equal(await waitForRestartReady('', { request: async () => { calls++; return { instance_id: 'new' }; } }), false);
  assert.equal(calls, 0);
});

// 远端活动续期和手机页会话回归：从旧测试迁入，仍覆盖原四个用例。
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
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

test('core/activity.js：远端会话的活动监听覆盖内部滚动容器', async () => {
  const sb = makeSandbox(async url => {
    assert.equal(url, '/api/auth/session');
    return response(200, { status: 'ok', remote: true, authenticated: true });
  });
  await startActivityTracking({ addEventListener: (...args) => sb.listeners.push({ name: args[0], options: args[2] }) }, sb.fetch);
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
