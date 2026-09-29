/** 历史记录页模板：只产出转义的 html 结果。 */
import { html, each } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { empty } from '../../ui/empty.js';
import { skeleton } from '../../ui/skeleton.js';
import { status } from '../../ui/status.js';
import { historyCommitFamily, historyNodeTitle, historyNodeSubtitle, formatLedgerTime,
  historyNodeSessionId, historySourceLabel } from '../../domain/history.js';
import { historyPayloadPreview, restoreTarget, reviewVisual, timeline } from './state.js';

function reviewStrip(row, rs) {
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

function learningSummary(row) {
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

function node(row, env) {
  const family = historyCommitFamily(row.commit_type);
  const busy = env.s.busy.has(String(row.seq));
  return html`<article class="hvw-node" data-key="${row.commit_id || row.seq}" data-family="${family}" data-seq="${row.seq}">
    <span class="hvw-dot" aria-hidden="true"></span><div class="hvw-card">
      <div class="hvw-head" data-family="${family}"><div>
        <h3 class="hvw-title">${historyNodeTitle(row, env.rows.rs)}</h3>
        <p class="hvw-subtitle">${historyNodeSubtitle(row, env.rows.rs)}</p>
      </div></div>
      ${learningSummary({ ...row, detail: env.s.details.get(String(row.seq)) })}
      ${reviewStrip(row, env.rows.rs)}
      <p class="hvw-meta"><time class="hvw-time">${formatLedgerTime(row.created_at, env.zone) || 'GENESIS'}</time><span>${historySourceLabel(row.source)}</span></p>
      <div class="hvw-folds"><details class="hvw-details"><summary data-action="history.detail" data-arg="${row.seq}">查看详情</summary>${detailBody(row, env.s)}</details>${env.s.edit ? operations(row, busy, env.s.busy.size > 0) : ''}</div>
    </div>
  </article>`;
}

function correction(row, env) {
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

export function view(s, zone) {
  const rows = timeline(s);
  const env = { s, rows, zone };
  const loading = s.phase === 'loading' && !s.commits.length;
  const failed = s.phase === 'error' && !s.commits.length;
  return html`<section class="hvw" data-key="history-view">
    <header class="hvw-toolbar"><div><h2>Ledger 时间线</h2>
      <p>默认只读浏览；需要改历史时先开启「修正模式」，撤销/恢复/替换记录集中在「修正记录」。</p></div>
      <div class="hvw-tools"><label>排序<select class="hvw-input" id="history-sort" data-change="history.sort">
        <option value="asc"${s.sort === 'asc' ? ' selected' : ''}>旧 → 新（最新在底部）</option>
        <option value="desc"${s.sort === 'desc' ? ' selected' : ''}>新 → 旧（最新在顶部）</option>
      </select></label>
      ${button({ label: `修正模式：${s.edit ? '开' : '关'}`, size: 'sm', variant: s.edit ? 'primary' : 'default', action: 'history.mode', pressed: s.edit })}
      ${button({ label: `修正记录 ${rows.corrections.length}`, size: 'sm', action: 'history.corrections', pressed: s.correctionsOpen })}
      ${button({ label: '刷新', size: 'sm', icon: 'refresh', action: 'history.refresh' })}</div></header>
    ${s.error && s.commits.length ? status({ tone: 'danger', text: `历史刷新失败：${s.error}` }) : ''}
    ${s.writeError ? status({ tone: 'danger', text: s.writeError }) : ''}
    ${s.note ? status({ tone: 'success', text: s.note }) : ''}
    ${s.correctionsOpen ? html`<section class="hvw-corrections" id="history-corrections" aria-label="修正记录">
      ${rows.corrections.length ? each(rows.corrections, row => `correction-${row.commit_id || row.seq}`, row => correction(row, env))
        : empty({ icon: 'clock', title: '暂无修正记录', hint: '撤销、恢复或修改反馈后，这里会出现对应的 Ledger 记录。', compact: true })}
    </section>` : ''}
    <div class="hvw-timeline" id="history-timeline" aria-label="Ledger 主时间线">
      ${loading ? skeleton({ lines: 5 }) : failed ? empty({ icon: 'alert-circle', title: '历史加载失败', hint: s.error || '检查服务后重试。', action: { label: '重试', action: 'history.refresh' } })
        : rows.main.length ? each(rows.main, row => row.commit_id || row.seq, row => node(row, env))
          : empty({ icon: 'clock', title: '暂无主时间线节点', hint: '当前没有可显示的历史；可刷新或查看修正记录。', action: { label: '刷新', action: 'history.refresh' } })}
    </div>
    ${s.hasMore ? html`<div class="hvw-more">${button({ label: s.loadingMore ? '加载中…' : '加载更早记录', size: 'sm', action: 'history.more', disabled: s.loadingMore })}</div>` : ''}
    <p class="hvw-summary" id="history-status" role="status">主时间线 ${rows.main.length} 个节点${rows.hidden ? `（${rows.hidden} 个已撤销已隐藏）` : ''}；修正记录 ${rows.corrections.length} 条</p>
  </section>`;
}
