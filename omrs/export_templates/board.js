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
  const bindingMm = clamp(Number(PRINT.binding_mm) || 22, 10, 40);
  const noteRatio = clamp(Number(PRINT.note_ratio) || .42, .30, .55);
  const gapLines = clamp(Number(PRINT.gap_lines) || 0, 0, 24);
  const BINDING = bindingMm * MM;
  const CONTENT_W = PAGE_W - BINDING - MARGIN_R;
  const CONTENT_H = PAGE_H - 2 * MARGIN_TB - FOOTER_SAFE;
  const COL_W = Math.floor((CONTENT_W - COL_GAP) * (1 - noteRatio) * 100) / 100;
  const COL_H = CONTENT_H - HEAD_H;

  function el(tag, cls, txt) { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

  // ---- 像素分析：每行墨量 + 干净缝带（与 a4.js 一致） ----
  const _cache = new Map();
  function analyze(img) {
    if (_cache.has(img.src)) return _cache.get(img.src);
    const W = img.naturalWidth, H = img.naturalHeight;
    const cv = document.createElement("canvas"); cv.width = W; cv.height = H;
    const ctx = cv.getContext("2d", { willReadFrequently: true });
    ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, W, H); ctx.drawImage(img, 0, 0);
    const data = ctx.getImageData(0, 0, W, H).data;
    const ink = new Int32Array(H);
    for (let y = 0; y < H; y++) {
      let c = 0, o = y * W * 4;
      for (let x = 0; x < W; x++) { const i = o + x * 4; if (Math.min(data[i], data[i + 1], data[i + 2]) < WHITE_THR) c++; }
      ink[y] = c;
    }
    const sorted = Array.from(ink).sort((a, b) => a - b);
    const floor = sorted[Math.floor(H * 0.05)] || 0;
    const quietThr = floor + Math.max(2, Math.round(W * 0.004));
    const G = Math.max(4, Math.round(H * 0.004));
    const bands = []; let s = -1;
    for (let y = 0; y <= H; y++) {
      const q = (y < H) && ink[y] <= quietThr;
      if (q) { if (s < 0) s = y; } else { if (s >= 0) { if (y - s >= G) bands.push([s, y]); s = -1; } }
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
    inner.style.left = BINDING + "px"; inner.style.top = MARGIN_TB + "px";
    inner.style.width = CONTENT_W + "px"; inner.style.height = CONTENT_H + "px";
    const head = el("div", "head");
    head.appendChild(el("span", "ttl", META.title || "错题集"));
    if (PRINT.show_meta !== false && META.generated) head.appendChild(el("span", "sub", META.generated));
    inner.appendChild(head);
    const col = el("div", "col");
    col.style.width = COL_W + "px"; col.style.height = COL_H + "px";
    inner.appendChild(col);
    page.appendChild(inner);
    // 装订辅助：左边距内一条极浅虚线（12mm 处）
    const line = el("div", "bind-line"); line.style.left = (12 * MM) + "px"; page.appendChild(line);
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
      if (y + h > COL_H + 0.5) { node.style.height = Math.max(0, COL_H - y) + "px"; forcePut(node, null); y = COL_H; return; }
      put(node, null);
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
  function gapBlock(lines) {
    return { kind: "gap", build: () => { const e = el("div", "blk question-gap"); e.style.setProperty("--gap-lines", String(lines)); return e; } };
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
      if (PRINT.show_meta !== false) {
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
      B.push(gapBlock(gapLines + clamp(Number(q.extra_gap_lines) || 0, 0, 24)));
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

  function waitForTwoFrames() { return new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); }

  function notify(type, layoutReport) {
    const payload = { type, boardId: META.board_id || "", mode: MODE, layout: layoutReport };
    try { if (window.opener && !window.opener.closed) window.opener.postMessage(payload, "*"); } catch (e) {}
    try { if (window.parent && window.parent !== window) window.parent.postMessage(payload, "*"); } catch (e) {}
  }

  async function initialRun() {
    await preload();
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    await waitForTwoFrames();
    run();                       // 首轮触发 KaTeX 字体加载
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    await waitForTwoFrames();
    const report = run();        // 用最终字体重排一次，打印复用这份 DOM
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
    if (event.data && event.data.type === "omrs-board-request-layout" && window.OMRS_LAYOUT) notify("omrs-board-layout", window.OMRS_LAYOUT);
  });
})();
