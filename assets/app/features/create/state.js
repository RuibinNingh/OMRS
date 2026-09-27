/** 录入题目工作区的导航定义；前三项按上传到写入题库的顺序排列。 */
export const STAGES = Object.freeze([
  { id: 'upload', title: '上传', hint: '手机 / 电脑投进收件箱', number: '1', count: 'ib-c-pending', countLabel: '待处理' },
  { id: 'process', title: '处理', hint: '框题目 / 答案，转文本或留图', number: '2', count: 'ib-c-boxed', countLabel: '已框选' },
  { id: 'create', title: '录入', hint: '核对题卡，写入题库', number: '3', count: 'ib-c-ready', countLabel: '待创建' },
  { id: 'train', title: 'AI 训练', hint: '框选与转文本的人工数据', icon: 'sparkle' },
  { id: 'quick', title: '快速录入', hint: '单题表单，剪贴板一贴即录', icon: 'edit' },
]);

export function stageOf(value) {
  return STAGES.some(stage => stage.id === value) ? value : 'upload';
}

export function newQuickState() {
  return {
    form: { subject: '', category: '', difficulty: '5', related: '', question: '', answer: '', cause: '', note: '' },
    images: { q: [], a: [] }, labels: [], target: 'q', nextImageId: 0, result: null,
  };
}

export function createPayload(state) {
  const form = state.form;
  const subject = String(form.subject || '').trim();
  const category = String(form.category || '').trim();
  if (!subject || !category) return { ok: false, error: '请填写科目和分类' };
  return { ok: true, data: {
    subject, category, difficulty: Number(form.difficulty) || 5,
    note: String(form.note || '').trim(),
    related_tags: String(form.related || '').split(/[,，]/).map(tag => tag.trim()).filter(Boolean),
    labels: [...new Set(state.labels)],
    question_text: String(form.question || '').trim(), answer_text: String(form.answer || '').trim(),
    cause: String(form.cause || '').trim(),
    question_images: state.images.q.map(image => ({ data: image.dataUrl })),
    answer_images: state.images.a.map(image => ({ data: image.dataUrl })),
  } };
}

export function mergeClassification(form, result) {
  const next = { ...form };
  if (!String(next.subject || '').trim() && result.subject) next.subject = String(result.subject);
  if (!String(next.category || '').trim() && result.category) next.category = String(result.category);
  if (result.difficulty != null && Number(result.difficulty) >= 1 && Number(result.difficulty) <= 10) {
    next.difficulty = String(result.difficulty);
  }
  const tags = String(next.related || '').split(/[,，]/).map(tag => tag.trim()).filter(Boolean);
  for (const tag of result.knowledge_tags || []) if (tag && !tags.includes(tag)) tags.push(tag);
  next.related = tags.join(', ');
  return next;
}

export function afterCreate(state) {
  return { ...state, form: { ...state.form, question: '', answer: '', cause: '' }, images: { q: [], a: [] } };
}
