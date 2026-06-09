/* OMRS 屏幕版逻辑：阅读卡片 + 答案折叠(主动回忆) + 主题筛选 + 搜索 + 图片灯箱 */
(function () {
  "use strict";
  const D = window.OMRS_DATA || { questions: [], answers: [] };
  const ansMap = {}; (D.answers || []).forEach(a => ansMap[a.uid] = a);
  let answersGlobalOpen = false;

  function el(t, c, x) { const e = document.createElement(t); if (c) e.className = c; if (x != null) e.textContent = x; return e; }
  function mathText(e, text) {
    String(text).split(/(\$\$[^$]+\$\$|\$[^$\n]+\$)/).forEach(p => {
      if (!p) return;
      const disp = p.startsWith("$$") && p.endsWith("$$"), inl = !disp && p.startsWith("$") && p.endsWith("$");
      if (disp || inl) e.appendChild(el("span", "math", disp ? p.slice(2, -2) : p.slice(1, -1)));
      else e.appendChild(document.createTextNode(p));
    });
  }
  function renderBlocks(container, blocks) {
    (blocks || []).forEach(b => {
      if (b.t === "img") { const im = el("img"); im.src = b.img.src; im.loading = "lazy"; container.appendChild(im); }
      else { const p = el("p"); mathText(p, b.text); container.appendChild(p); }
    });
  }

  function card(q) {
    const c = el("div", "qcard");
    c.dataset.subject = q.subject || "";
    c.dataset.text = ((q.uid || "") + " " + (q.category || "") + " " + (q.tags || "") + " " +
      (q.blocks || []).filter(b => b.t !== "img").map(b => b.text).join(" ")).toLowerCase();

    const head = el("div", "qhead");
    const no = el("span", "no", "第 " + q.idx + " 题"); head.appendChild(no);
    head.appendChild(el("span", "uid", "[" + q.uid + "]"));
    head.appendChild(el("span", "diff", "难度 " + q.difficulty + "/10"));
    c.appendChild(head);
    c.appendChild(el("div", "qmeta", "科目: " + q.subject + "　分类: " + q.category));
    if (q.tags) c.appendChild(el("div", "qtags", "标签: " + q.tags));

    const body = el("div", "qbody"); renderBlocks(body, q.blocks); c.appendChild(body);
    if (q.notes && q.notes["错因"]) { const n = el("div", "note"); n.innerHTML = "<b>错因：</b>"; mathText(n, q.notes["错因"]); c.appendChild(n); }
    if (q.notes && q.notes["关联"]) { const n = el("div", "note"); n.innerHTML = "<b>关联：</b>"; mathText(n, q.notes["关联"]); c.appendChild(n); }

    const a = ansMap[q.uid];
    if (a) {
      const wrap = el("div", "ans-wrap");
      const btn = el("button", "ans-toggle", "👁 显示答案");
      const ab = el("div", "ans-body hidden");
      if (!a.blocks.length) ab.appendChild(el("div", "ans-empty", "（暂无答案）"));
      else renderBlocks(ab, a.blocks);
      btn.onclick = () => { const open = ab.classList.toggle("hidden") === false; btn.textContent = open ? "🙈 收起答案" : "👁 显示答案"; };
      wrap._sync = (open) => { ab.classList.toggle("hidden", !open); btn.textContent = open ? "🙈 收起答案" : "👁 显示答案"; };
      wrap.appendChild(btn); wrap.appendChild(ab); c.appendChild(wrap);
    }
    return c;
  }

  function applyFilter() {
    const q = (document.getElementById("search").value || "").trim().toLowerCase();
    const subj = window.__subj || "全部";
    let shown = 0;
    document.querySelectorAll(".qcard").forEach(c => {
      const okS = subj === "全部" || c.dataset.subject === subj;
      const okQ = !q || c.dataset.text.indexOf(q) >= 0;
      const ok = okS && okQ; c.classList.toggle("hidden", !ok); if (ok) shown++;
    });
    document.getElementById("empty").classList.toggle("hidden", shown > 0);
  }

  function build() {
    const list = document.getElementById("list");
    (D.questions || []).forEach(q => list.appendChild(card(q)));

    // 主题筛选 chips
    const subjects = Array.from(new Set((D.questions || []).map(q => q.subject).filter(Boolean)));
    const fwrap = document.getElementById("filters");
    window.__subj = "全部";
    ["全部"].concat(subjects).forEach((s, i) => {
      const chip = el("div", "chip" + (i === 0 ? " on" : ""), s);
      chip.onclick = () => { window.__subj = s; document.querySelectorAll(".chip").forEach(x => x.classList.remove("on")); chip.classList.add("on"); applyFilter(); };
      fwrap.appendChild(chip);
    });
    if (subjects.length < 2) fwrap.style.display = "none";

    document.getElementById("search").addEventListener("input", applyFilter);
    const tg = document.getElementById("btnAns");
    tg.onclick = () => {
      answersGlobalOpen = !answersGlobalOpen;
      tg.classList.toggle("on", answersGlobalOpen);
      tg.textContent = answersGlobalOpen ? "隐藏全部答案" : "显示全部答案";
      document.querySelectorAll(".ans-wrap").forEach(w => w._sync && w._sync(answersGlobalOpen));
    };
    document.getElementById("count").textContent = (D.questions || []).length + " 题";

    // 图片灯箱
    const lb = document.getElementById("lightbox"), lbimg = lb.querySelector("img");
    list.addEventListener("click", e => { if (e.target.tagName === "IMG") { lbimg.src = e.target.src; lb.classList.add("show"); } });
    lb.addEventListener("click", () => lb.classList.remove("show"));
    document.addEventListener("keydown", e => { if (e.key === "Escape") lb.classList.remove("show"); });
  }
  document.addEventListener("DOMContentLoaded", build);
})();
