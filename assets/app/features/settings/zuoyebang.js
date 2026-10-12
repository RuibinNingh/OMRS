/** 服务配置控制器：无浏览器持久化凭据；连接测试只核验已保存配置。 */
import { get as apiGet, post as apiPost } from '../../core/api.js';
import { confirm as uiConfirm } from '../../ui/dialog.js';
import { panelUrl, serviceStatus, sameService } from '../../domain/zuoyebang-service.js';

export function createZuoyebangService(root, { get = apiGet, post = apiPost, confirm = uiConfirm, bus } = {}) {
  const field = name => root.querySelector(`#st-zyb-${name}`);
  let alive = true, epoch = 0, busy = false, saved = null;
  function status(message, tone = '') { const node = field('status'); node.textContent = message; node.dataset.tone = tone; }
  function modeHint() {
    const local = field('mode').value === 'local';
    field('private').disabled = local;
    field('mode-hint').textContent = local ? '本地是独立网关，不是旧直连；地址须为 OMRS 主机 loopback，可自定义端口。' : '外部默认仅公网 HTTPS；受信任的私网必须显式启用，才可用私网 HTTP。';
  }
  function apply(config) {
    if (!sameService(saved, config)) field('account').textContent = '账号与签名尚未查询；请测试已保存连接。';
    saved = { ...config };
    field('mode').value = config.mode; field('base').value = config.base_url;
    field('private').checked = config.allow_private_targets;
    field('key').value = ''; field('key').type = 'password';
    field('key-state').textContent = config.api_key_configured ? `Key 已配置（指纹 ${config.api_key_fingerprint}）；留空保存即保留。` : 'Key 未配置。';
    const panel = field('panel'), target = panelUrl(config);
    panel.href = target; panel.setAttribute?.('aria-disabled', target ? 'false' : 'true');
    if (!target) panel.removeAttribute('href');
    modeHint();
  }
  async function run(operation, success) {
    if (!alive || busy) return;
    const token = ++epoch; busy = true;
    root.querySelectorAll('#st-sec-zuoyebang input, #st-sec-zuoyebang select, #st-sec-zuoyebang button').forEach(el => { el.disabled = true; });
    try {
      const result = await operation();
      if (!alive || token !== epoch) return;
      if (!result.ok) { status(result.error?.message || '操作失败', 'danger'); return; }
      success(result.data);
    } catch { if (alive && token === epoch) status('请求失败，请检查 OMRS 与网关连接；账号状态未被判定为过期。', 'danger'); }
    finally {
      busy = false;
      if (alive) { root.querySelectorAll('#st-sec-zuoyebang input, #st-sec-zuoyebang select, #st-sec-zuoyebang button').forEach(el => { el.disabled = false; }); modeHint(); }
    }
  }
  const changed = () => { epoch++; modeHint(); };
  const load = () => run(() => get('/api/zuoyebang/service'), data => { apply(data.service); status('已读取保存的服务配置'); });
  const save = () => {
    const payload = { mode: field('mode').value, base_url: field('base').value.trim(), allow_private_targets: field('private').checked };
    if (field('key').value) payload.api_key = field('key').value;
    return run(() => post('/api/zuoyebang/service', payload), data => { apply(data.service); field('account').textContent = '配置已更新；请测试已保存连接。'; status('服务配置已保存', 'success'); bus?.emit('zuoyebang:service-changed', data.service); });
  };
  const test = () => run(() => post('/api/zuoyebang/service/test', {}), data => { status('已连接网关（仅状态查询，未调用上游搜题）', 'success'); field('account').textContent = serviceStatus(data); });
  const clearKey = async () => {
    if (!alive || busy || !await confirm('清除作业帮网关 API Key？连接与搜题将不可用；不会删除网关账号。', { title: '清除网关 Key', danger: true })) return;
    return run(() => post('/api/zuoyebang/service', { clear_api_key: true }), data => { apply(data.service); status('网关 Key 已清除', 'success'); bus?.emit('zuoyebang:service-changed', data.service); });
  };
  return { load, save, test, clearKey, changed, modeChanged: changed, dispose() { alive = false; epoch++; field('key').value = ''; } };
}
