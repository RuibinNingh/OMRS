/** 框选设置生命周期；不在浏览器持久化凭据，迟到响应不覆盖新编辑。 */
import { get as apiGet, post as apiPost } from '../../core/api.js';
import { confirm as uiConfirm } from '../../ui/dialog.js';
export function createBoxdetect(root, { get = apiGet, post = apiPost, confirm = uiConfirm, bus } = {}) {
  const field = name => root.querySelector(`#st-box-${name}`);
  let alive = true, epoch = 0, busy = false;
  const status = (text, tone = '') => { field('status').textContent = text; field('status').dataset.tone = tone; };
  function apply(s) {
    field('provider').value = s.provider; field('mode').value = s.mode; field('base').value = s.base_url; field('private').checked = s.allow_private_targets;
    field('key').value = ''; field('key-state').textContent = s.api_key_configured ? `已保存 Key（指纹 ${s.api_key_fingerprint}）` : s.legacy ? '当前沿用旧协议；填写调用 Key 并保存后升级连接。' : '尚未保存调用 Key。';
    field('model').textContent = '尚未查询在线模型。';
  }
  async function run(operation, done) {
    if (!alive || busy) return;
    const gen = ++epoch; busy = true;
    root.querySelectorAll('#st-sec-boxdetect button, #st-sec-boxdetect input, #st-sec-boxdetect select').forEach(el => { el.disabled = true; });
    try { const result = await operation(); if (!alive || gen !== epoch) return; if (!result.ok) { status(result.error?.message || '请求失败', 'danger'); return; } done(result.data); }
    catch { if (alive && gen === epoch) status('请求失败，请重新读取并核对连接状态。', 'danger'); }
    finally { busy = false; if (alive) root.querySelectorAll('#st-sec-boxdetect button, #st-sec-boxdetect input, #st-sec-boxdetect select').forEach(el => { el.disabled = false; }); }
  }
  const load = () => run(() => get('/api/boxdetect/service'), data => { apply(data.service); field('controls').hidden = !data.local_control; status('已读取服务连接'); });
  const save = () => run(() => post('/api/boxdetect/service', { mode: field('mode').value, base_url: field('base').value.trim(), allow_private_targets: field('private').checked, ...(field('key').value ? { api_key: field('key').value } : {}) }), data => { apply(data.service); field('controls').hidden = !data.local_control; status('连接已保存，请测试已保存连接。', 'success'); bus?.emit('boxdetect:service-changed', data.service); });
  const test = () => run(() => post('/api/boxdetect/service/test', {}), data => {
    status(data.paused ? '已连接且 Key 有效；服务已暂停接单。' : '已连接且 Key 有效，服务可接收框选。', data.paused ? '' : 'success');
    const keep = data.history_retention; field('model').textContent = `当前模型：${data.model.name || '未知'} · ${data.model.imgsz || '—'} · SHA ${data.model.sha256?.slice(0, 12) || '—'}${keep?.days ? `。服务端历史保留 ${keep.days} 天，原图仅服务管理员可见。` : ''}`;
  });
  return { load, save, test,
    changed() { epoch++; field('model').textContent = '连接已编辑，请保存后重新测试。'; },
    provider: () => run(() => post('/api/config', { inbox_detect_provider: field('provider').value }), () => { status('默认框选方式已保存', 'success'); bus?.emit('boxdetect:service-changed'); }),
    async clearKey() { if (!await confirm('清除框选调用 Key？独立服务检测将不可用。', { title: '清除调用 Key', danger: true })) return; return run(() => post('/api/boxdetect/service', { clear_api_key: true }), data => { apply(data.service); field('controls').hidden = !data.local_control; status('调用 Key 已清除'); }); },
    async control(action) { if (!await confirm(`${{ start: '启动', stop: '停止', restart: '重启' }[action]}本机框选服务？此操作影响使用该服务的客户端。`, { title: '本机部署控制' })) return; return run(() => post('/api/boxdetect/control', { action }), () => status('本机服务操作已完成，请测试连接核对状态。', 'success')); },
    dispose() { alive = false; epoch++; field('key').value = ''; },
  };
}
