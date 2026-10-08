/** 操作详情：安全转义前后对照，人工修订只展示服务端允许的字段。 */
import { html, raw } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { status } from '../../ui/status.js';
import { renderMd } from '../../domain/question/index.js';
import { itemLabel, itemSummary, sourceLabel, reviewStatus, isPending, changesOf, FIELD_LABELS, editInput } from './state.js';
import { draftSnapshot, relatedPreview } from './preview-view.js';
import { resultView } from './result-view.js';

const readable = (value, kind) => kind === 'list' || Array.isArray(value)
  ? html`<p>${(Array.isArray(value) ? value : []).map(v => typeof v === 'object' ? v.label || v.uid || v.question_id || '关联项目' : v).join('、') || '（空）'}</p>`
  : typeof value === 'number' ? html`<p>${value}</p>`
    : value ? html`<div class="q-md">${raw(renderMd(String(value)))}</div>` : html`<p class="arv-muted">（空）</p>`;
function impactView(preview) {
  const impact = preview?.impact || preview || {};
  return html`${(impact.reasons || []).length ? html`<p>${impact.reasons.join('、')}</p>` : ''}
    ${(impact.boards || []).map(board => html`<p>${board.name}：${board.deleted ? '删除展示板' : `${board.items_before} → ${board.items_after} 道题`}${board.paper_reset ? '；清除纸面记录' : ''}</p>`)}
    ${impact.folder ? html`<p>文件夹「${impact.folder.name}」：${impact.keep_boards ? '保留展示板，移到未归档' : '同时删除展示板'}</p>` : ''}`;
}
function editForm(s) {
  return html`<section class="arv-edit" aria-label="人工修订提案"><h3>人工修订</h3><p class="arv-muted">保存后请核对更新后的影响预览，再确认执行。</p>
    ${Object.entries(s.edited).map(([field, value]) => {
      const change = changesOf(s.item).find(row => row.field === field);
      const label = change?.label || FIELD_LABELS[field] || field;
      const numeric = typeof value === 'number' || change?.kind === 'number';
      return html`<label class="arv-field">${label}${numeric
        ? html`<input class="ui-input" type="number" value="${value}" data-input="ai-review.editField" data-arg="${field}"${s.busy ? html` disabled` : ''}>`
        : html`<textarea class="ui-textarea" rows="${Array.isArray(value) ? 2 : 5}" data-input="ai-review.editField" data-arg="${field}"${s.busy ? html` disabled` : ''}>${editInput(value)}</textarea>`}
        ${Array.isArray(value) ? html`<small class="arv-muted">用逗号或换行分隔。</small>` : ''}</label>`;
    })}</section>`;
}
export function operationView(s) {
  const item = s.item, preview = item.preview || {}, changes = changesOf(item);
  const pending = isPending(item);
  const unread = !!s.detailError || !!s.error?.startsWith('详情刷新失败');
  const reviewer = item.decision?.actor || {};
  return html`<article class="arv-operation" data-key="operation-${item.id}">
    <header class="arv-detail-head"><div><p class="arv-muted">${sourceLabel(item)} · ${reviewStatus(item)}</p><h2>${itemLabel(item)}</h2><p>${itemSummary(item)}</p></div>
      ${pending && Object.keys(s.original).length ? button({ label: s.editing ? '查看影响预览' : '人工修订', size: 'md', action: 'ai-review.edit', pressed: s.editing, disabled: s.busy }) : ''}</header>
    <dl class="arv-facts"><div><dt>操作编号</dt><dd>${item.id}</dd></div><div><dt>提案版本</dt><dd>第 ${item.revision} 版</dd></div><div><dt>提交时间</dt><dd>${time(item.created_at)}</dd></div><div><dt>来源</dt><dd>${item.actor?.name || item.actor?.key_name || sourceLabel(item)}</dd></div>
      ${item.actor?.key_id || item.key_id ? html`<div><dt>MCP 密钥编号</dt><dd>${item.actor?.key_id || item.key_id}</dd></div>` : ''}
      ${item.actor?.request_id ? html`<div><dt>来源请求</dt><dd>${item.actor.request_id}</dd></div>` : ''}
      ${item.actor?.run_id ? html`<div><dt>来源运行</dt><dd>${item.actor.run_id}</dd></div>` : ''}
      ${item.actor?.tool_call_id || item.actor?.runtime_seq ? html`<div><dt>来源调用</dt><dd>${item.actor.tool_call_id || item.actor.runtime_seq}</dd></div>` : ''}
      ${reviewer.kind || reviewer.access ? html`<div><dt>审核身份</dt><dd>${reviewer.kind === 'web' ? 'Web' : reviewer.kind || ''}${reviewer.access ? ` · ${({ direct: '本机访问', session: '登录会话' })[reviewer.access] || reviewer.access}` : ''}</dd></div>` : ''}
      ${reviewer.client_ip ? html`<div><dt>审核来源 IP</dt><dd>${reviewer.client_ip}</dd></div>` : ''}
      ${item.expires_at ? html`<div><dt>有效期至</dt><dd>${time(item.expires_at)}</dd></div>` : ''}</dl>
    ${item.history_incomplete ? status({ tone: 'warning', text: '历史信息不完整；只显示可以验证的记录。' }) : ''}
    ${item.revision > 1 ? html`<p class="arv-muted">提案已人工修订，以下展示当前版本。</p>` : ''}
    ${item.decision ? html`<p class="arv-muted">${item.decision.decision === 'approve' ? '已批准' : '已拒绝'} · ${time(typeof item.decision.decided_at === 'number' ? item.decision.decided_at * 1000 : item.decision.decided_at)}</p>` : ''}
    ${s.error ? status({ tone: 'danger', text: s.error }) : ''}${unread ? button({ label: '重试详情', action: 'ai-review.retry', disabled: s.busy }) : ''}${s.note ? status({ tone: 'success', text: s.note }) : ''}
    ${item.error_code ? status({ tone: 'danger', text: `未应用：${item.error_code}` }) : ''}
    ${s.editing ? editForm(s) : html`${item.tool === 'commit_draft' ? draftSnapshot(preview) : ''}${relatedPreview(item)}${changes.length ? html`<section class="arv-changes" aria-label="修改前后对照">${changes.map(change => html`<section class="arv-change"><h3>${change.label || FIELD_LABELS[change.field] || change.field}</h3>
      <div class="arv-diff"><div><h4>当前内容</h4>${readable(change.before, change.kind)}</div><div class="arv-after"><h4>修改后</h4>${readable(change.after, change.kind)}</div></div></section>`)}</section>` : impactView(preview)}
      ${preview.question || preview.answer ? html`<details class="ui-disclosure arv-context"><summary>对照完整题目与答案</summary><h3>题目</h3>${readable(preview.question)}<h3>答案解析</h3>${readable(preview.answer)}</details>` : ''}
      `}
    ${item.original_payload && item.revision > 1 ? html`<details class="arv-context"><summary>查看原始提案</summary><pre>${JSON.stringify(item.original_payload, null, 2)}</pre></details>` : ''}
    ${resultView(item)}${pending ? html`<footer class="arv-decision"><p class="arv-muted">${s.dirty ? '有未保存的人工修订，请先保存。' : '确认前会重新核对权限、题目版本与影响范围。'}</p><div>
      ${button({ label: '拒绝', action: 'ai-review.reject', disabled: s.busy || unread })}
      ${s.editing ? button({ label: '保存修订', action: 'ai-review.save', loading: s.busy, disabled: !s.dirty }) : ''}
      ${button({ label: '确认执行', variant: 'primary', action: 'ai-review.approve', loading: s.busy, disabled: s.dirty || unread })}</div></footer>`
      : html`<p class="arv-muted" role="status">当前状态：${reviewStatus(item)}。${['approved', 'applying', 'running'].includes(item.status) ? '等待实际执行结果。' : '详情只读。'}</p>`}
  </article>`;
}
const time = value => value && Number.isFinite(new Date(value).getTime()) ? new Date(value).toLocaleString('zh-CN') : '—';
