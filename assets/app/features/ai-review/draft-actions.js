/** 迁入中心的原草稿动作保持字段、图块和训练框编辑能力。 */
export function draftActions(editor) {
  const call = (method, ...args) => editor()?.[method]?.(...args);
  return {
    draftReload: () => call('reload'), draftRetry: () => call('reloadDetail'), draftReloadDetail: () => call('reloadDetail'),
    draftFilter: ({ arg, el }) => call('filter', el?.value || arg), draftOpen: ({ arg }) => call('open', arg),
    draftNavigate: ({ arg }) => call('navigate', arg), draftToggleQueue: () => call('toggleQueue'), draftToggleSource: () => call('toggleSource'),
    draftWorkspace: ({ arg }) => call('workspaceMode', arg), draftEditBlock: ({ arg }) => call('editBlock', arg), draftEditImage: ({ arg }) => call('editImage', arg),
    draftBlockMenu: ({ arg, el }) => call('blockMenu', arg, el), draftQueueMenu: ({ el }) => call('queueMenu', el),
    draftLocateIssue: () => call('locateIssue'), draftEditFields: () => call('editFields'), draftField: ({ arg, el }) => call('field', arg, el.value),
    draftLabels: ({ el }) => call('openLabels', el), draftSourceAdd: () => call('sourceAdd'), draftSourceRemove: ({ arg }) => call('sourceRemove', arg),
    draftPreviewSource: ({ arg }) => call('previewSource', arg), draftBlockText: ({ arg, el }) => call('blockField', arg, 'text', el.value),
    draftBlockNote: ({ arg, el }) => call('blockField', arg, 'note', el.value), draftAddText: ({ arg }) => call('addBlock', arg, 'text'),
    draftAddImage: ({ arg, el }) => call('addImage', arg, el), draftWhole: ({ arg }) => call('whole', arg),
    draftCanvasImage: ({ arg }) => call('canvasImage', arg), draftCanvasMode: ({ arg }) => call('canvasMode', arg),
    draftCanvasBlock: ({ el }) => call('canvasBlock', el.value), draftDrawSection: ({ arg }) => call('drawSection', arg),
    draftClearBox: ({ arg }) => call('clearBox', arg), draftTrainingSection: ({ arg, el }) => call('trainingSection', arg, el.value),
    draftTrainingRemove: ({ arg }) => call('trainingRemove', arg), draftTrainToggle: ({ arg }) => call('trainToggle', arg),
    draftExtract: ({ arg }) => call('extract', arg), draftDetect: ({ arg }) => call('detect', arg),
    draftAcceptCandidate: ({ arg }) => call('acceptCandidate', arg), draftRetryTraining: () => call('retryTraining'),
    draftCleanup: () => call('cleanup'), draftSave: () => call('save'), draftCommit: () => call('commit'),
    draftDiscard: () => call('discard'), draftQuestion: () => call('openQuestion'),
  };
}
