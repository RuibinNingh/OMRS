/**
 * 导出（P6 第 5 轮起）：POST /api/export 生成自包含 HTML 并存成文件。复习调度的「全题库导出」与「已有计划」的导出都走这里。
 * 返回 { ok, name, error }，不抛出，不写页面状态（页面自己显示结果）。
 */
import { downloadResponse } from '../core/download.js';

export async function requestExport(body, fallbackName, fetchImpl = globalThis.fetch) {
  try {
    const response = await fetchImpl('/api/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), credentials: 'same-origin' });
    if (!response.ok) {
      let message = '导出失败';
      try { message = (await response.json()).msg || message; } catch (error) { /* 非 JSON 错误体 */ }
      return { ok: false, name: '', error: message };
    }
    return { ok: true, name: await downloadResponse(response, fallbackName), error: '' };
  } catch (error) {
    return { ok: false, name: '', error: error?.message || '网络连接失败' };
  }
}
