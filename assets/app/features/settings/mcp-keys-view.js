/** MCP 密钥：能力说明、管理列表与创建窗口。只显示服务端返回的元数据。 */
import { html, each } from '../../core/html.js';
import { icon } from '../../ui/icon.js';
import { keyStatus, keyTime, splitKeys } from './mcp-keys-state.js';

export const mcpKeysView = () => html`<section class="st-mcp-card" aria-label="外部 AI / MCP">
  <div class="card st-card st-mcp-intro">
    <div class="st-mcp-intro-head">
      <div class="st-mcp-heading"><span class="st-mcp-symbol">${icon('link')}</span><h3>外部 AI / MCP</h3></div>
      <button class="ui-btn ui-btn--primary ui-btn--lg" type="button" data-action="settings.mcpCreate">${icon('plus')}创建密钥</button>
    </div>
    <p class="st-mcp-lead">让外部 AI 查询你的学习数据，或为你准备待审核草稿。</p>
    <div class="st-mcp-capabilities">
      <div>${icon('book')}<div><strong>查询学习数据</strong><p>题目、练习记录与复习建议</p></div></div>
      <div>${icon('edit')}<div><strong>创建待审核草稿</strong><p>由你审核后，再进入正式题库</p></div></div>
    </div>
    <div class="st-mcp-boundary">${icon('lock')}<span>MCP 密钥独立于 Web PIN 和模型 API Key，不授予题库修改权限。</span></div>
  </div>
  <div class="card st-card st-mcp-manager">
    <div class="st-mcp-list-head"><div><h3>密钥管理</h3><span class="st-mcp-count" id="st-mcp-count">—</span></div>
      <button class="ui-btn ui-btn--ghost" type="button" data-action="settings.mcpRefresh">${icon('refresh')}刷新</button>
    </div>
    <div id="st-mcp-status" class="st-status" role="status"></div>
    <div id="st-mcp-keys-list" aria-live="polite"><p class="hint st-mcp-loading">正在读取密钥…</p></div>
  </div>
  <div class="st-mcp-footer">${icon('lock')}<span>完整密钥仅在创建时显示一次</span><span>时间按设备本地时区显示</span></div>
</section>`;

export const mcpCreateView = () => html`<div class="st-mcp-form">
  <div class="form-group"><label class="st-mcp-field-label" for="st-mcp-name">密钥名称<span>可选</span></label>
    <input id="st-mcp-name" class="ui-input ui-input--lg" maxlength="80" autocomplete="off" placeholder="例如 ChatGPT · 家庭电脑"></div>
  <div class="form-group"><label for="st-mcp-expiry-kind">到期时间</label>
    <select id="st-mcp-expiry-kind" class="ui-select ui-select--lg"><option value="never">永不过期</option><option value="custom">指定到期时间</option></select>
    <input id="st-mcp-expires" class="ui-input ui-input--lg" type="datetime-local" aria-label="指定到期日期与时间" hidden>
    <p class="hint">到期或吊销后，正在使用的密钥也会立即失效。</p>
  </div>
  <fieldset class="st-mcp-scopes"><legend>授予的权限<span>至少选择一项</span></legend>
    <label>${icon('book')}<span><strong>查询学习数据</strong><small>查看题目、练习记录与复习建议</small></span><input id="st-mcp-scope-read" type="checkbox" checked></label>
    <label>${icon('edit')}<span><strong>创建待审核草稿</strong><small>发送到草稿区，由你审核后入库</small></span><input id="st-mcp-scope-draft" type="checkbox" checked></label>
  </fieldset>
  <p class="st-mcp-form-note">${icon('lock')}<span>创建后请立即复制完整密钥，关闭后将无法再次查看。</span></p>
  <div id="st-mcp-create-status" class="st-status" role="alert"></div>
</div>`;

export const mcpSecretView = secret => html`<div id="st-mcp-secret">
  <div class="st-mcp-secret-note">${icon('alert-triangle')}<div><strong>请保存这一次显示的完整密钥</strong><p>OMRS 不保存密钥明文。关闭此窗口后，将无法再次查看。</p></div></div>
  <label class="st-mcp-secret-label" for="st-mcp-secret-value">完整密钥</label>
  <input id="st-mcp-secret-value" class="ui-input ui-input--lg" type="text" value="${secret}" readonly autocomplete="off" spellcheck="false">
  <div class="st-mcp-copy-row"><div id="st-mcp-secret-status" class="st-status" role="status"></div>
    <button class="ui-btn" type="button" data-action="settings.mcpCopy">${icon('copy')}复制密钥</button></div>
</div>`;

const scopeLabel = scope => ({ 'omrs:read': '查询', 'draft:create': '创建草稿' })[scope] || scope;
const statusLabel = status => ({ active: '有效', revoked: '已吊销', expired: '已到期' })[status];

function detailsView(key, openKeys) {
  return html`<details class="ui-disclosure st-mcp-details" data-key-details="${key.key_id}" ${openKeys.has(key.key_id) ? html`open` : ''}>
    <summary>密钥详情</summary><dl class="st-mcp-details-grid">
      <dt>密钥 ID</dt><dd><code>${key.key_id}</code></dd><dt>短前缀</dt><dd><code>${key.prefix || '—'}</code></dd>
      <dt>创建时间</dt><dd>${keyTime(key.created_at)}</dd><dt>最近使用</dt><dd>${key.last_used_at ? keyTime(key.last_used_at) : '尚未使用'}</dd>
      <dt>到期时间</dt><dd>${key.expires_at ? keyTime(key.expires_at) : '永不过期'}</dd>
      ${key.revoked_at ? html`<dt>吊销时间</dt><dd>${keyTime(key.revoked_at)}</dd>` : ''}
    </dl>
  </details>`;
}

function keyView(key, now, openKeys) {
  const status = keyStatus(key, now);
  const active = status === 'active';
  return html`<article class="st-mcp-key${active ? '' : ' st-mcp-key-inactive'}" data-key="${key.key_id}">
    <div class="st-mcp-key-top"><div class="st-mcp-key-main"><div class="st-mcp-key-name"><strong>${key.name || key.key_id}</strong><span class="st-mcp-badge" data-state="${status}">${statusLabel(status)}</span></div>
      ${active ? html`<code>${key.prefix || 'omrs_mcp_…'}</code>` : ''}</div>
      ${active ? html`<button class="ui-btn ui-btn--ghost st-mcp-revoke" type="button" data-action="settings.mcpRevoke" data-arg="${key.key_id}" aria-label="吊销 ${key.name || key.key_id} 密钥">吊销</button>` : ''}
    </div>
    ${active ? html`<dl class="st-mcp-key-meta"><div><dt>权限</dt><dd class="st-mcp-scope-list">${(key.scopes || []).length ? each(key.scopes, scope => scope, scope => html`<span class="st-mcp-scope">${icon(scope === 'draft:create' ? 'edit' : 'book')}${scopeLabel(scope)}</span>`) : '无权限'}</dd></div>
      <div><dt>最近使用</dt><dd>${key.last_used_at ? keyTime(key.last_used_at, true, now) : '尚未使用'}</dd></div><div><dt>到期时间</dt><dd>${key.expires_at ? keyTime(key.expires_at, true, now) : '永不过期'}</dd></div></dl>`
      : html`<p class="st-mcp-inactive-meta">${(key.scopes || []).map(scopeLabel).join('、') || '无权限'} · ${keyTime(key.revoked_at || key.expires_at)} ${status === 'revoked' ? '吊销' : '到期'}</p>`}
    ${detailsView(key, openKeys)}
  </article>`;
}

export function mcpListView(keys, { now = Date.now(), historyOpen = false, openKeys = new Set() } = {}) {
  const { active, inactive } = splitKeys(keys, now);
  return html`<div class="st-mcp-active">${active.length ? each(active, key => key.key_id, key => keyView(key, now, openKeys)) : html`<div class="st-mcp-empty"><p>还没有可用的 MCP 密钥</p><button class="ui-btn" type="button" data-action="settings.mcpCreate">${icon('plus')}创建密钥</button></div>`}</div>
    ${inactive.length ? html`<details class="ui-disclosure st-mcp-history" id="st-mcp-history" ${historyOpen ? html`open` : ''}><summary><span>已失效的密钥</span><span class="st-mcp-count">${inactive.length}</span><span class="st-mcp-history-hint">保留记录，便于核对</span></summary>
      <div>${each(inactive, key => key.key_id, key => keyView(key, now, openKeys))}</div></details>` : ''}`;
}
