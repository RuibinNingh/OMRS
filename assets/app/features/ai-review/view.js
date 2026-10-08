/** 审核中心外框：单一队列与按需详情，草稿表单由原编辑控制器拥有。 */
import { html, each } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { empty } from '../../ui/empty.js';
import { status } from '../../ui/status.js';
import { itemLabel, itemSummary, reviewStatus, sourceLabel } from './state.js';
import { operationView } from './operation-view.js';

const options = (values, current) => values.map(([value, label]) => html`<option value="${value}"${value === current ? html` selected` : ''}>${label}</option>`);
export function reviewView(s) {
  if (s.embedded) return html`<section class="arv arv-embedded" aria-label="对话内审核详情">${detailView(s)}</section>`;
  return html`<section class="arv" data-mobile-detail="${String(s.mobileDetail)}"><header class="arv-header"><div><h2>审核中心</h2><p class="arv-muted">核对 AI 写入，查看已经执行的修改。</p></div><div class="arv-tabs">${button({ label: '草稿维护', action: 'ai-review.draftQueueMenu', disabled: s.busy })}${button({ label: '刷新', icon: 'refresh', action: 'ai-review.refresh' })}</div></header>
    <div class="arv-toolbar"><div class="arv-tabs" role="group" aria-label="审核视图">${button({ label: `待审核${s.counts ? ` ${s.counts.pending}` : ''}`, action: 'ai-review.view', arg: 'pending', pressed: s.view === 'pending', variant: s.view === 'pending' ? 'primary' : 'default' })}
      ${button({ label: '操作记录', action: 'ai-review.view', arg: 'records', pressed: s.view === 'records', variant: s.view === 'records' ? 'primary' : 'default' })}</div>
      <select class="ui-select" aria-label="筛选来源" data-change="ai-review.source">${options([['', '全部来源'], ['mcp', 'MCP'], ['agent', 'AI 助手'], ['legacy', '旧草稿']], s.source)}</select>
      <select class="ui-select" aria-label="筛选操作类型" data-change="ai-review.type">${options([['', '全部写操作'], ['draft', '新题草稿'], ['question', '题目修改'], ['session', '复习计划'], ['feedback', '学习反馈'], ['board', '展示板'], ['report', '报告'], ['category', '分类'], ['practice', '练习卡']], s.type)}</select>
      <select class="ui-select" aria-label="筛选提交时间" data-change="ai-review.range">${options([['', '全部时间'], ['1', '今天'], ['7', '最近 7 天'], ['30', '最近 30 天']], s.range)}</select>
      ${s.view === 'records' ? html`<select class="ui-select" aria-label="筛选操作状态" data-change="ai-review.status">${options([['', '全部状态'], ['applied', '已执行'], ['done', '草稿已入库'], ['discarded', '草稿已丢弃'], ['approved', '已批准，待执行'], ['partial', '部分成功'], ['unchanged', '无变更'], ['rejected', '已拒绝'], ['failed', '失败'], ['expired', '已过期'], ['conflict', '有冲突'], ['cancelled', '已中止'], ['interrupted', '已中断']], s.status)}</select>` : ''}</div>
    ${s.listError ? status({ tone: 'danger', text: `读取队列失败：${s.listError}；保留已有结果。` }) : ''}
    <div class="arv-workspace"><aside class="arv-queue" aria-label="AI 写操作队列">${!s.loaded ? html`<p role="status">正在读取…</p>`
      : s.items.length ? html`<div class="arv-items">${each(s.items, item => `${item.kind}:${item.id}`, item => html`<button class="arv-row" type="button" data-action="ai-review.open" data-arg="${item.id}" aria-current="${s.selectedId === item.id ? 'true' : 'false'}">
      <strong>${itemLabel(item)}</strong><span>${itemSummary(item)}</span><small>${sourceLabel(item)} · ${reviewStatus(item)}</small></button>`)}</div>`
        : empty({ icon: 'check-circle', title: s.view === 'pending' ? '没有待审核操作' : '没有匹配的写操作', hint: s.view === 'pending' ? 'MCP 和 AI 助手提交的写入提案会出现在这里。' : '调整来源、类型或状态筛选。', bordered: true })}
      ${s.hasMore ? button({ label: s.loadingMore ? '加载中…' : '加载更多', action: 'ai-review.more', disabled: s.loadingMore }) : ''}</aside>
      <section class="arv-detail" aria-label="审核详情"><div class="arv-mobile-back">${button({ label: '返回列表', icon: 'arrow-left', variant: 'ghost', action: 'ai-review.back' })}</div>
      ${detailView(s)}</section></div>
  </section>`;
}
function detailView(s) {
  return s.detailLoading ? html`<p role="status">正在读取详情…</p>` : s.detailError ? html`${status({ tone: 'danger', text: `详情读取失败：${s.detailError}` })}${button({ label: '重试详情', action: 'ai-review.retry' })}`
    : s.item?.kind === 'draft' ? html`<div id="ib-stage-drafts" data-key="review-draft-editor" data-morph="skip"></div>`
      : s.item ? operationView(s) : empty({ icon: 'edit', title: s.embedded ? '正在准备详情' : '选择一项操作', hint: '核对修改内容和影响范围，再决定是否执行。', bordered: true });
}
