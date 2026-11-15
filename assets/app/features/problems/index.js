/** 独立问题页控制器。编辑失败保留当前输入，写入统一领域API。 */
import { morph } from '../../core/dom.js';
import { read, write, requestId, upload } from '../../domain/problems.js';
import { viewQ } from '../../domain/question/modal.js';
import { view } from './view.js';
import { prompt } from '../../ui/dialog.js';

export const page = {
  id: 'problems', title: '问题',
  mount(root) {
    const s = { items: [], total: 0, next: null, query: '', filter: '', detail: null, editing: false, reason: '', message: '', busy: false, picker: false, questions: [], selected: new Set(), questionQuery: '', request: null };
    let alive = true;
    let loadId = 0;
    const paint = () => { if (alive) morph(root, view(s)); };
    const message = e => { s.message = e.message || String(e); paint(); };
    const load = async (append = false) => {
      const mine = ++loadId;
      const data = await read(`/api/problems?query=${encodeURIComponent(s.query)}&status=${s.filter}&cursor=${append ? s.next || '' : ''}`);
      if (!alive || mine !== loadId) return;
      s.items = append ? [...s.items, ...data.items] : data.items; s.total = data.total; s.next = data.next_cursor; paint();
    };
    const open = async id => {
      s.detail = (await read(`/api/problem?id=${encodeURIComponent(id)}`)).problem;
      s.editing = false; s.reason = ''; s.picker = false; s.request = null; paint();
    };
    async function mutation(action, data) {
      if (s.busy) return null;
      const payload = JSON.stringify([action, data]);
      if (s.request?.payload !== payload) s.request = { payload, id: requestId() };
      s.busy = true; paint();
      try {
        const res = await write(action, { ...data, request_id: s.request.id });
        s.request = null; s.message = '已保存'; await load(); return res;
      } finally { s.busy = false; paint(); }
    }
    const acts = {
      async new() {
        const res = await mutation('create_problem', { title: '待命名的问题', description_md: '## 具体表现\n\n## 应对办法\n\n## 怎样验证改善' });
        if (res) { await open(res.problem.id); s.editing = true; paint(); root.querySelector('[data-prb-field="title"]')?.focus(); }
      },
      open: el => open(el.dataset.id),
      back: () => { s.detail = null; paint(); },
      edit: () => { s.editing = !s.editing; paint(); },
      more: () => load(true),
      async save() {
        const p = s.detail;
        const res = await mutation('update_problem', { id: p.id, expected_revision: p.revision, title: p.title, description_md: p.description_md, status: p.status, reason: s.reason });
        if (res) await open(p.id);
      },
      async confirm() { const p=s.detail;const reason=await prompt('确认观察的依据');if (!reason) return;const res=await mutation('update_problem',{id:p.id,expected_revision:p.revision,basis:'user_confirmed',reason});if(res) await open(p.id); },
      async picker() { s.questions = (await read('/api/stats')).items || []; s.picker = !s.picker; paint(); },
      async link() {
        const p = s.detail;
        const res = await mutation('link_problem_questions', { id: p.id, expected_revision: p.revision, question_ids: [...s.selected] });
        if (res) { s.selected.clear(); await open(p.id); }
      },
      async unlink(el) {
        const p = s.detail;
        const res = await mutation('unlink_problem_questions', { id: p.id, expected_revision: p.revision, question_ids: [el.dataset.id] });
        if (res) await open(p.id);
      },
      question: el => viewQ(el.dataset.id,s.detail.questions.filter(q=>q.available).map(q=>q.question_id)),
    };
    const click = e => { const el = e.target.closest('[data-prb]'); if (el && acts[el.dataset.prb]) Promise.resolve(acts[el.dataset.prb](el)).catch(message); };
    const input = e => {
      const key = e.target.dataset.prbField;
      if (!key) return;
      if (['title','description_md','status'].includes(key)) s.detail[key] = e.target.value;
      else s[key] = e.target.value;
      if (key === 'query' || key === 'filter') load().catch(message);
      if (key === 'questionQuery') paint();
    };
    const change = async e => {
      if (e.target.dataset.prbQid) { if (e.target.checked) s.selected.add(e.target.dataset.prbQid); else s.selected.delete(e.target.dataset.prbQid); }
      if (e.target.matches('[data-prb-upload]') && e.target.files[0]) {
        try { const asset = await upload(e.target.files[0]); s.detail.description_md += `\n\n${asset.markdown}`; paint(); const editor = root.querySelector('[data-prb-field="description_md"]'); if (editor) editor.value = s.detail.description_md; } catch (error) { message(error); }
      }
    };
    async function attach(file) {
      const target=s.detail;
      const asset=await upload(file);
      target.description_md+=`\n\n${asset.markdown}`;
      if (s.detail===target) { paint();const editor=root.querySelector('[data-prb-field="description_md"]');if(editor)editor.value=target.description_md; }
    }
    const paste = async e => {
      if (!e.target.matches('[data-prb-field="description_md"]')) return;
      let file = [...(e.clipboardData?.files || [])][0];
      const source=e.clipboardData?.getData('text/plain') || '';
      if (!file && /^\s*(?:<\?xml[^>]*>\s*)?<svg[\s>]/i.test(source)) file=new File([source],'粘贴图示.svg',{type:'image/svg+xml'});
      if (file) { e.preventDefault();try { await attach(file); } catch(error) { message(error); } }
    };
    const dragover=e=>{if(e.target.matches('[data-prb-field="description_md"]'))e.preventDefault();};
    const drop=async e=>{if(!e.target.matches('[data-prb-field="description_md"]') || !e.dataTransfer?.files[0])return;e.preventDefault();try{await attach(e.dataTransfer.files[0]);}catch(error){message(error);}};
    root.addEventListener('click',click); root.addEventListener('input',input); root.addEventListener('change',change); root.addEventListener('paste',paste);root.addEventListener('dragover',dragover);root.addEventListener('drop',drop);
    paint(); load().catch(message);
    return () => { alive = false; root.removeEventListener('click',click); root.removeEventListener('input',input); root.removeEventListener('change',change); root.removeEventListener('paste',paste);root.removeEventListener('dragover',dragover);root.removeEventListener('drop',drop); };
  },
};
