import test from 'node:test';
import assert from 'node:assert/strict';
import { reviewPayload } from '../../assets/app/features/trainpanel/audits.js';
test('复核请求绑定选中案例与版本，不从表单覆盖身份或原判', () => {
 const payload=reviewPayload('run1',{id:'q',revision:3,judgment:{verdict:'usable'}},'correct','unusable','漏选项');
 assert.deepEqual(payload,{audit:'run1',case:'q',revision:3,action:'correct',verdict:'unusable',note:'漏选项'});
});
