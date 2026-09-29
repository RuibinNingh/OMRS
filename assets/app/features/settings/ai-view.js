/** 设置页「ai」分区结构。 */
import { html } from '../../core/html.js';

export const aiView = () => html`<section class="st-section" id="st-sec-ai" role="tabpanel" aria-labelledby="st-tab-ai">
          <header class="st-head"><h2>AI 识别</h2><p>配置 OpenAI 兼容接口（<code>/v1/chat/completions</code>）后，「录入题目」和收件箱可以用 AI 识别图片。模型须支持图片输入。保存后立即生效。</p></header>
          <div class="card st-card">
            <div class="card-title">接口</div>
            <div class="st-fields">
              <div class="form-group">
                <label for="st-ai-base">API 地址</label>
                <input id="st-ai-base" class="ui-input" placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1">
                <div class="hint">填到 <code>/v1</code> 即可，会自动补 <code>/chat/completions</code>。例如 OpenAI 用 <code>https://api.openai.com/v1</code>。</div>
              </div>
              <div class="form-group">
                <label for="st-ai-key">API Key</label>
                <div class="st-inline">
                  <input id="st-ai-key" class="ui-input" type="password" placeholder="sk-..." autocomplete="off">
                  <button class="ui-btn ui-btn--sm" type="button" data-action="settings.toggleKey" id="st-ai-key-toggle">显示</button>
                  <button class="ui-btn ui-btn--sm" type="button" data-action="settings.clearKey">清除</button>
                </div>
                <div class="hint" id="st-ai-key-state"></div>
                <div class="hint">只保存在本机 <code>错题/.omrs/config.json</code>，由本地后端转发请求，不会回显到页面。</div>
              </div>
            </div>
          </div>
          <div class="card st-card">
            <div class="card-title">模型</div>
            <div class="st-fields">
              <div class="form-group">
                <label for="st-ai-model">默认模型</label>
                <input id="st-ai-model" class="ui-input" placeholder="qwen-vl-max" list="st-ai-model-list">
                <datalist id="st-ai-model-list">
                  <option value="qwen-vl-max"><option value="qwen-vl-plus"><option value="qwen3-vl-plus"><option value="qwen3-vl-flash"><option value="qwen3.7-plus"><option value="qwen3.5-ocr"><option value="qwen-vl-ocr"><option value="gpt-4o"><option value="gpt-4o-mini">
                </datalist>
              </div>
              <div class="hint">收件箱按用途选模型，留空时使用默认模型：</div>
              <div class="st-grid3">
                <div class="form-group"><label for="st-ai-model-detect">框选</label><input id="st-ai-model-detect" class="ui-input" placeholder="qwen3-vl-plus" list="st-ai-model-list"><div class="hint">需支持定位输出</div></div>
                <div class="form-group"><label for="st-ai-model-extract">转文本</label><input id="st-ai-model-extract" class="ui-input" placeholder="qwen3.5-ocr" list="st-ai-model-list"><div class="hint">建议 OCR 类模型</div></div>
                <div class="form-group"><label for="st-ai-model-classify">分类</label><input id="st-ai-model-classify" class="ui-input" placeholder="qwen3-vl-flash" list="st-ai-model-list"><div class="hint">判断科目、分类、知识点</div></div>
              </div>
            </div>
            <div class="st-row st-row-top">
              <div class="st-row-text">
                <label class="st-row-label" for="st-ai-thinking">启用思考</label>
                <div class="hint">关闭后，deepseek-flash 的图片提取、分类等识图请求不生成思考，通常更快；其它模型沿用服务商默认行为。此项不控制 AI 助手主模型。</div>
              </div>
              <input type="checkbox" class="st-switch" id="st-ai-thinking">
            </div>
            <div class="st-row st-row-top">
              <div class="st-row-text">
                <label class="st-row-label" for="st-ai-restrict">知识点只从已有项中选择</label>
                <div class="hint">开启时，AI 给出的知识点只能取自「已有分类 ∪ 已有知识点」，新造的词会被剔除，便于按知识点筛选。关闭后，没有贴切的已有项时允许新建（最多 4 个）。科目和分类始终允许新建。</div>
              </div>
              <input type="checkbox" class="st-switch" id="st-ai-restrict" checked>
            </div>
          </div>
          <div class="st-actions st-actions-end">
            <button class="ui-btn ui-btn--primary" type="button" data-action="settings.saveAi">保存 AI 配置</button>
          </div>
          <div id="st-ai-settings-status" class="st-status" role="status"></div>
        </section>`;
