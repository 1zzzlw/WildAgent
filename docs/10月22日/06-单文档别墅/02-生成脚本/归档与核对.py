"""核对作者来源、正式文件、重放、报告与图片；仅归档本次已经生成的结果。"""
import ast
import hashlib
import json
import math
import re
import shutil
import struct
from datetime import datetime,timedelta,timezone
from pathlib import Path

base=Path(__file__).resolve().parents[1]
root=base.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
formal=base/'栖光别墅-单文档生成.wild'
fingerprint=sha(formal)
bp=read(formal)
summary=read(base/'03-过程记录/r2/生成摘要.json')
assert fingerprint==summary['sha256']==sha(base/'03-过程记录/r2/栖光别墅.wild')
assert fingerprint==sha(base/'03-过程记录/重放核验/栖光别墅.wild')
rule=root/'docs/Wild蓝图设计语言.md'
assert sha(rule)==summary['rule_sha256']=='b8ea0e85fae422871546a37381bad254ebb884ab859b9d553f16e322b0adf324'
author=base/'02-生成脚本/生成栖光别墅.py'
tree=ast.parse(author.read_text(encoding='utf-8'))
imports=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
imports += [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
assert all(n.split('.')[0] in {'argparse','hashlib','json','math','shutil','collections','pathlib'} for n in imports)
report=read(base/'04-校验/r2项目校验.json')
assert report['sha256']==fingerprint and report['source_unchanged']
assert not report['schema_errors'] and not report['pipeline_error_steps'] and not report['pipeline_warning_steps']
spatial=read(base/'04-校验/r2空间复核.json')
assert spatial['source_sha256']==fingerprint and spatial['passed']
for p in (base/'03-过程记录/r2/效果图').iterdir():
    if p.is_file():shutil.copyfile(p,base/'05-效果图'/p.name)
manifest=read(base/'05-效果图/render_manifest.json')
assert manifest['inputSha256']==fingerprint
manifests=[manifest]
cuts=[]
original={e['id']:e for k in ['elements','components'] for e in bp['geometry'][k]}
for name in ['首层','二层']:
    folder=base/'06-剖切查看/r2'/name
    cut=read(folder/'剖切.wild');origin=read(folder/'来源.json')
    kept=[e for k in ['elements','components'] for e in cut['geometry'][k]]
    assert all(e==original[e['id']] for e in kept)
    assert set(origin['removed_ids'])==set(original)-{e['id'] for e in kept}
    cm=read(folder/'效果图/render_manifest.json')
    assert origin['source_sha256']==fingerprint
    assert origin['copy_sha256']==sha(folder/'剖切.wild')==cm['inputSha256']
    manifests.append(cm)
    cp=read(base/'04-校验'/('r2'+name+'副本校验.json'))
    assert not cp['schema_errors'] and cp['sha256']==cm['inputSha256']
    cuts.append(dict(view=name,kept_geometry_matches=True,source_sha256=fingerprint,
        pipeline_error_steps=cp['pipeline_error_steps'],pipeline_warning_steps=cp['pipeline_warning_steps'],
        boundary='首层移除到达楼板、两层均移除屋面，后端完整建筑关系提示保留。'))
for m in manifests:
    assert m['compileErrors']==m['reconstructErrors']==m['unmappedMaterials']==0
    assert m['sourceDigest']==manifest['sourceDigest'] and m['contextSha256']==manifest['contextSha256']
    assert all(math.isfinite(v) for a in m['boundingBox'].values() for v in a)
    for shot in m['shots']:
        p=root/shot['file'];raw=p.read_bytes()
        assert raw[:8]==b'\x89PNG\r\n\x1a\n'
        assert struct.unpack('>II',raw[16:24])==(1280,960)
        assert len(raw)==shot['bytes'] and len(raw)>2000
logs=sorted((base/'03-过程记录/命令记录').glob('*.json'))
numbers=sorted(int(p.name.split('-',1)[0]) for p in logs)
assert numbers==list(range(1,len(numbers)+1)),numbers
broken=[]
for p in base.rglob('*.md'):
    for target in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
        resolved=p.parent/target
        # README 指向本脚本即将创建的清单，写出后再验证它存在。
        if ('://' not in target and resolved.resolve()!=(base/'04-校验/交付核对.json').resolve()
                and not resolved.exists()):broken.append((str(p),target))
assert not broken,broken
for p in base.rglob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
out=dict(created_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),formal_sha256=fingerprint,
    author_source=summary['author_source'],rule_version='1.2',rule_sha256=sha(rule),rule_unchanged=True,
    author_imports=imports,author_uses_standard_library_only=True,
    other_buildings_or_author_scripts_read_for_design=False,independent_blind_test=False,
    elements=len(bp['geometry']['elements']),components=len(bp['geometry']['components']),materials=len(bp['materials']),
    real_mesh_count=manifest['meshCount'],schema_passed=True,full_pipeline_passed=True,
    pipeline_errors=0,pipeline_warnings=0,render_errors=0,deterministic_replay_matches=True,
    cut_views=cuts,logged_commands_before_this_check=len(logs),broken_links=broken,
    scope='当前对话模型依据单文档设计，标准库脚本展开，项目仅做生成后验收和渲染。')
target=base/'04-校验/交付核对.json'
assert not target.exists()
target.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
assert target.is_file()
print(json.dumps(out,ensure_ascii=False,indent=2))
