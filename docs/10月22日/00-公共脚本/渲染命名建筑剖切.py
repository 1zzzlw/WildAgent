"""读取核对记录，顺序调用原项目 Core/WebGL 四视图入口，不修改剖切文件。"""
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
for arg in sys.argv[1:]:
    base=Path(arg).resolve()
    report=json.loads((base/'04-校验'/'交付关系核对.json').read_text(encoding='utf-8'))
    for cut in report['cuts']:
        target=base/cut['path']
        out=target.parent/'效果图'
        command=[sys.executable,str(Path(__file__).with_name('运行建筑任务.py')),str(base),'剖切-'+target.parent.name,
            'node',str(ROOT/'wild-web'/'scripts'/'render-baseline.mjs'),str(target),str(out)]
        result=subprocess.run(command,cwd=ROOT,capture_output=True,encoding='utf-8',errors='replace')
        if result.returncode:
            print(result.stdout);print(result.stderr,file=sys.stderr);sys.exit(result.returncode)
        manifest=json.loads((out/'render_manifest.json').read_text(encoding='utf-8'))
        assert manifest['inputSha256']==cut['sha256']
        assert manifest['compileErrors']==manifest['reconstructErrors']==0
        print(json.dumps(dict(cut=str(target),meshes=manifest['meshCount'],core_errors=0),ensure_ascii=False),flush=True)
