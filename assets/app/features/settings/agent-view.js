/** 设置页「assistant」分区：AI 助手的开关、模型接口、兼容配置、预算与调试日志。字段语义见 AI/agent.md「配置」。 */
import { html } from '../../core/html.js';

const limit = (id, label, max, hint) => html`<div class="form-group"><label for="${id}">${label}</label>
  <input id="${id}" class="ui-input" type="number" min="1" max="${max}" step="1" placeholder="${max}"><div class="hint">${hint}，上限 ${max}</div></div>`;

export const agentView = () => html`<section class="st-section" id="st-sec-assistant" role="tabpanel" aria-labelledby="st-tab-assistant">
  <header class="st-head"><h2>AI 助手</h2><p>侧栏「AI 助手」用的对话模型，需要支持工具调用（function calling）。助手能读写题库：只读与可撤销的操作直接执行，改正文、记反馈、录新题要你在界面上点「允许」。</p></header>
  <div class="card st-card">
    <div class="st-row st-row-top">
      <div class="st-row-text"><label class="st-row-label" for="st-agent-enabled">启用 AI 助手</label>
        <div class="hint">关闭时侧栏不显示入口，所有对话接口返回「未启用」。已有对话保留在 <code>错题/.omrs/agent.db</code>，随备份导出。</div></div>
      <input type="checkbox" class="st-switch" id="st-agent-enabled">
    </div>
    <div class="hint" id="st-agent-faux" hidden>当前进程由环境变量 <code>OMRS_AGENT_FAUX_SCRIPT</code> 指定了假模型（用于测试），下面的接口设置暂不生效。</div>
  </div>
  <div class="card st-card">
    <div class="card-title">接口</div>
    <div class="st-fields">
      <div class="form-group"><label for="st-agent-base">API 地址</label>
        <input id="st-agent-base" class="ui-input" placeholder="留空则沿用「AI 识别」的地址">
        <div class="hint">OpenAI 兼容接口，填到 <code>/v1</code> 即可。</div></div>
      <div class="form-group"><label for="st-agent-key">API Key</label>
        <div class="st-inline"><input id="st-agent-key" class="ui-input" type="password" autocomplete="off" placeholder="留空则沿用「AI 识别」的密钥">
          <button class="ui-btn ui-btn--sm" type="button" data-action="settings.agentToggleKey" id="st-agent-key-toggle">显示</button>
          <button class="ui-btn ui-btn--sm" type="button" data-action="settings.agentClearKey">清除</button></div>
        <div class="hint" id="st-agent-key-state"></div></div>
      <div class="st-grid3">
        <div class="form-group"><label for="st-agent-model">模型</label>
          <input id="st-agent-model" class="ui-input" placeholder="qwen-plus" list="st-agent-model-list">
          <datalist id="st-agent-model-list"><option value="qwen-plus"><option value="qwen3-max"><option value="deepseek-chat"><option value="gpt-4.1"><option value="gpt-4o-mini"></datalist>
          <div class="hint">必填，不沿用「AI 识别」的视觉模型</div></div>
        <div class="form-group"><label for="st-agent-compat">厂商兼容</label>
          <select id="st-agent-compat" class="ui-select"><option value="custom">通用</option><option value="openai">OpenAI</option><option value="dashscope">阿里云百炼</option><option value="deepseek">DeepSeek</option></select>
          <div class="hint">决定思考内容字段、max_tokens 字段名、上下文窗口</div></div>
      </div>
    </div>
  </div>
  <div class="card st-card">
    <div class="card-title">每次运行的预算</div>
    <div class="hint">只能调小，不能调大；超出即结束这次运行并说明原因。留空用默认值。</div>
    <div class="st-grid3">${limit('st-agent-rounds', '模型请求轮数', 25, '一次提问里最多请求模型几轮')}${limit('st-agent-calls', '工具调用', 40, '含只读')}${limit('st-agent-writes', '写入', 20, '可撤销与需确认的合计')}</div>
    <div class="st-row st-row-top">
      <div class="st-row-text"><label class="st-row-label" for="st-agent-debug">记录模型请求日志</label>
        <div class="hint">把每次请求与响应原文（不含密钥）写到 <code>错题/.omrs/logs/agent-llm.jsonl</code>，排查兼容问题时再开；日志含题目内容。</div></div>
      <input type="checkbox" class="st-switch" id="st-agent-debug">
    </div>
  </div>
  <div class="st-actions st-actions-end">
    <button class="ui-btn" type="button" data-action="settings.agentTest">测试连接</button>
    <button class="ui-btn ui-btn--primary" type="button" data-action="settings.saveAgent">保存助手配置</button>
  </div>
  <div id="st-agent-status" class="st-status" role="status"></div>
</section>`;
