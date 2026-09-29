/**
 * 即时练习：视图模板（只产出 html``，由 index.js 用 morph 差量写入 #panel-instant）。
 * 约定：会出现 / 消失的块都带 data-key，morph 按 key 对齐，不会因为某块缺席而把后面的节点整排重建；
 * 题面挂载点带 data-morph="skip" 与「uid + 是否翻开」的 key——只有换题、翻答案时才换新挂载点，判定、打分、切队列都不碰题面。
 */
import { html, each, cls } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { icon } from '../../ui/icon.js';
import { select } from '../../ui/select.js';
import { tag } from '../../ui/tag.js';
import { empty } from '../../ui/empty.js';
import { skeleton } from '../../ui/skeleton.js';
import { progress } from '../../ui/progress.js';
import { status } from '../../ui/status.js';
import { kbd } from '../../ui/kbd.js';
import { labelChip, labelChips } from '../../domain/labels/index.js';
import { counts, currentItem, isJudged, nextOpenIndex } from './state.js';
import { formatPercent } from '../../core/format.js';

const pct = value => formatPercent(Number(value) || 0);
const SOURCE = { due: ['到期', 'warning'], proficiency: ['熟练度', 'info'] };

export function dueText(days) {
  if (days == null) return ['未排期', ''];
  if (days < 0) return [`逾期 ${-days} 天`, 'is-overdue'];
  if (days === 0) return ['今日到期', 'is-due'];
  return [`${days} 天后到期`, ''];
}

function options(values, placeholder, value) {
  return [{ value: '', label: placeholder }, ...values.map(v => ({ value: v, label: v }))]
    .concat(value && !values.includes(value) ? [{ value, label: value }] : []);
}

function filterBar(s, env) {
  if (s.cardId) return html`<section class="inst-bar" data-key="bar" aria-label="临时练习卡">
    <h2>${s.cardTitle}</h2><p class="inst-bar__note">临时练习 · ${s.queue.length} 题。只有提交判定才记练习记录，不创建正式 Session。</p>
    ${s.chatDeleted ? status({ tone: 'warning', text: '关联对话已删除；当前练习仍可继续提交，不能再从聊天重新开始。', block: true }) : ''}
    ${s.unavailable.length ? status({ tone: 'warning', text: `${s.unavailable.length} 道题已删除或停用，按原题序跳过：${s.unavailable.map(i => i.uid_at_creation).join('、')}`, block: true }) : ''}
    ${s.chatDeleted ? '' : button({ label: '重新练一轮', action: 'instant.restartPractice' })}${button({ label: '加载推荐', action: 'instant.load' })}
  </section>`;
  const f = s.filters;
  const { subjects, categories, ktags } = env.facets;
  const loading = s.loading || s.phase === 'loading';
  const labels = env.labels;
  return html`<section class="inst-bar" data-key="bar" aria-label="练习设置">
  <p class="inst-bar__note" data-key="note">按推荐算法取题；判定只写练习记录，不建调度 Session。</p>
  <div class="inst-bar__filters" data-key="filters" data-change="instant.filter">
    ${select({ id: 'instant-subject', label: '科目', options: options(subjects, '全部科目', f.subject), value: f.subject })}
    ${select({ id: 'instant-category', label: '分类', options: options(categories, '全部分类', f.category), value: f.category })}
    ${select({ id: 'instant-ktag', label: '知识点', options: options(ktags, '全部知识点', f.ktag), value: f.ktag })}
    <label class="inst-count"><span class="inst-count__label">题数</span><input class="inst-count__input" type="number" id="instant-count" inputmode="numeric" min="1" max="50" value="${f.count}"></label>
    ${button({ label: loading ? '正在取题' : '加载推荐', variant: 'primary', icon: 'play', action: 'instant.load', loading })}
  </div>
  ${labels.length ? html`<div class="inst-bar__labels" data-key="labels" role="group" aria-label="标记筛选">
    <span class="inst-bar__cap">标记</span>
    ${each(labels, l => l.name, l => html`<button type="button" class="${cls('ui-btn', 'ui-btn--sm', 'ui-btn--ghost', 'inst-lblf')}" data-key="${l.name}" data-action="instant.label" data-arg="${l.name}" aria-pressed="${f.labels.includes(l.name) ? 'true' : 'false'}" title="${l.name}${l.count != null ? ` · ${l.count} 题` : ''}">${labelChip(l.name)}</button>`)}
    ${f.labels.length > 1 ? html`<span class="inst-bar__mode" data-key="mode" data-change="instant.labelMode">${select({ id: 'instant-label-mode', label: '标记匹配方式', size: 'sm', value: f.labelMode, options: [{ value: 'any', label: '任一命中' }, { value: 'all', label: '全部命中' }] })}</span>` : ''}
  </div>` : ''}
</section>`;
}

function cardHead(s, item, env) {
  const [source, tone] = SOURCE[item._source] || SOURCE.due;
  const [due, dueCls] = dueText(env.dueDays(item));
  const dueTone = { 'is-overdue': 'danger', 'is-due': 'warning' }[dueCls] || 'neutral';
  return html`<header class="inst-card__head" data-key="head">
    <div class="inst-card__pos">
      <h3 class="inst-card__title" id="inst-card-title">第 ${s.index + 1} 题<span class="inst-card__of"> / ${s.queue.length}</span></h3>
      <span class="inst-card__uid">${item.uid}</span>${tag({ label: source, tone })}
    </div>
    <div class="inst-card__meta">
      ${item.subject ? tag({ label: item.subject }) : ''}${item.category ? tag({ label: item.category }) : ''}
      ${tag({ label: `难度 ${item.difficulty ?? '?'}` })}${tag({ label: `熟练度 ${pct(item.mastery)}` })}${tag({ label: due, tone: dueTone })}
    </div>
  </header>`;
}

function grading(row) {
  const verdict = (value, label, ico, key) => html`<button type="button" class="${cls('ui-btn', 'inst-verdict__btn', `inst-verdict__btn--${value ? 'ok' : 'no'}`)}" data-action="instant.verdict" data-arg="${value ? '1' : '0'}" aria-pressed="${row.correct === value ? 'true' : 'false'}"${row.submitted ? html` disabled` : ''}>${icon(ico)}<span>${label}</span>${kbd(key)}</button>`;
  const score = row.score == null ? 5 : row.score;
  return html`<section class="inst-grade" data-key="grade" aria-label="判定">
    <div class="inst-verdict" role="group" aria-label="判定对错">${verdict(true, '对', 'check', '1')}${verdict(false, '错', 'x', '2')}</div>
    <label class="inst-score"><span class="inst-score__label">主观分</span><input class="inst-score__input" type="range" min="0" max="10" step="1" value="${score}" data-input="instant.score" aria-valuetext="${score} 分"${row.submitted ? html` disabled` : ''}><output class="inst-score__value">${score}</output></label>
    ${row.submitted ? html`<p class="inst-grade__note">${icon('lock')}这题已提交，判定不能再改。</p>` : ''}
  </section>`;
}

function card(s, env) {
  const item = currentItem(s);
  const row = s.results[item.uid] || { revealed: false, correct: null, score: null, submitted: false };
  const labels = item.labels || [];
  const ktags = item.knowledge_tags || [];
  const reveal = row.revealed ? '1' : '0';
  const last = s.queue.length - 1;
  return html`<article class="inst-card" data-key="card" aria-labelledby="inst-card-title">
    ${cardHead(s, item, env)}
    ${labels.length || ktags.length ? html`<div class="inst-card__tags" data-key="tags">${labelChips(labels)}${ktags.map(t => tag({ label: t, tone: 'accent' }))}</div>` : ''}
    <div class="inst-card__qv" data-key="qv:${item.uid}:${reveal}" data-morph="skip" data-qv-host data-uid="${item.uid}" data-reveal="${reveal}"></div>
    ${row.revealed ? grading(row) : ''}
    <nav class="inst-card__nav" data-key="nav" aria-label="切题">
      ${button({ label: '上一题', icon: 'arrow-left', action: 'instant.prev', disabled: s.index <= 0 })}
      ${button({ label: '下一道未判定', action: 'instant.nextOpen', disabled: nextOpenIndex(s.queue, s.results, s.index) < 0 })}
      ${button({ label: '下一题', iconRight: 'arrow-right', action: 'instant.next', disabled: s.index >= last })}
    </nav>
    <p class="inst-card__keys" data-key="keys">${kbd('J')}${kbd('K')} 切题 · ${kbd('空格')} 显示答案 · ${kbd('1')}${kbd('2')} 判对错 · ${kbd('0–9')} 打分 · ${kbd('Enter')} 下一道未判定 · ${kbd('E')} 编辑 · ${kbd('Ctrl', 'Enter')} 提交</p>
  </article>`;
}

function mainArea(s, env) {
  if (s.phase === 'loading') {
    return html`<div class="inst-card inst-card--wait" data-key="loading">${skeleton({ lines: 6, label: '正在按推荐算法取题' })}</div>`;
  }
  if (s.phase === 'error') {
    return html`<div class="inst-state" data-key="error">${empty({ icon: 'alert-circle', title: '取题失败', hint: s.error || '服务没有响应，请稍后重试。', action: { label: '重试', action: 'instant.load', icon: 'refresh' }, bordered: true })}</div>`;
  }
  if (s.phase === 'empty') {
    return html`<div class="inst-state" data-key="empty">${empty({ icon: 'filter', title: '当前筛选下没有可练的题', hint: '放宽科目、分类、知识点或标记后再试。', action: { label: '清空筛选并重新取题', action: 'instant.clear' }, bordered: true })}</div>`;
  }
  if (!s.queue.length) {
    return html`<div class="inst-state" data-key="idle">${empty({ icon: 'play', title: '还没开始练习', hint: '按推荐算法从到期题和低熟练度题里取题；判定结果只写练习记录，不会建调度 Session。', action: { label: '开始练习', action: 'instant.load', icon: 'play' }, bordered: true })}</div>`;
  }
  return card(s, env);
}

function queueItem(s, item, i, env) {
  const row = s.results[item.uid];
  const judged = isJudged(row);
  const state = row?.submitted ? 'submitted' : judged ? (row.correct ? 'ok' : 'no') : 'open';
  const mark = { submitted: ['check-circle', '已提交'], ok: ['check', '判对'], no: ['x', '判错'], open: [null, '未判定'] }[state];
  const [due, dueCls] = dueText(env.dueDays(item));
  return html`<li class="inst-q-item" data-key="${item.uid}"><button type="button" class="${cls('inst-q', `is-${state}`)}" data-action="instant.go" data-arg="${i}"${i === s.index ? html` aria-current="step"` : ''} title="${item.uid} · ${mark[1]}">
    <span class="inst-q__n">${i + 1}</span>
    <span class="inst-q__main"><span class="inst-q__uid">${item.uid}</span><span class="inst-q__meta">熟练度 ${pct(item.mastery)} · <span class="${cls('inst-q__due', dueCls)}">${due}</span></span></span>
    <span class="inst-q__mark" aria-label="${mark[1]}">${mark[0] ? icon(mark[0]) : ''}</span>
  </button></li>`;
}

function summary(s) {
  const c = counts(s);
  const open = nextOpenIndex(s.queue, s.results, s.index);
  return html`<section class="inst-sum" data-key="sum" aria-label="进度与提交">
    <div class="inst-sum__row"><span class="inst-sum__cap">已判定</span><strong class="inst-sum__num">${c.judged}<span> / ${c.total}</span></strong></div>
    ${progress({ value: c.judged, max: Math.max(1, c.total), label: '判定进度', size: 'sm' })}
    <p class="inst-sum__meta">已提交 ${c.submitted} · 待提交 ${c.pending}</p>
    <div class="inst-sum__acts">
      ${button({ label: s.submitting ? '正在提交' : (c.pending ? `提交 ${c.pending} 道` : '提交已判定'), variant: 'primary', icon: 'send', action: 'instant.submit', loading: s.submitting, disabled: !c.pending })}
      ${button({ label: '下一道未判定', action: 'instant.nextOpen', disabled: open < 0 })}
    </div>
    ${s.submitError ? status({ tone: 'danger', text: `提交失败：${s.submitError}`, block: true }) : ''}
  </section>`;
}

const RESULT_TONE = { 已击杀: 'success', 真不会: 'danger' };

function results(s) {
  if (!s.lastSubmit.length) return '';
  return html`<section class="inst-res" data-key="res" aria-label="本次提交结果">
    <h3 class="inst-rail__cap">本次提交</h3>
    <ul class="inst-res__list">${each(s.lastSubmit, (r, i) => `${r.uid}:${i}`, (r, i) => {
      const ok = r.status === 'ok';
      return html`<li class="${cls('inst-res__row', ok ? 'is-ok' : 'is-err')}" data-key="${r.uid}:${i}"><span class="inst-res__uid">${r.uid}</span>${r.label ? tag({ label: r.label, tone: RESULT_TONE[r.label] || 'warning' }) : ''}<span class="inst-res__delta">${ok ? (r.reused ? '已记录，未重复计分' : `${pct(r.old_mastery)} → ${pct(r.new_mastery)}`) : (r.msg || '失败')}</span></li>`;
    })}</ul>
  </section>`;
}

function rail(s, env) {
  return html`<aside class="inst-rail" data-key="rail" aria-label="练习队列">
    ${summary(s)}
    <section class="inst-queue" data-key="queue" aria-label="队列">
      <h3 class="inst-rail__cap">队列</h3>
      <ol class="inst-queue__list">${each(s.queue, item => item.uid, (item, i) => queueItem(s, item, i, env))}</ol>
    </section>
  </aside>`;
}

/** DOM 顺序：进度与队列 → 题卡 → 提交结果（窄屏自然竖排）；>1160 由 CSS 摆成「题卡 | 右栏」两列。 */
export function view(s, env) {
  const withRail = s.queue.length > 0 && (s.phase === 'ready' || s.phase === 'loading');
  return html`<div class="${cls('inst', withRail && 'inst--rail')}" data-key="inst">
  ${filterBar(s, env)}
  <div class="inst-work" data-key="work">
    ${withRail ? rail(s, env) : ''}
    <div class="inst-main" data-key="main">${mainArea(s, env)}</div>
    ${withRail ? results(s) : ''}
  </div>
</div>`;
}
