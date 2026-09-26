/** 数据与存储的纯投影：占用、人类可读大小和压缩候选。 */
const number = value => Number.isFinite(Number(value)) ? Number(value) : 0;

export function formatBytes(bytes) {
  const n = Math.max(0, number(bytes));
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(2)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${Math.round(n)} B`;
}

export function optValues(summary, scan = null, job = null) {
  const sizes = summary?.sizes || {};
  const data = number(sizes.data_chain?.bytes);
  const files = number(sizes.question_files?.bytes);
  const images = number(sizes.question_images?.bytes);
  const common = [
    { key: 'data', label: '数据链', bytes: data, files: number(sizes.data_chain?.files) },
    { key: 'files', label: '题目文件', bytes: files, files: number(sizes.question_files?.files) },
  ];
  if (!scan) return { center: formatBytes(data + files + images), items: [
    ...common, { key: 'images', label: '题目图片', bytes: images, files: number(sizes.question_images?.files) },
  ] };
  const exact = scan.exact !== false;
  const base = exact ? number(scan.compressible_bytes) : number(scan.potential_bytes);
  const remaining = Math.max(0, base - number(job?.checked_bytes || job?.saved_bytes));
  return {
    center: job ? `已节省 ${formatBytes(job.saved_bytes)}`
      : exact ? `可压缩 ${formatBytes(scan.compressible_bytes)}` : `待深扫 ${scan.candidate_count || 0} 张`,
    items: [...common, { key: 'images', label: exact ? '可压缩大小' : '待深扫图片', bytes: remaining,
      files: number(scan.candidate_count), note: `原题图 ${formatBytes(images)}` }],
  };
}
