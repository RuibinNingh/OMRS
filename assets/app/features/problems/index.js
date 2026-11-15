/** 问题工作台：大量浏览、批量管理、草稿保护与材料关联。 */
import { morph } from '../../core/dom.js';
import { registerKeys } from '../../core/keys.js';
import { read, upload, statuses } from '../../domain/problems.js';
import { viewQ } from '../../domain/question/modal.js';
import { view } from './view.js';
import { createWorkspace } from './store.js';
import { confirm, prompt } from '../../ui/dialog.js';

export const page = {
  id: 'problems', title: '问题', workbench: true,
  mount(root, ctx) {
    let alive = true, timer = null;
    const model = createWorkspace(s => {
      morph(root, view(s));
      const box = root.querySelector('[data-prb-check-all]');
      if (box) box.indeterminate = s.items.some(p => s.chosen.has(p.id)) && !s.items.every(p => s.chosen.has(p.id));
    });
    const { s } = model;
    const message = e => model.notice(e.message || String(e), true);
    const guard = async () => !s.busy && !s.uploading && (!model.dirty() || await confirm('还有未保存的问题', {
      hint: '离开会放弃本次修改。', okText: '放弃修改', cancelText: '继续编辑', danger: true,
    }));
    const focus = () => root.querySelector('[data-prb-field="title"]')?.focus();
    const reload = () => { clearTimeout(timer); return model.load(); };
    const browse = async change => {
      if (!await guard() || !alive) return;
      model.close(); change(); s.chosen.clear(); s.offset = 0; await reload();
    };
    async function manage(operation, targets, status) {
      if (!targets.length || s.busy) return;
      if (targets.length > 100) { model.notice('每次最多处理100个问题，请减少勾选。', true); return; }
      if (!await guard() || !alive) return;
      const ids = targets.map(p => ({ id: p.id, expected_revision: p.revision }));
      let reason = '';
      if (operation === 'trash' && !await confirm(`删除 ${targets.length} 个问题？`, {
        hint: '问题将移入回收站，随时可以恢复。关联题目和错因记录会保留。', danger: true, okText: '移入回收站',
      })) return;
      if (operation === 'status') {
        reason = await prompt(`将 ${targets.length} 个问题设为「${statuses[status]}」`, '', {
          hint: '填写这次状态变更的依据。', placeholder: '例如：已完成针对练习，等待隔时验证', maxLength: 1000,
        });
        if (!reason) return;
      }
      if (!alive) return;
      const result = await model.mutate('manage_problems', { operation, items: ids, ...(status ? { status } : {}), reason });
      if (!result) return;
      const detailId = s.detail?.id;
      const affected = ids.some(p => p.id === detailId);
      s.chosen.clear();
      if (affected) model.close();
      if (operation === 'status' && affected) await model.open(detailId);
      await reload();
      model.notice(operation === 'trash' ? `已将 ${ids.length} 个问题移入回收站` : operation === 'restore' ? `已恢复 ${ids.length} 个问题` : `已更新 ${ids.length} 个问题的状态`);
    }
    const acts = {
      async new() { if (await guard() && alive) { model.create(); focus(); } },
      async open(el) { if (await guard() && alive) await model.open(el.dataset.id); },
      async back() { if (await guard() && alive) { const id = s.detail?.id; model.close(); root.querySelector(`[data-prb="open"][data-id="${id}"]`)?.focus(); } },
      edit() { s.editing = !s.editing; model.emit(); if (s.editing) focus(); },
      async cancel() { if (await guard() && alive) { if (s.creating) model.close(); else { s.draft = { ...s.detail }; s.reason = ''; s.editing = false; model.emit(); } } },
      filter: el => browse(() => { s.filter = el.dataset.value; }),
      clear: () => browse(() => { s.query = ''; s.filter = ''; }),
      async prev() { if (!s.loading) { s.offset = Math.max(0, s.offset - s.limit); await reload(); } },
      async next() { if (!s.loading && s.offset + s.limit < s.total) { s.offset += s.limit; await reload(); } },
      refresh() { model.notice(''); return reload(); },
      clearSelected() { s.chosen.clear(); model.emit(); },
      trash: el => manage('trash', el.dataset.id ? [s.detail?.id === el.dataset.id ? s.detail : s.items.find(p => p.id === el.dataset.id)] : [...s.chosen.values()]),
      restore: el => manage('restore', el.dataset.id ? [s.detail] : [...s.chosen.values()]),
      async save() {
        if (s.uploading) return;
        const p = s.draft;
        if (!p.title.trim()) { model.notice('先给问题起一个标题。', true); focus(); return; }
        const result = await model.mutate(s.creating ? 'create_problem' : 'update_problem', {
          ...(s.creating ? {} : { id: p.id, expected_revision: s.detail.revision }),
          title: p.title, description_md: p.description_md, status: p.status, reason: s.reason,
        });
        if (result) { model.accept(result.problem); await model.open(result.problem.id); await reload(); model.notice(s.detailError ? '问题已保存，详情刷新失败，可重新打开查看。' : '问题已保存'); }
      },
      async confirm() {
        if (!await guard()) return;
        const p = s.detail, reason = await prompt('确认观察的依据');
        if (!reason || !alive) return;
        const res = await model.mutate('update_problem', { id: p.id, expected_revision: p.revision, basis: 'user_confirmed', reason });
        if (res) { await model.open(p.id); await reload(); model.notice('已确认观察依据'); }
      },
      async picker() {
        if (!await guard()) return;
        const target = s.detail;
        const data = await read('/api/stats');
        if (!alive || s.detail !== target) return;
        s.questions = data.items || []; s.picker = !s.picker; model.emit();
      },
      async link() {
        const p = s.detail;
        const res = await model.mutate('link_problem_questions', { id: p.id, expected_revision: p.revision, question_ids: [...s.selected] });
        if (res) { await model.open(p.id); await reload(); model.notice('已关联题目'); }
      },
      async unlink(el) {
        if (!await guard()) return;
        const p = s.detail;
        const res = await model.mutate('unlink_problem_questions', { id: p.id, expected_revision: p.revision, question_ids: [el.dataset.id] });
        if (res) { await model.open(p.id); await reload(); model.notice('已移除题目关联'); }
      },
      question: el => viewQ(el.dataset.id, s.detail.questions.filter(q => q.available).map(q => q.question_id)),
    };
    const run = (fn, ...args) => Promise.resolve().then(() => fn(...args)).catch(message);
    const click = e => {
      const el = e.target.closest('[data-prb]');
      if (el && !el.disabled && !s.busy && acts[el.dataset.prb]) run(acts[el.dataset.prb], el);
    };
    const input = e => {
      const key = e.target.dataset.prbField;
      if (!key || e.isComposing) return;
      if (['title', 'description_md', 'status'].includes(key)) s.draft[key] = e.target.value;
      else s[key] = e.target.value;
      if (key === 'query') {
        clearTimeout(timer); s.offset = 0; s.chosen.clear(); model.invalidateList();
        timer = setTimeout(reload, 220);
      } else if (key === 'questionQuery' || key === 'status') model.emit();
      else if (['title', 'description_md', 'reason'].includes(key)) {
        const hint = root.querySelector('[data-prb-dirty]');
        if (hint) hint.textContent = model.dirty() ? '有未保存的修改' : '所有修改已保存';
      }
    };
    async function attach(file) {
      const target = s.draft;
      s.uploading++; model.emit();
      try {
        const asset = await upload(file);
        if (!alive || s.draft !== target) return;
        target.description_md += `\n\n${asset.markdown}`; model.emit();
        const editor = root.querySelector('[data-prb-field="description_md"]');
        if (editor) editor.value = target.description_md;
      } finally { s.uploading--; model.emit(); }
    }
    const change = async e => {
      const el = e.target;
      if (el.dataset.prbCheck) {
        const p = s.items.find(p => p.id === el.dataset.prbCheck);
        if (el.checked) s.chosen.set(p.id, p); else s.chosen.delete(p.id);
        model.emit();
      }
      if (el.matches('[data-prb-check-all]')) {
        for (const p of s.items) { if (el.checked) s.chosen.set(p.id, p); else s.chosen.delete(p.id); }
        model.emit();
      }
      if (el.dataset.prbQid) { if (el.checked) s.selected.add(el.dataset.prbQid); else s.selected.delete(el.dataset.prbQid); model.emit(); }
      if (el.dataset.prbField === 'sort' || el.dataset.prbField === 'limit') {
        s[el.dataset.prbField] = el.dataset.prbField === 'limit' ? Number(el.value) : el.value; s.offset = 0; await reload();
      }
      if (el.matches('[data-prb-batch-status]') && el.value) {
        const status = el.value; el.value = ''; await manage('status', [...s.chosen.values()], status);
      }
      if (el.matches('[data-prb-upload]') && el.files[0]) await attach(el.files[0]);
    };
    const paste = async e => {
      if (!e.target.matches('[data-prb-field="description_md"]')) return;
      let file = [...(e.clipboardData?.files || [])][0];
      const source = e.clipboardData?.getData('text/plain') || '';
      if (!file && /^\s*(?:<\?xml[^>]*>\s*)?<svg[\s>]/i.test(source)) file = new File([source], '粘贴图示.svg', { type: 'image/svg+xml' });
      if (file) { e.preventDefault(); await attach(file); }
    };
    const dragover = e => { if (e.target.matches('[data-prb-field="description_md"]')) e.preventDefault(); };
    const drop = async e => {
      if (!e.target.matches('[data-prb-field="description_md"]') || !e.dataTransfer?.files[0]) return;
      e.preventDefault(); await attach(e.dataTransfer.files[0]);
    };
    const offKeys = registerKeys('problems', {
      '/': () => root.querySelector('[data-prb-field="query"]')?.focus(),
      'escape': () => { if (!s.detail && !s.opening) return false; run(acts.back); },
      'mod+enter': { inInput: true, handler: () => { if (!s.draft || s.detail?.deleted_at) return false; run(acts.save); } },
    });
    const offGuard = ctx?.router.setLeaveGuard(guard);
    const beforeUnload = e => { if (model.dirty()) { e.preventDefault(); e.returnValue = ''; } };
    const listeners = { click, input, change: e => run(change, e), paste: e => run(paste, e), dragover, drop: e => run(drop, e), compositionend: input };
    for (const [name, fn] of Object.entries(listeners)) root.addEventListener(name, fn);
    window.addEventListener('beforeunload', beforeUnload);
    model.emit(); reload();
    return () => {
      alive = false; clearTimeout(timer); model.dispose(); offKeys(); offGuard?.();
      window.removeEventListener('beforeunload', beforeUnload);
      for (const [name, fn] of Object.entries(listeners)) root.removeEventListener(name, fn);
    };
  },
};
