/** 草稿转文字作业轮询；隐藏页面暂停，结束后只重读无本地改动的草稿。 */
import { get } from '../../core/api.js';
import { setDraftActivity } from '../../domain/drafts.js';

export function createDraftJobPolling(root, state, { isAlive, loadDetail, paint, responseError }) {
  let timer = null;
  function stop() {
    if (timer) clearTimeout(timer);
    timer = null;
    if (state.draft?.id) setDraftActivity(`extract:${state.draft.id}`, false);
    state.job = null;
  }
  function start(job) {
    stop();
    if (!job || !['queued', 'running'].includes(job.status)) return;
    state.job = job;
    setDraftActivity(`extract:${state.draft.id}`, true);
    const poll = async () => {
      if (!isAlive() || !state.job || state.job.id !== job.id) return;
      if (root.ownerDocument.hidden) { timer = setTimeout(poll, 1500); return; }
      const result = await get(`/api/drafts/job?id=${encodeURIComponent(job.id)}`);
      if (!isAlive() || state.job?.id !== job.id) return;
      if (!result.ok || !result.data?.job) {
        state.message = `读取转文字任务失败：${responseError(result)}`; stop(); paint(); return;
      }
      const latest = result.data.job;
      state.job = latest;
      if (['queued', 'running'].includes(latest.status)) { paint(); timer = setTimeout(poll, 1200); return; }
      stop();
      if (latest.status === 'done') {
        if (!state.dirty) await loadDetail(state.selectedId, { force: true });
        state.message = state.dirty ? '转文字完成；当前有未保存修改，请重新读取后核对结果。' : '转文字完成';
      } else if (latest.status === 'conflict') {
        state.message = '转文字结果与草稿新版本冲突，未写入；请核对后重新读取。';
      } else if (latest.status === 'interrupted') {
        state.message = '转文字任务被中断，原图片区块保留；请重新提交。';
      } else {
        const reason = latest.errors?.[0]?.msg || latest.errors?.[0]?.error || latest.error || latest.status;
        const partial = latest.status === 'error' && (latest.result || []).some(row => row.status === 'done');
        if (partial && !state.dirty) await loadDetail(state.selectedId, { force: true });
        state.message = partial
          ? `部分转文字成功，其余未完成：${reason}。${state.dirty ? '本地有未保存修改，请重新读取后核对服务端结果。' : '已同步成功的文字块。'}`
          : `转文字未完成：${reason}。原图片区块已保留。`;
      }
      paint();
    };
    timer = setTimeout(poll, 1200);
    paint();
  }
  return { start, stop };
}
