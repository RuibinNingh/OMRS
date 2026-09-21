'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function fixture() {
  const nodes = new Map();
  const requests = [];
  const context = {
    SESSIONS:[], DATA:null, console,
    document:{addEventListener(){},getElementById(id){
      if (!nodes.has(id)) nodes.set(id,{innerHTML:'',classList:{add(){}},scrollIntoView(){}});
      return nodes.get(id);
    }},
    window:{matchMedia:()=>({matches:false})},
    api:()=>new Promise((resolve,reject)=>requests.push({resolve,reject})),
    qvSetContext(){},escapeHtml:String,jsArg:JSON.stringify,
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets/schedule.js'),'utf8'),context);
  context.schRenderPlans=()=>{};
  context.refreshFbSessionPicker=()=>{};
  context.renderUnifiedListV2=()=>{};
  return {context,nodes,requests};
}

test('slow older session response cannot erase the refreshed list', async()=>{
  const {context:c,requests}=fixture();
  const older=c.refreshSessions();
  const newer=c.refreshSessions();
  requests[1].resolve({sessions:[{session_id:'latest'}]});
  await newer;
  requests[0].reject(new Error('old offline response'));
  await older;
  assert.equal(c.SESSIONS[0].session_id,'latest');
  assert.equal(vm.runInContext('SCH_SESSIONS_ERROR',c),'');
  const failed=c.refreshSessions();
  requests[2].reject(new Error('offline'));
  await failed;
  assert.equal(c.SESSIONS[0].session_id,'latest');
  assert.equal(vm.runInContext('SCH_SESSIONS_ERROR',c),'offline');
});

test('selecting another plan keeps its detail when an older response arrives', async()=>{
  const {context:c,nodes,requests}=fixture();
  const older=c.schOpenPlan('OLD');
  const newer=c.schOpenPlan('NEW');
  const detail=id=>({session_id:id,created_at:'2026-09-20T10:00:00',items:[],count:0,status:'active'});
  requests[1].resolve(detail('NEW'));
  await newer;
  requests[0].resolve(detail('OLD'));
  await older;
  assert.equal(vm.runInContext('SCH_DETAIL.session_id',c),'NEW');
  assert.match(nodes.get('sch-plan-detail').innerHTML,/NEW/);
  assert.doesNotMatch(nodes.get('sch-plan-detail').innerHTML,/OLD/);
});

test('delete confirmation blocks duplicate requests and cancellation preserves the plan', async()=>{
  const {context:c,requests}=fixture();
  let confirm;
  c.uiConfirm=()=>new Promise(resolve=>{confirm=resolve;});
  c.SESSIONS=[{session_id:'KEEP'}];
  const first=c.schDeletePlan('KEEP');
  await c.schDeletePlan('KEEP');
  assert.equal(requests.length,0);
  confirm(false);
  await first;
  assert.equal(c.SESSIONS.length,1);
  assert.equal(vm.runInContext('SCH_DELETING.size',c),0);
});

test('delete business error preserves state and permits retry', async()=>{
  const {context:c,requests}=fixture();
  const messages=[];
  c.uiConfirm=async()=>true;
  c.uiToast=message=>messages.push(message);
  c.SESSIONS=[{session_id:'KEEP'}];
  const attempt=c.schDeletePlan('KEEP');
  await new Promise(setImmediate);
  requests[0].resolve({status:'error',deleted:false});
  await attempt;
  assert.equal(c.SESSIONS.length,1);
  assert.match(messages[0],/删除失败/);
  assert.equal(vm.runInContext('SCH_DELETING.size',c),0);
});
