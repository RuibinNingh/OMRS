/** 助手消息图片：读取、校验与浏览器端缩放。 */
export const MAX_ATTACHMENTS = 6;
export const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
export const MAX_IMAGE_EDGE = 4096;

const TYPES = new Set(['image/png', 'image/jpeg', 'image/gif']);

export function readFileDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(new Error('读取图片失败'));
    reader.readAsDataURL(file);
  });
}

function loadImage(dataUrl) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error('无法读取图片尺寸'));
    image.src = dataUrl;
  });
}

export async function prepareImageFile(file) {
  if (!file || !TYPES.has(file.type)) throw new Error('只支持 PNG、JPEG 或 GIF 图片');
  if (file.size > MAX_IMAGE_BYTES) throw new Error('图片超过 8MB，已忽略');
  const original = await readFileDataUrl(file);
  const image = await loadImage(original);
  const width = image.naturalWidth || image.width;
  const height = image.naturalHeight || image.height;
  if (!width || !height) throw new Error('无法读取图片尺寸');
  if (Math.max(width, height) <= MAX_IMAGE_EDGE) return { dataUrl: original, width, height, type: file.type };
  const scale = MAX_IMAGE_EDGE / Math.max(width, height);
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
  if ((dataUrl.length - dataUrl.indexOf(',') - 1) * 0.75 > MAX_IMAGE_BYTES) throw new Error('缩放后的图片仍超过 8MB，已忽略');
  return { dataUrl, width: canvas.width, height: canvas.height, type: 'image/jpeg' };
}

export function imageSrc(image) {
  if (!image) return '';
  return image.dataUrl || (image.sha ? `/api/drafts/image?sha=${encodeURIComponent(image.sha)}` : '');
}
