import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { view } from '../../assets/app/features/settings/view.js';
import { SECTIONS } from '../../assets/app/features/settings/state.js';
import { panelUrl } from '../../assets/app/domain/zuoyebang-service.js';

const moduleUrl = new URL('../../assets/app/features/settings/zuoyebang.js', import.meta.url);
const controlIds = ['st-zyb-mode', 'st-zyb-base', 'st-zyb-key', 'st-zyb-private', 'st-zyb-status', 'st-zyb-account', 'st-zyb-panel', 'st-zyb-key-state', 'st-zyb-mode-hint'];
const rootOf = () => { const controls = new Map(controlIds.map(id => [id, { value: '', checked: false, type: 'password', textContent: '', dataset: {}, removeAttribute() {} }])); return { controls, querySelector: selector => controls.get(selector.slice(1)), querySelectorAll: () => [] }; };
const config = { mode: 'local', base_url: 'http://127.0.0.1:8745', api_key_configured: true, api_key_fingerprint: 'abc', allow_private_targets: false };
const response = service => ({ ok: true, data: { service } });

test('同域反代面板保留路径前缀，拒绝路径穿越、编码和查询凭据', () => {
  assert.equal(panelUrl({ base_url: 'https://example.org/zuoyebang' }), 'https://example.org/zuoyebang/');
  assert.equal(panelUrl({ base_url: 'https://example.org/zuoyebang/' }), 'https://example.org/zuoyebang/');
  assert.equal(panelUrl({ base_url: 'http://127.0.0.1:8745' }), 'http://127.0.0.1:8745/');
  for (const path of ['/../admin', '/./admin', '/a//b', '/%2e%2e/admin', '/a%2fb', '/a;param', '/?key=secret']) {
    assert.equal(panelUrl({ base_url: 'https://example.org' + path }), '');
  }
});
async function make(root, io) { assert.ok(fs.existsSync(moduleUrl), '作业帮服务设置控制器尚未实现'); const { createZuoyebangService } = await import(moduleUrl); return createZuoyebangService(root, io); }

test('设置新增独立作业帮服务分区，表单有模式/地址/私网信任/密码框和安全面板链接', () => {
  assert.ok(SECTIONS.includes('zuoyebang'));
  const output = String(view());
  for (const id of ['st-sec-zuoyebang', 'st-zyb-mode', 'st-zyb-base', 'st-zyb-key', 'st-zyb-private']) assert.ok(output.includes(`id="${id}"`));
  assert.match(output, /st-zyb-key[^>]*type="password"/);
  assert.match(output, /target="_blank"[^>]*rel="noopener noreferrer"/);
  assert.doesNotMatch(output, /on(click|change|input)=/);
  assert.match(output, /id="st-zyb-mode"[^>]*data-change="settings.zybMode"/);
  assert.match(output, /id="st-zyb-key"[^>]*data-input="settings.zybChanged"/);
});

test('读取不回显Key，留空保存保留，成功清空输入，失败保留编辑', async () => {
  const root = rootOf(), calls = []; let failure = false;
  const controller = await make(root, { get: async () => response(config), post: async (url, payload) => { calls.push([url, payload]); return failure ? { ok: false, error: { message: '合成失败' } } : response(config); } });
  await controller.load();
  assert.equal(root.controls.get('st-zyb-key').value, '');
  await controller.save();
  assert.equal(calls[0][1].api_key, undefined);
  root.controls.get('st-zyb-mode').value = 'external';
  root.controls.get('st-zyb-base').value = 'https://gateway.example.org';
  root.controls.get('st-zyb-key').value = 'synthetic-new-key';
  failure = true; await controller.save();
  assert.equal(root.controls.get('st-zyb-key').value, 'synthetic-new-key');
  assert.equal(root.controls.get('st-zyb-base').value, 'https://gateway.example.org');
  failure = false; await controller.save();
  assert.equal(calls.at(-1)[1].api_key, 'synthetic-new-key');
  assert.equal(root.controls.get('st-zyb-key').value, '');
  assert.equal(root.controls.get('st-zyb-key').type, 'password');
});

test('清除密钥需确认，取消无写入，成功后调用独立接口', async () => {
  const root = rootOf(), calls = []; let accepted = false;
  const controller = await make(root, { get: async () => response(config), confirm: async () => accepted, post: async (url, payload) => { calls.push([url, payload]); return response({ ...config, api_key_configured: false }); } });
  await controller.load(); await controller.clearKey(); assert.equal(calls.length, 0);
  accepted = true; await controller.clearKey();
  assert.deepEqual(calls, [['/api/zuoyebang/service', { clear_api_key: true }]]);
  assert.match(root.controls.get('st-zyb-key-state').textContent, /未配置/);
});

test('测试只使用已保存配置，不传Key，不触发搜题，网络错误不抹除账号状态', async () => {
  const root = rootOf(), calls = []; let failure = false;
  const controller = await make(root, { get: async () => response(config), post: async (url, payload) => { calls.push([url, payload]); return failure ? { ok: false, error: { message: '网络故障', code: 'gateway_network' } } : { ok: true, data: { connected: true, local_session_ready: true, observations: { account: { state: 'valid' }, signing: { state: 'invalid' } } } }; } });
  await controller.load(); root.controls.get('st-zyb-key').value = 'unsaved'; await controller.test();
  assert.deepEqual(calls, [['/api/zuoyebang/service/test', {}]]);
  assert.match(root.controls.get('st-zyb-account').textContent, /账号.*有效.*签名.*失效/);
  failure = true; await controller.test();
  assert.match(root.controls.get('st-zyb-status').textContent, /网络故障/);
  assert.match(root.controls.get('st-zyb-account').textContent, /账号.*有效/);
  assert.equal(root.controls.get('st-zyb-key').value, 'unsaved');
});

test('离页清除密钥，在途读取不覆盖新编辑或卸载控件', async () => {
  const root = rootOf(); let resolve;
  const controller = await make(root, { get: () => new Promise(done => { resolve = done; }) });
  const pending = controller.load(); root.controls.get('st-zyb-base').value = 'https://edited.example.org'; controller.changed(); resolve(response(config)); await pending;
  assert.equal(root.controls.get('st-zyb-base').value, 'https://edited.example.org');
  root.controls.get('st-zyb-key').value = 'secret-input'; controller.dispose();
  assert.equal(root.controls.get('st-zyb-key').value, '');
});

test('重新读取保留同一配置的观察，切换服务或Key后清除旧账号观察', async () => {
  const root = rootOf(); let saved = config;
  const controller = await make(root, { get: async () => response(saved), post: async () => ({ ok: true, data: { local_session_ready: true, observations: { account: { state: 'valid' }, signing: { state: 'valid' } } } }) });
  await controller.load(); await controller.test(); await controller.load();
  assert.match(root.controls.get('st-zyb-account').textContent, /账号：有效/);
  saved = { ...config, api_key_fingerprint: 'replacement' };
  await controller.load();
  assert.doesNotMatch(root.controls.get('st-zyb-account').textContent, /账号：有效/);
  assert.match(root.controls.get('st-zyb-account').textContent, /尚未查询/);
});
