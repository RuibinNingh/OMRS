import test from 'node:test';
import assert from 'node:assert/strict';
import {controlPayload,modelScores} from '../../assets/app/features/trainpanel/control.js';
test('模型应用绑定当前版本、模型身份及固定阈值，不传路径或命令',()=>{
 const model={id:'run',sha256:'hash',conf:.55,imgsz:640};
 assert.deepEqual(controlPayload({revision:4},'activate',model,'request'),{action:'activate',revision:4,request_id:'request',model_id:'run',sha256:'hash',conf:.55,imgsz:640});
 assert.deepEqual(controlPayload({revision:4},'stop',model,'request'),{action:'stop',revision:4,request_id:'request'});
});
test('内容分数保留分母、复核覆盖和样本用途',()=>{
 assert.match(modelScores({scores:[{purpose:'historical_regression',raw_passed:9,reviewed_passed:9,images:15,reviewed:30,cases:30,user_reviewed:0}]}),/历史回归：原判 9\/15，复核后 9\/15；已复核 30\/30（用户 0）/);
 assert.match(modelScores({}),/不代表质量达标/);
});
