/**
 * 展示板打印协调（P7 第 3 步从 assets/board.js 搬来，行为与文案不变）：
 * 导出（打印预览窗口 / 下载 HTML）→ 按板登记待记录的导出任务 → 「记录纸面」用该任务的快照 POST /api/board/printed；
 * 独立打印窗口回传的版面只更新它自己的任务；重置纸面、切打印范围让旧任务作废（「仅补印新增」靠纸面记录续排）。
 * 模块不读旧全局：当前板、保存、请求、提示与确认都由调用方注入；旧 board.js 经 boardPrint() 懒创建唯一实例。
 */
const clone = value => JSON.parse(JSON.stringify(value));
const paperOf = board => (board && board.printed_summary) || { pages: 0, count: 0, new_count: 0, changed_count: 0 };

/** POST /api/export 取展示板导出 HTML；失败时抛出服务端的 msg，没有就用 fallback。预览与打印共用。 */
export async function fetchBoardExport(boardId, mode, options = {}) {
  const response = await fetch('/api/export', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ board_id: boardId, format: 'board', mode }), signal: options.signal,
  });
  if (!response.ok) {
    let message = options.fallback || '导出失败';
    try { message = (await response.json()).msg || message; } catch (error) { /* 非 JSON 错误体 */ }
    throw new Error(message);
  }
  return response.text();
}

/** 隐藏 iframe 里跑同一份导出模板，拿到浏览器实测的版面（页数 / 每题位置 / 续排 cursor）。 */
export function measureBoardLayout(html, options = {}) {
  const timeout = options.timeout || 30000;
  return new Promise((resolve, reject) => {
    const frame = document.createElement('iframe');
    frame.setAttribute('aria-hidden', 'true');
    // 测量要真排版：不能 display:none，只能挪到屏幕外
    frame.style.cssText = 'position:fixed;left:-10000px;top:0;width:900px;height:1200px;visibility:hidden;pointer-events:none;border:0';
    let settled = false;
    const finish = (error, layout) => {
      if (settled) return;
      settled = true;
      window.removeEventListener('message', onMessage);
      clearTimeout(timer);
      frame.remove();
      if (error) reject(error); else resolve(layout);
    };
    const onMessage = event => { if (event.source === frame.contentWindow && event.data?.type === 'omrs-board-layout') finish(null, event.data.layout); };
    const timer = setTimeout(() => finish(new Error('版面测量超时')), timeout);
    // 取消时立刻拆掉 iframe，别让作废的排版继续占用主线程
    if (options.signal) options.signal.addEventListener('abort', () => finish(new Error('已取消')), { once: true });
    window.addEventListener('message', onMessage);
    document.body.appendChild(frame);
    frame.srcdoc = html;
  });
}

// 打印预览窗口的占位页：独立文档，不吃站内样式，所以只用系统字体与系统色
const PLACEHOLDER = '<!doctype html><meta charset="utf-8"><title>正在生成打印预览…</title>'
  + '<style>body{font:14px system-ui;padding:24px;color:CanvasText}small{color:GrayText}</style>'
  + '<p>正在生成打印预览…<br><small>题目多、图片大时需要几秒；排版好后「打印」按钮才会亮起。</small></p>';

/**
 * deps：detail() 当前板；mode() 状态条同源的打印范围；flush() 排空保存队列 → Promise<bool>；post(path, body)；
 * reload()；renderStatus()；toast(text, options)；confirm(title, options) → Promise<bool>；
 * previewLayout() 常驻预览最近一次版面；recorded(board, boardId) 记录成功（当前板才采纳、打印范围切到「仅新增」）；
 * reset(board) 重置成功（采纳并把打印范围切回「全部」）。
 */
export function createBoardPrint(deps) {
  const { detail, mode, flush, post, reload, renderStatus, toast, confirm, previewLayout, recorded, reset } = deps;
  const jobs = new Map();      // boardId -> 本次导出的 {boardId, mode, html, layout, recording?, recorded?}
  const windows = new Map();   // 打印预览窗口 -> 它的导出任务

  const print = {
    jobs,
    windows,
    awaiting() { const board = detail(); return board ? jobs.get(board.id) || null : null; },
    clearAwaiting(boardId = detail()?.id) { jobs.delete(boardId); },
    /** 打印 / 下载之后状态条主按钮翻成「✓ 记录纸面」。没给任务时用常驻预览的版面（同板同范围才算）。 */
    markAwaiting(printMode, job = null) {
      const board = detail();
      if (!job && !board) return;
      if (!job) {
        const layout = previewLayout();
        job = { boardId: board.id, mode: printMode, layout: layout?.board_id === board.id && layout.mode === printMode ? clone(layout) : null };
      }
      jobs.set(job.boardId, job);
      renderStatus();
    },
    async exportCurrent(openPreview = false) {
      const board = detail();
      if (!board) { toast('请先选择一个展示板', { kind: 'warn' }); return; }
      const boardId = board.id, boardName = board.name;
      const printMode = mode();
      if (printMode === 'new' && !paperOf(board).new_count) { toast('没有新增题目需要打印', { kind: 'warn' }); return; }
      // 必须在 await 之前同步开窗：浏览器只允许在用户手势的同步调用栈里 window.open，
      // 等导出 HTML 回来时手势已过期，弹窗会被拦截（板子越大越容易触发）。
      let preview = null;
      if (openPreview) {
        preview = window.open('', '_blank');
        if (!preview) { toast('浏览器拦截了预览窗口，请允许弹出窗口后重试', { kind: 'error' }); return; }
        try { preview.document.write(PLACEHOLDER); preview.document.close(); } catch (error) { /* 窗口已被关闭 */ }
      }
      try {
        if (!(await flush())) throw new Error('设置尚未保存，请重试');
        const html = await fetchBoardExport(boardId, printMode);
        const job = { boardId, mode: printMode, html, layout: null };
        const url = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }));
        if (openPreview) {
          // 先登记任务，再导航窗口；极快加载时模板可能在 replace 返回前就回传版面。
          // location.replace 之后窗口对象不变，windows.get(event.source) 的回传照常工作。
          windows.set(preview, job);
          print.markAwaiting(printMode, job);
          try { preview.location.replace(url); } catch (error) {
            windows.delete(preview);
            if (jobs.get(boardId) === job) print.clearAwaiting(boardId);
            throw error;
          }
          setTimeout(() => URL.revokeObjectURL(url), 60000);
        } else {
          const link = document.createElement('a');
          link.href = url;
          link.download = `OMRS-BD-${boardName}${printMode === 'new' ? '-新增' : ''}-错题集.html`;
          document.body.appendChild(link); link.click(); link.remove();
          setTimeout(() => URL.revokeObjectURL(url), 1200);
          print.markAwaiting(printMode, job);
          toast('已下载；打印后回到状态条点「✓ 记录纸面」');
        }
      } catch (error) {
        if (preview) { try { preview.close(); } catch (closeError) { /* 已关闭 */ } }
        toast(`展示板导出失败：${error.message}`, { kind: 'error' });
      }
    },
    async recordPrinted(boardId, printMode, layout, job = null) {
      if (layout?.board_id && layout.board_id !== boardId) throw new Error('版面所属展示板不匹配');
      if (layout?.mode && layout.mode !== printMode) throw new Error('版面打印范围不匹配');
      if (job && jobs.get(boardId) !== job) throw new Error('这份打印任务已失效，请重新导出');
      if (!(await flush())) throw new Error('设置尚未保存，请重试');
      const result = await post('/api/board/printed', { id: boardId, mode: printMode, layout });
      if (!job || jobs.get(boardId) === job) print.clearAwaiting(boardId);
      if (job) job.recorded = true;
      recorded(result.board, boardId);
      await reload();
      const paper = paperOf(result.board);
      toast(`已记录纸面：共 ${paper.count} 题 / ${paper.pages} 页，下次加题可只打印新增`);
    },
    async markPrinted() {
      const board = detail();
      if (!board) return;
      const boardId = board.id;
      const job = print.awaiting();
      if (job?.recording || job?.recorded) return;
      if (job) job.recording = true;
      const printMode = job?.mode || mode();
      try {
        const ok = await confirm(printMode === 'new' ? '已经把这次新增题目打印出来了？' : '已经把这次整板打印出来了？', {
          hint: job ? '按刚才导出或下载的那份纸面记录；之后的编辑不会替换这份快照。' : '按当前版面记录纸面。',
          okText: '标记为已打印',
        });
        if (!ok || job?.recorded) return;
        let layout = job?.layout;
        if (!layout && job?.html) layout = await measureBoardLayout(job.html);
        if (!layout) {
          if (!(await flush())) return;
          layout = await measureBoardLayout(await fetchBoardExport(boardId, printMode));
        }
        if (job) { job.layout = layout; job.html = null; }
        await print.recordPrinted(boardId, printMode, layout, job);
      } catch (error) { toast(`记录纸面失败：${error.message}`, { kind: 'error' }); }
      finally { if (job) job.recording = false; }
    },
    async resetPrinted() {
      const board = detail();
      if (!board) return;
      const ok = await confirm('重置纸面记录？', { hint: '忘掉「哪些题已经在纸上」；之后只能「打印全部」重新开始。', okText: '重置', danger: true });
      if (!ok) return;
      const boardId = board.id;
      // 请求返回前也使旧窗口失效，避免它在重置进行中回传旧版面并重新写回纸面。
      print.clearAwaiting(boardId);
      try {
        const result = await post('/api/board/printed/reset', { id: boardId });
        reset(result.board);
        await reload();
        toast('纸面记录已重置');
      } catch (error) { toast(`重置失败：${error.message}`, { kind: 'error' }); }
    },
    /** window 的 message：独立打印窗口只更新它自己的导出快照，不能借用当前选中的展示板。 */
    async handleMessage(event) {
      const type = event.data?.type;
      if (type !== 'omrs-board-layout' && type !== 'omrs-board-printed') return;
      const job = windows.get(event.source), layout = event.data.layout;
      // 切换打印范围、重置纸面或重新导出后，旧窗口仍可能加载完并回传消息；只有当前板仍持有的那份任务可以更新纸面。
      if (!job || jobs.get(job.boardId) !== job || job.recorded || !layout || layout.board_id !== job.boardId || layout.mode !== job.mode) return;
      if (event.data.boardId !== job.boardId || event.data.mode !== job.mode) return;
      job.layout = clone(layout);
      job.html = null; // 已取得实际窗口的版面，不再保留近 1MB 的 HTML
      if (type === 'omrs-board-layout' || job.recording) return;
      job.recording = true;
      try {
        const ok = await confirm('打印预览窗口说已经打印完成，记录纸面？', { hint: '记录这份打印窗口中的纸面，与当前选中的展示板无关。', okText: '记录' });
        if (ok) await print.recordPrinted(job.boardId, job.mode, job.layout, job);
      } catch (error) { toast(`记录纸面失败：${error.message}`, { kind: 'error' }); }
      finally { job.recording = false; }
    },
  };
  return print;
}
