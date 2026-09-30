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
              <select id="st-ledger-time-zone" class="ui-select ui-select" data-change="settings.timeZone">
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
          <div class="card st-card st-entry-background-card">
            <div class="card-title">入口背景</div>
            <p class="hint st-lead">只作用于入口锁屏页，工作台页面背景、主题和布局保持不变。当前自定义背景会显示给能够访问入口页的设备。</p>
            <div class="st-entry-background-presets" role="group" aria-label="入口背景预设">
              <button class="st-entry-preset active" type="button" id="st-entry-background-black-hole" data-action="settings.entryBackgroundMode" data-arg="black-hole" aria-pressed="true">
                <span class="st-entry-preset-visual st-entry-hole-thumb" aria-hidden="true"></span><strong>黑洞</strong><small>现有 WebGL 入口视觉</small>
              </button>
              <button class="st-entry-preset" type="button" id="st-entry-background-custom" data-action="settings.entryBackgroundMode" data-arg="custom" aria-pressed="false">
                <span class="st-entry-preset-visual st-entry-custom-thumb" aria-hidden="true"></span><strong>自定义</strong><small>上传图片或视频</small>
              </button>
            </div>
            <div class="st-entry-background-preview" id="st-entry-background-preview" data-mode="black-hole" role="img" aria-label="入口背景实时预览"></div>
            <div class="st-entry-background-controls">
              <div class="form-group">
                <label for="st-entry-background-file">上传图片或视频</label>
                <input id="st-entry-background-file" class="ui-input" type="file" accept="image/png,image/jpeg,image/webp,image/gif,image/avif,image/bmp,video/mp4,video/webm,video/ogg" data-change="settings.entryBackgroundChoose" disabled>
                <div class="hint" id="st-entry-background-file-meta">切换到自定义后可上传媒体</div>
              </div>
              <div class="st-row st-entry-background-row">
                <div class="st-row-text"><label class="st-row-label" for="st-entry-background-style">样式预设</label><div class="hint">首版提供高斯模糊，图片和视频共用。</div></div>
                <select id="st-entry-background-style" class="ui-select st-select" data-change="settings.entryBackgroundStyle">
                  <option value="gaussian-blur">高斯模糊</option>
                </select>
              </div>
              <div class="st-row st-entry-background-row">
                <div class="st-row-text"><label class="st-row-label" for="st-entry-background-blur">模糊程度</label><div class="hint">可调范围 0–32px，实时应用到预览和入口。</div></div>
                <div class="st-entry-background-range"><input id="st-entry-background-blur" type="range" min="0" max="32" step="1" value="0" data-input="settings.entryBackgroundBlur" aria-label="高斯模糊程度"><output id="st-entry-background-blur-value">0px</output></div>
              </div>
            </div>
            <div class="st-actions"><button class="ui-btn ui-btn--primary" type="button" data-action="settings.saveEntryBackground">保存入口背景</button><span class="st-actions-gap"></span><span class="st-status" id="st-entry-background-status" role="status"></span></div>
          </div>
        </section>`;
