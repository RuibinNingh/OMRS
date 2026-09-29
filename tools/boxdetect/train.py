"""有独立内存看护进程的 CPU 训练，逐轮原子发布面板状态。"""
import argparse
import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.boxdetect.common import atomic_json, sha256


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


def memory_available():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            available = int(line.split()[1]) * 1024
            # cgroup v2 当前进程及祖先的剩余额度，与宿主机取较小值。
            try:
                relative = next(x.split(':',2)[2] for x in Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::'))
                base = Path('/sys/fs/cgroup')
                current = base / relative.lstrip('/')
                for folder in [current, *current.parents]:
                    if not folder.is_relative_to(base): break
                    if folder == base and not (folder/'memory.max').exists():
                        continue  # cgroup v2 根层不提供 memory.max，无此层限额。
                    limit = (folder/'memory.max').read_text().strip()
                    used = int((folder/'memory.current').read_text())
                    if limit != 'max': available = min(available, max(0,int(limit)-used))
            except (OSError,ValueError,StopIteration):
                raise RuntimeError('无法读取 cgroup 内存边界，拒绝无保护启动')
            return available
    raise RuntimeError('无法读取可用内存，拒绝无保护启动')


def process_tree_rss(pid):
    processes = {}
    for path in Path('/proc').glob('[0-9]*/status'):
        try:
            values = {line.split(':', 1)[0]: line.split(':', 1)[1].strip() for line in path.read_text().splitlines() if ':' in line}
            processes[int(path.parent.name)] = (int(values['PPid']), int(values.get('VmRSS', '0 kB').split()[0]) * 1024)
        except (OSError, ValueError, KeyError):
            continue
    family = {pid}
    while True:
        expanded = family | {p for p, (parent, _) in processes.items() if parent in family}
        if expanded == family:
            break
        family = expanded
    return sum(processes.get(p, (0, 0))[1] for p in family)


def worker(args):
    os.environ.update(OMP_NUM_THREADS=str(args.threads), MKL_NUM_THREADS=str(args.threads),
                      OPENBLAS_NUM_THREADS=str(args.threads), NUMEXPR_NUM_THREADS=str(args.threads),
                      YOLO_CONFIG_DIR=str(Path(args.run).parent.parent / 'config'), YOLO_AUTOINSTALL='false')
    if hasattr(os, 'sched_setaffinity'):
        os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:args.threads])
    os.nice(max(0, 19-os.getpriority(os.PRIO_PROCESS, 0)))
    import torch
    import importlib.metadata
    from ultralytics import YOLO
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    run = Path(args.run)
    dataset = Path(args.dataset)
    fingerprint = sha256(dataset / 'manifest.json')
    identity = {'dataset': str(dataset.resolve()), 'manifest_sha256': fingerprint, 'data_yaml_sha256': sha256(dataset/'data.yaml'),
                'imgsz': args.imgsz, 'batch': args.batch, 'epochs': args.epochs,
                'threads': args.threads, 'weights': str(Path(args.weights).resolve()),
                'weights_sha256': sha256(args.weights)}
    if args.resume:
        if json.loads((run / 'identity.json').read_text()) != identity:
            raise ValueError('续训的数据或参数与原实验不同')
        checkpoint = run / 'weights' / 'last.pt'
        if not checkpoint.exists():
            raise ValueError('没有 last.pt，不能续训')
        model = YOLO(checkpoint)
    else:
        atomic_json(run / 'identity.json', identity)
        atomic_json(run/'environment.json', {name:importlib.metadata.version(name) for name in ('torch','ultralytics','onnx','onnxruntime','numpy','pillow')})
        model = YOLO(args.weights)
    state = {'state': 'running', 'epoch': 0, 'epochs': args.epochs, 'started_at': now(),
             'updated_at': now(), 'epoch_seconds': 0, 'pid': os.getpid(), 'dataset': dataset.name}
    if args.resume:
        state.update(json.loads((run / 'status.json').read_text()))
        state.update(state='running', pid=os.getpid(), updated_at=now())
    atomic_json(run / 'status.json', state)
    began = time.monotonic()
    last_epoch = state['epoch']

    def start(trainer):
        torch.set_num_threads(args.threads)

    def epoch(trainer):
        nonlocal last_epoch
        n = trainer.epoch + 1
        # final_eval 会再触发此回调，不能伪造额外一轮。
        if n <= last_epoch or n > args.epochs or not getattr(trainer.validator, 'training', True):
            return
        last_epoch = n
        metric = {'epoch': n, 'epoch_seconds': float(trainer.epoch_time or 0)}
        metric.update({k: float(v) for k, v in trainer.label_loss_items(trainer.tloss).items()})
        metric.update({k: float(v) for k, v in trainer.metrics.items()})
        with (run / 'metrics.jsonl').open('a') as stream:
            stream.write(json.dumps(metric) + '\n'); stream.flush(); os.fsync(stream.fileno())
        state.update(epoch=n, updated_at=now(), epoch_seconds=metric['epoch_seconds'])
        atomic_json(run / 'status.json', state)
        if time.monotonic()-began >= args.max_hours*3600:
            trainer.stop = True

    model.add_callback('on_train_start', start)
    model.add_callback('on_fit_epoch_end', epoch)
    try:
        kwargs = dict(data=str(dataset / 'data.yaml'), device='cpu', epochs=args.epochs, imgsz=args.imgsz,
                      batch=args.batch, workers=0, project=str(run.parent), name=run.name, exist_ok=True,
                      seed=20260929, cache=False, amp=False, plots=False, patience=40,
                      mosaic=0, fliplr=0, flipud=0, degrees=0, translate=.05, scale=.15,
                      close_mosaic=0, optimizer='AdamW', lr0=.001, deterministic=True)
        if args.resume:
            kwargs['resume'] = True
        model.train(**kwargs)
        state.update(state='done', updated_at=now(), total_seconds=time.monotonic()-began)
        atomic_json(run / 'status.json', state)
    except BaseException as exc:
        state.update(state='failed', updated_at=now(), error=str(exc)[:1000])
        atomic_json(run / 'status.json', state)
        raise


def supervise(args):
    run = Path(args.run).resolve()
    if run.exists() and not args.resume:
        raise ValueError('实验目录已存在，必须换实验名或使用 --resume')
    if memory_available() < 4 * 1024**3:
        raise ValueError('可用内存不足 4 GiB，暂不启动训练')
    run.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], '--worker']
    def interrupted(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, interrupted)
    peak = 0; reason = None; started = time.monotonic()
    with (run / 'train.log').open('a') as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while child.poll() is None:
                rss = process_tree_rss(child.pid); peak = max(peak, rss)
                if memory_available() < 2 * 1024**3:
                    reason = '可用内存低于 2 GiB，保护性停止；减半 batch 后换实验名重试'
                elif rss > args.max_rss_gib * 1024**3:
                    reason = f'训练进程树超过 {args.max_rss_gib} GiB 内存上限，保护性停止'
                elif time.monotonic()-started > (args.max_hours*3600 + 180):
                    reason = '训练超出时间预算，已停止'
                if reason:
                    break
                time.sleep(.5)
        except BaseException:
            reason = '看护进程被中断，已停止训练子进程'
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL); child.wait()
    path = run / 'status.json'
    state = json.loads(path.read_text()) if path.exists() else {'epoch': 0, 'epochs': args.epochs, 'dataset': Path(args.dataset).name}
    state.update(updated_at=now(), peak_rss_bytes=peak, wall_seconds=time.monotonic()-started)
    if reason or child.returncode:
        state.update(state='failed', error=reason or f'训练退出码 {child.returncode}；见 train.log')
    atomic_json(path, state)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 1 if reason or child.returncode else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--weights', default=str(Path.home() / 'omrs-train/pretrained/yolov8n.pt'))
    parser.add_argument('--epochs', type=int, default=120)
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--batch', type=int, default=4)
    parser.add_argument('--threads', type=int, default=6)
    parser.add_argument('--max-hours', type=float, default=4)
    parser.add_argument('--max-rss-gib', type=float, default=6)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not (1 <= args.threads <= 6 and 1 <= args.batch <= 16 and 32 <= args.imgsz <= 960 and args.imgsz % 32 == 0 and args.epochs > 0 and 0 < args.max_hours <= 4 and 0 < args.max_rss_gib <= 8):
        parser.error('线程 1–6、batch 1–16、输入 32–960 且为 32 的倍数、轮数正数、时间不超过 4 小时、RSS 不超过 8 GiB')
    if args.worker:
        worker(args)
    else:
        sys.exit(supervise(args))


if __name__ == '__main__':
    main()
