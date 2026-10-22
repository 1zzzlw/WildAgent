"""核对本次两份正式文件、重放、实际校验输入与真实渲染来源，不改写建筑。"""
import ast
import hashlib
import json
import math
import re
import struct
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
day = Path(__file__).resolve().parents[1]
root = day.parents[1]
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):
    return json.loads(path.read_bytes())

reference = root/'docs/10月20日优化/汀院别墅-Codex.wild'
ref = read(day/'00-质量参考/凉亭写字楼同条件参考/render_manifest.json')
assert sha(reference)==ref['inputSha256']=='4afbe0bb3802f232b68328e265da4d284e8dc232f7b34039aa4e238e2b91f720'
buildings = []
directories = []
for folder, filename, copy_name, views in [
    ('04-凉亭', '听雨水榭-凉亭.wild', '听雨水榭.wild', [('木构查看', '来源.json', '木构效果图')]),
    ('05-写字楼', '云序中心-写字楼.wild', '云序中心.wild', [(n, n+'来源.json', n) for n in ['首层', '标准层', '六层露台']])]:
    base = day/folder
    directories.append(base)
    source = base/filename
    fingerprint = sha(source)
    bp = read(source)
    original = {e['id']: e for k in ['elements', 'components'] for e in bp['geometry'][k]}
    assert len(original)==sum(len(bp['geometry'][k]) for k in ['elements', 'components'])
    manifest = read(base/'05-效果图/render_manifest.json')
    pipeline = read(base/'04-校验/最终项目校验.json')
    assert fingerprint==manifest['inputSha256']==pipeline['sha256']
    assert pipeline['source_unchanged'] and not pipeline['schema_errors']
    assert not pipeline['pipeline_warning_steps']
    if folder=='04-凉亭':
        assert pipeline['pipeline_error_steps']==['validate_roof_coverage']
        actual = read(base/'04-校验/实际坡面与木构承托复核.json')
        assert actual['source_sha256']==fingerprint and actual['actual_surface_contact_passed']
    else:
        assert not pipeline['pipeline_error_steps']
        actual = read(base/'04-校验/楼板开口与交通复核.json')
        assert actual['source_sha256']==fingerprint and actual['passed']
    assert sha(base/'03-过程记录/r4'/copy_name)==fingerprint
    assert sha(base/'03-过程记录/重放核验'/copy_name)==fingerprint
    assert read(base/'03-过程记录/重放核验/生成摘要.json')['sha256']==fingerprint
    render_manifests = [manifest]
    cuts = []
    for name, origin_file, image_folder in views:
        path = base/'06-剖切查看'/(name+'.wild')
        cut = read(path)
        origin = read(base/'06-剖切查看'/origin_file)
        cm = read(base/'06-剖切查看'/image_folder/'render_manifest.json')
        assert origin['source_sha256']==fingerprint
        assert origin['copy_sha256']==sha(path)==cm['inputSha256']
        kept = [e for k in ['elements', 'components'] for e in cut['geometry'][k]]
        assert all(e==original[e['id']] for e in kept)
        assert set(origin['removed_ids'])==set(original)-{e['id'] for e in kept}
        render_manifests.append(cm)
        cuts.append(dict(view=name, sha256=sha(path), kept_geometry_matches_source=True))
    for m in render_manifests:
        assert m['sourceDigest']==ref['sourceDigest'] and m['contextSha256']==ref['contextSha256']
        assert m['compileErrors']==m['reconstructErrors']==m['unmappedMaterials']==0
        assert all(math.isfinite(v) for a in m['boundingBox'].values() for v in a)
        for shot in m['shots']:
            path = root/shot['file']
            raw = path.read_bytes()
            assert raw[:8]==b'\x89PNG\r\n\x1a\n'
            assert struct.unpack('>II', raw[16:24])==(1280, 960)
            assert path.stat().st_size==shot['bytes']
    buildings.append(dict(directory=folder, file=filename, sha256=fingerprint,
        elements=len(bp['geometry']['elements']), components=len(bp['geometry']['components']),
        material_count=len(bp['materials']), real_mesh_count=manifest['meshCount'],
        schema_passed=True, pipeline_error_steps=pipeline['pipeline_error_steps'],
        pipeline_warning_steps=pipeline['pipeline_warning_steps'], real_render_errors=0,
        deterministic_replay_matches=True, render_context_matches_reference=True, cuts=cuts))

broken = []
docs = [day/'README.md', day/'00-质量参考/凉亭与写字楼对照.md']
docs += [p for base in directories for p in base.rglob('*.md')]
for doc in docs:
    for link in re.findall(r'\]\(([^)]+)\)', doc.read_text(encoding='utf-8')):
        if '://' in link or link.startswith('#'):
            continue
        target = link.strip('<>').split('#', 1)[0]
        if target and not (doc.parent/target).exists():
            broken.append(dict(file=str(doc.relative_to(day)), target=target))
assert not broken, broken
for path in [p for b in directories for p in b.rglob('*.py')]+list((day/'00-公共脚本').glob('*.py')):
    ast.parse(path.read_text(encoding='utf-8'), filename=str(path))

source_paths = ['docs/Wild蓝图设计语言.md', 'wild-core/schema.json',
    'wild-core/src/primitive/resolver.ts', 'wild-core/src/primitive/geometry/roof.ts',
    'wild-core/src/primitive/geometry/beam.ts', 'wild-core/src/primitive/geometry/stair.ts',
    'wild-core/src/compiler/components/light.ts', 'wild-core/src/compiler/components/elevator.ts',
    'wild-server/app/tools/spatial_tools.py', 'wild-server/app/tools/component_tools.py',
    'wild-web/scripts/render-baseline.mjs', 'wild-web/scripts/validate-generated.mjs',
    'docs/10月22日/00-公共脚本/构件作者工具.py', 'docs/10月22日/00-公共脚本/校验蓝图.py']
sources = [dict(file=p, bytes=(root/p).stat().st_size, sha256=sha(root/p)) for p in source_paths]
changed = subprocess.run(['git', '-c', 'core.quotepath=false', 'diff', '--name-only', 'HEAD'],
    cwd=root, capture_output=True, encoding='utf-8', check=True).stdout.splitlines()
application_changes = [p for p in changed if not p.startswith('docs/')]
assert not application_changes, application_changes
files = [dict(file=p.relative_to(day).as_posix(), bytes=p.stat().st_size, sha256=sha(p))
    for base in directories for p in sorted(base.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
report = dict(created_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
    creation_method='Codex 设计、确定性展开 WILD、项目只读校验、Chromium/WebGL 实际渲染及人工看图；未运行 Agent/RAG 或外部模型盲测',
    reference_sha256=sha(reference), reference_unchanged=True, buildings=buildings,
    broken_links=broken, python_syntax_passed=True, tracked_application_changes=application_changes,
    source_fingerprints=sources, building_files=files)
(day/'凉亭与写字楼交付核对.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(dict(buildings=buildings, files=len(files), broken_links=broken,
    reference_unchanged=True, application_changes=application_changes), ensure_ascii=False, indent=2))
