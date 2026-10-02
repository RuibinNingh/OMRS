/** 调参等待完整重放；断连后只按有效参数和发布版本核验结果。 */
import { get, post } from '../../core/api.js';
import { configSavedStatus } from '../../core/config-status.js';
import { reloadData } from '../../domain/data.js';
import { TUNING_FIELDS, readTuning, tuningMatches, recalculationText } from './tuning-state.js';

export function createTuning(root, { read = get, write = post, reload = reloadData } = {}) {
  const el = id => root.querySelector(`#${id}`);
  let alive = true;
  let busy = false;
  let ready = false;
  let cfg = null;
  let pending = null;
  const status = (text, tone = '') => {
    if (!alive) return;
    const target = el('st-tuning-status');
    if (target) { target.textContent = text; target.dataset.tone = tone; }
  };
  const controls = () => {
    if (!alive) return;
    for (const field of TUNING_FIELDS) if (el(`st-tuning-${field.key}`)) el(`st-tuning-${field.key}`).disabled = busy || !ready;
    if (el('st-tuning-save')) el('st-tuning-save').disabled = busy || !ready;
    if (el('st-tuning-check')) el('st-tuning-check').disabled = busy;
    el('st-tuning-card')?.setAttribute('aria-busy', String(busy));
  };
  function display(data, prefix = '', tone = '') {
    const text = recalculationText(data);
    const saved = configSavedStatus(data, `${prefix}${text}`);
    status(saved.text, tone || (text.includes('待确认') ? 'warning' : saved.tone));
  }
  async function load() {
    const result = await read('/api/config');
    if (!alive) return result;
    if (!result.ok) { status(`无法读取学习参数：${result.error?.message || '未知错误'}`, 'danger'); return result; }
    cfg = result.data;
    ready = TUNING_FIELDS.every(field => typeof cfg?.tuning_effective?.[field.key] === 'number');
    if (!ready) { status('学习参数不完整，请核验当前状态后重试', 'danger'); controls(); return result; }
    for (const field of TUNING_FIELDS) if (el(`st-tuning-${field.key}`)) el(`st-tuning-${field.key}`).value = cfg.tuning_effective[field.key];
    if (cfg.recalculation) display(cfg);
    else status(`当前参数已生效${cfg.revision == null ? '' : `；配置版本 ${cfg.revision}`}`);
    controls();
    return result;
  }
  async function verify() {
    const result = await read('/api/config');
    if (!alive) return;
    if (!pending) return load();
    const data = result.data;
    const changed = !tuningMatches(pending.before, pending.tuning);
    const versionConfirmed = !changed || (Number.isFinite(Number(data?.revision)) && Number(data.revision) > Number(pending.revision));
    const complete = ['completed', 'complete', 'done', 'unchanged'].includes(data?.recalculation?.status);
    if (result.ok && versionConfirmed && complete && tuningMatches(data?.tuning_effective, pending.tuning)) {
      cfg = data;
      pending = null;
      display(data, '已核验：');
      await reload();
    } else status(`结果待确认：${result.ok ? '尚未确认请求参数与历史重算已一同发布' : result.error?.message || '无法连接服务'}。输入已保留，请稍后核验当前状态。`, 'warning');
  }
  async function check() {
    if (busy || !alive) return;
    busy = true; controls();
    try { await (pending ? verify() : load()); }
    finally { busy = false; controls(); }
  }
  async function save() {
    if (busy || !ready || !alive) return;
    let tuning;
    try { tuning = readTuning(key => el(`st-tuning-${key}`)?.value); }
    catch (error) { status(error.message, 'danger'); return; }
    pending = { tuning, before: cfg?.tuning_effective, revision: cfg?.revision ?? 0 };
    busy = true; controls();
    status('重算全部历史…完成后新参数、统计与复习计划将一同生效。', 'busy');
    try {
      const result = await write('/api/config', { tuning }, { timeout: 600000 });
      if (!alive) return;
      if (result.ok) {
        cfg = { ...cfg, ...result.data, tuning_effective: result.data?.tuning_effective || tuning };
        pending = null;
        const superseded = result.data?.superseded || !tuningMatches(cfg.tuning_effective, tuning);
        display(cfg, superseded ? '本次参数已被后续配置更新覆盖，输入已保留。当前状态：' : '', superseded ? 'warning' : '');
        await reload();
      } else if (result.status === 0 || result.status >= 500 || ['network', 'timeout'].includes(result.error?.code)) {
        status('连接中断，正在核验参数与历史重算是否已经生效…', 'busy');
        await verify();
      } else {
        pending = null;
        status(`参数未保存：${result.error?.message || '请求被拒绝'}。输入已保留。`, 'danger');
      }
    } finally { busy = false; controls(); }
  }
  return { load, save, check, dispose() { alive = false; } };
}
