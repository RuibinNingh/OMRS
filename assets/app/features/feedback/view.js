/**
 * 反馈录入工作台：视图模板（只产出 html``，由 index.js 用 morph 差量写入 #panel-feedback）。
 * 约定同即时练习：会出现 / 消失的块都带 data-key；题面挂载点带 data-morph="skip" 与 key=uid——
 * 只有换题时才换新挂载点，判定、打分、写备注都不碰题面（KaTeX、图片、滚动保留）。
 */
import { html, each, cls, raw } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { icon } from '../../ui/icon.js';
import { select } from '../../ui/select.js';
import { empty } from '../../ui/empty.js';
import { status } from '../../ui/status.js';
import { kbd } from '../../ui/kbd.js';
import { labelChip, labelChips, listLabels } from '../../domain/labels/index.js';
import {
  sessionUniqueUids, fbSessionProgress, fbRailEntries, fbSessionPositions,
  clampCursor, nextOpenIndex, currentContext,
} from './state.js';
import { formatPercent } from '../../core/format.js';

const TONE = { ok: 'success', warn: 'warning', danger: 'danger' };

function metaText(items, uid) {
  const q = items.find(x => x.uid === uid);
  return q ? [q.subject || '', q.category || ''].filter(Boolean).join(' · ') || '—' : '—';
}

// ── 顶栏：Session 选择 + 动作 + 进度 ──────────────────────────────────────────────
function sessionOptions(sessions, active) {
  const opts = [{ value: '', label: '— 手动录入（不关联 Session）—' }];
  sessions.forEach(session => {
    const p = fbSessionProgress(session);
    opts.push({ value: session.session_id, label: `${session.session_id} · ${session.subject_filter || '全部'} · ${p.feedback_count}/${p.total} 题${p.pending_count ? ` · 待录 ${p.pending_count}` : ' · 已完成'}` });
  });
  if (active && !sessions.some(s => s.session_id === active)) opts.push({ value: active, label: `${active}（不在列表中）` });
  return opts;
}

function sessionInfo(session, s, active) {
  if (!session) return active ? html`已导入 <strong>${s.rows.length}</strong> 题（Session ${active} 不在列表中）` : (s.rows.length ? html`已导入 <strong>${s.rows.length}</strong> 条作答（未关联 Session）` : '');
  const p = fbSessionProgress(session);
  return html`<strong>${p.feedback_count}/${p.total}</strong> 已录入 · ${p.pending_count ? html`还剩 <strong>${p.pending_count}</strong> 题待录入` : '本 Session 已全部录入'}`;
}

function topBar(s, env) {
  const active = env.activeId;
  return html`<section class="fbw-bar" data-key="bar" aria-label="反馈录入设置">
  <div class="fbw-bar__pick" data-key="pick" data-change="feedback.session">
    <label class="fbw-bar__cap" for="fb-session-picker">继续录入 Session</label>
    ${select({ id: 'fb-session-picker', label: '继续录入 Session', options: sessionOptions(env.sessions, active), value: active, disabled: s.submitting })}
  </div>
  <div class="fbw-bar__acts" data-key="acts">
    ${button({ label: '刷新', icon: 'refresh', action: 'feedback.refresh', loading: s.sessionsLoading, title: '刷新 Session 进度' })}
    ${button({ label: '读剪贴板填写', icon: 'download', variant: 'primary', action: 'feedback.readClipboard', disabled: s.submitting, title: '读取剪贴板里的 OMR /result 顶层 JSON 或反馈 JSON，按题号自动填写本 Session' })}
    ${button({ label: '添加行', icon: 'plus', action: 'feedback.addRow', disabled: s.submitting })}
  </div>
  <p class="fbw-bar__info" data-key="info" role="status">${sessionInfo(env.session, s, active)}</p>
  ${s.sessionsError ? html`<div class="fbw-bar__err" data-key="err">${status({ tone: 'danger', text: `Session 列表读取失败：${s.sessionsError}。点「刷新」重试。` })}</div>` : ''}
</section>`;
}

// ── 导入折叠面板（答题卡 / 屏幕版 / AI）──────────────────────────────────────────
function importPanel(s) {
  return html`<section class="${cls('fbw-import', s.importOpen && 'is-open')}" data-key="import">
  <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm fbw-import__toggle" data-action="feedback.toggleImport" aria-expanded="${s.importOpen ? 'true' : 'false'}" aria-controls="fbw-import-body">${icon(s.importOpen ? 'chevron-down' : 'chevron-right')}<span class="ui-btn__label">导入反馈：答题卡扫描 / 屏幕版 / AI</span></button>
  ${s.importOpen ? html`<div class="fbw-import__body" id="fbw-import-body" data-key="body">
    <p class="fbw-import__hint">
      <strong>答题卡：</strong>先在上面选中这张卡对应的 Session，在 OMR 识别详情页点「复制结果 JSON」（来自 <code>/api/v1/recognitions/&lt;id&gt;/result</code>，顶层含 <code>recognition_id / template_id / mode / status / questions / unresolved</code>）。回本页点「读剪贴板填写」，或在本页空白处按 ${kbd('Ctrl', 'V')}。题号按 Session 的固定条目顺序对应题目身份。
      <strong>屏幕版：</strong>复习完后在「作答情况」抽屉点「复制作答 JSON」并粘贴。<strong>AI：</strong>先复制提示词，把纸面批改结果发给 AI，让它整理成同一份反馈 JSON 后粘贴。
    </p>
    <p class="fbw-import__warn">${icon('alert-triangle')}<span>只接受上述 <code>/result</code> 顶层协议；旧的原始识别记录 <code>items</code>、裸数组和包装层会明确拒绝。<code>unresolved</code> 涉及的题不会自动猜测，字段与状态会写进备注留给人工。已归档、停用或身份未确认的条目保留原序号，但不能自动录入。提交前请对着中栏题面核一遍。</span></p>
    <div class="fbw-import__row">${button({ label: '复制 AI 反馈提示词', icon: 'copy', size: 'sm', action: 'feedback.copyPrompt' })}${s.promptStatus ? status({ tone: TONE[s.promptStatus.tone] || 'neutral', text: s.promptStatus.text }) : ''}</div>
    <textarea class="fbw-import__box ui-input" id="fb-json" rows="5" data-input="feedback.draft"${s.submitting ? html` disabled` : ''} placeholder='粘贴 OMR /result 顶层 JSON，或反馈 JSON（{"type":"omrs-feedback","session_id":"EXP-…","items":[{"uid":"…","is_correct":true,"sub_score":9}]}）'>${s.importText || ''}</textarea>
    <div class="fbw-import__row">${button({ label: '导入 JSON', icon: 'check', variant: 'primary', size: 'sm', action: 'feedback.importBox', disabled: s.submitting })}${s.importStatus ? html`<span class="fbw-import__status ${cls(`is-${s.importStatus.tone}`)}">${raw(s.importStatus.html)}</span>` : ''}</div>
  </div>` : ''}
</section>`;
}

// ── rail：全部题目 ────────────────────────────────────────────────────────────────
function railMark(entry, rows) {
  if (entry.recorded) return html`<span class="fbw-mk is-done" aria-label="已录入">${icon('check-circle')}</span>`;
  const row = entry.index >= 0 ? rows[entry.index] : null;
  if (row?.correct === true) return html`<span class="fbw-mk is-ok" aria-label="判对">${icon('check')}</span>`;
  if (row?.correct === false) return html`<span class="fbw-mk is-no" aria-label="判错">${icon('x')}</span>`;
  return html`<span class="fbw-mk is-up" aria-label="未判定"></span>`;
}

// 唯一 key：有对应行的用行下标（行下标唯一），只读的已录入题用 uid（Session 内 uid 已去重）
const railKey = entry => `${entry.index}|${entry.index >= 0 ? '' : entry.uid}`;

function railItem(entry, at, s, env) {
  const row = entry.index >= 0 ? env.rows[entry.index] : null;
  const state = entry.recorded ? 'done' : row?.correct === true ? 'ok' : row?.correct === false ? 'no' : 'up';
  const meta = entry.uid ? metaText(env.items, entry.uid) : '新增行';
  return html`<li class="fbw-q-item" data-key="${railKey(entry)}"><button type="button" class="${cls('fbw-q', `is-${state}`)}" data-action="feedback.go" data-arg="${at}"${at === s.cursor ? html` aria-current="step"` : ''} title="${entry.uid || '（待填 UID）'}">
    <span class="fbw-q__n">${entry.number || at + 1}</span>
    <span class="fbw-q__main"><strong class="fbw-q__uid">${entry.uid || '（待填 UID）'}</strong><small class="fbw-q__meta">${meta}</small></span>
    ${railMark(entry, env.rows)}
  </button></li>`;
}

function rail(s, env) {
  const entries = env.entries;
  if (!entries.length) {
    return html`<aside class="fbw-rail" data-key="rail" aria-label="题目列表">${empty({ icon: 'inbox', title: env.activeId ? '本 Session 已全部录入' : '还没有待录入的题', hint: env.activeId ? '换一个 Session，或点「添加行」手动录入。' : '选择一个 Session，或点「添加行」手动录入。', compact: true })}</aside>`;
  }
  return html`<aside class="fbw-rail" data-key="rail" aria-label="题目列表"><ol class="fbw-rail__list">${each(entries, railKey, (entry, i) => railItem(entry, i, s, env))}</ol></aside>`;
}

// ── stage：题面（qview 挂载点，morph 不碰）───────────────────────────────────────
function stage(s, env) {
  const entries = env.entries;
  const entry = entries[s.cursor];
  if (entry?.availability && entry.availability !== 'active') return html`<div class="fbw-stage" data-key="stage">${empty({ icon: 'alert-triangle', title: '此题暂不可反馈', hint: entry.availability === 'unresolved' ? '题目身份无法自动确认，请在复习调度的计划详情手动绑定。' : '题目已归档或停用，历史条目保留。', bordered: true })}</div>`;
  const uid = entry?.uid || '';
  if (!uid) {
    return html`<div class="fbw-stage" data-key="stage">${empty({ icon: 'file', title: entries.length ? '先填写这一行的 UID' : '这里显示题面与答案', hint: entries.length ? '填好 UID 后，这里显示题面、答案与做题记录。' : '选择一个 Session 或添加一行后，这里显示题目。', bordered: true })}</div>`;
  }
  return html`<div class="fbw-stage" data-key="stage"><div class="fbw-stage__qv" data-key="qv:${uid}" data-morph="skip" data-qv-host data-uid="${uid}"></div></div>`;
}

// ── 判定面板 ──────────────────────────────────────────────────────────────────────
function tally(rows) {
  const total = rows.length;
  if (!total) return '';
  const ok = rows.filter(r => r.correct === true).length;
  const no = rows.filter(r => r.correct === false).length;
  return html`<div class="fbw-tally" data-key="tally">
    <div class="fbw-tally__st"><span class="is-ok">对 ${ok}</span><span class="is-no">错 ${no}</span><span class="is-up">未判 ${total - ok - no}</span></div>
    <svg class="fbw-tally__bar" viewBox="0 0 100 6" preserveAspectRatio="none" aria-hidden="true"><rect class="is-ok" x="0" width="${ok / total * 100}" height="6"></rect><rect class="is-no" x="${ok / total * 100}" width="${no / total * 100}" height="6"></rect></svg>
    <div class="fbw-tally__sub">本批共 ${total} 题</div>
  </div>`;
}

function labelControls(row, env) {
  const item = row && row.uid ? env.items.find(x => x.uid === String(row.uid || '').trim()) : null;
  if (!item) return html`<div class="fbw-labels__hint" data-key="labels">填写有效 UID 后可编辑标记。</div>`;
  const current = new Set(item.labels || []);
  const recent = listLabels().slice(0, 4);
  return html`<div class="fbw-labels" data-key="labels">
    <div class="fbw-labels__head"><span>标记</span>${button({ label: '编辑标记', icon: 'plus', variant: 'ghost', size: 'sm', action: 'feedback.labels' })}</div>
    <div class="fbw-labels__list">${(item.labels || []).length ? labelChips(item.labels) : html`<span class="fbw-labels__none">暂无标记</span>`}</div>
    ${recent.length ? html`<div class="fbw-labels__quick">${each(recent, l => l.name, l => html`<button type="button" class="${cls('ui-btn', 'ui-btn--sm', 'ui-btn--ghost', 'fbw-lblq', current.has(l.name) && 'is-on')}" data-key="${l.name}" data-action="feedback.label" data-arg="${l.name}" aria-pressed="${current.has(l.name) ? 'true' : 'false'}" title="${l.name}">${labelChip(l.name)}</button>`)}<span class="fbw-labels__hint">最近标记，点击切换</span></div>` : ''}
  </div>`;
}

function submitBar(s, env) {
  const c = env.counts;
  return html`<div class="fbw-panel__submit" data-key="submit">
    ${button({ label: s.submitting ? '正在提交' : (c.ready ? `提交 ${c.ready} 道` : '提交反馈'), variant: 'primary', icon: 'send', action: 'feedback.submit', loading: s.submitting, disabled: !c.ready })}
    ${s.status ? status({ tone: TONE[s.status.tone] || 'neutral', text: s.status.text, block: true }) : ''}
    <p class="fbw-panel__keys">${kbd('J')}${kbd('K')} 切题 · ${kbd('1')} 对 ${kbd('2')} 错 · ${kbd('0–9')} 打分 · ${kbd('E')} 编辑 · ${kbd('Ctrl', 'V')} 读答题卡 · ${kbd('Ctrl', 'Enter')} 提交</p>
  </div>`;
}

function panel(s, env) {
  const entries = env.entries;
  const entry = entries[s.cursor];
  const head = entry ? html`<header class="fbw-panel__head" data-key="head"><h3 class="fbw-panel__title">第 ${entry.number || s.cursor + 1} 题</h3><span class="fbw-panel__uid">${entry.uid || '待填 UID'}</span></header>` : html`<header class="fbw-panel__head" data-key="head"><h3 class="fbw-panel__title">判定</h3></header>`;
  let bodyBlock;
  if (!entry) bodyBlock = html`<div class="fbw-panel__empty" data-key="body">${empty({ icon: 'edit', title: '没有待判定的题目', hint: '选择一个 Session 或点「添加行」。', compact: true })}</div>`;
  else if (entry.availability && entry.availability !== 'active') bodyBlock = html`<div class="fbw-readonly" data-key="body">${icon('lock')}${entry.availability === 'unresolved' ? '身份待确认，请到计划详情绑定题目。' : '题目已归档或停用，暂不能录入反馈。'}</div>`;
  else if (entry.recorded) bodyBlock = html`<div class="fbw-readonly" data-key="body">${icon('lock')}本题已录入反馈。如需修正请到「数据复盘 → 历史记录」操作，不要重复提交。</div>`;
  else {
    const row = entry.index >= 0 ? env.rows[entry.index] : null;
    if (!row) bodyBlock = html`<div class="fbw-panel__empty" data-key="body">这一行已被移除。</div>`;
    else {
      const showUid = !env.session || entry.extra || !entry.uid;
      const score = row.score == null ? 5 : row.score;
      const verdict = (value, label, ico, key) => html`<button type="button" class="${cls('ui-btn', 'fbw-verdict__btn', `fbw-verdict__btn--${value ? 'ok' : 'no'}`)}" data-action="feedback.verdict" data-arg="${value ? '1' : '0'}" aria-pressed="${row.correct === value ? 'true' : 'false'}"${s.submitting ? html` disabled` : ''}>${icon(ico)}<span>${label}</span>${kbd(key)}</button>`;
      bodyBlock = html`<div class="fbw-form" data-key="body">
        ${showUid ? html`<label class="fbw-field" data-key="uid"><span class="fbw-field__label">UID</span><input class="ui-input" list="uid-list" value="${row.uid || ''}" data-change="feedback.uid"${s.submitting ? html` disabled` : ''} placeholder="输入或选择 UID"></label>` : ''}
        <div class="fbw-verdict" role="group" aria-label="判定对错" data-key="verdict">${verdict(true, '对', 'check', '1')}${verdict(false, '错', 'x', '2')}</div>
        <label class="fbw-score" data-key="score"><span class="fbw-score__label">主观分</span><input class="fbw-score__input" type="range" min="0" max="10" step="1" value="${score}" data-input="feedback.score"${s.submitting ? html` disabled` : ''} aria-valuetext="${score} 分"><output class="fbw-score__value">${score}</output></label>
        <label class="fbw-field" data-key="note"><span class="fbw-field__label">备注</span><input class="ui-input" value="${row.note || ''}" data-input="feedback.note"${s.submitting ? html` disabled` : ''} placeholder="页码 / 错因（可选）"></label>
        ${labelControls(row, env)}
        <div class="fbw-form__acts" data-key="acts">
          ${row.correct === false && row.uid ? button({ label: '加入展示板', icon: 'bookmark', size: 'sm', action: 'feedback.board' }) : ''}
          ${button({ label: '移除此行', icon: 'trash', variant: 'ghost', size: 'sm', action: 'feedback.drop', disabled: s.submitting })}
        </div>
      </div>`;
    }
  }
  return html`<div class="fbw-panel" data-key="panel" aria-label="判定 · 统计 · 提交">
    ${head}
    ${bodyBlock}
    ${tally(env.rows)}
    ${submitBar(s, env)}
  </div>`;
}

// ── 状态行 ────────────────────────────────────────────────────────────────────────
function statusBar(s) {
  if (!s.lastResult && !s.status) return '';
  return html`<div class="fbw-statusbar" data-key="statusbar">
    ${s.lastResult ? button({ label: '查看本次结果', icon: 'list', size: 'sm', action: 'feedback.reopenResults' }) : ''}
  </div>`;
}

/** 提交结果明细（弹进 ui/dialog 的 body）。 */
export function resultBody(result) {
  if (!result || !result.rows?.length) return html`<div class="fbw-result__empty">这次没有返回任何处理结果。</div>`;
  const pct = v => formatPercent(Number(v) || 0);
  return html`<div class="fbw-result">
    <p class="fbw-result__meta">${result.okCount}/${result.total} 条写入成功${result.total - result.okCount > 0 ? html` · ${result.total - result.okCount} 条失败` : ''}${result.sessionId ? html` · Session ${result.sessionId}` : ''}${result.at ? html` · ${result.at}` : ''}</p>
    <ul class="fbw-result__list">${each(result.rows, (r, i) => `${r.uid}:${i}`, r => {
      const ok = r.status === 'ok';
      const detail = ok ? `${pct(r.old_mastery)} → ${pct(r.new_mastery)}${r.new_interval != null ? ` · ${r.new_interval}d · ${r.new_due_date || '?'}` : ''}${r.source ? ` [${r.source === 'due' ? '到期' : '熟练度'}]` : ''}` : (r.msg || '失败');
      return html`<li class="${cls('fbw-result__row', ok ? 'is-ok' : 'is-err')}"><span class="fbw-result__uid">${r.uid}</span>${r.label ? html`<span class="fbw-result__label">${r.label}</span>` : ''}<span class="fbw-result__delta">${detail}</span></li>`;
    })}</ul>
  </div>`;
}

/** 三栏 DOM 顺序：rail → stage → panel（窄屏竖排；>1160 由 CSS 摆成三列）。 */
export function view(s, env) {
  return html`<div class="fbw" data-key="fbw">
  ${topBar(s, env)}
  ${importPanel(s)}
  <div class="fbw-work" data-key="work">
    ${rail(s, env)}
    ${stage(s, env)}
    ${panel(s, env)}
  </div>
  ${statusBar(s)}
</div>`;
}
