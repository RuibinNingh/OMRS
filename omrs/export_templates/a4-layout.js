/* OMRS A4 排版引擎（落地版）
 * 浏览器按当前媒体真实测量；中文字体与行高固定，打印前复核栏底。
 *   1) 按栏宽测每个内容块的真实渲染高度（长文字题干由浏览器自动折行）；
 *   2) 贪心填进固定尺寸的 A4 双栏页；
 *   3) 图片高过一整栏必切（防截断），或高过当前栏剩余且有干净白缝则切来填栏；
 *      无干净缝则整段顺到下一栏（绝不为填栏切穿内容）。
 *   切口靠读像素找“缝带”，切片用 overflow 裁切同一张内嵌图（只存一份，浏览器无 WPS 白底涂白 bug）。
 */
(function () {
  "use strict";
  const MM = 3.779528;
  const PAGE_W = 210 * MM, PAGE_H = 297 * MM;
  const MARGIN_TB = 12.7 * MM, MARGIN_LR = 6.35 * MM, COL_GAP = 12.7 * MM;
  const FOOTER_SAFE = 8.5 * MM;
  const COL_W = (PAGE_W - 2 * MARGIN_LR - COL_GAP) / 2;
  const COL_H = PAGE_H - 2 * MARGIN_TB - FOOTER_SAFE;
  const SAFETY = 4, MIN_FILL = 40, MIN_SLICE = 28, WHITE_THR = 245, ORPHAN = 56;


  // ---- 像素分析：每行墨量 + 干净缝带 ----
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

  function el(tag, cls, txt) { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
  function sliceEl(src, dispW, naturalW, y0, y1, mark) {
    const scale = dispW / naturalW;
    const wrap = el("div", "slice"); wrap.style.width = dispW + "px"; wrap.style.height = (y1 - y0) * scale + "px";
    const im = el("img"); im.src = src; im.style.width = dispW + "px"; im.style.marginTop = (-y0 * scale) + "px";
    wrap.appendChild(im); if (mark) wrap.classList.add(mark); return wrap;
  }

  function layout(blocks, mount, singleColumn) {
    const warnings = [];
    let colW = singleColumn ? PAGE_W - 2 * MARGIN_LR : COL_W;
    let colH = COL_H;
    const tolerance = 0.02;
    const measurer = el("div", "measurer"); measurer.style.width = colW + "px";
    mount.parentNode.insertBefore(measurer, mount);
    const pages = [];
    let page = null, colIdx = 0, col = null, y = 0;
    function newPage() {
      page = el("div", singleColumn ? "page single" : "page"); const inner = el("div", "page-inner");
      const c0 = el("div", "col"); inner.appendChild(c0);
      const cols = [c0];
      if (!singleColumn) { const c1 = el("div", "col"); inner.appendChild(c1); cols.push(c1); }
      page.appendChild(inner); page._cols = cols; pages.push(page); mount.appendChild(page); colIdx = 0; col = c0; y = 0;
      colW = col.getBoundingClientRect().width;
      colH = col.getBoundingClientRect().height;
      measurer.style.width = colW + "px";
    }
    function nextCol() { if (!singleColumn && colIdx === 0) { colIdx = 1; col = page._cols[1]; y = 0; } else { newPage(); } }
    // 先测量只是快速判断；真正落位后再以 DOM 的实际底边为准，避免字体/行距差异把内容塞出栏底。
    function put(node) {
      col.appendChild(node);
      const used = node.getBoundingClientRect().bottom - col.getBoundingClientRect().top;
      if (used > colH + tolerance) { col.removeChild(node); return false; }
      y = used;
      return true;
    }
    function forcePut(node) {
      col.appendChild(node);
      y = node.getBoundingClientRect().bottom - col.getBoundingClientRect().top;
    }
    function measure(node) { measurer.appendChild(node); const h = node.getBoundingClientRect().height; measurer.removeChild(node); return h; }

    function formulaBreakOffsets(text) {
      const source = String(text || "");
      const token = /(\$\$[\s\S]+?\$\$|\$[^$\n]+\$)/g;
      const offsets = [];
      let match;
      while ((match = token.exec(source))) offsets.push(match.index);
      return offsets;
    }

    // 只在整段放不下时才动公式：把“公式之前的文字”留在当前栏，公式及后文从下一栏继续。
    // 从靠后的公式开始试，尽可能少地移动文字；普通文本没有公式边界时仍沿用原来的整段换栏。
    function splitFormulaText(b, source) {
      const offsets = formulaBreakOffsets(source);
      for (let i = offsets.length - 1; i >= 0; i--) {
        const cut = offsets[i];
        const prefix = source.slice(0, cut);
        if (!prefix.trim()) continue;
        const prefixNode = b.build(prefix);
        const prefixH = measure(prefixNode);
        if (y + prefixH > colH + tolerance || !put(prefixNode)) continue;
        nextCol();
        return placeText(b, source.slice(cut));
      }
      return false;
    }

    function placeText(b, source) {
      const node = b.build(source);
      const h = measure(node);
      if (y + h <= colH + tolerance && put(node)) return true;
      if (splitFormulaText(b, source)) return true;
      nextCol();
      if (put(node)) return true;
      // 已确认的极端场景：单个公式即使在新栏也过高；不在本次改动中缩放或重写公式。
      forcePut(node);
      return false;
    }

    function placePlainBlock(b) {
      const node = b.build(); const h = measure(node);
      if (b.keepNext && colH - y < h + ORPHAN) nextCol();
      if (y + h > colH + tolerance) nextCol();
      if (put(node)) return true;
      nextCol();
      if (put(node)) return true;
      forcePut(node);
      return false;
    }

    function placeContentBlock(b) {
      if (b.kind === "image") { placeImage(b); return true; }
      if (b.kind === "text") return placeText(b, b.text);
      return placePlainBlock(b);
    }

    newPage();
    for (const b of blocks) {
      placeContentBlock(b);
    }

    function placeImage(b) {
      const im = b.imgEl;
      if (!im || !im.naturalWidth) { return; } // 解码失败：跳过(不致命)
      const naturalW = im.naturalWidth, naturalH = im.naturalHeight;
      const dispScale = colW / naturalW, dispH = naturalH * dispScale;
      if (b.keepNextHeader && colH - y < 64) nextCol();
      if (dispH <= colH - y + tolerance) {
        const node = sliceEl(b.src, colW, naturalW, 0, naturalH);
        if (!put(node)) { nextCol(); if (!put(node)) forcePut(node); }
        return;
      }
      const an = analyze(im);
      let start = 0;
      while (start < naturalH) {
        const remDisp = colH - y, remPx = remDisp / dispScale, colPx = colH / dispScale;
        const restPx = naturalH - start, restDisp = restPx * dispScale;
        if (restDisp <= remDisp + tolerance) {
          const node = sliceEl(b.src, colW, naturalW, start, naturalH);
          if (!put(node)) { nextCol(); if (!put(node)) forcePut(node); }
          return;
        }
        const fitsAColumn = restDisp <= colH + tolerance;
        if (fitsAColumn) {
          if (remDisp >= MIN_FILL) {
            const cap = Math.max(MIN_SLICE, Math.floor(remPx - SAFETY / dispScale));
            const cut = findCut(an, start, cap);
            if (cut !== null) { const node = sliceEl(b.src, colW, naturalW, start, cut); if (!put(node)) { nextCol(); if (!put(node)) forcePut(node); } start = cut; nextCol(); continue; }
          }
          nextCol(); const node = sliceEl(b.src, colW, naturalW, start, naturalH); if (!put(node)) forcePut(node); return;
        }
        let cap = Math.max(MIN_SLICE, Math.floor((remDisp >= MIN_FILL ? remPx : colPx) - SAFETY / dispScale));
        cap = Math.min(cap, Math.floor(colPx - SAFETY / dispScale));
        let cut = findCut(an, start, cap), mark = null;
        if (cut === null) {
          if (remDisp < MIN_FILL && y > 0) { nextCol(); continue; }
          const lo = start + MIN_SLICE, hi = Math.max(start + MIN_SLICE, start + cap);
          cut = leastInk(an, lo, hi); mark = "clip-warn";
          warnings.push("「" + (b.label || "?") + "」图无干净白缝，于 " + start + "→" + cut + "px 被迫切，可能擦到内容");
        }
        if (cut <= start) cut = Math.min(start + Math.floor(cap), naturalH - 1);
        const node = sliceEl(b.src, colW, naturalW, start, cut, mark);
        if (!put(node)) { nextCol(); if (!put(node)) forcePut(node); }
        start = cut; nextCol();
      }
    }

    measurer.remove();
    pages.forEach((p, i) => { const f = el("div", "pagenum", (i + 1) + " / " + pages.length); p.appendChild(f); });
    return { pages: pages.length, warnings };
  }

  window.OMRS_A4_LAYOUT = layout;
})();
