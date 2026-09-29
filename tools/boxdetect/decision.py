"""冻结内容验证阈值与比较候选：只输出可复核结论，不发布模型。"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from omrs.trainaudit import audit,summary
from tools.boxdetect.audit import immutable


def load(path):
    path=Path(path).resolve()
    data=audit(path.parent.parent,path.name)
    report=summary(path.parent.parent,path.name)
    if not report['images'] or report['states'].get('pending',0):
        raise ValueError('评测为空或尚未完成，不能形成结论')
    return data,report


def population(data):
    return {(c['sample'],c.get('source_sha256')) for c in data['cases']}


def select(paths,out):
    loaded=[load(p) for p in paths]
    first=loaded[0][0]
    if sorted(d['conf'] for d,s in loaded)!=[.1,.25,.4,.55]:
        raise ValueError('必须覆盖预定的四个置信度')
    for data,report in loaded:
        if report['reviewed']<report['cases']:
            raise ValueError('用于阈值选择的案例尚未全部复核')
        if data['split']!='val' or any(data.get(k)!=first.get(k) for k in ('manifest_sha256','model_sha256','prompt_sha256')) or population(data)!=population(first):
            raise ValueError('阈值比较必须使用同模型、同验证快照、同提示词与样本')
    reports=[s for d,s in loaded]
    selected=max(reports,key=lambda s:(s['reviewed_passed'],-s['missing_images'],-s['extra_images'],s['conf']))
    record={'selected':selected['conf'],'selected_audit':selected['id'],'trials':reports,
            'model_sha256':first.get('model_sha256'),'manifest_sha256':first.get('manifest_sha256'),
            'rule':'仅验证集：内容通过数、较少缺漏、较少多余、较高阈值','production_authorized':False}
    immutable(out,record);return record


def compare(baseline,candidate,out,independent_baseline=None,independent_candidate=None):
    b,bs=load(baseline);c,cs=load(candidate)
    if b['split']!='test' or c['split']!='test' or population(b)!=population(c):
        raise ValueError('历史回归必须是同一批冻结原图')
    if any(s['reviewed']<s['cases'] for s in (bs,cs)):
        raise ValueError('用于决定候选的回归案例尚未全部复核')
    if b.get('prompt_sha256')!=c.get('prompt_sha256'):
        raise ValueError('裁判提示词不同，不能直接比较')
    checks={'reaches_80_percent':cs['reviewed_passed']*5>=cs['images']*4,
            'more_usable':cs['reviewed_passed']>bs['reviewed_passed'],
            'no_more_missing':cs['missing_images']<=bs['missing_images']}
    independent=None
    if bool(independent_baseline)!=bool(independent_candidate):raise ValueError('独立集必须提供两份对照')
    if independent_baseline:
        ib,ibs=load(independent_baseline);ic,ics=load(independent_candidate)
        if any(d['split']!='independent' for d in (ib,ic)) or population(ib)!=population(ic):raise ValueError('独立集身份不一致')
        if any(s['reviewed']<s['cases'] for s in (ibs,ics)):raise ValueError('独立集尚未全部复核')
        checks['independent_pass']=ics['reviewed_passed']*5>=ics['images']*4 and ics['reviewed_passed']>=ibs['reviewed_passed'] and ics['missing_images']<=ibs['missing_images']
        independent={'baseline':ibs,'candidate':ics}
    value={'baseline':bs,'candidate':cs,'checks':checks,'independent':independent,
           'recommendation':'candidate_local' if all(checks.values()) else 'retain_old',
           'production_authorized':False,'limitation':'历史回归已用于诊断；没有独立样本时不能据此声称泛化达标。'}
    immutable(out,value);return value


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);subs=p.add_subparsers(dest='command',required=True)
    a=subs.add_parser('select');a.add_argument('--audits',nargs=4,required=True);a.add_argument('--out',required=True)
    a=subs.add_parser('compare');a.add_argument('--baseline',required=True);a.add_argument('--candidate',required=True);a.add_argument('--out',required=True);a.add_argument('--independent-baseline');a.add_argument('--independent-candidate')
    args=vars(p.parse_args());command=args.pop('command')
    if command=='select':args['paths']=args.pop('audits');value=select(**args)
    else:value=compare(**args)
    print(json.dumps(value,ensure_ascii=False,indent=2))
