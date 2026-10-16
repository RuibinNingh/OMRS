/** 重试身份使用安全随机字节；兼容没有 randomUUID 的局域网 HTTP。 */
export function requestId(random = globalThis.crypto) {
  if (!random?.getRandomValues) throw new Error('浏览器无法生成请求标识');
  const bytes = new Uint8Array(16);
  random.getRandomValues(bytes);
  return [...bytes].map(n => n.toString(16).padStart(2, '0')).join('');
}
