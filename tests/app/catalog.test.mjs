import test from 'node:test';
import assert from 'node:assert/strict';
import { fallbackTree, folderStats, treeSummary, matches, formatSize, treePaths } from '../../assets/app/features/catalog/state.js';
import { view } from '../../assets/app/features/catalog/view.js';

const items = [
  { uid: '隐圆模型1', path: '错题/数学/隐圆模型/隐圆模型1.md', mastery: .2, decayed_mastery: .18, due_date: 'past' },
  { uid: '隐圆模型2', path: '错题/数学/隐圆模型/隐圆模型2.md', mastery: .9, decayed_mastery: .88 },
  { uid: '动能定理1', path: '错题/物理/动能定理/动能定理1.md', mastery: .5, decayed_mastery: .45, is_leech: true },
];
const due = item => item.due_date === 'past' ? -1 : 9;
const tree = fallbackTree(items);
const state = () => ({ tree, summary: null, source: 'fallback', open: new Set(treePaths(tree)),
  stats: folderStats(items, due), query: '', showAll: false, loading: false, error: '', copyMessage: '' });

test('后备树按题目路径建立层级并排序', () => {
  assert.equal(tree.name, '错题');
  assert.deepEqual(tree.children.map(node => node.name), ['数学', '物理']);
  assert.equal(tree.children[0].children[0].files.length, 2);
  assert.equal(tree.question_count, 3);
  assert.equal(tree.file_count, 3);
});

test('文件夹统计叠加待复习、顽固题和衰减熟练度', () => {
  const stats = folderStats(items, due);
  assert.deepEqual(stats.get('错题/数学/隐圆模型'), { count: 2, masterySum: 1.06, killed: 0, due: 1, leech: 0 });
  assert.equal(stats.get('错题/物理').leech, 1);
  assert.equal(stats.get('错题').count, 3);
});

test('已击杀题不进入待复习计数', () => {
  const rows = folderStats([{ path: '错题/数学/A.md', mastery: 1, due_date: 'past' }], due);
  assert.equal(rows.get('错题/数学').due, 0);
  assert.equal(rows.get('错题/数学').killed, 1);
});

test('目录汇总沿用后端数字，后备汇总计算文件夹数', () => {
  assert.equal(treeSummary(tree).dirs, 4);
  assert.equal(treeSummary(tree, { dirs: 99 }).dirs, 99);
});

test('搜索命中后代并过滤不相关分支', () => {
  assert.equal(matches(tree, '动能'), true);
  assert.equal(matches(tree.children[0], '动能'), false);
  assert.equal(matches(tree, '找不到'), false);
});

test('展开全部的路径唯一', () => {
  assert.deepEqual(treePaths(tree), ['错题', '错题/数学', '错题/数学/隐圆模型', '错题/物理', '错题/物理/动能定理']);
});

test('目录文件大小格式与旧页面一致', () => {
  assert.equal(formatSize(500), '500 B');
  assert.equal(formatSize(2048), '2.0 KB');
  assert.equal(formatSize(1048576), '1.0 MB');
});

test('题目文件可打开，文件夹标出题量、待复习、顽固题', () => {
  const markup = String(view(state(), items, due));
  assert.match(markup, /data-action="catalog.open"/);
  assert.match(markup, /aria-expanded="true"/);
  assert.match(markup, /2 题/);
  assert.match(markup, /待复习/);
  assert.match(markup, /顽固/);
  assert.match(markup, /题目文件/);
});

test('折叠后孙节点不渲染；搜索自动展开命中分支', () => {
  const collapsed = state();
  collapsed.open = new Set(['错题']);
  assert.doesNotMatch(String(view(collapsed, items, due)), /隐圆模型1\.md/);
  collapsed.query = '动能';
  const markup = String(view(collapsed, items, due));
  assert.match(markup, /动能定理1\.md/);
  assert.doesNotMatch(markup, /隐圆模型1\.md/);
});

test('文件名和路径经过转义，模板没有行内事件与样式', () => {
  const unsafe = fallbackTree([{ uid: "A'B", path: '错题/数学/<题>.md', mastery: .5 }]);
  const s = { ...state(), tree: unsafe, open: new Set(treePaths(unsafe)), stats: new Map() };
  const markup = String(view(s, [{ uid: "A'B", path: '错题/数学/<题>.md', mastery: .5 }], due));
  assert.match(markup, /&lt;题&gt;\.md/);
  assert.doesNotMatch(markup, /<题>| on\w+=| style=/);
});
