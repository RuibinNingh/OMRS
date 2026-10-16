/** 刷新恢复原图、题框、逐候选人工内容与在途作业；每次读取都校验挂载代次。 */
import { bindCard, searchRegions } from './zyb-state.js';
export const WORKSPACE_KEY = 'omrs-zuoyebang-workspace';

export async function restoreWorkspace(state, { read, current }) {
  let saved;
  try { saved = JSON.parse(sessionStorage.getItem(WORKSPACE_KEY) || 'null'); } catch (_) { return null; }
  if (!saved) return null;
  const search = saved.search_id ? await read(saved.search_id) : null;
  if (!current()) return null;
  const record = saved.render_id ? await read(saved.render_id) : null;
  if (!current()) return null;
  Object.assign(state, { search, selected: Number.isInteger(saved.selected) ? saved.selected : null,
    sourceMode: saved.sourceMode === 'camera' ? 'camera' : 'upload',
    region: Number.isInteger(saved.region) ? saved.region : null, boxes: saved.boxes || {},
    drafts: saved.drafts || {}, renderIds: saved.renderIds || {}, savedLocations: saved.savedLocations || {} });
  if (!searchRegions(state).some(row => row.index === state.region)) state.region = searchRegions(state)[0]?.index ?? null;
  if (record) {
    bindCard(state, record);
    // 兼容拆页前仅保存一张题卡的会话。
    if (!state.result && saved.sections && !saved.drafts?.[record.id]) {
      Object.assign(state, { sections: saved.sections, form: saved.form, labels: saved.labels || [], dirty: !!saved.dirty });
      if (saved.versions) state.versions = saved.versions;
    }
  }
  if (saved.job?.id) { state.job = saved.job; state.busy = saved.job.type; }
  return saved.jobContext || (state.job?.type === 'render' ? { render: { search_id: search?.id, candidate_index: state.selected } } : null);
}
