/** 设置页六分区外壳；各分区结构放在对应模块。 */
import { html } from '../../core/html.js';
import { appearanceView } from './appearance-view.js';
import { accessView } from './access-view.js';
import { aiView } from './ai-view.js';
import { agentView } from './agent-view.js';
import { dataView } from './data-view.js';
import { serviceView } from './service-view.js';

export function view() {
  return html`<div class="st-layout">
    <nav class="st-nav" role="tablist" aria-label="设置分区" aria-orientation="vertical">
      <button class="st-nav-item" type="button" role="tab" id="st-tab-appearance" data-st-section="appearance" aria-controls="st-sec-appearance" data-action="settings.section" data-arg="appearance"><strong>外观与显示</strong><span>主题、密度、时区</span></button>
      <button class="st-nav-item" type="button" role="tab" id="st-tab-access" data-st-section="access" aria-controls="st-sec-access" data-action="settings.section" data-arg="access"><strong>访问与安全</strong><span>局域网访问、远端 PIN</span></button>
      <button class="st-nav-item" type="button" role="tab" id="st-tab-ai" data-st-section="ai" aria-controls="st-sec-ai" data-action="settings.section" data-arg="ai"><strong>AI 识别</strong><span>接口、模型、知识点</span></button>
      <button class="st-nav-item" type="button" role="tab" id="st-tab-assistant" data-st-section="assistant" aria-controls="st-sec-assistant" data-action="settings.section" data-arg="assistant"><strong>AI 助手</strong><span>对话模型、预算、开关</span></button>
      <button class="st-nav-item" type="button" role="tab" id="st-tab-data" data-st-section="data" aria-controls="st-sec-data" data-action="settings.section" data-arg="data"><strong>数据与存储</strong><span>备份恢复、图片压缩</span></button>
      <button class="st-nav-item" type="button" role="tab" id="st-tab-service" data-st-section="service" aria-controls="st-sec-service" data-action="settings.section" data-arg="service"><strong>服务与运行</strong><span>运行状态、重启、源码</span></button>
    </nav>
    <div class="st-body">${appearanceView()}${accessView()}${aiView()}${agentView()}${dataView()}${serviceView()}</div>
  </div>`;
}
