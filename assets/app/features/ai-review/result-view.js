/** 执行结果与原生回执；批准状态不代替业务执行结果。 */
import { html } from '../../core/html.js';
import { button } from '../../ui/button.js';

export function resultView(item) {
  const result = item.result || {}, rows = result.items || result.details || [];
  if (!Object.keys(result).length && !item.commits?.length) return '';
  return html`<section class="arv-related" aria-label="实际执行结果"><h3>实际执行结果</h3>
    ${result.message || result.summary ? html`<p>${result.message || result.summary}</p>` : ''}
    ${result.draft_id ? button({ label: '查看关联草稿', action: 'ai-review.openDraft', arg: result.draft_id }) : ''}
    ${result.board_id ? button({ label: '查看关联展示板', action: 'ai-review.openBoard', arg: result.board_id }) : ''}
    ${result.session_id ? button({ label: '查看复习计划', action: 'ai-review.openSession', arg: result.session_id }) : ''}
    ${result.card_id ? button({ label: '打开练习卡', action: 'ai-review.openPractice', arg: result.card_id }) : ''}
    ${result.report_id ? html`<a class="ui-btn" href="/api/report/view?id=${encodeURIComponent(result.report_id)}" target="_blank" rel="noopener noreferrer">查看报告</a>` : ''}
    ${Array.isArray(rows) ? rows.map(row => html`<p>${row.uid || row.question_id || '关联项目'}：${row.error || row.msg || row.message || row.summary || ({ ok: '成功', applied: '已应用', failed: '失败', unchanged: '无变更' })[row.status] || row.status || '已有回执'}</p>`) : ''}
    ${Array.isArray(result.failed) && result.failed.length ? html`<p>未完成：${result.failed.map(row => typeof row === 'string' ? row : [row.uid, row.error || row.msg].filter(Boolean).join(' · ')).join('、')}</p>` : ''}
    ${item.commits?.length ? html`<p class="arv-muted">已生成 ${item.commits.length} 条变更记录。</p>` : ''}
    <details class="arv-context"><summary>查看回执详情</summary><pre>${JSON.stringify({ result, commits: item.commits || [] }, null, 2)}</pre></details></section>`;
}
