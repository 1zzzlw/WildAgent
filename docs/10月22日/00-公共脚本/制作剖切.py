"""从交付 WILD 仅删除遮挡构件，保存逐项来源，不移动或重建保留构件。"""
import json
import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

source = Path(sys.argv[1])
root = source.parent
bp = json.loads(source.read_bytes())
layers = json.loads((root/'03-过程记录'/'构件分层.json').read_text(encoding='utf-8'))
out = root/'06-剖切查看'
out.mkdir(parents=True, exist_ok=True)
for name, removed_layers in [('一层', {'roof', 'roof_detail', 'wall_upper', 'floor_upper', 'facade_upper', 'gate'}),
                              ('二层', {'roof', 'roof_detail', 'gate'})]:
    copy = deepcopy(bp)
    removed = []
    for kind in ['elements', 'components']:
        keep = []
        for row in bp['geometry'][kind]:
            layer = layers[row['id']]
            upper_furniture = name == '一层' and layer == 'furniture' and row.get('position', [0, 0, 0])[1] > 4
            # 一层剖切还移除上层门窗/栏杆组件；保留两跑梯和中间平台。
            upper_component = name == '一层' and kind == 'components' and (
                row.get('from', [0, 0, 0])[1] >= 4 or
                (row.get('path') and min(p[1] for p in row['path']) >= 4))
            if layer in removed_layers or upper_furniture or upper_component:
                removed.append(dict(id=row['id'], layer=layer))
            else:
                keep.append(row)
        copy['geometry'][kind] = keep
    kept_ids = {e['id'] for e in copy['geometry']['elements']}
    attached = []
    for row in copy['geometry']['components']:
        if row.get('parentWall') and row['parentWall'] not in kept_ids:
            removed.append(dict(id=row['id'], layer=layers[row['id']], reason='宿主随剖切移除'))
        else:
            attached.append(row)
    copy['geometry']['components'] = attached
    copy['meta']['name'] += ' · '+name+'查看副本'
    data = (json.dumps(copy, ensure_ascii=False, separators=(',', ':'))+'\n').encode('utf-8')
    (out/(name+'剖切.wild')).write_bytes(data)
    record = dict(source=str(source), source_sha256=sha256(source.read_bytes()).hexdigest(),
                  copy_sha256=sha256(data).hexdigest(), removed=removed,
                  kept_elements=len(copy['geometry']['elements']),
                  kept_components=len(copy['geometry']['components']), kept_geometry_unchanged=True)
    (out/(name+'来源.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(view=name, removed=len(removed), kept=record['kept_elements']), ensure_ascii=False))
