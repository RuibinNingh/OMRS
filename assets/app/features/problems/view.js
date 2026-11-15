/** 问题页：桌面列表和详情，手机逐层查看。 */
import { html, raw } from '../../core/html.js';
import { statuses, markdown } from '../../domain/problems.js';
const date = t => new Date(t * 1000).toLocaleString('zh-CN');
export function view(s) {
  const p = s.detail;
  return html`<div class="prb-page ${p ? 'has-detail' : ''}">
    <aside class="prb-list" aria-label="问题列表">
      <header class="prb-head"><div><h2>问题</h2><p>从一次错因，找到可验证的改善。</p></div><button class="ui-btn ui-btn--primary" data-prb="new">＋ 新建问题</button></header>
      <label>搜索问题<input class="ui-input" data-prb-field="query" value="${s.query}" placeholder="搜索标题或描述"></label>
      <label>状态<select class="ui-select" data-prb-field="filter"><option value="">全部状态</option>${Object.entries(statuses).map(([key,label]) => html`<option value="${key}" ${raw(s.filter === key ? 'selected' : '')}>${label}</option>`)}</select></label>
      <p class="prb-muted">${s.total} 个问题 · 按最近更新</p>
      <div class="prb-items">${s.items.map(p => html`<button class="prb-row ${s.detail?.id === p.id ? 'is-selected' : ''}" data-prb="open" data-id="${p.id}"><span class="prb-status">${statuses[p.status]}</span><strong>${p.title}</strong><small>${p.question_count} 道关联题 · ${date(p.updated_at)}</small></button>`)}</div>
      ${s.next ? html`<button class="ui-btn" data-prb="more">加载更多</button>` : ''}
      ${!s.items.length ? html`<p>先记下一个想改善的问题，也可以暂不关联题目。</p>` : ''}
    </aside>
    <section class="prb-detail" aria-label="问题详情">
      ${p ? html`<header class="prb-head"><button class="ui-btn prb-back" data-prb="back">← 返回列表</button><span class="prb-status">${p.basis === 'ai_hypothesis' ? 'AI 假设 · 待用户确认' : '用户确认的观察'}</span><button class="ui-btn" data-prb="edit">${s.editing ? '查看预览' : '编辑描述'}</button></header>
      ${s.editing ? html`<label>标题<input class="ui-input" data-prb-field="title" value="${p.title}" maxlength="160"></label><label>描述（Markdown）<textarea class="ui-textarea prb-editor" data-prb-field="description_md" rows="9">${p.description_md}</textarea></label><label>添加图片或静态 SVG<input class="ui-input" type="file" accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml" data-prb-upload></label>` : html`<h1>${p.title}</h1><div class="q-md prb-markdown">${raw(markdown(p.description_md || '尚未填写描述。'))}</div>`}
      <div class="prb-state"><label>问题状态<select class="ui-select" data-prb-field="status">${Object.entries(statuses).map(([key,label]) => html`<option value="${key}" ${raw(p.status === key ? 'selected' : '')}>${label}</option>`)}</select></label><label>变更理由<input class="ui-input" data-prb-field="reason" value="${s.reason}" placeholder="状态变更或重新开启的依据"></label><button class="ui-btn ui-btn--primary" data-prb="save" ${raw(s.busy ? 'disabled' : '')}>${s.busy ? '保存中…' : '保存问题'}</button>${p.basis === 'ai_hypothesis' ? html`<button class="ui-btn" data-prb="confirm">确认观察依据</button>` : ''}</div>
      <section class="prb-section"><header class="prb-head"><h3>关联题目 · ${p.questions?.length || 0}</h3><button class="ui-btn ui-btn--sm" data-prb="picker">＋ 关联题目</button></header><div class="prb-linked">${(p.questions || []).map(q => html`<div class="prb-question"><button class="ui-btn ui-btn--ghost" data-prb="question" data-id="${q.question_id}" ${raw(q.available ? '' : 'disabled')}>${q.uid} <small>${q.question_id}${q.available ? '' : ' · 已归档或不可用'}</small></button><button class="ui-btn ui-btn--ghost ui-btn--sm" data-prb="unlink" data-id="${q.question_id}" aria-label="移除关联 ${q.uid}">移除</button></div>`)}</div>
      ${s.picker ? html`<div class="prb-picker"><label>查找题目<input class="ui-input" data-prb-field="questionQuery" value="${s.questionQuery}" placeholder="UID、学科或题干"></label>${s.questions.filter(q => `${q.uid} ${q.subject} ${q.question || ''}`.includes(s.questionQuery)).slice(0,100).map(q => html`<label class="prb-choice"><input type="checkbox" data-prb-qid="${q.question_id}" ${raw(s.selected.has(q.question_id) ? 'checked' : '')}>${q.uid} · ${q.subject} <small>${q.question_id}</small></label>`)}<button class="ui-btn" data-prb="link">关联选中的题目</button></div>` : ''}</section>
      <section class="prb-section"><h3>错因与处理时间线</h3>${(p.entries || []).map(e => html`<article class="prb-event"><small>${date(e.created_at)} · ${e.basis === 'ai_hypothesis' ? 'AI 假设' : '用户记录'}${e.recurrence_of ? ' · 再次发生' : ''}</small><div class="q-md">${e.withdrawn ? '记录已撤回（保留修订痕迹）' : raw(markdown(e.content_md))}</div></article>`)}${(p.events || []).map(e => html`<article class="prb-event"><small>${date(e.at)} · ${e.action === 'create_problem' ? '创建问题' : '更新问题'} · ${e.actor.kind === 'web' ? '用户' : 'AI'}</small><p>${e.reason || statuses[e.value.status] || '更新关联材料'}</p></article>`)}</section>` : html`<div class="prb-empty"><h2>把反复出现的困难，变成具体问题</h2><p>记录现象、应对办法和验证标准。问题状态独立于题目熟练度。</p><button class="ui-btn ui-btn--primary" data-prb="new">新建第一个问题</button></div>`}
    </section><p class="prb-message" role="status">${s.message}</p></div>`;
}
