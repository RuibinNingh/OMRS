// === assets/qview.js — 共享题目视图（qview）：题面 / 答案双栏 ===
// 供题目 Modal、反馈工作台、即时练习、画廊卡片复用，收敛原来三处各自为政的题目渲染副本。
// 依赖 questions.js 的 renderMdContent / ensureQuestionDetail / QUESTION_CACHE，
// 以及 core.js 的 escapeHtml / escapeAttr / getItemByUid / getDueDays / asNumber
// 与记录模块用到的 qRecordsFromDetail / qHistoryStats（v1.16.0，v1.16.1 改读 Ledger），
// 因此 <script> 必须排在 questions.js 之后。
// 约定：本文件不写业务逻辑，工具按钮只转调 questions.js 已有的全局函数；
// DOM 里不拼函数名，所有交互走 data-qv-act 事件委托。

const QV_DEFAULTS = {
  layout: 'split',      // 'split' 双栏 / 'stack' 单栏；窄容器由容器查询自动降级
  reveal: true,         // false 时不渲染答案 DOM，只给「显示答案」按钮
  showAnswer: true,
  showNotes: true,
  showHistory: true,    // 题目详情最下面的「记录」通栏模块（v1.16.0），画廊卡 / 即时练习关掉
  showMeta: true,       // 头部 UID / 科目 / 难度 / 熟练度 / 到期
  bare: false,          // true 时去掉正文的边框底色，供画廊缩略卡嵌套使用
  actions: [],          // 'edit' | 'suspend' | 'delete' | 'open'
  clamp: 0,             // >0 时正文按行数截断
  revealLabel: '显示答案',
};

const QV_MOUNTS = new Map();        // 挂载点元素 -> {uid, opts}
const QV_CONTEXTS = {};             // 上下文名 -> uid 序列，供 Modal 翻页使用
let QV_NAV = { list: [], index: -1 };

// 各列表渲染时登记「当前上下文的 uid 序列」，viewQ(uid,'q') 即可在该序列内翻页。
// 用上下文名而不是把整个数组拼进行内 onclick。
function qvSetContext(name, uids) {
  QV_CONTEXTS[name] = [...new Set((uids || []).map(uid => String(uid || '').trim()).filter(Boolean))];
  return QV_CONTEXTS[name];
}
function qvContext(name) { return QV_CONTEXTS[name] || []; }

function qvOptions(opts) { return Object.assign({}, QV_DEFAULTS, opts || {}); }

function qvChips(detail, item) {
  const chips = [];
  const push = (text, cls) => {
    const value = String(text ?? '').trim();
    if (value) chips.push(`<span class="chip${cls ? ' ' + cls : ''}">${escapeHtml(value)}</span>`);
  };
  push(detail.subject || item.subject || '');
  push(detail.category || item.category || '');
  const difficulty = detail.difficulty ?? item.difficulty;
  if (String(difficulty ?? '').trim()) push(`难度 ${difficulty}`);
  if (item.mastery != null) push(`熟练度 ${(asNumber(item.mastery, 0) * 100).toFixed(0)}%`);
  const dueDays = typeof getDueDays === 'function' ? getDueDays(item) : null;
  if (dueDays != null) {
    if (dueDays < 0) push(`逾期 ${Math.abs(dueDays)} 天`, 'warn');
    else if (dueDays === 0) push('今日到期', 'warn');
    else push(`${dueDays} 天后到期`);
  }
  if (item.suspended) push('已停用', 'muted');
  const uid = detail.uid || item.uid || '';
  const labels = typeof lblChips === 'function'
    ? lblChips(detail.labels || item.labels || [], { lg: true, add: true, uid })
    : '';
  return chips.join('') + labels;
}

function qvToolsHtml(uid, actions) {
  const buttons = (actions || []).map(action => {
    switch (action) {
      case 'edit':
        return '<button type="button" class="btn sm" data-qv-act="edit">编辑 Markdown</button>';
      case 'suspend': {
        const suspended = typeof getItemByUid === 'function' && getItemByUid(uid)?.suspended;
        return suspended
          ? '<button type="button" class="btn sm" data-qv-act="resume">恢复题目</button>'
          : '<button type="button" class="btn sm" data-qv-act="suspend">停用题目</button>';
      }
      case 'delete':
        return '<button type="button" class="btn sm danger" data-qv-act="delete">删除题目</button>';
      case 'open':
        return '<button type="button" class="btn sm" data-qv-act="open">在题目库打开</button>';
      case 'board':
        return '<button type="button" class="btn sm" data-qv-act="board" data-board-hint>加入展示板</button>';
      case 'labels':
        return '<button type="button" class="btn sm" data-qv-act="labels">编辑标记</button>';
      default:
        return '';
    }
  }).filter(Boolean).join('');
  return buttons ? `<div class="qv-tools">${buttons}</div>` : '';
}

// 纯函数：给定题目详情与投影条目产出 HTML，方便在 node 侧单测
function qvHtml(q, item, opts) {
  const o = qvOptions(opts);
  const detail = q || {};
  const model = item || {};
  const uid = detail.uid || model.uid || '';
  const clampStyle = o.clamp > 0 ? ` style="--qv-clamp:${Math.max(1, Math.round(o.clamp))}"` : '';

  if (detail._fallback) {
    return `<div class="qv qv-stack" data-qv-uid="${escapeAttr(uid)}">
      <div class="qv-fallback">
        <div>无法加载题目预览（后端未响应或题目已被移除）。</div>
        <button type="button" class="btn sm" data-qv-act="retry">重试</button>
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
      <div class="qv-id">${escapeHtml(uid)}</div>
      <div class="qv-chips">${qvChips(detail, model)}</div>
      ${tools}
    </header>`;
  } else if (tools) {
    head = `<header class="qv-head qv-head-slim">${tools}</header>`;
  }

  const question = `<section class="qv-q">
    <div class="qv-label">题目</div>
    <div class="q-md"${clampStyle}>${renderMdContent(detail.question || '（无题目内容）')}</div>
  </section>`;

  const side = [];
  if (o.showAnswer) {
    if (!o.reveal) {
      side.push(`<div class="qv-locked"><button type="button" class="btn primary" data-qv-act="reveal">${escapeHtml(o.revealLabel)}</button></div>`);
    } else {
      side.push('<div class="qv-label">答案</div>');
      side.push(`<div class="q-md q-answer-md">${renderMdContent(detail.answer || '（无答案内容）')}</div>`);
    }
  }
  if (o.showNotes && o.reveal && String(detail.notes || '').trim()) {
    side.push('<div class="qv-label">备注 / 错因</div>');
    side.push(`<div class="q-md">${renderMdContent(detail.notes)}</div>`);
  }
  const answer = side.length ? `<section class="qv-a">${side.join('')}</section>` : '';
  const record = o.showHistory ? qvRecordHtml(detail, model) : '';

  return `<div class="${classes.join(' ')}" data-qv-uid="${escapeAttr(uid)}" data-reveal="${o.reveal ? '1' : '0'}">
    ${head}${question}${answer}${record}
  </div>`;
}

// === 记录模块（v1.16.0）===
// 原本是右栏里一个 <details> 包着 Markdown「## 历史」原文的 <pre>；现在改成题目详情最下面
// 一整块通栏模块：四个派生数 + 主观分走势 + 明细。数据来自 detail.records（Ledger 投影）；
// 老后端没给 records 时才退回解析 detail.history 的遗留行（见 core.js::qRecordsFromDetail）。
// 只报异常：连错 ≥2 才出提示行；顺利的题一个字都不多说。
function qvRecordSparkHtml(records) {
  const width = 100, height = 34, count = records.length;
  const x = index => count === 1 ? width / 2 : (index / (count - 1)) * width;
  const y = score => height - (Math.max(0, Math.min(10, asNumber(score, 0))) / 10) * height;
  const dots = records.map((record, index) =>
    `<circle cx="${x(index).toFixed(1)}" cy="${y(record.score).toFixed(1)}" r="2.4" fill="${record.correct ? 'var(--green)' : 'var(--red)'}"><title>${escapeHtml(`${record.date} ${record.correct ? '对' : '错'} ${record.score} 分`)}</title></circle>`).join('');
  const line = count > 1
    ? `<polyline points="${records.map((record, index) => `${x(index).toFixed(1)},${y(record.score).toFixed(1)}`).join(' ')}" fill="none" stroke="var(--accent-light)" stroke-width="1" vector-effect="non-scaling-stroke"/>`
    : '';
  return `<div class="qv-rec-spark"><svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="主观分走势">${line}${dots}</svg></div>
    <div class="qv-rec-axis"><span>${escapeHtml(records[0].date)}</span><span>主观分 0–10</span><span>${escapeHtml(records[count - 1].date)}</span></div>`;
}

function qvRecordRowHtml(record) {
  return `<div class="qv-rec-row">
    <span class="qv-rec-date">${escapeHtml(record.date)}${record.time ? `<small> ${escapeHtml(record.time)}</small>` : ''}</span>
    <span class="${record.correct ? 'qv-rec-ok' : 'qv-rec-no'}">${record.correct ? '对' : '错'}</span>
    <span class="qv-rec-score">${escapeHtml(record.score)} 分</span>
    <span class="qv-rec-note">${escapeHtml(record.note || '')}</span>
  </div>`;
}

function qvRecordHtml(detail, item) {
  const records = typeof qRecordsFromDetail === 'function' ? qRecordsFromDetail(detail) : [];
  const stats = typeof qHistoryStats === 'function' ? qHistoryStats(records) : { count: 0 };
  const head = '<div class="qv-label">记录</div>';
  if (!stats.count) {
    // 只在「老后端没给 records、且 Markdown 历史小节被手改成别的写法」时原样保留原文，不假装没有；
    // 后端已给 records（哪怕是空数组）时，Markdown 里的旧文本一律不管——它不是记录来源。
    const raw = records.source === 'markdown' ? String(detail?.history || '').trim() : '';
    const body = raw
      ? `<pre class="qv-rec-raw">${escapeHtml(raw)}</pre>`
      : '<div class="qv-rec-empty">还没练过。加入下一次复习后，这里会出现次数、正确率和主观分走势。</div>';
    return `<section class="qv-rec">${head}${body}</section>`;
  }
  const alert = stats.tailWrong >= 2
    ? `<div class="qv-rec-alert">最近连错 ${stats.tailWrong} 次${stats.last.note ? `，上次卡在「${escapeHtml(stats.last.note)}」` : '，建议重看错因'}</div>`
    : '';
  const nums = [
    ['count', `${stats.count}`, '练习次数'],
    ['rate', `${stats.rate}%`, `正确 ${stats.correct}/${stats.count}`],
    ['avg', `${stats.avgScore}`, '平均主观分'],
    ['gap', stats.avgGap == null ? '—' : `${stats.avgGap} 天`, '平均间隔'],
  ].map(([key, value, label]) =>
    `<div class="qv-rec-num${key === 'rate' && stats.rate < 60 ? ' bad' : ''}"><b>${escapeHtml(value)}</b><span>${escapeHtml(label)}</span></div>`).join('');
  const newest = [...records].reverse();
  const shown = newest.slice(0, 3), rest = newest.slice(3);
  const more = rest.length
    ? `<details class="qv-rec-more"><summary>其余 ${rest.length} 条</summary>${rest.map(qvRecordRowHtml).join('')}</details>`
    : '';
  return `<section class="qv-rec">${head}${alert}
    <div class="qv-rec-nums">${nums}</div>
    ${qvRecordSparkHtml(records)}
    <div class="qv-rec-list">${shown.map(qvRecordRowHtml).join('')}</div>${more}
  </section>`;
}

// 挂载：拉详情（走 ensureQuestionDetail 缓存）→ 渲染 → 登记到 QV_MOUNTS
async function qvRender(target, uid, opts) {
  const mount = typeof target === 'string' ? document.querySelector(target) : target;
  if (!mount) return null;
  const key = String(uid || '').trim();
  if (!key) { QV_MOUNTS.delete(mount); mount.innerHTML = ''; return null; }
  const options = qvOptions(opts);
  mount.dataset.qvMount = '1';
  QV_MOUNTS.set(mount, { uid: key, opts: options });
  if (!QUESTION_CACHE[key]) mount.innerHTML = '<div class="qv-loading">正在加载题目…</div>';
  const detail = await ensureQuestionDetail(key);
  const current = QV_MOUNTS.get(mount);
  if (!current || current.uid !== key) return null;   // 期间已切到别的题，丢弃这次结果
  const item = (typeof getItemByUid === 'function' && getItemByUid(key)) || {};
  mount.innerHTML = qvHtml(detail, item, current.opts);
  return detail;
}

// 失效重绘：清详情缓存，重绘所有挂着该 uid 的容器
async function qvInvalidate(uid) {
  const key = String(uid || '').trim();
  if (!key) return;
  delete QUESTION_CACHE[key];
  const targets = [];
  QV_MOUNTS.forEach((state, mount) => {
    if (state.uid === key && mount.isConnected) targets.push([mount, state.opts]);
    if (!mount.isConnected) QV_MOUNTS.delete(mount);
  });
  await Promise.all(targets.map(([mount, opts]) => qvRender(mount, key, opts)));
}

// 批量失效：反馈提交 / 历史修正后，题目的正式记录（detail.records）变了，
// 缓存里的详情就过期了。uids 给谁清谁；不给则清空整个 QUESTION_CACHE（历史修正可能波及任意题）。
async function qvInvalidateMany(uids) {
  const list = Array.isArray(uids) ? [...new Set(uids.map(uid => String(uid || '').trim()).filter(Boolean))] : null;
  if (list) { await Promise.all(list.map(uid => qvInvalidate(uid))); return; }
  Object.keys(QUESTION_CACHE).forEach(key => { delete QUESTION_CACHE[key]; });
  const targets = [];
  QV_MOUNTS.forEach((state, mount) => {
    if (mount.isConnected) targets.push([mount, state.uid, state.opts]); else QV_MOUNTS.delete(mount);
  });
  await Promise.all(targets.map(([mount, uid, opts]) => qvRender(mount, uid, opts)));
}

// 纯重绘：不动详情缓存，只把已挂载的容器按当前设置（如题面换行模式）重画一遍
function qvRerenderAll() {
  QV_MOUNTS.forEach((state, mount) => {
    if (!mount.isConnected) { QV_MOUNTS.delete(mount); return; }
    const detail = QUESTION_CACHE[state.uid];
    if (!detail) return;
    const item = (typeof getItemByUid === 'function' && getItemByUid(state.uid)) || {};
    mount.innerHTML = qvHtml(detail, item, state.opts);
  });
}

function qvGoQuestions(uid) {
  if (typeof closeModal === 'function') closeModal();
  if (typeof switchTab === 'function') switchTab('questions');
  const search = document.getElementById('q-search');
  if (search) search.value = uid;
  const suspended = document.getElementById('q-filter-suspended');
  if (suspended && typeof getItemByUid === 'function' && getItemByUid(uid)?.suspended) suspended.value = 'all';
  if (typeof filterQ === 'function') filterQ();
}

// === Modal 翻页 ===
function qvNavRender() {
  const box = document.getElementById('qv-nav');
  if (!box) return;
  const total = QV_NAV.list.length;
  const single = total <= 1;
  box.classList.toggle('is-single', single);
  const pos = document.getElementById('qv-nav-pos');
  if (pos) pos.textContent = single ? '' : `第 ${QV_NAV.index + 1} / ${total} 题`;
  const prev = box.querySelector('[data-qv-nav="prev"]');
  const next = box.querySelector('[data-qv-nav="next"]');
  if (prev) prev.disabled = single || QV_NAV.index <= 0;
  if (next) next.disabled = single || QV_NAV.index >= total - 1;
}

async function qvNavGo(step) {
  const index = QV_NAV.index + step;
  if (index < 0 || index >= QV_NAV.list.length) return;
  QV_NAV.index = index;
  await viewQ(QV_NAV.list[index]);
}
function qvNavPrev() { return qvNavGo(-1); }
function qvNavNext() { return qvNavGo(1); }

// === 事件委托：工具按钮 / 翻页 / 键盘 ===
function qvHandleClick(event) {
  const nav = event.target.closest?.('[data-qv-nav]');
  if (nav) { qvNavGo(nav.dataset.qvNav === 'prev' ? -1 : 1); return; }
  const button = event.target.closest?.('[data-qv-act]');
  if (!button) return;
  const root = button.closest('.qv');
  const uid = root?.dataset.qvUid || '';
  const mount = button.closest('[data-qv-mount]');
  const state = mount ? QV_MOUNTS.get(mount) : null;
  const action = button.dataset.qvAct;
  if (action === 'reveal') {
    if (state?.opts?.onReveal) state.opts.onReveal(state.uid || uid);
    return;
  }
  if (action === 'retry') { qvInvalidate(state?.uid || uid); return; }
  if (!uid) return;
  if (action === 'edit' && typeof openMarkdownEditor === 'function') openMarkdownEditor(uid);
  else if (action === 'board' && typeof boardQuickAdd === 'function') boardQuickAdd(uid, { anchor: button, direct: event.shiftKey });
  else if (action === 'labels' && typeof openLabelPicker === 'function') openLabelPicker(uid, button);
  else if (action === 'suspend' && typeof suspendQuestion === 'function') suspendQuestion(uid);
  else if (action === 'resume' && typeof resumeQuestion === 'function') resumeQuestion(uid);
  else if (action === 'delete' && typeof deleteQuestion === 'function') deleteQuestion(uid);
  else if (action === 'open') qvGoQuestions(uid);
}

function qvHandleKey(event) {
  const modal = document.getElementById('modal');
  if (!modal || !modal.classList.contains('open')) return;
  if (document.getElementById('md-editor')?.classList.contains('open')) return;
  if (event.target.closest?.('input,textarea,select')) return;
  if (event.key === 'ArrowLeft') { event.preventDefault(); qvNavPrev(); }
  else if (event.key === 'ArrowRight') { event.preventDefault(); qvNavNext(); }
}

if (typeof document !== 'undefined') {
  document.addEventListener('click', qvHandleClick);
  document.addEventListener('keydown', qvHandleKey);
}

// ---------- 共享画廊卡片 ----------
// 题目库画廊与展示板画廊共用同一副骨架：卡头（勾选 / 编号 / 状态标 / 菜单）、
// 可选元信息行、题面缩略预览、脚注（统计 + 标记）。
// 刻意只收「已经算好的 HTML 片段」而不读任何题库全局：两个调用点的状态标、
// 脚注、菜单本来就不一样，把差异留给调用方，骨架才只有一份。
function qvGalleryCard(spec) {
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
      <div class="gallery-preview ${card.previewClass || ''}" data-question-preview-uid="${escapeAttr(uid)}">${preview}</div>
      <div class="gc-foot">
        ${card.footHtml || ''}
        <span class="q-label-cell gc-labels" data-lbl-target="${escapeAttr(uid)}">${card.labelsHtml || ''}</span>
      </div>
    </div>`;
}
// UID 里重复了分类名时拆成「分类 + 序号」两截：一屏几十张卡时，重复的前缀纯属噪音
function qvGalleryIdHtml(uid, category) {
  const id = String(uid || '');
  const cat = String(category || '');
  if (cat && id.startsWith(cat)) {
    const rest = id.slice(cat.length).replace(/^[-_·\s]+/, '');
    return `<span class="gc-cat">${escapeHtml(cat)}</span>${rest ? `<span class="gc-num">${escapeHtml(rest)}</span>` : ''}`;
  }
  return `<span class="gc-num">${escapeHtml(id)}</span>`;
}

if (typeof module !== 'undefined') module.exports = { qvHtml, qvChips, qvToolsHtml, qvRecordHtml, qvInvalidateMany, qvSetContext, qvContext, qvRerenderAll, qvGalleryCard, qvGalleryIdHtml, QV_DEFAULTS };
