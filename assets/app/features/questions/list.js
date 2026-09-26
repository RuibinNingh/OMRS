/**
 * 题库页列表模板：表格与画廊（只产出 html``，由 index.js 用 morph 差量写入）。
 * - 行 / 卡带 data-key=uid 与 data-q-row=uid：morph 按 uid 对齐；整行点击由 index.js 在根上委托（跳过勾选框、按钮、标记格）。
 *   行 / 卡 tabindex="-1"：点击时焦点落在行上，题目弹窗关闭后焦点能回到行（不进 Tab 序列，键盘移动仍走行游标）。
 * - 表格在 ≤760px 由 questions.css 降级为卡片列表（D4）：每格带 data-label，勾选 / 题目 / 操作占第一行。
 * - 画廊的题面预览挂载点 data-morph="skip"，key 编码「uid + 截断行数」：只有换题或换密度时才换新挂载点，hydrate() 交给 domain 的 qvRender。
 * - 战绩带：详情已在缓存里就直接画（画廊为预览本来就拉一次详情，拉完 index.js 再重绘一次），不额外发请求。
 */
import { html, raw, each, cls } from '../../core/html.js';
import { icon } from '../../ui/icon.js';
import { progress } from '../../ui/progress.js';
import { empty } from '../../ui/empty.js';
import { labelChips } from '../../domain/labels/index.js';
import { qvGalleryIdHtml, qRecordsFromDetail, qHistoryStats, qStreakHtml } from '../../domain/question/index.js';
import { COLUMN_LABELS, dueInfo, statusOf, reviveOf, masteryPct, masteryTone, galleryFlags, galleryCardOpts } from './state.js';

const num = (value, fallback = 0) => { const n = Number(value); return Number.isFinite(n) ? n : fallback; };

export function masteryCell(item, { short = false } = {}) {
  const pct = masteryPct(item);
  return html`<span class="${cls('qlb-mastery', short && 'qlb-mastery--short')}">${progress({ value: pct, max: 100, label: `熟练度 ${pct}%`, tone: masteryTone(pct), size: 'sm' })}<span class="qlb-num">${pct}%</span></span>`;
}

export function statusCell(item) {
  const status = statusOf(item);
  const revive = reviveOf(item);
  return html`<span class="qlb-status" data-status="${status.kind}">${status.label}</span>${revive ? html`<span class="qlb-revive" title="${revive.title}">${revive.label}</span>` : ''}`;
}

const moreButton = item => html`<button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon qlb-more" data-action="questions.more" data-arg="${item.uid}" aria-haspopup="menu" aria-label="更多操作：${item.uid}" title="更多操作">${icon('more-h')}</button>`;
const checkBox = (uid, on) => html`<label class="qlb-check" title="选择"><input type="checkbox" data-change="questions.select" data-arg="${uid}" aria-label="选择 ${uid}"${on ? html` checked` : ''}></label>`;

const CELLS = {
  select: (item, env) => checkBox(item.uid, env.selected.has(item.uid)),
  main: item => html`<strong class="qlb-uid">${item.uid}</strong><span class="qlb-meta">${item.subject || ''} · ${item.category || ''}${item.is_leech ? html`<span class="qlb-leech">顽固</span>` : ''}</span>`,
  labels: item => html`<span class="q-label-cell qlb-labels" data-lbl-target="${item.uid}">${labelChips(item.labels || [], { add: true, max: 4 })}</span>`,
  mastery: item => masteryCell(item),
  due: (item, env) => { const due = dueInfo(env.dueDays(item)); return html`<span class="qlb-due" data-tone="${due.tone}">${due.text}</span>`; },
  status: item => statusCell(item),
  difficulty: item => html`<span class="qlb-num">${item.difficulty ?? ''}</span>`,
  decayed: item => html`<span class="qlb-num">${Math.round(num(item.decayed_mastery) * 100)}%</span>`,
  attempts: item => html`<span class="qlb-num">${item.attempts ?? 0}</span>`,
  last_review: item => html`<span class="qlb-num">${item.last_review || '—'}</span>`,
  ef: item => html`<span class="qlb-num">${item.ef ?? ''}</span>`,
  actions: item => moreButton(item),
};

function emptyState(env) {
  if (!env.total) {
    return empty({ icon: 'inbox', title: '题库里还没有题目', hint: '在「录入题目」添加第一道题，或把 Obsidian 里的题目文件放进题库后点「重新扫描」。', action: { label: '录入题目', action: 'questions.goCreate' }, compact: true });
  }
  return empty({ icon: 'search', title: '没有匹配的题目', hint: '当前筛选条件下没有题目，放宽条件或清空筛选再看。', action: { label: '清空筛选', action: 'questions.clearAll', variant: 'default' }, compact: true });
}

export function tableView(rows, env) {
  const cols = env.columns;
  const head = cols.map(key => {
    if (key === 'select') return html`<th scope="col" data-col="select"><label class="qlb-check" title="全选当前显示"><input type="checkbox" id="qlb-select-all" data-change="questions.selectAll" aria-label="全选当前显示"${env.sel.all ? html` checked` : ''}></label></th>`;
    if (key === 'actions') return html`<th scope="col" data-col="actions"><span class="qlb-sr">${COLUMN_LABELS.actions}</span></th>`;
    return html`<th scope="col" data-col="${key}">${COLUMN_LABELS[key]}</th>`;
  });
  const body = rows.length
    ? each(rows, item => item.uid, item => html`<tr data-key="${item.uid}" data-q-row="${item.uid}" tabindex="-1" class="${cls('qlb-row', item.suspended && 'is-suspended')}" aria-selected="${env.selected.has(item.uid) ? 'true' : 'false'}"${env.cursor === item.uid ? html` data-cursor="1"` : ''} title="点击查看题目">${cols.map(key => html`<td data-col="${key}" data-label="${COLUMN_LABELS[key]}">${CELLS[key](item, env)}</td>`)}</tr>`)
    : html`<tr class="qlb-empty" data-key="__empty"><td colspan="${cols.length}">${emptyState(env)}</td></tr>`;
  return html`<div class="qlb-table-wrap" data-key="table" tabindex="-1"><table class="qlb-table" data-density="${env.prefs.density}"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

/** 画廊脚注的战绩带：详情在手才画（最近记录 + 记录数 + 连错 ≥2 的提醒），否则退回「N 次」；关掉战绩带时只显示次数。 */
export function streakFoot(item, detail, on = true) {
  const attempts = num(item.attempts);
  if (!on || !detail) return attempts ? { text: `${attempts} 次` } : null;
  const records = qRecordsFromDetail(detail);
  const stats = qHistoryStats(records);
  if (!stats.count) return attempts ? { text: `${attempts} 次` } : null;
  return { streak: qStreakHtml(records), text: `${stats.count} 次`, warn: stats.tailWrong >= 2 ? `连错 ${stats.tailWrong}` : '' };
}

function galleryCard(item, env) {
  const prefs = env.prefs;
  const flags = galleryFlags(item, env.dueDays(item), prefs.galleryDetail);
  const ktags = (item.knowledge_tags || []).filter(tag => tag && tag !== item.category);
  const opts = galleryCardOpts(prefs);
  const foot = streakFoot(item, env.detailOf(item.uid), prefs.streak);
  return html`<article class="${cls('qlb-gcard', item.suspended && 'is-suspended')}" data-key="${item.uid}" data-q-row="${item.uid}" tabindex="-1" aria-selected="${env.selected.has(item.uid) ? 'true' : 'false'}"${env.cursor === item.uid ? html` data-cursor="1"` : ''}>
  <header class="qlb-gcard__head">${checkBox(item.uid, env.selected.has(item.uid))}<span class="qlb-gcard__id">${raw(qvGalleryIdHtml(item.uid, item.category))}</span>
    <span class="qlb-gcard__flags">${flags.map(f => html`<span class="qlb-flag" data-tone="${f.tone}"${f.title ? html` title="${f.title}"` : ''}>${f.text}</span>`)}</span>${moreButton(item)}</header>
  ${prefs.galleryDetail ? html`<p class="qlb-gcard__meta" data-key="meta">${item.subject || ''} · 上次复习 ${item.last_review || '—'} · 衰减后 ${Math.round(num(item.decayed_mastery) * 100)}%${ktags.length ? ` · ${ktags.join(' / ')}` : ''}</p>` : ''}
  <div class="qlb-gcard__preview" data-key="pv:${item.uid}:${opts.clamp}" data-morph="skip" data-qv-host data-uid="${item.uid}"></div>
  <footer class="qlb-gcard__foot">
    ${masteryPct(item) > 0 || num(item.attempts) > 0 ? masteryCell(item, { short: true }) : html`<span class="qlb-muted">未练习</span>`}
    ${item.difficulty != null && item.difficulty !== '' ? html`<span class="qlb-muted">难度 ${item.difficulty}</span>` : ''}
    ${foot ? html`<span class="qlb-streak">${foot.streak ? raw(foot.streak) : ''}<span class="qlb-muted">${foot.text}</span>${foot.warn ? html`<span class="qlb-warn">${foot.warn}</span>` : ''}</span>` : ''}
    <span class="q-label-cell qlb-labels" data-lbl-target="${item.uid}">${labelChips(item.labels || [], { add: true, max: 3 })}</span>
  </footer>
</article>`;
}

export function galleryView(rows, env) {
  const prefs = env.prefs;
  if (!rows.length) return html`<div class="qlb-gallery qlb-gallery--empty" data-key="gallery-empty">${emptyState(env)}</div>`;
  return html`<div class="qlb-gallery" data-key="gallery" data-cols="${prefs.galleryCols ? String(prefs.galleryCols) : 'auto'}" data-density="${prefs.density}"${prefs.galleryDetail ? html` data-detail="1"` : ''}>${each(rows, item => item.uid, item => galleryCard(item, env))}</div>`;
}
