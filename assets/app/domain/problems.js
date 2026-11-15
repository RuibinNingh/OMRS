/** 问题领域接口；幂等编号由草稿保存并用于失败重试。 */
import { get, post } from '../core/api.js';
export { requestId } from '../core/request-id.js';
import { requestId } from '../core/request-id.js';
import { problemMarkdown } from './problem-markdown.js';
export const statuses = { analyzing: '待分析', working: '处理中', verifying: '待验证', resolved: '已解决', parked: '搁置' };
export async function read(path) {
  const res = await get(path);
  if (!res.ok) throw new Error(res.error?.message || '读取失败');
  return res.data;
}
export async function write(action, data) {
  const res = await post('/api/problems/write', { action, data });
  if (!res.ok) throw new Error(res.error?.message || '保存失败');
  return res.data;
}
export const markdown = problemMarkdown;
export async function upload(file) {
  if (file.size > 8 * 1024 * 1024) throw new Error('附件超过8MiB');
  const data = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = () => reject(new Error('附件读取失败'));
    reader.readAsDataURL(file);
  });
  return (await write('add_problem_asset', { data_base64: data, request_id: requestId() })).asset;
}
