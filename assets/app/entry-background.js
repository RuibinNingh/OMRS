/** 独立锁屏背景：先显示静态图，认证控件就绪后按需启动动画。 */
import { chooseEntryQuality, createEntryFrameMonitor, ENTRY_QUALITY_LABELS, ENTRY_RENDER_BUDGETS,
  readEntryFallback, readEntryQuality, rememberEntryFallback, writeEntryQuality } from './core/entry-quality.js';

const FALLBACK = '/assets/vendor/entry-poster.webp';
const SCENE = '/assets/vendor/entry-scene.js';

export function startEntryBackground({ config = {}, ready = Promise.resolve(), win = window } = {}) {
  const doc = win.document;
  const root = doc.getElementById('gravity');
  const viewport = doc.getElementById('gravity-viewport');
  const custom = doc.getElementById('entry-custom');
  const poster = doc.getElementById('entry-poster');
  const select = doc.getElementById('entry-quality');
  const status = doc.getElementById('entry-quality-status');
  const reduced = win.matchMedia('(prefers-reduced-motion: reduce)');
  let storage;
  try { storage = win.localStorage; } catch { /* 隐私模式下使用内存偏好。 */ }
  let preference = readEntryQuality(storage);
  let generation = 0, stopped = false, scene = null, media = null, timer = 0, idleTimer = 0;
  let idle = false, monitor = null, selected = null;
  const listeners = [];
  const listen = (target, type, fn, options) => {
    target.addEventListener(type, fn, options);
    listeners.push(() => target.removeEventListener(type, fn, options));
  };
  const current = token => !stopped && token === generation;

  function stopResources() {
    win.clearTimeout(timer); win.clearTimeout(idleTimer);
    monitor = null;
    if (media) {
      media.pause?.(); media.removeAttribute('src'); media.load?.(); media.remove(); media = null;
    }
    const old = scene; scene = null;
    old?.();
    // 初始化中途失败时，尚未返回销毁器的上下文也必须释放。
    for (const canvas of viewport.querySelectorAll('canvas[data-engine]')) {
      canvas.getContext('webgl2')?.getExtension('WEBGL_lose_context')?.loseContext();
      canvas.remove();
    }
    custom.replaceChildren(); custom.hidden = true;
    poster.hidden = false;
    root.dataset.paused = 'false';
  }

  function describe(reason = selected?.reason || '') {
    root.dataset.preference = preference;
    root.dataset.quality = selected.quality;
    status.textContent = `${preference === 'auto' ? '自动 · ' : ''}${ENTRY_QUALITY_LABELS[selected.quality]}${idle ? ' · 闲置暂停' : ''}。${reason}`;
    select.value = preference;
  }

  function staticBackground(reason, token = generation) {
    if (!current(token)) return;
    generation++;
    stopResources();
    selected = { quality: 'static', reason };
    root.dataset.status = 'static';
    describe();
    // 视频、GIF 不赋 src，静态档完全跳过它们的下载与解码。
    if (config.mode !== 'custom' || !config.asset_url || config.kind === 'video' || config.mime === 'image/gif') return;
    const imageToken = generation;
    const image = doc.createElement('img');
    media = image;
    image.alt = '自定义入口静态背景';
    image.onload = () => {
      if (!current(imageToken)) return;
      const canvas = doc.createElement('canvas');
      const scale = Math.min(1, Math.sqrt(1_000_000 / Math.max(1, image.naturalWidth * image.naturalHeight)));
      canvas.width = Math.max(1, Math.floor(image.naturalWidth * scale));
      canvas.height = Math.max(1, Math.floor(image.naturalHeight * scale));
      const context = canvas.getContext('2d');
      if (!context) return;
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      canvas.setAttribute('role', 'img'); canvas.setAttribute('aria-label', image.alt);
      custom.replaceChildren(canvas); custom.hidden = false; poster.hidden = true;
      image.onload = image.onerror = null; image.removeAttribute('src'); media = null;
    };
    image.onerror = () => { if (current(imageToken)) describe('自定义背景加载失败，显示黑洞静态背景'); };
    image.src = config.asset_url;
  }

  function pause(paused) {
    root.dataset.paused = String(paused);
    scene?.setPaused?.(paused);
    if (media?.tagName === 'VIDEO') {
      if (paused) media.pause(); else media.play().catch(() => {});
    }
    monitor?.reset(win.performance.now());
  }

  function activity() {
    if (stopped || selected?.quality === 'static') return;
    win.clearTimeout(idleTimer);
    if (idle) { idle = false; pause(doc.hidden); describe(); }
    idleTimer = win.setTimeout(() => {
      if (stopped) return;
      idle = true; pause(true); describe();
    }, 15000);
  }

  async function loadScene(token) {
    try {
      const module = await import(SCENE);
      if (!current(token) || doc.hidden) return;
      await module.prepareGravityScene();
      if (!current(token) || doc.hidden) return;
      // 将资源准备和场景初始化分到不同任务，让输入有机会先得到处理。
      timer = win.setTimeout(() => {
        if (!current(token) || doc.hidden) return;
        const budget = ENTRY_RENDER_BUDGETS[selected.quality];
        monitor = preference === 'auto' ? createEntryFrameMonitor({ fps: budget.fps, onSlow() {
          rememberEntryFallback(storage);
          // 不在渲染调用栈内销毁仍被使用的纹理和后处理资源。
          timer = win.setTimeout(() => staticBackground('运行持续较慢，已切换静态背景', token), 0);
        } }) : null;
        monitor?.reset(win.performance.now());
        try {
          const created = module.createGravityScene(viewport, () => {
            if (!current(token)) return;
            poster.hidden = true; root.dataset.status = 'ready';
          }, () => {
            if (current(token)) timer = win.setTimeout(() => staticBackground('动画暂不可用，已显示静态背景', token), 0);
          }, { quality: selected.quality, ...budget, onFrame: time => monitor?.sample(time) });
          if (!current(token)) { created(); return; }
          scene = created;
          pause(doc.hidden || idle);
        } catch { staticBackground('动画暂不可用，已显示静态背景', token); }
      }, 0);
    } catch { staticBackground('动画资源加载失败，已显示静态背景', token); }
  }

  function loadMedia(token) {
    const video = config.kind === 'video';
    const element = doc.createElement(video ? 'video' : 'img');
    element.className = 'entry-custom-media';
    media = element;
    if (video) {
      element.muted = true; element.loop = true; element.playsInline = true;
      element.preload = 'metadata'; element.poster = FALLBACK;
      element.setAttribute('aria-label', '自定义入口视频背景');
    } else element.alt = '自定义入口背景';
    element.addEventListener(video ? 'loadeddata' : 'load', () => {
      if (!current(token)) return;
      custom.hidden = false; poster.hidden = true; root.dataset.status = 'custom-ready';
      if (video) pause(doc.hidden || idle);
    }, { once: true });
    element.addEventListener('error', () => staticBackground('自定义背景加载失败，已显示静态背景', token), { once: true });
    custom.replaceChildren(element);
    element.src = config.asset_url;
    if (video) element.play().catch(error => {
      if (current(token) && !doc.hidden && !idle && error.name !== 'AbortError') {
        staticBackground('视频无法自动播放，已显示静态背景', token);
      }
    });
  }

  async function apply() {
    const token = ++generation;
    stopResources(); idle = false;
    selected = chooseEntryQuality({ preference, reduced: reduced.matches,
      saveData: win.navigator.connection?.saveData, cores: win.navigator.hardwareConcurrency,
      memory: win.navigator.deviceMemory, fallback: readEntryFallback(storage) });
    root.dataset.status = 'static'; describe();
    custom.style.setProperty('--entry-blur', `${selected.quality === 'full' ? config.blur_px || 0 : Math.min(8, config.blur_px || 0)}px`);
    if (selected.quality === 'static') { staticBackground(selected.reason, token); return; }
    await ready;
    if (!current(token) || doc.hidden) return;
    // 先给登录区域和静态背景一次绘制机会，避免装饰效果争抢首屏。
    timer = win.setTimeout(() => {
      if (!current(token) || doc.hidden) return;
      activity();
      if (config.mode === 'custom' && config.asset_url) loadMedia(token); else loadScene(token);
    }, 120);
  }

  listen(select, 'change', () => { preference = writeEntryQuality(select.value, storage); apply(); });
  listen(win, 'storage', event => {
    if (event.key === 'omrs-entry-quality') { preference = readEntryQuality(storage); apply(); }
  });
  const motionChanged = () => apply();
  if (reduced.addEventListener) listen(reduced, 'change', motionChanged);
  else { reduced.addListener(motionChanged); listeners.push(() => reduced.removeListener(motionChanged)); }
  listen(doc, 'visibilitychange', () => {
    pause(doc.hidden || idle);
    if (!doc.hidden && selected?.quality !== 'static' && !scene && !media) apply();
  });
  for (const type of ['pointerdown', 'pointermove', 'keydown', 'scroll']) listen(doc, type, activity, { passive: true });
  const dispose = () => {
    if (stopped) return;
    stopped = true; generation++; stopResources(); listeners.forEach(remove => remove());
  };
  listen(win, 'pagehide', dispose);
  apply();
  return dispose;
}
