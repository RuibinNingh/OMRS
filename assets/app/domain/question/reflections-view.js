/** 错因区模板：录入与历史互斥显示，正文优先、辅助信息按需展开。 */
import { html, raw } from '../../core/html.js';
import { tabs } from '../../ui/tabs.js';
import { markdown } from '../problems.js';

export function draftLabel(state, draft) {
  return state.revision ? '正在修订' : draft.dirty() ? '未保存' : '尚未填写';
}

function entryView(entry, state) {
  const recorded = entry.created_at ? new Date(entry.created_at * 1000).toLocaleString('zh-CN') : '';
  return html`<article class="ref-entry" data-key="${entry.id}">
    <p class="ref-note">${entry.occurred_at ? `发生日期：${entry.occurred_at}` : recorded ? `记录于 ${recorded}` : '发生日期未知'}</p>
    ${entry.basis === 'ai_hypothesis' ? html`<p class="ref-hypothesis">AI 假设 · 待确认依据</p>` : ''}
    ${entry.recurrence_of ? html`<p class="ref-note">再次发生</p>` : ''}
    <div class="q-md">${entry.withdrawn ? '此记录已撤回，修订痕迹已保留。' : raw(markdown(entry.content_md))}</div>
    <details class="ref-entry__details" data-ref-entry-details="${entry.id}" ${raw(state.expanded.has(entry.id) ? 'open' : '')}>
      <summary>${recorded ? `记录时间：${recorded}` : '原有记录'} · 详情与操作</summary>
      <p class="ref-note">${entry.basis === 'ai_hypothesis' ? 'AI 假设' : '用户记录'} · 第 ${entry.revision} 版 · 发生日期：${entry.occurred_at || '未知'}</p>
      ${entry.revision > 1 ? html`<details data-ref-revisions="${entry.id}" ${raw(state.revisions.has(entry.id) ? 'open' : '')}><summary>查看修订痕迹</summary>${(entry.revisions || []).map(r => html`<p class="ref-note">第 ${r.value.revision} 版 · ${r.reason || '初次记录'}</p><div class="q-md">${raw(markdown(r.value.content_md))}</div>`)}</details>` : ''}
      ${!entry.withdrawn ? html`<div class="ref-actions">
        ${entry.basis === 'ai_hypothesis' ? html`<button class="ui-btn ui-btn--ghost ui-btn--sm" data-ref="confirm" data-id="${entry.id}">确认错因依据</button>` : ''}
        <button class="ui-btn ui-btn--ghost ui-btn--sm" data-ref="recurrence" data-id="${entry.id}">再次发生</button>
        <button class="ui-btn ui-btn--ghost ui-btn--sm" data-ref="revise" data-id="${entry.id}">修订</button>
        <button class="ui-btn ui-btn--ghost ui-btn--sm" data-ref="withdraw" data-id="${entry.id}">撤回</button>
      </div>` : ''}
    </details>
  </article>`;
}

export function reflectionsView(state, draft) {
  const d = draft.value;
  const prefix = state.idPrefix || `ref-${d.question_id}`;
  return html`<section class="reflections" aria-label="快捷错因与记录">
    <div class="ref-head"><strong>错因记录 · ${state.entries.length} 条</strong></div>
    ${tabs({ label: '错因记录', idPrefix: prefix, value: state.tab, items: [
      { id: 'history', label: '历史记录', badge: state.entries.length, panel: `${prefix}-history-panel`, disabled: state.busy },
      { id: 'new', label: '记录本次', panel: `${prefix}-editor`, disabled: state.busy },
    ] })}
    <div id="${prefix}-editor" role="tabpanel" aria-labelledby="${prefix}-new" data-ref-panel="new" ${raw(state.tab !== 'new' ? 'hidden' : '')}>
      <fieldset class="ref-form" ${raw(state.busy ? 'disabled' : '')}>
        <div class="ref-editor__head"><label for="${prefix}-content">本次错在哪里？</label><small data-ref-draft>${draftLabel(state, draft)}</small></div>
        <textarea id="${prefix}-content" class="ui-textarea" rows="4" data-ref-input="content_md" placeholder="记下卡住的一步，以及下次怎么检查。">${d.content_md}</textarea>
        ${d.recurrence_of ? html`<p class="ref-note">再次发生：引用已有错因，保存后新增一条记录。</p>` : ''}
        <details class="ref-disclosure" data-ref-disclosure="association" ${raw(state.association ? 'open' : '')}>
          <summary>关联问题（可不选）</summary>
          <label>搜索已有问题<input class="ui-input" data-ref-search value="${state.search}" placeholder="按问题标题搜索"></label>
          <div class="ref-choices">${state.problems.filter(p => p.title.includes(state.search)).map(p => html`<label class="ref-choice"><input type="checkbox" data-ref-problem="${p.id}" ${raw(d.problem_ids.includes(p.id) ? 'checked' : '')}>${p.title}</label>`)}</div>
        </details>
        <details class="ref-disclosure" data-ref-disclosure="more" ${raw(state.more ? 'open' : '')}>
          <summary>更多信息</summary>
          <label>发生日期（未知可留空）<input class="ui-input" type="date" data-ref-input="occurred_at" value="${d.occurred_at}"></label>
          <label>图片或静态 SVG<input class="ui-input" type="file" accept="image/*" data-ref-file></label>
          <button class="ui-btn ui-btn--sm" data-ref="newProblem">以此新建问题</button>
        </details>
        <div class="ref-save"><button class="ui-btn ui-btn--primary ui-btn--sm" data-ref="save" ${raw(state.busy ? 'disabled' : '')}>${state.busy ? '保存中…' : state.revision ? '保存修订' : '保存错因'}</button><small>Ctrl / ⌘ + Enter 保存</small></div>
      </fieldset>
    </div>
    <div id="${prefix}-history-panel" role="tabpanel" aria-labelledby="${prefix}-history" data-ref-panel="history" ${raw(state.tab !== 'history' ? 'hidden' : '')}>
      <div class="ref-timeline">${state.entries.map(entry => entryView(entry, state))}</div>
      ${!state.entries.length ? html`<p class="ref-empty">${state.loading ? '正在读取记录…' : '还没有错因记录，可以先记下这次的观察。'}</p>` : ''}
    </div>
    <p class="ref-message" role="status" aria-live="polite">${state.message}</p>
  </section>`;
}
