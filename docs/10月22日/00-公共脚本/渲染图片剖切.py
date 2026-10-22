"""逐层查看副本仍调用原项目WebGL四视图，不复制或修图参考附件。"""
import json
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
for arg in sys.argv[1:]:
    base=Path(arg).resolve()
    report=json.loads((base/'04-校验/设计落实与交通复核.json').read_text(encoding='utf-8'))
    for cut in report['cuts']:
        target=base/cut['path'];out=target.parent/'效果图'
        result=subprocess.run([sys.executable,str(HERE/'运行建筑任务.py'),str(base),'剖切实图-'+target.parent.name,
            'node',str(ROOT/'wild-web/scripts/render-baseline.mjs'),str(target),str(out)],cwd=ROOT,capture_output=True,encoding='utf-8',errors='replace')
        if result.returncode:
            print(result.stdout);print(result.stderr,file=sys.stderr);sys.exit(result.returncode)
        m=json.loads((out/'render_manifest.json').read_text(encoding='utf-8'))
        assert m['inputSha256']==cut['sha256'] and m['compileErrors']==m['reconstructErrors']==0
        print(base.name,target.parent.name,'Core/WebGL PASS',flush=True)
