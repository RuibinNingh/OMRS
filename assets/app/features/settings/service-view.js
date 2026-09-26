/** 设置页「service」分区结构。 */
import { html } from '../../core/html.js';

export const serviceView = () => html`<section class="st-section" id="st-sec-service" role="tabpanel" aria-labelledby="st-tab-service">
          <header class="st-head"><h2>服务与运行</h2><p>查看服务状态、重启服务，或下载脱敏源码包用于协助排查。</p></header>
          <div class="card st-card">
            <div class="card-title">运行状态</div>
            <div class="status-grid st-runtime" id="st-runtime">
              <div><span>版本</span><strong id="st-runtime-version">—</strong></div>
              <div><span>已运行</span><strong id="st-runtime-uptime">—</strong></div>
              <div><span>托管题目</span><strong id="st-runtime-count">—</strong></div>
              <div><span>状态</span><strong id="st-runtime-state">加载中</strong></div>
            </div>
            <div class="hint st-lead" id="st-runtime-vault"></div>
            <dl class="st-paths">
              <div><dt>后端入口</dt><dd><code>omrs_engine.py</code></dd></div>
              <div><dt>前端文件</dt><dd><code>omrs_dashboard.html</code> + <code>assets/</code></dd></div>
              <div><dt>数据目录</dt><dd><code>错题/.omrs/</code></dd></div>
            </dl>
            <div class="st-actions">
              <button class="btn" type="button" data-action="settings.refreshStatus">刷新状态</button>
              <span class="st-actions-gap"></span>
              <button class="btn danger" type="button" data-action="settings.restart">重启服务</button>
            </div>
            <div class="hint">重启期间页面会短暂无响应；确认新服务就绪后自动刷新，最长等待 90 秒。远端登录会在重启后失效。</div>
            <div id="st-status" class="st-status" role="status"></div>
          </div>
          <div class="card st-card">
            <div class="card-title">源码协助</div>
            <p class="hint st-lead">按项目源码目录下载脱敏 .zip，包含未提交的源码，不依赖 Git；不含「错题」题库、附件、运行数据、日志或生成的导出文件。分享前请核对包内清单和源码内容。</p>
            <button class="btn" type="button" data-action="settings.sourceExport">下载脱敏源码</button>
            <div id="svc-source-status" class="st-status"></div>
          </div>
        </section>`;
