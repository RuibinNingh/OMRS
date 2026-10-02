import { configSavedStatus } from '../../core/config-status.js';
/** AI 助手配置：agent_* 键；密钥只提交、不回显；预算只能调小（服务端再夹一次）。保存后经 bus 通知侧栏入口刷新。 */
import { get, post } from '../../core/api.js';
import { confirm } from '../../ui/dialog.js';

const LIMITS = { rounds: 25, calls: 40, writes: 20 };
const MAX_OUTPUT_TOKENS_DEFAULT = 10240;
const MAX_OUTPUT_TOKENS_LIMIT = 65536;

export function createAgent(root, bus) {
  const el = id => root.querySelector(`#${id}`);
  const value = id => String(el(id)?.value || '').trim();
  let alive = true;
  let busy = false;
  let faux = false;
  const status = (text, tone = '') => {
    const target = el('st-agent-status');
    if (target) { target.textContent = text; target.dataset.tone = tone; }
  };

  async function load() {
    const [cfgRes, stRes] = await Promise.all([get('/api/config'), get('/api/agent/status')]);
    if (!alive) return;
    if (!cfgRes.ok) { status(`无法读取助手配置：${cfgRes.error?.message || '未知错误'}`, 'danger'); return; }
    const cfg = cfgRes.data || {};
    if (el('st-agent-enabled')) el('st-agent-enabled').checked = !!cfg.agent_enabled;
    if (el('st-agent-vision')) el('st-agent-vision').checked = !!cfg.agent_vision;
    if (el('st-draft-mode')) el('st-draft-mode').value = cfg.draft_mode || 'silent';
    if (el('st-draft-crop-mode')) el('st-draft-crop-mode').value = cfg.draft_crop_mode || 'ask';
    if (el('st-draft-train-default')) el('st-draft-train-default').checked = !!cfg.draft_train_default;
    if (el('st-draft-force-crop')) el('st-draft-force-crop').checked = !!cfg.draft_force_crop;
    if (el('st-agent-base')) el('st-agent-base').value = cfg.agent_base_url || '';
    if (el('st-agent-model')) el('st-agent-model').value = cfg.agent_model || '';
    if (el('st-agent-compat')) el('st-agent-compat').value = cfg.agent_compat || 'custom';
    if (el('st-agent-max-output-tokens')) el('st-agent-max-output-tokens').value = cfg.agent_max_output_tokens ?? MAX_OUTPUT_TOKENS_DEFAULT;
    if (el('st-agent-debug')) el('st-agent-debug').checked = !!cfg.agent_debug_log;
    const lim = cfg.agent_limits || {};
    for (const key of Object.keys(LIMITS)) if (el(`st-agent-${key}`)) el(`st-agent-${key}`).value = lim[key] ?? '';
    if (el('st-agent-key')) { el('st-agent-key').value = ''; el('st-agent-key').type = 'password'; }
    if (el('st-agent-key-toggle')) el('st-agent-key-toggle').textContent = '显示';
    if (el('st-agent-key-state')) el('st-agent-key-state').textContent = cfg.agent_api_key_configured
      ? '已配置助手专用密钥（不会回显）' : cfg.ai_api_key_configured ? '未单独配置，沿用「AI 识别」的密钥' : '尚未配置密钥';
    faux = !!stRes.data?.faux;
    if (el('st-agent-faux')) el('st-agent-faux').hidden = !faux;
  }

  function payload() {
    const limits = {};
    for (const [key, max] of Object.entries(LIMITS)) {
      const n = Number.parseInt(value(`st-agent-${key}`), 10);
      if (Number.isFinite(n)) limits[key] = Math.max(1, Math.min(max, n));
    }
    const out = { agent_enabled: !!el('st-agent-enabled')?.checked, agent_vision: !!el('st-agent-vision')?.checked, agent_base_url: value('st-agent-base'), agent_model: value('st-agent-model'),
      agent_compat: value('st-agent-compat') || 'custom', agent_debug_log: !!el('st-agent-debug')?.checked,
      agent_max_output_tokens: Number(value('st-agent-max-output-tokens') || MAX_OUTPUT_TOKENS_DEFAULT),
      draft_mode: value('st-draft-mode') || 'silent', draft_crop_mode: value('st-draft-crop-mode') || 'ask',
      draft_train_default: !!el('st-draft-train-default')?.checked,
      draft_force_crop: !!el('st-draft-force-crop')?.checked, agent_limits: limits };
    const key = value('st-agent-key');
    if (key) out.agent_api_key = key;
    return out;
  }

  async function save({ quiet = false } = {}) {
    if (busy) return false;
    const maxOutputRaw = value('st-agent-max-output-tokens');
    if (maxOutputRaw && (!/^\d+$/.test(maxOutputRaw) || Number(maxOutputRaw) < 1 || Number(maxOutputRaw) > MAX_OUTPUT_TOKENS_LIMIT)) {
      status(`最大输出 Token 必须是 1–${MAX_OUTPUT_TOKENS_LIMIT} 的整数`, 'danger');
      el('st-agent-max-output-tokens')?.focus();
      return false;
    }
    const data = payload();
    if (data.agent_enabled && !data.agent_model && !faux) { status('启用助手需要填写模型名', 'danger'); el('st-agent-model')?.focus(); return false; }
    busy = true;
    status('正在保存助手配置…', 'busy');
    const result = await post('/api/config', data);
    busy = false;
    if (!alive) return false;
    if (!result.ok) { status(`保存失败：${result.error?.message || '未知错误'}`, 'danger'); return false; }
    await load();
    bus?.emit?.('agent:config');
    const saved = configSavedStatus(result.data, '助手配置已保存（立即生效，无需重启）');
    if (!quiet || result.data?.mirror_pending) status(saved.text, saved.tone);
    return true;
  }

  async function test() {
    if (!await save({ quiet: true })) return;
    busy = true;
    status('正在向模型发送测试请求…', 'busy');
    const result = await post('/api/agent/test', {}, { timeout: 130000 });
    busy = false;
    if (!alive) return;
    if (!result.ok) { status(`连接失败：${result.error?.message || '未知错误'}`, 'danger'); return; }
    const r = result.data;
    const vision = r.vision_ok === true ? '图片直传正常' : r.vision_ok === false ? `图片直传失败${r.vision_error ? `：${r.vision_error}` : ''}` : '未测试图片直传';
    status(`连接正常：${r.model}，${r.ms} ms，${r.tools ? '支持工具调用' : '模型没有按要求调用工具，助手可能无法工作'}，${vision}`, r.tools && r.vision_ok !== false ? 'success' : 'danger');
  }

  function toggleKey() {
    const input = el('st-agent-key');
    if (!input) return;
    const showing = input.type === 'password';
    input.type = showing ? 'text' : 'password';
    if (el('st-agent-key-toggle')) el('st-agent-key-toggle').textContent = showing ? '隐藏' : '显示';
  }

  async function clearKey() {
    if (busy || !await confirm('清除助手专用密钥？清除后沿用「AI 识别」的密钥。', { okText: '清除', danger: true })) return;
    const result = await post('/api/config', { clear_agent_api_key: true });
    if (!alive) return;
    if (!result.ok) { status(`清除失败：${result.error?.message || '未知错误'}`, 'danger'); return; }
    await load();
    const saved = configSavedStatus(result.data, '助手密钥已清除');
    status(saved.text, saved.tone);
  }

  return { load, save, test, toggleKey, clearKey, dispose() { alive = false; } };
}
