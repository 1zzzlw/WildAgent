"""核对最终证据并更新项目skill分发包；不安装全局skill，不修改业务代码。"""
import difflib
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
ROOT=BASE.parents[2]
PACKAGE=ROOT/'docs/10月23日/蓝图技能'
SKILL=PACKAGE/'wild-blueprint-authoring'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,data): path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def now(): return datetime.now(timezone(timedelta(hours=8))).isoformat()
commands=[]
def run(args):
    start=now()
    result=subprocess.run([str(a) for a in args],cwd=ROOT,text=True,encoding='utf-8',errors='replace',capture_output=True)
    commands.append(dict(command=[str(a) for a in args],cwd=str(ROOT),started_at=start,ended_at=now(),
                         exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr))
    save(HERE/'验收命令.json',commands)
    if result.returncode: raise RuntimeError(result.stderr or result.stdout)
    return result.stdout

# 原Skill验证器read_text默认GBK失败已记录；此处仅以UTF-8模式执行同一检查器。
validator=Path('C:/Users/Administrator/.codex/skills/.system/skill-creator/scripts/quick_validate.py')
print(run([sys.executable,'-X','utf8',validator,SKILL]))
wild=BASE/'棕影水院-现代热带别墅.wild'
before=wild.read_bytes()
print(run([sys.executable,'-X','utf8',BASE/'02-生成/展开本方案.py']))
assert wild.read_bytes()==before, '重放结果不一致'
static=json.loads((BASE/'03-验证/静态与空间检查.json').read_text('utf-8'))
assert static['ok'] and static['input_sha256']==sha(wild)
assert json.loads((BASE/'02-生成/生成记录.json').read_text('utf-8'))['design_sha256']==sha(BASE/'01-设计/DesignDocument.json')

renders=[]
for rel,source in [('04-效果图/日景',wild),('04-效果图/夜景',wild),('05-剖切/效果图',BASE/'05-剖切/室内剖切.wild')]:
    m=json.loads((BASE/rel/'render_manifest.json').read_text('utf-8'))
    assert m['inputSha256']==sha(source)
    assert m['compileErrors']==m['reconstructErrors']==m['unmappedMaterials']==0
    shots=[]
    for name in m['views']:
        p=BASE/rel/(name+'.png');raw=p.read_bytes()
        assert raw[:8]==b'\x89PNG\r\n\x1a\n' and len(raw)>2000
        size=struct.unpack('>II',raw[16:24]);assert size==(1280,960)
        shots.append(dict(file=str(p.relative_to(BASE)),bytes=len(raw),size=size,sha256=sha(p)))
    renders.append(dict(directory=rel,input_sha256=m['inputSha256'],source_digest=m['sourceDigest'],
                        mesh_count=m['meshCount'],browser=m['browserVersion']['product'],images=shots))
save(BASE/'03-验证/最终验收.json',dict(ok=True,input_sha256=sha(wild),deterministic_replay=True,
    design_sha256=sha(BASE/'01-设计/DesignDocument.json'),static_and_routes=static['ok'],renders=renders,
    scope='当前项目Core与浏览器显示；不是全编辑器、后端Agent或独立模型盲测'))

changed=['wild-blueprint-authoring/SKILL.md','wild-blueprint-authoring/references/runtime.md',
         'wild-blueprint-authoring/references/independent-authoring.md','交付说明.md']
diff=[];files=[];links=[]
for rel in changed:
    p=PACKAGE/rel;old=HERE/'修改前'/rel
    a=old.read_text('utf-8').splitlines(keepends=True) if old.exists() else []
    b=p.read_text('utf-8').splitlines(keepends=True)
    diff.extend(difflib.unified_diff(a,b,fromfile='before/'+rel,tofile='after/'+rel))
    files.append(dict(file=rel,before_sha256=sha(old) if old.exists() else None,after_sha256=sha(p)))
    for href in re.findall(r'\]\(([^)]+)\)', ''.join(b)):
        if href.startswith(('http:','https:','#')): continue
        path=p.parent/href.split('#')[0]
        assert path.exists(), f'缺少链接: {p}: {href}'
        links.append(dict(source=rel,target=href,exists=True))
(HERE/'技能修改.diff').write_text(''.join(diff),encoding='utf-8')

archive=PACKAGE/'wild-blueprint-authoring.zip'
with zipfile.ZipFile(archive) as z:
    oldnames={x for x in z.namelist() if not x.endswith('/')}
    oldhash=sha(archive)
newnames=oldnames | {'wild-blueprint-authoring/references/independent-authoring.md'}
temp=PACKAGE/'wild-blueprint-authoring.new.zip'
with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for name in sorted(newnames):
        assert all(x not in ['node_modules','__pycache__','.git'] for x in Path(name).parts)
        p=PACKAGE/name;assert p.is_file(), name
        z.write(p,name)
with zipfile.ZipFile(temp) as z:
    assert z.testzip() is None
    for name in sorted(newnames):
        assert hashlib.sha256(z.read(name)).hexdigest()==sha(PACKAGE/name),name
os.replace(temp,archive)
(PACKAGE/'wild-blueprint-authoring.zip.sha256').write_text(sha(archive)+'  wild-blueprint-authoring.zip\n',encoding='utf-8')
report=dict(ok=True,scope='仅项目skill及分发ZIP；未覆盖全局安装副本、未修改业务代码',
    updated_at=now(),skill_validation='quick_validate passed with Python -X utf8',
    files=files,links=links,zip_entries=len(newnames),archive_before_sha256=oldhash,archive_sha256=sha(archive),
    zip_matches_source=True,independent_agent_test=False,
    evidence='../17-独立创作-现代热带别墅/03-验证/最终验收.json')
save(HERE/'更新校验.json',report)
save(PACKAGE/'独立创作修订核对.json',report)
source_paths=['wild-core/schema.json','wild-core/types.ts','wild-core/src/primitive/parser.ts',
    'wild-core/src/primitive/geometry/floor.ts','wild-core/src/primitive/geometry/roof.ts',
    'wild-core/src/compiler/index.ts','wild-core/src/compiler/components/door.ts','wild-core/src/compiler/components/window.ts',
    'wild-web/scripts/validate-generated.mjs','wild-web/scripts/render-baseline.mjs','wild-server/app/design/contracts.py']
save(BASE/'03-验证/源码指纹.json',[dict(file=p,sha256=sha(ROOT/p)) for p in source_paths])
print(json.dumps(dict(ok=True,wild_sha256=sha(wild),images=sum(len(x['images']) for x in renders),
                      zip_entries=len(newnames),zip_sha256=sha(archive)),ensure_ascii=False))
