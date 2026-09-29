/**
 * 每个工具怎么给人看：标题、参数摘要、结果预览、内联确认卡、确认对话框正文。名字给模型，这里的字给人。
 * 结果形状以 omrs/agent/tools/*.py 的返回为准；确认对话框的「现在 / 修改后 / 预计熟练度」来自服务端 tool.waiting 的 preview。
 * 条形图一律用 SVG 属性画（模板不写 style=，check_ui R6）。
 */
import { html, raw } from '../../core/html.js';
import { icon } from '../../ui/icon.js';
import { labelChips } from '../../domain/labels/index.js';
import { renderInline } from './md.js';
import { clamp, hhmm, pct } from './state.js';
import { detectCardState } from './draft-cards.js';

let refHtml = uid => `<code>${uid}</code>`;
/** index.js 注入：知道哪些 UID 在题库里、到期状态如何。 */
export function setRefRenderer(fn) { refHtml = fn; }
export const refOf = code => refHtml(code);
export const ref = uid => raw(refHtml(uid));
export const md = text => raw(renderInline(text, refHtml));

export const bar = (p, warn = false) => {
  const w = Math.round(clamp(p || 0, 0, 1) * 100);
  return raw(`<svg class="ast-bar${warn ? ' is-warn' : ''}" viewBox="0 0 100 4" preserveAspectRatio="none" aria-hidden="true"><rect class="ast-bar__t" width="100" height="4"/><rect class="ast-bar__v" width="${w}" height="4"/></svg>`);
};
const mBar = m => (m == null ? html`<span class="ast-list__m">新题</span>` : html`<span class="ast-list__m">${bar(m, m < 0.3)}${pct(m)}</span>`);
const streak = recs => raw(`<svg class="ast-streak" viewBox="0 0 ${Math.max(1, recs.length) * 5} 14" aria-hidden="true">${recs.map((r, i) => {
  const h = 3 + Math.round(clamp(Number(r.score) || 0, 0, 10));
  return `<rect class="${r.correct ? 'ok' : ''}" x="${i * 5}" y="${14 - h}" width="3" height="${h}"/>`;
}).join('')}</svg>`);

export const LVL = { read: ['只读', 'eye'], rev: ['可撤销', 'undo'], confirm: ['需确认', 'lock'], none: ['不提供', 'x'] };
export const lvl = (k, text) => html`<span class="ast-lvl ast-lvl--${k}">${icon(LVL[k][1])}${text || LVL[k][0]}</span>`;
const ovCell = (k, v, s) => html`<div class="ast-ov__c"><div class="ast-ov__k">${k}</div><div class="ast-ov__v">${v}${s ? html`<small>${s}</small>` : ''}</div></div>`;
const liRec = x => html`<li class="ast-list__i">${ref(x.uid)}<span class="ast-list__why">${x.why}</span>${mBar(x.mastery)}</li>`;
const note = text => html`<p class="ast-note">${text}</p>`;
const box = (text, after = false) => html`<div class="ast-diff__box${after ? ' is-after' : ''}${text ? '' : ' is-empty'}">${text ? md(text) : html`<span class="ast-diff__none">（空）</span>`}</div>`;
const diff = (a, b, h1 = '之前', h2 = '之后') => html`<div class="ast-diff"><div><h4>${h1}</h4>${box(a)}</div><div><h4>${h2}</h4>${box(b, true)}</div></div>`;
const sessRef = id => html`<button type="button" class="ast-ref" data-action="assistant.openSession" data-arg="${id}">${icon('calendar')}${id}</button>`;

const T = {
  get_overview: {
    title: '看概况', icon: 'chart', args: a => a.subject || '全部科目',
    preview: r => html`<div class="ast-ov">${ovCell('题目', r.total, `停用 ${r.suspended}`)}${ovCell('待复习', r.overdue + r.due_today, `逾期 ${r.overdue}`)}${ovCell('顽固', r.leech, '连错 ≥3')}${ovCell('已击杀', r.killed, '')}</div>
      <div class="ast-weak">${(r.weakest || []).map(w => html`<span>${w.path}</span>${bar(w.avg, w.avg < 0.35)}<b>${pct(w.avg)}</b>`)}</div>
      ${note('按分类平均熟练度从低到高，未练过的新题不计入。')}`,
  },
  get_recommendations: {
    title: '取推荐', icon: 'target', args: a => `${a.count || 8} 道以内${a.subject ? '，' + a.subject : ''}`,
    preview: r => html`<div class="ast-cols"><div><h5>到期列表 ${r.due.length}</h5><ul class="ast-list">${r.due.map(liRec)}</ul></div><div><h5>熟练度列表 ${r.proficiency.length}</h5><ul class="ast-list">${r.proficiency.map(liRec)}</ul></div></div>
      ${note('两个列表互斥分配，进行中的 Session 里的题已排除。')}`,
  },
  search_questions: {
    title: '搜题', icon: 'search',
    args: a => [a.keywords?.length && `「${a.keywords.join(' ')}」`, a.subject, a.category, a.knowledge_point, a.label, a.status,
      a.mastery_max != null && `熟练度 < ${Math.round(a.mastery_max * 100)}%`, a.mastery_min != null && `熟练度 ≥ ${Math.round(a.mastery_min * 100)}%`].filter(Boolean).join('，') || '全部',
    preview: r => html`${r.total ? html`<ul class="ast-list">${r.items.map(it => html`<li class="ast-list__i">${ref(it.uid)}<span class="ast-list__why ast-snip">${md(it.snippet)}</span>${mBar(it.mastery)}</li>`)}</ul>` : note('没有命中。')}
      ${r.pages > 1 ? note(`第 ${r.page} / ${r.pages} 页，共 ${r.total} 题。`) : ''}${r.image_only ? note(`筛选范围内另有 ${r.image_only} 道纯图片题，正文没有文字，关键词搜不到。`) : ''}`,
  },
  get_question: {
    title: '读题目', icon: 'file', args: a => a.uid,
    preview: r => html`<div class="ast-snip">${md(r.sections['题目'])}</div>
      <dl class="ast-kv"><dt>错因</dt><dd>${r.sections['错因'] ? md(r.sections['错因']) : '（空）'}</dd>
      <dt>最近记录</dt><dd>${r.records.length ? html`${streak(r.records)} ${r.records.map(x => `${x.correct ? '对' : '错'} ${x.score} 分`).join('，')}` : '还没有练过'}</dd>
      <dt>熟练度</dt><dd>${pct(r.mastery)}，${r.due}</dd></dl>`,
  },
  get_session: {
    title: '查 Session', icon: 'calendar', args: a => a.session_id,
    preview: r => html`<div class="ast-chips">${r.pending.map(ref)}</div>${note(`待反馈 ${r.pending.length} / ${r.count}`)}`,
  },
  list_sessions: {
    title: '列 Session', icon: 'calendar', args: a => (a.status === 'active' ? '进行中' : a.status === 'completed' ? '已完成' : '全部'),
    preview: r => html`<ul class="ast-list">${r.sessions.map(s => html`<li class="ast-list__i">${sessRef(s.session_id)}<span class="ast-list__why">${s.count} 道，待反馈 ${s.pending}</span><span class="ast-list__m">${s.status}</span></li>`)}</ul>`,
  },
  list_taxonomy: {
    title: '查分类', icon: 'list', args: a => a.subject || '全部科目',
    preview: r => html`<dl class="ast-kv">${r.subjects.map(s => html`<dt>${s.name}</dt><dd>${s.categories.map(c => `${c.name} ${c.n} 题`).join('，')}</dd>`)}
      <dt>标记</dt><dd>${labelChips(r.labels.map(l => l.name))}</dd></dl>`,
  },
  create_review_session: {
    title: '建复习 Session', icon: 'calendar', level: 'rev',
    args: a => { const items = a.items || []; const due = items.filter(i => i.source !== 'proficiency').length; return `${items.length} 道，到期 ${due} + 熟练度 ${items.length - due}`; },
    preview: r => html`<div class="ast-dlg-row">${sessRef(r.session_id)}<span>${r.count} 道，状态 ${r.status}</span></div><div class="ast-chips">${(r.items || []).map(ref)}</div>`,
  },
  set_question_labels: {
    title: '打标记', icon: 'tag', level: 'rev',
    args: a => `${(a.uids || []).length} 道${a.add?.length ? `，加「${a.add.join('、')}」` : ''}${a.remove?.length ? `，去「${a.remove.join('、')}」` : ''}`,
    preview: r => html`<ul class="ast-list">${r.details.map(d => html`<li class="ast-list__i">${ref(d.uid)}${labelChips(d.after)}<span class="ast-note">新加</span></li>`)}${r.skipped.map(u => html`<li class="ast-list__i">${ref(u)}<span class="ast-list__why">已有，跳过</span></li>`)}</ul>`,
  },
  update_question_section: {
    title: a => `改${a.section || '正文'}`, icon: 'edit', level: 'confirm', args: a => `${a.uid}，${a.mode === 'append' ? '追加' : '替换'}`,
    gate: a => ({ what: `想把 ${a.uid} 的「${a.section}」${a.mode === 'append' ? '追加' : '写成'}：`, preview: a.content }),
    confirm: (a, p) => ({
      title: `允许助手修改「${a.uid}」的${a.section}？`, ok: '允许并写入',
      hint: '这是需确认的写入。允许后写入 1 条记录，来源标为 AI，可以随这次运行一起撤销；旧版本正文存在 Ledger 里。',
      body: html`<div class="ast-dlg-row">${lvl('confirm')}<code>update_question_section</code><span>${a.uid}，${a.section}，${a.mode === 'append' ? '追加' : '替换'}</span></div>
        ${diff(p.before, p.after, '现在', '修改后')}${p.images_kept?.length ? note(`原有的 ${p.images_kept.length} 张图片会保留。`) : ''}
        <details class="ast-ref-q"><summary>对照题面和答案</summary>${box(p.question)}${box(p.answer, true)}</details>`,
    }),
    preview: r => html`${diff(r.before, r.after)}${note(html`正文哈希 <code>${(r.before_hash || '').slice(0, 8)}…</code> → <code>${(r.after_hash || '').slice(0, 8)}…</code>，旧版本存在 Ledger 的 blobs 里，可以还原。`)}`,
  },
  set_knowledge_points: {
    title: '改知识点', icon: 'tag', level: 'confirm', args: a => `${a.uid}，${(a.points || []).length} 个`,
    gate: a => ({ what: `想把 ${a.uid} 的知识点设为：`, preview: (a.points || []).join('、') || '（清空）' }),
    confirm: (a, p) => ({ title: `允许助手修改「${a.uid}」的知识点？`, ok: '允许并写入', hint: '允许后写入 1 条记录，可以撤销。',
      body: diff((p.before || []).join('、'), (p.after || []).join('、'), '现在', '修改后') }),
    preview: r => (r.changed ? diff((r.before || []).join('、'), (r.after || []).join('、')) : note('知识点没有变化。')),
  },
  move_question: {
    title: '移动题目', icon: 'folder', level: 'confirm', args: a => `${a.uid} → ${a.subject ? a.subject + ' / ' : ''}${a.category}`,
    gate: a => ({ what: `想把 ${a.uid} 移到：`, preview: `${a.subject ? a.subject + ' / ' : ''}${a.category}` }),
    confirm: (a, p) => ({ title: `允许助手移动「${a.uid}」？`, ok: '允许并移动', hint: 'UID 会按新分类重新编号。允许后写入 1 条记录，可以撤销（移回原分类）。',
      body: html`<dl class="ast-kv"><dt>现在</dt><dd>${p.from}</dd><dt>移到</dt><dd>${p.to}</dd></dl>` }),
    preview: r => html`<div class="ast-dlg-row">${r.old_uid} <span class="ast-arrow">→</span> ${ref(r.uid)}</div>`,
  },
  suspend_question: {
    title: '停用题目', icon: 'pause', level: 'confirm', args: a => a.uid,
    gate: a => ({ what: `想停用 ${a.uid}：`, preview: a.reason || '（未写原因）' }),
    confirm: (a, p) => ({ title: `允许助手停用「${a.uid}」？`, ok: '允许并停用', hint: '停用后不再进入推荐与复习；可以撤销。',
      body: html`<dl class="ast-kv"><dt>题目</dt><dd>${ref(a.uid)} ${p.path || ''}</dd><dt>原因</dt><dd>${a.reason || '（未写）'}</dd></dl>` }),
    preview: () => note('已停用。'),
  },
  resume_question: {
    title: '恢复题目', icon: 'play', level: 'confirm', args: a => a.uid,
    gate: a => ({ what: `想恢复 ${a.uid}：`, preview: a.reason || '（未写原因）' }),
    confirm: a => ({ title: `允许助手恢复「${a.uid}」？`, ok: '允许并恢复', hint: '恢复后重新参与推荐；可以撤销。', body: html`<dl class="ast-kv"><dt>题目</dt><dd>${ref(a.uid)}</dd></dl>` }),
    preview: () => note('已恢复。'),
  },
  create_draft: {
    title: '建 AI 草稿', icon: 'file', level: 'rev', args: a => `${a.subject || ''} / ${a.category || ''}`,
    preview: (r, _args, current, cropMode) => {
      const d = current?.draft;
      const detect = detectCardState(d);
      const forcePending = (d?.training_tasks || []).some(task => task.force_crop && !(task.boxes || []).length);
      const needsCrop = d?.status === 'cropping' || forcePending;
      const status = current?.error ? '状态读取失败' : current?.loading || !d ? '正在获取当前状态'
        : ({ cropping: '待框选', review: '待审核', done: '已入库', discarded: '已丢弃' }[d.status] || d.status);
      const blocks = d?.blocks || r.blocks || [];
      const question = d ? (blocks.filter(b => b.section === '题目' && b.kind === 'text').map(b => b.text || '').join('').slice(0, 60) || '（题目是图片）')
        : r.question_preview || '（题目是图片）';
      return html`<div class="ast-draft-card"><div class="ast-draft-card__head"><code>${r.draft_id}</code><span class="ui-tag ui-tag--info">${status}</span></div>
        <dl class="ast-kv"><dt>科目 / 分类</dt><dd>${d?.subject || r.subject} / ${d?.category || r.category}</dd><dt>题目</dt><dd>${question}</dd></dl>
        <div class="ast-draft-card__blocks">${blocks.map(block => html`<span class="ui-tag">${block.section} · ${block.kind === 'image' ? '图片' : '文字'}</span>`)}</div>
        ${current?.error ? html`<p class="ast-note is-error">${current.error}</p><button type="button" class="ui-btn ui-btn--sm" data-action="assistant.retryDraft" data-arg="${r.draft_id}">重试读取</button>` : ''}
        ${detect.phase !== 'idle' ? html`<p class="ast-note${detect.phase === 'retry' ? ' is-error' : ''}">${detect.message}</p>` : ''}
        ${needsCrop && cropMode === 'ask' ? html`<button type="button" class="ui-btn ui-btn--sm ui-btn--primary" data-action="assistant.openDraft" data-arg="${r.draft_id}">我来框</button>` : ''}
        ${needsCrop && cropMode === 'ask' && !['busy', 'retry'].includes(detect.phase) ? html`<button type="button" class="ui-btn ui-btn--sm" data-action="assistant.detectDraft" data-arg="${r.draft_id}" ${current?.detecting ? 'disabled' : ''}>AI 框</button>` : ''}
        ${needsCrop && detect.phase === 'retry' && cropMode !== 'manual' ? html`<button type="button" class="ui-btn ui-btn--sm" data-action="assistant.detectDraft" data-arg="${r.draft_id}" ${current?.detecting ? 'disabled' : ''}>重试 AI 框</button>` : ''}
        <button type="button" class="ui-btn ui-btn--sm" data-action="assistant.openDraft" data-arg="${r.draft_id}">查看草稿</button></div>`;
    },
  },
  commit_draft: {
    title: '通过 AI 草稿', icon: 'check-circle', level: 'confirm', args: a => `${a.draft_id} · 第 ${a.revision} 版`,
    gate: a => ({ what: `想将草稿 ${a.draft_id} 的第 ${a.revision} 版入库：`, preview: '请核对预览中的正文、图片、错因与元数据。' }),
    confirm: (a, p) => ({ title: `允许助手通过草稿「${a.draft_id}」？`, ok: '允许并入库',
      hint: `仅允许第 ${p.revision} 版；等待期间修改草稿或切换录题方式后，本次确认会失效。`,
      body: html`<dl class="ast-kv"><dt>科目 / 分类</dt><dd>${p.subject} / ${p.category}</dd>
        <dt>难度</dt><dd>${p.difficulty}</dd><dt>知识点</dt><dd>${(p.knowledge_points || []).join('、') || '（无）'}</dd>
        <dt>标记</dt><dd>${(p.labels || []).join('、') || '（无）'}</dd><dt>错因</dt><dd>${p.cause || '（未填）'}</dd>
        <dt>备注</dt><dd>${p.note || '（未填）'}</dd><dt>来源截图</dt><dd>${(p.source_images || []).length} 张</dd></dl>
        <div class="ast-draft-review">${(p.blocks || []).map(b => html`<div class="ast-draft-review__block"><strong>${b.section} · ${b.kind === 'image' ? '图片' : '文字'}</strong>
          ${b.kind === 'image' ? html`<img src="/api/drafts/image?sha=${encodeURIComponent(b.image_sha || '')}" alt="${b.section}图片预览">` : html`<p>${b.text}</p>`}
          ${b.note ? html`<small>${b.note}</small>` : ''}</div>`)}</div>` }),
    preview: r => html`<p class="ast-note">草稿 ${r.draft_id || ''} 已入库${r.uid ? `：${r.uid}` : '。'}</p>`,
  },
  record_feedback: {
    title: '记录反馈', icon: 'check-circle', level: 'confirm', args: a => (a.items || []).map(i => i.uid).join('、'),
    gate: a => ({ what: '想按你的原话记录反馈：', preview: '「' + (a.user_statement || '') + '」' }),
    confirm: (a, p, st) => ({
      title: `允许助手记录 ${(a.items || []).length} 条反馈？`, ok: '允许并记录',
      hint: '反馈只按你明说的对错和分数记录。允许后写入 1 条记录，来源标为 AI，可以撤销。',
      body: html`<div class="ast-quote"><small>你的原话${st.userAt ? '，' + hhmm(st.userAt) : ''}</small>${a.user_statement}</div>
        <div class="ast-table"><table class="ast-fb"><thead><tr><th>题目</th><th>结果</th><th>自评分</th><th>熟练度（预计）</th><th>状态</th></tr></thead>
        <tbody>${(p.items || []).map(i => html`<tr><td>${ref(i.uid)}</td><td class="${i.is_correct ? 'ok' : 'no'}">${i.is_correct ? '答对' : '答错'}</td><td>${i.sub_score}</td><td>${pct(i.mastery_before)} <span class="ast-arrow">→</span> ${pct(i.mastery_after)}</td><td>${i.state}</td></tr>`)}</tbody></table></div>
        ${p.session_id ? note(`记入 ${p.session_id}，记完还剩 ${p.session_left} 道待反馈。`) : note('不属于任何 Session，按即时练习记录。')}`,
    }),
    preview: r => html`<div class="ast-table"><table class="ast-fb"><thead><tr><th>题目</th><th>熟练度</th><th>状态</th></tr></thead><tbody>${r.items.map(x => html`<tr><td>${ref(x.uid)}</td><td>${pct(x.mastery_before)} <span class="ast-arrow">→</span> ${pct(x.mastery_after)}</td><td>${x.state}</td></tr>`)}</tbody></table></div>
      ${r.session_id ? note(`${r.session_id} 还剩 ${r.session_pending} 道待反馈。`) : ''}`,
  },
};

const FALLBACK = { title: n => n, icon: 'sliders', args: a => JSON.stringify(a || {}).slice(0, 60), preview: r => html`<pre class="ast-raw">${JSON.stringify(r, null, 2)}</pre>` };
export const toolDef = name => T[name] || { ...FALLBACK, title: () => name };
export const toolTitle = st => { const t = toolDef(st.name).title; return typeof t === 'function' ? t(st.args || {}) : t; };
export const toolIcon = st => toolDef(st.name).icon;
export function toolArgs(st) {
  if (!st.args) return st.argsSrc ? st.argsSrc.slice(0, 60) : '';
  try { return toolDef(st.name).args(st.args); } catch (_) { return ''; }
}
export function toolPreview(st, currentDraft, cropMode) {
  const r = st.result;
  if (!r) return '';
  if (r.ok === false) return html`<p class="ast-note is-error">${r.error}</p>`;
  try { return toolDef(st.name).preview(r, st.args || {}, currentDraft, cropMode); } catch (_) { return FALLBACK.preview(r); }
}
export const gateOf = st => (toolDef(st.name).gate ? toolDef(st.name).gate(st.args || {}) : { what: '想执行这一步：', preview: toolArgs(st) });
export const confirmOf = st => (toolDef(st.name).confirm
  ? toolDef(st.name).confirm(st.args || {}, st.preview || {}, st)
  : { title: `允许助手执行「${toolTitle(st)}」？`, ok: '允许', hint: '', body: html`<pre class="ast-raw">${JSON.stringify(st.args, null, 2)}</pre>` });
