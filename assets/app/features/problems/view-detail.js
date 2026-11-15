/** 问题详情与编辑器，材料与时间线保持原领域契约。 */
import { html, raw } from '../../core/html.js';
import { icon } from '../../ui/icon.js';
import { statuses, markdown } from '../../domain/problems.js';

const disabled = v => raw(v ? 'disabled' : '');
const date = t => t ? new Date(t * 1000).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
const eventNames = { create_problem: '创建问题', update_problem: '更新问题', link_problem_questions: '关联题目', unlink_problem_questions: '移除关联', reflection_link: '错因关联题目', trash_problem: '移入回收站', restore_problem: '恢复问题' };

function materials(s, p) {
  const linked = new Set((p.questions || []).map(q => q.question_id));
  const choices = s.questions.filter(q => !linked.has(q.question_id) && `${q.uid} ${q.subject} ${q.question || ''}`.toLocaleLowerCase().includes(s.questionQuery.toLocaleLowerCase()));
  return html`<section class="prb-section"><header class="prb-head"><h3>${icon('link')}关联题目 <span>${p.questions?.length || 0}</span></h3>${!p.deleted_at ? html`<button class="ui-btn ui-btn--ghost ui-btn--sm" data-prb="picker" ${disabled(s.busy)}>${icon('plus')}关联题目</button>` : ''}</header>
    <div class="prb-linked">${(p.questions || []).map(q => html`<div class="prb-question" data-key="${q.question_id}"><button class="ui-btn ui-btn--ghost" data-prb="question" data-id="${q.question_id}" ${disabled(!q.available || s.busy)}>${q.uid}<small>${q.available ? '查看题目' : '已归档或不可用'}</small></button>${!p.deleted_at ? html`<button class="ui-btn ui-btn--ghost ui-btn--sm" data-prb="unlink" data-id="${q.question_id}" aria-label="移除关联 ${q.uid}" ${disabled(s.busy)}>移除</button>` : ''}</div>`)}</div>
    ${!p.questions?.length ? html`<p class="prb-muted">还没有关联题目，可以先整理问题，再补充材料。</p>` : ''}
    ${s.picker ? html`<div class="prb-picker"><label>查找题目<input class="ui-input" data-prb-field="questionQuery" value="${s.questionQuery}" placeholder="UID、学科或题干"></label><div class="prb-picker-items">${choices.slice(0, 100).map(q => html`<label class="prb-choice" data-key="${q.question_id}"><input type="checkbox" data-prb-qid="${q.question_id}" ${raw(s.selected.has(q.question_id) ? 'checked' : '')} ${disabled(s.selected.size >= 100 && !s.selected.has(q.question_id))}>${q.uid} · ${q.subject}</label>`)}${!choices.length ? html`<p class="prb-muted">没有匹配的可关联题目</p>` : ''}</div><button class="ui-btn" data-prb="link" ${disabled(!s.selected.size || s.busy)}>关联选中的 ${s.selected.size} 道题</button></div>` : ''}</section>`;
}
function timeline(p) {
  const records = [...(p.entries || []).map(e => ({ ...e, at: e.created_at, reflection: true })), ...(p.events || [])].sort((a, b) => b.at - a.at);
  return html`<details class="prb-section prb-timeline"><summary>错因与处理时间线 <span>${records.length}</span></summary>${records.map(e => html`<article class="prb-event"><small>${date(e.at)} · ${e.reflection ? e.basis === 'ai_hypothesis' ? 'AI 假设' : '用户记录' : eventNames[e.action] || '更新问题'}${e.recurrence_of ? ' · 再次发生' : ''}</small>${e.reflection ? html`<div class="q-md">${e.withdrawn ? '记录已撤回（保留修订痕迹）' : raw(markdown(e.content_md))}</div>` : html`<p>${e.reason || statuses[e.value?.status] || '更新关联材料'}</p>`}</article>`)}</details>`;
}
export function detailView(s) {
  const p = s.draft || s.detail;
  if (!p) return html`<section class="prb-detail"><header class="prb-detail-head"><span>正在读取详情…</span><button class="ui-btn ui-btn--ghost" data-prb="back">返回列表</button></header></section>`;
  const dirty = s.creating || s.reason || ['title', 'description_md', 'status'].some(k => p[k] !== s.detail[k]);
  return html`<section class="prb-detail ${s.opening ? 'is-loading' : ''}" aria-label="问题详情" aria-busy="${s.opening ? 'true' : 'false'}">
    <header class="prb-detail-head"><button class="ui-btn ui-btn--ghost ui-btn--sm prb-back" data-prb="back" ${disabled(s.busy)}>${icon('arrow-left')}返回列表</button><span>${s.creating ? '新建问题' : '问题详情'}</span><div>${!s.creating && !p.deleted_at ? html`<button class="ui-btn ui-btn--ghost ui-btn--icon" data-prb="trash" data-id="${p.id}" aria-label="删除此问题" ${disabled(s.busy || s.opening)}>${icon('trash')}</button>` : ''}<button class="ui-btn ui-btn--ghost ui-btn--icon prb-close" data-prb="back" aria-label="关闭详情" ${disabled(s.busy)}>${icon('x')}</button></div></header>
    <div class="prb-detail-scroll" data-key="detail-${p.id}">
    ${p.deleted_at ? html`<div class="prb-trash-note">${icon('trash')}<div><strong>此问题在回收站中</strong><p>恢复后可以继续编辑和跟进。</p></div><button class="ui-btn" data-prb="restore" data-id="${p.id}" ${disabled(s.busy)}>恢复</button></div>` : ''}
    <div class="prb-detail-meta"><span class="prb-status" data-status="${p.status}"><span class="prb-dot"></span>${statuses[p.status]}</span><span>${p.basis === 'ai_hypothesis' ? 'AI 假设 · 待确认' : '用户确认的观察'}</span></div>
    ${s.editing ? html`<label>问题标题<input class="ui-input prb-title-input" data-prb-field="title" value="${p.title}" maxlength="160" placeholder="用一句话描述你想解决的问题" ${disabled(s.busy)}></label><label>问题说明 <small>支持 Markdown、公式和图片</small><textarea class="ui-textarea prb-editor" data-prb-field="description_md" rows="10" ${disabled(s.busy)}>${p.description_md}</textarea></label><label class="prb-upload">添加图片或静态 SVG<input class="ui-input" type="file" accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml" data-prb-upload ${disabled(s.busy)}></label>` : html`<div class="prb-title"><h1>${p.title || '未命名的问题'}</h1>${!p.deleted_at ? html`<button class="ui-btn ui-btn--ghost ui-btn--sm" data-prb="edit" ${disabled(s.busy)}>${icon('edit')}编辑描述</button>` : ''}</div><div class="q-md prb-markdown">${raw(markdown(p.description_md || '尚未填写描述。'))}</div>`}
    ${!p.deleted_at ? html`<div class="prb-state"><label>问题状态<select class="ui-select" data-prb-field="status" ${disabled(s.busy)}>${Object.entries(statuses).map(([key, label]) => html`<option value="${key}" ${raw(p.status === key ? 'selected' : '')}>${label}</option>`)}</select></label>${!s.creating ? html`<label>变更依据<input class="ui-input" data-prb-field="reason" value="${s.reason}" maxlength="1000" placeholder="切换状态时填写" ${disabled(s.busy)}></label>` : ''}</div>` : ''}
    ${!s.creating ? html`${materials(s, p)}${timeline(p)}<p class="prb-detail-footnote">创建于 ${date(p.created_at)} · 更新于 ${date(p.updated_at)}</p>` : html`<p class="prb-muted">保存问题后，可以关联题目并查看处理记录。</p>`}
    </div>
    ${!p.deleted_at ? html`<footer class="prb-savebar"><span data-prb-dirty>${s.uploading ? '附件上传中，请稍候…' : dirty ? '有未保存的修改' : '所有修改已保存'}</span><div>${s.editing ? html`<button class="ui-btn ui-btn--ghost" data-prb="cancel" ${disabled(s.busy)}>取消编辑</button><button class="ui-btn" data-prb="edit" ${disabled(s.busy)}>查看预览</button>` : ''}${p.basis === 'ai_hypothesis' ? html`<button class="ui-btn" data-prb="confirm" ${disabled(s.busy)}>确认观察依据</button>` : ''}<button class="ui-btn ui-btn--primary" data-prb="save" ${disabled(s.busy || s.opening || s.uploading)}>${s.busy ? '保存中…' : '保存问题'}</button></div></footer>` : ''}
    </section>`;
}
