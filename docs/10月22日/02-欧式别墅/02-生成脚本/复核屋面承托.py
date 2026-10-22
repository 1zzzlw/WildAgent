"""对实际屋面承托组运行原检查器；保留全图误判，不改写整体报告。"""
import json
import sys
from hashlib import sha256
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'wild-server'))
from app.tools.spatial_tools import get_roof_support_bounds, validate_roof_coverage

source = HERE/'玫庭庄园-欧式别墅.wild'
bp = json.loads(source.read_bytes())
elements = {e['id']: e for e in bp['geometry']['elements']}
groups = [('main_roof', ['front_u', 'back_u', 'west_u', 'east_u']),
          ('winter_roof', ['winter_front', 'winter_east', 'winter_back'])]
groups += [(f'dormer_roof_{j}', [f'dormer_{j}_{side}' for side in ['f', 'b', 'l', 'r']]) for j in range(3)]
rows = []
for roof_id, wall_ids in groups:
    roof, walls = elements[roof_id], [elements[i] for i in wall_ids]
    xs = [v for w in walls for v in [w['from'][0]-w['thickness']/2, w['to'][0]+w['thickness']/2]]
    zs = [v for w in walls for v in [w['from'][2]-w['thickness']/2, w['to'][2]+w['thickness']/2]]
    x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
    cx, y, cz = roof['position']
    roof_bounds = [cx-roof['span']/2, cz-roof['depth']/2, cx+roof['span']/2, cz+roof['depth']/2]
    covers = roof_bounds[0] <= x0 and roof_bounds[1] <= z0 and roof_bounds[2] >= x1 and roof_bounds[3] >= z1
    gaps = [round(y-max(w['from'][1], w['to'][1]), 6) for w in walls]
    report = validate_roof_coverage.invoke({'blueprint': {'geometry': {'elements': walls+[roof], 'components': []}}})
    rows.append(dict(roof=roof_id, support_wall_ids=wall_ids, original_checker_output=report,
                     original_support_bounds=get_roof_support_bounds(walls, roof),
                     independent_wall_envelope_including_thickness=[x0, z0, x1, z1],
                     roof_envelope=roof_bounds, covers_walls=covers,
                     base_minus_wall_top=gaps, passed=covers and all(abs(g) < 1e-6 for g in gaps) and '❌' not in report))
out = dict(source_sha256=sha256(source.read_bytes()).hexdigest(),
           scope='逐屋面实际承托组；没有修改输入或全图校验报告，也未宣称全图流水线通过',
           original_global_limitation='全图 _stepped_support_y 将嵌在主坡内的老虎窗当成退台，改用主楼墙顶与外包络',
           groups=rows, all_groups_passed=all(r['passed'] for r in rows))
target = HERE/'04-校验'/'屋面承托逐组复核.json'
target.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(out, ensure_ascii=False, indent=2))
sys.exit(0 if out['all_groups_passed'] else 1)
