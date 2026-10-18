/** 作业帮题卡状态及迟到 AI 结果的合并规则；不保存账号凭据。 */
export const ROLES = ['question', 'answer'];
export const MOBILE_LAYOUT_VERSION = 'mobile-360-v2';
export function newZybState() {
  return { session: null, sessionError: '', accountPanel: '', camera: { on: false, pending: false, message: '摄像头未开启' },
    sourceMode: 'upload', file: null, fileUrl: '', search: null, selected: null, region: null, render: null, role: 'question', zoom: 'fit', showHtml: false,
    boxes: {}, showBoxes: true, adjusting: false, drafts: {}, renderIds: {}, savedLocations: {},
    sections: { question: { mode: 'image', text: '', reason: '尚未识别，按完整图片保存' }, answer: { mode: 'image', text: '', reason: '尚未识别，按完整图片保存' } },
    versions: { question: 0, answer: 0 }, form: { subject: '', category: '', difficulty: '5', related: '', cause: '' },
    labels: [], busy: '', job: null, message: '', error: false, history: [], result: null, qr: null, dirty: false };
}
export function searchRegions(state) {
  if (state.search?.regions?.length) return state.search.regions;
  const groups = new Map();
  for (const candidate of state.search?.candidates || []) {
    const index = Number(candidate.location) || 0;
    if (!groups.has(index)) groups.set(index, { index, candidate_indices: [] });
    groups.get(index).candidate_indices.push(candidate.index);
  }
  return [...groups.values()];
}
export const regionBounds = (state, index = state.region) => state.boxes[index] || searchRegions(state).find(row => row.index === index)?.bounds;
export const candidateKey = (state, index = state.selected) => `${state.search?.id}:${index == null ? `source-${state.region}` : index}`;
export function stashCard(state) {
  if (!state.render) return;
  state.drafts[state.render.id] = structuredClone({ form: state.form, labels: state.labels, sections: state.sections, versions: state.versions, dirty: state.dirty });
}
export function bindCard(state, record) {
  bindRender(state, record);
  const saved = state.drafts[record.id];
  if (saved && !state.result) Object.assign(state, structuredClone(saved));
  else if (saved) ROLES.forEach(role => { state.sections[role].view = saved.sections?.[role]?.view === 'source' ? 'source' : 'preview'; });
  if (state.search?.id === record.search_id) {
    state.renderIds[candidateKey(state, record.candidate?.index)] = record.id;
    if (state.result && Number.isInteger(record.candidate?.location)) state.savedLocations[record.candidate.location] = state.result.uid;
  }
}
export function canRegenerate(state) {
  const record = state.render;
  return record?.status === 'ready' && record.source_kind !== 'crop' && !record.commit &&
    record.layout?.version !== MOBILE_LAYOUT_VERSION && state.search?.id === record.search_id &&
    Number.isInteger(state.selected) && record.candidate?.index === state.selected;
}
export function bindRegeneratedCard(state, record, previousId) {
  if (state.render?.id !== previousId || state.render.commit || record.search_id !== state.search?.id ||
      record.candidate?.index !== state.selected) return false;
  // 完成时取最新人工内容，连重新生成期间的编辑一起保留；旧题卡仍可从历史恢复。
  stashCard(state);
  const draft = state.drafts[previousId];
  bindCard(state, record);
  Object.assign(state, structuredClone(draft));
  stashCard(state);
  return true;
}
export function bindSearch(state, record) {
  const same = record && state.search?.id === record.id;
  state.search = record; state.region = searchRegions(state)[0]?.index ?? null;
  state.selected = null; state.render = null; state.result = null; state.dirty = false;
  if (!same) { state.boxes = {}; state.renderIds = {}; state.savedLocations = {}; state.drafts = {}; }
  state.adjusting = false;
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
