import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createCamera } from '../../assets/app/features/create/zyb-camera.js';
import { newZybState, bindRender, extractionSnapshot, mergeExtraction, commitPayload } from '../../assets/app/features/create/zyb-state.js';
import { STAGES, stageOf } from '../../assets/app/features/create/state.js';
import { accountView, cameraView, candidatesView } from '../../assets/app/features/create/zyb-view.js';

 test('录入服务菜单只打开设置与独立面板，不管理账号或迁移会话', () => {
  const s = { ...newZybState(), accountPanel: 'main', service: { base_url: 'http://127.0.0.1:8745', mode: 'local' }, session: { connected: true, local_session_ready: true, observations: { account: { state: 'valid' }, signing: { state: 'valid' } }, panel_url: 'https://evil.example/?token=secret' } };
  const output = String(accountView(s));
  assert.match(output, /打开服务设置/);
  assert.match(output, /aria-expanded="true"/);
  assert.match(output, /href="http:\/\/127\.0\.0\.1:8745\/"[^>]*target="_blank"[^>]*rel="noopener noreferrer"/);
  assert.doesNotMatch(output, /zyb-profile|zybLogin|扫码登录|create\.zybAccount|evil\.example|token=/);
  s.sessionError = '连接失败';
  assert.match(String(accountView(s)), /连接失败/);
  assert.match(String(accountView(s)), /账号：有效/);
  assert.doesNotMatch(String(accountView(s)), /账号.*已过期/);
 });
 test('候选保留来源网关与模式的非敏感投影', () => {
  const s = newZybState();
  s.search = { id: 'search-test', service: { mode: 'external', base_url: 'https://gateway.example.org' }, candidates: [{ index: 0, title: '原题', location: 0 }] };
  assert.match(String(candidatesView(s)), /来源.*外部.*https:\/\/gateway\.example\.org/);
 });

const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { resolve, promise }; };
const record = id => ({ id, status: 'ready', images: { question: { url: 'q' }, answer: { url: 'a' } }, extraction: {} });

test('导航替换草稿按钮而旧草稿地址仍可交接', () => {
  assert.ok(STAGES.some(stage => stage.id === 'zuoyebang'));
  assert.ok(!STAGES.some(stage => stage.id === 'drafts'));
  assert.equal(stageOf('drafts'), 'drafts');
});
test('摄像头只请求后置优先视频，关闭释放全部资源', async () => {
  let request, stopped = 0;
  const stream = { getTracks: () => [{ stop: () => { stopped++; } }], getVideoTracks: () => [] };
  const video = { play: async () => {} };
  const camera = createCamera({ secure: true, video, mediaDevices: { getUserMedia: async options => { request = options; return stream; } } });
  await camera.open();
  assert.deepEqual(request, { video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1440 } }, audio: false });
  assert.equal(video.srcObject, stream);
  camera.dispose();
  assert.equal(stopped, 1); assert.equal(video.srcObject, null);
});
test('离页后到达的摄像头授权立即停止且不绑定到旧视频', async () => {
  const pending = deferred(); let stopped = 0;
  const video = { play: async () => assert.fail('不能播放旧请求') };
  const camera = createCamera({ secure: true, video, mediaDevices: { getUserMedia: () => pending.promise } });
  const opening = camera.open(); camera.stop();
  pending.resolve({ getTracks: () => [{ stop: () => { stopped++; } }] }); await opening;
  assert.equal(stopped, 1); assert.equal(video.srcObject, null);
});
test('不安全地址和权限拒绝给出可操作提示', async () => {
  const states = [];
  await createCamera({ secure: false, changed: state => states.push(state) }).open();
  assert.match(states.at(-1).message, /HTTPS/);
  await createCamera({ secure: true, changed: state => states.push(state), mediaDevices: { getUserMedia: async () => { throw { name: 'NotAllowedError' }; } } }).open();
  assert.match(states.at(-1).message, /权限/);
});
test('拍照按视频原始尺寸取帧，不使用预览CSS尺寸并释放画布', async () => {
  const video = { play: async () => {}, readyState: 2, videoWidth: 1920, videoHeight: 1440, clientWidth: 320 };
  const blob = new Blob(['photo'], { type: 'image/jpeg' });
  const calls = [];
  const canvas = { getContext: () => ({ drawImage: (...args) => calls.push(args) }),
    toBlob(done, type, quality) { assert.equal(this.width, 1920); assert.equal(this.height, 1440); assert.equal(type, 'image/jpeg'); assert.equal(quality, .95); done(blob); } };
  const camera = createCamera({ secure: true, video, createCanvas: () => canvas, mediaDevices: { getUserMedia: async () => ({ getTracks: () => [], getVideoTracks: () => [] }) } });
  await camera.open();
  assert.equal(await camera.capture(), blob);
  assert.deepEqual(calls, [[video, 0, 0, 1920, 1440]]);
  assert.equal(canvas.width, 0); assert.equal(canvas.height, 0);
  camera.stop();
});
test('尚无视频帧时不能生成空白照片', async () => {
  const camera = createCamera({ secure: true, video: { play: async () => {}, readyState: 1, videoWidth: 0, videoHeight: 0 },
    mediaDevices: { getUserMedia: async () => ({ getTracks: () => [], getVideoTracks: () => [] }) }, createCanvas: () => assert.fail('不能创建空画布') });
  await camera.open(); await assert.rejects(camera.capture(), /尚未就绪/); camera.stop();
});
test('摄像头开启后提供拍照按钮，不因网关未连接禁止本地取图', () => {
  const s = newZybState(); s.camera.on = true;
  const output = String(cameraView(s));
  assert.match(output, /拍照搜题/); assert.match(output, /关闭摄像头/);
  assert.doesNotMatch(output, /disabled/);
});
test('拍照编码期间切模式或离页，迟到照片不得进入搜题', async () => {
  let finish;
  const canvas = { getContext: () => ({ drawImage() {} }), toBlob(done) { finish = done; } };
  const camera = createCamera({ secure: true, video: { play: async () => {}, readyState: 2, videoWidth: 1280, videoHeight: 720 },
    mediaDevices: { getUserMedia: async () => ({ getTracks: () => [], getVideoTracks: () => [] }) }, createCanvas: () => canvas });
  await camera.open(); const capture = camera.capture(); camera.stop(); finish(new Blob(['photo']));
  await assert.rejects(capture, /已取消/); assert.equal(canvas.width, 0);
});
test('浏览器无法编码照片时提示重拍并释放画布', async () => {
  const canvas = { getContext: () => ({ drawImage() {} }), toBlob(done) { done(null); } };
  const camera = createCamera({ secure: true, video: { play: async () => {}, readyState: 2, videoWidth: 1280, videoHeight: 720 },
    mediaDevices: { getUserMedia: async () => ({ getTracks: () => [], getVideoTracks: () => [] }) }, createCanvas: () => canvas });
  await camera.open(); await assert.rejects(camera.capture(), /未能生成照片/);
  assert.equal(canvas.width, 0); camera.stop();
});
test('切换候选不会沿用上一题正文和旧 AI 结果', () => {
  const s = newZybState(); bindRender(s, record('old')); const snap = extractionSnapshot(s);
  s.sections.question.text = '旧正文'; bindRender(s, record('new'));
  assert.equal(s.sections.question.text, '');
  assert.equal(mergeExtraction(s, { ...record('old'), extraction: { question: { mode: 'text', text: '迟到结果' } } }, snap), false);
});
test('识别在途修改的正文和保存方式保留，未改的答案可合并', () => {
  const s = newZybState(); bindRender(s, record('r')); const snap = extractionSnapshot(s);
  s.sections.question = { mode: 'text', text: '人工核对正文' }; s.versions.question++;
  mergeExtraction(s, { ...record('r'), extraction: { question: { mode: 'image', text: '', reason: '图形' }, answer: { mode: 'text', text: '完整答案' } } }, snap);
  assert.equal(s.sections.question.text, '人工核对正文'); assert.equal(s.sections.question.mode, 'text');
  assert.equal(s.sections.answer.text, '完整答案');
});
test('入库使用来源编号和两区保存方式，不从客户端传外部 HTML', () => {
  const s = newZybState(); bindRender(s, record('r')); s.form.subject = '数学'; s.form.category = '几何';
  s.sections.answer = { mode: 'text', text: '完整原解析' };
  const payload = commitPayload(s);
  assert.equal(payload.render_id, 'r'); assert.equal(payload.sections.question.mode, 'image');
  assert.equal(payload.sections.answer.text, '完整原解析'); assert.equal(payload.html, undefined);
  s.sections.answer.text = ''; assert.throws(() => commitPayload(s), /正文不能为空/);
});
test('刷新后的预留题卡恢复首次提交内容与回执', () => {
  const s = newZybState();
  bindRender(s, { ...record('r'), commit: { result: { uid: '几何1' }, payload: { subject: '数学', category: '几何', difficulty: 5, related_tags: [], labels: [], cause: '', sections: { question: { mode: 'image', text: '' }, answer: { mode: 'text', text: '首次提交正文' } } } } });
  assert.equal(s.result.uid, '几何1'); assert.equal(s.sections.answer.text, '首次提交正文');
});
