/** 设置页「data」分区结构。 */
import { html } from '../../core/html.js';

export const dataView = () => html`<section class="st-section" id="st-sec-data" role="tabpanel" aria-labelledby="st-tab-data">
          <header class="st-head"><h2>数据与存储</h2><p>备份整个「错题」目录，查看存储占用并无损压缩题图。压缩前建议先导出一份备份。</p></header>
          <div class="card st-card">
            <div class="card-title">备份与恢复</div>
            <p class="hint st-lead">把「错题」目录打包成 .zip 下载留存。导入会先校验并预览，确认后才覆盖恢复。</p>
            <div class="opt-actions">
              <div class="opt-action" id="svc-a-export" role="button" tabindex="0" data-action="settings.backupExport" >
                <div class="opt-action-icon aicon-export"><svg viewBox="0 0 24 24"><path d="M12 3v12"></path><polyline points="7 10 12 15 17 10"></polyline><path d="M4 19h16"></path></svg></div>
                <div>
                  <div class="opt-action-name">导出备份</div>
                  <div class="opt-action-desc hint">下载完整 .zip 存档</div>
                </div>
              </div>
              <div class="opt-action" id="svc-a-import" role="button" tabindex="0" data-action="settings.backupPick" >
                <div class="opt-action-icon aicon-import"><svg viewBox="0 0 24 24"><path d="M12 15V3"></path><polyline points="7 8 12 3 17 8"></polyline><path d="M4 19h16"></path></svg></div>
                <div>
                  <div class="opt-action-name">导入备份</div>
                  <div class="opt-action-desc hint">从 .zip 校验后恢复</div>
                </div>
              </div>
            </div>
            <input type="file" id="opt-import-file" accept=".zip,application/zip" data-change="settings.backupImport" hidden>
            <div id="svc-backup-status" class="st-status"></div>
          </div>
          <div class="card st-card optimize-card">
            <div class="card-title">存储与图片压缩</div>
            <div class="opt-head">
              <div class="opt-head-left">
                <div class="opt-head-title">存储概览</div>
                <div class="opt-head-sub hint" id="opt-head-sub">加载中</div>
              </div>
              <div class="opt-head-total" id="opt-total">—</div>
            </div>
            <div class="opt-metrics">
              <div class="opt-metric" id="opt-m-data">
                <div class="opt-metric-label" id="opt-l-data">数据链</div>
                <div class="opt-metric-value" id="opt-v-data">—</div>
                <div class="opt-metric-detail hint" id="opt-d-data"></div>
                <progress class="st-opt-bar" id="opt-b-data" max="100" value="0" aria-label="数据链占用比例"></progress>
              </div>
              <div class="opt-metric" id="opt-m-files">
                <div class="opt-metric-label" id="opt-l-files">题目文件</div>
                <div class="opt-metric-value" id="opt-v-files">—</div>
                <div class="opt-metric-detail hint" id="opt-d-files"></div>
                <progress class="st-opt-bar" id="opt-b-files" max="100" value="0" aria-label="题目文件占用比例"></progress>
              </div>
              <div class="opt-metric" id="opt-m-images">
                <div class="opt-metric-label" id="opt-l-images">题目图片</div>
                <div class="opt-metric-value" id="opt-v-images">—</div>
                <div class="opt-metric-detail hint" id="opt-d-images"></div>
                <progress class="st-opt-bar" id="opt-b-images" max="100" value="0" aria-label="题目图片占用比例"></progress>
              </div>
            </div>
            <div class="opt-progress st-opt-progress" id="opt-progress" hidden>
              <div class="opt-progress-head">
                <span id="opt-progress-text">准备中</span>
                <strong id="opt-progress-percent">0%</strong>
              </div>
              <progress class="st-opt-progress__bar" id="opt-progress-fill" max="100" value="0" aria-label="图片处理进度"></progress>
              <div class="hint" id="opt-progress-file"></div>
            </div>
            <div class="opt-actions">
              <div class="opt-action" id="opt-a-scan" role="button" tabindex="0" data-action="settings.scanImages">
                <div class="opt-action-icon aicon-scan"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"></circle><line x1="16.5" y1="16.5" x2="21" y2="21"></line></svg></div>
                <div>
                  <div class="opt-action-name">扫描图片</div>
                  <div class="opt-action-desc hint">快速扫描可无损压缩的图片，不改动任何文件</div>
                </div>
              </div>
              <div class="opt-action disabled" id="opt-a-compress" role="button" tabindex="0" aria-disabled="true" data-action="settings.compress">
                <div class="opt-action-icon aicon-compress"><svg viewBox="0 0 24 24"><polyline points="4 10 10 10 10 4"></polyline><polyline points="20 14 14 14 14 20"></polyline><line x1="10" y1="10" x2="4" y2="4"></line><line x1="14" y1="14" x2="20" y2="20"></line></svg></div>
                <div>
                  <div class="opt-action-name">确认压缩</div>
                  <div class="opt-action-desc hint" id="opt-compress-hint">扫描图片后可压缩</div>
                </div>
              </div>
            </div>
            <div class="opt-deps" id="opt-deps"></div>
            <div id="opt-status"></div>
          </div>
        </section>`;
