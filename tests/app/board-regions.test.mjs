/** 展示板改版的页面结构与数据边界。 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { boardStatusModel } from '../../assets/app/features/board/model.js';
import * as S from '../../assets/app/features/board/state.js';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const source = name => fs.readFileSync(path.join(root, 'assets/app/features/board', name), 'utf8');
const VIEW = source('view.js') + source('view-panel.js');   // 工作台 + 题目面板（列表 / 详情）
const PAGE = source('index.js');
const DETAIL = source('detail.js');
const PREVIEW = source('preview.js');
const summary = extra => ({ pages: 0, count: 0, new_count: 0, changed_count: 0, ...extra });

test('打印范围与补印位置沿用原状态机', () => {
  const board = { items: Array(9), printed_summary: summary({ pages: 2, count: 5, new_count: 4, cursor: { page: 2 } }) };
  const all = boardStatusModel(board, 'all', null);
  const next = boardStatusModel(board, 'new', null);
  assert.equal(all.scope, 'all');
  assert.match(all.why, /作废/);
  assert.equal(next.scope, 'new');
  assert.match(next.why, /第 2 页/);
  assert.match(DETAIL, /const effectiveMode = \(\) => boardStatusModel\(/);
});

test('板头只有一个打印主按钮，记录纸面独立显示在确认条', () => {
  assert.equal((VIEW.match(/data-board-primary/g) || []).length, 1);
  assert.match(VIEW, /function confirmBar\(s\)/);
  assert.match(VIEW, /data-action="board\.markPrinted"/);
  assert.match(VIEW, /data-action="board\.cancelPrint"/);
  assert.match(VIEW, /data-board-modes/);
  assert.match(PAGE, /cancelPrint: \(\) => \{ D\.clearAwaiting\(\)/);
});

test('纸面与题目列表常驻，纸面舞台只有一个固定挂载点', () => {
  assert.equal((VIEW.match(/id="bd-stage"/g) || []).length, 1);
  assert.match(VIEW, /id="bd-stage" data-morph="skip"/);
  assert.match(VIEW, /id="bd-content-body"/);
  assert.match(VIEW, /id="bd-inspector"/);
  assert.ok(!VIEW.includes('data-board-view='));
  assert.match(PAGE, /D\.setView\('paper'\)/);
  assert.match(PAGE, /boardPreviewMount\(stage\)/);
  assert.match(PREVIEW, /if \(BP_FRAME\.parentNode !== container\) container\.appendChild\(BP_FRAME\)/);
});

test('行内留白、详情预设和版式字段走现有锁定保护', () => {
  assert.match(VIEW, /data-action="board\.gapStep"/);
  assert.match(VIEW, /data-action="board\.gapPreset"/);
  assert.match(VIEW, /data-board-print="note_ratio"/);
  assert.match(PAGE, /D\.setItemGap\(uid,/);
  assert.match(PAGE, /D\.applyPrintField\(arg,/);
  assert.match(DETAIL, /boardSettings\(\)\.setItemGap/);
});

test('关联标记按板保存在本机，待同步数排除停用及已有题', () => {
  const store = { data: new Map(), getItem(k) { return this.data.get(k) || null; }, setItem(k, v) { this.data.set(k, v); } };
  S.setLinkedLabel('a', '考前必看', store);
  S.setLinkedLabel('b', '概念不清', store);
  assert.equal(S.linkedLabel('a', store), '考前必看');
  assert.equal(S.linkedLabel('b', store), '概念不清');
  S.setLinkedLabel('a', '', store);
  assert.equal(S.linkedLabel('a', store), '');
  assert.match(PAGE, /!item\.suspended && \(item\.labels \|\| \[\]\)\.includes\(label\) && !inBoard\.has\(item\.uid\)/);
});

test('版式和纸面记录由工具条打开浮层，题目详情可返回及前后导航', () => {
  assert.match(VIEW, /data-action="board\.layoutPop"/);
  assert.match(VIEW, /data-action="board\.paperPop"/);
  assert.match(VIEW, /function popover\(kind, v\)/);
  assert.match(VIEW, /data-action="board\.back"/);
  assert.match(VIEW, /data-action="board\.detailStep"/);
  assert.match(PAGE, /onPaperSelect: uid => current\.openDetail\(uid\)/);
});

test('纸面工具条提供可配置动效入口，动效只通过嵌入式预览消息传递', () => {
  assert.match(VIEW, /data-action="board\.motionPop"/);
  assert.match(VIEW, /data-action="board\.motionKind"/);
  assert.match(VIEW, /data-input="board\.motionDuration"/);
  assert.match(PAGE, /boardPreviewSetMotion/);
  assert.match(PREVIEW, /motion: \{ \.\.\.BP_MOTION \}/);
  assert.match(PREVIEW, /type: 'omrs-board-view'/);
  assert.match(PREVIEW, /boardSwapOut/);
});

test('嵌入纸面时导出模板隐藏自己的打印动作条', () => {
  assert.match(PREVIEW, /omrs-board-view[\s\S]{0,200}embedded: true/);
  const template = fs.readFileSync(path.join(root, 'omrs/export_templates/board.js'), 'utf8');
  assert.ok(template.includes('classList.toggle("embedded"'));
  assert.match(template, /function animatePageChange/);
  assert.match(template, /if \(!valid \|\| next === previous\)/);
  assert.match(template, /prefers-reduced-motion/);
  assert.match(template, /MOTION_KINDS/);
});
