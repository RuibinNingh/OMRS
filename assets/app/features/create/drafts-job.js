/** 草稿转文字与 AI 框选作业轮询；隐藏页面暂停，终态响应也直接完成同步。 */
import { get } from '../../core/api.js';
import { setDraftActivity } from '../../domain/drafts.js';

export function createDraftJobPolling(root, state, { isAlive, loadDetail, paint, responseError }) {
  let timer = null;
  let activity = null;
  function stop() {
    if (timer) clearTimeout(timer);
    timer = null;
    if (activity) setDraftActivity(activity, false);
    activity = null;
    state.job = null;
  }
  async function finish(job, latest) {
    const draftId = state.draft?.id;
    stop();
    if (job.type === 'detect') {
      const rows = latest.result || [];
      if (['done', 'error'].includes(latest.status) && !state.dirty) await loadDetail(draftId, { force: true });
      if (!isAlive() || state.draft?.id !== draftId || state.job) return;
      if (latest.status === 'conflict') state.message = 'AI 框选结果与草稿新版本冲突，未写入；请核对后重试。';
      else if (latest.status === 'interrupted') state.message = 'AI 框选任务被中断，可重新发起。';
      else if (state.dirty) state.message = 'AI 框选已返回，本地仍有未保存修改；请重新读取后核对候选。';
      else if (latest.status === 'error') {
        const reason = latest.errors?.[0]?.error || latest.errors?.[0]?.msg || '检测服务未返回可用结果';
        state.message = `AI 框选失败：${reason}。可手动画框或重试。`;
      } else if (rows.some(row => row.status === 'suggested')) state.message = 'AI 框选有候选待核对；可明确选择候选或手动画框。';
      else if (rows.some(row => row.status === 'applied')) state.message = 'AI 框选已填入明确匹配的框；请核对后继续。';
      else state.message = `AI 框选已跳过：${rows.map(row => row.reason).filter(Boolean).join('；') || '请手动画框。'}`;
      paint(); return;
    }
    if (latest.status === 'done') {
      if (!state.dirty) await loadDetail(draftId, { force: true });
      if (!isAlive() || state.draft?.id !== draftId || state.job) return;
      state.message = state.dirty ? '转文字完成；当前有未保存修改，请重新读取后核对结果。' : '转文字完成';
    } else if (latest.status === 'conflict') {
      state.message = '转文字结果与草稿新版本冲突，未写入；请核对后重新读取。';
    } else if (latest.status === 'interrupted') {
      state.message = '转文字任务被中断，原图片区块保留；请重新提交。';
    } else {
      const reason = latest.errors?.[0]?.msg || latest.errors?.[0]?.error || latest.error || latest.status;
      const partial = latest.status === 'error' && (latest.result || []).some(row => row.status === 'done');
      if (partial && !state.dirty) await loadDetail(draftId, { force: true });
      if (!isAlive() || state.draft?.id !== draftId || state.job) return;
      state.message = partial
        ? `部分转文字成功，其余未完成：${reason}。${state.dirty ? '本地有未保存修改，请重新读取后核对服务端结果。' : '已同步成功的文字块。'}`
        : `转文字未完成：${reason}。原图片区块已保留。`;
    }
    paint();
  }
  function start(job) {
    stop();
    if (!job) return;
    state.job = job;
    if (!['queued', 'running'].includes(job.status)) { void finish(job, job); return; }
    activity = `${job.type}:${state.draft.id}`;
    setDraftActivity(activity, true);
    const poll = async () => {
      if (!isAlive() || state.job?.id !== job.id) return;
      if (root.ownerDocument.hidden) { timer = setTimeout(poll, 1500); return; }
      const result = await get(`/api/drafts/job?id=${encodeURIComponent(job.id)}`);
      if (!isAlive() || state.job?.id !== job.id) return;
      if (!result.ok || !result.data?.job) {
        state.message = `读取${job.type === 'detect' ? 'AI 框选' : '转文字'}任务失败：${responseError(result)}`;
        stop(); paint(); return;
      }
      const latest = result.data.job;
      state.job = latest;
      if (['queued', 'running'].includes(latest.status)) { paint(); timer = setTimeout(poll, 1200); return; }
      await finish(job, latest);
    };
    timer = setTimeout(poll, 1200);
    paint();
  }
  return { start, stop };
}
