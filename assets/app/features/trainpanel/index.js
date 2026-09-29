/** 独立训练面板入口；仅运行中轮询，隐藏页暂停，按块增量更新。 */
import { html } from '../../core/html.js';
import { render, morph } from '../../core/dom.js';
import * as api from '../../core/api.js';
import { startActivityTracking } from '../../core/activity.js';
import { installIcons } from '../../ui/icon.js';
import { dialog } from '../../ui/dialog.js';
import { toast } from '../../ui/toast.js';
import { createTrainStore } from './store.js';
import { mountTry } from './try.js';
import { mountControl } from './control.js';
import { mountAudits } from './audits.js';
import { headerView, progressView, curvesView, evaluationView, datasetView, historyView, globalErrorView } from './view.js';

export function mountTrainpanel(root) {
  root.className = 'tp-app';
  render(root, html`<header class="tp-head" id="tp-head"></header><div id="tp-global-errors"></div>
    <main><section class="tp-section" id="tp-control"></section><section class="tp-section" id="tp-try"></section><section class="tp-section" id="tp-audits"></section>
      ${[['progress', '训练进度'], ['curves', '训练曲线'], ['evaluation', '效果评估'], ['dataset', '数据概况'], ['history', '实验历史']].map(([id, label]) => html`<section class="tp-section" aria-labelledby="tp-${id}-title"><h2 id="tp-${id}-title">${label}</h2><div id="tp-${id}"></div></section>`)}
    </main>`);
  const disposeAudits = mountAudits(root.querySelector('#tp-audits'), api);
  const tester = mountTry(root.querySelector('#tp-try'), api);
  const signatures = new Map();
  const views = { progress: progressView, curves: curvesView, evaluation: evaluationView, dataset: datasetView, history: historyView, 'global-errors': globalErrorView };
  let timer = null, disposed = false;
  function paint(state) {
    const put = (id, markup) => {
      if (signatures.get(id) === markup.text) return;
      signatures.set(id, markup.text); morph(root.querySelector(`#tp-${id}`), markup);
    };
    put('head', headerView(state.overview, state.service));
    Object.entries(views).forEach(([id, view]) => put(id, view(state)));
    if (state.overview) tester.sync(state.overview.collect);
  }
  const disposeControl = mountControl(root.querySelector('#tp-control'), api, () => refresh(true));
  const store = createTrainStore({ api, changed: paint });
  async function refresh(force = false) {
    clearTimeout(timer);
    await store.refresh(force);
    if (!disposed && !document.hidden && store.state.overview?.latest?.status?.state === 'running') timer = setTimeout(refresh, 5000);
  }
  root.addEventListener('click', async event => {
    const target = event.target.closest('[data-action]');
    if (!target || target.disabled) return;
    const { action, arg } = target.dataset;
    if (action === 'refresh') refresh(true);
    if (action === 'select') store.select(arg);
    if (action === 'copy') {
      try { await navigator.clipboard.writeText(arg); toast('命令已复制', { kind: 'ok' }); }
      catch { dialog({ title: '复制命令', body: html`<p class="tp-muted">浏览器不支持剪贴板，请选中复制：</p><code>${arg}</code>`, hideCancel: true }); }
    }
    if (action === 'overlay') dialog({ title: '人工框与模型框', body: html`<img class="tp-overlay-large" src="${arg}" alt="人工框为绿，模型框为红">`, size: 'lg', hideCancel: true, okText: '关闭' });
  });
  const visibility = () => { clearTimeout(timer); if (!document.hidden) refresh(true); };
  document.addEventListener('visibilitychange', visibility);
  paint(store.state); refresh();
  return () => { disposed = true; clearTimeout(timer); store.dispose(); tester.dispose(); disposeAudits(); disposeControl(); document.removeEventListener('visibilitychange', visibility); };
}

installIcons();
startActivityTracking();
const dispose = mountTrainpanel(document.querySelector('#tp-app'));
window.addEventListener('pagehide', dispose, { once: true });
