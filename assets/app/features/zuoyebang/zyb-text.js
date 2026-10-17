/** 核对正文的预览／源码；图片只在显示层缩写，原文仍用于草稿和入库。 */
import { html, raw } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { renderMd } from '../../domain/question/index.js';

const sources = new WeakMap();
const IMAGE_START = /!\[\[|!\[(?:\\.|[^\]\\])*\]\(|<img(?=[\s/>])|data:image\/[a-z0-9.+-]+(?:;[^,\s"'<>]*)?,/gi;

function imageEnd(text, match) {
  const start = match.index + match[0].length;
  if (match[0] === '![[') {
    const end = text.indexOf(']]', start);
    return end < 0 ? -1 : end + 2;
  }
  if (/^data:/i.test(match[0])) {
    const tail = text.slice(start).search(/[\s"'<>\)\]]/);
    return tail < 0 ? text.length : start + tail;
  }
  const tag = /^<img/i.test(match[0]);
  let depth = 1, quote = '', angle = false;
  for (let i = start; i < text.length; i += 1) {
    const ch = text[i];
    if (!tag && ch === '\\') { i += 1; continue; }
    if (quote) { if (ch === quote) quote = ''; continue; }
    if (tag || /\s/.test(text[i - 1])) {
      if (ch === '"' || ch === "'") { quote = ch; continue; }
    }
    if (tag) { if (ch === '>') return i + 1; continue; }
    if (angle) { if (ch === '>') angle = false; continue; }
    if (ch === '<') angle = true;
    else if (ch === '(') depth += 1;
    else if (ch === ')' && --depth === 0) return i + 1;
  }
  // 兼容共享 Markdown 渲染器能识别的未配平图片地址，避免预览意外请求图片。
  const fallback = tag ? -1 : text.indexOf(')', start);
  return fallback < 0 ? -1 : fallback + 1;
}

export function compactImages(text = '') {
  const source = String(text), re = new RegExp(IMAGE_START.source, 'gi');
  const images = [];
  let value = '', last = 0, match, number = 0;
  while ((match = re.exec(source))) {
    const end = imageEnd(source, match);
    if (end < 0) continue;
    let token;
    do { number += 1; token = `[图片 ${number}]`; } while (source.includes(token));
    images.push({ token, source: source.slice(match.index, end) });
    value += source.slice(last, match.index) + token;
    last = end; re.lastIndex = end;
  }
  return { value: value + source.slice(last), images };
}

export function expandImages(value, images) {
  const byToken = new Map(images.map(image => [image.token, image.source]));
  return String(value).replace(/\[图片 \d+\]/g, token => byToken.get(token) ?? token);
}

export function sourceProjection(section) {
  let source = sources.get(section);
  if (!source || source.expanded !== section.text) {
    source = { ...compactImages(section.text), expanded: section.text };
    sources.set(section, source);
  }
  return source;
}

export function editSource(section, value) {
  const source = sourceProjection(section);
  const expanded = expandImages(value, source.images), changed = expanded !== section.text;
  source.value = value; source.expanded = expanded; section.text = expanded;
  return changed;
}

export function toggleTextView(section) {
  if (!section || section.mode !== 'text') return false;
  section.view = section.view === 'source' ? 'preview' : 'source';
  sources.delete(section);
  return true;
}

export function textView(section, role, locked) {
  const source = section.view === 'source', compact = sourceProjection(section);
  const title = role === 'question' ? '题目正文' : '完整答案正文';
  return html`<div class="zyb-text">
    <div class="zyb-head"><span id="zyb-text-title-${role}">${title}</span>${button({ label: source ? '预览' : '源码', action: 'zuoyebang.zybTextView', arg: role, pressed: source, title: source ? '预览文字与公式' : '编辑正文源码' })}</div>
    ${source ? html`<textarea class="ui-textarea zyb-text-source" rows="6" aria-labelledby="zyb-text-title-${role}" data-zyb-text="${role}"${locked ? html` readonly` : ''}>${compact.value}</textarea>`
      : html`<div class="zyb-text-preview q-md" data-zyb-preview="${role}" role="region" aria-labelledby="zyb-text-title-${role}" tabindex="0">${section.text.trim() ? raw(renderMd(compactImages(section.text).value, 'full')) : html`<p class="zyb-help">${locked ? '暂无正文' : '暂无正文，可切换源码补充。'}</p>`}</div>`}
    ${compact.images.length ? html`<p class="zyb-help">图片以 [图片 1] 等占位符显示，保留占位符即可保留原图。</p>` : ''}
  </div>`;
}
