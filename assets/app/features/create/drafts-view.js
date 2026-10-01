/** AI 草稿工作区：列表、来源关联、字段与有序内容块。 */
import { html, each, raw } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { empty } from '../../ui/empty.js';
import { renderMd, hashText } from '../../domain/question/index.js';
import { labelChips } from '../../domain/labels/index.js';
import { commitProblem, draftPendingCount, draftStatusLabel, imageSha, imageUrl, latestDetectResult, reviewChecks } from './drafts-state.js';

const statuses = [
  ['pending', '待审核'], ['done', '已入库'], ['discarded', '已丢弃'],
];
const trainingStatus = status => ({ pending: '待框选', ready: '已框选', registered: '已登记', error: '登记失败' })[status] || '待创建';
const boxOrigin = origin => ({ original: '完整原图', manual: '手动', ai: 'AI 建议', ai_edited: 'AI 建议后人工调整' })[origin] || '手动';
const titleOf = draft => draft.blocks?.find(block => block.section === '题目' && block.kind === 'text')?.text?.slice(0, 72)
  || draft.blocks?.find(block => block.section === '题目' && block.kind === 'image')?.note || '图片草稿';

function listView({ list, listLoaded, listError, filter, selectedId, counts, busy, queueOpen }) {
  return html`<aside class="drf-list ${queueOpen ? 'is-open' : ''}" aria-label="AI 草稿列表">
    <div class="drf-list-head"><div><h2>AI 草稿</h2><p class="drf-count">${draftPendingCount(counts)} 份待审核</p></div>
      <div class="drf-list-actions">${button({ label: queueOpen ? '收起队列' : '查看队列', size: 'sm', action: 'create.draftToggleQueue' })}${button({ label: '清理', size: 'sm', action: 'create.draftCleanup', disabled: busy })}${button({ label: '刷新', size: 'sm', action: 'create.draftReload', disabled: busy })}</div></div>
    <div class="drf-filters" role="group" aria-label="筛选草稿">
      ${statuses.map(([value, label]) => button({ label, size: 'sm', action: 'create.draftFilter', arg: value, pressed: filter === value }))}
    </div>
    ${listError ? html`<div class="drf-error" role="alert">读取列表失败：${listError}${button({ label: '重试', size: 'sm', action: 'create.draftReload' })}</div>`
    : !listLoaded ? html`<p role="status">正在读取草稿…</p>`
      : list.length ? html`<div class="drf-list-items">${each(list, draft => draft.id, draft => html`
      <button type="button" class="drf-item ${draft.id === selectedId ? 'on' : ''}" data-key="${draft.id}"
        data-action="create.draftOpen" data-arg="${draft.id}" aria-current="${draft.id === selectedId ? 'true' : 'false'}">
        <span class="drf-item-top"><strong>${draft.subject || '未填科目'} · ${draft.category || '未填分类'}</strong><small>${draftStatusLabel(draft.status)}</small></span>
        <span class="drf-item-excerpt">${titleOf(draft)}</span><small>${draft.source_channel === 'mcp' ? '来源：MCP · ' : ''}${draft.created_at || ''}</small>
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
      <figure class="drf-source" data-key="${imageSha(image)}"><button type="button" class="drf-source__preview" data-action="create.draftPreviewSource" data-arg="${imageSha(image)}" aria-label="预览来源截图 ${image.ref || imageSha(image)?.slice(0, 8)}"><img loading="lazy" src="${imageUrl(imageSha(image))}" alt="来源截图 ${image.ref || imageSha(image)?.slice(0, 8)}"></button>
        <figcaption>${image.ref || imageSha(image)?.slice(0, 10)} · ${image.width && image.height ? `${image.width}×${image.height}` : '原图'}
        ${(draft.training_tasks || []).some(task => task.image_sha === imageSha(image) && task.force_crop && task.status !== 'registered')
          ? html`<small>独立训练框待核对；不影响题目入库</small>` : ''}
        ${readonly ? '' : draft.source_channel === 'mcp' && source.some(row => imageSha(row) === imageSha(image))
          ? html`<small>MCP 完整原图保留</small>`
          : button({ label: '取消关联', size: 'sm', action: 'create.draftSourceRemove', arg: imageSha(image) })}</figcaption>
      </figure>`)}</div>` : html`<p class="drf-hint">尚未关联来源截图。</p>`}
    ${!readonly && available.length ? html`<div class="drf-source-add"><label for="drf-source-select">补关联本次对话截图</label>
      <select id="drf-source-select" class="ui-select"><option value="">请选择</option>${available.map(image => html`<option value="${imageSha(image)}">${image.ref || imageSha(image)?.slice(0, 10)} · ${image.width || '?'}×${image.height || '?'}</option>`)}</select>
      ${button({ label: '关联', size: 'sm', action: 'create.draftSourceAdd' })}</div>` : ''}
  </section>`;
}

function detectPanel(detected, mode, readonly, busy, revision, trainingReadonly) {
  if (!detected) return '';
  const { job, result } = detected;
  if (!result) {
    const error = job.errors?.[0]?.error || job.errors?.[0]?.msg;
    return error ? html`<p class="drf-hint" role="status">AI 框选失败：${error}。可手动画框或重试。</p>` : '';
  }
  if (result.status === 'suggested') return html`<div class="drf-detect" role="status">
    <p>AI 候选待核对：${result.reason || '有多种框法，未自动修改正文。'}${job.revision !== revision
      ? '这组候选来自旧版草稿，请重新检测。' : '选择当前图片区块后，可明确采用一个候选；虚线框只供参考。'}</p>
    <div class="drf-detect-list">${(result.candidates || []).map((candidate, index) => html`<div class="drf-detect-row">
      <span>${candidate.role === 'answer' ? '答案' : '题目'}候选 ${index + 1}${Number.isFinite(candidate.conf) ? ` · ${Math.round(candidate.conf * 100)}%` : ''}</span>
      ${button({ label: mode === 'training' ? '采用为训练框' : '采用到当前图片区块', size: 'sm', action: 'create.draftAcceptCandidate',
        arg: String(index), disabled: busy || job.revision !== revision || (readonly && mode !== 'training') || (mode === 'training' && trainingReadonly) })}</div>`)}</div>
  </div>`;
  if (result.status === 'applied') return result.applied_blocks?.length
    ? html`<p class="drf-hint" role="status">AI 已填入 ${result.applied_blocks.length} 个明确匹配的正文框，请核对后继续。</p>`
    : html`<p class="drf-hint" role="status">AI 已填入独立训练框；正文保持只读，训练登记仍受来源图开关控制。</p>`;
  if (result.status === 'skipped') return html`<p class="drf-hint" role="status">AI 框选已跳过：${result.reason || '请手动画框。'}</p>`;
  if (result.status === 'conflict') return html`<p class="drf-hint" role="status">AI 框选结果与草稿版本冲突，未修改当前框；请核对后重试。</p>`;
  return '';
}

function canvasPanel({ draft, value, training, canvasSha, canvasMode, selectedBlock, drawSection, busy, job }) {
  const images = (draft.source_images || []).filter(image => value.source_images.includes(imageSha(image)));
  if (!images.length || draft.status === 'discarded') return '';
  const current = images.find(image => imageSha(image) === canvasSha) || images[0];
  const sha = imageSha(current);
  const task = (draft.training_tasks || []).find(row => row.image_sha === sha);
  const boxes = task ? (training?.[task.id] || []) : [];
  const bodyBlocks = value.blocks.filter(row => row.kind === 'image' && row.image_sha === sha);
  const bodyReadonly = draft.status === 'done' || busy;
  const trainReadonly = task?.status === 'registered' || busy;
  const trainingOn = current.train === true;
  const trainingAvailable = Boolean(task && (trainingOn || task.force_crop || !bodyBlocks.length));
  const detected = latestDetectResult(draft, job, sha);
  const canDetect = !busy && !job && task?.status !== 'registered'
    && (['cropping', 'review'].includes(draft.status) || (draft.status === 'done' && !bodyBlocks.length));
  const selected = bodyBlocks.find(row => (row.id || row._key) === selectedBlock);
  return html`<section class="drf-canvas"><div class="drf-section-head"><h3>来源图框选</h3><span>按来源图逐张核对</span></div>
    <div class="drf-canvas-tabs" role="group" aria-label="来源图">
      ${images.map(image => button({ label: image.ref || imageSha(image).slice(0, 10), size: 'sm',
        action: 'create.draftCanvasImage', arg: imageSha(image), pressed: sha === imageSha(image) }))}
    </div>
    <div class="drf-canvas-meta"><span>${current.ref || sha.slice(0, 10)} · ${current.width}×${current.height}</span>
      ${current.inbox_item_id ? html`<span>训练图已登记</span>` : button({ label: trainingOn ? '参与训练：开' : '参与训练：关', size: 'sm',
        action: 'create.draftTrainToggle', arg: sha, disabled: busy })}
      ${!current.inbox_item_id && trainingOn ? html`<small>该图片的训练开关由同图草稿共享。</small>` : ''}
      ${task?.force_crop && task.status !== 'registered' ? html`<small>这张图有独立训练框任务；可以先入库，再补标。</small>` : ''}
    </div>
    <div class="drf-canvas-tabs" role="group" aria-label="框选用途">
      ${button({ label: '题目正文', size: 'sm', action: 'create.draftCanvasMode', arg: 'body', pressed: canvasMode !== 'training' })}
      ${trainingAvailable ? button({ label: '独立训练框', size: 'sm', action: 'create.draftCanvasMode', arg: 'training', pressed: canvasMode === 'training' }) : ''}
      ${canDetect ? button({ label: 'AI 框选', size: 'sm', action: 'create.draftDetect', arg: sha }) : ''}
    </div>
    ${canvasMode === 'training' && trainingAvailable ? html`<div class="drf-canvas-tools">
      <span>训练任务：${trainingStatus(task?.status)}${task?.error ? ` · ${task.error}` : ''}</span>
      ${button({ label: '画题目框', size: 'sm', action: 'create.draftDrawSection', arg: '题目', pressed: drawSection !== '答案', disabled: trainReadonly })}
      ${button({ label: '画答案框', size: 'sm', action: 'create.draftDrawSection', arg: '答案', pressed: drawSection === '答案', disabled: trainReadonly })}
      <small>训练框独立于正文；题目入库后仍可补标。${!trainingOn ? '当前未开启参与训练，保存标注不会登记数据集。' : ''}</small></div>`
    : html`<div class="drf-canvas-tools"><label for="drf-canvas-block">当前图片区块</label>
      <select id="drf-canvas-block" class="ui-select" data-change="create.draftCanvasBlock"${bodyReadonly ? html` disabled` : ''}>
        <option value="">选择要框选的图片块</option>${bodyBlocks.map((row, index) => html`<option value="${row.id || row._key}"${(row.id || row._key) === selectedBlock ? html` selected` : ''}>${row.section}图片 ${index + 1}${row.box ? ' · 已框' : ' · 待框'}</option>`)}</select>
      ${selected && !bodyReadonly ? button({ label: '整图', size: 'sm', action: 'create.draftWhole', arg: selected.id || selected._key }) : ''}
      <small>${bodyBlocks.length ? '选择图片块后，在图上画框、拖动或拉动边角。'
        : draft.status === 'done' ? '正文已入库且只读；可切换独立训练框继续标注来源图。'
          : '这份草稿只有文字块；如需保留来源图框位，请切换独立训练框。'}</small></div>`}
    <div class="drf-canvas-wrap"><div class="ib-stage-img" id="drf-stage-img" data-morph="skip"></div></div>
    <p class="drf-hint"><span id="drf-canvas-file"></span><span id="drf-canvas-zoom"></span> · 可用鼠标或触摸手势画框、移动和缩放。</p>
    ${detectPanel(detected, canvasMode, draft.status === 'done', busy, draft.revision, trainReadonly)}
    ${canvasMode === 'training' && trainingAvailable ? html`<div class="drf-training-boxes">
      ${boxes.map(box => html`<div class="drf-training-box" data-key="${box.id || box._key}"><span>${box.section}框 · ${boxOrigin(box.box_origin)}</span>
        ${trainReadonly ? '' : html`<select class="ui-select" data-change="create.draftTrainingSection" data-arg="${task.id}|${box.id || box._key}">
          <option value="题目"${box.section === '题目' ? html` selected` : ''}>题目</option><option value="答案"${box.section === '答案' ? html` selected` : ''}>答案</option></select>
          ${button({ label: '删除框', size: 'sm', variant: 'danger', action: 'create.draftTrainingRemove', arg: `${task.id}|${box.id || box._key}` })}`}</div>`)}
      ${!boxes.length ? html`<p class="drf-hint">尚无训练框。画框后点「保存」登记标注。</p>` : ''}</div>` : ''}
    ${canvasMode !== 'training' && selected?.box && !bodyReadonly ? html`<div class="drf-canvas-tools">
      ${button({ label: '删除当前框', size: 'sm', variant: 'danger', action: 'create.draftClearBox', arg: selected.id || selected._key })}
      ${button({ label: job ? '正在转文字…' : '转为文字', size: 'sm', action: 'create.draftExtract', arg: selected.id || selected._key,
        disabled: busy || Boolean(job) || !selected.id })}
      ${!selected.id ? html`<small>先保存新图片区块，再转文字。</small>` : ''}</div>` : ''}
    ${job ? html`<p class="drf-message" role="status">${job.type === 'detect' ? 'AI 框选' : '转文字'}任务：${job.status === 'queued' ? '排队中' : '处理中'} · ${job.processed || 0}/${job.total || 1}</p>` : ''}
  </section>`;
}

const fieldInput = (name, label, value, readonly, type = 'text') => html`<label class="drf-field">${label}
  <input class="ui-input" type="${type}" data-input="create.draftField" data-arg="${name}" value="${value ?? ''}"${readonly ? html` readonly` : ''}></label>`;

function fieldsView(value, readonly, editing) {
  const f = value.fields;
  return html`<section class="drf-fields drf-review-info"><div class="drf-section-head"><h3>题目信息</h3>
    ${readonly ? '' : button({ label: editing ? '完成编辑' : '编辑信息', size: 'sm', action: 'create.draftEditFields' })}</div>
    ${!editing ? html`<dl class="drf-info-summary"><div><dt>科目 · 分类</dt><dd>${f.subject || '未填'} · ${f.category || '未填'}</dd></div>
      <div><dt>难度 · 知识点</dt><dd>${f.difficulty || '未填'} · ${(f.knowledge_points || []).join('、') || '无'}</dd></div>
      <div><dt>错因</dt><dd>${f.cause || '未记录'}</dd></div>
      ${f.note ? html`<div><dt>备注</dt><dd>${f.note}</dd></div>` : ''}
      ${(f.labels || []).length ? html`<div><dt>标记</dt><dd>${labelChips(f.labels)}</dd></div>` : ''}</dl>` : html`<div class="drf-fields-grid">
    ${fieldInput('subject', '科目 *', f.subject, readonly)}${fieldInput('category', '分类 *', f.category, readonly)}
    ${fieldInput('difficulty', '难度（1–10）', f.difficulty, readonly, 'number')}
    ${fieldInput('knowledge_points', '知识点（逗号分隔）', (f.knowledge_points || []).join('，'), readonly)}
    <div class="drf-field"><span>标记</span><div class="drf-labels">${labelChips(f.labels || [])}
      ${readonly ? '' : button({ label: '添加标记', icon: 'plus', size: 'sm', action: 'create.draftLabels' })}</div></div>
    <label class="drf-field drf-wide">错因<textarea class="ui-textarea" rows="2" data-input="create.draftField" data-arg="cause"${readonly ? html` readonly` : ''}>${f.cause || ''}</textarea></label>
    <label class="drf-field drf-wide">备注<textarea class="ui-textarea" rows="2" data-input="create.draftField" data-arg="note"${readonly ? html` readonly` : ''}>${f.note || ''}</textarea></label>
  </div>`}</section>`;
}

function blockView(block, index, value, readonly, editingBlock) {
  const key = block.id || block._key;
  const peers = value.blocks.filter(row => row.section === block.section);
  const peerIndex = peers.indexOf(block);
  const image = value.source_images.includes(block.image_sha);
  return html`<article class="drf-block" data-key="${key}"><header><strong>${block.kind === 'text' ? '文字' : '图片'} ${index + 1}</strong>
    ${readonly ? '' : html`<div class="drf-block-actions">
      ${block.kind === 'text' ? button({ label: editingBlock === key ? '完成编辑' : '编辑文字', size: 'sm', action: 'create.draftEditBlock', arg: key }) : ''}
      <details class="drf-block-menu"><summary>更多</summary><div class="drf-block-menu__items">
        ${button({ label: '移动到上方', size: 'sm', action: 'create.draftMove', arg: `${key}|-1`, disabled: peerIndex === 0 })}
        ${button({ label: '移动到下方', size: 'sm', action: 'create.draftMove', arg: `${key}|1`, disabled: peerIndex === peers.length - 1 })}
        ${button({ label: '删除块', size: 'sm', variant: 'danger', action: 'create.draftRemoveBlock', arg: key })}
      </div></details></div>`}</header>
    ${readonly ? '' : html`<label class="drf-field">所属部分<select class="ui-select" data-change="create.draftBlockSection" data-arg="${key}">
      <option value="题目"${block.section === '题目' ? html` selected` : ''}>题目</option><option value="答案"${block.section === '答案' ? html` selected` : ''}>答案</option></select></label>`}
    ${block.kind === 'text' ? html`${editingBlock === key && !readonly ? html`<label class="drf-field">内容<textarea class="ui-textarea" rows="5" data-input="create.draftBlockText" data-arg="${key}">${block.text || ''}</textarea></label>` : ''}
      <div class="drf-md q-md" data-hash="${hashText(block.text || '')}">${raw(renderMd(block.text || ''))}</div>`
    : html`<div class="drf-block-image">${image ? block.box && (block.box.x !== 0 || block.box.y !== 0 || block.box.w !== 1 || block.box.h !== 1)
      ? html`<canvas data-draft-crop="${key}" data-morph="skip" aria-label="${block.section}裁图预览"></canvas>`
      : html`<img loading="lazy" src="${imageUrl(block.image_sha)}" alt="${block.section}图片区">`
      : html`<p class="drf-error">来源图片已取消关联</p>`}</div>
      <p class="drf-hint">${block.box ? (block.box.x === 0 && block.box.y === 0 && block.box.w === 1 && block.box.h === 1 ? '已选择整图' : '已选取局部区域') : '尚未框选，入库前请画框或使用整图'}</p>
      ${readonly ? '' : button({ label: '使用整图', size: 'sm', action: 'create.draftWhole', arg: key, disabled: !image })}
      <label class="drf-field">图片说明<input class="ui-input" data-input="create.draftBlockNote" data-arg="${key}" value="${block.note || ''}"${readonly ? html` readonly` : ''}></label>`}
  </article>`;
}

function blocksView(value, readonly, editingBlock) {
  return html`<div class="drf-blocks">
    ${['题目', '答案'].map(section => {
      const blocks = value.blocks.filter(block => block.section === section);
      return html`<section class="drf-section drf-review-${section === '题目' ? 'question' : 'answer'}"><div class="drf-section-head"><h3>${section}</h3><span>${blocks.length} 块</span></div>
        ${blocks.length ? each(blocks, block => block.id || block._key, (block, index) => blockView(block, index, value, readonly, editingBlock))
    : html`<p class="drf-hint">${section === '题目' ? '至少需要一个题目块。' : '可以没有答案。'}</p>`}
        ${readonly ? '' : html`<div class="drf-add">${button({ label: '添加文字', size: 'sm', action: 'create.draftAddText', arg: section })}
          ${value.source_images.length ? html`<select class="ui-select" data-draft-image="${section}" aria-label="${section}图片来源">
            ${value.source_images.map(sha => html`<option value="${sha}">${sha.slice(0, 10)}</option>`)}</select>
            ${button({ label: '添加图片', size: 'sm', action: 'create.draftAddImage', arg: section })}` : ''}</div>`}</section>`;
    })}</div>`;
}

function reviewChecksView(value) {
  const checks = reviewChecks(value);
  const pending = checks.filter(check => check.status !== 'ok').length;
  return html`<section class="drf-review-checks" aria-label="入库检查"><div class="drf-section-head"><h3>入库检查</h3>
    <span>${pending ? `${pending} 项待处理` : '可以入库'}</span></div>
    <ul>${checks.map(check => html`<li class="drf-check drf-check--${check.status}"><span aria-hidden="true">${check.status === 'ok' ? '✓' : '!'}</span><span>${check.label}</span><strong>${check.status === 'ok' ? '已确认' : '待核对'}</strong></li>`)}</ul>
  </section>`;
}

function reviewActions({ draft, dirty, busy, problem }) {
  const readonly = ['done', 'discarded'].includes(draft.status);
  if (readonly) return html`<footer class="drf-footer"><p class="drf-hint">此草稿的正文已锁定。${draft.status === 'done' && (draft.training_tasks || []).some(task => task.status === 'error') ? '训练登记失败，可重试。' : ''}</p>
    ${draft.status === 'done' && dirty ? button({ label: '保存训练框', variant: 'primary', action: 'create.draftSave', loading: busy }) : ''}
    ${draft.status === 'done' && (draft.training_tasks || []).some(task => task.status === 'error') ? button({ label: '重试训练登记', action: 'create.draftRetryTraining', disabled: busy }) : ''}</footer>`;
  return html`<footer class="drf-footer">
    ${button({ label: '暂存', action: 'create.draftSave', loading: busy, disabled: !dirty })}
    ${button({ label: '保存并入库，下一题', variant: 'primary', action: 'create.draftCommit', loading: busy, disabled: Boolean(problem) })}
    ${button({ label: '丢弃草稿', variant: 'danger', action: 'create.draftDiscard', disabled: busy })}
  </footer>`;
}

function reviewInspector(state, readonly, problem) {
  return html`<aside class="drf-review-inspector" aria-label="审核 Inspector"><div class="drf-inspector-title"><strong>审核信息</strong><span>${readonly ? '只读' : '可编辑'}</span></div>
    ${fieldsView(state.value, readonly || state.busy, state.fieldsEditing)}
    ${reviewChecksView(state.value)}
    ${reviewActions({ draft: state.draft, dirty: state.dirty, busy: state.busy, problem })}
  </aside>`;
}

function reviewWorkspace(state, readonly, problem) {
  return html`<div class="drf-review-workspace"><section class="drf-review-content"><div class="drf-content-head"><div><span class="drf-eyebrow">内容审核</span><h3>题目与答案解析</h3></div><span class="drf-hint">默认阅读模式</span></div>
    ${blocksView(state.value, readonly || state.busy, state.editingBlock)}</section>${reviewInspector(state, readonly, problem)}</div>`;
}

function sourceWorkspace(state, readonly, problem) {
  return html`<div class="drf-source-workspace"><section class="drf-source-content">${canvasPanel(state)}</section>
    <aside class="drf-source-inspector" aria-label="来源 Inspector">${sourceView(state.draft, state.value, readonly || state.busy)}
      ${reviewChecksView(state.value)}${reviewActions({ draft: state.draft, dirty: state.dirty, busy: state.busy, problem })}</aside>
  </div>`;
}

function detailView(state) {
  const { draft, value, detailLoaded, detailError, dirty, busy, message, conflict } = state;
  if (detailError) return html`<main class="drf-detail"><div class="drf-error" role="alert">读取草稿失败：${detailError}${button({ label: '重试', action: 'create.draftRetry' })}</div></main>`;
  if (!detailLoaded) return html`<main class="drf-detail"><p role="status">正在读取草稿…</p></main>`;
  if (!draft || !value) return html`<main class="drf-detail">${empty({ icon: 'inbox', title: '选择一份草稿', hint: '在左侧列表选择，核对后保存或通过。', bordered: true })}</main>`;
  const readonly = draft.status === 'done' || draft.status === 'discarded';
  const problem = readonly ? '' : commitProblem(value);
  const position = state.list.findIndex(row => row.id === draft.id);
  const total = state.list.length;
  const mode = state.workspaceMode || 'review';
  const tab = mode === 'source' ? 'source' : state.reviewTab;
  return html`<main class="drf-detail" data-review-tab="${tab}" data-workspace-mode="${mode}"><div class="drf-detail-head"><div class="drf-detail-title"><span class="drf-eyebrow">AI 草稿审核${draft.source_channel === 'mcp' ? ' · 来源：MCP' : ''}</span>
    ${draft.cause_verification === 'client_asserted' ? html`<p class="hint">错因由外部助手提供，待核对。${draft.cause_statement || ''}</p>` : ''}
      <p class="drf-id">${position >= 0 ? `第 ${position + 1}/${total} 题 · ` : ''}${draft.id} · 第 ${draft.revision ?? '?'} 版</p>
      <h2>${draftStatusLabel(draft.status)} ${dirty ? '· 未保存' : ''}</h2></div>
      <div class="drf-detail-actions"><div class="drf-review-nav">${button({ label: '上一题', size: 'sm', action: 'create.draftNavigate', arg: '-1', disabled: busy || position <= 0 })}
        ${button({ label: '下一题', size: 'sm', action: 'create.draftNavigate', arg: '1', disabled: busy || position < 0 || position >= total - 1 })}</div>
        <button type="button" class="drf-source-trigger ui-btn ui-btn--sm" data-action="create.draftToggleSource" aria-expanded="${mode === 'source' ? 'true' : 'false'}">${mode === 'source' ? '返回内容审核' : '来源对照 / 框选'}<span class="ui-btn__label"> · ${value.source_images.length} 张图</span></button></div></div>
    ${message ? html`<p class="drf-message" role="status">${message}
      ${conflict ? button({ label: '重新读取并放弃本地修改', size: 'sm', action: 'create.draftReloadDetail' }) : ''}</p>` : ''}
    ${draft.status === 'done' ? html`<p class="drf-success">${draft.question_available === false ? '已入库，题目当前不可用' : `已入库：${draft.uid || draft.question_id || '题目'}`}
      ${draft.uid && draft.question_available !== false ? button({ label: '查看题目', size: 'sm', action: 'create.draftQuestion' }) : ''}</p>` : ''}
    ${problem ? html`<p class="drf-review-problem" role="status">入库前需处理：${problem}</p>` : ''}
    <nav class="drf-review-tabs" aria-label="审核内容">
      ${[['question', '题目'], ['answer', '答案解析'], ['info', '信息'], ['source', '来源']].map(([key, label]) => button({ label, size: 'sm', action: 'create.draftReviewTab', arg: key, pressed: tab === key }))}
    </nav>
    ${mode === 'source' ? sourceWorkspace(state, readonly, problem) : reviewWorkspace(state, readonly, problem)}</main>`;
}

export function draftsView(state) {
  return html`<div class="drf">${listView(state)}${detailView(state)}</div>`;
}
