"""已有设计的最终编译、只读校验、实图、剖切、字节重放，任一步失败就停止。"""
import json
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
for arg in sys.argv[1:]:
    base=Path(arg).resolve()
    target=next(base.glob('*.wild'))
    design=base/'01-需求与设计'/'DesignDocument.json'
    stages=[
        ('作者编译',[sys.executable,str(HERE/'编译命名建筑.py'),str(design)]),
        ('项目校验',[sys.executable,str(HERE/'校验蓝图.py'),str(target),str(base/'04-校验'/'最终项目校验.json')]),
        ('Core重建',['node',str(ROOT/'wild-web/scripts/validate-generated.mjs'),str(target)]),
        ('四视图',['node',str(ROOT/'wild-web/scripts/render-baseline.mjs'),str(target),str(base/'05-效果图')]),
        ('日夜与招牌',['node',str(HERE/'渲染命名建筑.mjs'),str(target),str(base/'05-效果图'/'世界环境')]),
        ('关系与剖切',[sys.executable,str(HERE/'核对命名建筑.py'),str(target)]),
        ('剖切实图',[sys.executable,str(HERE/'渲染命名建筑剖切.py'),str(base)]),
        ('字节重放',[sys.executable,str(HERE/'编译命名建筑.py'),str(design),'--check']),
    ]
    for name,cmd in stages:
        result=subprocess.run([sys.executable,str(HERE/'运行建筑任务.py'),str(base),'最终收尾-'+name,*cmd],
            cwd=ROOT,capture_output=True,encoding='utf-8',errors='replace')
        print(json.dumps(dict(building=target.stem,stage=name,exit_code=result.returncode),ensure_ascii=False),flush=True)
        if result.returncode:
            print(result.stdout);print(result.stderr,file=sys.stderr);sys.exit(result.returncode)
