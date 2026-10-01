/** 草稿审核正文：紧凑信息摘要、连续分块与统一底部操作。 */
import { html, each, raw } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { renderMd, hashText } from '../../domain/question/index.js';
import { labelChips } from '../../domain/labels/index.js';
import { commitProblem, imageUrl } from './drafts-state.js';

const fieldInput = (name, label, value, readonly, type = 'text') => html`<label class="drf-field">${label}
  <input class="ui-input" type="${type}" data-input="create.draftField" data-arg="${name}" value="${value ?? ''}"${readonly ? html` readonly` : ''}></label>`;

function fieldsView(value, readonly, editing, busy) {
  const f = value.fields;
  const locked = readonly || busy;
  return html`<section class="drf-fields drf-review-info" data-key="draft-fields"><div class="drf-section-head"><h3>题目信息</h3>
    ${readonly ? '' : button({ label: editing ? '完成编辑' : '编辑信息', variant: 'ghost', size: 'sm', action: 'create.draftEditFields', disabled: busy })}</div>
    ${!editing || readonly ? html`<dl class="drf-info-summary"><div><dt>科目 · 分类</dt><dd>${f.subject || '未填'} · ${f.category || '未填'}</dd></div>
      <div><dt>难度 · 知识点</dt><dd>${f.difficulty || '未填'} · ${(f.knowledge_points || []).join('、') || '无'}</dd></div>
      <div class="drf-wide"><dt>错因</dt><dd>${f.cause || '未记录'}</dd></div>
      ${f.note ? html`<div class="drf-wide"><dt>备注</dt><dd>${f.note}</dd></div>` : ''}
      ${(f.labels || []).length ? html`<div class="drf-wide"><dt>标记</dt><dd>${labelChips(f.labels)}</dd></div>` : ''}</dl>` : html`<div class="drf-fields-grid">
    ${fieldInput('subject', '科目 *', f.subject, locked)}${fieldInput('category', '分类 *', f.category, locked)}
    ${fieldInput('difficulty', '难度（1–10）', f.difficulty, locked, 'number')}
    ${fieldInput('knowledge_points', '知识点（逗号分隔）', (f.knowledge_points || []).join('，'), locked)}
    <div class="drf-field"><span>标记</span><div class="drf-labels">${labelChips(f.labels || [])}
      ${button({ label: '添加标记', icon: 'plus', size: 'sm', action: 'create.draftLabels', disabled: busy })}</div></div>
    <label class="drf-field drf-wide">错因<textarea class="ui-textarea" rows="2" data-input="create.draftField" data-arg="cause"${locked ? html` readonly` : ''}>${f.cause || ''}</textarea></label>
    <label class="drf-field drf-wide">备注<textarea class="ui-textarea" rows="2" data-input="create.draftField" data-arg="note"${locked ? html` readonly` : ''}>${f.note || ''}</textarea></label>
  </div>`}</section>`;
}

function imageView(block, value, readonly, editing, busy) {
  const key = block.id || block._key;
  const attached = value.source_images.includes(block.image_sha);
  return html`<div class="drf-block-image">${attached ? block.box && (block.box.x !== 0 || block.box.y !== 0 || block.box.w !== 1 || block.box.h !== 1)
    ? html`<canvas data-draft-crop="${key}" data-morph="skip" aria-label="${block.section}裁图预览"></canvas>`
    : html`<img loading="lazy" src="${imageUrl(block.image_sha)}" alt="${block.section}图片区">`
    : html`<p class="drf-error">来源图片已取消关联</p>`}</div>
    <div class="drf-image-tools"><span class="drf-hint">${block.box ? (block.box.x === 0 && block.box.y === 0 && block.box.w === 1 && block.box.h === 1 ? '已选择整图' : '已选取局部区域') : '尚未框选'}</span>
      ${readonly ? '' : html`${button({ label: '框选 / 转文字', variant: 'ghost', size: 'sm', action: 'create.draftEditImage', arg: key, disabled: busy || !attached })}
        ${button({ label: '使用整图', variant: 'ghost', size: 'sm', action: 'create.draftWhole', arg: key, disabled: busy || !attached })}`}</div>
    ${editing && !readonly ? html`<label class="drf-field">图片说明<input class="ui-input" data-input="create.draftBlockNote" data-arg="${key}" value="${block.note || ''}"${busy ? html` readonly` : ''}></label>`
      : block.note ? html`<p class="drf-hint">${block.note}</p>` : ''}`;
}

function blockView(block, index, value, readonly, editingBlock, busy) {
  const key = block.id || block._key;
  const editing = editingBlock === key && !readonly;
  const number = String(index + 1).padStart(2, '0');
  return html`<article class="drf-block ${editing ? 'is-editing' : ''}" data-key="${key}" aria-label="${block.section}${block.kind === 'text' ? '文字' : '图片'}块 ${number}">
    <span class="drf-block-number" aria-hidden="true">${number}</span><div class="drf-block-body">
      ${block.kind === 'text' ? editing
        ? html`<label class="drf-field">内容<textarea class="ui-textarea" rows="5" data-input="create.draftBlockText" data-arg="${key}"${busy ? html` readonly` : ''}>${block.text || ''}</textarea></label>`
        : html`<div class="drf-md q-md" data-hash="${hashText(block.text || '')}">${block.text?.trim() ? raw(renderMd(block.text)) : html`<p class="drf-hint">空文字块，点击编辑补充。</p>`}</div>`
      : imageView(block, value, readonly, editing, busy)}
    </div>${readonly ? '' : html`<div class="drf-block-actions">
      ${button({ label: editing ? '完成' : '编辑', variant: 'ghost', size: 'sm', action: 'create.draftEditBlock', arg: key, disabled: busy, title: `${block.section}块 ${number}` })}
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="create.draftBlockMenu" data-arg="${key}" aria-haspopup="menu" aria-label="${block.section}块 ${number} 更多操作"${busy ? html` disabled` : ''}>更多</button>
    </div>`}</article>`;
}

function blocksView(value, readonly, editingBlock, busy) {
  return html`<div class="drf-blocks" data-key="draft-blocks">
    ${['题目', '答案'].map(section => {
      const blocks = value.blocks.filter(block => block.section === section);
      return html`<section class="drf-section drf-review-${section === '题目' ? 'question' : 'answer'}" data-key="${section}"><div class="drf-section-head"><h3>${section === '答案' ? '答案解析' : section}</h3><span>${blocks.length} 块</span></div>
        ${blocks.length ? each(blocks, block => block.id || block._key, (block, index) => blockView(block, index, value, readonly, editingBlock, busy))
          : html`<p class="drf-hint">${section === '题目' ? '至少需要一个题目块。' : '可以没有答案。'}</p>`}
        ${readonly ? '' : html`<div class="drf-add" data-key="add-${section}">${button({ label: '添加文字', icon: 'plus', variant: 'ghost', size: 'sm', action: 'create.draftAddText', arg: section, disabled: busy })}
          ${value.source_images.length ? button({ label: '添加图片', icon: 'plus', variant: 'ghost', size: 'sm', action: 'create.draftAddImage', arg: section, disabled: busy }) : ''}</div>`}</section>`;
    })}</div>`;
}

export function reviewActions({ draft, value, dirty, busy }) {
  const readonly = ['done', 'discarded'].includes(draft.status);
  if (readonly) return html`<footer class="drf-footer" data-key="draft-actions"><p class="drf-hint">此草稿的正文已锁定。${draft.status === 'done' && (draft.training_tasks || []).some(task => task.status === 'error') ? '训练登记失败，可重试。' : ''}</p>
    ${draft.status === 'done' && dirty ? button({ label: '保存训练框', variant: 'primary', action: 'create.draftSave', loading: busy }) : ''}
    ${draft.status === 'done' && (draft.training_tasks || []).some(task => task.status === 'error') ? button({ label: '重试训练登记', action: 'create.draftRetryTraining', disabled: busy }) : ''}</footer>`;
  const problem = commitProblem(value);
  return html`<footer class="drf-footer" data-key="draft-actions"><div class="drf-format-check" role="status">${problem
    ? button({ label: `需处理：${problem}`, variant: 'ghost', size: 'sm', action: 'create.draftLocateIssue', disabled: busy })
    : html`<span>✓ 格式检查通过</span>`}</div><div class="drf-footer-actions">
      ${button({ label: '丢弃', variant: 'ghost', action: 'create.draftDiscard', disabled: busy })}
      ${button({ label: '暂存', action: 'create.draftSave', loading: busy, disabled: !dirty })}
      ${button({ label: '入库并下一题', variant: 'primary', action: 'create.draftCommit', loading: busy, disabled: Boolean(problem) })}
    </div></footer>`;
}

export function reviewWorkspace(state, readonly) {
  return html`<div class="drf-review-workspace"><section class="drf-review-content" aria-label="内容审核">
    ${fieldsView(state.value, readonly, state.fieldsEditing, state.busy)}
    ${blocksView(state.value, readonly, state.editingBlock, state.busy)}</section>${reviewActions(state)}</div>`;
}
