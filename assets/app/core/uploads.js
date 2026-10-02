/** 有界附件上传：原始字节分块发送，领域请求仅携带暂存引用。 */
import { post } from './api.js';

const need = result => { if (!result.ok) throw new Error(result.error?.message || '图片上传失败'); return result.data; };
export function dataUrlBlob(value) {
  const match = /^data:([^;,]+);base64,([\s\S]*)$/.exec(String(value || ''));
  if (!match) throw new Error('图片内容格式无效');
  const raw = atob(match[2]);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return new Blob([bytes], { type: match[1] });
}

export async function uploadImage(value, { purpose = 'image', filename, signal, send = post } = {}) {
  if (value?.upload_ref) return value;
  const blob = typeof value === 'string' ? dataUrlBlob(value) : value;
  if (!(blob instanceof Blob) || !blob.size) throw new Error('图片内容为空');
  const name = filename || blob.name || `image.${({ 'image/jpeg': 'jpg', 'image/gif': 'gif', 'image/webp': 'webp' })[blob.type] || 'png'}`;
  const opts = { timeout: 600000, signal };
  const started = need(await send('/api/uploads/start', { filename: name, mime: blob.type, total_bytes: blob.size, purpose }, opts));
  const chunkBytes = Math.min(16 * 1024 * 1024, Number(started.chunk_bytes));
  if (!started.upload_id || !Number.isInteger(chunkBytes) || chunkBytes < 1) throw new Error('服务器返回了无效的上传参数');
  for (let offset = 0, index = 0; offset < blob.size; offset += chunkBytes, index += 1) {
    const chunk = blob.slice(offset, Math.min(blob.size, offset + chunkBytes));
    let result;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      result = await send(`/api/uploads/chunk?upload_id=${encodeURIComponent(started.upload_id)}&index=${index}`, chunk,
        { ...opts, headers: { 'Content-Type': 'application/octet-stream' } });
      if (result.ok || signal?.aborted || ![0, 408, 503].includes(result.status)) break;
    }
    need(result);
  }
  const done = need(await send('/api/uploads/complete', { upload_id: started.upload_id }, opts));
  if (!done.upload_ref || Number(done.bytes) !== blob.size) throw new Error('服务器返回的图片大小不一致');
  return { upload_ref: done.upload_ref };
}

/** 旧小图内联兼容；超过 1MiB 的 base64 自动转引用，避免大 JSON 与重复编码。 */
export async function imageValue(value, purpose = 'image', options = {}) {
  if (typeof value === 'string' && value.length < 1024 * 1024) return value;
  return uploadImage(value, { ...options, purpose });
}

export async function uploadFiles(files, purpose, path, { send = post, ...options } = {}) {
  try {
    const images = [];
    for (const file of files || []) images.push({ ...(await uploadImage(file, { ...options, purpose, filename: file.name, send })), filename: file.name || 'image.png' });
    return await send(path, { images }, { timeout: 600000, signal: options.signal });
  } catch (error) {
    return { ok: false, status: 0, data: null, error: { message: error.message || '图片上传失败' } };
  }
}
