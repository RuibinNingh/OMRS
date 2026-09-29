/** 助手输入与拖放事件；卸载页面时成组释放。 */
export function bindAssistantInteractions(root, main, S, { send, addFiles, sizeInput, syncViewport, schedule }) {
  let dragDepth = 0;
  const onKey = event => {
    if (event.target.id !== 'ast-input' || event.key !== 'Enter' || event.shiftKey || event.isComposing || S.composing || event.keyCode === 229 || performance.now() - (S.imeEndedAt || -1000) < 100 || matchMedia('(max-width: 760px)').matches) return;
    event.preventDefault();
    send(event.target.value);
  };
  const onInput = event => { if (event.target.id !== 'ast-input') return; S.inputValue = event.target.value; sizeInput(); schedule(); };
  const onFocus = event => { if (event.target.id === 'ast-input') { S.inputActive = true; schedule(); syncViewport(); } };
  const onBlur = event => { if (event.target.id === 'ast-input') { S.inputActive = false; schedule(); } };
  const onCompositionStart = event => { if (event.target.id === 'ast-input') S.composing = true; };
  const onCompositionEnd = event => { if (event.target.id === 'ast-input') { S.composing = false; S.imeEndedAt = performance.now(); } };
  const onPaste = event => {
    if (event.target?.id !== 'ast-input') return;
    const files = [...(event.clipboardData?.items || [])].filter(item => item.kind === 'file' && item.type.startsWith('image/')).map(item => item.getAsFile()).filter(Boolean);
    if (!files.length) return;
    event.preventDefault();
    addFiles(files);
  };
  const hasFiles = event => [...(event.dataTransfer?.types || [])].includes('Files');
  const onDragEnter = event => { if (!hasFiles(event)) return; event.preventDefault(); dragDepth += 1; main.classList.add('is-dragging'); };
  const onDragLeave = event => { if (!hasFiles(event)) return; dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) main.classList.remove('is-dragging'); };
  const onDragOver = event => { if (hasFiles(event)) { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; } };
  const onDrop = event => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth = 0; main.classList.remove('is-dragging');
    addFiles(event.dataTransfer.files);
  };
  const rootEvents = { keydown: onKey, input: onInput, focusin: onFocus, focusout: onBlur, compositionstart: onCompositionStart, compositionend: onCompositionEnd, paste: onPaste };
  const mainEvents = { dragenter: onDragEnter, dragleave: onDragLeave, dragover: onDragOver, drop: onDrop };
  Object.entries(rootEvents).forEach(([name, fn]) => root.addEventListener(name, fn));
  Object.entries(mainEvents).forEach(([name, fn]) => main.addEventListener(name, fn));
  return () => {
    Object.entries(rootEvents).forEach(([name, fn]) => root.removeEventListener(name, fn));
    Object.entries(mainEvents).forEach(([name, fn]) => main.removeEventListener(name, fn));
  };
}
