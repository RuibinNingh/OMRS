/**
 * 把 fetch 的响应存成文件：文件名优先取 Content-Disposition（含 RFC 5987 的 filename*），否则用 fallbackName。
 * 返回实际文件名。与旧 export.js 的 downloadExportResponse 同一做法，但不写任何页面状态。
 */
export function fileNameOf(response, fallbackName) {
  const disposition = response?.headers?.get?.('Content-Disposition') || '';
  const matched = disposition.match(/filename\*=UTF-8''([^;]+)/i) || disposition.match(/filename="([^"]+)"/i);
  if (!matched) return fallbackName;
  try { return decodeURIComponent(matched[1]); } catch (error) { return matched[1]; }
}

export async function downloadResponse(response, fallbackName, doc = globalThis.document) {
  const name = fileNameOf(response, fallbackName);
  const url = URL.createObjectURL(await response.blob());
  const link = doc.createElement('a');
  link.href = url;
  link.download = name;
  link.hidden = true;
  doc.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return name;
}
