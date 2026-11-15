/** 弹窗内原位录因；页签切换保留编辑框和草稿，记录独立于练习反馈。 */
import { html } from '../../core/html.js';
import { morph } from '../../core/dom.js';
import { read, write, upload, requestId } from '../problems.js';
import { dialog, prompt } from '../../ui/dialog.js';
import { bindTabs } from '../../ui/tabs.js';
import { ReflectionDraft } from './reflection-state.js';
import { reflectionsView, draftLabel } from './reflections-view.js';

export function mountReflections(host, questionId) {
  const draft = new ReflectionDraft(questionId);
  const s = {
    entries: [], problems: [], tab: 'history', loading: true, busy: false, message: '',
    composing: false, association: false, more: false, search: '',
    expanded: new Set(), revisions: new Set(), revision: draft.value.editing_entry || null,
  };
  let alive = true;
  let guard = false;
  let loadVersion = 0;
  function paint() { if (alive) morph(host, reflectionsView(s, draft)); }
  async function load() {
    const version = ++loadVersion;
    const [entries, problems] = await Promise.all([
      read(`/api/reflections?question_id=${encodeURIComponent(questionId)}&limit=100`), read('/api/problems?limit=100'),
    ]);
    if (!alive || version !== loadVersion) return;
    const items = [...entries.items];
    let cursor = entries.next_cursor;
    while (cursor && alive && version === loadVersion) {
      const next = await read(`/api/reflections?question_id=${encodeURIComponent(questionId)}&limit=100&cursor=${encodeURIComponent(cursor)}`);
      items.push(...next.items);
      cursor = next.next_cursor;
    }
    if (!alive || version !== loadVersion) return;
    s.entries = items;
    s.problems = problems.items;
    s.loading = false;
    paint();
  }
  function syncText() {
    const editor = host.querySelector('textarea');
    if (alive && editor) editor.value = draft.value.content_md;
  }
  function openEditor() {
    if (!alive) return;
    s.tab = 'new';
    paint();
    const editor = host.querySelector('textarea');
    editor?.focus({ preventScroll: true });
    editor?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }
  async function save() {
    if (!alive || s.busy || s.composing || !draft.dirty()) return false;
    s.busy = true;
    s.message = '';
    paint();
    let saved = false;
    try {
      const data = draft.payload();
      if (s.revision) await write('revise_reflection_entry', {
        id: s.revision.id, expected_revision: s.revision.revision, expected_content_hash: s.revision.content_hash, content_md: data.content_md,
        problem_ids: data.problem_ids, occurred_at: data.occurred_at,
        reason: '用户修订错因', request_id: data.request_id,
      });
      else await write('add_reflection_entry', data);
      draft.clear();
      saved = true;
      s.revision = null;
      s.message = '已保存；可以继续补记下一条。';
      // 写入成功后刷新失败不等于保存失败，避免误导用户重复录入。
      try { await load(); }
      catch { s.message = '已保存，但历史记录刷新失败，请重新打开查看。'; }
      syncText();
      return true;
    } catch (error) {
      s.message = `${error.message}；草稿已保留，可重试。`;
      return false;
    } finally {
      s.busy = false;
      paint();
      if (alive && saved) host.querySelector('textarea')?.focus({ preventScroll: true });
    }
  }
  const acts = {
    toggle: openEditor,
    save,
    async recurrence(el) {
      if (!await canLeave() || !alive) return;
      const entry = s.entries.find(v => v.id === el.dataset.id);
      draft.clear();
      draft.update({ content_md: entry.content_md, recurrence_of: entry.id, problem_ids: entry.problem_ids });
      s.revision = null;
      s.message = '';
      openEditor();
      syncText();
    },
    async revise(el) {
      if (!await canLeave() || !alive) return;
      const entry = s.entries.find(v => v.id === el.dataset.id);
      draft.clear();
      draft.update({
        content_md: entry.content_md, problem_ids: entry.problem_ids, occurred_at: entry.occurred_at || '',
        editing_entry: { id: entry.id, revision: entry.revision, content_hash: entry.content_hash },
      });
      s.revision = entry;
      s.message = '';
      openEditor();
      syncText();
    },
    async withdraw(el) {
      const entry = s.entries.find(v => v.id === el.dataset.id);
      const reason = await prompt('撤回原因');
      if (reason && alive) {
        await write('revise_reflection_entry', { id: entry.id, expected_revision: entry.revision, expected_content_hash: entry.content_hash, withdrawn: true, reason, request_id: requestId() });
        await load();
      }
    },
    async confirm(el) {
      const entry = s.entries.find(v => v.id === el.dataset.id);
      const reason = await prompt('确认错因的依据');
      if (reason && alive) {
        await write('revise_reflection_entry', { id: entry.id, expected_revision: entry.revision, expected_content_hash: entry.content_hash, basis: 'user_confirmed', reason, request_id: requestId() });
        await load();
      }
    },
    async newProblem() {
      const title = await prompt('新问题标题');
      if (!title || !alive) return;
      const res = await write('create_problem', { title, description_md: draft.value.content_md, question_ids: [questionId], request_id: requestId() });
      if (!alive) return;
      draft.update({ problem_ids: [...draft.value.problem_ids, res.problem.id] });
      await load();
    },
  };
  const click = event => {
    const el = event.target.closest('[data-ref]');
    if (el && acts[el.dataset.ref]) Promise.resolve(acts[el.dataset.ref](el)).catch(error => { s.message = error.message; paint(); });
  };
  const input = event => {
    if (event.target.dataset.refInput) {
      draft.update({ [event.target.dataset.refInput]: event.target.value });
      s.message = '';
      host.querySelector('[data-ref-draft]').textContent = draftLabel(s, draft);
      host.querySelector('.ref-message').textContent = '';
    }
    if (event.target.matches('[data-ref-search]')) { s.search = event.target.value; paint(); }
  };
  const change = async event => {
    const pid = event.target.dataset.refProblem;
    if (pid) draft.update({ problem_ids: event.target.checked ? [...draft.value.problem_ids, pid] : draft.value.problem_ids.filter(v => v !== pid) });
    if (event.target.matches('[data-ref-file]') && event.target.files[0]) {
      try {
        const asset = await upload(event.target.files[0]);
        if (!alive) return;
        draft.update({ content_md: `${draft.value.content_md}\n${asset.markdown}` });
        paint();
        syncText();
      } catch (error) { s.message = error.message; paint(); }
    }
  };
  const tab = event => { s.tab = event.detail.id; };
  const disclosure = event => {
    const el = event.target;
    if (el.dataset.refDisclosure) s[el.dataset.refDisclosure] = el.open;
    for (const [attr, values] of [['refEntryDetails', s.expanded], ['refRevisions', s.revisions]]) {
      const id = el.dataset[attr];
      if (id) { if (el.open) values.add(id); else values.delete(id); }
    }
  };
  const start = () => { s.composing = true; };
  const end = () => { s.composing = false; };
  const key = event => {
    if (event.target.closest('[role="tab"]') && ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) event.stopPropagation();
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !event.isComposing && !s.composing) {
      event.preventDefault();
      save();
    }
  };
  const listeners = { click, input, change, keydown: key, compositionstart: start, compositionend: end, 'ui-tabs:change': tab };
  for (const [name, handler] of Object.entries(listeners)) host.addEventListener(name, handler);
  host.addEventListener('toggle', disclosure, true);
  paint();
  const markdownChanged = event => {
    if (event.detail?.question_id === questionId) load().catch(error => { s.message = error.message; paint(); });
  };
  window.addEventListener('omrs:question-markdown', markdownChanged);
  bindTabs(host.querySelector('[role="tablist"]'));
  load().catch(error => { s.loading = false; s.message = error.message; paint(); });
  async function canLeave() {
    if (s.busy || s.composing || guard) return false;
    if (!draft.dirty()) return true;
    guard = true;
    let discard = false;
    const answer = await dialog({
      title: '还有未保存的错因', hint: '草稿按题目身份保留。可保存后离开、放弃草稿，或继续编辑。',
      okText: '保存后离开', cancelText: '继续编辑',
      body: html`<button class="ui-btn" data-discard-reflection>放弃草稿并离开</button>`,
      onOpen(el) {
        el.querySelector('[data-discard-reflection]').addEventListener('click', () => {
          discard = true;
          el.querySelector('[data-dialog-cancel]').click();
        });
      },
      onOk: () => save(),
    });
    guard = false;
    if (discard) draft.clear();
    return answer.ok || discard;
  }
  return {
    toggle: openEditor,
    canLeave,
    dispose() {
      alive = false;
      window.removeEventListener('omrs:question-markdown', markdownChanged);
      for (const [name, handler] of Object.entries(listeners)) host.removeEventListener(name, handler);
      host.removeEventListener('toggle', disclosure, true);
    },
  };
}
