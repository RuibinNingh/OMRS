/** 处理工作区静态三栏；由控制器挂到现有的 #ib-stage-process。 */
import { html } from '../../core/html.js';
import { icon } from '../../ui/icon.js';

export function processView() {
  return html`<div class="ib-proc">
    <div class="ib-pq" aria-label="处理队列">
      <div class="ib-pq-head">
        <label class="crp-check" title="全选处理队列"><input type="checkbox" class="ib-chk" id="ib-pq-all" data-change="create.processQueueAll" aria-label="全选处理队列"></label>
        <span class="t">处理队列</span><span class="n" id="ib-pq-n"></span>
      </div>
      <div class="ib-pq-list" id="ib-pq-list" data-morph="skip"></div>
      <div class="ib-pq-foot">
        <button class="ui-btn ui-btn--sm" type="button" data-action="create.processDetectSelected">${icon('sparkle')}AI 框选<span id="ib-pq-sel-n"></span></button>
        <button class="ui-btn ui-btn--sm" type="button" data-action="create.processDetectSelected" data-arg="template" title="零联网模板框选">${icon('grid')}模板</button>
        <button class="ui-btn ui-btn--sm" type="button" data-action="create.processApplyLastSelected">沿用框位</button>
      </div>
    </div>
    <div class="ib-pc" aria-label="图片框选画布">
      <div class="ib-pc-tools">
        <button class="ui-btn ui-btn--sm" type="button" data-action="create.processStep" data-arg="-1" title="上一张" aria-label="上一张">←</button>
        <button class="ui-btn ui-btn--sm" type="button" data-action="create.processStep" data-arg="1" title="下一张（Enter）" aria-label="下一张">→</button>
        <span class="fname" id="ib-pc-fname"></span>
        <div class="ib-seg roles" id="ib-role-seg" role="group" aria-label="画框角色" title="画框角色（Q / A / X）">
          <button type="button" data-action="create.processRole" data-arg="question" data-v="question" class="on">题目 <span class="ib-kbd">Q</span></button>
          <button type="button" data-action="create.processRole" data-arg="answer" data-v="answer">答案 <span class="ib-kbd">A</span></button>
          <button type="button" data-action="create.processRole" data-arg="ignore" data-v="ignore">忽略 <span class="ib-kbd">X</span></button>
        </div>
      </div>
      <div class="ib-pc-tools">
        <button class="ui-btn ui-btn--sm" type="button" data-action="create.processDetectCurrent">${icon('sparkle')}AI 框选此图</button>
        <button class="ui-btn ui-btn--sm" type="button" data-action="create.processDetectCurrent" data-arg="template" title="零联网：按版式或最近一张同版式样本给初始框">${icon('grid')}模板框选</button>
        <button class="ui-btn ui-btn--sm" type="button" data-action="create.processWholeImage" title="不需要裁：整张图就是题目">整图即题目</button>
        <button class="ui-btn ui-btn--sm" type="button" data-action="create.processApplyLast" title="套用上一张处理过的图的框">沿用上一张框位</button>
        <span class="grow"></span>
        <button class="ui-btn ui-btn--sm" type="button" data-action="create.processClearBoxes">清空框</button>
      </div>
      <div class="ib-pc-scroll" id="ib-pc-scroll">
        <div class="ib-stage-img" id="ib-stage-img" data-morph="skip"><img id="ib-stage-src" alt=""></div>
      </div>
      <div class="ib-pc-foot">
        <span>拖拽空白处画框</span><span><span class="ib-kbd">Q</span>/<span class="ib-kbd">A</span>/<span class="ib-kbd">X</span> 切角色</span>
        <span><span class="ib-kbd">Del</span> 删框</span><span><span class="ib-kbd">Enter</span> 下一张</span>
        <span><span class="ib-kbd">⌘/Ctrl</span>+<span class="ib-kbd">Enter</span> 转文本</span>
        <span class="grow"></span><span id="ib-pc-zoom" class="mono"></span>
      </div>
    </div>
    <div class="ib-ps" aria-label="区域与转换">
      <div class="ib-ps-head">
        <div class="t">区域与转换 <span class="hint" id="ib-ps-card-n"></span></div>
        <div class="meta" id="ib-ps-meta"></div>
        <div class="layout"><label for="ib-layout">版式</label>
          <select class="input" id="ib-layout" data-change="create.processLayout">
            <option value="zuoyebang">作业帮截图</option><option value="photo">拍照 / 扫描</option>
            <option value="plain">已裁好的题图</option><option value="other">其他</option>
          </select><span class="hint">作为训练标签记录</span>
        </div>
      </div>
      <div class="ib-ps-body" id="ib-ps-body" data-morph="skip"></div>
      <div class="ib-ps-foot">
        <button class="ui-btn ui-btn--sm" type="button" data-action="create.processAddCard" title="同一张图里的第 2 道题">+ 新题卡</button>
        <button class="ui-btn ui-btn--sm ui-btn--danger" type="button" data-action="create.processDiscardCurrent">丢弃</button>
        <span class="grow"></span>
        <button class="ui-btn ui-btn--sm" type="button" data-action="create.processExtractAll">转换文本</button>
        <button class="ui-btn ui-btn--sm ui-btn--primary" type="button" data-action="create.processMarkReady">标记就绪 →</button>
      </div>
    </div>
  </div>`;
}
