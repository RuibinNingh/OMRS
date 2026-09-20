'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const values = new Map();
function element(id) {
  if (!values.has(id)) values.set(id, { id, value: '', checked: false });
  return values.get(id);
}
const sandbox = {
  console,
  Date,
  Math,
  Number,
  String,
  Object,
  Array,
  Set,
  Map,
  URLSearchParams,
  document: { getElementById: id => element(id), querySelectorAll: () => [], addEventListener() {} },
  localStorage: { getItem: () => null, setItem() {} },
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(root, 'assets/core.js'), 'utf8'), sandbox);
const publicGetFilterState = sandbox.getFilterState;
const publicFilterItems = sandbox.filterItems;
vm.runInContext(fs.readFileSync(path.join(root, 'assets/recommend_v2.js'), 'utf8'), sandbox);

test('recommend v2 keeps the shared filter API intact', () => {
  assert.strictEqual(sandbox.getFilterState, publicGetFilterState);
  assert.strictEqual(sandbox.filterItems, publicFilterItems);
  assert.equal(typeof sandbox.recV2GetFilterState, 'function');
  assert.equal(typeof sandbox.recV2FilterItems, 'function');
});

test('recommend v2 filters use the shared suspended/text/knowledge contract', () => {
  element('rec-search-v2').value = 'circle';
  element('rec-filter-ktag-v2').value = '圆';
  element('rec-filter-sort-v2').value = 'mastery-asc';
  const items = [
    { uid: 'circle-1', subject: '数学', category: '几何', knowledge_tags: ['圆'], mastery: 0.2, difficulty: 5, suspended: false },
    { uid: 'circle-paused', subject: '数学', category: '几何', knowledge_tags: ['圆'], mastery: 0.1, difficulty: 5, suspended: true },
    { uid: 'line-1', subject: '数学', category: '几何', knowledge_tags: ['直线'], mastery: 0.1, difficulty: 5, suspended: false },
  ];
  const filters = sandbox.recV2GetFilterState();
  assert.deepEqual(Array.from(sandbox.recV2FilterItems(items, filters), item => item.uid), ['circle-1']);
});

test('local dates match today across Shanghai and negative UTC offsets', () => {
  const before = process.env.TZ;
  for (const timezone of ['Asia/Shanghai', 'America/Los_Angeles']) {
    process.env.TZ = timezone;
    const now = new Date();
    const date = `${now.getFullYear()}-${now.getMonth()+1}-${now.getDate()}`;
    const tomorrow = new Date(now.getFullYear(),now.getMonth(),now.getDate()+1);
    const items = [
      {uid:'today',due_date:date,difficulty:5},
      {uid:'slash',due_date:date.replaceAll('-','/'),difficulty:5},
      {uid:'future',due_date:`${tomorrow.getFullYear()}-${tomorrow.getMonth()+1}-${tomorrow.getDate()}`,difficulty:5},
      {uid:'invalid',due_date:'2026-02-31',difficulty:5}
    ];
    const filters = {text:'',labels:[],difficultyMin:1,difficultyMax:10,dueFilter:'today',sort:'priority'};
    assert.deepEqual(Array.from(sandbox.recV2FilterItems(items,filters),i=>i.uid), ['today','slash']);
    filters.dueFilter = 'future';
    assert.deepEqual(Array.from(sandbox.recV2FilterItems(items,filters),i=>i.uid), ['future']);
  }
  if (before === undefined) delete process.env.TZ; else process.env.TZ = before;
});

test('label all/any and 0% mastery remain real filters', () => {
  const items = [
    {uid:'both',difficulty:5,mastery:0,labels:['考前','易错']},
    {uid:'one',difficulty:5,mastery:.5,labels:['易错']},
    {uid:'none',difficulty:5,mastery:0,labels:[]},
  ];
  const f = {labels:['考前','易错'],labelMode:'any',difficultyMin:1,difficultyMax:10,sort:'priority'};
  assert.deepEqual(Array.from(sandbox.recV2FilterItems(items,f),i=>i.uid),['both','one']);
  f.labelMode='all';
  assert.deepEqual(Array.from(sandbox.recV2FilterItems(items,f),i=>i.uid),['both']);
  f.labels=[]; f.masteryMax=0;
  assert.deepEqual(Array.from(sandbox.recV2FilterItems(items,f),i=>i.uid),['both','none']);
  f.difficultyMin=9; f.difficultyMax=2;
  assert.equal(sandbox.recV2FilterItems(items,f).length,0);
});

test('balanced recommendation keeps due first and rotates subjects without rescoring', () => {
  const items = [
    {uid:'m1',subject:'数学',_source:'due',mastery:.9},
    {uid:'m2',subject:'数学',_source:'due',mastery:0},
    {uid:'p1',subject:'物理',_source:'due',mastery:0},
    {uid:'early1',subject:'数学',_source:'proficiency'},
    {uid:'early2',subject:'物理',_source:'proficiency'},
  ];
  assert.deepEqual(Array.from(sandbox.recOrderItems(items,'balanced'),i=>i.uid),['m1','p1','m2','early1','early2']);
  assert.deepEqual(Array.from(sandbox.recOrderItems(items,'due'),i=>i.uid),['m1','m2','p1','early1','early2']);
  assert.deepEqual(Array.from(sandbox.recOrderItems(items,'weak'),i=>i.uid),['early1','early2','m1','m2','p1']);
});

test('latest recommendation response wins and refresh keeps eligible selected items', async () => {
  const pending=[];
  sandbox.api=()=>new Promise(resolve=>pending.push(resolve));
  sandbox.renderUnifiedListV2=()=>{};
  sandbox.uiToast=()=>{};
  vm.runInContext("REC_SELECTED_V2 = new Map([['keep',{uid:'keep'}],['gone',{uid:'gone'}]])",sandbox);
  const old=sandbox.loadRecommendationsV2();
  const latest=sandbox.loadRecommendationsV2();
  pending[1]({due:[{uid:'keep'}],proficiency:[{uid:'new'}]});
  await latest;
  pending[0]({due:[{uid:'stale'}]});
  await old;
  assert.deepEqual(Array.from(vm.runInContext('REC_DATA_V2.map(i=>i.uid)',sandbox)),['keep','new']);
  assert.deepEqual(Array.from(vm.runInContext('[...REC_SELECTED_V2.keys()]',sandbox)),['keep']);
});
