/** 面板五块内容与独立空态，不重建实时测试输入区。 */
import { html } from '../../core/html.js';
import { formatDate } from '../../core/format.js';
import { button } from '../../ui/button.js';
import { stat } from '../../ui/stat.js';
import { progress } from '../../ui/progress.js';
import { status } from '../../ui/status.js';
import { empty } from '../../ui/empty.js';
import { skeleton } from '../../ui/skeleton.js';
import { table } from '../../ui/table.js';
import { roles, duration, remaining, stateLabels, pct } from './state.js';
import { lineChart, comparison, histogram } from './charts.js';

export const command = (label, value) => html`<div class="tp-command"><code>${value}</code>${button({ label: `复制${label}命令`, size: 'sm', action: 'copy', arg: value })}</div>`;
const failure = text => html`<div class="tp-error-row tp-errors" role="alert">${text}${button({ label: '重试', size: 'sm', action: 'refresh' })}</div>`;
const errors = value => Object.values(value || {}).map(failure);
const stateTone = value => ({ done: 'success', failed: 'danger', interrupted: 'warning', running: 'info' })[value] || 'neutral';
export const overlayURL = (run, name) => `/api/trainpanel/overlay?run=${encodeURIComponent(run)}&name=${encodeURIComponent(name)}`;

export function headerView(data, service) {
  const model = service?.state === 'online' ? service.model : null;
  const label = { online: '检测服务在线', offline: '检测服务未启动', unconfigured: '检测服务未配置' }[service?.state] || '正在检查服务';
  return html`<div><h1>训练面板</h1><p>${model ? `${model.name} · ${formatDate(model.created_at)} · SHA-256 ${model.sha256?.slice(0, 8)}` : '未加载在线模型 · 训练与测试题目、答案的范围'}</p></div>
    <div class="tp-row">${status({ tone: service?.state === 'online' ? 'success' : 'warning', text: label })}<a class="ui-btn ui-btn--sm" href="/#/create">返回录入题目</a>${button({ label: '刷新', size: 'sm', action: 'refresh' })}</div>`;
}

export function progressView(state) {
  if (state.loading) return skeleton({ lines: 3, label: '读取训练进度' });
  const data = state.overview;
  const run = data?.latest;
  const current = run?.status;
  if (!current) return html`${run?.error ? failure(run.error) : empty({ title: '还没有训练记录', hint: '在终端构建数据集并开始训练，面板会读取进度。', compact: true })}
    ${data?.commands ? html`<div class="tp-commands">${command('构建数据集', data.commands.build)}${command('开始训练', data.commands.train)}${command('评估', data.commands.evaluate)}${command('启动检测服务', data.commands.serve)}</div>` : ''}`;
  const elapsed = current.wall_seconds ?? current.total_seconds ?? Math.max(0, (Date.now() - Date.parse(current.started_at)) / 1000);
  return html`<div class="tp-row"><span>${run.name}</span>${status({ tone: stateTone(current.state), text: stateLabels[current.state] || current.state })}</div>
    ${run.error ? failure(run.error) : ''}
    <div class="tp-stats">${stat({ label: '当前轮次', value: `${current.epoch} / ${current.epochs}` })}${stat({ label: '已经用时', value: duration(elapsed) })}${stat({ label: '预计剩余', value: remaining(current), hint: `每轮 ${duration(current.epoch_seconds)}` })}</div>
    ${progress({ value: current.epoch, max: current.epochs, label: '训练轮次', meta: `第 ${current.epoch} / ${current.epochs} 轮` })}
    ${current.error ? failure(current.error) : ''}
    ${current.state === 'interrupted' ? html`<p class="tp-muted">训练进程不在或长时间未更新，可从最近检查点恢复。</p>${command('续训', data.commands.resume)}` : ''}`;
}

export function curvesView(state) {
  if (state.loading) return skeleton({ lines: 3 });
  const detail = state.detail;
  const rows = detail?.metrics || [];
  if (!rows.length) return html`${detail?.errors?.metrics ? failure(detail.errors.metrics) : empty({ title: '第一轮结束后显示曲线', hint: '训练中每 5 秒检查进度。', compact: true })}`;
  return html`${detail.errors?.metrics ? failure(detail.errors.metrics) : ''}<p class="tp-muted">${detail.name} · ${rows.length} 轮记录</p><div class="tp-cols">
    ${lineChart(rows, [{ key: 'train/box_loss', label: '训练 box' }, { key: 'train/cls_loss', label: '训练 cls' }, { key: 'val/box_loss', label: '验证 box' }, { key: 'val/cls_loss', label: '验证 cls' }], '框与分类损失')}
    ${lineChart(rows, [{ key: 'metrics/mAP50(B)', label: '验证 mAP50' }, { key: 'metrics/mAP50-95(B)', label: '验证 mAP50–95' }], '验证集检测指标', 1)}
  </div>`;
}

export function evaluationView(state) {
  if (state.loading) return skeleton({ lines: 3 });
  const detail = state.detail;
  const result = detail?.evaluation;
  if (!result?.model) return html`${detail?.errors?.evaluation ? failure(detail.errors.evaluation) : empty({ title: '评估尚未运行', hint: '训练完成后运行整图评估，查看模型与模板在同一测试集上的对照。', compact: true })}`;
  return html`${detail.errors?.evaluation ? failure(detail.errors.evaluation) : ''}<p class="tp-muted">${detail.name} · ${result.split === 'val' ? '验证集' : '冻结测试集'} ${result.model.images} 张整图</p>
    <p class="tp-muted">以下 IoU 衡量框位置差异，不代表内容是否可用。内容验收请看上方评测记录。</p><div class="tp-stats">${stat({ label: '模型：两框几何匹配', value: pct(result.model.unchanged_rate), hint: `${result.model.unchanged} / ${result.model.images} 张，两框 IoU ≥ 0.75 且无多余框` })}${stat({ label: '模板：两框几何匹配', value: pct(result.template?.unchanged_rate) })}${stat({ label: '推理阈值', value: result.conf })}</div>
    <div class="tp-cols">${roles.flatMap(role => [comparison(result.model, result.template, role, 'pass_rate', 'IoU ≥ 0.75 占比'), comparison(result.model, result.template, role, 'mean_iou', '平均 IoU')])}</div>
    <div class="tp-cols">${roles.map(role => histogram(result.model, result.template, role))}</div>
    <h3>几何差异样本</h3><p class="tp-muted">人工框为绿，模型框为红。点击查看大图。</p><div class="tp-wall">${(result.overlays || []).slice(0, 12).map((item, index) => html`<button class="tp-thumb" data-action="overlay" data-arg="${overlayURL(detail.name, item.name)}" aria-label="查看叠加样本 ${index + 1}"><img loading="lazy" src="${overlayURL(detail.name, item.name)}" alt="人工框与模型框叠加样本 ${index + 1}"><span>样本 ${index + 1}</span></button>`)}</div>`;
}

export function datasetView(state) {
  if (state.loading) return skeleton({ lines: 3 });
  const data = state.overview;
  const dataset = data?.dataset;
  if (!dataset) return html`${data?.errors?.dataset ? failure(data.errors.dataset) : empty({ title: '还没有数据集', hint: '先完成标注，再按上方命令构建数据集。', compact: true })}`;
  const counts = dataset.counts || {};
  const strips = dataset.strip_counts || {};
  const excluded = new Map();
  (dataset.excluded || []).forEach(item => { const reason = item.reason.split('：')[0]; excluded.set(reason, (excluded.get(reason) || 0) + 1); });
  return html`<p>数据版本：<strong>${dataset.version}</strong></p><div class="tp-stats">${[['train', '训练集'], ['val', '验证集'], ['test', '历史回归集'], ['independent', '独立验收集']].map(([key, label]) => stat({ label, value: `${counts[key] || 0} 张`, hint: `${strips[key] || 0} 条带` }))}</div>
    <div class="tp-facts">${[...excluded].map(([reason, count]) => html`<span>${reason}：${count} 张</span>`)}</div>
    <p class="tp-muted">新增已完成图片 ${data.live?.additional || 0} 张；当前标注集 ${data.live?.done?.annotate || 0} 张，收件箱 ${data.live?.done?.inbox || 0} 张已完成。</p>
    ${errors(data.live?.errors)}${data.live?.additional >= 10 ? html`<p>可重新构建数据集并重训，测试集保持冻结。</p>${command('重建数据集', data.commands.build)}${command('重训', data.commands.train)}` : ''}`;
}

export function historyView(state) {
  if (state.loading) return skeleton({ lines: 3 });
  const runs = state.overview?.runs || [];
  if (!runs.length) return empty({ title: '还没有实验历史', hint: '每次训练使用独立实验名，结果会保留在这里。', compact: true });
  return table({ rowKey: 'name', rows: runs, stack: true, columns: [
    { key: 'name', label: '实验', render: row => button({ label: row.name, size: 'sm', action: 'select', arg: row.name }) },
    { label: '日期／数据', render: row => `${formatDate(row.status?.started_at)} / ${row.status?.dataset || '—'}` },
    { label: '轮次／用时', render: row => `${row.status?.epoch ?? '—'} 轮 / ${duration(row.status?.wall_seconds ?? row.status?.total_seconds)}` },
    { label: '题目／答案 IoU 达标率', render: row => `${pct(row.evaluation?.model?.question?.pass_rate)} / ${pct(row.evaluation?.model?.answer?.pass_rate)}` },
    { label: '状态', render: row => row.error ? '读取失败' : `${stateLabels[row.status?.state] || '未知'}${row.current ? ' · 当前模型' : ''}` },
  ] });
}
export const globalErrorView = state => html`${state.error ? failure(state.error) : ''}${state.overview?.errors?.model ? failure(state.overview.errors.model) : ''}`;
