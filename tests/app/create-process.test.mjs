import test from 'node:test';
import assert from 'node:assert/strict';
import { draggedBox, groupCards, pointInImage, statusAfterEdit } from '../../assets/app/features/create/process-state.js';
import { processView } from '../../assets/app/features/create/process-view.js';
import { gridView } from '../../assets/app/features/create/grid-view.js';

test('框位坐标约束：画框、移动与八向缩放不越界', () => {
  assert.deepEqual(pointInImage(140, -10, { left: 100, top: 0, width: 100, height: 200 }), { x: .4, y: 0 });
  assert.deepEqual(draggedBox('draw', { x: .8, y: .7 }, { x: .2, y: .1 }), { x: .2, y: .1, w: .6000000000000001, h: .6 });
  assert.deepEqual(draggedBox('move', { x: .5, y: .5 }, { x: 1, y: 1 }, { x: .2, y: .2, w: .3, h: .4 }), { x: .7, y: .6, w: .3, h: .4 });
  const resized = draggedBox('resize', { x: .5, y: .5 }, { x: 1, y: 1 }, { x: .2, y: .2, w: .3, h: .4 }, 'se');
  assert.equal(resized.x + resized.w, 1);
  assert.equal(resized.y + resized.h, 1);
});

test('框选工作区和批量栏不再提供模板或沿用框位入口', () => {
  const process = processView().text;
  const grid = gridView({ items: [{ id: 'a', file: '题图.png', status: 'pending', width: 10, height: 10, regions: [] }], selected: new Set(['a']), stage: 'upload' }).text;
  for (const markup of [process, grid]) {
    assert.doesNotMatch(markup, /模板框选|沿用上一张框位|create\.processApplyLast|create\.gridApplyLast|data-arg="template"/);
    assert.match(markup, /AI 框选/);
  }
  assert.match(process, /重置此图/);
});

test('题卡分组、待处理状态与已录入状态保持旧契约', () => {
  const regions = [{ card: 2 }, { card: 1 }, { card: 2 }];
  assert.deepEqual(groupCards({ regions }).map(([card, rows]) => [card, rows.length]), [[1, 1], [2, 2]]);
  assert.equal(statusAfterEdit({ regions, status: 'pending' }), 'boxed');
  assert.equal(statusAfterEdit({ regions: [], status: 'boxed' }), 'pending');
  assert.equal(statusAfterEdit({ regions, status: 'ready' }), 'boxed');
});
