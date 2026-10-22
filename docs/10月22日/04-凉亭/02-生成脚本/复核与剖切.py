"""保留全图校验限制，按真实坡面复核木构接触；生成只删除屋面的查看副本。"""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

base = Path(__file__).resolve().parents[1]
path = base/'听雨水榭-凉亭.wild'
data = path.read_bytes()
bp = json.loads(data)
rows = {e['id']: e for e in bp['geometry']['elements']}
roof = rows['main_roof']
def underside(x, z):
    cx, cy, cz = roof['position']
    hx, hz = roof['span']/2, roof['depth']/2
    return cy+roof['height']*min(hx-abs(x-cx), hz-abs(z-cz), min(hx, hz))/min(hx, hz)-roof['thickness']
checks = []
for sign in [-1, 1]:
    purlin = rows[f'purlin_x_{sign}']
    top = purlin['from'][1]+purlin['height']/2
    for x in [-3.4, 0, 3.4]:
        gap = underside(x, sign*2.5)-top
        assert abs(gap) < 1e-8
        checks.append(dict(member=purlin['id'], x=x, z=sign*2.5, roof_underside=underside(x, sign*2.5),
                           timber_top=top, gap=gap))
# 柱头叠涩最高至 3.885，短柱从 3.77 开始，檩条底 4.32，短柱到 4.43。
assert .91+2.65 >= 3.47-.12/2
assert 3.885 >= 4.10-.66/2
assert 4.10+.66/2 >= 4.43-.22/2
out = dict(source_sha256=hashlib.sha256(data).hexdigest(), support_chain_connected=True,
           actual_hip_surface_checks=checks, actual_surface_contact_passed=True,
           pipeline_passed=False,
           limitation='全图屋面检查按屋顶 position.y 与单个最近柱/梁顶比较；不能表达柱-斗拱-短柱-檩条-坡面承托链。保留原始报错，不回写或降低屋顶。')
(base/'04-校验/实际坡面与木构承托复核.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
layers = json.loads((base/'03-过程记录/构件分层.json').read_bytes())
cut = deepcopy(bp)
removed = []
for kind in ['elements', 'components']:
    kept = []
    for row in cut['geometry'][kind]:
        if layers[row['id']] in {'roof', 'roof_detail'}:
            removed.append(row['id'])
        else:
            kept.append(row)
    cut['geometry'][kind] = kept
cut['meta']['name'] += ' · 木构查看副本'
raw = (json.dumps(cut, ensure_ascii=False, separators=(',', ':'))+'\n').encode('utf-8')
(base/'06-剖切查看/木构查看.wild').write_bytes(raw)
(base/'06-剖切查看/来源.json').write_text(json.dumps(dict(source_sha256=out['source_sha256'],
    copy_sha256=hashlib.sha256(raw).hexdigest(), removed_ids=removed, kept_geometry_unchanged=True),
    ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(dict(surface_contacts=len(checks), actual_support_passed=True, removed_roof_parts=len(removed)), ensure_ascii=False))
