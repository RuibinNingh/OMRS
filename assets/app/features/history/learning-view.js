/** 历史记录页模板：只产出转义的 html 结果。 */
import { html } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { historyCommitFamily, historyNodeTitle, historyNodeSubtitle, formatLedgerTime,
  historyNodeSessionId, historySourceLabel } from '../../domain/history.js';
import { historyPayloadPreview, restoreTarget, reviewVisual } from './state.js';

export function reviewStrip(row, rs) {
  const model = reviewVisual(row, rs);
  if (!model) return '';
  const ok = model.correctPct;
  return html`<div class="hvw-review" aria-label="${model.correct} 对，${model.wrong} 错">
    <svg class="hvw-ratio" viewBox="0 0 100 6" preserveAspectRatio="none" aria-hidden="true">
      <rect class="hvw-ratio__ok" x="0" y="0" width="${ok}" height="6"></rect>
      <rect class="hvw-ratio__no" x="${ok}" y="0" width="${100 - ok}" height="6"></rect>
    </svg>
    <span class="hvw-marks">${model.marks.map(mark => html`<span class="hvw-mark" data-result="${mark}" aria-label="${mark === 'ok' ? '答对' : mark === 'no' ? '答错' : '已撤销'}"></span>`)}</span>
  </div>`;
}

function reviewOps(row, busy, writing) {
  const feedbacks = row.payload?.feedbacks;
  if (!Array.isArray(feedbacks) || !feedbacks.length) return '';
  const first = feedbacks[0];
  const seq = row.seq;
  return html`<div class="hvw-review-ops"><strong>反馈修正</strong>
    <div class="hvw-review-grid">
      <label>反馈条目<select class="hvw-input" id="hist-review-index-${seq}">${feedbacks.map((fb, index) => html`<option value="${index}">#${index + 1} ${fb.uid_at_that_time || fb.uid || fb.question_id || ''}</option>`)}</select></label>
      <label>主观分<input class="hvw-input" id="hist-review-score-${seq}" type="number" min="0" max="10" value="${first.sub_score ?? 5}"></label>
      <label>结果<select class="hvw-input" id="hist-review-correct-${seq}"><option value="true"${first.is_correct ? ' selected' : ''}>答对</option><option value="false"${first.is_correct ? '' : ' selected'}>答错</option></select></label>
      <label>备注<input class="hvw-input" id="hist-review-note-${seq}" placeholder="备注"></label>
      <label>原因<input class="hvw-input" id="hist-review-reason-${seq}" placeholder="原因"></label>
    </div>
    <div class="hvw-actions">
      ${button({ label: '修改反馈', size: 'sm', action: 'history.review', arg: `${seq}:replace`, loading: busy, disabled: writing })}
      ${button({ label: '撤销反馈', size: 'sm', variant: 'danger', action: 'history.review', arg: `${seq}:retract`, loading: busy, disabled: writing })}
      ${button({ label: '恢复反馈', size: 'sm', action: 'history.review', arg: `${seq}:restore`, loading: busy, disabled: writing })}
    </div>
  </div>`;
}

function operations(row, busy, writing) {
  const sid = historyNodeSessionId(row);
  if (row.seq <= 1 && !sid && !row.payload?.feedbacks?.length) return '';
  return html`<details class="hvw-ops"><summary>修改 / 撤销 / 还原</summary>
    <div class="hvw-ops__body">${reviewOps(row, busy, writing)}
      ${sid ? html`<div class="hvw-operation"><span>Session <strong>${sid}</strong></span>
        ${button({ label: '撤销整次 Session', size: 'sm', variant: 'danger', action: 'history.session', arg: `${row.seq}:retract`, loading: busy, disabled: writing })}
        ${button({ label: '恢复 Session', size: 'sm', action: 'history.session', arg: `${row.seq}:restore`, loading: busy, disabled: writing })}
      </div>` : ''}
      ${row.seq > 1 ? html`<div class="hvw-operation"><label>状态还原原因<input class="hvw-input" id="hist-restore-reason-${row.seq}" placeholder="还原原因"></label>
        ${button({ label: '还原到此节点', size: 'sm', action: 'history.restoreState', arg: String(row.seq), loading: busy, disabled: writing })}</div>` : ''}
    </div>
  </details>`;
}

export function learningSummary(row) {
  const learning = row.learning || {};
  if (row.commit_type === 'review.batch_submit') {
    const subjects = Object.entries(learning.subjects || {}).map(([name, count]) => `${name} ${count} 题`).join('、');
    const examples = (learning.questions || []).slice(0, 3).join('；');
    return html`<div class="hvw-learning"><p>${subjects || '科目无可用历史摘要'}</p>
      <p>${examples || '题面无可用历史摘要'}</p></div>`;
  }
  if (row.commit_type === 'question.move' || row.commit_type === 'question.move_external') {
    return html`<p class="hvw-learning">分类：${learning.from_category || '无可用历史摘要'} → ${learning.to_category || '无可用历史摘要'}</p>`;
  }
  const fields = Object.entries(learning.fields || {});
  if (fields.length) return html`<div class="hvw-learning">${fields.map(([key, values]) => html`<p>${key}：${String(values[0])} → ${String(values[1])}</p>`)}</div>`;
  if (row.commit_type === 'question.content_update' || row.commit_type.startsWith('question.metadata_update')) {
    return html`<p class="hvw-learning">正文变化：${contentChangeText(row)}</p>`;
  }
  return '';
}

function contentChangeText(row) {
  const change = row.learning?.change || row.detail?.content_change;
  if (!change?.available) return '无可用历史摘要';
  return change.sections.map(item => `${item.section}：${item.before || '空'} → ${item.after || '空'}`).join('；');
}

function detailBody(row, s) {
  const detail = s.details.get(String(row.seq));
  const error = s.detailErrors.get(String(row.seq));
  if (error) return html`<p class="hvw-detail-error">详情读取失败：${error}</p>`;
  if (!detail) return html`<p>正在读取详情…</p>`;
  const full = { ...row, payload: detail.payload, detail };
  const reviews = row.commit_type === 'review.batch_submit' ? detail.payload?.feedbacks || [] : [];
  return html`${reviews.length ? html`<ol class="hvw-review-items">${reviews.map(item => html`<li>
    ${item.uid_at_that_time || item.uid || ''} · ${item.question_summary || '无可用历史摘要'} · ${item.is_correct ? '答对' : '答错'} · ${item.sub_score == null ? '无分数' : `${item.sub_score} 分`}
  </li>`)}</ol>` : ''}
    ${detail.content_change ? html`<p class="hvw-learning">${contentChangeText(full)}</p>` : ''}
    <p class="hvw-meta">${detail.commit_type} · ${detail.commit_id} · seq ${detail.seq}</p>
    <pre>${historyPayloadPreview(full)}</pre>`;
}

export function correction(row, env) {
  const p = row.payload || {};
  const target = p.target_seq ? `目标 seq ${p.target_seq}` : p.session_id ? `Session ${p.session_id}`
    : p.target_commit_id ? `目标 ${p.target_commit_id}` : '';
  const restore = restoreTarget(row, env.rows.rs);
  return html`<article class="hvw-correction" data-key="correction-${row.commit_id || row.seq}">
    <div class="hvw-correction__head"><div><h3>${row.summary || row.message || row.commit_type}</h3>
      <p class="hvw-meta"><span>${formatLedgerTime(row.created_at, env.zone)}</span><span>${historySourceLabel(row.source)}</span><span>${target}</span></p></div>
      ${restore && env.s.edit ? button({ label: '恢复', size: 'sm', action: 'history.directRestore', arg: String(row.seq), loading: env.s.busy.has(String(row.seq)), disabled: env.s.busy.size > 0 }) : ''}
    </div>
    <details class="hvw-details"><summary data-action="history.detail" data-arg="${row.seq}">查看记录</summary>${detailBody(row, env.s)}</details>
    ${p.reason ? html`<p class="hvw-reason">${p.reason}</p>` : ''}
  </article>`;
}

export function learningPanel(row, s, rs, zone) {
  if (!row) return html`<p class="hvw-panel-empty">选择一条记录，查看内容与结果。</p>`;
  const full = s.details.get(String(row.seq));
  const error = s.detailErrors.get(String(row.seq));
  const calls = full?.runtime_calls || [];
  const draftId = row.payload?.source_draft_id || full?.payload?._draft?.draft_id;
  return html`<div class="hvw-panel-content">
    <h3 class="hvw-title">${historyNodeTitle(row, rs)}</h3>
    <p class="hvw-subtitle">${historyNodeSubtitle(row, rs)}</p>
    ${learningSummary({ ...row, detail: full })}${reviewStrip(row, rs)}
    <p class="hvw-meta"><time>${formatLedgerTime(row.created_at, zone) || '初始化节点'}</time><span>${historySourceLabel(row.source)}</span></p>
    ${error ? html`<p class="hvw-detail-error">详情读取失败：${error}</p>${button({ label: '重试详情', size: 'sm', action: 'history.detail', arg: String(row.seq) })}` : ''}
    ${draftId ? html`<section class="hvw-related"><h4>来源调用</h4>${full?.runtime_calls_error ? html`<p class="hvw-detail-error">${full.runtime_calls_error}</p>` : calls.length ? calls.map(call => button({ label: `${call.title} · ${call.key_name || '未命名密钥'}`, iconRight: 'arrow-right', action: 'history.runtimeRelated', arg: String(call.seq), size: 'sm' })) : html`<p class="hvw-muted">${full ? '暂无可追溯的 MCP 调用记录。' : '正在读取来源调用…'}</p>`}</section>` : ''}
    <details class="hvw-details"><summary>逐题与技术详情</summary>${detailBody(row, s)}</details>
    ${s.edit ? operations({ ...row, payload: full?.payload || row.payload }, s.busy.has(String(row.seq)), s.busy.size > 0) : ''}
  </div>`;
}
