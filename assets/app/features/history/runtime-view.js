/** MCP 调用列表与只读详情，所有动态内容经过 html 模板转义。 */
import { html } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { icon } from '../../ui/icon.js';
import { status } from '../../ui/status.js';
import { formatLedgerTime } from '../../domain/history.js';
import { durationText, timeGroups } from './state.js';

const LABELS = { success: '成功', failure: '失败', running: '进行中', interrupted: '已中断' };
const DRAFTS = { review: '待审核', pending: '待处理', cropping: '待框选', done: '已入库', discarded: '已丢弃', missing: '草稿不可用' };
export const runtimeLabel = row => LABELS[row.status] || '未知状态';

export function runtimeTimeline(s, zone) {
  return timeGroups(s.records, zone).map(group => html`<section class="hvw-day" data-key="runtime-day-${group.date}">
    <div class="hvw-day-head"><h3>${group.date}</h3><span>${group.rows.length} 条</span></div>
    ${group.rows.map(row => html`<article class="hvw-node hvw-runtime-node" data-key="runtime-${row.seq}" data-seq="${row.seq}" data-family="system">
      <button type="button" class="hvw-row" data-action="history.select" data-arg="${row.seq}" aria-pressed="${String(Number(s.selectedSeq) === row.seq)}">
        <time class="hvw-time">${formatLedgerTime(row.started_at, zone).slice(11, 16)}</time>
        <span class="hvw-event-icon" data-tone="${row.status}">${icon(row.status === 'failure' || row.status === 'interrupted' ? 'alert-circle' : row.tool === 'create_draft' ? 'file' : 'link')}</span>
        <span class="hvw-row-body"><span class="hvw-row-title">${row.title}</span>
          <span class="hvw-row-description">${row.scope_summary}${row.scope_summary ? ' · ' : ''}${row.summary}</span>
          <span class="hvw-meta"><span class="hvw-state" data-tone="${row.status}">${runtimeLabel(row)}</span><span>${row.key_name || '未识别密钥'}</span><span>${durationText(row)}</span></span>
        </span>
      </button>
    </article>`)}
  </section>`);
}

export function runtimePanel(s, zone) {
  if (s.selectedSeq == null) return html`<p class="hvw-panel-empty">选择一条调用，查看结果与关联。</p>`;
  const key = String(s.selectedSeq), cached = s.details.get(key);
  const row = cached || s.records.find(item => item.seq === Number(s.selectedSeq));
  const error = s.detailErrors.get(key);
  const retry = button({ label: '重试详情', size: 'sm', action: 'history.select', arg: key });
  if (!row) return error ? html`${status({ tone: 'danger', text: `详情读取失败：${error}` })}${retry}` : html`<p class="hvw-panel-empty">正在读取调用详情…</p>`;
  return html`<article class="hvw-panel-content">
    ${error ? html`${status({ tone: 'danger', text: `详情刷新失败：${error}` })}${retry}` : ''}
    <span class="hvw-state" data-tone="${row.status}">${runtimeLabel(row)}</span>
    <h3 class="hvw-title">${row.title}</h3><p class="hvw-muted hvw-tool">${row.tool}</p>
    <p class="hvw-outcome" data-tone="${row.status}">${row.summary}</p>
    <dl class="hvw-facts"><dt>时间</dt><dd>${formatLedgerTime(row.started_at, zone)}</dd>
      <dt>来源</dt><dd>MCP</dd><dt>所用密钥</dt><dd>${row.key_name || '未识别密钥'}</dd>
      <dt>耗时</dt><dd>${durationText(row)}</dd><dt>调用性质</dt><dd>${row.tool === 'create_draft' ? '创建待审核草稿' : row.tool === 'unknown_tool' ? '未开放工具' : '只读查询'}</dd></dl>
    ${cached?.draft ? html`<section class="hvw-related"><h4>关联草稿</h4>
      <p class="hvw-muted">${DRAFTS[cached.draft.status] || cached.draft.status}</p>
      ${button({ label: '查看草稿', size: 'sm', iconRight: 'arrow-right', action: 'history.openDraft', arg: cached.draft.id, disabled: cached.draft.status === 'missing' })}
    </section>` : ''}
    ${cached?.related_commits?.length ? html`<section class="hvw-related"><h4>后续人工操作</h4>${cached.related_commits.map(commit => button({ label: `${commit.title} · ${commit.uid}`, size: 'sm', iconRight: 'arrow-right', action: 'history.learningRelated', arg: String(commit.seq) }))}</section>` : ''}
    ${cached ? html`<details class="hvw-details" data-key="runtime-arguments"><summary>参数摘要</summary><pre>${JSON.stringify(cached.arguments, null, 2)}</pre></details>
      <details class="hvw-details" data-key="runtime-result"><summary>结果摘要</summary><pre>${cached.status === 'running' ? '尚未完成' : JSON.stringify(cached.result, null, 2)}</pre></details>
      <details class="hvw-details" data-key="runtime-technical"><summary>技术信息</summary><dl class="hvw-facts"><dt>调用编号</dt><dd>${cached.call_id}</dd><dt>错误码</dt><dd>${cached.error_code || '—'}</dd></dl><p class="hvw-muted">仅保留脱敏摘要，不记录密钥明文、正文或原图。</p></details>`
      : html`<p class="hvw-muted">${error ? '详情暂不可用' : '正在读取详情…'}</p>`}
  </article>`;
}
