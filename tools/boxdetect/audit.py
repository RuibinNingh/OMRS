"""离线双图内容验收：准备、限额调用、旧实验导入；不发布模型。"""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.boxdetect.common import atomic_json, sha256
from omrs.trainaudit import VERDICTS, now, summary

PROMPT = Path(__file__).with_name('crop-prompt-v2.txt')
PARAMS = {'thinking': {'type':'enabled'}, 'max_tokens':4096, 'stream':False}


def immutable(path, data):
    path = Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    # 先完整落盘，再用不覆盖目标的硬链接提交，崩溃不会留下半份正式结果。
    name=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix='.audit-',delete=False) as out:
            name=out.name
            json.dump(data,out,ensure_ascii=False,indent=2)
            out.flush();os.fsync(out.fileno())
        os.link(name,path)
    finally:
        if name is not None:Path(name).unlink(missing_ok=True)



def parse_response(response):
    choice = response['choices'][0]
    if choice.get('finish_reason') != 'stop': raise ValueError('输出未完整结束')
    value = json.loads(choice['message']['content'])
    if not isinstance(value,dict) or value.get('verdict') not in VERDICTS:
        raise ValueError('判定格式不合法')
    if any(not isinstance(value.get(k),list) or any(not isinstance(x,str) for x in value[k]) for k in ('missing_content','extra_content')):
        raise ValueError('缺漏与多余内容必须是字符串数组')
    if type(value.get('cut_characters')) is not bool or not isinstance(value.get('evidence'),str):
        raise ValueError('依据或截字字段不合法')
    if value['verdict']=='usable' and (value['missing_content'] or value['extra_content'] or value['cut_characters']):
        raise ValueError('可用结论与缺漏字段矛盾')
    return value


def cost(usage):
    hit = usage.get('prompt_cache_hit_tokens',usage.get('prompt_tokens_details',{}).get('cached_tokens',0))
    return (max(0,usage.get('prompt_tokens',0)-hit)*.30+hit*.006+usage.get('completion_tokens',0)*1.2)/1_000_000


def _prepare(dataset, out, model=None, conf=.55, split='test'):
    from PIL import Image
    from tools.boxdetect.evaluate import model_predictions, template_predictions
    from tools.boxdetect.inference import Detector
    dataset, out = Path(dataset), Path(out)
    manifest = json.loads((dataset/'manifest.json').read_text())
    if out.exists(): raise ValueError('评测目录已存在，请换名称或恢复调用')
    out.mkdir(parents=True); (out/'images').mkdir()
    detector = Detector(model,conf=conf) if model else None
    data = {'id':out.name,'dataset':manifest['version'],'manifest_sha256':sha256(dataset/'manifest.json'),
            'split':split,'purpose': 'historical_regression' if split=='test' else split,
            'model':Path(model).parent.name if model else 'template','model_sha256':sha256(model) if model else None,
            'conf':conf,'created_at':now(),'prompt_version':'crop-v2','prompt_sha256':sha256(PROMPT),
            'parameters':PARAMS,'cases':[],'resources':{}}
    shutil.copyfile(PROMPT,out/'prompt.txt')
    training = [s for s in manifest['samples'] if s['split']=='train']
    for sample in [s for s in manifest['samples'] if s['split']==split]:
        with Image.open(dataset/sample['file']) as im:
            original = im.convert('RGB')
            boxes = model_predictions(original,detector) if detector else template_predictions(sample,training)
            index = len(data['cases']); resource = f'original-{index}'; filename=resource+'.png'
            original.save(out/'images'/filename); data['resources'][resource]=filename
            for role in ('question','answer'):
                candidates=[b for b in boxes if b['role']==role]
                expected=sum(b['role']==role for b in sample['boxes'])
                # 数量不足必须显式保留；按空间顺序记录，不用 IoU 决定内容好坏。
                candidates.sort(key=lambda b:(b['y'],b['x']))
                for pos in range(max(expected,len(candidates))):
                    ident=f'case-{len(data["cases"]):04d}'
                    c={'id':ident,'sample':sample['id'],'group':sample['group'],'role':role,
                       'original':resource,'source_sha256':sample['sha256'],'box':None,
                       'structural_error':'missing' if pos>=len(candidates) else ('extra' if pos>=expected else None)}
                    if pos<len(candidates):
                        b=candidates[pos]; c['box']=b
                        xy=[max(0,int(b['x']*im.width)),max(0,int(b['y']*im.height)),
                            min(im.width,int((b['x']+b['w'])*im.width+.999)),min(im.height,int((b['y']+b['h'])*im.height+.999))]
                        crop=original.crop(xy); filename=ident+'.png';crop.save(out/'images'/filename)
                        c.update(crop=ident,crop_sha256=sha256(out/'images'/filename),crop_xyxy=xy)
                        data['resources'][ident]=filename
                    else:
                        immutable(out/(ident+'.json'),{'state':'missing','judgment':{'verdict':'unusable','missing_content':['未检测到必要区域'],'extra_content':[],'cut_characters':False,'evidence':'检测未返回足够的目标框'}})
                    data['cases'].append(c)
    immutable(out/'audit.json',data)
    return data



def prepare(dataset, out, model=None, conf=.55, split='test'):
    if not 0 < conf <= 1:
        raise ValueError('检测置信度必须在0到1之间')
    root=Path(out).resolve().parent.parent
    root.mkdir(parents=True,exist_ok=True)
    with (root/'training.lock').open('a') as guard:
        try: fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('训练运行中，暂不批量推理')
        return _prepare(dataset,out,model,conf,split)


def run(out, config_path, budget_name='content-round-1'):
    out=Path(out).resolve(); root=out.parent.parent
    from omrs.trainpanel import safe_path
    ledger=safe_path(root,budget_name+'.json'); lock=safe_path(root,'audit-run.lock')
    with lock.open('a') as handle:
        try: fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('已有评测运行，拒绝重复调用')
        cfg=json.loads(Path(config_path).read_text())
        if cfg.get('agent_model')!='deepseek-flash': raise ValueError('需要现有 deepseek-flash 配置')
        base=(cfg.get('agent_base_url') or cfg.get('ai_base_url') or '').rstrip('/')
        key=cfg.get('agent_api_key') or cfg.get('ai_api_key')
        if not base or not key: raise ValueError('缺少助手渠道配置')
        endpoint=base if base.endswith('/chat/completions') else base+'/chat/completions'
        data=json.loads((out/'audit.json').read_text()); prompt=(out/'prompt.txt').read_text()
        if sha256(out/'prompt.txt')!=data['prompt_sha256']: raise ValueError('提示词已改变')
        budget=json.loads(ledger.read_text()) if ledger.exists() else {'requests':0,'cost_usd':0,'unknown_usage':0}
        cache=root/'audit-cache'; cache.mkdir(exist_ok=True)
        status={'pid':os.getpid(),'state':'running','updated_at':now(),'completed':0,'total':len(data['cases'])}
        atomic_json(out/'progress.json',status)
        try:
            for c in data['cases']:
                dest=out/(c['id']+'.json')
                if dest.exists(): continue
                fingerprint=hashlib.sha256(json.dumps([c['source_sha256'],c['crop_sha256'],data['prompt_sha256'],c['role'],'deepseek-flash',PARAMS,endpoint],sort_keys=True).encode()).hexdigest()
                cached=cache/(fingerprint+'.json')
                if cached.exists():
                    r=json.loads(cached.read_text());r.update(state='cached',cost_usd=0,seconds=0)
                    immutable(dest,r);continue
                content=[{'type':'text','text':prompt+'\n本次目标类型：'+('题目' if c['role']=='question' else '答案')}]
                for kind in ('original','crop'):
                    image=out/'images'/data['resources'][c[kind]]
                    content.append({'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(image.read_bytes()).decode()}})
                payload={'model':'deepseek-flash','messages':[{'role':'user','content':content}],**PARAMS}
                for attempt in range(3):
                    if budget['requests']>=300 or budget['cost_usd']>=2: raise RuntimeError('已达到本轮调用预算')
                    budget['requests']+=1;atomic_json(ledger,budget)
                    started=time.monotonic();r={'state':'error','requested_model':'deepseek-flash','cache_key':fingerprint,'usage':{},'cost_usd':0}
                    retry=False;fatal=False
                    try:
                        request=urllib.request.Request(endpoint,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
                        with urllib.request.urlopen(request,timeout=60) as response:
                            body=response.read(4*1024*1024+1)
                        if len(body)>4*1024*1024:raise ValueError('响应过大')
                        raw=json.loads(body);r.update(response=raw,usage=raw.get('usage',{}),response_model=raw.get('model'))
                        r['cost_usd']=cost(r['usage']);r['judgment']=parse_response(raw);r['state']='done'
                    except urllib.error.HTTPError as exc:
                        r['error']='HTTP '+str(exc.code);retry=exc.code==429 or exc.code>=500;fatal=exc.code in (401,403)
                    except (urllib.error.URLError,TimeoutError,ConnectionError) as exc:
                        r['error']=type(exc).__name__;retry=True
                    except (ValueError,KeyError,IndexError,TypeError) as exc:
                        r['error']=type(exc).__name__+': '+str(exc)[:200]
                    r['seconds']=round(time.monotonic()-started,3)
                    budget['cost_usd']+=r['cost_usd'];budget['unknown_usage']+=not bool(r['usage']);atomic_json(ledger,budget)
                    attempts=out/'attempts';attempts.mkdir(exist_ok=True)
                    immutable(attempts/(c['id']+'-'+str(budget['requests'])+'.json'),r)
                    if fatal: raise RuntimeError('评测渠道鉴权失败')
                    if retry and attempt<2:time.sleep(2**attempt);continue
                    immutable(dest,r)
                    if r['state']=='done' and not cached.exists(): immutable(cached,r)
                    print(c['id'],r['state'],r.get('judgment',{}).get('verdict'),flush=True)
                    break
                status.update(updated_at=now(),completed=sum((out/(x['id']+'.json')).exists() for x in data['cases']),budget=budget)
                atomic_json(out/'progress.json',status)
            status.update(state='done',completed=len(data['cases']))
        except BaseException as exc:
            status.update(state='paused',error=str(exc));raise
        finally:
            status['updated_at']=now();atomic_json(out/'progress.json',status)
    return summary(root,out.name)


def import_legacy(source,out):
    source,out=Path(source),Path(out)
    if out.exists():raise ValueError('导入目录已存在')
    out.mkdir(parents=True);(out/'images').mkdir()
    cases=json.loads((source/'cases.json').read_text())
    data={'id':out.name,'dataset':'20260929-1','split':'calibration','purpose':'calibration',
          'model':'640 legacy','prompt_version':'v1/v2','created_at':now(),'cases':[],'resources':{}}
    for folder in (source,source/'no-thinking',source/'retry-4096',source/'v2'):
        for p in sorted(folder.glob('C*-response.json')):
            raw=json.loads(p.read_text());c=next(c for c in cases['cases'] if c['case']==raw['case'])
            ident=f'legacy-{len(data["cases"]):02d}'
            entry={'id':ident,'sample':c['sample'],'role':c['role'],'kind':c['kind'],'description':c['description'],
                   'prompt_version':'v2' if folder.name=='v2' else 'v1','variant':folder.name,
                   'scope_ambiguous':c['case']=='C02','crop_xyxy':c['crop_xyxy'],'source_sha256':c['source_sha256']}
            for kind in ('original','crop'):
                resource=ident+'-'+kind;filename=resource+Path(c[kind]).suffix
                shutil.copyfile(c[kind],out/'images'/filename);data['resources'][resource]=filename;entry[kind]=resource
            data['cases'].append(entry)
            usage=raw.get('response',{}).get('usage',{})
            r={**raw,'state':'done' if raw.get('judgment') else 'error','usage':usage,'cost_usd':cost(usage)}
            immutable(out/(ident+'.json'),r)
    immutable(out/'audit.json',data)
    return {'imported':len(data['cases'])}


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('--dataset',required=True);a.add_argument('--out',required=True);a.add_argument('--model');a.add_argument('--conf',type=float,default=.55);a.add_argument('--split',choices=['train','val','test','independent'],default='test')
    a=sub.add_parser('run');a.add_argument('--out',required=True);a.add_argument('--config',required=True);a.add_argument('--budget-name',default='content-round-1')
    a=sub.add_parser('import');a.add_argument('--source',required=True);a.add_argument('--out',required=True)
    args=vars(p.parse_args());command=args.pop('command')
    if command=='prepare': value=prepare(**args);value={'cases':len(value['cases'])}
    elif command=='run':args['config_path']=args.pop('config');value=run(**args)
    else:value=import_legacy(**args)
    print(json.dumps(value,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
