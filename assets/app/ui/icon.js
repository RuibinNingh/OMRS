/**
 * 图标：24 网格、1.5 描边、currentColor，内部自绘。sprite 由 installIcons() 注入一次（main.js / gallery.js 调用），
 * 组件里用 icon(name) 引用 <use href="#ic-name">。旧页面的 #i-* 导航图标不受影响。
 */
import { html, raw } from '../core/html.js';

const C = (cx, cy, r) => `M${cx + r} ${cy}a${r} ${r} 0 1 1-${2 * r} 0 ${r} ${r} 0 0 1 ${2 * r} 0z`;
const RING = C(12, 12, 9);

const PATHS = {
  check: 'M5 12.5l4.5 4.5L19 7.5',
  x: 'M6 6l12 12M18 6L6 18',
  stop: 'M7 7h10v10H7z',
  'arrow-up': 'M12 19V5M6 11l6-6 6 6',
  'arrow-down': 'M12 5v14M6 13l6 6 6-6',
  undo: 'M9 14 4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 0 11H11',
  message: 'M4 5h16v11H9l-5 4z',
  plus: 'M12 5v14M5 12h14',
  minus: 'M5 12h14',
  'chevron-down': 'M6 9l6 6 6-6',
  'chevron-up': 'M6 15l6-6 6 6',
  'chevron-left': 'M15 6l-6 6 6 6',
  'chevron-right': 'M9 6l6 6-6 6',
  'arrow-left': 'M19 12H5M11 6l-6 6 6 6',
  'arrow-right': 'M5 12h14M13 6l6 6-6 6',
  search: `${C(11, 11, 6)}M15.5 15.5L20 20`,
  filter: 'M4 5h16l-6 7.5V19l-4-2v-4.5z',
  sort: 'M8 5v14M4.5 15.5L8 19l3.5-3.5M16 19V5M12.5 8.5L16 5l3.5 3.5',
  refresh: 'M19.5 10A8 8 0 0 0 5.2 7.5M4.5 14a8 8 0 0 0 14.3 2.5M5 3.5v4h4M19 20.5v-4h-4',
  upload: 'M12 15V4M7.5 8.5L12 4l4.5 4.5M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3',
  download: 'M12 4v11M7.5 10.5L12 15l4.5-4.5M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3',
  file: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5',
  folder: 'M3.5 7a2 2 0 0 1 2-2h4l2 2.5h7a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z',
  edit: 'M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4',
  trash: 'M4 7h16M9.5 7V4.5h5V7M6.5 7l1 12.5a1.5 1.5 0 0 0 1.5 1.5h6a1.5 1.5 0 0 0 1.5-1.5l1-12.5M10 11v6M14 11v6',
  copy: 'M10 9h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1zM15 9V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h4',
  external: 'M14 4h6v6M20 4l-9 9M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4',
  eye: `M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z${C(12, 12, 3)}`,
  'eye-off': 'M3 3l18 18M10.5 5.7a9.9 9.9 0 0 1 1.5-.2c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-3 3.8M6.6 6.6C3.9 8.4 2.5 12 2.5 12s3.5 6.5 9.5 6.5c1.8 0 3.3-.5 4.6-1.3M9.9 9.9a3 3 0 0 0 4.2 4.2',
  info: `${RING}M12 11v5M12 7.8v.2`,
  'alert-triangle': 'M12 4L2.8 19.5h18.4zM12 10v4.5M12 17.2v.3',
  'alert-circle': `${RING}M12 7.5V13M12 16.2v.3`,
  'check-circle': `${RING}M8 12.5l2.8 2.8 5.7-5.8`,
  'help-circle': `${RING}M9.5 9.5a2.5 2.5 0 0 1 4.9.6c0 1.7-2.4 2.1-2.4 3.6M12 16.8v.2`,
  sliders: 'M4 7h9M17 7h3M4 17h3M11 17h9M15 5v4M9 15v4',
  'more-h': `${C(6, 12, 1)}${C(12, 12, 1)}${C(18, 12, 1)}`,
  menu: 'M4 6.5h16M4 12h16M4 17.5h16',
  grid: 'M4 4h6.5v6.5H4zM13.5 4H20v6.5h-6.5zM4 13.5h6.5V20H4zM13.5 13.5H20V20h-6.5z',
  list: 'M9 6.5h11M9 12h11M9 17.5h11M4.5 6.5h.01M4.5 12h.01M4.5 17.5h.01',
  table: 'M4 5h16v14H4zM4 10h16M4 14.5h16M10 10v9',
  calendar: 'M5 6h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1zM4 10h16M8.5 3.5v4M15.5 3.5v4',
  clock: `${RING}M12 7.5V12l3 2`,
  star: 'M12 3.8l2.5 5.2 5.6.7-4.1 3.9 1 5.6-5-2.7-5 2.7 1-5.6-4.1-3.9 5.6-.7z',
  bookmark: 'M6.5 4h11v16.5L12 16.5l-5.5 4z',
  tag: 'M3.5 12.5v-8a1 1 0 0 1 1-1h8l8 8-9 9zM8.5 8.5h.01',
  play: 'M8 5.5v13l10.5-6.5z',
  pause: 'M8.5 5.5v13M15.5 5.5v13',
  inbox: 'M4 13.5l2.5-8.5h11l2.5 8.5V19a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1zM4 13.5h4.5l1 2.5h5l1-2.5H20',
  image: 'M5 4.5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-13a1 1 0 0 1 1-1zM4 16l4.5-4.5L13 16l2.5-2.5L20 18M15.5 9h.01',
  paperclip: 'M8.5 12.5l6.7-6.7a3.5 3.5 0 0 1 5 5l-8.7 8.7a5 5 0 0 1-7.1-7.1l8.4-8.4M7.5 15.5l8.4-8.4',
  link: 'M10 14a4 4 0 0 0 5.7 0l3-3A4 4 0 0 0 13 5.3l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1',
  lock: 'M6 11h12v9H6zM8.5 11V8a3.5 3.5 0 0 1 7 0v3',
  sun: `${C(12, 12, 4)}M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4`,
  moon: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z',
  book: 'M4 5.5A1.5 1.5 0 0 1 5.5 4H11v16H5.5A1.5 1.5 0 0 1 4 18.5zM20 5.5A1.5 1.5 0 0 0 18.5 4H13v16h5.5a1.5 1.5 0 0 0 1.5-1.5z',
  chart: 'M5 20V11M12 20V5M19 20v-6',
  home: 'M4 11l8-7 8 7v8a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z',
  send: 'M20 4L4 11l6.5 2.5L13 20zM20 4l-9.5 9.5',
  print: 'M7 9V4h10v5M7 17H5a1 1 0 0 1-1-1v-5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v5a1 1 0 0 1-1 1h-2M7 14h10v6H7z',
  sparkle: 'M12 4l1.8 4.7 4.7 1.8-4.7 1.8L12 17l-1.8-4.7-4.7-1.8 4.7-1.8z',
  target: `${RING}${C(12, 12, 4.5)}M12 12h.01`,
};

export const ICON_NAMES = Object.freeze(Object.keys(PATHS));
const SVG_NS = 'http://www.w3.org/2000/svg';

export function installIcons(doc = document) {
  if (doc.getElementById('ui-icon-sprite')) return;
  const svg = doc.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('id', 'ui-icon-sprite');
  svg.setAttribute('class', 'ui-icon-sprite');
  svg.setAttribute('aria-hidden', 'true');
  for (const [name, d] of Object.entries(PATHS)) {
    const symbol = doc.createElementNS(SVG_NS, 'symbol');
    symbol.setAttribute('id', `ic-${name}`);
    symbol.setAttribute('viewBox', '0 0 24 24');
    const path = doc.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', d);
    symbol.append(path);
    svg.append(symbol);
  }
  doc.body.prepend(svg);
}

/** icon('search') / icon('x', {label:'关闭', size:'lg'})；无 label 时对读屏隐藏。 */
export function icon(name, { label, size } = {}) {
  if (!PATHS[name]) throw new Error(`未知图标：${name}`);
  const a11y = label ? html`role="img" aria-label="${label}"` : raw('aria-hidden="true"');
  return html`<svg class="ui-icon${size ? ` ui-icon--${size}` : ''}" ${a11y} focusable="false"><use href="#ic-${name}"></use></svg>`;
}
