/**
 * 共享题目视图 qview 的纯函数部分（从旧 assets/qview.js 迁入）：题目详情 + 投影条目 → HTML 字符串，node 下可单测。
 * 挂载、失效重绘、题目弹窗在 mount.js。工具按钮只带 data-qv-act，由 mount.js 的委托处理器分发，HTML 里不拼函数名。
 * 读旧全局（getDueDays、getItemByUid）一律带守卫：node 单测与旧函数缺席时退化为空。标记芯片用 domain/labels（P5 第 4 轮起）。
 */
import { chipsHtml } from '../labels/chips.js';
import { escape } from '../../core/html.js';
import { renderMd } from './markdown.js';
import { qRecordsFromDetail, qHistoryStats } from './records.js';
import { dueDays, itemOf } from '../items.js';

const num = (value, fallback = 0) => { const n = Number(value); return Number.isFinite(n) ? n : fallback; };

export const QV_DEFAULTS = Object.freeze({
  layout: 'split',      // 'split' 双栏 / 'stack' 单栏；挂载点窄于 680px 时由容器查询自动塌成单栏
  reveal: true,         // false 时不渲染答案 DOM，只给「显示答案」按钮
  showAnswer: true,
  showNotes: true,
  showHistory: true,    // 题目详情最下面的「记录」通栏模块
  showMeta: true,       // 头部 UID / 科目 / 难度 / 熟练度 / 到期
  bare: false,          // true 时去掉正文的边框底色，供画廊缩略卡嵌套
  actions: [],          // 'edit' | 'board' | 'labels' | 'suspend' | 'delete' | 'open'
  clamp: 0,             // >0 时正文按行数截断（1–12）
  revealLabel: '显示答案',
});

/** 画廊 / 选题卡片用的缩略预设（旧 questions.js 的 QV_CARD_OPTS 另有一份按密度调整的副本，随题库页迁移合并）。 */
export const QV_CARD_OPTS = Object.freeze({ layout: 'stack', showMeta: false, showAnswer: false, showNotes: false, showHistory: false, actions: [], bare: true, clamp: 5 });

export const qvOptions = opts => ({ ...QV_DEFAULTS, ...(opts || {}) });

export function qvChips(detail, item) {
  const chips = [];
  const push = (text, cls) => {
    const value = String(text ?? '').trim();
    if (value) chips.push(`<span class="chip${cls ? ` ${cls}` : ''}">${escape(value)}</span>`);
  };
  push(detail.subject || item.subject || '');
  push(detail.category || item.category || '');
  const difficulty = detail.difficulty ?? item.difficulty;
  if (String(difficulty ?? '').trim()) push(`难度 ${difficulty}`);
  if (item.mastery != null) push(`熟练度 ${(num(item.mastery, 0) * 100).toFixed(0)}%`);
  const days = dueDays(item);
  if (days != null) {
    if (days < 0) push(`逾期 ${Math.abs(days)} 天`, 'warn');
    else if (days === 0) push('今日到期', 'warn');
    else push(`${days} 天后到期`);
  }
  if (item.suspended) push('已停用', 'muted');
  // 复燃题的 Due_Date 是击杀时的旧值，只有「逾期 N 天」会读成没做完的旧账
  if (item.is_revived) push(`复燃 · 已休眠 ${num(item.dormant_days, 0)} 天`, 'warn');
  const uid = detail.uid || item.uid || '';
  // 标记以题目列表为准：打标记是乐观更新列表后立刻重绘，这时重新拉到的详情可能还是保存前的（请求先于保存到达服务端）
  const labels = chipsHtml(Array.isArray(item.labels) ? item.labels : (detail.labels || []), { lg: true, add: true, uid });
  return chips.join('') + labels;
}

const TOOL = {
  edit: () => '<button type="button" class="ui-btn ui-btn--sm" data-qv-act="edit">编辑 Markdown</button>',
  suspend: uid => (itemOf(uid)?.suspended
    ? '<button type="button" class="ui-btn ui-btn--sm" data-qv-act="resume">恢复题目</button>'
    : '<button type="button" class="ui-btn ui-btn--sm" data-qv-act="suspend">停用题目</button>'),
  delete: () => '<button type="button" class="ui-btn ui-btn--sm ui-btn--danger" data-qv-act="delete">删除题目</button>',
  open: () => '<button type="button" class="ui-btn ui-btn--sm" data-qv-act="open">在题目库打开</button>',
  board: () => '<button type="button" class="ui-btn ui-btn--sm" data-qv-act="board" data-board-hint>加入展示板</button>',
  labels: () => '<button type="button" class="ui-btn ui-btn--sm" data-qv-act="labels">编辑标记</button>',
};

export function qvToolsHtml(uid, actions) {
  const buttons = (actions || []).map(action => (TOOL[action] ? TOOL[action](uid) : '')).filter(Boolean).join('');
  return buttons ? `<div class="qv-tools">${buttons}</div>` : '';
}

const clampLines = value => Math.max(1, Math.min(12, Math.round(num(value, 0))));

export function qvHtml(q, item, opts) {
  const o = qvOptions(opts);
  const detail = q || {};
  const model = item || {};
  const uid = detail.uid || model.uid || '';
  const clamp = o.clamp > 0 ? ` data-clamp="${clampLines(o.clamp)}"` : '';

  if (detail._fallback) {
    return `<div class="qv qv-stack" data-qv-uid="${escape(uid)}">
      <div class="qv-fallback">
        <div>无法加载题目预览（后端未响应或题目已被移除）。</div>
        <button type="button" class="ui-btn ui-btn--sm" data-qv-act="retry">重试</button>
      </div>
    </div>`;
  }

  const classes = ['qv', o.layout === 'split' ? 'qv-split' : 'qv-stack'];
  if (o.bare) classes.push('qv-bare');
  if (o.clamp > 0) classes.push('qv-clamp');

  const tools = qvToolsHtml(uid, o.actions);
  let head = '';
  if (o.showMeta) {
    head = `<header class="qv-head">
      <div class="qv-id">${escape(uid)}</div>
      <div class="qv-chips">${qvChips(detail, model)}</div>
      ${tools}
    </header>`;
  } else if (tools) {
    head = `<header class="qv-head qv-head-slim">${tools}</header>`;
  }

  const question = `<section class="qv-q">
    <div class="qv-label">题目</div>
    <div class="q-md"${clamp}>${renderMd(detail.question || '（无题目内容）')}</div>
  </section>`;

  const side = [];
  if (o.showAnswer) {
    if (!o.reveal) {
      side.push(`<div class="qv-locked"><button type="button" class="ui-btn ui-btn--primary" data-qv-act="reveal">${escape(o.revealLabel)}</button></div>`);
    } else {
      side.push('<div class="qv-label">答案</div>');
      side.push(`<div class="q-md q-answer-md">${renderMd(detail.answer || '（无答案内容）')}</div>`);
    }
  }
  if (o.showNotes && o.reveal && String(detail.notes || '').trim()) {
    side.push('<div class="qv-label">备注 / 错因</div>');
    side.push(`<div class="q-md">${renderMd(detail.notes)}</div>`);
  }
  const answer = side.length ? `<section class="qv-a">${side.join('')}</section>` : '';
  const record = o.showHistory ? qvRecordHtml(detail, model) : '';

  return `<div class="${classes.join(' ')}" data-qv-uid="${escape(uid)}" data-reveal="${o.reveal ? '1' : '0'}">
    ${head}${question}${answer}${record}
  </div>`;
}

// ── 记录模块：四个派生数 + 主观分走势 + 明细（首屏 3 条，其余折叠）。只报异常：连错 ≥2 才出提示行 ──
function recordSparkHtml(records) {
  const width = 100;
  const height = 34;
  const count = records.length;
  const x = i => (count === 1 ? width / 2 : (i / (count - 1)) * width);
  const y = score => height - (Math.max(0, Math.min(10, num(score, 0))) / 10) * height;
  const dots = records.map((r, i) =>
    `<circle cx="${x(i).toFixed(1)}" cy="${y(r.score).toFixed(1)}" r="2.4" fill="${r.correct ? 'var(--success)' : 'var(--danger)'}"><title>${escape(`${r.date} ${r.correct ? '对' : '错'} ${r.score} 分`)}</title></circle>`).join('');
  const line = count > 1
    ? `<polyline points="${records.map((r, i) => `${x(i).toFixed(1)},${y(r.score).toFixed(1)}`).join(' ')}" fill="none" stroke="var(--accent-muted)" stroke-width="1" vector-effect="non-scaling-stroke"/>`
    : '';
  return `<div class="qv-rec-spark"><svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="主观分走势">${line}${dots}</svg></div>
    <div class="qv-rec-axis"><span>${escape(records[0].date)}</span><span>主观分 0–10</span><span>${escape(records[count - 1].date)}</span></div>`;
}

function recordRowHtml(r) {
  return `<div class="qv-rec-row">
    <span class="qv-rec-date">${escape(r.date)}${r.time ? `<small> ${escape(r.time)}</small>` : ''}</span>
    <span class="${r.correct ? 'qv-rec-ok' : 'qv-rec-no'}">${r.correct ? '对' : '错'}</span>
    <span class="qv-rec-score">${escape(r.score)} 分</span>
    <span class="qv-rec-note">${escape(r.note || '')}</span>
  </div>`;
}

export function qvRecordHtml(detail) {
  const records = qRecordsFromDetail(detail);
  const stats = qHistoryStats(records);
  const head = '<div class="qv-label">记录</div>';
  if (!stats.count) {
    // 只在「老后端没给 records、且 Markdown 历史被手改成别的写法」时原样保留原文；后端给了 records（哪怕为空）就不看 Markdown
    const rawText = records.source === 'markdown' ? String(detail?.history || '').trim() : '';
    const body = rawText
      ? `<pre class="qv-rec-raw">${escape(rawText)}</pre>`
      : '<div class="qv-rec-empty">还没练过。加入下一次复习后，这里会出现次数、正确率和主观分走势。</div>';
    return `<section class="qv-rec">${head}${body}</section>`;
  }
  const alert = stats.tailWrong >= 2
    ? `<div class="qv-rec-alert">最近连错 ${stats.tailWrong} 次${stats.last.note ? `，上次卡在「${escape(stats.last.note)}」` : '，建议重看错因'}</div>`
    : '';
  const nums = [
    ['count', `${stats.count}`, '练习次数'],
    ['rate', `${stats.rate}%`, `正确 ${stats.correct}/${stats.count}`],
    ['avg', `${stats.avgScore}`, '平均主观分'],
    ['gap', stats.avgGap == null ? '—' : `${stats.avgGap} 天`, '平均间隔'],
  ].map(([key, value, label]) =>
    `<div class="qv-rec-num${key === 'rate' && stats.rate < 60 ? ' bad' : ''}"><b>${escape(value)}</b><span>${escape(label)}</span></div>`).join('');
  const newest = [...records].reverse();
  const rest = newest.slice(3);
  const more = rest.length
    ? `<details class="qv-rec-more"><summary>其余 ${rest.length} 条</summary>${rest.map(recordRowHtml).join('')}</details>`
    : '';
  return `<section class="qv-rec">${head}${alert}
    <div class="qv-rec-nums">${nums}</div>
    ${recordSparkHtml(records)}
    <div class="qv-rec-list">${newest.slice(0, 3).map(recordRowHtml).join('')}</div>${more}
  </section>`;
}

// ── 共享画廊卡片：题库画廊、展示板画廊、选题弹窗共用同一副骨架。只收调用方算好的 HTML 片段，不读题库全局 ──
export function qvGalleryCard(spec) {
  const card = spec || {};
  const uid = String(card.uid || '');
  const preview = card.previewHtml || '<div class="preview-placeholder">正在加载题目预览…</div>';
  const meta = card.metaHtml ? `<div class="gc-meta">${card.metaHtml}</div>` : '';
  const more = card.menuHtml ? `<span class="gc-more">${card.menuHtml}</span>` : '';
  return `<div class="gallery-card ${card.className || ''}" ${card.rowAttr || ''}>
      <div class="gallery-head">
        ${card.leadHtml || ''}
        <span class="gc-id">${card.idHtml || ''}</span>
        <span class="gc-flags">${card.flagsHtml || ''}</span>
        ${more}
      </div>
      ${meta}
      <div class="gallery-preview ${card.previewClass || ''}" data-question-preview-uid="${escape(uid)}">${preview}</div>
      <div class="gc-foot">
        ${card.footHtml || ''}
        <span class="q-label-cell gc-labels" data-lbl-target="${escape(uid)}">${card.labelsHtml || ''}</span>
      </div>
    </div>`;
}

/** UID 里重复了分类名时拆成「分类 + 序号」两截：一屏几十张卡时，重复的前缀纯属噪音。 */
export function qvGalleryIdHtml(uid, category) {
  const id = String(uid || '');
  const cat = String(category || '');
  if (cat && id.startsWith(cat)) {
    const rest = id.slice(cat.length).replace(/^[-_·\s]+/, '');
    return `<span class="gc-cat">${escape(cat)}</span>${rest ? `<span class="gc-num">${escape(rest)}</span>` : ''}`;
  }
  return `<span class="gc-num">${escape(id)}</span>`;
}
