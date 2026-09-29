/** 面板数据唯一所有者；失败保留最近一次可读指标。 */
import { mergeMetrics } from './state.js';
export function createTrainStore({ api, changed = () => {} }) {
  const state = { overview: null, detail: null, service: null, loading: true, error: '', selected: null, busy: false };
  let alive = true, detailRequest = 0;
  async function detail(name, force = false) {
    const request = ++detailRequest;
    const latest = state.overview?.runs.find(row => row.name === name);
    if (!force && state.detail?.name === name && state.detail.status?.epoch === latest?.status?.epoch && state.detail.status?.state === latest?.status?.state) return;
    const result = await api.get(`/api/trainpanel/run?name=${encodeURIComponent(name)}`);
    if (!alive || request !== detailRequest) return;
    if (result.ok) {
      const previous = state.detail?.name === name ? state.detail : null;
      const next = result.data;
      if (previous && next.errors?.status) next.status = previous.status;
      if (previous && next.errors?.metrics) next.metrics = previous.metrics;
      else if (previous) next.metrics = mergeMetrics(previous.metrics || [], next.metrics || []);
      if (previous && next.errors?.evaluation) next.evaluation = previous.evaluation;
      state.detail = next;
    } else state.error = result.error?.message || '读取实验失败';
    changed(state);
  }
  async function refresh(force = false) {
    if (state.busy) return;
    state.busy = true;
    const [result, service] = await Promise.all([api.get('/api/trainpanel/overview'), api.get('/api/trainpanel/service')]);
    if (!alive) return;
    state.loading = false; state.busy = false;
    if (result.ok) {
      const next = result.data;
      // 临时读失败保留最后一次进度，继续轮询，错误仍在对应块显示。
      next.runs = next.runs.map(run => {
        const previous = state.overview?.runs.find(row => row.name === run.name);
        return run.error && previous?.status ? { ...run, status: previous.status } : run;
      });
      const previousLatest = next.runs.find(run => run.name === state.overview?.latest?.name);
      if (previousLatest?.error && Date.parse(previousLatest.status?.started_at) >= Date.parse(next.latest?.status?.started_at || '1970-01-01')) next.latest = previousLatest;
      else if (next.latest) next.latest = next.runs.find(run => run.name === next.latest.name) || next.latest;
      state.overview = next; state.error = '';
    }
    else state.error = result.error?.message || '读取训练目录失败';
    state.service = service.ok ? service.data : { state: 'offline', message: service.error?.message };
    changed(state);
    const name = state.selected || state.overview?.latest?.name;
    if (name) await detail(name, force);
  }
  return { state, refresh, async select(name) { state.selected = name; await detail(name, true); },
    dispose() { alive = false; } };
}
