/** 共享单题选择器：人工绑定旧计划等需要明确确认题目身份的入口。 */
import { html, each } from '../../core/html.js';
import { toElement, morph } from '../../core/dom.js';
import { dialog } from '../../ui/dialog.js';
import { allItems, filterAll } from '../items.js';
import { questionRef } from './ref.js';

export async function pickQuestion({ title = '选择题目', hint = '请核对 UID、科目和分类后确认。', items = allItems(), showDialog = dialog } = {}) {
  const snapshot = items.filter(item => !item.suspended && item.question_id).map(item => ({ ...item }));
  const node = toElement(html`<div class="qop-form"></div>`);
  let query = '', selected = '';
  function paint() {
    const rows = filterAll(snapshot, { text: query.toLowerCase(), sort: 'none' });
    morph(node, html`<label class="ui-field__label" for="question-pick-search">搜索题目</label>
      <input class="ui-input" id="question-pick-search" type="search" value="${query}" placeholder="UID / 科目 / 分类">
      <label class="ui-field__label" for="question-pick-value">题目</label>
      <select class="ui-input" id="question-pick-value"><option value="">请选择…</option>${each(rows, item => item.question_id, item => html`<option value="${item.question_id}"${selected === item.question_id ? html` selected` : ''}>${item.uid} · ${item.subject || ''} / ${item.category || ''}</option>`)}</select>`);
  }
  node.addEventListener('input', event => { if (event.target.id === 'question-pick-search') { query = event.target.value; selected = ''; paint(); } });
  node.addEventListener('change', event => { if (event.target.id === 'question-pick-value') selected = event.target.value; });
  paint();
  const result = await showDialog({ title, hint, content: node, okText: '确认题目', focus: '#question-pick-search', onOk: () => !!selected });
  return result.ok && selected ? questionRef(snapshot.find(item => item.question_id === selected), snapshot) : null;
}
