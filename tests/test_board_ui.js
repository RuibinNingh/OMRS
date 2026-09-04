const assert = require('node:assert/strict');
const test = require('node:test');

global.document = {
  addEventListener() {},
  querySelectorAll() { return []; },
};

const { boardMoveItems, boardUniqueUids } = require('../assets/board.js');

test('board item movement handles up/down and invalid positions', () => {
  const items = [{ uid: 'A' }, { uid: 'B' }, { uid: 'C' }];
  assert.deepEqual(boardMoveItems(items, 2, 0).map(item => item.uid), ['C', 'A', 'B']);
  assert.deepEqual(boardMoveItems(items, 0, 1).map(item => item.uid), ['B', 'A', 'C']);
  assert.deepEqual(boardMoveItems(items, -1, 1), items);
});

test('board quick-add UID normalization removes duplicates and blanks', () => {
  assert.deepEqual(boardUniqueUids([' A ', '', 'A', null, 'B']), ['A', 'B']);
});
