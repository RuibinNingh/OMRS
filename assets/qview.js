// === assets/qview.js — 共享题目视图（qview）：题面 / 答案双栏 ===
// 供题目 Modal、反馈工作台、即时练习、画廊卡片复用，收敛原来三处各自为政的题目渲染副本。
// 依赖 questions.js 的 renderMdContent / ensureQuestionDetail / QUESTION_CACHE，
// 以及 core.js 的 escapeHtml / escapeAttr / getItemByUid / getDueDays / asNumber，
// 因此 <script> 必须排在 questions.js 之后。
// 约定：本文件不写业务逻辑，工具按钮只转调 questions.js 已有的全局函数；
// DOM 里不拼函数名，所有交互走 data-qv-act 事件委托。

const QV_DEFAULTS = {
  layout: 'split',      // 'split' 双栏 / 'stack' 单栏；窄容器由容器查询自动降级
  reveal: true,         // false 时不渲染答案 DOM，只给「显示答案」按钮
  showAnswer: true,
  showNotes: true,
  showHistory: true,
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
        return '<button type="button" class="btn sm" data-qv-act="board">加入展示板</button>';
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
  if (o.showHistory && String(detail.history || '').trim()) {
    side.push(`<details class="qv-hist"><summary>做题历史</summary><pre>${escapeHtml(detail.history)}</pre></details>`);
  }
  const answer = side.length ? `<section class="qv-a">${side.join('')}</section>` : '';

  return `<div class="${classes.join(' ')}" data-qv-uid="${escapeAttr(uid)}" data-reveal="${o.reveal ? '1' : '0'}">
    ${head}${question}${answer}
  </div>`;
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
  else if (action === 'board' && typeof boardQuickAdd === 'function') boardQuickAdd(uid);
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

if (typeof module !== 'undefined') module.exports = { qvHtml, qvChips, qvToolsHtml, qvSetContext, qvContext, qvRerenderAll, QV_DEFAULTS };
