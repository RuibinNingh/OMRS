"""助手问题工具；写工具交给原运行的统一确认链。"""
from ... import problems, problem_review

S={'type':'string'}
STRINGS={'type':'array','items':S,'maxItems':100}
FIELDS={'request_id':S,'id':S,'title':S,'description_md':S,'subject':S,'status':{'type':'string','enum':list(problems.STATUSES)},
        'expected_revision':{'type':'integer','minimum':1},'reason':S,'question_id':S,'question_ids':STRINGS,'problem_ids':STRINGS,
        'content_md':S,'recurrence_of':S,'occurred_at':S,'withdrawn':{'type':'boolean'},'data_base64':S}
REQUIRED={'create_problem':['title'],'update_problem':['id','expected_revision'],'link_problem_questions':['id','expected_revision','question_ids'],
          'unlink_problem_questions':['id','expected_revision','question_ids'],'add_reflection_entry':['question_id','content_md'],
          'revise_reflection_entry':['id','expected_revision','reason'],'add_problem_asset':['data_base64']}
LABELS={'create_problem':'创建问题','update_problem':'修改问题描述或状态（变更状态必须给理由）','link_problem_questions':'关联问题材料',
        'unlink_problem_questions':'解除材料关联','add_reflection_entry':'向题目 Markdown 追加错因记录','revise_reflection_entry':'修订或撤回 Markdown 中的具体错因记录','add_problem_asset':'保存问题图片或静态SVG附件'}


def _write(_ctx,_args):
    raise ValueError('问题写必须通过原运行的统一审核')


def _preview(name):
    return lambda ctx,args: problem_review.preview(name,args,ctx['vault'])


SPECS=[
 ('search_problems','read','分页搜索已有问题，新增前先搜索避免近义重复。',{'type':'object','additionalProperties':False,'properties':{'query':S,'status':S,'question_id':S,'cursor':S,'limit':{'type':'integer','minimum':1,'maximum':100}}},lambda ctx,args:{'result':problems.search(ctx['vault'],**args)}),
 ('get_problem','read','读取问题描述、稳定题目关联、来源与修订事件。',{'type':'object','required':['id'],'additionalProperties':False,'properties':{'id':S}},lambda ctx,args:{'result':problems.get(ctx['vault'],args['id'])}),
 ('get_reflections','read','分页读取指定稳定题目的多条错因记录，不推断未知发生时间。',{'type':'object','required':['question_id'],'additionalProperties':False,'properties':{'question_id':S,'cursor':S,'limit':{'type':'integer','minimum':1,'maximum':100}}},lambda ctx,args:{'result':problems.reflections(ctx['vault'],**args)}),
]
for name in problems.ACTIONS:
    schema={'type':'object','additionalProperties':False,'required':['request_id',*REQUIRED[name]],'properties':FIELDS}
    SPECS.append((name,'confirm',LABELS[name]+'。须确认；AI内容标为假设，不冒充用户事实；不改变熟练度。',schema,_write,_preview(name)))
