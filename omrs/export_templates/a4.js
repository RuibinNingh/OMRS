/* OMRS A4 排版引擎（落地版）
 * 浏览器既是排版引擎、又是你最终看的引擎 —— 所见即所打印，无需预测、无跨渲染器保真度差。
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
  const COL_W = (PAGE_W - 2 * MARGIN_LR - COL_GAP) / 2;
  const COL_H = PAGE_H - 2 * MARGIN_TB;
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

  function layout(blocks, mount) {
    const warnings = [];
    const measurer = el("div", "measurer"); measurer.style.width = COL_W + "px";
    mount.parentNode.insertBefore(measurer, mount);
    const pages = [];
    let page = null, colIdx = 0, col = null, y = 0;
    function newPage() {
      page = el("div", "page"); const inner = el("div", "page-inner");
      const c0 = el("div", "col"), c1 = el("div", "col"); inner.appendChild(c0); inner.appendChild(c1);
      page.appendChild(inner); page._cols = [c0, c1]; pages.push(page); colIdx = 0; col = c0; y = 0;
    }
    function nextCol() { if (colIdx === 0) { colIdx = 1; col = page._cols[1]; y = 0; } else { newPage(); } }
    function put(node, h) { col.appendChild(node); y += h; }
    function measure(node) { measurer.appendChild(node); const h = node.getBoundingClientRect().height; measurer.removeChild(node); return h; }

    newPage();
    for (const b of blocks) {
      if (b.kind === "image") { placeImage(b); continue; }
      const node = b.build(); const h = measure(node);
      if (b.keepNext && COL_H - y < h + ORPHAN) nextCol();
      if (y + h > COL_H + 0.5) nextCol();
      put(node, h);
    }

    function placeImage(b) {
      const im = b.imgEl;
      if (!im || !im.naturalWidth) { return; } // 解码失败：跳过(不致命)
      const naturalW = im.naturalWidth, naturalH = im.naturalHeight;
      const dispScale = COL_W / naturalW, dispH = naturalH * dispScale;
      if (b.keepNextHeader && COL_H - y < 64) nextCol();
      if (dispH <= COL_H - y + 0.5) { put(sliceEl(b.src, COL_W, naturalW, 0, naturalH), dispH); return; }
      const an = analyze(im);
      let start = 0;
      while (start < naturalH) {
        const remDisp = COL_H - y, remPx = remDisp / dispScale, colPx = COL_H / dispScale;
        const restPx = naturalH - start, restDisp = restPx * dispScale;
        if (restDisp <= remDisp + 0.5) { put(sliceEl(b.src, COL_W, naturalW, start, naturalH), restDisp); return; }
        const fitsAColumn = restDisp <= COL_H + 0.5;
        if (fitsAColumn) {
          if (remDisp >= MIN_FILL) {
            const cap = Math.max(MIN_SLICE, Math.floor(remPx - SAFETY / dispScale));
            const cut = findCut(an, start, cap);
            if (cut !== null) { put(sliceEl(b.src, COL_W, naturalW, start, cut), (cut - start) * dispScale); start = cut; nextCol(); continue; }
          }
          nextCol(); put(sliceEl(b.src, COL_W, naturalW, start, naturalH), restDisp); return;
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
        put(sliceEl(b.src, COL_W, naturalW, start, cut, mark), (cut - start) * dispScale);
        start = cut; nextCol();
      }
    }

    measurer.remove();
    pages.forEach((p, i) => { const f = el("div", "pagenum", (i + 1) + " / " + pages.length); p.appendChild(f); mount.appendChild(p); });
    return { pages: pages.length, warnings };
  }

  // ---------- 应用层：数据 -> 内容块 ----------
  const D = window.OMRS_DATA || { questions: [] };
  const imgMap = new Map();
  function preload() {
    const srcs = new Set();
    (D.questions || []).forEach(q => q.blocks.forEach(b => b.t === "img" && srcs.add(b.img.src)));
    (D.answers || []).forEach(a => a.blocks.forEach(b => b.t === "img" && srcs.add(b.img.src)));
    return Promise.all(Array.from(srcs).map(src => new Promise(res => {
      const im = new Image(); im.onload = () => { imgMap.set(src, im); res(); }; im.onerror = () => res(); im.src = src;
    })));
  }
  function mathText(e, text) {
    // 把 $...$ / $$...$$ 渲染为辨识用的样式片段（无 KaTeX 依赖；纯文本原样）
    const parts = String(text).split(/(\$\$[^$]+\$\$|\$[^$\n]+\$)/);
    for (const p of parts) {
      if (!p) continue;
      const disp = p.startsWith("$$") && p.endsWith("$$"), inl = !disp && p.startsWith("$") && p.endsWith("$");
      if (disp || inl) { const s = el("span", "math", disp ? p.slice(2, -2) : p.slice(1, -1)); e.appendChild(s); }
      else e.appendChild(document.createTextNode(p));
    }
    return e;
  }
  function txtBlock(cls, text, keepNext, withMath) {
    return { keepNext: !!keepNext, build: () => { const e = el("div", "blk " + cls); withMath ? mathText(e, text) : (e.textContent = text); return e; } };
  }
  function headBlock(q) {
    return { keepNext: true, build: () => {
      const e = el("div", "blk q-head");
      const l1 = el("div"); l1.innerHTML = '<span class="no">第 ' + q.idx + ' 题</span><span class="uid">[' + esc(q.uid) + ']</span>'; e.appendChild(l1);
      e.appendChild(el("div", "meta", "科目: " + q.subject + "    分类: " + q.category + "    难度: " + q.difficulty + "/10"));
      if (q.tags) e.appendChild(el("div", "tags", "标签: " + q.tags));
      return e;
    } };
  }
  function ansHeadBlock(a) {
    return { keepNext: true, build: () => { const e = el("div", "blk q-head"); e.innerHTML = '<span class="no">第 ' + a.idx + ' 题</span><span class="uid">[' + esc(a.uid) + ']</span>'; return e; } };
  }
  function noteBlock(k, v) { return { build: () => { const e = el("div", "blk q-note"); e.innerHTML = "<b>" + k + "：</b>"; mathText(e, v); return e; } }; }
  function imgBlock(b, label, firstOfQ) { return { kind: "image", src: b.img.src, imgEl: imgMap.get(b.img.src), label: label, keepNextHeader: !!firstOfQ }; }
  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

  function buildBlocks() {
    const B = [];
    B.push(txtBlock("doc-title", (D.meta && D.meta.title) || "OMRS 错题复习清单"));
    if (D.meta && D.meta.sub) B.push(txtBlock("doc-sub", D.meta.sub));
    B.push(txtBlock("doc-note", "请在下方空白处作答，完成后在末尾的反馈表中打分和勾选对错。"));
    B.push(txtBlock("section", "一、题目", true));
    (D.questions || []).forEach(q => {
      B.push(headBlock(q)); let first = true;
      q.blocks.forEach(b => { if (b.t === "img") B.push(imgBlock(b, q.uid, first)); else B.push(txtBlock("q-text", b.text, false, true)); first = false; });
      if (q.notes && q.notes["错因"]) B.push(noteBlock("错因", q.notes["错因"]));
      if (q.notes && q.notes["关联"]) B.push(noteBlock("关联", q.notes["关联"]));
    });
    if (D.feedback && D.feedback.length) {
      B.push(txtBlock("section", "二、反馈勾选表", true));
      B.push(txtBlock("doc-note", "完成后按行填写。主观分 0-10，数字越大越熟练。"));
      D.feedback.forEach(f => B.push({ build: () => { const e = el("div", "blk fb-row"); e.innerHTML = '<span class="u">' + esc(f.uid) + '</span><span class="c">分___　□对　□错　页___</span>'; return e; } }));
    }
    if (D.answers && D.answers.length) {
      B.push(txtBlock("section", "三、答案", true));
      (D.answers || []).forEach(a => {
        B.push(ansHeadBlock(a));
        if (!a.blocks.length) { B.push(txtBlock("ans-empty", "（暂无答案）")); return; }
        let first = true;
        a.blocks.forEach(b => { if (b.t === "img") B.push(imgBlock(b, a.uid, first)); else B.push(txtBlock("ans-text", b.text, false, true)); first = false; });
      });
    }
    return B;
  }

  function run() {
    const mount = document.getElementById("stage");
    const t0 = performance.now();
    const res = layout(buildBlocks(), mount);
    const ms = (performance.now() - t0).toFixed(0);
    const stat = document.getElementById("stat");
    if (stat) stat.textContent = res.pages + " 页 · 排版 " + ms + "ms" + (res.warnings.length ? " · ⚠" + res.warnings.length + " 处被迫切穿" : " · 无切穿");
    if (res.warnings.length) console.warn("切片告警:\n" + res.warnings.join("\n"));
    window.__OMRS_RESULT = res;
  }
  document.addEventListener("DOMContentLoaded", () => {
    const p = document.getElementById("btnPrint"); if (p) p.onclick = () => window.print();
    const d = document.getElementById("btnDebug"); if (d) d.onchange = e => document.body.classList.toggle("debug", e.target.checked);
    preload().then(run);
  });
})();
