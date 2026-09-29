/** 可输入的共享建议框：保留原生 input 与输入法行为，建议层挂到 body 避开裁剪容器。 */
let nextMenuId = 0;
export function createCombobox(host, { options, onSelect } = {}) {
  const menu = document.createElement('div');
  menu.className = 'ui-combobox-menu';
  menu.id = `ui-combobox-menu-${++nextMenuId}`;
  menu.setAttribute('role', 'listbox');
  menu.hidden = true;
  document.body.append(menu);
  let active = null;
  let rows = [];
  let selected = 0;
  let composing = false;

  const close = () => {
    if (active) { active.setAttribute('aria-expanded', 'false'); active.removeAttribute('aria-activedescendant'); }
    active = null;
    menu.hidden = true;
    menu.replaceChildren();
  };
  const position = () => {
    if (!active || menu.hidden) return;
    const rect = active.getBoundingClientRect();
    const mobile = matchMedia('(max-width: 760px)').matches;
    if (mobile) {
      const viewport = window.visualViewport;
      menu.style.left = '';
      menu.style.top = '';
      menu.style.width = '';
      menu.style.bottom = `${Math.max(0, innerHeight - ((viewport?.offsetTop || 0) + (viewport?.height || innerHeight)))}px`;
      menu.style.maxHeight = `${Math.max(100, Math.round((viewport?.height || innerHeight) * .45))}px`;
    } else {
      menu.style.bottom = '';
      menu.style.maxHeight = '';
      menu.style.left = `${Math.max(8, rect.left)}px`;
      menu.style.top = `${Math.min(rect.bottom + 4, innerHeight - 60)}px`;
      menu.style.width = `${Math.max(180, rect.width)}px`;
    }
  };
  const highlight = () => {
    [...menu.querySelectorAll('[role="option"]')].forEach((node, index) => {
      node.classList.toggle('is-active', index === selected);
      node.setAttribute('aria-selected', index === selected ? 'true' : 'false');
    });
    if (active) {
      if (rows.length) active.setAttribute('aria-activedescendant', `${menu.id}-option-${selected}`);
      else active.removeAttribute('aria-activedescendant');
    }
  };
  const paint = input => {
    if (!input || input.disabled || composing) return;
    if (active && active !== input) {
      active.setAttribute('aria-expanded', 'false');
      active.removeAttribute('aria-activedescendant');
    }
    active = input;
    const multi = input.dataset.combobox === 'tags';
    const query = (multi ? input.value.split(/[,，]/).at(-1) : input.value).trim();
    const source = options?.(input.dataset.combobox, input) || [];
    rows = [...new Set(source.map(String).filter(Boolean))]
      .filter(value => !query || value.toLocaleLowerCase().includes(query.toLocaleLowerCase()))
      .slice(0, 30);
    if (query && !rows.includes(query)) rows.push(query);
    menu.replaceChildren();
    const title = document.createElement('div');
    title.className = 'ui-combobox-menu__title';
    title.textContent = input.dataset.combobox === 'category' ? '当前科目的分类' : '可选建议';
    menu.append(title);
    if (!rows.length) {
      const empty = document.createElement('p');
      empty.className = 'ui-combobox-menu__empty';
      empty.textContent = '暂无建议，可以直接输入新名称';
      menu.append(empty);
    }
    rows.forEach((value, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'ui-combobox-menu__option';
      button.id = `${menu.id}-option-${index}`;
      button.setAttribute('role', 'option');
      button.dataset.index = String(index);
      button.textContent = value === query && !source.includes(query) ? `使用「${value}」` : value;
      menu.append(button);
    });
    selected = 0;
    highlight();
    menu.hidden = false;
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-controls', menu.id);
    input.setAttribute('aria-expanded', 'true');
    position();
  };
  const choose = index => {
    const value = rows[index];
    if (!active || value == null) return;
    const input = active;
    if (input.dataset.combobox === 'tags') {
      const previous = input.value.split(/[,，]/).slice(0, -1).map(part => part.trim()).filter(Boolean);
      input.value = [...new Set([...previous, value])].join(', ');
    } else input.value = value;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    onSelect?.(input, value);
    close();
    input.focus();
  };
  const fromEvent = event => event.target.closest?.('[data-combobox]');
  const onFocus = event => { const input = fromEvent(event); if (input && host.contains(input)) paint(input); };
  const onInput = event => { const input = fromEvent(event); if (input && host.contains(input)) paint(input); };
  const onKey = event => {
    const input = fromEvent(event);
    if (!input || input !== active || composing || event.isComposing) return;
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); return; }
    if (event.key === 'Tab') { close(); return; }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      selected = (selected + (event.key === 'ArrowDown' ? 1 : -1) + rows.length) % Math.max(1, rows.length);
      highlight();
      menu.querySelector('.is-active')?.scrollIntoView({ block: 'nearest' });
    } else if (event.key === 'Enter' && !menu.hidden && rows.length) {
      event.preventDefault();
      choose(selected);
    }
  };
  const onOutside = event => { if (active && !menu.contains(event.target) && event.target !== active) close(); };
  const onMenu = event => { const option = event.target.closest('[data-index]'); if (option) choose(Number(option.dataset.index)); };
  host.addEventListener('focusin', onFocus);
  host.addEventListener('input', onInput);
  host.addEventListener('keydown', onKey);
  const onCompositionStart = () => { composing = true; };
  const onCompositionEnd = event => { composing = false; const input = fromEvent(event); if (input) paint(input); };
  host.addEventListener('compositionstart', onCompositionStart);
  host.addEventListener('compositionend', onCompositionEnd);
  document.addEventListener('pointerdown', onOutside);
  menu.addEventListener('pointerdown', event => event.preventDefault());
  menu.addEventListener('click', onMenu);
  window.addEventListener('resize', position);
  window.addEventListener('scroll', position, true);
  window.visualViewport?.addEventListener('resize', position);
  return { close, sync() { if (active && !host.contains(active)) close(); else position(); }, dispose() {
    close();
    host.removeEventListener('focusin', onFocus);
    host.removeEventListener('input', onInput);
    host.removeEventListener('keydown', onKey);
    host.removeEventListener('compositionstart', onCompositionStart);
    host.removeEventListener('compositionend', onCompositionEnd);
    document.removeEventListener('pointerdown', onOutside);
    window.removeEventListener('resize', position);
    window.removeEventListener('scroll', position, true);
    window.visualViewport?.removeEventListener('resize', position);
    menu.remove();
  } };
}
