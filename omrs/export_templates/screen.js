/* OMRS 屏幕版 —— 全屏卡片复习 App（移动优先）。
 * 功能：单卡全屏阅读 → 显示答案 → 判对错 + 打分 → 翻到下一题；
 *       滑动/方向键翻题；底部进度抽屉（总览统计 + 学科分解 + 跳转网格）；
 *       全部判定与当前位置存入 localStorage，刷新不丢；可一键重置。
 * 数据形状见 exporting.py：{meta, questions:[{idx,uid,subject,category,difficulty,tags,blocks,notes}], answers:[{uid,blocks}]}。
 */
(function () {
  "use strict";
  const D = window.OMRS_DATA || { meta: {}, questions: [], answers: [] };
  const QS = D.questions || [];
  const ansMap = {}; (D.answers || []).forEach(a => ansMap[a.uid] = a);
  const N = QS.length;

  /* ---------- 持久化 key：session + 题目指纹，换一份导出件互不串档 ---------- */
  function fingerprint() {
    let h = 0; const s = (D.meta && D.meta.sub || "") + "|" + QS.map(q => q.uid).join(",");
    for (let i = 0; i < s.length; i++) { h = (h * 31 + s.charCodeAt(i)) | 0; }
    return "omrs_review_" + (h >>> 0).toString(36);
  }
  const STORE_KEY = fingerprint();
  let canPersist = true;
  try { const k = "__omrs_test__"; localStorage.setItem(k, "1"); localStorage.removeItem(k); }
  catch (e) { canPersist = false; }

  /* 状态：每题 {revealed, verdict:'right'|'wrong'|null, score:0-10|null} + cur 指针 */
  let state = { cur: 0, items: {} };
  function blankItem() { return { revealed: false, verdict: null, score: null }; }
  function itemOf(i) { const u = QS[i].uid; return state.items[u] || (state.items[u] = blankItem()); }

  function load() {
    if (!canPersist) return;
    try {
      const raw = localStorage.getItem(STORE_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw);
      if (saved && saved.items) {
        state.items = saved.items;
        state.cur = Math.min(Math.max(saved.cur | 0, 0), Math.max(N - 1, 0));
      }
    } catch (e) { /* 损坏存档：忽略，从头开始 */ }
  }
  let saveTimer = null;
  function save() {
    if (!canPersist) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); flashSaved(); }
      catch (e) { canPersist = false; }
    }, 150);
  }

  /* ---------- 小工具 ---------- */
  function el(t, c, x) { const e = document.createElement(t); if (c) e.className = c; if (x != null) e.textContent = x; return e; }
  function renderMath(node, latex, display) {
    if (window.katex && typeof window.katex.render === "function") {
      try {
        window.katex.render(latex, node, { displayMode: !!display, throwOnError: false, strict: "ignore", trust: false, output: "html" });
        return;
      } catch (e) { /* fallback below */ }
    }
    node.textContent = latex;
  }
  function mathText(node, text) {
    String(text == null ? "" : text).split(/(\$\$[\s\S]+?\$\$|\$[^$\n]+\$)/).forEach(p => {
      if (!p) return;
      const disp = p.startsWith("$$") && p.endsWith("$$"), inl = !disp && p.startsWith("$") && p.endsWith("$");
      if (disp || inl) {
        const s = el("span", disp ? "math display" : "math");
        renderMath(s, disp ? p.slice(2, -2) : p.slice(1, -1), disp);
        node.appendChild(s);
      }
      else node.appendChild(document.createTextNode(p));
    });
  }
  function renderBlocks(container, blocks) {
    (blocks || []).forEach(b => {
      if (b.t === "img") { const im = el("img"); im.src = b.img.src; im.loading = "lazy"; im.alt = ""; container.appendChild(im); }
      else { const p = el("p"); mathText(p, b.text); container.appendChild(p); }
    });
  }

  /* ====================================================================
   *  卡片构建
   * ==================================================================== */
  function buildCard(q, i) {
    const slide = el("div", "slide"); slide.dataset.i = i;
    const card = el("div", "card");

    /* 题头 */
    const head = el("div", "qhead");
    const r1 = el("div", "row1");
    const dot = el("span", "state-dot"); dot.dataset.dot = i;
    r1.appendChild(dot);
    r1.appendChild(el("span", "no", "第 " + q.idx + " 题"));
    if (q.uid) r1.appendChild(el("span", "uid", q.uid));
    if (q.difficulty != null && q.difficulty !== "") r1.appendChild(el("span", "diff", "难度 " + q.difficulty + "/10"));
    head.appendChild(r1);

    const meta = el("div", "meta");
    if (q.subject) meta.appendChild(el("span", null, "科目 " + q.subject));
    if (q.subject && q.category) meta.appendChild(el("span", "sep", "·"));
    if (q.category) meta.appendChild(el("span", null, "分类 " + q.category));
    head.appendChild(meta);

    if (q.tags) {
      const tw = el("div", "tags");
      q.tags.split("·").map(s => s.trim()).filter(Boolean).forEach(t => tw.appendChild(el("span", "tag", t)));
      head.appendChild(tw);
    }
    card.appendChild(head);

    /* 题面 */
    const body = el("div", "qbody"); renderBlocks(body, q.blocks); card.appendChild(body);

    /* 错因 / 关联（题面给出即显示——这是复习提示，不算"答案"） */
    if (q.notes && q.notes["错因"]) { const n = el("div", "note"); n.innerHTML = "<b>错因 </b>"; mathText(n, q.notes["错因"]); card.appendChild(n); }
    if (q.notes && q.notes["关联"]) { const n = el("div", "note"); n.innerHTML = "<b>关联 </b>"; mathText(n, q.notes["关联"]); card.appendChild(n); }

    /* 答案区 */
    const sec = el("div", "ans-sec");
    const reveal = el("button", "reveal");
    reveal.innerHTML = '<span>👁</span><span class="rt">显示答案</span>';
    const ans = el("div", "ans");
    ans.appendChild(el("div", "lbl", "答案 / 解析"));
    const a = ansMap[q.uid];
    if (!a || !a.blocks || !a.blocks.length) ans.appendChild(el("div", "empty", "（本题未附答案——按你的理解自评即可）"));
    else renderBlocks(ans, a.blocks);

    /* 评分区 */
    const grade = el("div", "grade locked");
    grade.appendChild(el("div", "hint", "看完答案后，判定对错并给自己打分"));
    const verdict = el("div", "verdict");
    const bRight = el("button", "right"); bRight.innerHTML = '<span class="ic">✓</span><span>答对</span>';
    const bWrong = el("button", "wrong"); bWrong.innerHTML = '<span class="ic">✕</span><span>答错</span>';
    verdict.appendChild(bRight); verdict.appendChild(bWrong);
    grade.appendChild(verdict);

    const sbox = el("div", "score-box");
    const top = el("div", "top");
    top.appendChild(el("span", "t", "自评分数"));
    const vWrap = el("span", "v"); const vNum = el("span", null, "—"); const vMax = el("small", null, " / 10");
    vWrap.appendChild(vNum); vWrap.appendChild(vMax); top.appendChild(vWrap);
    sbox.appendChild(top);
    const range = document.createElement("input");
    range.type = "range"; range.min = "0"; range.max = "10"; range.step = "1"; range.value = "8";
    sbox.appendChild(range);
    const quick = el("div", "quick");
    const QUICKS = [0, 4, 6, 8, 10];
    const qBtns = QUICKS.map(v => { const b = el("button", null, v); b.dataset.v = v; quick.appendChild(b); return b; });
    sbox.appendChild(quick);
    const rubric = el("div", "rubric");  // 随「对错 + 分数」更新的判定释义（取自 OMRS 熟练度算法的四象限）
    sbox.appendChild(rubric);
    grade.appendChild(sbox);
    sec.appendChild(reveal); sec.appendChild(ans); sec.appendChild(grade);
    card.appendChild(sec);
    slide.appendChild(card);

    /* ---- 交互绑定 ---- */
    const it = itemOf(i);

    function paintScore() {
      const v = it.score;
      vNum.textContent = v == null ? "—" : v;
      if (v != null) range.value = v;
      qBtns.forEach(b => b.classList.toggle("on", it.score != null && +b.dataset.v === it.score));
      paintRubric();
    }
    // 判定释义：对应 OMRS 熟练度算法的四象限（高分阈值 = 7 分）
    function paintRubric() {
      const HIGH = 7;
      if (!it.verdict) { rubric.className = "rubric"; rubric.textContent = ""; return; }
      const s = it.score == null ? null : it.score;
      let cls, txt;
      if (it.verdict === "right") {
        if (s == null) { rubric.className = "rubric"; rubric.textContent = "打个分：完全掌握给高分，靠印象/猜中给低分"; return; }
        if (s >= HIGH) { cls = "ok"; txt = "高分待确认 · 思路与过程清晰，再答对一次即「已击杀」"; }
        else { cls = "warm"; txt = "磨合中 · 答案对但还不熟，理解或过程仍有水分"; }
      } else {
        if (s == null) { rubric.className = "rubric"; rubric.textContent = "打个分：只差一步给高分，毫无头绪给低分"; return; }
        if (s >= HIGH) { cls = "warm"; txt = "粗心 / 陷阱 · 思路基本对，栽在细节或计算上"; }
        else { cls = "bad"; txt = "真不会 · 关键步骤没掌握，需要重点重练"; }
      }
      rubric.className = "rubric " + cls; rubric.textContent = txt;
    }
    function paintVerdict() {
      bRight.classList.toggle("on", it.verdict === "right");
      bWrong.classList.toggle("on", it.verdict === "wrong");
    }
    function openAns(animate) {
      it.revealed = true;
      reveal.querySelector(".rt").textContent = "答案已显示";
      reveal.style.display = "none";
      ans.classList.add("open");
      grade.classList.remove("locked");
    }
    if (it.revealed) openAns(false);
    paintVerdict(); paintScore();

    reveal.onclick = () => { openAns(true); save(); };
    bRight.onclick = () => {
      it.verdict = it.verdict === "right" ? null : "right";
      if (it.verdict === "right" && it.score == null) { it.score = 10; }   // 答对默认满分，可下调
      paintVerdict(); paintScore(); syncMeta(i); refreshNextBtn(); save();
    };
    bWrong.onclick = () => {
      it.verdict = it.verdict === "wrong" ? null : "wrong";
      if (it.verdict === "wrong" && it.score == null) { it.score = 4; }    // 答错默认偏低，可上调
      paintVerdict(); paintScore(); syncMeta(i); refreshNextBtn(); save();
    };
    range.oninput = () => { it.score = +range.value; vNum.textContent = it.score; qBtns.forEach(b => b.classList.toggle("on", +b.dataset.v === it.score)); paintRubric(); };
    range.onchange = () => { syncMeta(i); save(); };
    qBtns.forEach(b => b.onclick = () => { it.score = +b.dataset.v; paintScore(); syncMeta(i); save(); });

    return slide;
  }

  /* ====================================================================
   *  舞台 / 导航
   * ==================================================================== */
  const track = document.getElementById("track");

  function goto(i, animate) {
    i = Math.min(Math.max(i, 0), N - 1);
    state.cur = i;
    if (!animate) track.classList.add("no-anim");
    track.style.transform = "translateX(" + (-i * 100) + "%)";
    if (!animate) requestAnimationFrame(() => track.classList.remove("no-anim"));
    const sl = track.children[i]; if (sl) sl.scrollTop = 0;
    refreshNav();
    save();
  }

  function refreshNextBtn() {
    const nextBtn = document.getElementById("nextBtn");
    const last = state.cur >= N - 1;
    const allDone = answeredCount() >= N;
    if (last) {
      nextBtn.classList.toggle("done", allDone);
      nextBtn.innerHTML = allDone ? '<span>全部完成</span><span>✓</span>' : '<span>查看作答情况</span><span>→</span>';
    } else {
      nextBtn.classList.remove("done");
      nextBtn.innerHTML = '<span>下一题</span><span>→</span>';
    }
  }
  function refreshNav() {
    document.getElementById("prevBtn").disabled = state.cur <= 0;
    document.getElementById("nextNavBtn").disabled = state.cur >= N - 1;
    document.getElementById("navMid").innerHTML = "<b>" + (state.cur + 1) + "</b> / " + N;
    refreshNextBtn();
    refreshRing();
  }

  /* ---------- 进度环 ---------- */
  function answeredCount() { return QS.reduce((n, q, i) => n + (itemOf(i).verdict ? 1 : 0), 0); }
  function refreshRing() {
    const done = answeredCount(), pct = N ? Math.round(done / N * 100) : 0;
    const C = 2 * Math.PI * 16;
    const fill = document.querySelector(".ring .fill");
    if (fill) { fill.style.strokeDasharray = C; fill.style.strokeDashoffset = C * (1 - done / Math.max(N, 1)); }
    const pl = document.querySelector(".ring .pct"); if (pl) pl.textContent = pct + "%";
  }

  /* ---------- 同步题头状态点 + 网格 ---------- */
  function syncMeta(i) {
    const it = itemOf(i);
    document.querySelectorAll('[data-dot="' + i + '"]').forEach(d => {
      d.classList.toggle("ok", it.verdict === "right");
      d.classList.toggle("no", it.verdict === "wrong");
    });
    const cell = document.querySelector('.cell[data-j="' + i + '"]');
    if (cell) paintCell(cell, i);
    refreshRing();
  }

  /* ====================================================================
   *  进度抽屉
   * ==================================================================== */
  function paintCell(cell, i) {
    const it = itemOf(i);
    cell.classList.toggle("ok", it.verdict === "right");
    cell.classList.toggle("no", it.verdict === "wrong");
    cell.classList.toggle("cur", i === state.cur);
    const sc = cell.querySelector(".sc");
    if (sc) sc.textContent = it.score != null ? it.score : "";
  }
  function buildGrid() {
    const grid = document.getElementById("grid"); grid.innerHTML = "";
    QS.forEach((q, i) => {
      const cell = el("div", "cell"); cell.dataset.j = i;
      cell.appendChild(el("span", null, String(i + 1)));
      cell.appendChild(el("span", "sc"));
      paintCell(cell, i);
      cell.onclick = () => { closeSheet(); goto(i, false); };
      grid.appendChild(cell);
    });
  }
  function refreshStats() {
    const done = answeredCount();
    const right = QS.reduce((n, q, i) => n + (itemOf(i).verdict === "right" ? 1 : 0), 0);
    const wrong = done - right;

    document.getElementById("st-done").innerHTML = done + '<small> / ' + N + '</small>';
    document.getElementById("st-right").textContent = right;
    document.getElementById("st-wrong").textContent = wrong;

    /* 学科分解 */
    const bySub = {};
    QS.forEach((q, i) => {
      const s = q.subject || "未分类"; const it = itemOf(i);
      const b = bySub[s] || (bySub[s] = { total: 0, ok: 0, no: 0 });
      b.total++; if (it.verdict === "right") b.ok++; else if (it.verdict === "wrong") b.no++;
    });
    const wrap = document.getElementById("subjBreak"); wrap.innerHTML = "";
    const subjects = Object.keys(bySub);
    if (subjects.length > 1) {
      wrap.appendChild(el("div", "sb-ttl", "各科作答"));
      subjects.forEach(s => {
        const b = bySub[s];
        const row = el("div", "sb-row");
        row.appendChild(el("div", "nm", s));
        const trk = el("div", "trk");
        const okBar = el("div", "ok"); okBar.style.width = (b.ok / b.total * 100) + "%";
        const noBar = el("div", "no"); noBar.style.width = (b.no / b.total * 100) + "%";
        trk.appendChild(okBar); trk.appendChild(noBar); row.appendChild(trk);
        row.appendChild(el("div", "ct", (b.ok + b.no) + "/" + b.total));
        wrap.appendChild(row);
      });
    }
  }
  function openSheet() {
    refreshStats(); buildGrid();
    document.querySelectorAll(".cell").forEach((c, i) => paintCell(c, i));
    document.getElementById("sheet").classList.add("open");
  }
  function closeSheet() { document.getElementById("sheet").classList.remove("open"); }

  /* ---------- 重置 ---------- */
  function resetAll() {
    if (!confirm("确定清空全部作答记录？此操作无法撤销。")) return;
    state = { cur: 0, items: {} };
    if (canPersist) { try { localStorage.removeItem(STORE_KEY); } catch (e) {} }
    rebuild(); closeSheet(); toast("已清空作答记录");
  }

  /* ---------- 作答 JSON（对接主程序「提交反馈 → 导入作答 JSON」） ---------- */
  function sessionId() {
    if (D.meta && D.meta.session_id) return D.meta.session_id;
    const m = ((D.meta && D.meta.sub) || "").match(/Session:\s*(\S+)/);   // 旧导出件兜底
    return m ? m[1] : "";
  }
  function buildAnswersJson() {
    const items = [];
    QS.forEach((q, i) => {
      const it = itemOf(i);
      if (it.verdict !== "right" && it.verdict !== "wrong") return;       // 只导出已判定的题
      items.push({
        uid: q.uid,
        is_correct: it.verdict === "right",
        sub_score: it.score == null ? (it.verdict === "right" ? 10 : 4) : it.score,
      });
    });
    const d = new Date(), p = n => String(n).padStart(2, "0");
    return {
      type: "omrs-feedback", version: 1,
      session_id: sessionId(),
      exported_at: d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes()),
      total: N, graded: items.length, items: items,
    };
  }
  function copyTextLegacy(text) {
    try {
      const ta = document.createElement("textarea");
      ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.focus(); ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch (e) { return false; }
  }
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(() => true).catch(() => copyTextLegacy(text));
    }
    return Promise.resolve(copyTextLegacy(text));
  }
  function downloadJson(text) {
    try {
      const blob = new Blob([text], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "OMRS-作答-" + (sessionId() || "export") + ".json";
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1200);
      return true;
    } catch (e) { return false; }
  }
  function copyAnswersJson() {
    const payload = buildAnswersJson();
    if (!payload.graded) { toast("还没有已判定的题目，先判几道再复制"); return; }
    const text = JSON.stringify(payload);
    copyText(text).then(ok => {
      if (ok) { toast("已复制 " + payload.graded + " 条作答，去主程序「提交反馈」页导入"); return; }
      // 剪贴板不可用（个别环境）→ 退化为下载 .json 文件，导入页同样可粘贴其内容
      toast(downloadJson(text) ? "剪贴板不可用，已改为下载 JSON 文件" : "复制失败，请尝试在其他浏览器打开");
    });
  }

  /* ---------- 滑动手势 ---------- */
  function bindSwipe() {
    const stage = document.getElementById("stage");
    let x0 = null, y0 = null, locked = null;
    stage.addEventListener("touchstart", e => {
      if (e.touches.length !== 1) return;
      x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; locked = null;
    }, { passive: true });
    stage.addEventListener("touchmove", e => {
      if (x0 == null) return;
      const dx = e.touches[0].clientX - x0, dy = e.touches[0].clientY - y0;
      if (locked == null && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) locked = Math.abs(dx) > Math.abs(dy) ? "x" : "y";
    }, { passive: true });
    stage.addEventListener("touchend", e => {
      if (x0 == null) return;
      const dx = e.changedTouches[0].clientX - x0;
      if (locked === "x" && Math.abs(dx) > 55) { if (dx < 0) goto(state.cur + 1, true); else goto(state.cur - 1, true); }
      x0 = y0 = null; locked = null;
    }, { passive: true });
  }

  /* ---------- Toast / 存档提示 ---------- */
  let toastTimer = null;
  function toast(msg) {
    const t = document.getElementById("toast"); t.textContent = msg; t.classList.add("show");
    clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), 1600);
  }
  let savedTimer = null;
  function flashSaved() {
    const s = document.getElementById("savedTag"); if (!s) return;
    s.innerHTML = '已自动保存 · <b>刷新不丢失</b>';
    clearTimeout(savedTimer); savedTimer = setTimeout(() => { s.textContent = "进度自动保存在本设备"; }, 1400);
  }

  /* ====================================================================
   *  装配
   * ==================================================================== */
  function rebuild() {
    track.innerHTML = "";
    QS.forEach((q, i) => track.appendChild(buildCard(q, i)));
    goto(state.cur, false);
  }

  function build() {
    // 顶栏标题
    const sub = (D.meta && D.meta.sub) || "";
    const mSession = sub.match(/Session:\s*(\S+)/);
    document.getElementById("barSub").textContent = mSession ? mSession[1] : (N + " 道题");

    if (N === 0) {
      document.getElementById("stage").innerHTML = '<div style="margin:auto;color:var(--fg3);font-size:.9rem">没有可复习的题目</div>';
      return;
    }

    rebuild();

    // 导航按钮
    document.getElementById("prevBtn").onclick = () => goto(state.cur - 1, true);
    document.getElementById("nextNavBtn").onclick = () => goto(state.cur + 1, true);
    document.getElementById("nextBtn").onclick = () => {
      if (state.cur >= N - 1) openSheet(); else goto(state.cur + 1, true);
    };
    document.getElementById("progBtn").onclick = openSheet;
    document.querySelector(".ring").onclick = openSheet;

    // 抽屉
    document.querySelector("#sheet .scrim").onclick = closeSheet;
    document.getElementById("sheetClose").onclick = closeSheet;
    document.getElementById("resetBtn").onclick = resetAll;
    const cj = document.getElementById("copyJsonBtn");
    if (cj) cj.onclick = copyAnswersJson;
    document.getElementById("jumpFirstUngraded").onclick = () => {
      const idx = QS.findIndex((q, i) => !itemOf(i).verdict);
      closeSheet(); goto(idx < 0 ? 0 : idx, false);
    };

    // 键盘（桌面）
    document.addEventListener("keydown", e => {
      if (document.getElementById("lightbox").classList.contains("show")) { if (e.key === "Escape") lb.classList.remove("show"); return; }
      if (document.getElementById("sheet").classList.contains("open")) { if (e.key === "Escape") closeSheet(); return; }
      if (e.key === "ArrowRight") goto(state.cur + 1, true);
      else if (e.key === "ArrowLeft") goto(state.cur - 1, true);
      else if (e.key === "Escape") openSheet();
    });

    bindSwipe();

    // 灯箱
    const lb = document.getElementById("lightbox"), lbimg = lb.querySelector("img");
    track.addEventListener("click", e => { if (e.target.tagName === "IMG") { lbimg.src = e.target.src; lb.classList.add("show"); } });
    lb.addEventListener("click", () => lb.classList.remove("show"));

    if (!canPersist) {
      const s = document.getElementById("savedTag");
      if (s) { s.innerHTML = '⚠ 此环境无法保存进度（刷新将清空）'; s.style.color = "var(--yellow)"; }
    }
  }

  load();
  document.addEventListener("DOMContentLoaded", build);
})();
