/** 草稿来源工作台：图片选择、正文／训练框与来源维护。 */
import { html, each } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { imageSha, imageUrl, latestDetectResult } from './drafts-state.js';
import { reviewActions } from './drafts-review.js';

const trainingStatus = status => ({ pending: '待框选', ready: '已框选', registered: '已登记', error: '登记失败' })[status] || '待创建';
const boxOrigin = origin => ({ original: '完整原图', manual: '手动', ai: 'AI 建议', ai_edited: 'AI 建议后人工调整' })[origin] || '手动';

export function sourceView(draft, value, readonly) {
  const source = draft.source_images || [];
  const known = new Map([...source, ...(draft.conversation_images || [])].map(image => [imageSha(image), image]));
  const attached = value.source_images.map(sha => known.get(sha) || { sha256: sha });
  const available = (draft.conversation_images || []).filter(image => !value.source_images.includes(imageSha(image)));
  return html`<section class="drf-sources"><div class="drf-section-head"><h3>来源截图</h3><span>${attached.length} 张</span></div>
    ${draft.sources_complete === false ? html`<p class="drf-hint" role="status">旧草稿的来源未完整恢复，请核对并从本次对话截图补关联。</p>` : ''}
    ${attached.length ? html`<div class="drf-image-grid">${each(attached, image => imageSha(image), image => html`
      <figure class="drf-source" data-key="${imageSha(image)}"><button type="button" class="drf-source__preview" data-action="ai-review.draftPreviewSource" data-arg="${imageSha(image)}" aria-label="预览来源截图 ${image.ref || imageSha(image)?.slice(0, 8)}"><img loading="lazy" src="${imageUrl(imageSha(image))}" alt="来源截图 ${image.ref || imageSha(image)?.slice(0, 8)}"></button>
        <figcaption>${image.ref || imageSha(image)?.slice(0, 10)} · ${image.width && image.height ? `${image.width}×${image.height}` : '原图'}
        ${(draft.training_tasks || []).some(task => task.image_sha === imageSha(image) && task.force_crop && task.status !== 'registered')
          ? html`<small>独立训练框待核对；不影响题目入库</small>` : ''}
        ${readonly ? '' : draft.source_channel === 'mcp' && source.some(row => imageSha(row) === imageSha(image))
          ? html`<small>MCP 完整原图保留</small>`
          : button({ label: '取消关联', size: 'sm', action: 'ai-review.draftSourceRemove', arg: imageSha(image) })}</figcaption>
      </figure>`)}</div>` : html`<p class="drf-hint">尚未关联来源截图。</p>`}
    ${!readonly && available.length ? html`<div class="drf-source-add"><label for="drf-source-select">补关联本次对话截图</label>
      <select id="drf-source-select" class="ui-select"><option value="">请选择</option>${available.map(image => html`<option value="${imageSha(image)}">${image.ref || imageSha(image)?.slice(0, 10)} · ${image.width || '?'}×${image.height || '?'}</option>`)}</select>
      ${button({ label: '关联', size: 'sm', action: 'ai-review.draftSourceAdd' })}</div>` : ''}
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
      ${button({ label: mode === 'training' ? '采用为训练框' : '采用到当前图片区块', size: 'sm', action: 'ai-review.draftAcceptCandidate',
        arg: String(index), disabled: busy || job.revision !== revision || (readonly && mode !== 'training') || (mode === 'training' && trainingReadonly) })}</div>`)}</div>
  </div>`;
  if (result.status === 'applied') return result.applied_blocks?.length
    ? html`<p class="drf-hint" role="status">AI 已填入 ${result.applied_blocks.length} 个明确匹配的正文框，请核对后继续。</p>`
    : html`<p class="drf-hint" role="status">AI 已填入独立训练框；正文保持只读，训练登记仍受来源图开关控制。</p>`;
  if (result.status === 'skipped') return html`<p class="drf-hint" role="status">AI 框选已跳过：${result.reason || '请手动画框。'}</p>`;
  if (result.status === 'conflict') return html`<p class="drf-hint" role="status">AI 框选结果与草稿版本冲突，未修改当前框；请核对后重试。</p>`;
  return '';
}

export function canvasPanel({ draft, value, training, canvasSha, canvasMode, selectedBlock, drawSection, busy, job }) {
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
  return html`<section class="drf-canvas"><div class="drf-section-head"><h3>原图与框选</h3><span>${images.length} 张来源图片</span></div>
    <div class="drf-canvas-tabs" role="group" aria-label="来源图">
      ${images.map((image, index) => html`<button type="button" class="drf-canvas-image" data-action="ai-review.draftCanvasImage"
        data-arg="${imageSha(image)}" aria-pressed="${String(sha === imageSha(image))}" aria-label="选择来源图 ${image.ref || index + 1}">
        <img loading="lazy" src="${imageUrl(imageSha(image))}" alt=""><span><strong>${image.ref || `来源图 ${index + 1}`}</strong><small>${image.width} × ${image.height}</small></span></button>`)}
    </div>
    <div class="drf-canvas-meta"><span>${current.ref || sha.slice(0, 10)} · ${current.width}×${current.height}</span>
      ${current.inbox_item_id ? html`<span>训练图已登记</span>` : button({ label: trainingOn ? '参与训练：开' : '参与训练：关', size: 'sm',
        action: 'ai-review.draftTrainToggle', arg: sha, disabled: busy })}
      ${!current.inbox_item_id && trainingOn ? html`<small>该图片的训练开关由同图草稿共享。</small>` : ''}
      ${task?.force_crop && task.status !== 'registered' ? html`<small>这张图有独立训练框任务；可以先入库，再补标。</small>` : ''}
    </div>
    <div class="drf-canvas-tabs" role="group" aria-label="框选用途">
      ${button({ label: '题目正文', size: 'sm', action: 'ai-review.draftCanvasMode', arg: 'body', pressed: canvasMode !== 'training' })}
      ${trainingAvailable ? button({ label: '独立训练框', size: 'sm', action: 'ai-review.draftCanvasMode', arg: 'training', pressed: canvasMode === 'training' }) : ''}
      ${canDetect ? button({ label: 'AI 框选', size: 'sm', action: 'ai-review.draftDetect', arg: sha }) : ''}
    </div>
    ${canvasMode === 'training' && trainingAvailable ? html`<div class="drf-canvas-tools">
      <span>训练任务：${trainingStatus(task?.status)}${task?.error ? ` · ${task.error}` : ''}</span>
      ${button({ label: '画题目框', size: 'sm', action: 'ai-review.draftDrawSection', arg: '题目', pressed: drawSection !== '答案', disabled: trainReadonly })}
      ${button({ label: '画答案框', size: 'sm', action: 'ai-review.draftDrawSection', arg: '答案', pressed: drawSection === '答案', disabled: trainReadonly })}
      <small>训练框独立于正文；题目入库后仍可补标。${!trainingOn ? '当前未开启参与训练，保存标注不会登记数据集。' : ''}</small></div>`
    : html`<div class="drf-canvas-tools"><label for="drf-canvas-block">当前图片区块</label>
      <select id="drf-canvas-block" class="ui-select" data-change="ai-review.draftCanvasBlock"${bodyReadonly ? html` disabled` : ''}>
        <option value="">选择要框选的图片块</option>${bodyBlocks.map((row, index) => html`<option value="${row.id || row._key}"${(row.id || row._key) === selectedBlock ? html` selected` : ''}>${row.section}图片 ${index + 1}${row.box ? ' · 已框' : ' · 待框'}</option>`)}</select>
      ${selected && !bodyReadonly ? button({ label: '整图', size: 'sm', action: 'ai-review.draftWhole', arg: selected.id || selected._key }) : ''}
      <small>${bodyBlocks.length ? '选择图片块后，在图上画框、拖动或拉动边角。'
        : draft.status === 'done' ? '正文已入库且只读；可切换独立训练框继续标注来源图。'
          : '添加题目或答案图片后可框选配图；独立训练框不影响正文。'}</small></div>`}
    ${canvasMode !== 'training' && !bodyReadonly ? html`<div class="drf-canvas-add">
      ${button({ label: '添加题目图片', icon: 'plus', size: 'sm', variant: 'ghost', action: 'ai-review.draftAddSourceImage', arg: '题目' })}
      ${button({ label: '添加答案图片', icon: 'plus', size: 'sm', variant: 'ghost', action: 'ai-review.draftAddSourceImage', arg: '答案' })}</div>` : ''}
    <div class="drf-canvas-wrap"><div class="ib-stage-img" id="drf-stage-img" data-morph="skip"></div></div>
    <p class="drf-hint"><span id="drf-canvas-file"></span><span id="drf-canvas-zoom"></span> · 鼠标或触摸画框、移动和缩放。</p>
    ${canvasMode !== 'training' && !bodyReadonly ? html`<p class="drf-canvas-sync" role="status">${selected?.box ? '选区已同步到正文配图；暂存或入库后保存。' : '画框后实时预览到正文，完整原图保留。'}</p>` : ''}
    ${detectPanel(detected, canvasMode, draft.status === 'done', busy, draft.revision, trainReadonly)}
    ${canvasMode === 'training' && trainingAvailable ? html`<div class="drf-training-boxes">
      ${boxes.map(box => html`<div class="drf-training-box" data-key="${box.id || box._key}"><span>${box.section}框 · ${boxOrigin(box.box_origin)}</span>
        ${trainReadonly ? '' : html`<select class="ui-select" data-change="ai-review.draftTrainingSection" data-arg="${task.id}|${box.id || box._key}">
          <option value="题目"${box.section === '题目' ? html` selected` : ''}>题目</option><option value="答案"${box.section === '答案' ? html` selected` : ''}>答案</option></select>
          ${button({ label: '删除框', size: 'sm', variant: 'danger', action: 'ai-review.draftTrainingRemove', arg: `${task.id}|${box.id || box._key}` })}`}</div>`)}
      ${!boxes.length ? html`<p class="drf-hint">尚无训练框。画框后点「保存」登记标注。</p>` : ''}</div>` : ''}
    ${canvasMode !== 'training' && selected?.box && !bodyReadonly ? html`<div class="drf-canvas-tools">
      ${button({ label: '删除当前框', size: 'sm', variant: 'danger', action: 'ai-review.draftClearBox', arg: selected.id || selected._key })}
      ${button({ label: job ? '正在转文字…' : '转为文字', size: 'sm', action: 'ai-review.draftExtract', arg: selected.id || selected._key,
        disabled: busy || Boolean(job) || !selected.id })}
      ${!selected.id ? html`<small>先保存新图片区块，再转文字。</small>` : ''}</div>` : ''}
    ${job ? html`<p class="drf-message" role="status">${job.type === 'detect' ? 'AI 框选' : '转文字'}任务：${job.status === 'queued' ? '排队中' : '处理中'} · ${job.processed || 0}/${job.total || 1}</p>` : ''}
  </section>`;
}

export function sourceWorkspace(state, readonly) {
  return html`<div class="drf-source-workspace"><section class="drf-source-content">${canvasPanel(state)}</section>
    <aside class="drf-source-inspector" aria-label="来源 Inspector">${sourceView(state.draft, state.value, readonly || state.busy)}
      ${reviewActions(state)}</aside>
  </div>`;
}
