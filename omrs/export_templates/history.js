/* 自包含导出中的微型历史图。SVG 高度固定，数字、符号与图形都随 HTML 离线保存。 */
(function () {
  "use strict";
  const ns = "http://www.w3.org/2000/svg";
  function svg(tag, attrs, text) {
    const node = document.createElementNS(ns, tag);
    Object.entries(attrs || {}).forEach(([key, value]) => node.setAttribute(key, String(value)));
    if (text != null) node.textContent = text;
    return node;
  }
  window.OMRS_HISTORY = function (records) {
    if (!Array.isArray(records) || !records.length) return null;
    const options = window.OMRS_DATA?.meta?.history || {};
    const root = document.createElement("figure");
    root.className = "review-history";
    const caption = document.createElement("figcaption");
    caption.textContent = "近 " + records.length + " 次";
    const direction = document.createElement("small"); direction.textContent = "新 → 旧"; caption.appendChild(direction);
    root.appendChild(caption);
    const width = Math.max(108, records.length * 15), base = 34;
    const graph = svg("svg", { viewBox: "0 0 " + width + " 51", width: width, height: 51, role: "img", "aria-label": records.map(r => r.date + " " + (r.correct ? "对" : "错") + " " + r.score + "分").join("；") });
    graph.appendChild(svg("line", { x1: 0, x2: width, y1: base, y2: base, class: "history-baseline" }));
    // 各记录等距排列；每题都使用 0–10 的固定量尺，零分保留细条。
    records.forEach((record, index) => {
      const step = width / records.length, x = step * (index + .5), h = Math.max(1.2, Math.max(0, Math.min(10, +record.score || 0)) * 2.5);
      const g = svg("g", { class: record.correct ? "history-right" : "history-wrong", "data-score": record.score, "data-date": record.date, "data-correct": record.correct ? "1" : "0" });
      g.appendChild(svg("title", {}, record.date + (record.time ? " " + record.time : "") + " · " + record.score + " 分 · " + (record.correct ? "答对" : "答错")));
      g.appendChild(svg("rect", { x: x - 3.5, y: base - h, width: 7, height: h, rx: 1 }));
      if (options.scores !== false) g.appendChild(svg("text", { x, y: base - h - 2.5, class: "history-score", "text-anchor": "middle" }, record.score));
      g.appendChild(svg("text", { x, y: 42, class: "history-verdict", "text-anchor": "middle" }, record.correct ? "✓" : "×"));
      graph.appendChild(g);
    });
    if (options.dates !== false) {
      const newest = records[0].date, oldest = records[records.length - 1].date;
      const short = date => newest.slice(0, 4) === oldest.slice(0, 4) ? date.slice(5).replace("-", "/") : date.replaceAll("-", "/");
      graph.appendChild(svg("text", { x: 0, y: 51, class: "history-date" }, short(newest)));
      if (records.length > 1) graph.appendChild(svg("text", { x: width, y: 51, class: "history-date", "text-anchor": "end" }, short(oldest)));
    }
    root.appendChild(graph);
    return root;
  };
})();
