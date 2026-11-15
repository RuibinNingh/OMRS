/** 问题说明复用备注的安全排版，PA附件仍走问题库受控入口。 */
import { richMarkdown } from './rich-markdown.js';

export function problemMarkdown(source = '') {
  return richMarkdown(source).replace(/\/api\/image\?name=(PA-[a-f0-9]{64}\.(?:svg|png|jpg|gif|webp))/g, '/api/problem-asset?name=$1');
}
