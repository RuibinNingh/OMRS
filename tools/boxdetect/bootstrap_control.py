"""部署者初始化受管模型映射；不修改systemd、不启动服务。"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from omrs.traincontrol import model_info, write


def bootstrap(root, model_dir):
    root=Path(root);home=root/'managed'
    if (home/'state.json').exists():raise ValueError('已初始化，不覆盖已有服务历史')
    meta=model_info(model_dir);name=hashlib.sha256(json.dumps(meta,sort_keys=True).encode()).hexdigest()
    folder=home/'snapshots'/name;folder.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(model_dir,folder)
    (home/'active').symlink_to(Path('snapshots')/name,target_is_directory=True)
    write(home/'state.json',{'revision':0,'current':name,'previous':None})
    return home

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True);p.add_argument('--model-dir',required=True);a=p.parse_args()
    print(bootstrap(a.root,a.model_dir))
