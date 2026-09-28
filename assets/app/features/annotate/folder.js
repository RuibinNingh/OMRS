/**
 * 批量入口：从拖放（含整个文件夹，递归）或文件夹选择框里收集图片文件，按相对路径自然排序后上传。
 * 截图文件名多带序号（Screenshot_2026…_1、_2、_10），自然排序让上传顺序与文件夹里看到的一致。
 */
export const IMAGE_TYPES = Object.freeze(['image/png', 'image/jpeg', 'image/gif']);
const EXT = /\.(png|jpe?g|gif)$/i;

export const isImage = file => IMAGE_TYPES.includes(String(file?.type || '').toLowerCase()) || EXT.test(String(file?.name || ''));
const pathOf = file => file.relPath || file.webkitRelativePath || file.name || '';
const collator = new Intl.Collator('zh-CN', { numeric: true, sensitivity: 'base' });

/** 过滤出图片并按路径自然排序；返回 { files, skipped }。 */
export function imageFiles(list) {
  const all = [...(list || [])];
  const files = all.filter(isImage).sort((a, b) => collator.compare(pathOf(a), pathOf(b)));
  return { files, skipped: all.length - files.length };
}

function readAll(reader) {
  return new Promise(resolve => {
    const out = [];
    const next = () => reader.readEntries(batch => { if (!batch.length) resolve(out); else { out.push(...batch); next(); } }, () => resolve(out));
    next();
  });
}

async function walk(entry, prefix, out) {
  if (entry.isFile) {
    const file = await new Promise(resolve => entry.file(resolve, () => resolve(null)));
    if (file) { file.relPath = `${prefix}${file.name}`; out.push(file); }
  } else if (entry.isDirectory) {
    for (const child of await readAll(entry.createReader())) await walk(child, `${prefix}${entry.name}/`, out);
  }
}

/** DataTransfer → File[]：有文件夹时递归展开；浏览器不支持 webkitGetAsEntry 时退回 dataTransfer.files。 */
export async function filesFromDrop(dataTransfer) {
  const items = [...(dataTransfer?.items || [])].filter(item => item.kind === 'file');
  const entries = items.map(item => item.webkitGetAsEntry?.()).filter(Boolean);
  if (!entries.length || !entries.some(entry => entry.isDirectory)) return [...(dataTransfer?.files || [])];
  const out = [];
  for (const entry of entries) await walk(entry, '', out);
  return out;
}
