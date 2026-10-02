import test from 'node:test';
import assert from 'node:assert/strict';
import { createTuning } from '../../assets/app/features/settings/tuning.js';
import { TUNING_FIELDS, readTuning } from '../../assets/app/features/settings/tuning-state.js';

function harness() {
  const values = Object.fromEntries(TUNING_FIELDS.map(field => [field.key, field.max === 1 ? 0.5 : Math.max(1, field.min)]));
  const cfg = { tuning_effective: values, revision: 4, recalculation: { status: 'unchanged', revision: 4 } };
  const fields = Object.fromEntries([...TUNING_FIELDS.map(field => `st-tuning-${field.key}`), 'st-tuning-status', 'st-tuning-save', 'st-tuning-check', 'st-tuning-card']
    .map(id => [id, { value: '', disabled: true, textContent: '', dataset: {}, setAttribute(name, value) { this[name] = value; } }]));
  const root = { querySelector: selector => fields[selector.slice(1)] || null };
  return { cfg, fields, root, field: key => fields[`st-tuning-${key}`], status: fields['st-tuning-status'] };
}
const done = (tuning, mirror_pending = false) => ({ revision: 5, tuning_effective: tuning, mirror_pending,
  recalculation: { status: 'completed', questions: 123, feedbacks: 456, seconds: 1.25, revision: 5 } });

test('实际调参控制器冻结完整参数、等待重算且拒绝重复提交，镜像待同步仍明确生效', async () => {
  const h = harness(); let release; let request; let writes = 0; let reloads = 0;
  const ctl = createTuning(h.root, { read: async () => ({ ok: true, data: h.cfg }),
    write: async (path, body, options) => { writes++; request = { path, body, options }; return new Promise(resolve => { release = resolve; }); },
    reload: async () => { reloads++; } });
  await ctl.load(); h.field('high_score_threshold').value = '8';
  const pending = ctl.save();
  assert.match(h.status.textContent, /重算全部历史/);
  assert.equal(h.fields['st-tuning-save'].disabled, true);
  assert.equal(h.field('high_score_threshold').disabled, true);
  await ctl.save(); assert.equal(writes, 1);
  assert.equal(request.path, '/api/config'); assert.equal(request.options.timeout, 600000);
  assert.equal(Object.keys(request.body.tuning).length, 19);
  assert.equal(request.body.tuning.high_score_threshold, 8);
  release({ ok: true, data: done(request.body.tuning, true) }); await pending;
  assert.match(h.status.textContent, /123 题、456 条反馈，耗时 1.25 秒；配置版本 5/);
  assert.match(h.status.textContent, /配置已生效，配置镜像待同步/);
  assert.equal(h.status.dataset.tone, 'warning'); assert.equal(reloads, 1);
  assert.equal(h.field('high_score_threshold').value, '8');
  assert.equal(h.fields['st-tuning-save'].disabled, false);
});

test('参数拒绝与非法输入保留编辑，不刷新为旧配置，也不启动重算', async () => {
  const h = harness(); let writes = 0;
  const ctl = createTuning(h.root, { read: async () => ({ ok: true, data: h.cfg }),
    write: async () => { writes++; return { ok: false, status: 409, error: { message: '配置已更新' } }; }, reload: async () => assert.fail('不应刷新统计') });
  await ctl.load(); h.field('kill_streak').value = '1.5'; await ctl.save();
  assert.equal(writes, 0); assert.match(h.status.textContent, /击杀连对次数必须是整数/);
  assert.equal(h.field('kill_streak').value, '1.5');
  h.field('kill_streak').value = '3'; await ctl.save();
  assert.equal(writes, 1); assert.match(h.status.textContent, /参数未保存：配置已更新。输入已保留/);
  assert.equal(h.field('kill_streak').value, '3');
  assert.throws(() => readTuning(key => key === 'proficiency_factor' ? '0' : h.cfg.tuning_effective[key]), /必须大于0/);
});

test('网络中断后核验有效参数和发布版本，确认完成才显示成功', async () => {
  const h = harness(); let server = h.cfg; let reads = 0; let reloads = 0;
  const ctl = createTuning(h.root, { read: async () => { reads++; return { ok: true, data: server }; },
    write: async (_path, body) => { server = done(body.tuning); return { ok: false, status: 0, error: { code: 'network' } }; },
    reload: async () => { reloads++; } });
  await ctl.load(); h.field('high_score_threshold').value = '9'; await ctl.save();
  assert.equal(reads, 2); assert.equal(reloads, 1);
  assert.match(h.status.textContent, /已核验：历史重算完成/);
  assert.equal(h.status.dataset.tone, 'success');
});

test('超时未确认时保留全部输入，稍后核验通过才转为已生效', async () => {
  const h = harness(); let server = h.cfg; let payload;
  const ctl = createTuning(h.root, { read: async () => ({ ok: true, data: server }),
    write: async (_path, body) => { payload = body.tuning; return { ok: false, status: 0, error: { code: 'timeout' } }; }, reload: async () => {} });
  await ctl.load(); h.field('high_score_threshold').value = '9'; await ctl.save();
  assert.match(h.status.textContent, /结果待确认/); assert.doesNotMatch(h.status.textContent, /失败/);
  assert.equal(h.field('high_score_threshold').value, '9');
  server = { ...done(payload), revision: 4 }; await ctl.check();
  assert.match(h.status.textContent, /结果待确认/, '同版本不能确认发生改变的候选参数');
  server = done(payload); await ctl.check();
  assert.match(h.status.textContent, /已核验：历史重算完成/);
});

test('离开设置页后在途保存回包不更新已卸载控件', async () => {
  const h = harness(); let release;
  const ctl = createTuning(h.root, { read: async () => ({ ok: true, data: h.cfg }),
    write: async () => new Promise(resolve => { release = resolve; }), reload: async () => assert.fail('卸载后不应刷新') });
  await ctl.load(); const pending = ctl.save(); ctl.dispose();
  const text = h.status.textContent;
  release({ ok: true, data: done(h.cfg.tuning_effective) }); await pending;
  assert.equal(h.status.textContent, text);
});

test('后续配置覆盖与第三方镜像冲突明确显示，仍保留本次编辑', async () => {
  const h = harness();
  const ctl = createTuning(h.root, { read: async () => ({ ok: true, data: h.cfg }),
    write: async () => ({ ok: true, data: { ...done(h.cfg.tuning_effective), superseded: true, mirror_conflict: true } }), reload: async () => {} });
  await ctl.load(); h.field('high_score_threshold').value = '8'; await ctl.save();
  assert.match(h.status.textContent, /后续配置更新覆盖/);
  assert.match(h.status.textContent, /第三方冲突，两份文件均已保留/);
  assert.equal(h.status.dataset.tone, 'warning');
  assert.equal(h.field('high_score_threshold').value, '8');
});
