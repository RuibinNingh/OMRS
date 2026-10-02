/** 分区时间线：学习与变更、系统运行及选择式详情面板。 */
import { html } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { icon } from '../../ui/icon.js';
import { tabs } from '../../ui/tabs.js';
import { empty } from '../../ui/empty.js';
import { skeleton } from '../../ui/skeleton.js';
import { status } from '../../ui/status.js';
import { historyCommitFamily, historyNodeTitle, historyNodeSubtitle, formatLedgerTime, historySourceLabel } from '../../domain/history.js';
import { timeline, timeGroups } from './state.js';
import { learningPanel, correction } from './learning-view.js';
import { runtimeTimeline, runtimePanel } from './runtime-view.js';

const choices = (values, value) => values.map(([id, label]) => html`<option value="${id}"${value === id ? ' selected' : ''}>${label}</option>`);

function toolbar(s, rows) {
  return html`<div class="hvw-filters">
    <label class="hvw-search">${icon('search')}<input class="ui-input" type="search" maxlength="200" value="${s.query}" placeholder="搜索动作、科目或题目" aria-label="搜索历史记录" data-input="history.query"></label>
    <select class="ui-select" aria-label="时间范围" data-change="history.range">${choices([['all','全部时间'],['today','今天'],['7d','最近 7 天'],['30d','最近 30 天']], s.range)}</select>
    ${s.tab === 'system' ? html`<select class="ui-select" aria-label="所用密钥" data-change="history.key">${choices([['','全部密钥'], ...s.system.keys.map(key => [key.key_id, key.name])], s.system.key)}</select>
      <select class="ui-select" aria-label="调用状态" data-change="history.status">${choices([['','全部状态'],['failure','失败'],['success','成功'],['running','进行中'],['interrupted','已中断'],['pending_confirmation','待网页确认'],['applied','已应用'],['rejected','已拒绝'],['expired','已到期'],['conflict','冲突']], s.system.status)}</select>`
      : html`<select class="ui-select" id="history-sort" aria-label="记录排序" data-change="history.sort">${choices([['desc','最新在前'],['asc','最早在前']], s.sort)}</select>
        ${button({ label: `修正记录 ${rows.corrections.length}`, size: 'md', action: 'history.corrections', pressed: s.correctionsOpen })}
        ${button({ label: `修正模式：${s.edit ? '开' : '关'}`, size: 'md', action: 'history.mode', pressed: s.edit, variant: s.edit ? 'primary' : 'default' })}`}
  </div>`;
}

function learningRows(s, rows, zone) {
  return timeGroups(rows.main, zone).map(group => html`<section class="hvw-day" data-key="learning-day-${group.date}">
    <div class="hvw-day-head"><h3>${group.date}</h3><span>${group.rows.length} 条</span></div>
    ${group.rows.map(row => html`<article class="hvw-node" data-key="${row.commit_id || row.seq}" data-family="${historyCommitFamily(row.commit_type)}" data-seq="${row.seq}">
      <button type="button" class="hvw-row" data-action="history.select" data-arg="${row.seq}" aria-pressed="${String(Number(s.selectedSeq) === row.seq)}">
        <time class="hvw-time">${formatLedgerTime(row.created_at, zone).slice(11, 16) || '初始'}</time>
        <span class="hvw-event-icon">${icon(historyCommitFamily(row.commit_type) === 'review' ? 'check-circle' : 'book')}</span>
        <span class="hvw-row-body"><span class="hvw-row-title">${historyNodeTitle(row, rows.rs)}</span>
          <span class="hvw-row-description">${historyNodeSubtitle(row, rows.rs)}</span>
          <span class="hvw-meta"><span>${historySourceLabel(row.source)}</span>${row.learning?.subjects ? html`<span>${Object.entries(row.learning.subjects).map(([name,count]) => `${name} ${count} 题`).join('、')}</span>` : ''}</span>
        </span>
      </button>
    </article>`)}
  </section>`);
}

function listBody(s, kind, rows, zone) {
  const data = kind === 'system' ? s.system : s;
  const list = kind === 'system' ? data.records : rows.main;
  const count = kind === 'system' ? data.records.length : s.commits.length;
  if (!count && data.phase === 'loading') return skeleton({ lines: 5 });
  if (!count && data.phase === 'error') return empty({ icon: 'alert-circle', title: '记录加载失败', hint: data.error, action: { label: '重试', action: 'history.refresh' } });
  if (!list.length) return empty({ icon: 'clock', title: s.query || s.range !== 'all' || (kind === 'system' && (data.key || data.status)) ? '没有匹配记录' : '暂无记录',
    hint: kind === 'system' ? '获授权的 MCP 工具调用会在这里留下记录；旧调用不会补造。' : '可调整筛选，或查看修正记录。', action: { label: '刷新', action: 'history.refresh' } });
  return kind === 'system' ? runtimeTimeline(data, zone) : learningRows(s, rows, zone);
}

function content(s, rows, kind, zone) {
  const data = kind === 'system' ? s.system : s;
  const selected = s.commits.find(row => row.seq === Number(s.selectedSeq)) || s.details.get(String(s.selectedSeq));
  return html`<div class="hvw-workspace" data-mobile-detail="${String(s.mobileDetail && s.tab === kind)}">
    <div class="hvw-list-column"><div class="hvw-timeline" id="${kind === 'system' ? 'runtime-timeline' : 'history-timeline'}" aria-label="${kind === 'system' ? 'MCP 调用时间线' : 'Ledger 主时间线'}">${listBody(s, kind, rows, zone)}</div>
      ${data.hasMore ? html`<div class="hvw-more">${button({ label: data.loadingMore ? '加载中…' : '加载更早记录', size: 'sm', action: 'history.more', disabled: data.loadingMore })}</div>` : ''}
    </div>
    <aside class="hvw-detail-panel" data-key="detail-${kind}-${data.selectedSeq}" aria-label="${kind === 'system' ? '调用详情' : '学习记录详情'}">
      <div class="hvw-panel-head"><span>${kind === 'system' ? '调用详情' : '记录详情'}</span>${button({ label: '返回列表', size: 'sm', variant: 'ghost', icon: 'arrow-left', action: 'history.close', state: 'back' })}${button({ label: '关闭详情', size: 'sm', variant: 'ghost', icon: 'x', iconOnly: true, action: 'history.close' })}</div>
      ${kind === 'system' ? runtimePanel(data, zone) : learningPanel(selected, s, rows.rs, zone)}
    </aside>
  </div>`;
}

export function view(s, zone) {
  const rows = timeline(s), system = s.system;
  return html`<section class="hvw" data-key="history-view">
    <header class="hvw-toolbar"><div><h2>历史记录</h2><p>回看学习轨迹，追踪系统运行。</p></div>${button({ label: '刷新', size: 'md', icon: 'refresh', action: 'history.refresh' })}</header>
    <div class="hvw-tabs">${tabs({ label: '历史记录分类', idPrefix: 'history-tab', value: s.tab,
      items: [{ id: 'learning', label: '学习与变更', panel: 'history-learning-panel' }, { id: 'system', label: '系统运行', panel: 'history-system-panel' }] })}</div>
    ${toolbar(s, rows)}
    <section id="history-learning-panel" role="tabpanel" aria-labelledby="history-tab-learning"${s.tab !== 'learning' ? ' hidden' : ''}>
      ${s.error && s.commits.length ? status({ tone: 'danger', text: `历史刷新失败：${s.error}；保留上次成功结果。` }) : ''}
      ${s.writeError ? status({ tone: 'danger', text: s.writeError }) : ''}${s.note ? status({ tone: 'success', text: s.note }) : ''}
      ${s.edit ? html`<p class="hvw-edit-hint">修正模式已开启；操作会追加节点，原始记录保留。</p>` : ''}
      ${s.correctionsOpen ? html`<section class="hvw-corrections" id="history-corrections" aria-label="修正记录">${rows.corrections.length ? rows.corrections.map(row => correction(row, { s, rows, zone })) : empty({ title: '暂无修正记录', compact: true })}</section>` : ''}
      ${content(s, rows, 'learning', zone)}
      <p class="hvw-summary" id="history-status" role="status">主时间线 ${rows.main.length} 个节点${rows.hidden ? `（${rows.hidden} 个已撤销已隐藏）` : ''}；修正记录 ${rows.corrections.length} 条</p>
    </section>
    <section id="history-system-panel" role="tabpanel" aria-labelledby="history-tab-system"${s.tab !== 'system' ? ' hidden' : ''}>
      ${system.error && system.records.length ? status({ tone: 'danger', text: `运行记录刷新失败：${system.error}；保留上次成功结果。` }) : ''}
      <p class="hvw-summary" role="status">MCP · ${system.summary.total} 次调用 · ${system.summary.failure} 次失败 · ${system.summary.running} 次进行中${system.summary.interrupted ? ` · ${system.summary.interrupted} 次中断` : ''}${system.summary.pending_confirmation ? ` · ${system.summary.pending_confirmation} 次待确认` : ''}</p>
      ${content(s, rows, 'system', zone)}
      <p class="hvw-summary">已显示 ${system.records.length} 条 · 高风险操作在详情确认</p>
    </section>
  </section>`;
}
