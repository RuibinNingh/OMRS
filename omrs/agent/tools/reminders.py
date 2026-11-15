"""助手可准备提醒素材，用户在调度页选用；不改计划或全局设置。"""
import hashlib
from ... import schedule_reminders


def create(ctx, args):
    result = schedule_reminders.create(ctx['vault'], args['name'], args['svg'],
        'agent:' + ctx['conversation_id'] + ':' + hashlib.sha256(args['request_id'].encode()).hexdigest(), source='AI 生成')
    result['item'] = {k: v for k, v in result['item'].items() if k != 'src'}
    return {'result': result, 'summary': '提醒已加入素材库，请在复习调度中预览并选用'}


SPECS = [
    ('list_schedule_reminders', 'read', '查询首页提醒素材名称与身份，不含SVG源码。',
     {'type': 'object', 'properties': {}, 'additionalProperties': False},
     lambda ctx, args: {'result': schedule_reminders.catalog(ctx['vault'])}),
    ('create_schedule_reminder', 'prepare',
     '新增复习清单首页提醒SVG素材，用户选择后才使用，不修改计划或默认设置。'
     'SVG按197.3mm通栏宽、最多28mm高设计，文字至少8.5pt、线宽至少0.5pt。'
     '必须有title、viewBox及首个铺满画布的白底rect；不含脚本、外链、动画、引用或裁剪。',
     {'type': 'object', 'required': ['name', 'svg', 'request_id'], 'additionalProperties': False,
      'properties': {'name': {'type': 'string', 'minLength': 1, 'maxLength': 80},
                     'svg': {'type': 'string', 'minLength': 1, 'maxLength': 262144},
                     'request_id': {'type': 'string', 'minLength': 1, 'maxLength': 200}}}, create),
]
