"""只把训练集内经复核的真实错误样本权重设为2，创建独立数据快照。"""
import argparse
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.boxdetect.common import atomic_json, sha256
from omrs.trainaudit import audit, result, reviews, effective


def build(dataset, audit_path, out):
    dataset,audit_path,out=Path(dataset).resolve(),Path(audit_path).resolve(),Path(out).resolve()
    manifest=json.loads((dataset/'manifest.json').read_text())
    data=audit(audit_path.parent.parent,audit_path.name)
    if data['split']!='train' or data['manifest_sha256']!=sha256(dataset/'manifest.json'):
        raise ValueError('困难样本评测必须来自同一数据快照的训练集')
    train=set(manifest['splits']['train']);hard=set();evidence=[]
    for c in data['cases']:
        if c['sample'] not in train:raise ValueError('评测混入非训练样本')
        h=reviews(audit_path.parent.parent,audit_path.name,c['id'])
        if not h:continue
        r=result(audit_path.parent.parent,audit_path.name,c['id'])
        if effective(r,h) in ('unusable','needs_adjustment'):
            hard.add(c['sample']);evidence.append({'case':c['id'],'sample':c['sample'],'history':h})
    if not hard:raise ValueError('没有已复核困难样本，不重复同配置训练')
    if out.exists() or out.is_relative_to(dataset):raise ValueError('目标目录必须是新的独立快照')
    shutil.copytree(dataset,out)
    lines=[]
    for s in manifest['samples']:
        s['sampling_weight']=2 if s['id'] in hard else 1
        if s['split']=='train':
            for strip in s['strips']:
                lines.extend([str(out/'images/train'/(strip['name']+'.jpg'))]*s['sampling_weight'])
    (out/'train-weighted.txt').write_text('\n'.join(lines)+'\n')
    manifest.update(version=out.name,reweighted_from=manifest['version'],hard_audit=audit_path.name,hard_ids=sorted(hard),review_evidence=evidence)
    atomic_json(out/'manifest.json',manifest);(out/'manifest.sha256').write_text(sha256(out/'manifest.json')+'\n')
    (out/'data.yaml').write_text('path: '+json.dumps(str(out))+'\ntrain: train-weighted.txt\nval: images/val\ntest: images/test\nnames:\n  0: question\n  1: answer\n')
    return {'hard_images':len(hard),'weighted_strips':len(lines),'original_train_images':len(train)}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',required=True);p.add_argument('--audit-path',required=True);p.add_argument('--out',required=True)
    print(json.dumps(build(**vars(p.parse_args())),ensure_ascii=False))
