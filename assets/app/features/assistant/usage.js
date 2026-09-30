/** 一次运行的用量：按请求身份替换，缓存和思考均只作子集展示。 */
const count = value => Number.isSafeInteger(value) && value >= 0 ? value : null;
const pick = (row, modern, legacy) => Object.hasOwn(row, modern) ? count(row[modern])
  : Object.hasOwn(row, legacy) ? count(row[legacy]) : null;

export function usageRecord(raw = {}, scope = 'main') {
  const u = raw && typeof raw === 'object' ? raw : {};
  const input = pick(u, 'input_total', 'prompt');
  const output = pick(u, 'output_total', 'completion');
  let cache = pick(u, 'cache_read', 'cached');
  // 旧事件的 cached=0 曾把供应商未返回的字段也压成零，无法证明是明确零。
  if (!Object.hasOwn(u, 'cache_read') && cache === 0) cache = null;
  let reasoning = pick(u, 'reasoning_output', 'reasoning');
  let invalid = !!u.invalid || (Object.hasOwn(u, 'input_total') && input === null && u.input_total !== null)
    || (Object.hasOwn(u, 'output_total') && output === null && u.output_total !== null)
    || (Object.hasOwn(u, 'cache_read') && cache === null && u.cache_read !== null)
    || (Object.hasOwn(u, 'reasoning_output') && reasoning === null && u.reasoning_output !== null)
    || (Object.hasOwn(u, 'cached') && count(u.cached) === null) || (Object.hasOwn(u, 'reasoning') && reasoning === null);
  if (cache !== null && input !== null && cache > input) { cache = null; invalid = true; }
  if (reasoning !== null && output !== null && reasoning > output) { reasoning = null; invalid = true; }
  return { input, output, cache, reasoning, scope, source: u.source || (u.estimated ? 'estimated' : Object.keys(u).length ? 'provider' : 'missing'),
    estimated: !!u.estimated, invalid };
}

export function usageTotals(requests) {
  const rows = [...requests.values()];
  const sum = (items, key) => items.reduce((n, row) => n + (row[key] ?? 0), 0);
  const main = rows.filter(row => row.scope === 'main');
  const aux = rows.filter(row => row.scope === 'aux');
  const complete = items => items.length > 0 && items.every(row => row.input !== null && row.output !== null
    && !row.estimated && !row.invalid);
  const group = items => {
    const eligible = items.filter(row => row.input !== null && row.cache !== null && !row.invalid && !row.estimated);
    const cached = sum(eligible, 'cache');
    // 供应商 input 已含缓存；界面拆成互斥的输入、输出、缓存三项。
    return { input: sum(items, 'input'), output: sum(items, 'output'), cache: cached,
      uncached: sum(items, 'input') - cached, cacheKnown: eligible.length,
      cacheComplete: !!items.length && eligible.length === items.length,
      total: sum(items, 'input') + sum(items, 'output'), complete: complete(items), count: items.length,
      known: items.filter(row => row.input !== null && row.output !== null && !row.estimated && !row.invalid).length };
  };
  const eligible = main.filter(row => row.input !== null && row.cache !== null && !row.invalid && !row.estimated);
  const denominator = sum(eligible, 'input');
  const cache = { read: sum(eligible, 'cache'), input: denominator, covered: eligible.length, total: main.length,
    ratio: eligible.length ? (denominator ? sum(eligible, 'cache') / denominator : 0) : null,
    complete: !!main.length && eligible.length === main.length };
  return { main: group(main), aux: group(aux), all: group(rows), cache };
}
