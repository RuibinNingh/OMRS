(async function () {
  "use strict";

  const data = window.OMRS_DATA || {};
  const mount = document.getElementById("stage");
  if (!mount) return;

  const MIN_SLICE = 28;
  const esc = value => String(value ?? "").replace(/[&<>"]/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;",
  }[ch]));

  function labelHtml(labels) {
    return (labels || []).map(raw => {
      const item = typeof raw === "string" ? { name: raw, color: "#64748b" } : raw;
      const color = String(item.color || "#64748b").replace(/^#/, "");
      const hex = /^[0-9a-f]{6}$/i.test(color) ? color : "64748b";
      const rgb = [0, 2, 4].map(index => parseInt(hex.slice(index, index + 2), 16)).join(",");
      return `<span class="lbl" style="--lrgb:${rgb};--link:${esc(item.ink || item.color || "#475569")}">${esc(item.name)}</span>`;
    }).join("");
  }

  function makePage(number, ratio, binding, bindingMarks) {
    const page = document.createElement("section");
    page.className = "bd-page";
    page.dataset.pageNumber = String(number);
    page.style.setProperty("--binding", `${Number(binding) || 83.149}px`);
    page.style.setProperty("--note-ratio", `${Number(ratio) || .42}`);
    const inner = document.createElement("div");
    inner.className = "bd-inner";
    const head = document.createElement("div");
    head.className = "bd-head";
    head.textContent = "错题集";
    const left = document.createElement("main");
    left.className = "bd-left";
    inner.append(head, left);
    const footer = document.createElement("div");
    footer.className = "bd-footer";
    footer.textContent = String(number);
    page.append(inner, footer);
    mount.appendChild(page);
    // CSS arithmetic with multiplication is not consistently implemented by
    // print browsers.  Resolve the left column against the mounted A4
    // geometry so the browser measures the same width it will print.
    const innerWidth = inner.getBoundingClientRect().width || inner.clientWidth;
    const noteRatio = Math.max(0, Math.min(1, Number(ratio) || .42));
    left.style.width = `${Math.max(0, (innerWidth - 24) * (1 - noteRatio))}px`;
    if (bindingMarks === "3hole" || bindingMarks === "26hole") {
      const marks = document.createElement("div");
      marks.className = `bd-binding-marks ${bindingMarks}`;
      marks.setAttribute("aria-hidden", "true");
      marks.style.left = `${Math.max(4, (Number(binding) || 83.149) / 2 - 4)}px`;
      marks.style.top = `${inner.offsetTop}px`;
      marks.style.height = `${inner.getBoundingClientRect().height || inner.clientHeight}px`;
      const count = bindingMarks === "3hole" ? 3 : 26;
      for (let index = 0; index < count; index += 1) {
        const mark = document.createElement("i");
        mark.className = "bd-binding-mark";
        const ratio = count === 1 ? .5 : index / (count - 1);
        mark.style.top = `${ratio * 100}%`;
        marks.appendChild(mark);
      }
      page.appendChild(marks);
    }
    return { number, page, inner, left };
  }

  function leftFits(left) {
    return left.scrollHeight <= left.clientHeight + 0.5;
  }

  function innerFits(inner) {
    return inner.scrollHeight <= inner.clientHeight + 0.5;
  }

  function addIfFits(container, node, fits = leftFits) {
    container.appendChild(node);
    if (fits(container)) return true;
    container.removeChild(node);
    return false;
  }

  function addBodyIfFits(container, body, node, fits = leftFits) {
    body.appendChild(node);
    if (fits(container)) return true;
    body.removeChild(node);
    return false;
  }

  function questionShell(question, continuation) {
    const article = document.createElement("article");
    article.className = "bd-question";
    article.style.setProperty("--gap", "0px");
    article.style.setProperty("--extra-gap", "0px");
    const head = document.createElement("div");
    head.className = "bd-qhead";
    head.innerHTML = `<span class="bd-no">${esc(continuation ? `${question.index}（续）` : question.index)}</span><span class="bd-uid">${esc(question.uid)}</span><span class="bd-labels">${labelHtml(question.labels)}</span>`;
    const meta = document.createElement("div");
    meta.className = "bd-meta";
    meta.textContent = question.meta || "";
    const body = document.createElement("div");
    body.className = "bd-text";
    article.append(head);
    if (question.meta) article.append(meta);
    article.append(body);
    return { article, body };
  }

  function answerShell(answer, continuation) {
    const row = document.createElement("div");
    row.className = "bd-answer-row";
    const title = document.createElement("div");
    title.innerHTML = `<b>${esc(answer.index)} ${esc(answer.uid)}${continuation ? "（续）" : ""}</b>`;
    const body = document.createElement("div");
    body.className = "bd-text";
    row.append(title, body);
    return { row, body };
  }

  function htmlNodes(html) {
    const holder = document.createElement("div");
    holder.innerHTML = html || "<p>（无题目内容）</p>";
    return [...holder.childNodes].filter(node => (
      node.nodeType === 1 || String(node.textContent || "").trim()
    ));
  }

  function textParagraph(text) {
    const node = document.createElement("p");
    node.textContent = text;
    return node;
  }

  function nextTextShell(question) {
    current = nextPage();
    return startQuestion(question, true);
  }

  function placeText(shell, text, question) {
    let rest = String(text || "");
    while (rest) {
      const whole = textParagraph(rest);
      if (addBodyIfFits(current.left, shell.body, whole)) return shell;

      let lo = 1;
      let hi = rest.length;
      let best = 0;
      while (lo <= hi) {
        const mid = Math.floor((lo + hi) / 2);
        const candidate = textParagraph(rest.slice(0, mid));
        shell.body.appendChild(candidate);
        if (leftFits(current.left)) {
          best = mid;
          shell.body.removeChild(candidate);
          lo = mid + 1;
        } else {
          shell.body.removeChild(candidate);
          hi = mid - 1;
        }
      }
      if (!best) {
        shell = nextTextShell(question);
        continue;
      }
      shell.body.appendChild(textParagraph(rest.slice(0, best)));
      rest = rest.slice(best);
      shell = nextTextShell(question);
    }
    return shell;
  }

  function imageSize(image, width) {
    const naturalWidth = image.naturalWidth || width;
    const naturalHeight = image.naturalHeight || width;
    const displayWidth = Math.min(width, naturalWidth);
    return {
      naturalWidth,
      naturalHeight,
      displayWidth,
      scale: displayWidth / naturalWidth,
      height: naturalHeight * displayWidth / naturalWidth,
    };
  }

  function imageSlice(image, size, y0, y1) {
    const wrap = document.createElement("div");
    wrap.className = "bd-img-slice";
    wrap.style.width = `${size.displayWidth}px`;
    wrap.style.height = `${Math.max(1, (y1 - y0) * size.scale)}px`;
    const copy = image.cloneNode(false);
    copy.style.width = `${size.displayWidth}px`;
    copy.style.marginTop = `${-y0 * size.scale}px`;
    wrap.appendChild(copy);
    return wrap;
  }

  function waitForImage(image) {
    if (image.complete) return Promise.resolve(image);
    return new Promise(resolve => {
      const done = () => resolve(image);
      image.addEventListener("load", done, { once: true });
      image.addEventListener("error", done, { once: true });
    });
  }

  async function waitForImages() {
    const images = [...mount.querySelectorAll("img")];
    await Promise.all(images.map(image => image.complete
      ? Promise.resolve()
      : new Promise(resolve => {
        image.addEventListener("load", resolve, { once: true });
        image.addEventListener("error", resolve, { once: true });
      })));
  }

  async function preloadSources() {
    const sources = new Set();
    [...questions, ...(data.answers || [])].forEach(item => {
      htmlNodes(item.html || item.text || "").forEach(node => {
        if (node.tagName === "IMG" && node.src) sources.add(node.src);
      });
    });
    await Promise.all([...sources].map(src => new Promise(resolve => {
      const image = new Image();
      image.addEventListener("load", resolve, { once: true });
      image.addEventListener("error", resolve, { once: true });
      image.src = src;
    })));
  }

  const questionSource = Array.isArray(data.all_questions) && data.all_questions.length
    ? data.all_questions
    : (data.pages || []).flatMap(page => page.questions || []);
  const questions = questionSource.map(question => ({
    ...question,
    index: Number(question.index || question.idx || 0),
    html: question.html || question.text || "<p>（无题目内容）</p>",
  }));
  const ratio = Number(data.note_ratio) || .42;
  const binding = Number(data.binding_px) || 83.149;
  const pages = [];
  let current = null;

  function nextPage() {
    current = makePage(pages.length + 1, ratio, binding, data.binding_marks);
    pages.push(current);
    return current;
  }

  function startQuestion(question, continuation = false) {
    if (!current) nextPage();
    let shell = questionShell(question, continuation);
    if (!addIfFits(current.left, shell.article)) {
      nextPage();
      shell = questionShell(question, continuation);
      current.left.appendChild(shell.article);
    }
    return shell;
  }

  function continueQuestion(question) {
    nextPage();
    return startQuestion(question, true);
  }

  async function placeQuestion(question) {
    let shell = startQuestion(question, false);
    for (const original of htmlNodes(question.html)) {
      const node = original.cloneNode(true);
      if (node.tagName === "IMG") {
        const image = node;
        await waitForImage(image);
        const size = imageSize(image, current.left.clientWidth);
        let y0 = 0;
        while (y0 < size.naturalHeight) {
          const remaining = current.left.clientHeight - current.left.scrollHeight;
          const restHeight = (size.naturalHeight - y0) * size.scale;
          if (restHeight <= remaining + 0.5) {
          const whole = imageSlice(image, size, y0, size.naturalHeight);
          if (!addBodyIfFits(current.left, shell.body, whole)) {
            shell = continueQuestion(question);
            if (!addBodyIfFits(current.left, shell.body, whole)) {
              // A malformed layout must not silently discard the image.
              shell.body.appendChild(whole);
            }
          }
            y0 = size.naturalHeight;
            continue;
          }
          if (remaining < MIN_SLICE) {
            shell = continueQuestion(question);
            continue;
          }
          const cut = Math.max(y0 + 1, Math.min(
            size.naturalHeight - 1,
            y0 + Math.floor(remaining / size.scale),
          ));
          const slice = imageSlice(image, size, y0, cut);
          if (!addBodyIfFits(current.left, shell.body, slice)) {
            shell = continueQuestion(question);
            if (!addBodyIfFits(current.left, shell.body, slice)) {
              shell.body.appendChild(slice);
            }
          }
          y0 = cut;
          shell = continueQuestion(question);
        }
        continue;
      }
      const text = node.tagName === "P" ? node.textContent || "" : "";
      if (node.tagName === "P" && text) {
        shell = placeText(shell, text, question);
      } else if (!addBodyIfFits(current.left, shell.body, node)) {
        shell = continueQuestion(question);
        if (!addBodyIfFits(current.left, shell.body, node)) {
          // Tables and other atomic nodes may exceed one page.  Keep them
          // visible rather than losing them when a fresh page is also tight.
          shell.body.appendChild(node);
        }
      }
    }
    const gap = document.createElement("div");
    gap.className = "bd-question-gap";
    gap.style.height = `${Math.max(0, Number(question.gap_px) || 0) + Math.max(0, Number(question.extra_gap_px) || 0)}px`;
    if (!addBodyIfFits(current.left, shell.body, gap)) {
      // The gap belongs after the previous question.  If only the gap does
      // not fit, carrying it to the top of the next page creates a misleading
      // blank strip; the next question may start at the page top instead.
      nextPage();
    }
  }

  function answerPage() {
    current = makePage(pages.length + 1, ratio, binding);
    current.left.remove();
    const answer = document.createElement("div");
    answer.className = "bd-answer";
    const title = document.createElement("h2");
    title.textContent = "答案";
    answer.appendChild(title);
    current.inner.appendChild(answer);
    current.answer = answer;
    return current;
  }

  function answerFits(answer) {
    return answer && answer.scrollHeight <= answer.clientHeight + 0.5;
  }

  function addAnswerNode(answer, shell, node) {
    if (node.tagName === "P" && node.textContent) {
      let rest = node.textContent;
      while (rest) {
        const whole = textParagraph(rest);
        if (addBodyIfFits(current.answer, shell.body, whole, answerFits)) return shell;
        let lo = 1, hi = rest.length, best = 0;
        while (lo <= hi) {
          const mid = Math.floor((lo + hi) / 2);
          const candidate = textParagraph(rest.slice(0, mid));
          shell.body.appendChild(candidate);
          if (answerFits(current.answer)) {
            best = mid;
            shell.body.removeChild(candidate);
            lo = mid + 1;
          } else {
            shell.body.removeChild(candidate);
            hi = mid - 1;
          }
        }
        if (!best) {
          answerPage();
          shell = answerShell(answer, true);
          current.answer.appendChild(shell.row);
          continue;
        }
        shell.body.appendChild(textParagraph(rest.slice(0, best)));
        rest = rest.slice(best);
        answerPage();
        shell = answerShell(answer, true);
        current.answer.appendChild(shell.row);
      }
      return shell;
    }
    if (!addBodyIfFits(current.answer, shell.body, node, answerFits)) {
      answerPage();
      shell = answerShell(answer, true);
      current.answer.appendChild(shell.row);
      if (!addBodyIfFits(current.answer, shell.body, node, answerFits)) {
        shell.body.appendChild(node);
      }
    }
    return shell;
  }

  async function placeAnswers(answers) {
    if (!answers.length) return;
    answerPage();
    for (const answer of answers) {
      let shell = answerShell(answer, false);
      current.answer.appendChild(shell.row);
      if (!answerFits(current.answer)) {
        current.answer.removeChild(shell.row);
        answerPage();
        shell = answerShell(answer, false);
        current.answer.appendChild(shell.row);
      }
      for (const original of htmlNodes(answer.html || answer.text || "<p>（无答案）</p>")) {
        const node = original.cloneNode(true);
        if (node.tagName === "IMG") await waitForImage(node);
        const nestedImages = node.querySelectorAll ? [...node.querySelectorAll("img")] : [];
        if (nestedImages.length) await Promise.all(nestedImages.map(waitForImage));
        shell = addAnswerNode(answer, shell, node);
      }
    }
  }

  await preloadSources();
  for (const question of questions) await placeQuestion(question);
  await waitForImages();
  if (document.fonts && document.fonts.ready) await document.fonts.ready;
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  if (!pages.length) nextPage();
  if (data.include_answers && Array.isArray(data.answers) && data.answers.length) {
    await placeAnswers(data.answers);
  }

  const start = Math.max(1, Number(data.page_start) || 1);
  const end = data.open_end ? Infinity : Math.max(start, Number(data.page_end) || start);
  const selected = pages.filter(page => page.number >= start && page.number <= end);
  pages.forEach(page => {
    if (!selected.includes(page)) page.page.remove();
  });
  const pageCountMeta = document.querySelector('meta[name="omrs-page-count"]');
  const totalCountMeta = document.querySelector('meta[name="omrs-total-page-count"]');
  const endMeta = document.querySelector('meta[name="omrs-page-end"]');
  if (pageCountMeta) pageCountMeta.content = String(selected.length);
  if (totalCountMeta) totalCountMeta.content = String(pages.length);
  if (endMeta) endMeta.content = String(data.open_end ? pages.length : Math.min(pages.length, end));

  const actualEnd = data.open_end ? pages.length : Math.min(pages.length, end);
  const toolbar = document.querySelector(".toolbar");
  if (toolbar) {
    const status = document.createElement("span");
    status.className = "board-export-status";
    status.textContent = selected.length
      ? `已排版 ${selected.length} 页（整板共 ${pages.length} 页）`
      : "打印范围没有可用页面";
    toolbar.appendChild(status);
    const confirm = document.createElement("button");
    confirm.type = "button";
    confirm.textContent = "确认已打印";
    confirm.disabled = selected.length === 0;
    confirm.addEventListener("click", () => {
      if (!selected.length) return;
      try {
        window.opener?.postMessage({
          type: "omrs-board-printed",
          boardId: data.board_id || "",
          pageEnd: actualEnd,
        }, "*");
        status.textContent = `已通知主程序推进到第 ${actualEnd} 页`;
        confirm.disabled = true;
      } catch (_) {
        status.textContent = "无法通知主程序，请回到展示板手动确认";
      }
    });
    toolbar.appendChild(confirm);
  }
})();
