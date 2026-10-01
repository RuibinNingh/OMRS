/** MCP Key 管理：只调用受 Web 会话保护的管理端点，不在浏览器持久化完整密钥。 */
import { get, post } from '../../core/api.js';
import { html, each } from '../../core/html.js';
import { morph } from '../../core/dom.js';
import { confirm } from '../../ui/dialog.js';
import { copyText } from '../../domain/sessions.js';

const scopeLabel = scope => scope === 'omrs:read' ? '查询' : scope === 'draft:create' ? '建草稿' : scope;
const dateLabel = value => value ? String(value).replace('T', ' ').replace('+00:00', ' UTC') : '—';

function listView(keys) {
  if (!keys.length) return html`<p class="hint">还没有 MCP Key。创建后在这里查看状态。</p>`;
  return html`${each(keys, key => key.key_id, key => html`<div class="st-mcp-key" data-key="${key.key_id}">
    <div class="st-mcp-key-main"><strong>${key.name || key.key_id}</strong><code>${key.prefix || 'omrs_mcp_…'}</code><span class="hint">${key.key_id}</span></div>
    <div class="st-mcp-key-meta"><span>${(key.scopes || []).map(scopeLabel).join('、') || '无权限'}</span><span>创建于 ${dateLabel(key.created_at)}</span>${key.expires_at ? html`<span>到期 ${dateLabel(key.expires_at)}</span>` : html`<span>不过期</span>`}${key.last_used_at ? html`<span>最近使用 ${dateLabel(key.last_used_at)}</span>` : html`<span>尚未使用</span>`}</div>
    <div class="st-mcp-key-actions">${key.revoked_at ? html`<span class="opt-pill no">已吊销 · ${dateLabel(key.revoked_at)}</span>` : html`<button class="ui-btn ui-btn--danger ui-btn--sm" type="button" data-action="settings.mcpRevoke" data-arg="${key.key_id}">吊销</button>`}</div>
  </div>`)}`;
}

function toExpiry(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toISOString();
}

export function createMcpKeys(root) {
  const el = id => root.querySelector(`#${id}`);
  let alive = true;
  let busy = false;
  let secret = '';

  const note = (id, text, tone = '') => {
    const target = el(id);
    if (target && alive) { target.textContent = text; target.dataset.tone = tone; }
  };

  function render(keys) {
    const host = el('st-mcp-keys-list');
    if (host && alive) morph(host, listView(Array.isArray(keys) ? keys : []));
  }

  function clearSecret() {
    secret = '';
    const box = el('st-mcp-secret');
    if (box) box.hidden = true;
    const input = el('st-mcp-secret-value');
    if (input) input.value = '';
    note('st-mcp-secret-status', '');
  }

  async function load() {
    const result = await get('/api/mcp/keys');
    if (!alive) return result;
    if (!result.ok) { note('st-mcp-status', `无法读取 MCP Key：${result.error?.message || '未知错误'}`, 'danger'); return result; }
    render(result.data?.keys || []);
    note('st-mcp-status', '');
    return result;
  }

  async function create() {
    if (busy) return false;
    const scopes = [];
    if (el('st-mcp-scope-read')?.checked) scopes.push('omrs:read');
    if (el('st-mcp-scope-draft')?.checked) scopes.push('draft:create');
    if (!scopes.length) { note('st-mcp-status', '至少选择一项权限。', 'danger'); return false; }
    const name = String(el('st-mcp-name')?.value || '').trim();
    const expires = toExpiry(el('st-mcp-expires')?.value || '');
    if (el('st-mcp-expires')?.value && !expires) { note('st-mcp-status', '到期时间格式不合法。', 'danger'); return false; }
    busy = true;
    note('st-mcp-status', '正在创建 MCP Key…', 'busy');
    const result = await post('/api/mcp/keys', { name, scopes, expires_at: expires || null });
    busy = false;
    if (!alive) return false;
    if (!result.ok) { note('st-mcp-status', `创建失败：${result.error?.message || '未知错误'}`, 'danger'); return false; }
    secret = String(result.data?.key?.secret || '');
    const input = el('st-mcp-secret-value');
    if (input) input.value = secret;
    const box = el('st-mcp-secret');
    if (box) box.hidden = !secret;
    if (el('st-mcp-name')) el('st-mcp-name').value = '';
    if (el('st-mcp-expires')) el('st-mcp-expires').value = '';
    await load();
    note('st-mcp-status', secret ? 'MCP Key 已创建。完整密钥只显示这一次。' : 'MCP Key 已创建，但服务没有返回明文。', secret ? 'success' : 'warning');
    return true;
  }

  async function revoke(keyId) {
    if (busy || !keyId) return false;
    if (!await confirm('吊销这个 MCP Key？', { hint: '吊销会立即终止使用它的 MCP 请求，已有草稿和题库数据不受影响。', okText: '吊销', danger: true })) return false;
    busy = true;
    note('st-mcp-status', '正在吊销…', 'busy');
    const result = await post('/api/mcp/keys/revoke', { key_id: keyId });
    busy = false;
    if (!alive) return false;
    if (!result.ok) { note('st-mcp-status', `吊销失败：${result.error?.message || '未知错误'}`, 'danger'); return false; }
    await load();
    note('st-mcp-status', 'MCP Key 已吊销。', 'success');
    return true;
  }

  async function copy() {
    if (!secret) return false;
    const ok = await copyText(secret);
    note('st-mcp-secret-status', ok ? '已复制到剪贴板。' : '复制失败，请手动选择并复制密钥。', ok ? 'success' : 'danger');
    return ok;
  }

  return { load, create, revoke, copy, clearSecret, dispose() { clearSecret(); alive = false; busy = false; } };
}
