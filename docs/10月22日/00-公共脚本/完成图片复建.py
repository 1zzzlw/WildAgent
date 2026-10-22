"""已保存设计的逐栋编译、校验与真实出图；任何错误退出，不吞掉失败。"""
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
for arg in sys.argv[1:]:
    base=Path(arg).resolve();target=next(base.glob('*.wild'))
    stages=[
        ('作者编译',[sys.executable,str(HERE/'编译图片复建.py'),str(base/'01-需求与设计/DesignDocument.json')]),
        ('项目校验',[sys.executable,str(HERE/'校验蓝图.py'),str(target),str(base/'04-校验/最终项目校验.json')]),
        ('Core重建',['node',str(ROOT/'wild-web/scripts/validate-generated.mjs'),str(target)]),
        ('四视图',['node',str(ROOT/'wild-web/scripts/render-baseline.mjs'),str(target),str(base/'05-效果图')]),
        ('参考实图',['node',str(HERE/'渲染图片复建.mjs'),str(target),str(base/'05-效果图/参考视角')]),
        ('字节重放',[sys.executable,str(HERE/'编译图片复建.py'),str(base/'01-需求与设计/DesignDocument.json'),'--check']),
    ]
    for label,command in stages:
        record_name='交付-'+label
        index=1
        while (base/'03-过程记录/命令记录'/(record_name+'.json')).exists():
            index+=1;record_name='交付-'+label+'-'+str(index)
        result=subprocess.run([sys.executable,str(HERE/'运行建筑任务.py'),str(base),record_name,*command],
                              cwd=ROOT,capture_output=True,encoding='utf-8',errors='replace')
        print(target.stem,label,result.returncode,flush=True)
        if result.returncode:
            print(result.stdout);print(result.stderr,file=sys.stderr);sys.exit(result.returncode)
