/** MCP 管理：只调用 Web 管理端点；一次性明文随窗口和页面生命周期清空。 */
import { get, post } from '../../core/api.js';
import { html } from '../../core/html.js';
import { morph } from '../../core/dom.js';
import { dialog, closeDialog } from '../../ui/dialog.js';
import { copyText } from '../../domain/sessions.js';
import { mcpCreateView, mcpSecretView, mcpListView } from './mcp-keys-view.js';
import { keyStatus, splitKeys } from './mcp-keys-state.js';

export function createMcpKeys(root) {
  const el = id => modal?.querySelector(`#${id}`) || root.querySelector(`#${id}`);
  let alive = true, busy = false, modal = null, secret = '';
  let keys = [], loadSeq = 0, expiryTimer = null;

  function note(id, text, tone = '') {
    const target = el(id);
    if (target && alive) {
      target.textContent = text;
      target.dataset.tone = tone;
      target.setAttribute('role', tone === 'danger' ? 'alert' : 'status');
    }
  }

  function render() {
    const host = el('st-mcp-keys-list');
    if (!host || !alive) return;
    const now = Date.now();
    const historyOpen = !!host.querySelector('#st-mcp-history')?.open;
    const openKeys = new Set([...host.querySelectorAll('details[open][data-key-details]')].map(node => node.dataset.keyDetails));
    morph(host, mcpListView(keys, { now, historyOpen, openKeys }));
    el('st-mcp-count').textContent = `${splitKeys(keys, now).active.length} 个可用`;
    clearTimeout(expiryTimer);
    const future = keys.filter(key => !key.revoked_at).map(key => Date.parse(key.expires_at)).filter(time => time > now);
    if (future.length) expiryTimer = setTimeout(render, Math.min(60000, Math.min(...future) - now + 1));
  }

  async function load() {
    const seq = ++loadSeq;
    const result = await get('/api/mcp/keys');
    if (!alive || seq !== loadSeq) return result;
    if (!result.ok) { note('st-mcp-status', `无法读取密钥：${result.error?.message || '未知错误'}`, 'danger'); return result; }
    keys = Array.isArray(result.data?.keys) ? result.data.keys : [];
    render();
    note('st-mcp-status', '');
    return result;
  }

  function clearSecret() {
    secret = '';
    const input = el('st-mcp-secret-value');
    if (input) { input.value = ''; input.removeAttribute('value'); }
    note('st-mcp-secret-status', '');
  }

  function rememberKey({ secret: _secret, ...metadata }) {
    if (!metadata.key_id) return;
    keys = keys.some(key => key.key_id === metadata.key_id)
      ? keys.map(key => key.key_id === metadata.key_id ? metadata : key) : [...keys, metadata];
    render();
  }

  function lockWindow(locked) {
    modal?.querySelectorAll('[data-dialog-cancel], input, select').forEach(node => { node.disabled = locked; });
  }

  async function create() {
    if (!alive || busy || modal) return false;
    let created = false;
    const result = await dialog({
      id: 'st-mcp-dialog', title: '创建 MCP 密钥', size: 'md', okText: '创建密钥',
      hint: '为每个外部 AI 分别创建，方便识别与管理。', body: mcpCreateView(), focus: '#st-mcp-name',
      dismissible: () => !busy,
      onOpen(window) {
        modal = window;
        window.addEventListener('change', event => {
          if (event.target.id === 'st-mcp-expiry-kind') {
            const custom = event.target.value === 'custom';
            el('st-mcp-expires').hidden = !custom;
            el('st-mcp-expires').required = custom;
          }
          note('st-mcp-create-status', '');
        });
      },
      async onOk(values, window) {
        if (!alive) return true;
        if (created) return true;
        const scopes = [];
        if (values['st-mcp-scope-read']) scopes.push('omrs:read');
        if (values['st-mcp-scope-draft']) scopes.push('draft:create');
        if (!scopes.length) { note('st-mcp-create-status', '至少选择一项权限。', 'danger'); return false; }
        const custom = values['st-mcp-expiry-kind'] === 'custom';
        const input = el('st-mcp-expires');
        if (custom && !input.reportValidity()) return false;
        const expiry = custom ? new Date(values['st-mcp-expires']) : null;
        if (expiry && (!Number.isFinite(expiry.getTime()) || expiry.getTime() <= Date.now())) {
          note('st-mcp-create-status', '到期时间必须晚于当前时间。', 'danger'); return false;
        }
        busy = true;
        lockWindow(true);
        note('st-mcp-create-status', '正在创建密钥…');
        const response = await post('/api/mcp/keys', { name: String(values['st-mcp-name'] || '').trim(), scopes, expires_at: expiry?.toISOString() || null });
        busy = false;
        lockWindow(false);
        if (!alive) return true;
        if (!response.ok) { note('st-mcp-create-status', `创建失败：${response.error?.message || '未知错误'}`, 'danger'); return false; }
        created = true;
        rememberKey(response.data?.key || {});
        secret = String(response.data?.key?.secret || '');
        if (!secret) {
          await load();
          note('st-mcp-status', '密钥已创建，但服务没有返回明文。', 'warning');
          return true;
        }
        window.querySelector('.ui-dialog__title').textContent = '密钥已创建';
        window.querySelector('.ui-dialog__hint').textContent = response.data?.key?.name || '请立即保存完整密钥。';
        morph(window.querySelector('.ui-dialog__body'), mcpSecretView(secret));
        window.querySelector('.ui-dialog__foot [data-dialog-cancel]').hidden = true;
        window.querySelector('[data-dialog-ok]').textContent = '我已保存，完成';
        el('st-mcp-secret-value').focus();
        el('st-mcp-secret-value').select();
        await load();
        return false;
      },
    });
    clearSecret();
    modal = null;
    return created && result.ok;
  }

  async function revoke(keyId) {
    if (!alive || busy || modal || !keyId) return false;
    const key = keys.find(item => item.key_id === keyId);
    if (!key || keyStatus(key) !== 'active') return false;
    const result = await dialog({
      id: 'st-mcp-revoke-dialog', title: '吊销这枚密钥？', hint: '吊销后无法恢复。', danger: true, okText: '确认吊销', cancelText: '保留密钥',
      body: html`<div class="st-mcp-revoke-name">${key.name || key.key_id}</div><p>使用它的 MCP 请求会立即失效。已经创建的草稿和题库数据会保留。</p><div id="st-mcp-revoke-status" class="st-status" role="alert"></div>`,
      dismissible: () => !busy,
      onOpen(window) { modal = window; },
      async onOk() {
        if (!alive) return true;
        busy = true;
        lockWindow(true);
        const response = await post('/api/mcp/keys/revoke', { key_id: keyId });
        busy = false;
        lockWindow(false);
        if (!alive) return true;
        if (!response.ok) { note('st-mcp-revoke-status', `吊销失败：${response.error?.message || '未知错误'}`, 'danger'); return false; }
        rememberKey(response.data?.key || {});
        const refreshed = await load();
        if (refreshed.ok) note('st-mcp-status', '密钥已吊销。', 'success');
        return true;
      },
    });
    modal = null;
    return result.ok;
  }

  async function copy() {
    if (!alive || !secret) return false;
    const copySecret = secret, copyWindow = modal;
    const ok = await copyText(copySecret);
    if (!alive || secret !== copySecret || modal !== copyWindow) return false;
    note('st-mcp-secret-status', ok ? '已复制到剪贴板。' : '复制失败，请手动选择并复制密钥。', ok ? 'success' : 'danger');
    return ok;
  }

  return { load, create, revoke, copy, clearSecret, dispose() {
    clearSecret();
    alive = false;
    ++loadSeq;
    clearTimeout(expiryTimer);
    lockWindow(false);
    closeDialog(modal);
    modal = null;
  } };
}
