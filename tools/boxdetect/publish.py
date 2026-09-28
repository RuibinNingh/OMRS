"""导出固定 ONNX 文件；显式发布时保留旧当前模型。"""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.boxdetect.common import ROLES, atomic_json, sha256


def export(run):
    os.environ.update(OMP_NUM_THREADS='3', MKL_NUM_THREADS='3', OPENBLAS_NUM_THREADS='3', YOLO_AUTOINSTALL='false',
                      YOLO_CONFIG_DIR=str(run.parent.parent / 'config'))
    import torch
    from ultralytics import YOLO
    torch.set_num_threads(3)
    identity = json.loads((run / 'identity.json').read_text())
    weights = run / 'weights/best.pt'
    output = YOLO(weights).export(format='onnx', imgsz=identity['imgsz'], dynamic=False, simplify=False,
                                  opset=17, device='cpu', nms=False, batch=1)
    target = run / 'model.onnx'
    shutil.copyfile(output, target)
    atomic_json(run / 'export.json', {'weights_sha256': sha256(weights), 'onnx_sha256': sha256(target),
                                    'imgsz': identity['imgsz']})
    return target


def publish(run, root, conf):
    import fcntl
    identity = json.loads((run / 'identity.json').read_text())
    model = run / 'model.onnx'
    if not model.exists():
        export(run)
    exported = json.loads((run / 'export.json').read_text())
    if exported['weights_sha256'] != sha256(run / 'weights/best.pt') or exported['onnx_sha256'] != sha256(model):
        raise ValueError('导出模型与当前最佳权重不一致，请重新导出')
    metadata = {'name':run.name, 'run':run.name, 'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'sha256':sha256(model), 'bytes':model.stat().st_size, 'classes':list(ROLES),
                'imgsz':identity['imgsz'], 'conf':conf, 'dataset':Path(identity['dataset']).name}
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.publish.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        stage = root / ('.publish-' + uuid.uuid4().hex)
        stage.mkdir()
        shutil.copyfile(model, stage / 'model.onnx')
        atomic_json(stage / 'model.json', metadata)
        current = root / 'current'
        archive = None
        if current.exists():
            old = json.loads((current / 'model.json').read_text())
            name = str(old.get('run', 'old'))
            if not name or Path(name).name != name or name in ('.', '..'):
                raise ValueError('旧模型元数据的实验名不合法')
            archive = root / name
            if archive.exists():
                archive = root / (name + '-' + uuid.uuid4().hex[:8])
            current.rename(archive)
        try:
            stage.rename(current)
        except OSError:
            if archive:
                archive.rename(current)
            raise
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--models', default=str(Path.home() / 'omrs-train/models'))
    parser.add_argument('--conf', type=float, default=.25)
    parser.add_argument('--export-only', action='store_true')
    args = parser.parse_args()
    if not 0 < args.conf <= 1:
        parser.error('conf 必须在 0–1 之间')
    run = Path(args.run).resolve()
    if args.export_only:
        print(export(run))
    else:
        print(json.dumps(publish(run, Path(args.models).resolve(), args.conf), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
