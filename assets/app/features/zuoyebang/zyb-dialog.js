/** 识别工作窗：保留逐题草稿，识别可在后台继续，提交始终由用户确认。 */
import { html } from '../../core/html.js';
import { toElement, morph } from '../../core/dom.js';
import { button } from '../../ui/button.js';
import { icon } from '../../ui/icon.js';
import { openModal } from '../../ui/overlay.js';
import { editorView } from './zyb-view.js';
import { ROLES, candidateKey } from './zyb-state.js';

const KEY = 'omrs-zuoyebang-review';
const action = (label, name, options = {}) => button({ label, action: `zuoyebang.zyb${name}`, ...options });
const stored = () => { try { return sessionStorage.getItem(KEY); } catch (_) { return null; } };
const store = id => { try { if (id) sessionStorage.setItem(KEY, id); else sessionStorage.removeItem(KEY); } catch (_) { /* 草稿仍保存在内存。 */ } };
const recognizing = s => !s.result && (s.busy === 'extract' || s.job?.type === 'extract');

function loading(s) {
  return recognizing(s) ? html`<div class="zyb-dialog-loading" role="status" aria-live="polite" aria-atomic="true">
    <span class="zyb-dialog-loading-spinner" aria-hidden="true"></span><strong>识别中</strong>
    <p>正在识别题目与答案<br>可继续填写信息，或暂存返回</p></div>` : html``;
}

function footer(s) {
  const failed = Object.values(s.render.extraction || {}).some(part => part.status === 'failed');
  return html`<div class="zyb-dialog-summary"><strong>${s.result ? `${s.result.uid} 已录入` : '核对完成后录入'}</strong><span>${ROLES.map(role => `${role === 'question' ? '题目' : '答案'}${{ image: '保留图片', text: '使用文本', none: '为空' }[s.sections[role].mode]}`).join(' · ')}</span></div>
    <div class="zyb-actions">${action('暂存并返回', 'CloseReview', { variant: 'ghost', disabled: s.busy === 'commit' })}
      ${!s.result ? action(failed ? '重试失败项' : 'AI 识别题目与答案', 'Extract', { icon: 'sparkle', loading: s.busy === 'extract', disabled: !!s.busy || !!s.job }) : ''}
      ${action(s.result ? '已录入题库' : '录入 OMRS', 'Commit', { icon: 'check', variant: 'primary', disabled: !!s.busy || !!s.job || !!s.result, loading: s.busy === 'commit' })}</div>`;
}
function progress(s) {
  if (recognizing(s) && !s.error) return html``;
  return html`<div class="zyb-dialog-notice${s.error ? ' is-error' : s.result ? ' is-success' : ''}" role="${s.error ? 'alert' : 'status'}" aria-live="polite">
    ${icon(s.error ? 'alert-circle' : s.result ? 'check-circle' : s.busy === 'extract' ? 'sparkle' : 'info')}
    <div><strong>${s.busy === 'extract' ? '正在识别题目与答案' : s.result ? '已保存到题库' : s.error ? '需要核对' : '识别结果由你确认'}</strong><p>${s.busy === 'extract' ? '可以先填写题目信息；暂存返回后，识别会继续。' : s.message || '无法完整转录的内容会保留原图，也可直接按图片录入。'}</p></div></div>`;
}

export function createRecognitionDialog(host, s, { extract, commit, remember, closeSuggestions }) {
  let entry = null, element = null, identity = null, card = null, preserve = false;
  function paint() {
    if (!entry) return;
    if (!s.render || candidateKey(s) !== card) { close(); return; }
    if (s.render.id !== identity) { identity = s.render.id; store(identity); }
    morph(element.querySelector('#zyb-dialog-status'), progress(s));
    morph(element.querySelector('#zyb-dialog-loading'), loading(s));
    morph(element.querySelector('#zyb-editor'), editorView(s));
    morph(element.querySelector('#zyb-dialog-foot'), footer(s));
    element.querySelector('[data-action="zuoyebang.zybCloseReview"]').disabled = s.busy === 'commit';
    element.querySelector('.zyb-dialog-steps').dataset.complete = String(!!s.result);
  }
  function open({ recognize = true } = {}) {
    if (entry || !s.render || (s.busy && !['extract', 'render'].includes(s.busy))) return;
    identity = s.render.id;
    card = candidateKey(s);
    preserve = false;
    element = toElement(html`<dialog class="ui-dialog ui-dialog--xl zyb-recognition" aria-labelledby="zyb-dialog-title" aria-describedby="zyb-dialog-hint">
      <div class="ui-dialog__panel">
        <header class="ui-dialog__head"><div class="zyb-dialog-heading"><span class="zyb-dialog-emblem">${icon('sparkle')}</span><div><h2 id="zyb-dialog-title" class="ui-dialog__title">识别与录入</h2><p id="zyb-dialog-hint" class="zyb-help">把核对好的题目，整理成你的错题。</p></div></div>
          ${action('关闭识别窗口', 'CloseReview', { icon: 'x', iconOnly: true, variant: 'ghost' })}</header>
        <ol class="zyb-dialog-steps" aria-label="录题进度"><li class="is-done">${icon('check')}原题已确认</li><li class="is-active"><span>02</span>识别与修订</li><li><span>03</span>录入题库</li></ol>
        <div class="ui-dialog__body"><div id="zyb-dialog-status"></div><section id="zyb-editor"></section></div>
        <div id="zyb-dialog-loading"></div>
        <footer id="zyb-dialog-foot" class="ui-dialog__foot"></footer>
      </div></dialog>`);
    host.append(element);
    // 在 showModal 前绘制正文，初始焦点明确落在关闭按钮，避免自动打开建议框。
    morph(element.querySelector('#zyb-editor'), editorView(s));
    store(identity);
    entry = openModal(element, {
      initialFocus: '[data-action="zuoyebang.zybCloseReview"]',
      dismissible: () => s.busy !== 'commit',
      returnFocus: () => host.querySelector('[data-action="zuoyebang.zybReview"]'),
      onEnter: () => { if (!s.busy && !s.job && !s.result) void commit(); },
      onClose: () => { closeSuggestions(); remember(); if (!preserve) store(null); entry = null; },
    });
    paint();
    if (recognize && !s.result && !s.job && !Object.keys(s.render.extraction || {}).length) void extract();
  }
  function close(keepOpen = false) {
    if (!entry) return;
    preserve = keepOpen;
    entry.close(false);
  }
  return { open, paint, close, restore() { if (stored() === s.render?.id) open({ recognize: false }); } };
}
