"""统一修复门禁：保留原始脚本入口，pytest 与浏览器验收显式登记。

运行 python3 tests/run_gates.py --ref <本次改动基线>；每条日志和实际结果写入临时目录。
--ref 用于文档差异和视觉比较；历史升级夹具由 --upgrade-ref 单独指定。
真实模型 boxdetect 需要外部冻结数据，用 --dataset 显式加入；不默认碰真实题库。
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def gates(ref, dataset=None, *, upgrade_ref='17d6d84'):
    py = sys.executable
    result = [
        ('unit','unittest',[py,'-m','unittest','discover','-s','tests','-p','test_*.py','-q']),
        ('unit','pytest-export',[py,'-m','pytest','tests/test_report_export.py','-q']),
        ('ui','node',['node','--test',*[str(p.relative_to(ROOT)) for p in sorted((ROOT/'tests/app').glob('*.test.mjs'))]]),
        ('ui','components',[py,'tests/app/run_browser.py']),
        ('ui','print',[py,'-m','unittest','tests.smoke_board_print','-q']),
        ('ui','discipline',[py,'tests/check_ui.py']),
        ('ui','contrast',[py,'tests/check_contrast.py']),
    ]
    for path in sorted((ROOT/'tests/e2e').glob('*.py')):
        command = [py,str(path.relative_to(ROOT))]
        if path.stem == 'boxdetect':
            if not dataset:
                continue
            command.extend(['--dataset',dataset])
        result.append(('e2e','e2e-'+path.stem,command))
    result.extend([
        ('release','upgrade-compat',[py,'tests/check_upgrade_compat.py','--ref',upgrade_ref]),
        ('visual','visual',[py,'tests/visual/run.py','--ref',ref]),
        ('docs','docs',[py,'tests/check_docs.py','--diff',ref]),
    ])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref',default='17d6d84',help='本次改动基线，仅用于文档差异与视觉比较')
    parser.add_argument('--upgrade-ref',default='17d6d84',help='历史升级夹具的旧代码提交，须保留旧 UID-only Session 与唯一索引语义')
    parser.add_argument('--groups',default='unit,ui,e2e,release,visual,docs')
    parser.add_argument('--only',help='只执行逗号分隔的门禁ID，用于失败项重跑')
    parser.add_argument('--out')
    parser.add_argument('--dataset',help='额外真实模型E2E的外部冻结数据，缺失时明确记录未运行')
    args = parser.parse_args()
    output = Path(args.out or tempfile.mkdtemp(prefix='omrs-gates-'))
    output.mkdir(parents=True,exist_ok=True)
    wanted = set(args.groups.split(',')); only = set(args.only.split(',')) if args.only else None
    all_gates = gates(args.ref,args.dataset,upgrade_ref=args.upgrade_ref)
    if wanted-{'unit','ui','e2e','release','visual','docs'} or (only and only-{g[1] for g in all_gates}):
        parser.error('未知门禁组或门禁ID')
    env = dict(os.environ)
    for key in ['OMRS_SYSTEMD_SERVICE','OMRS_BOXDETECT_CONTROL']:
        env.pop(key,None)
    results = []
    for group,name,command in all_gates:
        if group not in wanted or (only and name not in only):
            continue
        start = time.monotonic()
        print(name+': '+shlex.join(command),flush=True)
        if name == 'visual':
            command += ['--out',str(output/'visual')]
        with (output/(name+'.log')).open('w',encoding='utf-8') as log:
            completed = subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        results.append({'id':name,'command':command,'exit_code':completed.returncode,
                        'seconds':round(time.monotonic()-start,3),'log':str(output/(name+'.log'))})
        report = {'ref':args.ref,'upgrade_ref':args.upgrade_ref,'results':results,'not_run':([] if args.dataset else [
            {'id':'e2e-boxdetect','reason':'依赖外部冻结模型和数据集；本次未改模型，不访问真实训练材料'}])}
        (output/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(name+': '+str(completed.returncode),flush=True)
    print('结果：'+str(output/'results.json'),flush=True)
    return int(any(r['exit_code'] for r in results))


if __name__ == '__main__':
    sys.exit(main())
