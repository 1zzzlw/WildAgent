"""从实际交付 JSON 检查楼板孔、两跑梯、电梯及露台边缘；保留原件的查看副本。"""
import hashlib
import json
import math
import re
from copy import deepcopy
from pathlib import Path

base = Path(__file__).resolve().parents[1]
source = base/'云序中心-写字楼.wild'
raw = source.read_bytes()
bp = json.loads(raw)
elements = bp['geometry']['elements']
rows = {e['id']: e for k in ['elements', 'components'] for e in bp['geometry'][k]}
fingerprint = hashlib.sha256(raw).hexdigest()
holes = [(-11.1, -7.9, 1.5, 7.1), (-7.02, -4.58, 2.1, 4.5)]

def rect(e):
    return (min(e['from'][0], e['to'][0]), max(e['from'][0], e['to'][0]),
            min(e['from'][2], e['to'][2]), max(e['from'][2], e['to'][2]))
def overlap(a, b):
    return max(0, min(a[1], b[1])-max(a[0], b[0]))*max(0, min(a[3], b[3])-max(a[2], b[2]))
def floor_top(e):
    return e['from'][1]+e['thickness']
def contains(r, x, z):
    return r[0]-1e-8 <= x <= r[1]+1e-8 and r[2]-1e-8 <= z <= r[3]+1e-8

slab_checks = []
for level in range(1, 6):
    f = round(.3+level*3.9, 3)
    slabs = [e for e in elements if e['type']=='floor' and abs(floor_top(e)-f)<1e-7]
    boxes = [rect(e) for e in slabs]
    covered = sum((r[1]-r[0])*(r[3]-r[2]) for r in boxes)
    expected = 24.4*17.4-sum((h[1]-h[0])*(h[3]-h[2]) for h in holes)
    assert abs(covered-expected)<1e-7, (level, covered, expected)
    for j, ra in enumerate(boxes):
        assert all(overlap(ra, h)<1e-8 for h in holes)
        assert all(overlap(ra, rb)<1e-8 for rb in boxes[j+1:])
    slab_checks.append(dict(level=level+1, floor_top=f, slab_parts=len(slabs),
                           floor_area=covered, expected_area=expected, both_voids_clear=True, no_duplicate_area=True))

stairs = []
headroom_points = 0
for level in range(5):
    f = .3+level*3.9
    first, second = [rows[f'l{level}_stair_up_{suffix}'] for suffix in ['a', 'b']]
    landing = rows[f'l{level}_landing']
    for step in [first, second]:
        rise = step['to'][1]-step['from'][1]
        run = math.hypot(step['to'][0]-step['from'][0], step['to'][2]-step['from'][2])
        assert abs(rise-step['stepCount']*step['stepHeight'])<1e-7
        assert abs(run-step['stepCount']*step['stepDepth'])<1e-7
        for n in range(step['stepCount']):
            t = (n+.5)/step['stepCount']
            x = step['from'][0]+(step['to'][0]-step['from'][0])*t
            z = step['from'][2]+(step['to'][2]-step['from'][2])*t
            y = step['from'][1]+(n+1)*step['stepHeight']
            for slab in [e for e in elements if e['type']=='floor']:
                if contains(rect(slab), x, z) and slab['from'][1]>y+1e-6:
                    assert slab['from'][1]-y >= 2.0-1e-7, (step['id'], n, slab['id'])
            headroom_points += 1
    assert abs(first['to'][1]-floor_top(landing))<1e-7
    assert abs(second['from'][1]-floor_top(landing))<1e-7
    assert first['to'][2]==landing['from'][2]==second['from'][2]
    assert abs(second['to'][1]-(f+3.9))<1e-7
    assert abs(second['to'][2]-holes[0][2])<1e-7
    front_landing_depth = holes[0][2]-rows[f'l{level}_stair_front']['from'][2]
    assert front_landing_depth >= 1.2, ('楼层前平台不足', level+1, front_landing_depth)
    stairs.append(dict(from_level=level+1, to_level=level+2, flights=2, steps_per_flight=13,
                       intermediate_landing=floor_top(landing), arrival=f+3.9, arrival_meets_slab_edge=True,
                       front_landing_depth=front_landing_depth))

lift = rows['lift_six_stops']
cx, fy, cz = lift['position']
cab = (cx-lift['dimensions']['width']/2, cx+lift['dimensions']['width']/2,
       cz-lift['dimensions']['depth']/2, cz+lift['dimensions']['depth']/2)
assert overlap(cab, holes[1]) >= (cab[1]-cab[0])*(cab[3]-cab[2])-1e-8
assert all(abs(fy+i*lift['floorHeight']-(.3+i*3.9))<1e-7 for i in range(lift['floorCount']))
for i in range(6):
    walls = [rows[f'wall_core_l{i}_{s}'] for s in ['s', 'e', 'n', 'w']]
    assert all(abs(w['from'][1]-(.3+i*3.9))<1e-7 for w in walls)
    assert rows[f'l{i}_lift_door']['parentWall']==walls[2]['id']
terrace = rows['l5_terrace_guard']['path']
assert terrace[0][0]==terrace[1][0] and terrace[0][2]==-5.5 and terrace[1][2]==-8.65
assert rows['l5_terrace_door']['parentWall']=='l5_wall_s'
report = dict(source_sha256=fingerprint, slab_checks=slab_checks, stair_connections=stairs,
    tread_headroom_sample_points=headroom_points, all_checked_treads_have_2m_slab_headroom=True,
    cab_fits_actual_slab_void=True, elevator_stops_match_all_six_floors=True,
    shaft_walls_and_landing_doors_exist_on_all_floors=True, terrace_west_return_present=True,
    passed=True, boundary='按交付几何检查表达模型，不是结构、消防、无障碍或完整电梯设备认证。')
(base/'04-校验/楼板开口与交通复核.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

def level_of(id):
    m = re.match(r'(?:wall_core_)?l([0-5])_', id)
    return int(m[1]) if m else None

cuts = []
for name, level in [('首层', 0), ('标准层', 2), ('六层露台', 5)]:
    cut = deepcopy(bp)
    removed = []
    for kind in ['elements', 'components']:
        keep = []
        for e in bp['geometry'][kind]:
            lev = level_of(e['id'])
            remove = (lev is not None and lev>level) or e['id'].startswith('roof_')
            remove = remove or e['id']=='lift_six_stops'
            # 贯通竖片/边框会挡住剖切；只移除，不截短或移动。
            remove = remove or e['id'].startswith(('facade_fin_', 'corner_frame_', 'east_fin_'))
            remove = remove or (lev==level and '_ceiling_light_' in e['id'])
            remove = remove or (lev==level and e['type']=='light')
            if remove:
                removed.append(e['id'])
            else:
                keep.append(e)
        cut['geometry'][kind] = keep
    cut['meta']['name'] += ' · '+name+'查看副本'
    data = (json.dumps(cut, ensure_ascii=False, separators=(',', ':'))+'\n').encode('utf-8')
    path = base/'06-剖切查看'/(name+'.wild')
    path.write_bytes(data)
    origin = dict(source_sha256=fingerprint, copy_sha256=hashlib.sha256(data).hexdigest(),
                  removed_ids=removed, kept_geometry_unchanged=True,
                  note='只删除遮挡构件；电梯组件跨六层，查看副本中移除，正式文件仍有完整组件。')
    (path.parent/(name+'来源.json')).write_text(json.dumps(origin, ensure_ascii=False, indent=2), encoding='utf-8')
    cuts.append(dict(name=name, removed=len(removed)))
print(json.dumps(dict(passed=True, floors_checked=5, stairs_checked=10, headroom_points=headroom_points, cuts=cuts), ensure_ascii=False))
