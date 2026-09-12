/* OMRS 展示板（错题集）排版引擎
 * 与 a4.js 同一套思路：浏览器既是排版引擎、又是最终打印引擎，所见即所打印。
 *   1) 按题栏宽度测每个内容块的真实高度（KaTeX 公式、表格、图片一并测量）；
 *   2) 贪心填进固定高度的单栏（左题），右侧留白不画任何东西；
 *   3) 长图切白缝 / 跨页续排「（续）」题头 / 题头不留孤行；
 *   4) 增量打印：把纸面记录里的 cursor 之前的区域用占位块顶开，新题接在原纸空白处，
 *      随后需要新页时跳到「已打印总页数 + 1」，纸面页码永远是绝对页码；
 *   5) 排版完成后产出 window.OMRS_LAYOUT（每题所在页 / 高度、续排位置、页数），
 *      通过 postMessage 交回主程序记录纸面。
 */
(function () {
  "use strict";
  const MM = 3.779528;
  const PAGE_W = 210 * MM, PAGE_H = 297 * MM;
  const MARGIN_TB = 12 * MM, MARGIN_R = 10 * MM, FOOTER_SAFE = 8.5 * MM;
  const HEAD_H = 39;            // 页眉「错题集」27px + 12px 间距
  const COL_GAP = 24;           // 题栏与留白区之间的间距
  const SAFETY = 4, MIN_FILL = 40, MIN_SLICE = 28, WHITE_THR = 245, ORPHAN = 56;

  const D = window.OMRS_DATA || { meta: {}, questions: [], answers: [] };
  const META = D.meta || {};
  const PRINT = META.print || {};
  const MODE = META.mode === "new" ? "new" : "all";
  const PRINTED = MODE === "new" && META.printed ? META.printed : null;

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  // 版面派生量是可变的：宿主页面拖版面滑块时发 omrs-board-relayout，直接在本页重算重排，
  // 不重新请求那份将近 1MB 的导出 HTML。CONTENT_H / COL_H 只依赖纸张，恒定。
  const CONTENT_H = PAGE_H - 2 * MARGIN_TB - FOOTER_SAFE;
  const COL_H = CONTENT_H - HEAD_H;
  let PRINT_STATE = Object.assign({}, PRINT);
  let noteRatio, gapLines, CUT, CUT_LABEL, CONTENT_W, COL_W;
  let GAPS = null;              // uid -> 绝对行数 | null(继承全局)；宿主重排时整份覆盖
  function applyPrint(next) {
    if (next && typeof next === "object") PRINT_STATE = Object.assign({}, PRINT_STATE, next);
    const p = PRINT_STATE;
    noteRatio = clamp(Number(p.note_ratio) || .50, .30, .55);
    gapLines = clamp(Number(p.gap_lines) || 0, 0, 48);
    CUT = ["none", "dash", "solid"].indexOf(p.cut_line) >= 0 ? p.cut_line : "dash";
    CUT_LABEL = p.cut_label === true;
    CONTENT_W = PAGE_W - 2 * MARGIN_R;
    COL_W = Math.floor((CONTENT_W - COL_GAP) * (1 - noteRatio) * 100) / 100;
  }
  applyPrint(null);
  // 初次渲染用服务端算好的绝对值；宿主发来 gaps 之后改用宿主的（null = 继承当前全局）
  function questionGap(q) {
    if (GAPS && Object.prototype.hasOwnProperty.call(GAPS, q.uid)) {
      const own = GAPS[q.uid];
      return clamp(Number(own == null ? gapLines : own) || 0, 0, 48);
    }
    return clamp(Number(q.gap_lines) || 0, 0, 48);
  }

  function el(tag, cls, txt) { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

  // ---- 像素分析：每行墨量 + 干净缝带（与 a4.js 一致） ----
  // 找白缝只需要「每一行有多少墨」，不需要原图分辨率：宽于 ANALYZE_W 的图先缩到 ANALYZE_W
  // 再扫描，结果按比例映射回原图坐标。手机拍的千万像素长图从逐像素扫几百毫秒降到几毫秒，
  // 切口位置误差不超过一两个原图像素，落在 SAFETY 余量之内。
  const ANALYZE_W = 600;
  const _cache = new Map();
  function analyze(img) {
    if (_cache.has(img.src)) return _cache.get(img.src);
    const W = img.naturalWidth, H = img.naturalHeight;
    const scale = W > ANALYZE_W ? ANALYZE_W / W : 1;
    const aw = Math.max(1, Math.round(W * scale)), ah = Math.max(1, Math.round(H * scale));
    const cv = document.createElement("canvas"); cv.width = aw; cv.height = ah;
    const ctx = cv.getContext("2d", { willReadFrequently: true });
    ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, aw, ah); ctx.drawImage(img, 0, 0, aw, ah);
    const data = ctx.getImageData(0, 0, aw, ah).data;
    const inkScaled = new Int32Array(ah);
    for (let y = 0; y < ah; y++) {
      let c = 0, o = y * aw * 4;
      for (let x = 0; x < aw; x++) { const i = o + x * 4; if (Math.min(data[i], data[i + 1], data[i + 2]) < WHITE_THR) c++; }
      inkScaled[y] = c;
    }
    const sorted = Array.from(inkScaled).sort((a, b) => a - b);
    const floor = sorted[Math.floor(ah * 0.05)] || 0;
    const quietThr = floor + Math.max(2, Math.round(aw * 0.004));
    const G = Math.max(4, Math.round(ah * 0.004));
    const toNatural = y => Math.min(H, Math.round(y / scale));
    const bands = []; let s = -1;
    for (let y = 0; y <= ah; y++) {
      const q = (y < ah) && inkScaled[y] <= quietThr;
      if (q) { if (s < 0) s = y; } else { if (s >= 0) { if (y - s >= G) bands.push([toNatural(s), toNatural(y)]); s = -1; } }
    }
    // ink 仍按原图行号索引（leastInk 在原图坐标里找最少墨的一行），数值换算回原图宽度
    let ink = inkScaled;
    if (scale !== 1) {
      ink = new Int32Array(H);
      for (let y = 0; y < H; y++) ink[y] = Math.round(inkScaled[Math.min(ah - 1, Math.floor(y * scale))] / scale);
    }
    const out = { W, H, ink, bands }; _cache.set(img.src, out); return out;
  }
  function findCut(an, startPx, capPx) {
    let best = null;
    for (const [a, b] of an.bands) { const c = ((a + b) / 2) | 0; if (c > startPx + MIN_SLICE && c <= startPx + capPx) { if (best === null || c > best) best = c; } }
    return best;
  }
  function leastInk(an, lo, hi) { let m = Infinity, my = lo; for (let y = lo; y <= hi; y++) if (an.ink[y] < m) { m = an.ink[y]; my = y; } return my; }
  function sliceEl(src, dispW, naturalW, y0, y1, mark) {
    const scale = dispW / naturalW;
    const wrap = el("div", "slice"); wrap.style.width = dispW + "px"; wrap.style.height = (y1 - y0) * scale + "px";
    const im = el("img"); im.src = src; im.style.width = dispW + "px"; im.style.marginTop = (-y0 * scale) + "px";
    wrap.appendChild(im); if (mark) wrap.classList.add(mark); return wrap;
  }

  // ---- 标记芯片（打印变体：18% 淡底 + 同色相压暗文字） ----
  function labelRgb(value) {
    let hex = String(value || "#64748b").replace(/^#/, "");
    if (/^[0-9a-f]{3}$/i.test(hex)) hex = hex.split("").map(ch => ch + ch).join("");
    if (!/^[0-9a-f]{6}$/i.test(hex)) hex = "64748b";
    return [0, 2, 4].map(index => parseInt(hex.slice(index, index + 2), 16));
  }
  function appendLabelChips(parent, labels) {
    (Array.isArray(labels) ? labels : []).forEach(raw => {
      const item = typeof raw === "string" ? { name: raw, color: "#64748b" } : (raw || {});
      const name = String(item.name || "").trim();
      if (!name) return;
      const chip = el("span", "lbl", name);
      chip.style.setProperty("--lbl-rgb", labelRgb(item.color).join(","));
      chip.style.setProperty("--lbl-ink", item.ink || "#475569");
      parent.appendChild(chip);
    });
  }

  // ---- 页面骨架 ----
  function decoratePage(page, number, partial) {
    page.dataset.page = String(number);
    if (partial) page.classList.add("partial");
    const inner = el("div", "page-inner");
    inner.style.left = MARGIN_R + "px"; inner.style.top = MARGIN_TB + "px";
    inner.style.width = CONTENT_W + "px"; inner.style.height = CONTENT_H + "px";
    const head = el("div", "head");
    head.appendChild(el("span", "ttl", META.title || "错题集"));
    if (PRINT_STATE.show_meta !== false && META.generated) head.appendChild(el("span", "sub", META.generated));
    inner.appendChild(head);
    const col = el("div", "col");
    col.style.width = COL_W + "px"; col.style.height = COL_H + "px";
    inner.appendChild(col);
    page.appendChild(inner);
    page.appendChild(el("div", "pagenum", String(number)));
    return col;
  }

  // ---- 排版引擎 ----
  function layout(blocks, mount, options) {
    const warnings = [];
    const opt = options || {};
    const measurer = el("div", "measurer"); measurer.style.width = COL_W + "px";
    mount.parentNode.insertBefore(measurer, mount);
    const pages = [];              // {page, col, number, partial, answer}
    let page = null, col = null, y = 0;
    // 增量模式：首页编号为 cursor.page，其后从「已打印总页数 + 1」起
    let nextNumber = opt.startPage || 1;
    const afterPrinted = opt.printedPages || 0;
    let currentQ = null;           // 正在排版的题（用于续页题头）
    const segments = new Map();    // idx -> Map(pageNumber -> {top,bottom})
    const cuts = [];               // 切割线待绘制位置 {page, y, idx}

    function newPage(partial) {
      const number = nextNumber;
      nextNumber = (pages.length === 0 && afterPrinted) ? afterPrinted + 1 : number + 1;
      const node = el("div", "page");
      const c = decoratePage(node, number, !!partial);
      pages.push({ page: node, col: c, number, partial: !!partial, answer: false });
      mount.appendChild(node);
      page = pages[pages.length - 1]; col = c; y = 0;
      return page;
    }
    function nextCol() {
      newPage(false);
      if (currentQ && currentQ.started && !currentQ.done) forcePut(contHeadBlock(currentQ).build(), null);
    }
    function track(node, block) {
      const q = block && block.q;
      if (!q) return;
      node.dataset.qUid = q.uid || "";
      node.dataset.qIdx = String(q.idx);
      const rect = node.getBoundingClientRect(), base = col.getBoundingClientRect();
      const map = segments.get(q.idx) || new Map();
      const seg = map.get(page.number) || { top: Infinity, bottom: 0 };
      seg.top = Math.min(seg.top, rect.top - base.top);
      seg.bottom = Math.max(seg.bottom, rect.bottom - base.top);
      map.set(page.number, seg); segments.set(q.idx, map);
    }
    // 先测量只是快速判断；真正落位后再以 DOM 的实际底边为准。
    function put(node, block) {
      col.appendChild(node);
      const used = node.getBoundingClientRect().bottom - col.getBoundingClientRect().top;
      if (used > COL_H + 0.5) { col.removeChild(node); return false; }
      y = used; track(node, block);
      return true;
    }
    function forcePut(node, block) {
      col.appendChild(node);
      y = node.getBoundingClientRect().bottom - col.getBoundingClientRect().top;
      track(node, block);
    }
    function measure(node) { measurer.appendChild(node); const h = node.getBoundingClientRect().height; measurer.removeChild(node); return h; }

    function formulaBreakOffsets(text) {
      const source = String(text || "");
      const token = /(\$\$[\s\S]+?\$\$|\$[^$\n]+\$)/g;
      const offsets = []; let match;
      while ((match = token.exec(source))) offsets.push(match.index);
      return offsets;
    }
    // 只在整段放不下时才动公式：把「公式之前的文字」留在当前页，公式及后文从下一页继续。
    function splitFormulaText(b, source) {
      const offsets = formulaBreakOffsets(source);
      for (let i = offsets.length - 1; i >= 0; i--) {
        const cut = offsets[i];
        const prefix = source.slice(0, cut);
        if (!prefix.trim()) continue;
        const prefixNode = b.build(prefix);
        const prefixH = measure(prefixNode);
        if (y + prefixH > COL_H + 0.5 || !put(prefixNode, b)) continue;
        nextCol();
        return placeText(b, source.slice(cut));
      }
      return false;
    }
    function placeText(b, source) {
      const node = b.build(source);
      const h = measure(node);
      if (y + h <= COL_H + 0.5 && put(node, b)) return true;
      if (splitFormulaText(b, source)) return true;
      nextCol();
      if (put(node, b)) return true;
      forcePut(node, b);
      warnings.push("「" + (b.q ? b.q.uid : "?") + "」有一段文字即使单独占一页也放不下，已强制放置");
      return false;
    }
    function placePlainBlock(b) {
      const node = b.build(); const h = measure(node);
      if (b.keepNext && COL_H - y < h + ORPHAN) nextCol();
      if (y + h > COL_H + 0.5) nextCol();
      if (put(node, b)) return true;
      nextCol();
      if (put(node, b)) return true;
      forcePut(node, b);
      return false;
    }
    // 题间留白：放不下就贴到页底，不为它另起一页
    function placeGap(b) {
      const node = b.build(); const h = measure(node);
      if (y + h > COL_H + 0.5) { node.style.height = Math.max(0, COL_H - y) + "px"; forcePut(node, null); y = COL_H; recordCut(b); return; }
      put(node, null);
      recordCut(b);
    }
    // 切割线：落在每题留白的末尾，是「这道题写到这里为止」的提示，四种情况不画：
    // ① 贴页底（撕下来就是整页，没有意义）② 留白被顶到新页顶部 ③ 答案页 ④ 增量模式的已打印占位区内
    function recordCut(b) {
      if (CUT === "none" || !page || page.answer) return;
      if (y >= COL_H - 2 || y <= 0.5) return;
      if (page.partial && y <= (opt.cursorY || 0) + 0.5) return;
      cuts.push({ page, y: Math.round(y * 100) / 100, idx: b && b.q ? b.q.idx : null,
                  uid: b && b.q ? b.q.uid : "", lines: b ? (Number(b.lines) || 0) : 0 });
    }
    function placeImage(b) {
      const im = b.imgEl;
      if (!im || !im.naturalWidth) { warnings.push("「" + (b.q ? b.q.uid : "?") + "」有一张图片无法解码，已跳过"); return; }
      const naturalW = im.naturalWidth, naturalH = im.naturalHeight;
      const dispScale = COL_W / naturalW, dispH = naturalH * dispScale;
      if (dispH <= COL_H - y + 0.5) {
        const node = sliceEl(b.src, COL_W, naturalW, 0, naturalH);
        if (!put(node, b)) { nextCol(); put(node, b); }
        return;
      }
      const an = analyze(im);
      let start = 0;
      while (start < naturalH) {
        const remDisp = COL_H - y, remPx = remDisp / dispScale, colPx = COL_H / dispScale;
        const restPx = naturalH - start, restDisp = restPx * dispScale;
        if (restDisp <= remDisp + 0.5) {
          const node = sliceEl(b.src, COL_W, naturalW, start, naturalH);
          if (!put(node, b)) { nextCol(); put(node, b); }
          return;
        }
        const fitsAColumn = restDisp <= COL_H + 0.5;
        if (fitsAColumn) {
          if (remDisp >= MIN_FILL) {
            const cap = Math.max(MIN_SLICE, Math.floor(remPx - SAFETY / dispScale));
            const cut = findCut(an, start, cap);
            if (cut !== null) { const node = sliceEl(b.src, COL_W, naturalW, start, cut); if (!put(node, b)) { nextCol(); put(node, b); } start = cut; nextCol(); continue; }
          }
          nextCol(); const node = sliceEl(b.src, COL_W, naturalW, start, naturalH); if (!put(node, b)) forcePut(node, b); return;
        }
        let cap = Math.max(MIN_SLICE, Math.floor((remDisp >= MIN_FILL ? remPx : colPx) - SAFETY / dispScale));
        cap = Math.min(cap, Math.floor(colPx - SAFETY / dispScale));
        let cut = findCut(an, start, cap), mark = null;
        if (cut === null) {
          if (remDisp < MIN_FILL && y > 0) { nextCol(); continue; }
          const lo = start + MIN_SLICE, hi = Math.max(start + MIN_SLICE, start + cap);
          cut = leastInk(an, lo, hi); mark = "clip-warn";
          warnings.push("「" + (b.q ? b.q.uid : "?") + "」图无干净白缝，于 " + start + "→" + cut + "px 被迫切，可能擦到内容");
        }
        if (cut <= start) cut = Math.min(start + Math.floor(cap), naturalH - 1);
        const node = sliceEl(b.src, COL_W, naturalW, start, cut, mark);
        if (!put(node, b)) { nextCol(); if (!put(node, b)) forcePut(node, b); }
        start = cut; nextCol();
      }
    }
    function placeBlock(b) {
      if (b.kind === "qstart") { currentQ = b.q; currentQ.started = false; currentQ.done = false; return; }
      if (b.kind === "qend") { if (currentQ) currentQ.done = true; currentQ = null; return; }
      if (b.kind === "gap") { placeGap(b); return; }
      if (b.kind === "image") { placeImage(b); return; }
      if (b.kind === "text") { placeText(b, b.text); return; }
      if (b.kind === "answers") { newPage(false); page.answer = true; return; }
      placePlainBlock(b);
      if (b.head && currentQ) currentQ.started = true;
    }

    // 首页：增量模式下先用占位块顶开已打印区域
    const partial = !!(opt.cursorY > 0.5);
    newPage(partial);
    if (partial) {
      const ghost = el("div", "blk ghost");
      ghost.style.height = Math.min(COL_H, opt.cursorY) + "px";
      ghost.dataset.label = "已打印区域（不重复打印）";
      forcePut(ghost, null);
    }
    let cursor = null;
    for (const b of blocks) {
      placeBlock(b);
      if (b.kind === "gap") cursor = { page: page.number, y: Math.round(Math.min(COL_H, y) * 100) / 100 };
    }
    if (!cursor) cursor = { page: page.number, y: Math.round(y * 100) / 100 };

    // 增量模式：如果第一页（原纸）上除占位块外没放任何新内容，就不输出它
    if (partial) {
      const first = pages[0];
      const realNodes = [...first.col.children].filter(n => !n.classList.contains("ghost"));
      if (!realNodes.length) { first.page.remove(); pages.shift(); }
    }
    // 切割线画在 page-inner 上（不在 .col 里，避免被 overflow:hidden 裁掉）：
    // y 是相对题栏顶的偏移，题栏顶距 page-inner 顶正好是页眉高度 HEAD_H。
    for (const cut of cuts) {
      if (pages.indexOf(cut.page) < 0) continue;              // 被丢弃的占位页上的线一并丢掉
      const inner = cut.page.page.querySelector(".page-inner");
      if (!inner) continue;
      const line = el("div", "cut-line" + (CUT === "solid" ? " solid" : ""));
      line.style.top = (HEAD_H + cut.y) + "px";
      line.style.left = "0";
      line.style.width = CONTENT_W + "px";                    // 题栏 + COL_GAP + 留白区，全宽
      // 切割线同时是「这道题留白多高」的拖拽手柄；答案页与占位区的线根本不会走到这里
      if (cut.uid) { line.dataset.cutUid = cut.uid; line.dataset.cutLines = String(cut.lines); line.classList.add("draggable"); }
      if (CUT_LABEL && cut.idx != null) line.appendChild(el("span", "tag", "第 " + cut.idx + " 题止"));
      inner.appendChild(line);
    }
    measurer.remove();
    const items = [];
    segments.forEach((map, idx) => {
      const q = (D.questions || []).find(item => item.idx === idx);
      if (!q) return;
      items.push({ idx, uid: q.uid, question_id: q.question_id || "",
        segments: [...map.entries()].map(([number, seg]) => ({ page: number, top: Math.round(seg.top * 100) / 100, height: Math.round((seg.bottom - seg.top) * 100) / 100 })).sort((a, b) => a.page - b.page) });
    });
    items.sort((a, b) => a.idx - b.idx);
    return { pages, warnings, cursor, items };
  }

  // ---------- 应用层：数据 -> 内容块 ----------
  const imgMap = new Map();
  function preload() {
    const srcs = new Set();
    (D.questions || []).forEach(q => (q.blocks || []).forEach(b => b.t === "img" && srcs.add(b.img.src)));
    (D.answers || []).forEach(a => (a.blocks || []).forEach(b => b.t === "img" && srcs.add(b.img.src)));
    return Promise.all(Array.from(srcs).map(src => new Promise(res => {
      const im = new Image(); im.onload = () => { imgMap.set(src, im); res(); }; im.onerror = () => res(); im.src = src;
    })));
  }
  function mathText(e, text) {
    const parts = String(text).split(/(\$\$[\s\S]+?\$\$|\$[^$\n]+\$)/);
    for (const p of parts) {
      if (!p) continue;
      const disp = p.startsWith("$$") && p.endsWith("$$"), inl = !disp && p.startsWith("$") && p.endsWith("$");
      if (disp || inl) {
        const s = el("span", disp ? "math display" : "math");
        const latex = disp ? p.slice(2, -2) : p.slice(1, -1);
        if (window.katex && typeof window.katex.render === "function") {
          try { window.katex.render(latex, s, { displayMode: !!disp, throwOnError: false, strict: "ignore", trust: false, output: "html" }); }
          catch (error) { s.textContent = latex; }
        } else { s.textContent = latex; }
        e.appendChild(s);
      } else e.appendChild(document.createTextNode(p));
    }
    return e;
  }
  function txtBlock(cls, text, q, keepNext) {
    return { kind: "text", q, keepNext: !!keepNext, text: String(text || ""),
      build: value => { const e = el("div", "blk " + cls); mathText(e, value == null ? text : value); return e; } };
  }
  function plainBlock(cls, text, keepNext) {
    return { keepNext: !!keepNext, build: () => el("div", "blk " + cls, text) };
  }
  function gapBlock(lines, q) {
    return { kind: "gap", q, lines, build: () => { const e = el("div", "blk question-gap"); e.style.setProperty("--gap-lines", String(lines)); return e; } };
  }
  function tableBlock(table, q) {
    return { kind: "table", q, build: () => {
      const wrap = el("div", "blk md-table-wrap"), node = el("table", "md-table"), thead = el("thead"), head = el("tr");
      (table.headers || []).forEach(cell => { const th = el("th"); mathText(th, cell); head.appendChild(th); }); thead.appendChild(head); node.appendChild(thead);
      const tbody = el("tbody"); (table.rows || []).forEach(row => { const tr = el("tr"); (row || []).forEach(cell => { const td = el("td"); mathText(td, cell); tr.appendChild(td); }); tbody.appendChild(tr); }); node.appendChild(tbody); wrap.appendChild(node); return wrap;
    } };
  }
  function headBlock(q) {
    return { keepNext: true, head: true, q, build: () => {
      const e = el("div", "blk q-head");
      const l1 = el("div", "q-head-line");
      l1.appendChild(el("span", "no", "第 " + q.idx + " 题"));
      l1.appendChild(el("span", "uid", "[" + q.uid + "]"));
      const labels = el("span", "labels"); appendLabelChips(labels, q.labels);
      if (labels.childNodes.length) l1.appendChild(labels);
      e.appendChild(l1);
      if (PRINT_STATE.show_meta !== false) {
        const bits = [q.subject, q.category].filter(Boolean);
        if (String(q.difficulty ?? "").trim()) bits.push("难度 " + q.difficulty + "/10");
        if (bits.length) e.appendChild(el("div", "meta", bits.join("  ·  ")));
      }
      return e;
    } };
  }
  function contHeadBlock(q) {
    return { q, build: () => {
      const e = el("div", "blk q-head cont");
      const l1 = el("div", "q-head-line");
      l1.appendChild(el("span", "no", "第 " + q.idx + " 题"));
      l1.appendChild(el("span", "uid", "[" + q.uid + "]"));
      l1.appendChild(el("span", "cont-tag", "（续）"));
      e.appendChild(l1);
      return e;
    } };
  }
  function imgBlock(b, q) { return { kind: "image", q, src: b.img.src, imgEl: imgMap.get(b.img.src) }; }

  function buildBlocks() {
    const B = [];
    (D.questions || []).forEach(q => {
      B.push({ kind: "qstart", q });
      B.push(headBlock(q));
      (q.blocks || []).forEach(b => {
        if (b.t === "img") B.push(imgBlock(b, q));
        else if (b.t === "table") B.push(tableBlock(b, q));
        else B.push(txtBlock("q-text", b.text, q, false));
      });
      B.push({ kind: "qend", q });
      // 服务端已把「继承全局 / 单题覆盖」算成绝对行数，模板不再做加法
      B.push(gapBlock(questionGap(q), q));
    });
    if (D.answers && D.answers.length) {
      B.push({ kind: "answers" });
      B.push(plainBlock("section", MODE === "new" ? "答案（本次新增）" : "答案", true));
      D.answers.forEach(a => {
        B.push({ keepNext: true, build: () => { const e = el("div", "blk ans-head"); e.innerHTML = "第 " + a.idx + " 题 <span>[" + esc(a.uid) + "]</span>"; return e; } });
        if (!(a.blocks || []).length) { B.push(plainBlock("ans-empty", "（暂无答案）")); return; }
        a.blocks.forEach(b => { if (b.t === "img") B.push(imgBlock(b, null)); else if (b.t === "table") B.push(tableBlock(b, null)); else B.push(txtBlock("ans-text", b.text, null, false)); });
      });
    }
    return B;
  }

  function run() {
    const mount = document.getElementById("stage");
    mount.replaceChildren();
    const t0 = performance.now();
    const blocks = buildBlocks();
    const options = {};
    if (PRINTED && PRINTED.pages > 0) {
      const cursor = PRINTED.cursor || {};
      options.startPage = clamp(Number(cursor.page) || PRINTED.pages, 1, PRINTED.pages);
      options.cursorY = Number(cursor.y) || 0;
      options.printedPages = PRINTED.pages;
    }
    const res = layout(blocks, mount, options);
    const ms = (performance.now() - t0).toFixed(0);
    const numbers = res.pages.map(p => p.number);
    const answerPages = res.pages.filter(p => p.answer).map(p => p.number);
    const totalPages = Math.max(PRINTED ? PRINTED.pages : 0, ...numbers, 0);
    const partialPage = res.pages.length && res.pages[0].partial ? res.pages[0].number : null;
    const layoutReport = {
      kind: "board", mode: MODE, board_id: META.board_id || "",
      pages: totalPages, page_numbers: numbers, rendered_pages: res.pages.length,
      partial_page: partialPage, cursor: res.cursor, items: res.items, answer_pages: answerPages,
      warnings: res.warnings, question_count: (D.questions || []).length,
    };
    window.OMRS_LAYOUT = layoutReport;
    const stat = document.getElementById("stat");
    if (stat) {
      const range = numbers.length ? (numbers.length === 1 ? "第 " + numbers[0] + " 页" : "第 " + numbers[0] + "–" + numbers[numbers.length - 1] + " 页") : "无内容";
      stat.textContent = (MODE === "new" ? "本次打印 " : "") + res.pages.length + " 页（" + range + "） · 排版 " + ms + "ms" + (res.warnings.length ? " · ⚠" + res.warnings.length + " 处告警" : "");
    }
    const notice = document.getElementById("notice");
    if (notice) {
      if (MODE === "new" && res.pages.length) {
        const fresh = numbers.filter(n => n !== partialPage);
        notice.innerHTML = "<b>只打印新增题目</b>（" + (D.questions || []).length + " 题，接在纸面记录第 " + (PRINTED.cursor ? PRINTED.cursor.page : "?") + " 页之后）。"
          + (partialPage ? "第 <b>" + partialPage + "</b> 页会印在<b>已打印的那张纸</b>上：请把它放回打印机（注意正反面与方向），已打印区域留白，只有新增内容出墨；" : "")
          + (fresh.length ? "第 <b>" + fresh[0] + (fresh.length > 1 ? "–" + fresh[fresh.length - 1] : "") + "</b> 页是新纸。" : "")
          + " 打印时选 A4、缩放 100%、不要勾选“适合页面”。打印完成后点「已打印，记录纸面」。";
        notice.classList.add("show");
      } else if (MODE === "new") {
        notice.textContent = "没有需要打印的新增题目。";
        notice.classList.add("show");
      } else {
        notice.classList.remove("show");
      }
      document.getElementById("stage").classList.toggle("no-notice", !notice.classList.contains("show"));
    }
    if (res.warnings.length) console.warn("排版告警:\n" + res.warnings.join("\n"));
    return layoutReport;
  }

  // ---------- 宿主协议：实时预览 ----------
  // 宿主（展示板页）把这份导出放进常驻 iframe，用消息驱动重排 / 翻页 / 缩放，
  // 几何类改动全程零网络请求；只有增删题、换模式这类内容变化才重新拉导出。
  let VIEW = { single: false, page: 0, scale: 1 };
  function viewStyleEl() {
    let node = document.getElementById("omrs-view-style");
    if (!node) { node = el("style"); node.id = "omrs-view-style"; document.head.appendChild(node); }
    return node;
  }
  function pageNumbers() { return [...document.querySelectorAll("#stage .page")].map(p => Number(p.dataset.page)); }
  function applyView() {
    const numbers = pageNumbers();
    if (!numbers.length) { viewStyleEl().textContent = ""; return; }
    if (!numbers.includes(VIEW.page)) VIEW.page = numbers[0];
    const rules = [];
    if (VIEW.single) {
      // 模板本身不需要知道「单页」这回事：每页早就有 data-page，靠一条 CSS 就能只留一面
      rules.push('#stage .page{display:none;}');
      rules.push('#stage .page[data-page="' + VIEW.page + '"]{display:block;}');
    }
    const scale = clamp(Number(VIEW.scale) || 1, .2, 2);
    if (scale !== 1) {
      rules.push("#stage{transform:scale(" + scale + ");transform-origin:top center;}");
      rules.push("#stage .page{margin-bottom:" + Math.round(22 / scale) + "px;}");
    }
    viewStyleEl().textContent = rules.join("\n");
    notify("omrs-board-view-state", window.OMRS_LAYOUT || null);
  }
  function gotoPage(value) {
    const numbers = pageNumbers();
    if (!numbers.length) return;
    const target = Number(value);
    VIEW.page = numbers.includes(target) ? target : numbers[0];
    applyView();
    if (!VIEW.single) document.querySelector('#stage .page[data-page="' + VIEW.page + '"]')?.scrollIntoView({ block: "start" });
  }
  function gotoUid(uid) {
    const node = document.querySelector('#stage [data-q-uid="' + String(uid).replace(/["\\\\]/g, "\\\\$&") + '"]');
    const page = node && node.closest(".page");
    if (page) gotoPage(Number(page.dataset.page));
  }
  function relayout(message) {
    if (message && message.gaps && typeof message.gaps === "object") GAPS = message.gaps;
    applyPrint(message && message.print);
    const report = run();
    applyView();
    notify("omrs-board-layout", report);
    return report;
  }

  function waitForTwoFrames() { return new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); }

  function notifyRaw(payload) {
    try { if (window.opener && !window.opener.closed) window.opener.postMessage(payload, "*"); } catch (e) {}
    try { if (window.parent && window.parent !== window) window.parent.postMessage(payload, "*"); } catch (e) {}
  }
  function notify(type, layoutReport) {
    notifyRaw({ type, boardId: META.board_id || "", mode: MODE, layout: layoutReport, view: { single: VIEW.single, page: VIEW.page, scale: VIEW.scale } });
  }

  function loadedFontKeys() {
    const keys = new Set();
    try { document.fonts.forEach(face => { if (face.status === "loaded") keys.add(face.family + "|" + face.weight + "|" + face.style); }); } catch (e) {}
    return keys;
  }
  function hasMath() {
    const probe = list => (list || []).some(item => (item.blocks || []).some(b =>
      (b.t === "txt" && /\$/.test(b.text || "")) || (b.t === "table" && JSON.stringify([b.headers, b.rows]).indexOf("$") >= 0)));
    return probe(D.questions) || probe(D.answers);
  }
  // 有公式时先把常用 KaTeX 字体解码好：否则首轮排版用后备字体测高，之后还得整体重排一遍
  async function warmFonts() {
    if (!hasMath() || !document.fonts || typeof document.fonts.load !== "function") return;
    const specs = ['normal 400 16px "KaTeX_Main"', 'normal 700 16px "KaTeX_Main"', 'italic 400 16px "KaTeX_Main"',
      'italic 400 16px "KaTeX_Math"', 'normal 400 16px "KaTeX_Size1"', 'normal 400 16px "KaTeX_Size2"',
      'normal 400 16px "KaTeX_Size3"', 'normal 400 16px "KaTeX_Size4"', 'normal 400 16px "KaTeX_AMS"'];
    await Promise.all(specs.map(spec => document.fonts.load(spec).catch(() => null)));
  }
  async function initialRun() {
    const t0 = performance.now();
    await Promise.all([preload(), warmFonts()]);
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    await waitForTwoFrames();
    const before = loadedFontKeys();
    let report = run(), passes = 1;
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    // 只有首轮排版真的触发了新字体加载（少见的字体族 / 未预热的字重）才用最终字体重排一次
    if ([...loadedFontKeys()].some(key => !before.has(key))) { await waitForTwoFrames(); report = run(); passes = 2; }
    window.OMRS_LAYOUT_TIMING = { total_ms: Math.round(performance.now() - t0), passes };
    const stat = document.getElementById("stat");
    if (stat) stat.textContent += " · 就绪 " + ((performance.now() - t0) / 1000).toFixed(1) + "s";
    document.documentElement.dataset.omrsLayoutReady = "1";
    const printButton = document.getElementById("btnPrint");
    if (printButton) printButton.disabled = false;
    notify("omrs-board-layout", report);
  }

  document.addEventListener("DOMContentLoaded", () => {
    const p = document.getElementById("btnPrint");
    if (p) { p.disabled = true; p.onclick = () => window.print(); }
    const d = document.getElementById("btnDebug"); if (d) d.onchange = e => document.body.classList.toggle("debug", e.target.checked);
    const done = document.getElementById("btnDone");
    if (done) done.onclick = () => {
      if (!window.OMRS_LAYOUT) return;
      const hasOpener = !!(window.opener && !window.opener.closed);
      notify("omrs-board-printed", window.OMRS_LAYOUT);
      const stat = document.getElementById("stat");
      if (stat) stat.textContent = hasOpener ? "已通知主程序记录纸面，回到 OMRS 确认即可" : "这个窗口不是从 OMRS 打开的：请回到展示板页点「标记为已打印」";
      done.disabled = true;
    };
    initialRun();
  });
  window.addEventListener("message", event => {
    const message = event.data;
    if (!message || typeof message !== "object") return;
    if (message.type === "omrs-board-request-layout" && window.OMRS_LAYOUT) { notify("omrs-board-layout", window.OMRS_LAYOUT); return; }
    if (message.type === "omrs-board-relayout") { relayout(message); return; }
    if (message.type === "omrs-board-goto") {
      if (message.uid) gotoUid(message.uid); else gotoPage(message.page);
      return;
    }
    if (message.type === "omrs-board-view") {
      if (message.single != null) VIEW.single = !!message.single;
      if (message.page != null) VIEW.page = Number(message.page) || VIEW.page;
      if (message.scale != null) VIEW.scale = Number(message.scale) || 1;
      applyView();
      return;
    }
  });
  // ---- 拖切割线 = 改这道题的题后留白 ----
  // 拖动过程中**不重排**：只把线和一个读数移到指针处。重排要跑一遍完整 run()，
  // 大板上每个 pointermove 都排一次会顿；松手才提交一次，由宿主统一 relayout + 保存。
  // 全程零网络请求：宿主拿到 omrs-board-gap 后走 relayout，不重新请求导出。
  const GAP_MIN = 0, GAP_MAX = 48, LINE_PX = 18;
  let DRAG = null;
  function dragLabel(line) {
    let tag = line.querySelector(".drag-tag");
    if (!tag) { tag = el("span", "drag-tag"); line.appendChild(tag); }
    return tag;
  }
  function dragScale() { return clamp(Number(VIEW.scale) || 1, .2, 2); }
  document.addEventListener("pointerdown", event => {
    const line = event.target.closest && event.target.closest(".cut-line.draggable");
    if (!line || event.button !== 0) return;
    event.preventDefault();
    DRAG = { line, uid: line.dataset.cutUid, startY: event.clientY,
             startLines: clamp(Number(line.dataset.cutLines) || 0, GAP_MIN, GAP_MAX),
             top: parseFloat(line.style.top) || 0, lines: null };
    try { line.setPointerCapture(event.pointerId); } catch (e) {}
    line.classList.add("dragging");
    document.body.classList.add("dragging-cut");
  });
  document.addEventListener("pointermove", event => {
    if (!DRAG) return;
    // 缩放后 1 个屏幕像素不等于 1 个版面像素，换算回版面坐标再折成行
    const delta = (event.clientY - DRAG.startY) / dragScale();
    const lines = clamp(Math.round(DRAG.startLines + delta / LINE_PX), GAP_MIN, GAP_MAX);
    DRAG.lines = lines;
    DRAG.line.style.top = (DRAG.top + (lines - DRAG.startLines) * LINE_PX) + "px";
    dragLabel(DRAG.line).textContent = lines + " 行 ≈ " + (Math.round(lines * LINE_PX / MM / 10 * 10) / 10) + " cm";
  });
  function endDrag() {
    if (!DRAG) return;
    const drag = DRAG;
    DRAG = null;
    drag.line.classList.remove("dragging");
    document.body.classList.remove("dragging-cut");
    drag.line.querySelector(".drag-tag")?.remove();
    if (drag.lines == null || drag.lines === drag.startLines) {
      drag.line.style.top = drag.top + "px";                 // 没动过：归位，不打扰宿主
      return;
    }
    // 只报「哪道题、几行」；夹紧与保存都由宿主负责，模板不认识 boards.json
    notifyRaw({ type: "omrs-board-gap", boardId: META.board_id || "", uid: drag.uid, lines: drag.lines });
  }
  document.addEventListener("pointerup", endDrag);
  document.addEventListener("pointercancel", endDrag);

  // 点纸面上的题 → 告诉宿主选中了谁，宿主据此高亮检视条 / 列表行
  document.addEventListener("click", event => {
    if (event.target.closest && event.target.closest(".cut-line")) return;   // 拖线不是选题
    const node = event.target.closest && event.target.closest("#stage [data-q-uid]");
    if (!node) return;
    const page = node.closest(".page");
    notifyRaw({ type: "omrs-board-select", boardId: META.board_id || "", uid: node.dataset.qUid,
                idx: Number(node.dataset.qIdx) || null, page: page ? Number(page.dataset.page) : null });
  });
})();
