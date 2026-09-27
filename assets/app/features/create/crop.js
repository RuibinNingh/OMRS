/** 浏览器裁图：原图按 id 缓存；裁出 data URL 随任务或提交上传，canvas 预览按框位键只在框变化时重画。 */
const images = new Map();
export const JPEG_PIXELS = 1500000;   // 超过约 150 万像素的裁图（长截图的答案区）改用 JPEG 0.9 白底，避免几 MB 的 base64

export const rawUrl = id => `/api/inbox/raw?id=${encodeURIComponent(id)}`;

/** 裁图参数：像素尺寸与输出格式。纯函数，node 可测。 */
export function cropPlan(region, naturalWidth, naturalHeight, type = 'image/png', quality = 0.92) {
  const width = Math.max(1, Math.round(region.w * naturalWidth));
  const height = Math.max(1, Math.round(region.h * naturalHeight));
  const jpeg = type === 'image/png' && width * height > JPEG_PIXELS;
  return { sx: region.x * naturalWidth, sy: region.y * naturalHeight, width, height,
    type: jpeg ? 'image/jpeg' : type, quality: jpeg ? 0.9 : quality, whiteBackground: jpeg };
}

/** 预览尺寸：按最大宽度等比缩小，不放大。 */
export function previewSize(region, naturalWidth, naturalHeight, maxWidth) {
  const sw = region.w * naturalWidth;
  const sh = region.h * naturalHeight;
  const scale = Math.min(1, maxWidth / Math.max(1, sw));
  return { sw, sh, width: Math.max(1, Math.round(sw * scale)), height: Math.max(1, Math.round(sh * scale)) };
}

export const boxKey = region => ['x', 'y', 'w', 'h'].map(key => Number(region[key] || 0).toFixed(4)).join(',');

export function loadImage(item) {
  let image = images.get(item.id);
  if (!image) { image = new Image(); image.src = rawUrl(item.id); images.set(item.id, image); }
  if (image.complete && image.naturalWidth) return Promise.resolve(image);
  return new Promise((resolve, reject) => {
    image.addEventListener('load', () => resolve(image), { once: true });
    image.addEventListener('error', () => reject(new Error('原图加载失败')), { once: true });
  });
}

export async function cropDataUrl(item, region, type = 'image/png', quality = 0.92) {
  const image = await loadImage(item);
  const plan = cropPlan(region, image.naturalWidth, image.naturalHeight, type, quality);
  const canvas = document.createElement('canvas');
  canvas.width = plan.width;
  canvas.height = plan.height;
  const context = canvas.getContext('2d');
  if (plan.whiteBackground) { context.fillStyle = '#fff'; context.fillRect(0, 0, plan.width, plan.height); }
  context.drawImage(image, plan.sx, plan.sy, plan.width, plan.height, 0, 0, plan.width, plan.height);
  return canvas.toDataURL(plan.type, plan.quality);
}

/**
 * 补画 root 里的裁图预览：<canvas data-crop="图片id|区域id" data-crop-max="宽">。框位没变的不重画。
 * find(itemId) 返回图片；图片或区域不在了就跳过。
 */
export async function paintCrops(root, find) {
  for (const canvas of root.querySelectorAll('canvas[data-crop]')) {
    const [itemId, regionId] = canvas.dataset.crop.split('|');
    const item = find(itemId);
    const region = item?.regions?.find(row => row.id === regionId);
    if (!region) continue;
    const key = boxKey(region);
    if (canvas.dataset.painted === key) continue;
    canvas.dataset.painted = key;
    try {
      const image = await loadImage(item);
      const size = previewSize(region, image.naturalWidth, image.naturalHeight, Number(canvas.dataset.cropMax) || 340);
      canvas.width = size.width;
      canvas.height = size.height;
      canvas.getContext('2d').drawImage(image, region.x * image.naturalWidth, region.y * image.naturalHeight, size.sw, size.sh, 0, 0, size.width, size.height);
    } catch (_) { delete canvas.dataset.painted; }
  }
}
