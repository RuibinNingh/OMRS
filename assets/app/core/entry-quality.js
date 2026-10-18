/** 入口动画的浏览器本地偏好、资源预算与持续掉帧判定。 */
export const ENTRY_QUALITY_KEY = 'omrs-entry-quality';
export const ENTRY_FALLBACK_KEY = 'omrs-entry-quality-fallback';
export const ENTRY_FALLBACK_TTL = 30 * 60 * 1000;
export const ENTRY_QUALITIES = Object.freeze(['auto', 'light', 'full', 'static']);
export const ENTRY_QUALITY_LABELS = Object.freeze({ auto: '自动', light: '轻量', full: '完整', static: '静态' });

export function normalizeEntryQuality(value) {
  return ENTRY_QUALITIES.includes(value) ? value : 'auto';
}

export function readEntryQuality(storage) {
  try { return normalizeEntryQuality((storage || globalThis.localStorage)?.getItem(ENTRY_QUALITY_KEY)); } catch { return 'auto'; }
}

export function writeEntryQuality(value, storage) {
  const mode = normalizeEntryQuality(value);
  try {
    storage ||= globalThis.localStorage;
    storage?.setItem(ENTRY_QUALITY_KEY, mode);
    storage?.removeItem(ENTRY_FALLBACK_KEY);
  } catch { /* 存储不可用时，本次选择仍生效。 */ }
  return mode;
}

export function readEntryFallback(storage) {
  try { return JSON.parse((storage || globalThis.localStorage)?.getItem(ENTRY_FALLBACK_KEY) || 'null'); } catch { return null; }
}

export function rememberEntryFallback(storage, now = Date.now()) {
  try { (storage || globalThis.localStorage)?.setItem(ENTRY_FALLBACK_KEY, JSON.stringify({ at: now })); } catch { /* 仅本次降级。 */ }
}

export function chooseEntryQuality({ preference = 'auto', reduced = false, saveData = false,
  cores, memory, fallback, now = Date.now() } = {}) {
  const mode = normalizeEntryQuality(preference);
  if (reduced) return { quality: 'static', reason: '系统已开启减少动态效果' };
  if (mode !== 'auto') return { quality: mode, reason: '按当前浏览器的选择显示' };
  if (saveData) return { quality: 'static', reason: '已开启节省流量' };
  if ((cores > 0 && cores <= 2) || (memory > 0 && memory <= 2)) {
    return { quality: 'static', reason: '根据设备信息减少资源消耗' };
  }
  if (Number.isFinite(fallback?.at) && now >= fallback.at && now - fallback.at < ENTRY_FALLBACK_TTL) {
    return { quality: 'static', reason: '近期运行较慢，暂用静态背景；稍后自动重试' };
  }
  return { quality: 'light', reason: '自动控制动画资源消耗' };
}

export const ENTRY_RENDER_BUDGETS = Object.freeze({
  light: Object.freeze({ fps: 30, maxPixels: 1_000_000, maxSide: 2048, pixelRatio: 1,
    atlasWidth: 1024, bloom: false, powerPreference: 'low-power' }),
  full: Object.freeze({ fps: 60, maxPixels: 3_000_000, maxSide: 2560, pixelRatio: 1.5,
    atlasWidth: 2048, bloom: true, powerPreference: 'default' }),
});

/** 按实际渲染帧采样；主动限帧后的 30 FPS 不会被误判成 60 FPS 掉帧。 */
export function createEntryFrameMonitor({ fps = 30, warmupMs = 2000, windowMs = 3000,
  slowWindows = 2, onSlow = () => {} } = {}) {
  let warmupUntil = 0, start = null, frames = 0, slow = 0, done = false;
  const reset = now => {
    warmupUntil = now + warmupMs;
    start = null; frames = slow = 0;
  };
  return {
    reset,
    sample(now) {
      if (done || now < warmupUntil) return;
      if (start === null) { start = now; return; }
      frames++;
      const elapsed = now - start;
      if (elapsed < windowMs) return;
      const actualFps = frames * 1000 / elapsed;
      slow = actualFps < fps * .8 ? slow + 1 : 0;
      start = now; frames = 0;
      if (slow >= slowWindows) { done = true; onSlow(actualFps); }
    },
  };
}
