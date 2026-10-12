/** 非敏感网关展示契约；面板地址只从配置派生，不信任网关返回的链接。 */
export function sameService(left, right) {
  return !!left && !!right && ['mode', 'base_url', 'api_key_configured', 'api_key_fingerprint', 'allow_private_targets', 'revision']
    .every(name => left[name] === right[name]);
}

export function panelUrl(config) {
  try {
    const raw = String(config?.base_url || '');
    if (/[\\\s%]/.test(raw)) return '';
    const target = new URL(raw);
    const path = raw.match(/^https?:\/\/[^/]+(\/[^?#]*)?$/)?.[1] || '/';
    if (!['http:', 'https:'].includes(target.protocol) || target.username || target.password || target.search || target.hash
      || !/^(?:\/[A-Za-z0-9._~-]+)*\/?$/.test(path) || path.split('/').some(part => part === '.' || part === '..')) return '';
    return `${target.origin}${path.replace(/\/$/, '')}/`;
  } catch { return ''; }
}

export function serviceStatus(status) {
  const account = status?.observations?.account?.state;
  const signing = status?.observations?.signing?.state;
  const accountText = ({ valid: '有效', expired: '已过期', invalid: '失效', missing: '缺失', unknown: '未知' })[account] || '未知';
  const signingText = ({ valid: '有效', invalid: '失效', missing: '缺失', unknown: '未知' })[signing] || '未知';
  return `账号：${accountText}；签名：${signingText}。${status?.local_session_ready ? '网关本地会话已就绪' : '网关本地会话未就绪'}（不是上游实时验证）。`;
}
