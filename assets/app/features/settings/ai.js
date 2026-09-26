/** AI 识别配置：密钥只提交、不从后端回显。 */
import { get, post } from '../../core/api.js';
import { confirm } from '../../ui/dialog.js';

export function createAi(root) {
  const el = id => root.querySelector(`#${id}`);
  const value = id => String(el(id)?.value || '').trim();
  let alive = true;
  let busy = false;
  let loadId = 0;
  const status = (text, tone = '') => {
    const target = el('st-ai-settings-status');
    if (target) { target.textContent = text; target.dataset.tone = tone; }
  };

  async function load() {
    const mine = ++loadId;
    const result = await get('/api/config');
    if (!alive || mine !== loadId) return result;
    if (!result.ok) { status(`无法读取 AI 配置：${result.error?.message || '未知错误'}`, 'danger'); return result; }
    const cfg = result.data || {};
    if (el('st-ai-base')) el('st-ai-base').value = cfg.ai_base_url || '';
    if (el('st-ai-key')) {
      el('st-ai-key').value = '';
      el('st-ai-key').placeholder = cfg.ai_api_key_configured ? '已配置；留空表示保留现有密钥' : '输入新密钥';
      el('st-ai-key').type = 'password';
    }
    if (el('st-ai-key-toggle')) el('st-ai-key-toggle').textContent = '显示';
    if (el('st-ai-key-state')) el('st-ai-key-state').textContent = cfg.ai_api_key_configured
      ? '已配置密钥（不会从服务器回显）' : '尚未配置密钥';
    if (el('st-ai-model')) el('st-ai-model').value = cfg.ai_model || '';
    if (el('st-ai-restrict')) el('st-ai-restrict').checked = cfg.ai_restrict_tags !== false;
    for (const kind of ['detect', 'extract', 'classify']) {
      if (el(`st-ai-model-${kind}`)) el(`st-ai-model-${kind}`).value = cfg[`ai_model_${kind}`] || '';
    }
    return result;
  }

  function toggleKey() {
    const input = el('st-ai-key');
    const button = el('st-ai-key-toggle');
    if (!input) return;
    const showing = input.type === 'password';
    input.type = showing ? 'text' : 'password';
    if (button) button.textContent = showing ? '隐藏' : '显示';
  }

  async function save() {
    if (busy) return;
    const payload = {
      ai_base_url: value('st-ai-base'), ai_model: value('st-ai-model'),
      ai_restrict_tags: !!el('st-ai-restrict')?.checked,
      ai_model_detect: value('st-ai-model-detect'),
      ai_model_extract: value('st-ai-model-extract'),
      ai_model_classify: value('st-ai-model-classify'),
    };
    const key = value('st-ai-key');
    if (key) payload.ai_api_key = key;
    busy = true;
    status('正在保存 AI 配置…', 'busy');
    const result = await post('/api/config', payload);
    busy = false;
    if (!alive) return;
    if (!result.ok) { status(`保存失败：${result.error?.message || '未知错误'}`, 'danger'); return; }
    await load();
    status('AI 配置已保存（立即生效，无需重启）', 'success');
  }

  async function clearKey() {
    if (busy || !await confirm('清除已保存的 AI 密钥？', { okText: '清除', danger: true })) return;
    busy = true;
    const result = await post('/api/config', { clear_ai_api_key: true });
    busy = false;
    if (!alive) return;
    if (!result.ok) { status(`清除失败：${result.error?.message || '未知错误'}`, 'danger'); return; }
    await load();
    status('AI 密钥已清除', 'success');
  }

  return { load, save, clearKey, toggleKey, dispose() { alive = false; loadId += 1; } };
}
