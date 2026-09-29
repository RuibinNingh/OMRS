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

export function normalizeJpegBytes(bytes) {
  if (bytes[0] !== 0xff || bytes[1] !== 0xd8) return bytes;
  let offset = 2;
  let scan = false;
  const finish = tail => {
    const out = new Uint8Array(bytes.length + tail.length);
    out.set(bytes); out.set(tail, bytes.length);
    return out;
  };
  // 按段长度跳过 EXIF/缩略图；结束标记之后可能还有手机相册私有数据。
  while (offset < bytes.length) {
    if (scan) while (offset < bytes.length && bytes[offset] !== 0xff) offset += 1;
    if (offset === bytes.length) return finish([0xff, 0xd9]);
    if (bytes[offset] !== 0xff) return bytes;
    while (offset < bytes.length && bytes[offset] === 0xff) offset += 1;
    if (offset === bytes.length) return scan ? finish([0xd9]) : bytes;
    const marker = bytes[offset++];
    if (marker === 0xd9) return offset === bytes.length ? bytes : bytes.slice(0, offset);
    if (scan && (marker === 0 || (marker >= 0xd0 && marker <= 0xd7))) continue;
    if (marker === 1) continue;
    if (marker === 0 || marker === 0xd8 || offset + 2 > bytes.length) return bytes;
    const length = bytes[offset] * 256 + bytes[offset + 1];
    if (length < 2 || offset + length > bytes.length) return bytes;
    scan = marker === 0xda || (scan && marker === 0xdc);
    offset += length;
  }
  return scan ? finish([0xff, 0xd9]) : bytes;
}

export async function prepareImageFile(file) {
  if (!file || !TYPES.has(file.type)) throw new Error('只支持 PNG、JPEG 或 GIF 图片');
  if (file.size > MAX_IMAGE_BYTES) throw new Error('图片超过 8MB，已忽略');
  const source = file.type === 'image/jpeg'
    ? new Blob([normalizeJpegBytes(new Uint8Array(await file.arrayBuffer()))], { type: file.type }) : file;
  const original = await readFileDataUrl(source);
  const image = await loadImage(original);
  const width = image.naturalWidth || image.width;
  const height = image.naturalHeight || image.height;
  if (!width || !height) throw new Error('无法读取图片尺寸');
  const edge = Math.max(width, height);
  if (edge <= MAX_IMAGE_EDGE) return { dataUrl: original, width, height, type: file.type };
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
