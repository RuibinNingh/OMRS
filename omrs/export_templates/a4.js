/* A4 应用层：题面构造、字体等待与打印生命周期。 */
(function () {
  "use strict";
  function el(tag, cls, txt) { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
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
      const chip = el("span", "lbl print", name);
      chip.style.setProperty("--lbl-rgb", labelRgb(item.color).join(","));
      chip.style.setProperty("--lbl-ink", item.ink || "#475569");
      parent.appendChild(chip);
    });
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
        } else {
          s.textContent = latex;
        }
        e.appendChild(s);
      }
      else e.appendChild(document.createTextNode(p));
    }
    return e;
  }
  function txtBlock(cls, text, keepNext, withMath) {
    return {
      kind: withMath ? "text" : "",
      keepNext: !!keepNext,
      text: String(text || ""),
      build: value => {
        const e = el("div", "blk " + cls);
        const source = value == null ? text : value;
        withMath ? mathText(e, source) : (e.textContent = source);
        return e;
      },
    };
  }
  function questionGapBlock(lines) { return { build: () => {
    const e = el("div", "blk question-gap");
    e.style.setProperty("--gap-lines", String(lines));
    return e;
  } }; }
  function tableBlock(table) { return { kind: "table", build: () => {
    const wrap = el("div", "blk md-table-wrap"), node = el("table", "md-table"), thead = el("thead"), head = el("tr");
    (table.headers || []).forEach(cell => { const th = el("th"); mathText(th, cell); head.appendChild(th); }); thead.appendChild(head); node.appendChild(thead);
    const tbody = el("tbody"); (table.rows || []).forEach(row => { const tr = el("tr"); (row || []).forEach(cell => { const td = el("td"); mathText(td, cell); tr.appendChild(td); }); tbody.appendChild(tr); }); node.appendChild(tbody); wrap.appendChild(node); return wrap;
  } }; }
  function headBlock(q) {
    return { keepNext: true, build: () => {
      const e = el("div", "blk q-head");
      const l1 = el("div", "q-head-line");
      l1.appendChild(el("span", "no", "第 " + q.idx + " 题"));
      l1.appendChild(el("span", "uid", "[" + q.uid + "]"));
      const labels = el("span", "labels");
      appendLabelChips(labels, q.labels);
      if (labels.childNodes.length) l1.appendChild(labels);
      e.appendChild(l1);
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
    B.push(txtBlock("doc-note", "请在下方空白处作答，做完后再翻到末尾的反馈区核对答案与错因。"));
    B.push(txtBlock("section", "一、题目", true));
    const questionGapLines = Math.max(0, Math.min(20, Number(D.meta && D.meta.question_gap_lines) || 0));
    (D.questions || []).forEach((q, index) => {
      B.push(headBlock(q)); let first = true;
      q.blocks.forEach(b => {
        if (b.t === "img") B.push(imgBlock(b, q.uid, first));
        else if (b.t === "table") B.push(tableBlock(b));
        else B.push(txtBlock("q-text", b.text, false, true));
        first = false;
      });
      // 题面区只有「关联」；「错因」会提示解法，一律留在末尾反馈区
      if (q.notes && q.notes["关联"]) B.push(noteBlock("关联", q.notes["关联"]));
      if (questionGapLines && index < D.questions.length - 1) B.push(questionGapBlock(questionGapLines));
    });
    // 反馈区：勾选答案时「第 N 题」下面紧跟答案和错因（不分开）；不勾选时只剩错因。
    // 既没答案又没错因的题不占位，整体无内容时整段不输出。
    const withAnswer = (D.answers || []).some(a => a.blocks && a.blocks.length);
    const fed = (D.answers || []).filter(a => withAnswer || (a.notes && a.notes["错因"]));
    if (fed.length) {
      B.push(txtBlock("section", "二、反馈区", true));
      B.push(txtBlock("doc-note", withAnswer
        ? "每题下方是答案与错因。"
        : "本次未导出答案，只列错因。"));
      fed.forEach(a => {
        B.push(ansHeadBlock(a));
        let first = true;
        (a.blocks || []).forEach(b => { if (b.t === "img") B.push(imgBlock(b, a.uid, first)); else if (b.t === "table") B.push(tableBlock(b)); else B.push(txtBlock("ans-text", b.text, false, true)); first = false; });
        if (withAnswer && !(a.blocks || []).length) B.push(txtBlock("ans-empty", "（暂无答案）"));
        if (a.notes && a.notes["错因"]) B.push(noteBlock("错因", a.notes["错因"]));
      });
    }
    return B;
  }

  function run() {
    const mount = document.getElementById("stage");
    document.body.classList.remove("print-invalid");
    mount.replaceChildren();
    const t0 = performance.now();
    const blocks = buildBlocks();
    const res = window.OMRS_A4_LAYOUT(blocks, mount, !(D.meta && D.meta.a4_two_columns !== false));
    const overflow = [...mount.querySelectorAll(".col")].some(column => {
      const bounds = column.getBoundingClientRect();
      return [...column.children].some(child => child.getBoundingClientRect().bottom > bounds.bottom + 0.03);
    });
    if (overflow) throw new Error("有内容超出 A4 栏高，请改用单栏或调整超长公式后重新导出。");
    const ms = (performance.now() - t0).toFixed(0);
    const stat = document.getElementById("stat");
    if (stat) stat.textContent = res.pages + " 页 · 排版 " + ms + "ms" + (res.warnings.length ? " · ⚠" + res.warnings.length + " 处被迫切穿" : " · 无切穿");
    if (res.warnings.length) console.warn("切片告警:\n" + res.warnings.join("\n"));
    window.__OMRS_RESULT = { ...res, errors: [] };
  }

  let ready = false, resizeTimer = null;
  function failed(error) {
    ready = false;
    document.body.classList.add("print-invalid");
    const message = error instanceof Error ? error.message : String(error);
    document.getElementById("stage").replaceChildren(el("div", "layout-error", "排版失败：" + message));
    document.getElementById("stat").textContent = "排版未完成";
    document.getElementById("btnPrint").disabled = true;
    window.__OMRS_RESULT = { pages: 0, warnings: [], errors: [message] };
  }
  function relayout() {
    if (!ready) return;
    clearTimeout(resizeTimer);
    try { run(); } catch (error) { failed(error); }
  }

  function preparePrint() {
    if (!ready) {
      if (!window.__OMRS_RESULT?.errors?.length) document.body.classList.add("print-pending");
      return;
    }
    relayout();
  }
  function finishPrint() {
    document.body.classList.remove("print-pending");
    relayout();
  }
  // 打印媒体已生效时同步重排，不能依赖异步帧回调完成打印准备。
  window.addEventListener("beforeprint", preparePrint);
  window.addEventListener("afterprint", finishPrint);
  window.matchMedia("print").addEventListener("change", event => event.matches ? preparePrint() : finishPrint());
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(relayout, 80);
  });

  function waitForTwoFrames() {
    return new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  }

  async function initialRun() {
    await preload();
    // 先等页面已有字体，再生成含 KaTeX 的 DOM。
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    await waitForTwoFrames();
    // KaTeX 字体是在 run() 创建数学节点后才会被浏览器请求；必须再等一次，
    // 否则首轮测量用 fallback 字体，打印时字体完成会把栏底内容挤出去。
    run();
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    await waitForTwoFrames();
    const broken = [...document.fonts || []].some(font => font.family.includes("OMRS Print") && font.status === "error");
    if (broken) throw new Error("内嵌字体无法加载，请重新下载导出文件。");
    // 中文和数学字体都稳定后，以当前栏的真实尺寸再测量。
    run();
    ready = true;
    const printButton = document.getElementById("btnPrint");
    if (printButton) printButton.disabled = false;
  }

  document.addEventListener("DOMContentLoaded", () => {
    const p = document.getElementById("btnPrint");
    if (p) {
      p.disabled = true;
      p.onclick = () => window.print();
    }
    const d = document.getElementById("btnDebug"); if (d) d.onchange = e => document.body.classList.toggle("debug", e.target.checked);
    initialRun().catch(failed);
  });
})();
