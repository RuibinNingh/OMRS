/** 错因只在记录区展示；普通备注、关联和未知子节保留。 */
export function notesWithoutCause(notes = '') {
  let fence = '', cause = false;
  const kept = [];
  for (const line of String(notes).split('\n')) {
    const marker = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
    if (marker) {
      if (!fence) fence = marker[1];
      else if (marker[1][0] === fence[0] && marker[1].length >= fence.length && !marker[2].trim()) fence = '';
    } else if (!fence && /^#{1,2}[ \t]+/.test(line)) {
      cause = /^##[ \t]+错因(?:记录)?[ \t]*\r?$/.test(line);
    }
    if (!cause) kept.push(line);
  }
  return kept.join('\n').trim();
}
