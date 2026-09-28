/** AI 草稿工作区：列表、来源关联、字段与有序内容块。 */
import { html, each, raw } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { empty } from '../../ui/empty.js';
import { renderMd, hashText } from '../../domain/question/index.js';
import { labelChips } from '../../domain/labels/index.js';
import { commitProblem, draftPendingCount, draftStatusLabel, imageSha, imageUrl } from './drafts-state.js';

const statuses = [
  ['pending', '待审核'], ['done', '已入库'], ['discarded', '已丢弃'],
];
const titleOf = draft => draft.blocks?.find(block => block.section === '题目' && block.kind === 'text')?.text?.slice(0, 72)
  || draft.blocks?.find(block => block.section === '题目' && block.kind === 'image')?.note || '图片草稿';

function listView({ list, listLoaded, listError, filter, selectedId, counts, busy }) {
  return html`<aside class="drf-list" aria-label="AI 草稿列表">
    <div class="drf-list-head"><h2>AI 草稿</h2>${button({ label: '刷新', size: 'sm', action: 'create.draftReload', disabled: busy })}</div>
    <p class="drf-count">${draftPendingCount(counts)} 份待审核</p>
    <div class="drf-filters" role="group" aria-label="筛选草稿">
      ${statuses.map(([value, label]) => button({ label, size: 'sm', action: 'create.draftFilter', arg: value, pressed: filter === value }))}
    </div>
    ${listError ? html`<div class="drf-error" role="alert">读取列表失败：${listError}${button({ label: '重试', size: 'sm', action: 'create.draftReload' })}</div>`
    : !listLoaded ? html`<p role="status">正在读取草稿…</p>`
      : list.length ? html`<div class="drf-list-items">${each(list, draft => draft.id, draft => html`
      <button type="button" class="drf-item ${draft.id === selectedId ? 'on' : ''}" data-key="${draft.id}"
        data-action="create.draftOpen" data-arg="${draft.id}" aria-current="${draft.id === selectedId ? 'true' : 'false'}">
        <span class="drf-item-top"><strong>${draft.subject || '未填科目'} · ${draft.category || '未填分类'}</strong><small>${draftStatusLabel(draft.status)}</small></span>
        <span class="drf-item-excerpt">${titleOf(draft)}</span><small>${draft.created_at || ''}</small>
      </button>`)}</div>` : empty({ icon: 'inbox', title: filter === 'pending' ? '没有待审核草稿' : '这里还没有草稿',
        hint: filter === 'pending' ? 'AI 助手创建的草稿会出现在这里。' : '切换筛选可查看其他状态。', bordered: true })}
  </aside>`;
}

function sourceView(draft, value, readonly) {
  const source = draft.source_images || [];
  const known = new Map([...source, ...(draft.conversation_images || [])].map(image => [imageSha(image), image]));
  const attached = value.source_images.map(sha => known.get(sha) || { sha256: sha });
  const available = (draft.conversation_images || []).filter(image => !value.source_images.includes(imageSha(image)));
  return html`<section class="drf-sources"><div class="drf-section-head"><h3>来源截图</h3><span>${attached.length} 张</span></div>
    ${draft.sources_complete === false ? html`<p class="drf-hint" role="status">旧草稿的来源未完整恢复，请核对并从本次对话截图补关联。</p>` : ''}
    ${attached.length ? html`<div class="drf-image-grid">${each(attached, image => imageSha(image), image => html`
      <figure class="drf-source" data-key="${imageSha(image)}"><a href="${imageUrl(imageSha(image))}" target="_blank" rel="noopener" aria-label="打开来源截图 ${image.ref || imageSha(image)?.slice(0, 8)} 原图"><img loading="lazy" src="${imageUrl(imageSha(image))}" alt="来源截图 ${image.ref || imageSha(image)?.slice(0, 8)}"></a>
        <figcaption>${image.ref || imageSha(image)?.slice(0, 10)} · ${image.width && image.height ? `${image.width}×${image.height}` : '原图'}
        ${readonly ? '' : button({ label: '取消关联', size: 'sm', action: 'create.draftSourceRemove', arg: imageSha(image) })}</figcaption>
      </figure>`)}</div>` : html`<p class="drf-hint">尚未关联来源截图。</p>`}
    ${!readonly && available.length ? html`<div class="drf-source-add"><label for="drf-source-select">补关联本次对话截图</label>
      <select id="drf-source-select" class="ui-select"><option value="">请选择</option>${available.map(image => html`<option value="${imageSha(image)}">${image.ref || imageSha(image)?.slice(0, 10)} · ${image.width || '?'}×${image.height || '?'}</option>`)}</select>
      ${button({ label: '关联', size: 'sm', action: 'create.draftSourceAdd' })}</div>` : ''}
  </section>`;
}

const fieldInput = (name, label, value, readonly, type = 'text') => html`<label class="drf-field">${label}
  <input class="ui-input" type="${type}" data-input="create.draftField" data-arg="${name}" value="${value ?? ''}"${readonly ? html` readonly` : ''}></label>`;

function fieldsView(value, readonly) {
  const f = value.fields;
  return html`<section class="drf-fields"><h3>题目信息</h3><div class="drf-fields-grid">
    ${fieldInput('subject', '科目 *', f.subject, readonly)}${fieldInput('category', '分类 *', f.category, readonly)}
    ${fieldInput('difficulty', '难度（1–10）', f.difficulty, readonly, 'number')}
    ${fieldInput('knowledge_points', '知识点（逗号分隔）', (f.knowledge_points || []).join('，'), readonly)}
    <div class="drf-field"><span>标记</span><div class="drf-labels">${labelChips(f.labels || [])}
      ${readonly ? '' : button({ label: '添加标记', icon: 'plus', size: 'sm', action: 'create.draftLabels' })}</div></div>
    <label class="drf-field drf-wide">错因<textarea class="ui-textarea" rows="2" data-input="create.draftField" data-arg="cause"${readonly ? html` readonly` : ''}>${f.cause || ''}</textarea></label>
    <label class="drf-field drf-wide">备注<textarea class="ui-textarea" rows="2" data-input="create.draftField" data-arg="note"${readonly ? html` readonly` : ''}>${f.note || ''}</textarea></label>
  </div></section>`;
}

function blockView(block, index, value, readonly) {
  const key = block.id || block._key;
  const peers = value.blocks.filter(row => row.section === block.section);
  const peerIndex = peers.indexOf(block);
  const image = value.source_images.includes(block.image_sha);
  return html`<article class="drf-block" data-key="${key}"><header><strong>${block.kind === 'text' ? '文字' : '图片'} ${index + 1}</strong>
    ${readonly ? '' : html`<div class="drf-block-actions">
      ${button({ label: '上移', size: 'sm', action: 'create.draftMove', arg: `${key}|-1`, disabled: peerIndex === 0 })}
      ${button({ label: '下移', size: 'sm', action: 'create.draftMove', arg: `${key}|1`, disabled: peerIndex === peers.length - 1 })}
      ${button({ label: '删除', size: 'sm', variant: 'danger', action: 'create.draftRemoveBlock', arg: key })}</div>`}</header>
    ${readonly ? '' : html`<label class="drf-field">所属部分<select class="ui-select" data-change="create.draftBlockSection" data-arg="${key}">
      <option value="题目"${block.section === '题目' ? html` selected` : ''}>题目</option><option value="答案"${block.section === '答案' ? html` selected` : ''}>答案</option></select></label>`}
    ${block.kind === 'text' ? html`<label class="drf-field">内容<textarea class="ui-textarea" rows="4" data-input="create.draftBlockText" data-arg="${key}"${readonly ? html` readonly` : ''}>${block.text || ''}</textarea></label>
      <div class="drf-md q-md" data-hash="${hashText(block.text || '')}">${raw(renderMd(block.text || ''))}</div>`
    : html`<div class="drf-block-image">${image ? html`<img loading="lazy" src="${imageUrl(block.image_sha)}" alt="${block.section}图片区">` : html`<p class="drf-error">来源图片已取消关联</p>`}</div>
      <p class="drf-hint">${block.box ? '已框选整图' : '尚未框选，入库前请使用整图'}</p>
      ${readonly ? '' : button({ label: '使用整图', size: 'sm', action: 'create.draftWhole', arg: key, disabled: !image })}
      <label class="drf-field">图片说明<input class="ui-input" data-input="create.draftBlockNote" data-arg="${key}" value="${block.note || ''}"${readonly ? html` readonly` : ''}></label>`}
  </article>`;
}

function blocksView(value, readonly) {
  return html`<section class="drf-blocks"><h3>题目与答案 · 按显示顺序入库</h3>
    ${['题目', '答案'].map(section => {
      const blocks = value.blocks.filter(block => block.section === section);
      return html`<div class="drf-section"><div class="drf-section-head"><h4>${section}</h4><span>${blocks.length} 块</span></div>
        ${blocks.length ? each(blocks, block => block.id || block._key, (block, index) => blockView(block, index, value, readonly))
    : html`<p class="drf-hint">${section === '题目' ? '至少需要一个题目块。' : '可以没有答案。'}</p>`}
        ${readonly ? '' : html`<div class="drf-add">${button({ label: '添加文字', size: 'sm', action: 'create.draftAddText', arg: section })}
          ${value.source_images.length ? html`<select class="ui-select" data-draft-image="${section}" aria-label="${section}图片来源">
            ${value.source_images.map(sha => html`<option value="${sha}">${sha.slice(0, 10)}</option>`)}</select>
            ${button({ label: '添加图片', size: 'sm', action: 'create.draftAddImage', arg: section })}` : ''}</div>`}</div>`;
    })}</section>`;
}

function detailView({ draft, value, detailLoaded, detailError, dirty, busy, message, conflict }) {
  if (detailError) return html`<main class="drf-detail"><div class="drf-error" role="alert">读取草稿失败：${detailError}${button({ label: '重试', action: 'create.draftRetry' })}</div></main>`;
  if (!detailLoaded) return html`<main class="drf-detail"><p role="status">正在读取草稿…</p></main>`;
  if (!draft || !value) return html`<main class="drf-detail">${empty({ icon: 'inbox', title: '选择一份草稿', hint: '在左侧列表选择，核对后保存或通过。', bordered: true })}</main>`;
  const readonly = draft.status === 'done' || draft.status === 'discarded';
  const editingDisabled = readonly || busy;
  const problem = readonly ? '' : commitProblem(value);
  return html`<main class="drf-detail"><div class="drf-detail-head"><div><p class="drf-id">${draft.id} · 第 ${draft.revision ?? '?'} 版</p>
    <h2>${draftStatusLabel(draft.status)} ${dirty ? '· 未保存' : ''}</h2></div><span>${draft.updated_at || ''}</span></div>
    ${message ? html`<p class="drf-message" role="status">${message}
      ${conflict ? button({ label: '重新读取并放弃本地修改', size: 'sm', action: 'create.draftReloadDetail' }) : ''}</p>` : ''}
    ${draft.status === 'done' ? html`<p class="drf-success">${draft.question_available === false ? '已入库，题目当前不可用' : `已入库：${draft.uid || draft.question_id || '题目'}`}
      ${draft.uid && draft.question_available !== false ? button({ label: '查看题目', size: 'sm', action: 'create.draftQuestion' }) : ''}</p>` : ''}
    ${sourceView(draft, value, editingDisabled)}${fieldsView(value, editingDisabled)}${blocksView(value, editingDisabled)}
    ${readonly ? html`<p class="drf-hint">此草稿的正文已锁定。</p>` : html`<footer class="drf-footer">
      ${problem ? html`<p class="drf-hint" role="status">${problem}</p>` : ''}
      ${button({ label: '保存', variant: 'primary', action: 'create.draftSave', loading: busy, disabled: !dirty })}
      ${button({ label: '通过并入库', action: 'create.draftCommit', loading: busy, disabled: Boolean(problem) })}
      ${button({ label: '丢弃草稿', variant: 'danger', action: 'create.draftDiscard', disabled: busy })}
    </footer>`}</main>`;
}

export function draftsView(state) {
  return html`<div class="drf">${listView(state)}${detailView(state)}</div>`;
}
