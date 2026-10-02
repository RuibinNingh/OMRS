import { questionKey, questionRefs } from '../../domain/question/ref.js';
/**
 * 「添加题目」对话框（P7 第 6 轮起；原 assets/board.js 的 boardAddPrompt，旧 .modal-overlay 弹层 Esc 关不掉）。
 * - 外壳是 ui/dialog（Esc、点遮罩、焦点陷阱与焦点归还由 ui/overlay 负责）；内容节点 morph 重绘，搜索框聚焦时不丢输入。
 * - 筛选语义与题库、调度、导出共用 filterItems()（经 domain/items），条件由 state.js 的 addFilters 组装；停用题不列。
 * - 勾选集合 selected 是唯一真相：列表 / 画廊只是同一份筛选结果的两种画法，来回切视图不丢选择。视图只存本地。
 * - 「加入展示板」没有勾选时留在对话框里（Enter 在搜索框里按下去不会空手关掉）；确认后经 detail.js 的 addToBoard 写入。
 */
import { html, each, cls, raw } from '../../core/html.js';
import { morph, toElement } from '../../core/dom.js';
import { dialog } from '../../ui/dialog.js';
import { select } from '../../ui/select.js';
import { labelChip, labelChips, listLabels } from '../../domain/labels/index.js';
import { allItems, filterAll, facets } from '../../domain/items.js';
import { qvRender, qvGalleryIdHtml } from '../../domain/question/index.js';
import * as S from './state.js';

const CARD_OPTS = { layout: 'stack', showMeta: false, showAnswer: false, showNotes: false, showHistory: false, actions: [], bare: true, clamp: 5 };

function readView(storage) {
  try { return storage?.getItem(S.ADD_VIEW_KEY) === 'gallery' ? 'gallery' : 'list'; } catch (error) { return 'list'; }
}
function writeView(storage, value) {
  try { storage?.setItem(S.ADD_VIEW_KEY, value === 'gallery' ? 'gallery' : 'list'); } catch (error) { /* 隐私模式 */ }
}
const opts = (pairs, value) => pairs.map(([v, label]) => ({ value: v, label, selected: v === value }));
const withAll = (values, all) => [['', all], ...values.map(v => [v, v])];

function body(m) {
  return html`<div class="brd-add" data-key="add">
  <div class="brd-add__filters" data-key="filters">
    <input class="ui-input brd-add__search" type="search" data-bdadd="text" value="${m.f.text}" placeholder="搜索 UID / 科目 / 分类 / 知识点 / 标记…" aria-label="搜索题目" autocomplete="off">
    ${select({ id: 'bd-add-subject', size: 'sm', label: '科目', options: opts(withAll(m.facets.subjects, '全部科目'), m.f.subject), value: m.f.subject })}
    ${select({ id: 'bd-add-category', size: 'sm', label: '分类', options: opts(withAll(m.facets.categories, '全部分类'), m.f.category), value: m.f.category })}
    ${select({ id: 'bd-add-ktag', size: 'sm', label: '知识点', options: opts(withAll(m.facets.ktags, '全部知识点'), m.f.ktag), value: m.f.ktag })}
    ${select({ id: 'bd-add-tag', size: 'sm', label: '状态', options: opts(S.ADD_TAGS, m.f.tag), value: m.f.tag })}
    ${select({ id: 'bd-add-due', size: 'sm', label: '到期', options: opts(S.ADD_DUES, m.f.due), value: m.f.due })}
    ${select({ id: 'bd-add-sort', size: 'sm', label: '排序', options: opts(S.ADD_SORTS, m.f.sort), value: m.f.sort })}
  </div>
  <div class="brd-add__bar" data-key="bar"><span class="brd-add__k">标记</span>
    ${m.labels.length ? m.labels.map(name => html`<button type="button" class="brd-add__lbl" data-bdadd-label="${name}" aria-pressed="${m.f.labels.includes(name) ? 'true' : 'false'}">${labelChip(name)}</button>`) : html`<span class="brd-hint">暂无标记</span>`}
    <span class="brd-grow"></span>
    <div class="brd-seg" role="group" aria-label="视图">${[['list', '列表'], ['gallery', '画廊']].map(([key, label]) => html`<button type="button" class="brd-seg__btn" data-bdadd-view="${key}" aria-pressed="${m.view === key ? 'true' : 'false'}">${label}</button>`)}</div>
  </div>
  <div class="${cls('brd-add__list', m.view === 'gallery' && 'is-gallery')}" data-bdadd-list data-key="list-${m.view}">${list(m)}</div>
  <div class="brd-add__foot" data-key="foot"><span class="brd-add__count" data-bdadd-count role="status">已选 ${m.count} 题 · 筛出 ${m.rows.length} 题</span>
    <button class="ui-btn ui-btn--ghost ui-btn--sm" type="button" data-bdadd-all${m.rows.some(r => !r.on) ? '' : html` disabled`}>全选筛选结果</button></div>
</div>`;
}

function box(r) {
  return html`<input type="checkbox" data-bdadd-uid="${r.uid}" data-bdadd-key="${r.key}" aria-label="选择 ${r.uid}"${r.on ? html` checked` : ''}${r.in ? html` disabled` : ''}>`;
}
function list(m) {
  if (!m.rows.length) return html`<p class="brd-add__none" data-key="none">没有匹配的题目。</p>`;
  if (m.view === 'gallery') {
    return html`<div class="brd-gallery brd-gallery--pick" data-key="grid">${each(m.rows, r => r.uid, r => html`<article class="${cls('brd-gcard', r.in && 'is-in')}" data-key="${r.uid}"${r.on && !r.in ? html` aria-current="true"` : ''}>
  <header class="brd-gcard__head"><label class="brd-gcard__pick">${box(r)}</label><span class="brd-gcard__id">${raw(qvGalleryIdHtml(r.uid, r.category))}</span>${r.in ? html`<span class="brd-flag" data-tone="muted">已在板中</span>` : ''}</header>
  <div class="brd-gcard__preview" data-key="pv:${r.uid}" data-morph="skip" data-qv-host data-uid="${r.uid}"></div>
  <footer class="brd-gcard__foot"><span>${r.subject}${r.category ? ` · ${r.category}` : ''}</span><span>难度 ${r.difficulty}</span><span>熟练 ${r.mastery}%</span><span class="brd-labels">${labelChips(r.labels, { max: 3 })}</span></footer>
</article>`)}</div>`;
  }
  return each(m.rows, r => r.uid, r => html`<label class="${cls('brd-add__row', r.in && 'is-in')}" data-key="${r.uid}">${box(r)}
    <span class="brd-add__main"><strong>${r.uid}</strong>${r.in ? html`<span class="brd-flag" data-tone="muted">已在板中</span>` : ''}<small>${r.subject} · ${r.category} · 难度 ${r.difficulty} · 熟练度 ${r.mastery}%</small></span>
    <span class="brd-labels">${labelChips(r.labels, { max: 3 })}</span></label>`);
}

/**
 * 打开对话框。detail = 当前板详情；add(uids) 写入（detail.js 的 addToBoard）。deps 供测试替换：
 * { items, labels, dialog, storage, render }。返回 Promise<加入的 uid 数组 | null（取消）>。
 */
export async function openBoardAdd(detail, add, deps = {}) {
  if (!detail) return null;
  const d = { items: allItems, labels: () => listLabels().map(label => label.name), dialog, storage: () => globalThis.localStorage, ...deps };
  const all = d.items().filter(item => !item.suspended);
  const existing = new Set((detail.items || []).map(questionKey));
  const state = { f: { ...S.ADD_DEFAULTS, labels: [] }, view: readView(d.storage()), selected: new Set() };
  const meta = { facets: facets(all), labels: d.labels() };
  let visible = [];
  const node = toElement(html`<div class="brd-add-host"></div>`);

  const paint = () => {
    visible = filterAll(all, S.addFilters(state.f));
    const rows = S.addRows(visible, existing, state.selected);
    morph(node, body({ ...meta, f: state.f, view: state.view, rows, count: state.selected.size }));
    if (state.view === 'gallery') {
      node.querySelectorAll('[data-qv-host]').forEach(el => {
        if (el.dataset.qvFor === el.dataset.key) return;
        el.dataset.qvFor = el.dataset.key;
        qvRender(el, el.dataset.uid, CARD_OPTS).then(() => el.classList.toggle('is-clipped', el.scrollHeight - el.clientHeight > 4));
      });
    }
  };
  const FIELDS = { 'bd-add-subject': 'subject', 'bd-add-category': 'category', 'bd-add-ktag': 'ktag', 'bd-add-tag': 'tag', 'bd-add-due': 'due', 'bd-add-sort': 'sort' };
  node.addEventListener('input', event => {
    if (event.target.matches?.('[data-bdadd="text"]')) { state.f = { ...state.f, text: event.target.value }; paint(); }
  });
  node.addEventListener('change', event => {
    const t = event.target;
    if (FIELDS[t.id]) { state.f = { ...state.f, [FIELDS[t.id]]: t.value }; paint(); return; }
    const uid = t.dataset?.bdaddKey;
    if (!uid || t.disabled) return;
    if (t.checked) state.selected.add(uid); else state.selected.delete(uid);
    paint();
  });
  node.addEventListener('click', event => {
    const label = event.target.closest('[data-bdadd-label]');
    if (label) {
      const name = label.dataset.bdaddLabel;
      const labels = state.f.labels.includes(name) ? state.f.labels.filter(x => x !== name) : [...state.f.labels, name];
      state.f = { ...state.f, labels };
      paint();
      return;
    }
    const viewButton = event.target.closest('[data-bdadd-view]');
    if (viewButton) { state.view = viewButton.dataset.bdaddView === 'gallery' ? 'gallery' : 'list'; writeView(d.storage(), state.view); paint(); return; }
    if (event.target.closest('[data-bdadd-all]')) { state.selected = S.addSelectAll(visible, existing, state.selected); paint(); return; }
    // 画廊卡：点卡片任意处（按钮、复选框、标记以外）等于点它的复选框
    const card = event.target.closest('.brd-gcard');
    if (card && !event.target.closest('input, button, label, a, .lbl')) card.querySelector('[data-bdadd-uid]:not(:disabled)')?.click();
  });
  paint();

  const res = await d.dialog({
    title: `添加题目到「${detail.name || ''}」`, hint: '筛选后勾选；已在板里的题目会标灰并跳过。', size: 'xl',
    okText: '加入展示板', content: node, focus: '[data-bdadd="text"]', id: 'bd-add-dialog',
    onOk: () => state.selected.size > 0,
  });
  if (!res.ok || !state.selected.size) return null;
  const uids = [...state.selected];
  await add(questionRefs(uids, all));
  return uids;
}
