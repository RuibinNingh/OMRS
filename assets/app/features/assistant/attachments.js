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

async function jpegHasEndMarker(file) {
  const tail = new Uint8Array(await file.slice(-2).arrayBuffer());
  return tail.length === 2 && tail[0] === 0xff && tail[1] === 0xd9;
}

export async function prepareImageFile(file) {
  if (!file || !TYPES.has(file.type)) throw new Error('只支持 PNG、JPEG 或 GIF 图片');
  if (file.size > MAX_IMAGE_BYTES) throw new Error('图片超过 8MB，已忽略');
  const original = await readFileDataUrl(file);
  const image = await loadImage(original);
  const width = image.naturalWidth || image.width;
  const height = image.naturalHeight || image.height;
  if (!width || !height) throw new Error('无法读取图片尺寸');
  const edge = Math.max(width, height);
  const incompleteJpeg = file.type === 'image/jpeg' && !await jpegHasEndMarker(file);
  if (edge <= MAX_IMAGE_EDGE && !incompleteJpeg) return { dataUrl: original, width, height, type: file.type };
  const scale = Math.min(1, MAX_IMAGE_EDGE / edge);
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
  if ((dataUrl.length - dataUrl.indexOf(',') - 1) * 0.75 > MAX_IMAGE_BYTES) throw new Error('处理后的图片仍超过 8MB，已忽略');
  return { dataUrl, width: canvas.width, height: canvas.height, type: 'image/jpeg' };
}

export function imageSrc(image) {
  if (!image) return '';
  return image.dataUrl || (image.sha ? `/api/drafts/image?sha=${encodeURIComponent(image.sha)}` : '');
}
