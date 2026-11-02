/** 数据复盘的题目明细；沿用共享表格和题目弹窗。 */
import { html, each } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { select } from '../../ui/select.js';
import { table } from '../../ui/table.js';
import { reviewCycle } from '../../domain/question/review-cycle.js';
import { pct } from './state.js';
import { statusOf } from './progress.js';

export function questionsView(s, list) {
  return html`<div class="dat-filters" role="group" aria-label="按题目状态筛选">${each(list.counts, row => row.key, row => button({
    label: `${row.label} ${row.count}`, action: 'data.filter', arg: row.key, pressed: s.filter === row.key,
    variant: s.filter === row.key ? 'primary' : 'default',
  }))}</div>
  <div class="dat-tools">${select({ id: 'dat-subject', label: '明细科目', value: s.subject,
    options: [{ value: '', label: '全部科目' }, ...list.subjects.map(value => ({ value, label: value }))] })}
    <input class="ui-input" id="dat-search" type="search" aria-label="搜索题目明细" placeholder="搜索 UID、科目、分类或标记" value="${s.query}" data-input="data.search">
  </div>
  <p class="dat-card__sub">已击杀包含休眠中和复燃待复核；从未复习、顽固题与状态可能重叠。停用题不参与复盘。</p>
  ${table({ rowKey: 'uid', stack: true, rows: list.rows, empty: '没有符合条件的题目，可切换状态或清空搜索。', columns: [
    { key: 'uid', label: '题目', render: row => html`<b class="dat-uid">${row.uid}</b><span class="dat-question__meta">${row.subject} / ${row.category || '未分类'}</span>` },
    { key: 'status', label: '当前状态', render: row => { const status = statusOf(row); return html`<span class="dat-tone" data-tone="${status.tone}">${status.label}</span>`; } },
    { key: 'mastery', label: '熟练度', num: true, render: row => pct(row.mastery) },
    { key: 'kill_count', label: '累计击杀', num: true, render: row => `${Number(row.kill_count) || 0} 次` },
    { key: 'cycle', label: '排期 / 复核', render: row => { const cycle = reviewCycle(row); return html`<span${cycle ? html` title="${cycle.title}"` : ''}>${cycle?.label || '下次复习'}</span><span class="dat-question__meta">${row.due_date || '待安排'}</span>`; } },
    { key: 'actions', label: '操作', render: row => html`<span class="dat-acts">${button({ label: '查看', size: 'sm', action: 'data.detail', arg: row.uid })}${button({ label: '加入展示板', size: 'sm', variant: 'ghost', action: 'data.board', arg: row.uid })}</span>` },
  ] })}
  <div class="dat-pager"><span class="dat-card__sub" role="status">共 ${list.total} 题 · 第 ${list.page} / ${list.pages} 页</span>
    <div class="dat-acts">${button({ label: '上一页', action: 'data.page', arg: list.page - 1, disabled: list.page <= 1 })}${button({ label: '下一页', action: 'data.page', arg: list.page + 1, disabled: list.page >= list.pages })}</div>
  </div>`;
}
