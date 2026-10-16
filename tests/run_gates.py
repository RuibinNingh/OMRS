"""统一修复门禁：保留原始脚本入口，pytest 与浏览器验收显式登记。

运行 python3 tests/run_gates.py --ref <本次改动基线>；每条日志和实际结果写入临时目录。
--ref 用于文档差异和视觉比较；历史升级夹具由 --upgrade-ref 单独指定。
真实模型 boxdetect 需要外部冻结数据，用 --dataset 显式加入；不默认碰真实题库。
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def gates(ref, dataset=None, *, upgrade_ref='17d6d84', out=None, train_dir=None):
    if dataset and not train_dir:
        raise ValueError('真实检测门禁必须显式提供冻结train_dir，不能使用默认训练目录')
    py = sys.executable
    result = [
        ('unit','unittest',[py,'-m','unittest','discover','-s','tests','-p','test_*.py','-q']),
        ('unit','pytest-export',[py,'-m','pytest','tests/test_report_export.py','-q']),
        ('ui','node',['node','--test',*[str(p.relative_to(ROOT)) for p in sorted((ROOT/'tests/app').glob('*.test.mjs'))]]),
        ('ui','components',[py,'tests/app/run_browser.py']),
        ('ui','print',[py,'-m','unittest','tests.smoke_board_print','-q']),
        ('ui','print-a4',[py,'-m','unittest','tests.smoke_a4_print','-q']),
        ('ui','discipline',[py,'tests/check_ui.py']),
        ('ui','contrast',[py,'tests/check_contrast.py']),
    ]
    for path in sorted((ROOT/'tests/e2e').glob('*.py')):
        if path.stem == 'zuoyebang_paper':
            continue  # 由主站脚本调用的辅助模块，没有独立验收入口。
        command = [py,str(path.relative_to(ROOT))]
        if path.stem == 'boxdetect':
            if not dataset:
                continue
            command.extend(['--dataset',dataset,'--train-dir',str(train_dir)])
            if out:
                command.extend(['--shots',str(Path(out)/'e2e-boxdetect')])
        if path.stem == 'zuoyebang_gateway_integration':
            destination = Path(out or tempfile.gettempdir()) / 'integration-direct'
            command.extend(['--out', str(destination)])
            result.append(('e2e','e2e-zuoyebang_gateway_prefix',
                           [*command[:-1], str(destination.with_name('integration-prefix')), '--with-prefix']))
        result.append(('e2e','e2e-'+path.stem,command))
    result.extend([
        ('services','gateway-unit',[py,'-m','unittest','discover','-s','tests','-t','.','-q']),
        ('services','boxdetect-unit',[py,'-m','unittest','discover','-s','tests','-t','.','-q']),
        ('services','gateway-browser',[py,'tests/browser_acceptance.py']),
        ('release','upgrade-compat',[py,'tests/check_upgrade_compat.py','--ref',upgrade_ref]),
        ('visual','visual',[py,'tests/visual/run.py','--ref',ref]),
        ('docs','docs',[py,'tests/check_docs.py','--diff',ref]),
    ])
    return result


def execution_status(exit_code, log):
    """将缺依赖跳过保留为独立状态，不能凭进程退出0宣称通过。"""
    skips = [line for line in log.splitlines() if re.search(
        r'^\s*SKIP(?:PED)?\b|\bskipped=[1-9][0-9]*\b|\b[1-9][0-9]* skipped\b|^# skipped [1-9][0-9]*\b', line)]
    return ('failed' if exit_code else 'skipped' if skips else 'passed'), skips


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref',default='17d6d84',help='本次改动基线，仅用于文档差异与视觉比较')
    parser.add_argument('--upgrade-ref',default='17d6d84',help='历史升级夹具的旧代码提交，须保留旧 UID-only Session 与唯一索引语义')
    parser.add_argument('--groups',default='unit,ui,services,e2e,release,visual,docs')
    parser.add_argument('--only',help='只执行逗号分隔的门禁ID，用于失败项重跑')
    parser.add_argument('--out')
    parser.add_argument('--dataset',help='额外真实模型E2E的外部冻结数据，缺失时明确记录未运行')
    parser.add_argument('--train-dir',help='检测E2E的显式冻结训练材料副本；有--dataset时必填')
    args = parser.parse_args()
    if args.dataset and not args.train_dir:
        parser.error('--dataset必须同时提供--train-dir，不使用本机默认训练目录')
    output = Path(args.out or tempfile.mkdtemp(prefix='omrs-gates-')).expanduser().resolve()
    output.mkdir(parents=True,exist_ok=True)
    wanted = {value.strip() for value in args.groups.split(',') if value.strip()}
    only = ({value.strip() for value in args.only.split(',') if value.strip()}
            if args.only is not None else None)
    if not wanted:
        parser.error('--groups至少指定一个门禁组')
    if only is not None and not only:
        parser.error('--only至少指定一个门禁ID')
    all_gates = gates(args.ref,args.dataset,upgrade_ref=args.upgrade_ref,out=output,train_dir=args.train_dir)
    if wanted-{'unit','ui','services','e2e','release','visual','docs'} or (only and only-{g[1] for g in all_gates}):
        parser.error('未知门禁组或门禁ID')
    selected = [entry for entry in all_gates if entry[0] in wanted and (only is None or entry[1] in only)]
    if not selected:
        parser.error('--groups与--only没有共同的可执行门禁')
    env = dict(os.environ)
    for key in ['OMRS_SYSTEMD_SERVICE','OMRS_BOXDETECT_CONTROL']:
        env.pop(key,None)
    results = []
    for group,name,command in selected:
        start = time.monotonic()
        started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        print(name+': '+shlex.join(command),flush=True)
        if name == 'visual':
            command += ['--out',str(output/'visual')]
        cwd = ROOT / 'services' / ('boxdetect' if name == 'boxdetect-unit' else 'zuoyebang') if group == 'services' else ROOT
        child_env = dict(env)
        evidence = output / name
        evidence.mkdir(exist_ok=True)
        child_env.update(OMRS_E2E_SHOTS=str(evidence), OMRS_ZYB_SHOTS=str(evidence),
                         ZYB_TEST_EVIDENCE_DIR=str(evidence))
        if name == 'e2e-zuoyebang':
            # 摄像头替身启动参数只作用于独立 Chromium，不能复用已启动的共享浏览器。
            child_env.pop('OMRS_TEST_CDP_URL', None)
        log_path = output/(name+'.log')
        with log_path.open('w',encoding='utf-8') as log:
            completed = subprocess.run(command,cwd=cwd,env=child_env,stdout=log,stderr=subprocess.STDOUT)
        status, skips = execution_status(completed.returncode, log_path.read_text(encoding='utf-8',errors='replace'))
        results.append({'id':name,'command':command,'exit_code':completed.returncode,
                        'status':status,'skip_reasons':skips,'cwd':str(cwd),
                        'started_at':started_at,'ended_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        'seconds':round(time.monotonic()-start,3),'log':str(log_path)})
        report = {'ref':args.ref,'upgrade_ref':args.upgrade_ref,'results':results,'not_run':([] if args.dataset else [
            {'id':'e2e-boxdetect','reason':'依赖外部冻结模型和数据集；本次未改模型，不访问真实训练材料'}])}
        (output/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(name+': '+str(completed.returncode),flush=True)
    print('结果：'+str(output/'results.json'),flush=True)
    return int(any(r['status'] != 'passed' for r in results))


if __name__ == '__main__':
    sys.exit(main())
