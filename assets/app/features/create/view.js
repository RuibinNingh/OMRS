/** 工作区导航：五个按钮，前三项带收件箱各状态的张数。 */
import { html, each } from '../../core/html.js';
import { icon } from '../../ui/icon.js';
import { STAGES, stageOf } from './state.js';

export function flowView(selected = 'upload', counts = {}) {
  const current = stageOf(selected);
  return each(STAGES, stage => stage.id, (stage, index) => html`
    ${index > 0 && index < 3 ? html`<span class="ib-flow-arrow" aria-hidden="true">→</span>` : ''}
    <button type="button" class="ib-flow-step ${stage.icon ? 'aux' : ''} ${current === stage.id ? 'on' : ''}"
      data-key="${stage.id}" data-stage="${stage.id}" data-ib-stage="${stage.id}" data-action="create.stage" data-arg="${stage.id}"
      aria-controls="ib-stage-${stage.id}" aria-current="${current === stage.id ? 'step' : 'false'}">
      <span class="ib-flow-icon" aria-hidden="true">${stage.icon ? icon(stage.icon) : stage.number}</span>
      <span class="ib-flow-copy"><strong class="fs-name">${stage.title}</strong><span class="fs-sub">${stage.hint}</span></span>
      ${stage.count ? html`<span class="fs-count"><span id="${stage.count}">${counts[stage.countKey] ?? 0}</span><small>${stage.countLabel}</small></span>` : ''}
    </button>`);
}
