/** 设置页「access」分区结构。 */
import { html } from '../../core/html.js';

export const accessView = () => html`<section class="st-section" id="st-sec-access" role="tabpanel" aria-labelledby="st-tab-access">
          <header class="st-head"><h2>访问与安全</h2><p>决定哪些设备能打开 OMRS，以及远端设备如何登录。</p></header>
          <div class="st-overview" id="st-access-overview" aria-live="polite">
            <p class="st-overview-line" id="st-access-summary">正在读取访问状态…</p>
            <dl class="st-facts">
              <div><dt>当前监听</dt><dd id="st-fact-listen">—</dd></div>
              <div><dt>远端 PIN</dt><dd id="st-fact-pin">—</dd></div>
              <div><dt>免 PIN 网段</dt><dd id="st-fact-cidrs">—</dd></div>
              <div><dt>你的连接</dt><dd id="st-fact-you">—</dd></div>
            </dl>
          </div>

          <div class="card st-card">
            <div class="card-title">远端访问 PIN</div>
            <p class="hint st-lead" id="st-pin-status">读取中…</p>
            <div class="st-fields">
              <div class="form-group" id="st-pin-current-row" hidden>
                <label for="st-pin-current">当前 PIN</label>
                <input id="st-pin-current" class="ui-input" type="password" inputmode="numeric" autocomplete="current-password" maxlength="12">
                <div class="hint">从其他设备修改时须先验证当前 PIN；连续输错 5 次会锁定 15 分钟。</div>
              </div>
              <div class="form-group">
                <label for="st-pin-new" id="st-pin-new-label">新 PIN</label>
                <input id="st-pin-new" class="ui-input" type="password" inputmode="numeric" autocomplete="new-password" maxlength="12" placeholder="4 到 12 位数字">
                <div class="hint" id="st-pin-new-hint">留空则只更新空闲时间。</div>
              </div>
              <div class="form-group">
                <label for="st-pin-idle">空闲多久后需重新登录</label>
                <div class="st-inline"><input id="st-pin-idle" class="ui-input st-num" type="number" min="5" max="240" step="5" value="30"><span class="hint">分钟（5–240）</span></div>
                <div class="hint">登录最长有效 12 小时。只有点击、键盘、触摸、滚轮和滚动会延长空闲时间，后台刷新不算。</div>
              </div>
            </div>
            <div class="st-actions">
              <button class="ui-btn ui-btn--primary" type="button" data-action="settings.savePin">保存 PIN 设置</button>
              <button class="ui-btn" type="button" id="st-pin-logout" data-action="settings.logout" hidden>退出远端登录</button>
              <span class="st-actions-gap"></span>
              <button class="ui-btn ui-btn--danger" type="button" id="st-pin-disable" data-action="settings.disablePin" hidden>停用 PIN</button>
            </div>
            <div id="st-pin-action-status" class="st-status" role="status"></div>
          </div>

          <div class="card st-card">
            <div class="card-title">局域网访问</div>
            <div class="st-row st-row-top">
              <div class="st-row-text">
                <label class="st-row-label" for="st-allow-external">允许同一网络中的其他设备访问</label>
                <div class="hint">开启后服务监听所有网卡，其他设备用本机的局域网 IP 加端口访问（如 192.168.x.x:8471）；本机仍用 127.0.0.1。不要在浏览器里输入 0.0.0.0。开启前须先设置 PIN 或填写免 PIN 网段。</div>
              </div>
              <input type="checkbox" class="st-switch" id="st-allow-external" data-change="settings.networkChanged">
            </div>
            <div class="form-group st-fields">
              <label for="st-lan-pin-exempt-cidrs">免 PIN 网段（可选）</label>
              <input id="st-lan-pin-exempt-cidrs" class="ui-input" type="text" placeholder="例如 192.168.0.0/24，多个用逗号分隔" data-input="settings.networkChanged">
              <div class="hint">只认直连设备的实际 IP，经 Nginx 等代理的访问仍须 PIN。网段内所有设备都能使用全部功能，只填写可信设备所在的网段。留空则所有非本机访问都须 PIN。</div>
            </div>
            <div class="st-actions">
              <button class="ui-btn ui-btn--primary" type="button" id="st-net-save" data-action="settings.saveAccess">保存访问设置</button>
              <span class="hint" id="st-net-hint">改动开关会自动重启服务；只改网段立即生效。</span>
            </div>
            <div id="st-net-status" class="st-status" role="status"></div>
          </div>
        </section>`;
