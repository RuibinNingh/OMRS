/** 输入高度与可见视口高度：键盘出现时按真实可视区域计算，缩放时不补偿。 */
export function bindAssistantViewport(shell, inputOf, state) {
  let frame = 0;
  const rules = document.createElement('style');
  rules.textContent = '.content.is-assistant .ast { height: auto; } .content.is-assistant .ast-input { height: auto; }';
  document.head.append(rules);
  const shellRule = rules.sheet.cssRules[0].style;
  const inputRule = rules.sheet.cssRules[1].style;
  function sizeInput() {
    const input = inputOf();
    if (!input) return;
    inputRule.height = 'auto';
    const line = Number.parseFloat(getComputedStyle(input).lineHeight) || 20;
    const limit = line * (state.editorOpen ? 12 : matchMedia('(max-width: 760px)').matches ? 4 : 8);
    inputRule.height = `${Math.min(input.scrollHeight, limit)}px`;
  }
  function syncViewport() {
    if (frame) cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      frame = 0;
      const viewport = window.visualViewport;
      if (viewport && Math.abs(viewport.scale - 1) > 0.02) return;
      const bottom = viewport ? viewport.offsetTop + viewport.height : window.innerHeight;
      const top = shell.getBoundingClientRect().top;
      shellRule.height = `${Math.max(240, bottom - top - 8)}px`;
    });
  }
  syncViewport();
  window.visualViewport?.addEventListener('resize', syncViewport);
  window.visualViewport?.addEventListener('scroll', syncViewport);
  window.addEventListener('resize', syncViewport);
  return { sizeInput, syncViewport, dispose() {
    cancelAnimationFrame(frame);
    window.visualViewport?.removeEventListener('resize', syncViewport);
    window.visualViewport?.removeEventListener('scroll', syncViewport);
    window.removeEventListener('resize', syncViewport);
    rules.remove();
  } };
}
