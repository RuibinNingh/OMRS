/** AI 草稿编辑值独立于收件箱；服务端 revision 是每次写入的并发边界。 */
export const DRAFT_STATUSES = Object.freeze(['pending', 'done', 'discarded']);
export const DRAFT_SECTIONS = Object.freeze(['题目', '答案']);
export const DRAFT_FIELDS = Object.freeze(['subject', 'category', 'difficulty', 'knowledge_points', 'labels', 'cause', 'note']);

export const draftStatusLabel = status => ({ cropping: '待框选', review: '待审核', done: '已入库', discarded: '已丢弃' })[status] || status || '未知';
export const draftPendingCount = counts => Number(counts?.cropping || 0) + Number(counts?.review || 0);
export const csvValues = text => [...new Set(String(text || '').split(/[,，\n]/).map(value => value.trim()).filter(Boolean))];
export const imageSha = image => typeof image === 'string' ? image : image?.sha256;
export const imageUrl = sha => `/api/drafts/image?sha=${encodeURIComponent(sha || '')}`;
export const sortDraftQueue = rows => [...rows].sort((a, b) => (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0)
  || (a.id < b.id ? 1 : a.id > b.id ? -1 : 0));

export function latestDetectResult(draft, activeJob, sha) {
  const jobs = [...(activeJob?.type === 'detect' ? [activeJob] : []), ...(draft?.jobs || [])];
  for (const job of jobs) {
    if (job.type !== 'detect') continue;
    const result = (job.result || []).find(row => row.sha === sha);
    if (result) return { job, result };
    if ((job.errors || []).some(row => row.sha === sha)) return { job, result: null };
    if (job === activeJob && ['queued', 'running'].includes(job.status)) return { job, result: null };
  }
  return null;
}

export function editValue(draft) {
  if (!draft) return null;
  return {
    fields: Object.fromEntries(DRAFT_FIELDS.map(key => [key, Array.isArray(draft[key]) ? [...draft[key]] : draft[key] ?? ''])),
    blocks: (draft.blocks || []).map(block => ({ ...block, box: block.box ? { ...block.box } : null })),
    source_images: (draft.source_images || []).map(imageSha).filter(Boolean),
  };
}

export function editTraining(draft) {
  return Object.fromEntries((draft?.training_tasks || []).map(task => [task.id,
    (task.boxes || []).map(box => ({ ...box, box: box.box ? { ...box.box } : null }))]));
}

export function trainingBoxPayload(draft, training, savedTraining) {
  const original = JSON.parse(savedTraining || '{}');
  return (draft.training_tasks || []).flatMap(task => {
    const boxes = training[task.id] || [];
    if (JSON.stringify(boxes) === JSON.stringify(original[task.id] || [])) return [];
    if (!boxes.length) return [{ task_id: task.id, box: null }];
    return boxes.map(row => ({ ...(row.id ? { id: row.id } : {}), task_id: task.id,
      section: row.section, box: row.box, box_origin: row.box_origin || 'manual',
      ...(row.ai_box ? { ai_box: row.ai_box } : {}) }));
  });
}

export function updatePayload(draft, value) {
  const fields = { ...value.fields, difficulty: Number(value.fields.difficulty) || 5,
    knowledge_points: [...value.fields.knowledge_points], labels: [...value.fields.labels] };
  const blocks = DRAFT_SECTIONS.flatMap(section => value.blocks.filter(block => block.section === section)).map(block => {
    const result = { section: block.section, kind: block.kind, note: block.note || '' };
    if (block.id) result.id = block.id;
    if (block.kind === 'text') result.text = block.text || '';
    else { result.image_sha = block.image_sha; result.box = block.box || null;
      result.box_origin = block.box_origin || null; result.ai_box = block.ai_box || null; }
    return result;
  });
  return { id: draft.id, revision: draft.revision, fields, blocks, source_images: [...value.source_images] };
}

/** 同一份校验供暂存、入库和界面定位使用；通过只表示格式完整。 */
export function draftIssue(value, includeBoxes = true) {
  if (!value.fields.subject?.trim() || !value.fields.category?.trim()) return {
    message: '请填写科目和分类', field: value.fields.subject?.trim() ? 'category' : 'subject' };
  const difficulty = Number(value.fields.difficulty);
  if (!Number.isInteger(difficulty) || difficulty < 1 || difficulty > 10) return { message: '难度须为 1 到 10 的整数', field: 'difficulty' };
  if (value.fields.knowledge_points.length > 8) return { message: '知识点最多 8 个', field: 'knowledge_points' };
  if (!value.blocks.some(block => block.section === '题目')) return { message: '至少需要一个题目块', section: '题目' };
  const text = value.blocks.find(block => block.kind === 'text' && !block.text?.trim());
  if (text) return { message: '文字块不能为空', blockKey: text.id || text._key };
  const image = value.blocks.find(block => block.kind === 'image' && (!block.image_sha || !value.source_images.includes(block.image_sha)));
  if (image) return { message: '图片块必须关联一张来源图', source: true };
  const unboxed = includeBoxes && value.blocks.find(block => block.kind === 'image' && !block.box);
  return unboxed ? { message: '图片块尚未框选，请手动画框或点「使用整图」并保存', blockKey: unboxed.id || unboxed._key } : null;
}

export const draftProblems = value => draftIssue(value, false)?.message || '';
export const commitProblem = value => draftIssue(value)?.message || '';

/** 新块放在同组末尾，或指定同组块之后；不改变其他块的身份。 */
export function insertBlock(blocks, row, afterKey = null) {
  if (!DRAFT_SECTIONS.includes(row.section)) return false;
  let index = -1;
  if (afterKey) {
    index = blocks.findIndex(block => (block.id || block._key) === afterKey && block.section === row.section);
    if (index < 0) return false;
  } else blocks.forEach((block, i) => { if (block.section === row.section) index = i; });
  blocks.splice(index < 0 ? blocks.length : index + 1, 0, row);
  return true;
}

export function moveBlockToSection(blocks, key, section) {
  const index = blocks.findIndex(block => (block.id || block._key) === key);
  if (index < 0 || !DRAFT_SECTIONS.includes(section) || blocks[index].section === section) return false;
  const [row] = blocks.splice(index, 1);
  row.section = section;
  return insertBlock(blocks, row);
}

export function moveBlock(blocks, key, step) {
  if (![-1, 1].includes(step)) return false;
  const index = blocks.findIndex(block => (block.id || block._key) === key);
  if (index < 0) return false;
  const peers = blocks.map((block, i) => ({ block, i })).filter(row => row.block.section === blocks[index].section);
  const position = peers.findIndex(row => row.i === index);
  const other = peers[position + step];
  if (!other) return false;
  [blocks[index], blocks[other.i]] = [blocks[other.i], blocks[index]];
  return true;
}
