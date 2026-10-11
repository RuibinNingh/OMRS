/** 作业帮题卡状态及迟到 AI 结果的合并规则；不保存账号凭据。 */
export const ROLES = ['question', 'answer'];
export function newZybState() {
  return { session: null, sessionError: '', accountPanel: '', camera: { on: false, pending: false, message: '摄像头未开启' },
    file: null, fileUrl: '', search: null, selected: 0, render: null, role: 'question', zoom: 'fit', showHtml: false,
    sections: { question: { mode: 'image', text: '', reason: '尚未识别，按完整图片保存' }, answer: { mode: 'image', text: '', reason: '尚未识别，按完整图片保存' } },
    versions: { question: 0, answer: 0 }, form: { subject: '', category: '', difficulty: '5', related: '', cause: '' },
    labels: [], busy: '', job: null, message: '', error: false, history: [], result: null, qr: null, dirty: false };
}
export function bindRender(state, record) {
  state.render = record;
  state.result = record.commit?.result || null;
  state.sections = Object.fromEntries(ROLES.map(role => [role, {
    mode: record.images[role]?.empty ? 'none' : 'image', text: '', reason: record.images[role]?.empty ? '上游未返回答案' : '尚未识别，按完整图片保存',
  }]));
  state.versions = { question: state.versions.question + 1, answer: state.versions.answer + 1 };
  mergeExtraction(state, record, extractionSnapshot(state));
  if (record.commit?.payload) {
    const saved = record.commit.payload;
    Object.assign(state.form, { subject: saved.subject, category: saved.category, difficulty: String(saved.difficulty),
      related: saved.related_tags.join(', '), cause: saved.cause });
    state.labels = saved.labels;
    ROLES.forEach(role => Object.assign(state.sections[role], saved.sections[role]));
  }
  state.dirty = false;
}
export const extractionSnapshot = state => ({ id: state.render?.id, versions: { ...state.versions } });
export function mergeExtraction(state, record, snapshot) {
  if (state.render?.id !== record.id || snapshot.id !== record.id) return false;
  state.render = record;
  for (const role of ROLES) {
    if (state.versions[role] !== snapshot.versions[role]) continue;
    const result = record.extraction?.[role];
    if (!result) continue;
    Object.assign(state.sections[role], { mode: result.mode, text: result.text || '', reason: result.reason || '' });
  }
  return true;
}
export function commitPayload(state) {
  if (!state.render || state.render.status !== 'ready') throw new Error('请先完成后端渲染');
  if (!state.form.subject.trim() || !state.form.category.trim()) throw new Error('请填写科目和分类');
  if (ROLES.some(role => state.sections[role].mode === 'text' && !state.sections[role].text.trim())) throw new Error('文本正文不能为空，请补录或保留完整图片');
  return { render_id: state.render.id, form: { ...state.form, related_tags: state.form.related.split(/[,，]/).map(value => value.trim()).filter(Boolean), labels: state.labels },
    sections: Object.fromEntries(ROLES.map(role => [role, { mode: state.sections[role].mode, text: state.sections[role].text }])) };
}
