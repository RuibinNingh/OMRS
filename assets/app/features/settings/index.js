/** 设置页契约：六分区装配、局部导航与页面生命周期。 */
import { morph } from '../../core/dom.js';
import { view } from './view.js';
import { createAppearance } from './appearance.js';
import { createAccess } from './access.js';
import { createAi } from './ai.js';
import { createAgent } from './agent.js';
import { createStorage } from './storage.js';
import { createService } from './service.js';
import { SECTIONS, SECTION_KEY, sectionOf } from './state.js';

let root = null;
let onKeys = null;
let appearance = null;
let access = null;
let ai = null;
let agent = null;
let storage = null;
let service = null;
let current = 'appearance';

function openSection(value, { focus = false } = {}) {
  current = sectionOf(value);
  try { localStorage.setItem(SECTION_KEY, current); } catch { /* 本次切换仍有效。 */ }
  root?.querySelectorAll('.st-nav-item').forEach(tab => {
    const active = tab.dataset.stSection === current;
    tab.setAttribute('aria-selected', String(active));
    tab.tabIndex = active ? 0 : -1;
    if (active && focus) tab.focus();
  });
  root?.querySelectorAll('.st-section').forEach(panel => panel.classList.toggle('active', panel.id === `st-sec-${current}`));
  return current;
}

function navKey(event) {
  const step = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[event.key];
  if (!step && event.key !== 'Home' && event.key !== 'End') return;
  event.preventDefault();
  const index = SECTIONS.indexOf(current);
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? SECTIONS.length - 1
    : (index + step + SECTIONS.length) % SECTIONS.length;
  openSection(SECTIONS[next], { focus: true });
}

export const page = {
  id: 'settings', title: '设置',
  mount(host, ctx) {
    root = host.querySelector('#st-app') || host;
    morph(root, view());
    appearance = createAppearance(root, ctx.bus);
    service = createService(root);
    access = createAccess(root, id => service?.restart(id));
    ai = createAi(root);
    agent = createAgent(root, ctx.bus);
    storage = createStorage(root);
    let saved = '';
    try { saved = localStorage.getItem(SECTION_KEY) || ''; } catch { /* 使用默认分区。 */ }
    openSection(saved);
    appearance.sync();
    onKeys = event => {
      if (event.target.closest('.st-nav')) navKey(event);
      else if (event.target.matches('[role="button"][data-action]') && (event.key === 'Enter' || event.key === ' ')) {
        event.preventDefault();
        event.target.click();
      }
    };
    root.addEventListener('keydown', onKeys);
    access.load();
    ai.load();
    agent.load();
    storage.load();
    service.load();
    return () => {
      root?.removeEventListener('keydown', onKeys);
      access?.dispose(); ai?.dispose(); agent?.dispose(); storage?.dispose(); service?.dispose();
      root = null; onKeys = null; appearance = null; access = null; ai = null; agent = null; storage = null; service = null;
    };
  },
  actions: {
    section: ({ arg }) => openSection(arg),
    theme: ({ arg }) => appearance?.theme(arg),
    density: ({ arg }) => appearance?.density(arg),
    invert: ({ el }) => appearance?.invert(el.checked),
    timeZone: ({ value }) => appearance?.timeZone(value),
    savePin: () => access?.savePin(),
    logout: () => access?.logout(),
    disablePin: () => access?.disablePin(),
    networkChanged: () => access?.networkChanged(),
    saveAccess: () => access?.saveAccess(),
    toggleKey: () => ai?.toggleKey(),
    clearKey: () => ai?.clearKey(),
    saveAi: () => ai?.save(),
    saveAgent: () => agent?.save(),
    agentTest: () => agent?.test(),
    agentToggleKey: () => agent?.toggleKey(),
    agentClearKey: () => agent?.clearKey(),
    backupExport: () => storage?.backupExport(),
    backupPick: () => root?.querySelector('#opt-import-file')?.click(),
    backupImport: ({ event }) => storage?.backupImport(event),
    scanImages: () => storage?.scanImages(),
    compress: () => storage?.compress(),
    refreshStatus: () => service?.load(),
    restart: () => service?.restart(),
    sourceExport: () => service?.sourceExport(),
  },
};
