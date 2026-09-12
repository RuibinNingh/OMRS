// === assets/board_preview.js — 展示板实时预览：单例 iframe 的生命周期与消息协议 ===
// 依赖 core.js（api）；必须排在 board.js 之后。
//
// 为什么是常驻 iframe 而不是每次新建：那份导出 HTML 内联了 KaTeX 字体，将近 1MB，
// 重建节点等于重新解码一次字体。全页只留一个 iframe，切板换 srcdoc。
//
// 三档刷新，只有第三档走网络：
//   几何类（留白比例 / 题间留白 / 切割线）→ postMessage relayout，去抖 120ms，零请求；
//   内容类（增删题 / 排序 / 换模式 / 正文变动）    → 重新拉导出，去抖 500ms；
//   切板                                          → 立即拉导出。
// 导出指纹命中缓存时连第三档也省掉。

let BP_FRAME = null;                  // 单例 iframe
let BP_STATE = { boardId: '', mode: 'all', key: '', ready: false };
let BP_LAYOUT = null;                 // 最近一次 OMRS_LAYOUT
let BP_VIEW = { single: true, page: 1, scale: 1 };
let BP_RELAYOUT_TIMER = null;
let BP_REFRESH_TIMER = null;
let BP_PENDING = null;                // {print, gaps} 待发的几何改动
let BP_FETCH = null;                  // 进行中的导出请求 {key, controller}
let BP_HTML_CACHE = new Map();        // key -> html（只留最近一份，导出 HTML 很大）
let BP_ON_LAYOUT = null;              // 宿主回调：拿到新版面
let BP_ON_SELECT = null;              // 宿主回调：纸面上点了某道题
let BP_ON_GAP = null;                 // 宿主回调：拖切割线改了某题的题后留白
let BP_VISIBLE = true;

const BP_SCALES = { fit: 'fit', 1: 1 };

// 指纹只描述「导出内容」：板 + 模式 + 题目签名 + 纸面记录时间。
// 刻意不含 board.updated_at —— 拖一次版面滑块就会 bump 它，而版面改动本该走 relayout，
// 把它算进指纹等于每拖一下都重新请求近 1MB 的导出。
function boardPreviewKey(boardId, mode, signature, printedAt) {
  return [boardId || '', mode || 'all', signature || '', printedAt || ''].join('|');
}
function boardPreviewLayout() { return BP_LAYOUT; }
function boardPreviewFrame() { return BP_FRAME; }
function boardPreviewIsReady() { return !!(BP_FRAME && BP_STATE.ready); }

function boardPreviewOn(handlers) {
  if (handlers?.onLayout) BP_ON_LAYOUT = handlers.onLayout;
  if (handlers?.onSelect) BP_ON_SELECT = handlers.onSelect;
  if (handlers?.onGap) BP_ON_GAP = handlers.onGap;
}

// 不在前台就不排版：切到别的 Tab、或预览滚出视口时，几何改动只记不发，回来再补一次。
function boardPreviewActive() {
  if (!BP_VISIBLE) return false;
  const panel = document.getElementById('panel-board');
  return !!panel?.classList.contains('active');
}

function boardPreviewMount(container) {
  if (!container) return null;
  if (!BP_FRAME) {
    BP_FRAME = document.createElement('iframe');
    BP_FRAME.className = 'bd-preview-frame';
    BP_FRAME.setAttribute('title', '纸面预览');
    // 同源 srcdoc：宿主能直接读 contentWindow.OMRS_LAYOUT，postMessage 也不受跨源限制
    BP_FRAME.setAttribute('sandbox', 'allow-same-origin allow-scripts allow-modals');
    if (typeof IntersectionObserver === 'function') {
      new IntersectionObserver(entries => {
        BP_VISIBLE = entries.some(entry => entry.isIntersecting);
        if (BP_VISIBLE) boardPreviewFlushPending();
      }, { threshold: 0.01 }).observe(BP_FRAME);
    }
  }
  if (BP_FRAME.parentNode !== container) container.appendChild(BP_FRAME);
  return BP_FRAME;
}

function boardPreviewPost(message) {
  try { BP_FRAME?.contentWindow?.postMessage(message, '*'); } catch (error) {}
}

// ---------- 几何刷新（零网络） ----------
function boardPreviewRelayout(print, gaps) {
  BP_PENDING = { print: { ...(print || {}) }, gaps: { ...(gaps || {}) } };
  clearTimeout(BP_RELAYOUT_TIMER);
  BP_RELAYOUT_TIMER = setTimeout(boardPreviewFlushPending, 120);
}
function boardPreviewFlushPending() {
  clearTimeout(BP_RELAYOUT_TIMER);
  if (!BP_PENDING || !boardPreviewIsReady() || !boardPreviewActive()) return;
  const pending = BP_PENDING;
  BP_PENDING = null;
  boardPreviewPost({ type: 'omrs-board-relayout', print: pending.print, gaps: pending.gaps });
}

// ---------- 翻页与缩放 ----------
function boardPreviewGoto(target) {
  if (!boardPreviewIsReady()) return;
  if (typeof target === 'number' || /^\d+$/.test(String(target || ''))) {
    BP_VIEW.page = Number(target);
    boardPreviewPost({ type: 'omrs-board-goto', page: BP_VIEW.page });
  } else if (target) {
    boardPreviewPost({ type: 'omrs-board-goto', uid: String(target) });
  }
}
function boardPreviewPages() {
  const numbers = BP_LAYOUT?.page_numbers || [];
  return numbers.length ? numbers : (BP_LAYOUT?.pages ? [BP_LAYOUT.pages] : []);
}
function boardPreviewStep(delta) {
  const numbers = boardPreviewPages();
  if (!numbers.length) return;
  const at = Math.max(0, numbers.indexOf(BP_VIEW.page));
  boardPreviewGoto(numbers[Math.max(0, Math.min(numbers.length - 1, at + delta))]);
}
function boardPreviewSetView(view) {
  BP_VIEW = { ...BP_VIEW, ...(view || {}) };
  boardPreviewPost({ type: 'omrs-board-view', single: BP_VIEW.single, page: BP_VIEW.page, scale: BP_VIEW.scale });
}
// 「适应宽度」按容器实际宽度算比例：A4 屏幕宽 793.7px 是模板里的硬几何，不跟版面设置走。
function boardPreviewScale(mode) {
  let scale = Number(mode);
  if (!Number.isFinite(scale) || scale <= 0) {
    const width = BP_FRAME?.parentNode?.clientWidth || 0;
    scale = width ? Math.max(.3, Math.min(1.4, (width - 24) / 793.7)) : 1;
  }
  boardPreviewSetView({ scale: Math.round(scale * 100) / 100 });
  return scale;
}
function boardPreviewView() { return { ...BP_VIEW }; }

// ---------- 换板 / 换内容（走网络，带指纹缓存） ----------
async function boardPreviewSetBoard(boardId, mode, options = {}) {
  const key = boardPreviewKey(boardId, mode, options.signature, options.printedAt);
  if (!boardId) { BP_STATE = { boardId: '', mode: 'all', key: '', ready: false, loading: false }; BP_LAYOUT = null; return null; }
  // 同一份内容已经排好、或正在路上，就别再拉一次：导出 HTML 将近 1MB，
  // 初次进板时 boardInit 与随后的 render 会连着 sync 两次，没有这道闸就白拉一遍。
  if (key === BP_STATE.key && (BP_STATE.ready || BP_STATE.loading) && !options.force) return BP_STATE.ready ? BP_LAYOUT : null;
  clearTimeout(BP_REFRESH_TIMER);
  if (BP_FETCH && BP_FETCH.key !== key) { try { BP_FETCH.controller.abort(); } catch (error) {} BP_FETCH = null; }
  BP_STATE = { boardId, mode: mode === 'new' ? 'new' : 'all', key, ready: false, loading: true };
  let html = BP_HTML_CACHE.get(key);
  if (!html) {
    const controller = typeof AbortController === 'function' ? new AbortController() : null;
    BP_FETCH = { key, controller: controller || { abort() {} } };
    try {
      html = await boardPreviewFetch(boardId, BP_STATE.mode, controller?.signal);
    } catch (error) {
      if (error?.name === 'AbortError') return null;
      BP_STATE.error = error.message || String(error);
      BP_STATE.loading = false;
      BP_STATE.key = '';                                 // 失败不占坑，下次 sync 会重试
      throw error;
    } finally {
      if (BP_FETCH?.key === key) BP_FETCH = null;
    }
    if (BP_STATE.key !== key) return null;           // 期间又换板了，丢弃这次结果
    BP_HTML_CACHE = new Map([[key, html]]);          // 只留最近一份，别把几份 1MB 的 HTML 攒在内存里
  }
  if (!BP_FRAME) return null;
  BP_FRAME.srcdoc = html;
  return null;                                        // 版面等 iframe 排完由 onLayout 回调送出
}
async function boardPreviewFetch(boardId, mode, signal) {
  const response = await fetch('/api/export', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ board_id: boardId, format: 'board', mode }), signal,
  });
  if (!response.ok) {
    let message = '生成预览失败';
    try { message = (await response.json()).msg || message; } catch (error) {}
    throw new Error(message);
  }
  return response.text();
}
function boardPreviewScheduleRefresh(boardId, mode, options = {}) {
  clearTimeout(BP_REFRESH_TIMER);
  BP_REFRESH_TIMER = setTimeout(() => {
    boardPreviewSetBoard(boardId, mode, options).catch(() => {});
  }, 500);
}
function boardPreviewInvalidate() { BP_HTML_CACHE = new Map(); BP_STATE.key = ''; BP_STATE.loading = false; }

// ---------- iframe 回传 ----------
if (typeof window !== 'undefined') {
  window.addEventListener('message', event => {
    const message = event.data;
    if (!message || typeof message !== 'object' || !BP_FRAME) return;
    if (event.source !== BP_FRAME.contentWindow) return;         // 打印预览窗口另有链路，别抢
    if (message.type === 'omrs-board-layout') {
      BP_LAYOUT = message.layout || null;
      if (!BP_STATE.ready) {
        BP_STATE.ready = true;
        BP_STATE.loading = false;
        boardPreviewSetView(BP_VIEW);                            // 新 srcdoc 要重放单页/缩放状态
        boardPreviewFlushPending();
      }
      const numbers = boardPreviewPages();
      if (numbers.length && !numbers.includes(BP_VIEW.page)) BP_VIEW.page = numbers[0];
      if (BP_ON_LAYOUT) BP_ON_LAYOUT(BP_LAYOUT);
      return;
    }
    if (message.type === 'omrs-board-view-state') {
      if (message.view) BP_VIEW = { ...BP_VIEW, ...message.view };
      if (BP_ON_LAYOUT) BP_ON_LAYOUT(BP_LAYOUT);
      return;
    }
    if (message.type === 'omrs-board-select' && BP_ON_SELECT) { BP_ON_SELECT(message); return; }
    // 拖切割线：模板只报「哪道题、几行」，夹紧与保存都在宿主
    if (message.type === 'omrs-board-gap' && BP_ON_GAP && message.uid) BP_ON_GAP(message);
  });
}

if (typeof module !== 'undefined') module.exports = {
  boardPreviewKey, boardPreviewPages, boardPreviewLayout, boardPreviewView,
  boardPreviewMount, boardPreviewOn, boardPreviewRelayout, boardPreviewFlushPending,
  boardPreviewGoto, boardPreviewStep, boardPreviewSetView, boardPreviewScale,
  boardPreviewSetBoard, boardPreviewScheduleRefresh, boardPreviewInvalidate, boardPreviewIsReady,
};
