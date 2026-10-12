/** 独立作业帮服务；账户只在独立面板管理。 */
import { html } from '../../core/html.js';

export const zuoyebangView = () => html`<section class="st-section" id="st-sec-zuoyebang" role="tabpanel" aria-labelledby="st-tab-zuoyebang">
  <header class="st-head"><h2>作业帮服务</h2><p>OMRS 通过独立网关搜题。原图、候选、渲染、识别、人工核对和入库仍在 OMRS；账号、签名和审计在独立管理面板操作，不迁移旧会话。</p></header>
  <div class="card st-card"><div class="card-title">连接配置</div><div class="st-fields">
    <div class="form-group"><label for="st-zyb-mode">服务模式</label><select id="st-zyb-mode" class="ui-input" data-change="settings.zybMode"><option value="local">本地独立网关</option><option value="external">外部网关</option></select><div class="hint" id="st-zyb-mode-hint">本地不是 OMRS 内置直连；网关必须在 OMRS 主机的 loopback 上独立运行。</div></div>
    <div class="form-group"><label for="st-zyb-base">网关根地址</label><input id="st-zyb-base" class="ui-input" type="url" placeholder="http://127.0.0.1:8745" autocomplete="off" data-input="settings.zybChanged"><div class="hint">本地默认 127.0.0.1:8745，可用其它 loopback 端口；外部须 HTTPS，显式信任的私网可用 HTTP。不要填写路径、查询、用户名或密码。</div></div>
    <div class="form-group"><label for="st-zyb-key">网关 API Key</label><div class="st-inline"><input id="st-zyb-key" class="ui-input" type="password" autocomplete="off" placeholder="留空保留已保存的 Key" data-input="settings.zybChanged"><button class="ui-btn ui-btn--sm" type="button" data-action="settings.zybClearKey">清除 Key</button></div><div class="hint" id="st-zyb-key-state"></div><div class="hint">保存在本机私有配置文件，服务端转发时使用；不会回显到页面，也不会附在管理面板链接。</div></div>
    <div class="st-row"><div class="st-row-text"><label class="st-row-label" for="st-zyb-private">显式信任外部私网目标</label><div class="hint">只对你信任的私网网关开启；允许私网 HTTP，仍禁止元数据地址、重定向和环境代理。</div></div><input id="st-zyb-private" class="st-switch" type="checkbox" data-change="settings.zybChanged"></div>
  </div></div>
  <div class="st-actions"><button class="ui-btn ui-btn--primary" type="button" data-action="settings.zybSave">保存服务配置</button><button class="ui-btn" type="button" data-action="settings.zybLoad">重新读取</button><button class="ui-btn" type="button" data-action="settings.zybTest">测试已保存连接</button><a id="st-zyb-panel" class="ui-btn" target="_blank" rel="noopener noreferrer" aria-disabled="true">打开独立管理面板</a></div>
  <div id="st-zyb-status" class="st-status" role="status" aria-live="polite"></div><div id="st-zyb-account" class="st-status" role="status">账号与签名尚未查询；连接失败不代表账号过期。</div>
</section>`;
