/** 设置页纯规则：访问范围、PIN 状态、分区导航。 */
export const SECTIONS = ['appearance', 'access', 'ai', 'data', 'service'];
export const SECTION_KEY = 'omrs-settings-section';
const asNumber = (value, fallback) => Number.isFinite(Number(value)) ? Number(value) : fallback;

export function parseLanCidrs(text) {
  return String(text || '').split(/[,，\n]/).map(v => v.trim()).filter(Boolean);
}

// 监听地址只在重启后变化，因此优先比较运行中的 listen_external。
export function runningListenExternal(state) {
  return typeof state.status?.listen_external === 'boolean'
    ? state.status.listen_external : !!state.cfg?.allow_external;
}

export function networkNeedsRestart(allowExternal, state) {
  return !!allowExternal !== runningListenExternal(state);
}

export function describeAccess(state) {
  const { cfg, auth } = state;
  if (!cfg) {
    return { level: 'error', summary: '无法读取访问配置。请刷新页面；仍失败时检查服务日志。',
      listen: '—', listenNote: '', pin: '—', cidrs: '—', you: '—' };
  }
  const cidrs = Array.isArray(cfg.lan_pin_exempt_cidrs) ? cfg.lan_pin_exempt_cidrs : [];
  const pin = !!cfg.pin_configured;
  const configured = !!cfg.allow_external;
  const running = runningListenExternal(state);
  let level = 'guarded';
  let summary;
  if (!running) {
    level = 'local';
    summary = '现在只有这台电脑能打开 OMRS。';
  } else if (cidrs.length && pin) {
    level = 'open';
    summary = `局域网设备可以访问：${cidrs.join('、')} 内的设备直连免 PIN，其他设备须输入 PIN。`;
  } else if (cidrs.length) {
    level = 'open';
    summary = `局域网设备可以访问：只有 ${cidrs.join('、')} 内的设备能直连（免 PIN），其他设备会被拒绝。`;
  } else if (pin) {
    summary = '局域网设备可以访问，但必须先输入 PIN。';
  } else {
    summary = '服务已监听局域网，但还没有设置 PIN，其他设备都会被拒绝。';
  }
  let listenNote = '';
  if (running !== configured) {
    summary += configured ? '已保存「允许局域网访问」，重启服务后生效。' : '已关闭局域网访问，重启服务后生效。';
    listenNote = configured ? '重启后改为所有网卡' : '重启后改为仅本机';
  }
  const you = !auth ? '未知'
    : !auth.remote ? '本机直连，免 PIN'
    : auth.lan_pin_exempt ? '免 PIN 网段直连'
    : auth.authenticated ? '远端，已用 PIN 登录' : '远端，未登录';
  return {
    level, summary, listenNote, you,
    listen: running ? '所有网卡（局域网可达）' : '仅本机 127.0.0.1',
    pin: pin ? `已设置，空闲 ${asNumber(cfg.idle_minutes, 30)} 分钟后需重新登录` : '未设置',
    cidrs: cidrs.length ? cidrs.join('、') : '未设置',
  };
}

export function pinControlState(state) {
  const { cfg, auth } = state;
  const configured = !!cfg?.pin_configured;
  const remote = !!auth?.remote;
  const cidrs = Array.isArray(cfg?.lan_pin_exempt_cidrs) ? cfg.lan_pin_exempt_cidrs : [];
  const disableBlocked = !configured ? ''
    : remote ? '只能在本机上停用 PIN。'
    : cfg?.allow_external ? '先关闭局域网访问后才能停用 PIN。' : '';
  let statusText = configured ? 'PIN 已设置。' : cidrs.length
    ? 'PIN 尚未设置；目前只有免 PIN 网段内的设备能从其他电脑或手机访问。'
    : 'PIN 尚未设置。开启局域网访问前，请先设置 PIN 或填写免 PIN 网段。';
  if (disableBlocked) statusText += disableBlocked;
  return {
    configured, remote, disableBlocked, statusText,
    needCurrent: remote && configured,
    showLogout: remote && !auth?.lan_pin_exempt && !!auth?.authenticated,
    showDisable: configured && !remote,
    newLabel: configured ? '新 PIN' : '设置 PIN',
    newHint: configured
      ? '留空则只更新空闲时间。更换 PIN 后，所有远端设备都要重新登录。'
      : '4 到 12 位数字。设置后，不在免 PIN 网段内的设备须输入它才能访问。',
  };
}

export function sectionOf(value) { return SECTIONS.includes(value) ? value : SECTIONS[0]; }
