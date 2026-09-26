/**
 * 即时练习页（第一个 features 页面，页面契约的范例）。
 * - 契约：page = { id, title, workbench, mount(root, ctx) → unmount, actions, keys }；actions / keys 由外壳登记，
 *   命名空间与作用域都是 'instant'。处理函数只在挂载期间生效（未挂载时 ctl 为 null）。
 * - 渲染：每次状态变化 paint() → morph(root, view(state))；题面挂载点由 hydrate() 交给 domain/questions（qview）。
 * - 数据：题目列表读 store.data（旧 reloadData() 之后外壳同步）；标记定义变化听 bus 的 'labels'；
 *   旧入口经过渡桥发 'instant:load'（带仪表盘预设）。
 */
import { morph } from '../../core/dom.js';
import { get, post } from '../../core/api.js';
import { confirm } from '../../ui/dialog.js';
import { toast } from '../../ui/toast.js';
import { itemsOf, filterPractice, facets, dueDays } from '../../domain/items.js';
import { listLabels } from '../../domain/labels/index.js';
import { ensureDetail, mountQuestion, invalidateQuestions, editQuestion } from '../../domain/question/index.js';
import { reloadData } from '../../domain/data.js';
import * as S from './state.js';
import { view } from './view.js';

const s = S.state;
let ctl = null;

function createController(root, ctx) {
  let loadToken = 0;
  const env = () => ({ facets: facets(itemsOf(ctx.store.get().data)), labels: listLabels(), dueDays });

  function hydrate() {
    root.querySelectorAll('[data-qv-host]').forEach(el => {
      if (el.dataset.qvFor === el.dataset.key) return;
      el.dataset.qvFor = el.dataset.key;
      mountQuestion(el, el.dataset.uid, { reveal: el.dataset.reveal === '1', onReveal: () => api.reveal() });
    });
  }

  function paint() {
    morph(root, view(s, env()));
    hydrate();
  }

  function preload() {
    s.queue.slice(s.index, s.index + 4).forEach(item => { ensureDetail(item.uid); });
  }

  const current = () => S.currentItem(s);

  const api = {
    paint,
    async load(preset) {
      const pending = S.counts(s).pending;
      if (pending && !(await confirm(`还有 ${pending} 道已判定没提交`, { hint: '重新取题会丢掉这些判定。先提交的话，点「取消」后按「提交」。', okText: '丢掉并重新取题', danger: true }))) return;
      if (preset) s.filters = S.applyPreset(s.filters, preset);
      const token = ++loadToken;
      // 按钮立即进入加载态；超过 300ms 还没回来才换成骨架屏，避免快速返回时闪一下（设计规范 §4.6）
      s.loading = true;
      paint();
      const slow = setTimeout(() => { if (token === loadToken && s.loading) { s.phase = 'loading'; paint(); } }, 300);
      const res = await get(`/api/recommend?${S.buildParams(s.filters)}`);
      clearTimeout(slow);
      if (token !== loadToken) return;
      s.loading = false;
      if (!res.ok) {
        s.phase = 'error';
        s.error = res.error?.message || '未知错误';
        paint();
        return;
      }
      const due = filterPractice(res.data?.due, s.filters);
      const proficiency = filterPractice(res.data?.proficiency, s.filters);
      S.startRound(s, S.mergeRecommendations({ due, proficiency }, s.filters.count));
      if (s.queue.length) await ensureDetail(s.queue[0].uid);
      if (token !== loadToken) return;
      paint();
      preload();
    },
    go(index) {
      const i = Number(index);
      if (!Number.isInteger(i) || i < 0 || i >= s.queue.length || i === s.index) return;
      s.index = i;
      paint();
      preload();
    },
    prev() { api.go(s.index - 1); },
    next() { api.go(s.index + 1); },
    nextOpen() {
      const i = S.nextOpenIndex(s.queue, s.results, s.index);
      if (i >= 0) api.go(i);
    },
    reveal() {
      const item = current();
      if (!item || s.results[item.uid]?.revealed) return;
      S.reveal(s, item.uid);
      paint();
    },
    verdict(correct) {
      const item = current();
      if (!item) return;
      if (!S.setVerdict(s, item.uid, correct)) { toast('这题已提交，判定不能再改', { kind: 'warn' }); return; }
      paint();
    },
    score(value) {
      const item = current();
      if (!item || !s.results[item.uid]?.revealed) return;
      if (S.setScore(s, item.uid, value)) paint();
    },
    /** 数字键打分：与反馈工作台一致，要先判了对错才生效（1、2 留给判定）。 */
    scoreKey(n) {
      const item = current();
      if (!item || !S.isJudged(s.results[item.uid])) return false;
      api.score(n);
      return undefined;
    },
    async submit() {
      const rows = S.submitRows(s);
      if (!rows.length) { toast('还没有待提交的判定', { kind: 'warn' }); return; }
      if (s.submitting) return;
      s.submitting = true;
      s.submitError = '';
      paint();
      const res = await post('/api/feedback', { feedbacks: rows, session_id: s.sessionId || S.sessionId() });
      s.submitting = false;
      if (!res.ok) {
        s.submitError = res.error?.message || '未知错误';
        paint();
        return;
      }
      S.markSubmitted(s, rows);
      s.lastSubmit = Array.isArray(res.data?.results) ? res.data.results : [];
      paint();
      toast(`已提交 ${rows.length} 条反馈`, { kind: 'ok' });
      await reloadData();
      await invalidateQuestions(rows.map(row => row.uid));
      paint();
    },
    filter(target) {
      const field = { 'instant-subject': 'subject', 'instant-category': 'category', 'instant-ktag': 'ktag', 'instant-count': 'count' }[target?.id];
      if (!field) return;
      s.filters = { ...s.filters, [field]: field === 'count' ? S.clampCount(target.value) : target.value };
      paint();
    },
    toggleLabel(name) {
      const on = s.filters.labels.includes(name);
      s.filters = { ...s.filters, labels: on ? s.filters.labels.filter(l => l !== name) : [...s.filters.labels, name] };
      paint();
    },
    labelMode(value) {
      s.filters = { ...s.filters, labelMode: value === 'all' ? 'all' : 'any' };
      paint();
    },
    clear() {
      s.filters = { ...s.filters, subject: '', category: '', ktag: '', labels: [], labelMode: 'any' };
      api.load();
    },
    edit() {
      const item = current();
      if (item) editQuestion(item.uid);
    },
  };
  return api;
}

const onButton = event => !!event.target?.closest?.('button, a[href], [role="button"], summary');
const whenReady = fn => (...args) => (ctl && s.queue.length ? fn(...args) : false);

export const page = {
  id: 'instant',
  title: '即时练习',
  workbench: true,
  mount(root, ctx) {
    ctl = createController(root, ctx);
    const offs = [
      ctx.store.subscribe(() => ctl?.paint(), st => st.data),
      ctx.bus.on('labels', () => ctl?.paint()),
      ctx.bus.on('instant:load', preset => ctl?.load(preset || {})),
    ];
    ctl.paint();
    return () => { offs.forEach(off => off()); ctl = null; };
  },
  actions: {
    load: () => ctl?.load(),
    clear: () => ctl?.clear(),
    go: ({ arg }) => ctl?.go(arg),
    prev: () => ctl?.prev(),
    next: () => ctl?.next(),
    nextOpen: () => ctl?.nextOpen(),
    verdict: ({ arg }) => ctl?.verdict(arg === '1'),
    score: ({ value }) => ctl?.score(value),
    submit: () => ctl?.submit(),
    filter: ({ event }) => ctl?.filter(event.target),
    label: ({ arg }) => ctl?.toggleLabel(arg),
    labelMode: ({ event }) => ctl?.labelMode(event.target.value),
  },
  keys: {
    j: whenReady(() => ctl.next()),
    arrowdown: whenReady(() => ctl.next()),
    k: whenReady(() => ctl.prev()),
    arrowup: whenReady(() => ctl.prev()),
    space: whenReady(event => (onButton(event) ? false : ctl.reveal())),
    1: whenReady(() => ctl.verdict(true)),
    2: whenReady(() => ctl.verdict(false)),
    ...Object.fromEntries([0, 3, 4, 5, 6, 7, 8, 9].map(n => [String(n), whenReady(() => ctl.scoreKey(n))])),
    enter: whenReady(event => (onButton(event) ? false : ctl.nextOpen())),
    e: whenReady(() => ctl.edit()),
    'mod+enter': whenReady(() => ctl.submit()),
  },
};
