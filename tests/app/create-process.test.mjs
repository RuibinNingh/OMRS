import test from 'node:test';
import assert from 'node:assert/strict';
import { draggedBox, groupCards, newRegion, pointInImage, statusAfterEdit, transferBoxes } from '../../assets/app/features/create/process-state.js';

test('框位坐标约束：画框、移动与八向缩放不越界', () => {
  assert.deepEqual(pointInImage(140, -10, { left: 100, top: 0, width: 100, height: 200 }), { x: .4, y: 0 });
  assert.deepEqual(draggedBox('draw', { x: .8, y: .7 }, { x: .2, y: .1 }), { x: .2, y: .1, w: .6000000000000001, h: .6 });
  assert.deepEqual(draggedBox('move', { x: .5, y: .5 }, { x: 1, y: 1 }, { x: .2, y: .2, w: .3, h: .4 }), { x: .7, y: .6, w: .3, h: .4 });
  const resized = draggedBox('resize', { x: .5, y: .5 }, { x: 1, y: 1 }, { x: .2, y: .2, w: .3, h: .4 }, 'se');
  assert.equal(resized.x + resized.w, 1);
  assert.equal(resized.y + resized.h, 1);
});

test('沿用框位按顶部像素锚定，其他框按比例；新框不继承识别结果', () => {
  const from = { height: 1000, regions: [
    newRegion(1, 'question', .1, .2, .8, .1, { origin: 'ai', text: '旧题面', convert: 'text' }, () => 'old-q'),
    newRegion(1, 'answer', .1, .5, .8, .2, {}, () => 'old-a'),
  ] };
  let serial = 0;
  const [question, answer] = transferBoxes(from, { height: 2000 }, () => `new-${++serial}`);
  assert.equal(question.y, .1);
  assert.equal(question.h, .05);
  assert.equal(question.convert, 'auto');
  assert.equal(question.origin, 'manual');
  assert.equal(question.text, null);
  assert.equal(answer.y, .5);
  assert.equal(answer.h, .2);
  assert.notEqual(question.id, answer.id);
});

test('题卡分组、待处理状态与已录入状态保持旧契约', () => {
  const regions = [{ card: 2 }, { card: 1 }, { card: 2 }];
  assert.deepEqual(groupCards({ regions }).map(([card, rows]) => [card, rows.length]), [[1, 1], [2, 2]]);
  assert.equal(statusAfterEdit({ regions, status: 'pending' }), 'boxed');
  assert.equal(statusAfterEdit({ regions: [], status: 'boxed' }), 'pending');
  assert.equal(statusAfterEdit({ regions, status: 'ready' }), 'boxed');
});
