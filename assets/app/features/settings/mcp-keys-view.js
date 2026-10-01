/** 设置页 MCP Key 管理结构。完整密钥只在创建成功后由控制器临时显示。 */
import { html } from '../../core/html.js';

export const mcpKeysView = () => html`<div class="card st-card st-mcp-card">
  <div class="card-title">外部 AI / MCP</div>
  <p class="hint st-lead">MCP Key 只允许固定的 OMRS 查询工具，以及创建待审核草稿。它独立于 Web PIN 和 AI 模型密钥；完整密钥只在创建成功时显示一次。</p>
  <div class="st-mcp-create">
    <div class="st-fields">
      <div class="form-group">
        <label for="st-mcp-name">密钥名称</label>
        <input id="st-mcp-name" class="ui-input" maxlength="80" placeholder="例如 ChatGPT 家庭电脑">
      </div>
      <div class="form-group">
        <label for="st-mcp-expires">到期时间（可选）</label>
        <input id="st-mcp-expires" class="ui-input" type="datetime-local">
        <div class="hint">留空表示不过期；到期或吊销后，正在使用的 Key 也会立即失效。</div>
      </div>
    </div>
    <fieldset class="st-mcp-scopes">
      <legend>权限</legend>
      <label><input id="st-mcp-scope-read" type="checkbox" checked> 查询 OMRS 学习数据</label>
      <label><input id="st-mcp-scope-draft" type="checkbox" checked> 创建待审核草稿</label>
    </fieldset>
    <div class="st-actions">
      <button class="ui-btn ui-btn--primary" type="button" data-action="settings.mcpCreate">创建 MCP Key</button>
      <button class="ui-btn" type="button" data-action="settings.mcpRefresh">刷新列表</button>
    </div>
  </div>
  <div id="st-mcp-secret" class="st-mcp-secret" hidden>
    <strong>请立即复制完整密钥</strong>
    <p class="hint">关闭此页面或刷新后无法再次查看。OMRS 不保存明文。</p>
    <div class="st-inline">
      <input id="st-mcp-secret-value" class="ui-input" type="text" readonly autocomplete="off" spellcheck="false">
      <button class="ui-btn ui-btn--sm" type="button" data-action="settings.mcpCopy">复制密钥</button>
      <button class="ui-btn ui-btn--sm" type="button" data-action="settings.mcpHide">隐藏</button>
    </div>
    <div id="st-mcp-secret-status" class="st-status" role="status"></div>
  </div>
  <div id="st-mcp-status" class="st-status" role="status"></div>
  <div class="st-mcp-list-head"><h3>已创建的 Key</h3><span class="hint">列表只显示元数据和短前缀</span></div>
  <div id="st-mcp-keys-list" class="st-mcp-list" aria-live="polite"><p class="hint">正在读取…</p></div>
</div>`;
