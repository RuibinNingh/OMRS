/** 设置页「appearance」分区结构。 */
import { html } from '../../core/html.js';

export const appearanceView = () => html`<section class="st-section" id="st-sec-appearance" role="tabpanel" aria-labelledby="st-tab-appearance">
          <header class="st-head"><h2>外观与显示</h2><p>只保存在当前浏览器，切换后立即生效，不影响其他设备。</p></header>
          <div class="card st-card">
            <div class="st-row">
              <div class="st-row-text"><div class="st-row-label">主题</div><div class="hint">首次打开默认深色。题目截图多为浅底，白天可切到浅色阅读。</div></div>
              <div class="theme-switch" id="st-theme-switch">
                <button class="theme-opt" type="button" data-theme="light" data-action="settings.theme" data-arg="light">浅色</button>
                <button class="theme-opt" type="button" data-theme="dark" data-action="settings.theme" data-arg="dark">深色</button>
              </div>
            </div>
            <div class="st-row">
              <div class="st-row-text"><div class="st-row-label">界面密度</div><div class="hint">紧凑档收紧内边距、行高和控件高度。题库、反馈工作台、收件箱处理页始终按紧凑排版，这里只影响全站基准。</div></div>
              <div class="theme-switch" id="st-density-switch">
                <button class="theme-opt" type="button" data-density="comfortable" data-action="settings.density" data-arg="comfortable">舒适</button>
                <button class="theme-opt" type="button" data-density="compact" data-action="settings.density" data-arg="compact">紧凑</button>
              </div>
            </div>
            <div class="st-row">
              <div class="st-row-text"><label class="st-row-label" for="st-invert-img">深色模式下反转题图颜色</label><div class="hint">白底变黑、黑字变白，彩色会一并反相。只在深色模式下生效。</div></div>
              <input type="checkbox" class="st-switch" id="st-invert-img" data-change="settings.invert">
            </div>
            <div class="st-row">
              <div class="st-row-text"><label class="st-row-label" for="st-ledger-time-zone">Ledger 时间线时区</label><div class="hint">账本始终以 UTC 保存；这里只改变「历史记录」与仪表盘「最近动态」的显示。</div></div>
              <select id="st-ledger-time-zone" class="input st-select" data-change="settings.timeZone">
                <option value="local">跟随浏览器</option>
                <option value="Asia/Shanghai">中国标准时间（UTC+8）</option>
                <option value="UTC">UTC（账本原始时区）</option>
                <option value="Asia/Tokyo">日本标准时间（UTC+9）</option>
                <option value="Asia/Singapore">新加坡时间（UTC+8）</option>
                <option value="Europe/London">伦敦时间</option>
                <option value="America/New_York">纽约时间</option>
                <option value="America/Los_Angeles">洛杉矶时间</option>
              </select>
            </div>
          </div>
        </section>`;
