const assert = require('node:assert/strict');
const test = require('node:test');
const { fbSessionProgress, fbRowsForSession, fbRowsForSubmit } = require('../assets/feedback.js');

test('session progress keeps session order and filters already submitted UIDs', () => {
  const session = {
    count: 4,
    uids: ['U1', 'U2', 'U3', 'U4'],
    feedback_uids: ['U3', 'U3', 'U1'],
  };

  assert.deepEqual(fbSessionProgress(session), {
    total: 4,
    feedback_uids: ['U1', 'U3'],
    pending_uids: ['U2', 'U4'],
    feedback_count: 2,
    pending_count: 2,
    complete: false,
  });
  const rows = fbRowsForSession(session);
  assert.deepEqual(rows.map(row => row.uid), ['U2', 'U4']);
  assert.deepEqual(rows.map(row => row.number), [2, 4]);
});

test('completed session produces no editable feedback rows', () => {
  const session = { uids: ['U1', 'U2'], feedback_uids: ['U1', 'U2'] };

  assert.equal(fbSessionProgress(session).complete, true);
  assert.deepEqual(fbRowsForSession(session), []);
});

test('partial submit keeps unjudged rows for the next batch', () => {
  const rows = [
    { uid: 'U1', correct: true },
    { uid: 'U2', correct: null },
    { uid: 'U3', correct: false },
    { uid: '', correct: null },
  ];

  assert.deepEqual(fbRowsForSubmit(rows), {
    ready: [rows[0], rows[2]],
    pending: [rows[1], rows[3]],
  });
});
