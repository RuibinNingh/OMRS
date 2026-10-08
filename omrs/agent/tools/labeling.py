"""分批读题和准备后只提出一份整批标记审核。"""
from ...label_plan_prepare import candidates, list_labels, stage

S = {'type':'string'}
I = {'type':'integer','minimum':0}
SCOPE = {'type':'object','additionalProperties':False,'properties':{'subject':S,'category':S,'question_ids':{'type':'array','maxItems':1000,'items':S}}}
OP = {'type':'object','additionalProperties':False,'required':['action'],'properties':{
    'action':{'type':'string','enum':['create','update','merge','delete']},
    'change_id':S,'label_id':S,'key':S,'name':S,'color':S,'order':{'type':'integer','minimum':1},'into':S,'reason':S,'enabled':{'type':'boolean'}}}
Q = {'type':'object','additionalProperties':False,'required':['question_id','expected_content_hash'],'properties':{
    'question_id':S,'expected_content_hash':S,'add':{'type':'array','items':S,'maxItems':64},'remove':{'type':'array','items':S,'maxItems':64},
    'reason':S,'uncertain_reason':S,'enabled':{'type':'boolean'}}}
PAYLOAD = {'type':'object','additionalProperties':False,'properties':{'scope':SCOPE,'reason':S,'label_changes':{'type':'array','maxItems':100,'items':OP},
           'question_changes':{'type':'array','maxItems':50,'items':Q}}}


def listing(ctx,args):
    return {'result':list_labels(ctx['vault'],**args)}


def reading(ctx,args):
    return {'result':candidates(ctx['vault'],**args)}


def staging(ctx,args):
    result=stage(ctx['vault'],'agent',ctx['conversation_id'],**args)
    return {'result':result,'summary':f"已准备 {result['staged_questions']} 道题 · {result['staged_definitions']} 项定义",'wrote':False}


def proposing(ctx,args):
    raise ValueError('标记整理必须通过原运行的统一批准执行')


SPECS = [
 ('list_labels','read','分页读取标记稳定 ID、名称、颜色、排序、加成、引用题数和定义摘要。优先复用已有标记。',
  {'type':'object','additionalProperties':False,'properties':{'cursor':S,'limit':{'type':'integer','minimum':1,'maximum':20}}},listing),
 ('get_labeling_candidates','read','分页读取归类候选（最多20题），返回稳定身份、正文哈希、题目/答案/已有错因摘要、截断和游标；不足时另读完整题目或图片。',
  {'type':'object','additionalProperties':False,'properties':{'scope':SCOPE,'label_ids':{'type':'array','items':S},'cursor':S,'limit':{'type':'integer','minimum':1,'maximum':20}}},reading,None,24000),
 ('stage_label_plan','prepare','创建或追加技术准备分片，每次最多50题。首片不传 plan_id 且 expected_version=0；后续沿用 plan_id 和返回 version。新定义 key 可在同批归类 add/remove 引用。每题必须带读取哈希和理由。准备不改正式数据。',
  {'type':'object','additionalProperties':False,'required':['fragment_id','payload'],'properties':{'fragment_id':S,'payload':PAYLOAD,'plan_id':S,'expected_version':I}},staging),
 ('propose_label_plan','confirm','全部分片准备完成后按 plan_id 和 expected_version 提交一份整批方案，等待对话内一次确认。上限100定义/1000受影响题；跨范围级联默认关闭，用户可修订。不能在批准前报告完成。',
  {'type':'object','additionalProperties':False,'required':['plan_id','expected_version'],'properties':{'plan_id':S,'expected_version':{'type':'integer','minimum':1}}},proposing),
]
