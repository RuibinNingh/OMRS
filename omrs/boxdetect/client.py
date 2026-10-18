"""收件箱、聊天草稿与测试共用整图协议。"""
import base64
import math
import uuid
from .config import snapshot,assert_current
from .transport import json_request
from .errors import ServiceError


def status(vault):
    config=snapshot(vault)
    if not config.base_url:raise ServiceError('尚未配置AI框选服务','service_unconfigured',503)
    if not config.configured:raise ServiceError('当前为旧协议连接，请保存服务地址和调用Key后测试','service_legacy',409)
    value=json_request(config,'GET','/api/v1/status',timeout=10,limit=128*1024)
    model=value.get('model',{})
    if value.get('service')!='boxdetect' or value.get('protocol')!=1 or not isinstance(model,dict):raise ServiceError('该地址不是兼容的框选服务','service_protocol',502)
    assert_current(vault,config)
    # 不透传服务端额外字段；只展示连接与模型、配额摘要。
    return {'connected':True,'model':{k:model[k] for k in ('name','sha256','imgsz','conf') if k in model},'paused':value.get('paused') is True,
            'waiting':value.get('waiting') if type(value.get('waiting')) is int else None,'history_retention':value.get('history_retention',{})}


def detect(vault,data,mime,*,source='inbox',request_id=None):
    config=snapshot(vault)
    if not config.configured:return None
    payload={'image':'data:'+mime+';base64,'+base64.b64encode(data).decode(),'source':source,'request_id':request_id or uuid.uuid4().hex}
    result=json_request(config,'POST','/api/v1/detect',payload)
    boxes=result.get('boxes');strips=result.get('strips')
    if not isinstance(boxes,list) or len(boxes)>2000 or type(strips) is not int or not 1<=strips<=100:raise ServiceError('框选结果格式不合法','service_protocol',502)
    clean=[]
    for box in boxes:
        if not isinstance(box,dict) or box.get('role') not in ('question','answer') or any(type(box.get(k)) not in (int,float) or not math.isfinite(box[k]) or not 0<=box[k]<=1 for k in ('x','y','w','h','conf')):raise ServiceError('框选坐标不合法','service_protocol',502)
        clean.append({k:box[k] for k in ('role','x','y','w','h','conf')}|{'card':1})
    assert_current(vault,config)
    return {**result,'boxes':clean}
