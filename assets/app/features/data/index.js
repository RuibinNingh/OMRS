/**
 * 数据复盘页（P6 第 2 轮起的 features 页面；原 assets/data.js）。
 * - 契约：page = { id: 'data', title, mount(root, ctx) → unmount, actions }；动作命名空间 'data'。
 * - 数据：/api/analytics 每次进入页面、点「刷新」、以及统计快照变化（store.data，写操作之后）时重拉；
 *   「每日练习趋势」「标记分布」直接取统计快照。首次加载超过 300ms 才出骨架；失败时显示原因与「重试」，已有数据时保留旧数据只在顶部报错。
 * - 导出：GET /api/export-review 存成文件（core/download）。顽固题与屡练不熟的「查看」「加入展示板」经 domain。
 */
import { morph } from '../../core/dom.js';
import { get } from '../../core/api.js';
import { downloadResponse } from '../../core/download.js';
import { toast } from '../../ui/toast.js';
import { viewQ, qvSetContext } from '../../domain/question/index.js';
import { boardQuickAdd } from '../../domain/board.js';
import * as S from './state.js';
import { view } from './view.js';

const s = S.state;
let ctl = null;

function createController(root, ctx) {
  let token = 0;
  let slow = 0;

  function env() {
    const a = s.analytics || {};
    const data = ctx.store.get().data || {};
    return {
      s, a, kpis: S.kpis(a.overview), bars: S.barSets(a), subjects: S.subjectsSorted(a.subjects), scatter: S.scatterBins(a.items),
      hours: S.hours(a.behavior?.by_hour), alerts: S.alerts(a.review_alert), trend: S.trend(data.daily_trend), labels: S.labelCounts(data.items),
    };
  }
  const paint = () => morph(root, view(env()));

  async function load() {
    const mine = ++token;
    clearTimeout(slow);
    if (s.analytics) { s.phase = 'loading'; paint(); }
    else slow = setTimeout(() => { if (mine === token && ctl) { s.phase = 'loading'; paint(); } }, 300);
    const res = await get('/api/analytics');
    clearTimeout(slow);
    if (mine !== token) return;
    if (res.ok && res.data && typeof res.data === 'object') {
      s.analytics = res.data;
      s.phase = 'ready';
      s.error = '';
      const weak = res.data.weak_spots || {};
      qvSetContext('leech', [...(weak.leeches || []), ...(weak.struggling || [])].map(it => it.uid));
    } else {
      s.phase = 'error';
      s.error = res.error?.message || '未知错误';
    }
    if (ctl) paint();
  }

  async function exportReview() {
    if (s.exporting) return;
    s.exporting = true;
    s.exportError = '';
    paint();
    try {
      const response = await fetch('/api/export-review', { credentials: 'same-origin' });
      if (!response.ok) {
        let message = `HTTP ${response.status}`;
        try { message = (await response.json()).msg || message; } catch (error) { /* 非 JSON 错误体 */ }
        throw new Error(message);
      }
      const name = await downloadResponse(response, `OMRS-复盘-${new Date().toISOString().slice(0, 10)}.md`);
      toast(`已导出 ${name}`, { kind: 'ok' });
    } catch (error) {
      s.exportError = error.message || '未知错误';
    } finally {
      s.exporting = false;
      if (ctl) paint();
    }
  }

  return { paint, load, exportReview, dispose() { clearTimeout(slow); token += 1; } };
}

export const page = {
  id: 'data',
  title: '数据复盘',
  mount(root, ctx) {
    ctl = createController(root, ctx);
    const offs = [
      ctx.store.subscribe(() => { ctl?.paint(); ctl?.load(); }, st => st.data),
      ctx.bus.on('labels', () => ctl?.paint()),
    ];
    ctl.paint();
    ctl.load();
    return () => { offs.forEach(off => off()); ctl?.dispose(); ctl = null; };
  },
  actions: {
    refresh: () => ctl?.load(),
    export: () => ctl?.exportReview(),
    view: ({ arg }) => viewQ(arg, 'leech'),
    board: ({ el, arg }) => boardQuickAdd(arg, { anchor: el }),
  },
};
