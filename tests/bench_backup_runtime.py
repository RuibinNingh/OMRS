"""仅合成临时题库：真实备份／目录恢复／HTTP启动的时间、冻结和峰值RSS。"""
import argparse
import json
import os
from pathlib import Path
import resource
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from omrs import backup_store


def rss(pid=None):
    try:
        lines = Path('/proc',str(pid or os.getpid()),'status').read_text().splitlines()
        return int(next(l.split()[1] for l in lines if l.startswith('VmHWM:'))) / 1024
    except (OSError,StopIteration):
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def child(vault, action):
    start = time.perf_counter()
    if action == 'backup':
        archive,_,_,frozen = backup_store.create_backup(vault)
        result = dict(frozen_seconds=frozen,archive_bytes=os.path.getsize(archive))
        os.unlink(archive)
    elif action == 'restore':
        archive,_,_,_ = backup_store.create_backup(vault)
        target = tempfile.mkdtemp(prefix='omrs-capacity-restore-')
        try:
            before = time.perf_counter()
            prepared = backup_store.prepare_import(target,archive)
            prepare_seconds = time.perf_counter()-before
            before = time.perf_counter()
            restored = backup_store.restore(target,prepared['restore_id'],True)
            result = dict(prepare_seconds=prepare_seconds,restore_seconds=time.perf_counter()-before,
                          questions=restored['question_count'])
            assert restored['question_count'] == 10000, restored
        finally:
            os.unlink(archive)
            shutil.rmtree(target)
    else:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        env = dict(os.environ)
        for key in ['OMRS_SYSTEMD_SERVICE','OMRS_BOXDETECT_CONTROL']:env.pop(key,None)
        with tempfile.TemporaryFile() as log:
            proc = subprocess.Popen([sys.executable,str(ROOT/'omrs_engine.py'),'--vault',vault,'serve','-p',str(port)],
                                    cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                for _ in range(600):
                    if proc.poll() is not None:
                        log.seek(0);raise RuntimeError(log.read().decode())
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/auth/session',timeout=1) as response:
                            json.load(response)
                        break
                    except OSError:time.sleep(.05)
                else:raise RuntimeError('真实HTTP启动超时')
                ready_seconds = time.perf_counter() - start
                before = time.perf_counter()
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/stats',timeout=60) as response:
                    state = json.load(response)
                result = dict(server_rss_mib=rss(proc.pid),startup_seconds=ready_seconds,
                              stats_seconds=time.perf_counter()-before,items=len(state.get('items',[])))
                assert result['server_rss_mib'] <= 768,result
            finally:
                proc.terminate();proc.wait(timeout=10)
    result.update(action=action,seconds=time.perf_counter()-start,rss_mib=rss())
    assert result['rss_mib'] <= 768,result
    print(json.dumps(result,ensure_ascii=False),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault',required=True,help='bench_data_runtime生成并带真实Markdown/blob的临时合成题库')
    parser.add_argument('--action',choices=['backup','restore','startup'])
    parser.add_argument('--samples',type=int,default=5)
    args=parser.parse_args()
    # 本容量门禁必须显式使用临时数据，不能连真实题库。
    if not Path(args.vault).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
        parser.error('只允许临时合成题库')
    if args.action:
        child(args.vault,args.action);return
    for action in ['backup','restore','startup']:
        values=[]
        for _ in range(args.samples):
            completed=subprocess.run([sys.executable,__file__,'--vault',args.vault,'--action',action],check=True,capture_output=True,text=True)
            value=json.loads(completed.stdout.strip().splitlines()[-1]);values.append(value);print(json.dumps(value,ensure_ascii=False),flush=True)
        ordered=sorted(v['seconds'] for v in values)
        print(json.dumps({'action':action,'samples':len(values),'p50_seconds':statistics.median(ordered),
            'p95_seconds':ordered[min(len(ordered)-1,int(len(ordered)*.95))],
            'peak_rss_mib':max(max(v['rss_mib'],v.get('server_rss_mib',0)) for v in values),
            'freeze_p50_seconds':statistics.median([v['frozen_seconds'] for v in values]) if action=='backup' else None},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
