/** AI 训练工作区：进入时读数据集统计与框选策略；策略直接读写 /api/config 的 inbox_* 键（与「设置」共用）。 */
import { morph } from '../../core/dom.js';
import { get, post } from '../../core/api.js';
import { confirm } from '../../ui/dialog.js';
import { notify } from './inbox.js';
import { statsModel, policyForm, policyPayload, cleanupSummary } from './train-state.js';
import { trainView } from './train-view.js';

const view = { stats: null, loading: false, error: '', format: 'omrs_jsonl', policy: null, policyError: '', saving: false, message: null, annotate: null };

export function createTrain(root) {
  const host = root.querySelector('#ib-stage-train');
  let alive = true;
  let token = 0;

  function paint() {
    if (!alive) return;
    morph(host, trainView({ ...view, model: statsModel(view.stats) }));
  }

  async function loadStats() {
    const mine = ++token;
    view.loading = !view.stats; view.error = ''; paint();
    const result = await get('/api/inbox/dataset/stats');
    if (!alive || mine !== token) return;
    view.loading = false;
    if (result.ok) view.stats = result.data || {};
    else view.error = `读取数据集统计失败：${result.error?.message || '未知错误'}`;
    paint();
  }

  async function loadPolicy() {
    view.policyError = '';
    const result = await get('/api/config');
    if (!alive) return;
    if (result.ok) view.policy = policyForm(result.data || {});
    else view.policyError = `读取策略配置失败：${result.error?.message || '未知错误'}`;
    paint();
  }

  async function loadAnnotate() {
    const result = await get('/api/annotate/stats');
    if (!alive) return;
    view.annotate = result.ok ? result.data || null : null;
    paint();
  }

  function enter() { view.message = null; loadStats(); loadPolicy(); loadAnnotate(); }

  function setPolicy(key, event) {
    if (!view.policy) return;
    const target = event?.target;
    view.policy[key] = key === 'upload' ? !!target?.checked : String(target?.value ?? '');
    view.message = null;
    paint();
  }

  async function save() {
    if (!view.policy || view.saving) return;
    view.saving = true; view.message = null; paint();
    const result = await post('/api/config', policyPayload(view.policy));
    view.saving = false;
    if (!alive) return;
    view.message = result.ok ? { ok: true, text: '已保存，立即生效' } : { ok: false, text: result.error?.message || '保存失败' };
    paint();
  }

  async function cleanup(crops) {
    if (crops && !await confirm('清空裁剪缓存？（可重建，不影响原图与标注）', { danger: true })) return;
    const result = await post('/api/inbox/cleanup', { crops: !!crops });
    if (!result.ok) { notify(`清理失败：${result.error?.message || '未知错误'}`, 'warn'); return; }
    notify(cleanupSummary(result.data || {}, crops));
    loadStats();
  }

  paint();

  return {
    enter, save, cleanup,
    refresh: enter,
    format(event) { view.format = String(event?.target?.value || 'omrs_jsonl'); paint(); },
    policy: setPolicy,
    dispose() { alive = false; },
  };
}
