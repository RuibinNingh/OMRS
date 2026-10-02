import { questionKey } from '../../domain/question/ref.js';
/**
 * 复习调度 ·「安排复习」视图（原 omrs_dashboard.html 的 #recommend-panel-v2 与 recommend_v2.js 的渲染）。
 * 保留旧 id（#recommend-panel-v2、#rec-*），冒烟测试与旧入口按 id 找；表单控件的值全部来自页面状态（morph 会把未聚焦控件同步回模板值）。
 * 画廊题面挂载点带 data-morph="skip"，key 是 uid，由 index.js 懒加载 qview。
 */
import { html, each, cls } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { select } from '../../ui/select.js';
import { tag } from '../../ui/tag.js';
import { empty } from '../../ui/empty.js';
import { status } from '../../ui/status.js';
import { labelChip, labelChips } from '../../domain/labels/index.js';
import { DUE_OPTIONS, SORT_OPTIONS, MODE_OPTIONS, reason, revive } from './arrange.js';

const opts = (values, all) => [{ value: '', label: all }, ...values.map(v => ({ value: v, label: v }))];
const pairs = list => list.map(([value, label]) => ({ value, label }));

function field(label, key, control, wide) {
  return html`<label class="${cls('schd-field', wide && 'schd-field--grow')}" data-change="schedule.field" data-arg="${key}"><span>${label}</span>${control}</label>`;
}
function numberField(label, key, id, value, min, max, placeholder) {
  return html`<label class="schd-field"><span>${label}</span><input id="${id}" class="schd-input" type="number" min="${min}" max="${max}" placeholder="${placeholder}" value="${value}" data-input="schedule.field" data-arg="${key}"></label>`;
}

function setup(a, env) {
  const f = a.filters;
  const { subjects, categories, ktags } = env.facets;
  return html`<div class="schd-setup" data-key="setup">
  <div class="schd-filters">
    ${field('科目', 'subject', select({ id: 'rec-subject-v2', options: opts(subjects, '全部科目'), value: f.subject }))}
    <label class="schd-field schd-field--grow"><span>搜索</span><input id="rec-search-v2" class="schd-input" type="search" placeholder="题号、分类、知识点或标记" value="${f.text}" data-input="schedule.field" data-arg="text"></label>
    ${field('推荐方式', 'mode', select({ id: 'rec-practice-mode', options: pairs(MODE_OPTIONS), value: f.mode }))}
  </div>
  <details id="rec-more-filters" class="schd-more"${a.more ? ' open' : ''}><summary data-action="schedule.more">更多筛选</summary><div class="schd-filters schd-filters--more">
    ${field('分类', 'category', select({ id: 'rec-filter-category-v2', options: opts(categories, '全部分类'), value: f.category }))}
    ${field('知识点', 'ktag', select({ id: 'rec-filter-ktag-v2', options: opts(ktags, '全部知识点'), value: f.ktag }))}
    ${field('状态', 'tag', select({ id: 'rec-filter-tag-v2', options: opts(['待攻克', '已击杀'], '全部状态'), value: f.tag }))}
    ${field('到期范围', 'due', select({ id: 'rec-filter-due-v2', options: pairs(DUE_OPTIONS), value: f.due }))}
    ${numberField('难度下限', 'diffMin', 'rec-filter-diff-min-v2', f.diffMin, 1, 10, '1')}
    ${numberField('难度上限', 'diffMax', 'rec-filter-diff-max-v2', f.diffMax, 1, 10, '10')}
    ${numberField('熟练度下限 %', 'masteryMin', 'rec-filter-mastery-min-v2', f.masteryMin, 0, 100, '0')}
    ${numberField('熟练度上限 %', 'masteryMax', 'rec-filter-mastery-max-v2', f.masteryMax, 0, 100, '100')}
    ${field('排序', 'sort', select({ id: 'rec-filter-sort-v2', options: pairs(SORT_OPTIONS), value: f.sort }))}
    ${field('标记匹配', 'labelMode', select({ id: 'rec-v2-label-mode', options: [{ value: 'any', label: '匹配任一标记' }, { value: 'all', label: '匹配全部标记' }], value: f.labelMode }))}
    <div class="schd-labels" aria-label="复习标记筛选"><span class="schd-field__cap">标记</span>${env.labels.length ? each(env.labels, l => l.name, l => html`<button type="button" class="schd-lblf" aria-pressed="${f.labels.includes(l.name) ? 'true' : 'false'}" data-action="schedule.label" data-arg="${l.name}">${labelChip(l.name)}</button>`) : html`<span class="schd-meta">还没有标记</span>`}</div>
  </div></details>
  <div id="rec-filter-chips" class="schd-chips">${env.chips.length ? html`${each(env.chips, c => c.key, c => button({ label: c.label, iconRight: 'x', size: 'sm', action: 'schedule.clearField', arg: c.key, title: `移除「${c.label}」` }))}${button({ label: '清除筛选', size: 'sm', variant: 'ghost', action: 'schedule.resetFilters' })}` : ''}</div>
  <div class="schd-suggest"><label class="schd-check">建议题量 <input id="rec-target-count" class="schd-num" type="number" min="1" step="1" value="${a.target}" aria-label="建议题量" data-input="schedule.target"></label><button type="button" id="rec-suggest" class="ui-btn" data-action="schedule.smart"${env.suggestDisabled ? ' disabled' : ''}><span class="ui-btn__label">按建议选择</span></button><span class="schd-meta">替换当前选择；也可以自行勾选</span></div>
</div>`;
}

function candidate(item, i, a, env) {
  const sel = a.selected.has(questionKey(item));
  const rv = revive(item);
  return html`<div class="${cls('schd-cand', sel && 'is-selected')}" data-key="${item.uid}">
  <input type="checkbox" class="schd-cand__check" aria-label="选择 ${item.uid}"${sel ? ' checked' : ''} data-change="schedule.toggle" data-arg="${questionKey(item)}">
  <span class="schd-cand__n">${i + 1}</span>
  <div class="schd-cand__main"><p class="schd-cand__title"><strong class="schd-cand__uid">${item.uid}</strong>${rv ? tag({ label: rv.label, tone: 'warning', title: rv.title }) : ''}</p>
    <p class="schd-meta">${item.subject} · ${item.category} · 难度 ${item.difficulty}${labelChips(item.labels || [])}</p></div>
  ${env.gallery ? html`<div class="schd-cand__preview" data-preview-uid="${item.uid}" data-key="pv-${item.uid}" data-morph="skip"></div>` : ''}
  <div class="schd-cand__info">${tag({ label: reason(item, env.dueDays(item)), tone: item._source === 'due' ? 'warning' : 'neutral' })}<span class="schd-meta">熟练度 ${Math.round((Number(item.mastery) || 0) * 100)}%</span></div>
  ${button({ label: '预览', size: 'sm', action: 'schedule.preview', arg: item.uid })}
</div>`;
}

export function arrangeView(a, env) {
  const statusLine = a.error
    ? html`${status({ tone: 'danger', text: `推荐加载失败：${a.error}` })}${button({ label: '重试', size: 'sm', action: 'schedule.reload' })}`
    : a.notice ? status({ tone: 'danger', text: a.notice })
      : a.loading ? html`<span class="schd-meta">正在更新推荐…</span>` : env.problem ? status({ tone: 'warning', text: env.problem }) : '';
  const seg = v => html`<button type="button" id="rec-view-${v}" class="${cls('schd-seg', a.view === v && 'is-on')}" aria-pressed="${a.view === v ? 'true' : 'false'}" data-action="schedule.recView" data-arg="${v}">${v === 'list' ? '列表' : '画廊'}</button>`;
  const e = env.empty;
  return html`<section class="schd-arrange" id="recommend-panel-v2" role="tabpanel" aria-labelledby="sch-tab-arrange" data-key="arrange">
  <div class="schd-heading"><div><h2 class="schd-heading__title">给这次复习，安排刚好的题量</h2><p class="schd-meta">先筛选，再选题。完成后可打印练习，随时回来录入结果。</p></div>${button({ label: '刷新推荐', icon: 'refresh', size: 'sm', action: 'schedule.reload' })}</div>
  ${setup(a, env)}
  <div id="rec-status-v2" class="schd-note" role="status" aria-live="polite">${statusLine}</div>
  <div class="schd-listbar"><span id="rec-summary-v2" class="schd-meta">${a.data ? `当前显示 ${env.shown.length} 题 · 可安排 ${a.data.length} 题` : '正在准备推荐…'}</span>
    <div class="schd-listbar__acts"><span class="schd-segs" role="group" aria-label="推荐题目视图">${seg('list')}${seg('gallery')}</span>${button({ label: '全选当前结果', size: 'sm', action: 'schedule.selectAll' })}<button type="button" id="rec-only-selected" class="${cls('ui-btn ui-btn--sm', a.onlySelected && 'is-on')}" aria-pressed="${a.onlySelected ? 'true' : 'false'}" data-action="schedule.onlySelected"><span class="ui-btn__label">只看已选</span></button></div></div>
  <div id="rec-unified-list-v2" class="schd-cands" data-view="${env.gallery && env.shown.length ? 'gallery' : 'list'}">${env.shown.length
    ? each(env.shown, item => item.uid, (item, i) => candidate(item, i, a, env))
    : empty({ icon: 'calendar', title: e.title, compact: true, action: e.action === 'plans' ? { label: '查看已有计划', action: 'schedule.view', arg: 'plans', variant: 'default' } : e.action === 'reset' ? { label: '清除筛选', action: 'schedule.resetFilters', variant: 'default' } : undefined })}</div>
  <div id="rec-selection-bar-v2" class="schd-selbar">
    <div class="schd-selbar__info"><strong id="rec-selected-count-v2">已选 ${a.selected.size} 题</strong><span id="rec-est-time-v2" class="schd-meta">${a.selected.size ? `约 ${env.minutes} 分钟 · 仅供参考` : '勾选题目，或按建议选择'}</span>
      <div id="rec-hidden-count" class="schd-meta">${env.hidden ? html`${env.hidden} 道已选题被筛选隐藏，仍会加入计划。 ${button({ label: '查看全部已选', size: 'sm', variant: 'ghost', action: 'schedule.showHidden' })}` : ''}</div></div>
    <div class="schd-acts">${button({ label: '清空', size: 'sm', action: 'schedule.clearSelection' })}<button type="button" id="rec-confirm" class="ui-btn ui-btn--primary" data-action="schedule.confirm"${env.confirmDisabled ? ' disabled' : ''}><span class="ui-btn__label">${a.submitting ? '正在生成…' : '生成计划'}</span></button></div>
  </div>
</section>`;
}
