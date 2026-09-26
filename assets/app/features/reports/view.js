/** 报告页：材料准备、上传、列表与隔离预览。 */
import { html, each } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { empty } from '../../ui/empty.js';
import { filedrop } from '../../ui/filedrop.js';
import { skeleton } from '../../ui/skeleton.js';
import { formatSize, materialHint } from './state.js';

function reportRow(row, selected) {
  return html`<article class="rpw-row" data-key="${row.id}"${selected ? html` data-selected` : ''}>
    <div class="rpw-row__text"><strong>${row.name}</strong><p>${row.created_at || ''} · ${formatSize(row.size)}</p><code>${row.id}</code></div>
    <div class="rpw-row__actions">
      ${button({ label: '浏览', size: 'sm', action: 'reports.open', arg: row.id })}
      ${button({ label: '删除', size: 'sm', variant: 'danger', action: 'reports.delete', arg: row.id })}
    </div>
  </article>`;
}

export function view(s) {
  const selected = s.reports.find(row => row.id === s.selectedId);
  return html`<section class="rpw" data-key="reports-view">
    <div class="rpw-grid">
      <section class="rpw-card" aria-labelledby="rpw-create-title"><h2 id="rpw-create-title">创建报告</h2>
        <p class="rpw-intro">先准备分析材料并交给 AI，再上传生成的 HTML 报告。报告由本程序托管。</p>
        <div class="rpw-kit"><div class="rpw-kit__head"><div><strong>AI 分析材料</strong><p>提示词会按图片选项调整</p></div>
          <label class="rpw-check"><input id="rp-include-images" type="checkbox" data-change="reports.images"${s.includeImages ? html` checked` : ''}>包含题目图片</label></div>
          <div class="rpw-actions">${button({ label: '复制 AI 报告提示词', size: 'sm', action: 'reports.prompt' })}
            ${button({ label: '下载分析数据', size: 'sm', action: 'reports.download', loading: s.downloading })}</div>
          <p class="rpw-hint" id="rp-material-hint">${materialHint(s.includeImages)}</p></div>
        <label class="rpw-field">报告名称 *<input id="rp-name" type="text" placeholder="如：6 月薄弱点分析" value="${s.name}" data-input="reports.name"></label>
        <div class="rpw-upload">${filedrop({ id: 'rp-file', title: s.file ? s.file.name : '拖入 HTML 文件，或点击选择',
          hint: s.file ? formatSize(s.file.size) : '支持 .html / .htm', accept: '.html,.htm,text/html', disabled: s.uploading,
          error: s.fileError })}</div>
        ${button({ label: '上传并创建', action: 'reports.create', variant: 'primary', loading: s.uploading })}
        <p class="rpw-status" id="rp-status" role="status"${s.statusTone ? html` data-tone="${s.statusTone}"` : ''}>${s.status}</p>
      </section>
      <section class="rpw-card" aria-labelledby="rpw-list-title"><div class="rpw-list-head"><h2 id="rpw-list-title">已托管报告</h2>
        ${button({ label: '刷新', size: 'sm', icon: 'refresh', action: 'reports.refresh', loading: s.loading })}</div>
        ${s.listError ? html`<p class="rpw-error" role="alert">无法加载报告：${s.listError}</p>` : ''}
        <div id="rp-list" class="rpw-list">${s.loading && !s.loaded ? skeleton({ lines: 3 })
          : !s.reports.length ? empty({ icon: 'file', title: '还没有报告', hint: '在左侧上传一个 HTML 报告。' })
            : each(s.reports, row => row.id, row => reportRow(row, row.id === s.selectedId))}</div>
      </section>
    </div>
    ${selected ? html`<section class="rpw-card rpw-preview" aria-labelledby="rpw-preview-title"><div class="rpw-list-head">
      <div><h2 id="rpw-preview-title">${selected.name}</h2><p>报告在独立来源的沙箱里预览</p></div>
      <div class="rpw-actions">${button({ label: '新标签打开', size: 'sm', action: 'reports.newTab', arg: selected.id })}
        ${button({ label: '关闭预览', size: 'sm', action: 'reports.close' })}</div></div>
      <iframe class="rpw-frame" title="报告预览：${selected.name}" src="/api/report/view?id=${encodeURIComponent(selected.id)}"
        sandbox="allow-scripts allow-downloads allow-popups" referrerpolicy="no-referrer" data-morph="skip"></iframe>
    </section>` : ''}
  </section>`;
}
