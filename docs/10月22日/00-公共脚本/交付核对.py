"""核对最终 WILD、校验、渲染、剖切来源和工作区边界，保存指纹清单。"""
import ast
import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

DAY = Path(__file__).resolve().parents[1]
ROOT = DAY.parents[1]
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

reference = ROOT/'docs/10月20日优化/汀院别墅-Codex.wild'
ref_manifest = read(DAY/'00-质量参考/汀院同条件渲染/render_manifest.json')
assert sha(reference) == ref_manifest['inputSha256'] == '4afbe0bb3802f232b68328e265da4d284e8dc232f7b34039aa4e238e2b91f720'
rows = []
for folder, filename, validation_file in [
    ('01-新中式别墅', '听澜合院-新中式别墅.wild', '最终项目校验.json'),
    ('02-欧式别墅', '玫庭庄园-欧式别墅.wild', '最终项目校验-含屋面误判.json')]:
    base = DAY/folder
    path = base/filename
    bp = read(path)
    fingerprint = sha(path)
    render = read(base/'05-效果图/render_manifest.json')
    report = read(base/'04-校验'/validation_file)
    assert fingerprint == render['inputSha256'] == report['sha256']
    assert not report['schema_errors']
    assert render['contextSha256'] == ref_manifest['contextSha256']
    assert render['sourceDigest'] == ref_manifest['sourceDigest']
    assert render['compileErrors'] == render['reconstructErrors'] == render['unmappedMaterials'] == 0
    assert all(__import__('math').isfinite(v) for a in render['boundingBox'].values() for v in a)
    for view in ['front', 'side', 'top', 'perspective']:
        assert (base/'05-效果图'/(view+'.png')).stat().st_size > 2000
    original = {e['id']: e for k in ['elements', 'components'] for e in bp['geometry'][k]}
    cuts = []
    for name in ['一层', '二层']:
        cutpath = base/'06-剖切查看'/(name+'剖切.wild')
        cut = read(cutpath)
        origin = read(base/'06-剖切查看'/(name+'来源.json'))
        manifest = read(base/'06-剖切查看'/name/'render_manifest.json')
        assert origin['source_sha256'] == fingerprint
        assert origin['copy_sha256'] == manifest['inputSha256'] == sha(cutpath)
        assert manifest['compileErrors'] == manifest['reconstructErrors'] == manifest['unmappedMaterials'] == 0
        assert manifest['contextSha256'] == ref_manifest['contextSha256']
        assert all(e == original[e['id']] for k in ['elements', 'components'] for e in cut['geometry'][k])
        cuts.append(dict(view=name, kept_geometry_matches_source=True, sha256=sha(cutpath)))
    row = dict(building=folder, file=filename, sha256=fingerprint,
               elements=len(bp['geometry']['elements']), components=len(bp['geometry']['components']),
               schema_passed=True, pipeline_error_steps=report['pipeline_error_steps'],
               pipeline_warning_steps=report['pipeline_warning_steps'], real_render_passed=True,
               context_matches_reference=True, mesh_count=render['meshCount'], cuts=cuts)
    if folder.startswith('02'):
        local = read(base/'04-校验/屋面承托逐组复核.json')
        assert local['source_sha256'] == fingerprint and local['all_groups_passed']
        row['all_five_roof_support_groups_passed'] = True
        row['full_pipeline_passed'] = False
    else:
        assert not report['pipeline_error_steps'] and not report['pipeline_warning_steps']
        row['full_pipeline_passed'] = True
    rows.append(row)

# 所有本轮 Markdown 本地文件链接可定位；不联网。
broken = []
for doc in DAY.rglob('*.md'):
    for link in re.findall(r'\]\(([^)]+)\)', doc.read_text(encoding='utf-8')):
        if '://' in link or link.startswith('#'):
            continue
        link = link.strip('<>').split('#', 1)[0]
        if link and not (doc.parent/link).exists():
            broken.append(dict(file=str(doc.relative_to(DAY)), link=link))
assert not broken, broken
for script in DAY.rglob('*.py'):
    ast.parse(script.read_text(encoding='utf-8'), filename=str(script))

source_files = [
    'README.md', 'docs/specs/WILD_BLUEPRINT_SPEC.md',
    'docs/10月20日优化/汀院别墅-Codex.wild',
    'docs/10月21日/V1-优化前手工基线/README.md',
    'docs/10月21日/V4-Codex设计与项目计划流程/README.md',
    'docs/10月21日/V4-Codex设计与项目计划流程/01-执行项目流程.py',
    'wild-core/schema.json', 'wild-core/package.json', 'wild-web/package.json',
    'wild-web/scripts/render-baseline.mjs', 'wild-web/scripts/validate-generated.mjs',
    'wild-core/src/primitive/geometry/roof.ts', 'wild-core/src/primitive/geometry/floor.ts',
    'wild-core/src/primitive/geometry/primitive.ts', 'wild-core/src/primitive/geometry/column.ts',
    'wild-core/src/primitive/resolver.ts', 'wild-core/src/compiler/components/door.ts',
    'wild-core/src/compiler/components/window.ts', 'wild-server/app/tools/spatial_tools.py',
    'wild-server/app/services/agent_service.py', '.codex/skills/building-blueprint-diagnostics/SKILL.md']
source_records = [dict(file=f, sha256=sha(ROOT/f), bytes=(ROOT/f).stat().st_size) for f in source_files]
(DAY/'扫描资料与源码指纹.json').write_text(json.dumps(source_records, ensure_ascii=False, indent=2), encoding='utf-8')
tracked = subprocess.run(['git', 'diff', '--name-only', 'HEAD'], cwd=ROOT, capture_output=True,
                         encoding='utf-8', check=True).stdout.strip()
assert not tracked, tracked
status = subprocess.run(['git', 'status', '--short'], cwd=ROOT, capture_output=True, encoding='utf-8', check=True).stdout
files = [dict(file=p.relative_to(DAY).as_posix(), bytes=p.stat().st_size, sha256=sha(p))
         for p in sorted(DAY.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
         and p.name != '交付核对.json']
out = dict(created_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
           reference_sha256=sha(reference), reference_unchanged=True,
           tracked_application_files_changed=False, git_status=status,
           broken_markdown_links=broken, python_syntax_passed=True, buildings=rows, files=files)
(DAY/'交付核对.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(dict(buildings=rows, files=len(files), reference_unchanged=True,
                     tracked_files_changed=False, broken_links=0), ensure_ascii=False, indent=2))
